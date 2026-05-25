# =============================================================
# serverless-go-live.ps1 — 火山 VeFaaS 一键全自动上线 (v3)
#
# 升级亮点：GHA 在 build 时实时调火山 OpenAPI 拿 docker login 临时 token，
# 用户连密码都不用设。
#
# 全流程：
#   0) 检查本地工具
#   1) 从 .env 读 AK/SK
#   2) 调 CR OpenAPI: 发现实例 + 确保命名空间/仓库存在
#   3) 调 gh CLI 写 GitHub Secrets/Variables（仅 AK/SK + namespace）
#   4) push 空 commit 触发 GHA build；GHA 实时拿 token 推镜像
#   5) 轮询等 build 完成
#   6) 调 VeFaaS OpenAPI 创建 manhuaju-api + manhuaju-worker
#   7) 输出公网 URL
# =============================================================

param(
    [string]$VcrNamespace = "manhuaju",
    [string]$VcrRepo = "manhuaju-autopilot",
    [string]$Region = "cn-beijing",
    [string]$VcrRegistry = "",
    [switch]$SkipGhSecrets,
    [switch]$SkipBuild,
    [switch]$SkipProvision,
    [switch]$OnlyProvision
)

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

$ProjectRoot = (Get-Item (Join-Path $PSScriptRoot "..\..")).FullName

function H1($t) {
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Magenta
    Write-Host "  $t" -ForegroundColor Magenta
    Write-Host "==============================================================" -ForegroundColor Magenta
}
function OK($t)   { Write-Host "  [OK]   $t" -ForegroundColor Green }
function INFO($t) { Write-Host "  [i]    $t" -ForegroundColor Cyan }
function WARN($t) { Write-Host "  [WARN] $t" -ForegroundColor Yellow }
function ERR($t)  { Write-Host "  [X]    $t" -ForegroundColor Red }

# 0. tool check ------------------------------------------------------
H1 "0/5  Check local tools"
foreach ($tool in @("gh","python","git")) {
    & $tool --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) { ERR "missing tool: $tool"; exit 1 }
    OK $tool
}
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { ERR "gh not logged in. Run: gh auth login"; exit 1 }
OK "gh authenticated"

python -c "import volcengine, volcenginesdkcore, volcenginesdkcr, volcenginesdkvefaas" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    INFO "Installing Volcengine SDK ..."
    pip install --quiet volcengine volcengine-python-sdk redo
    if ($LASTEXITCODE -ne 0) { ERR "pip install failed"; exit 1 }
}
OK "Volcengine SDK"

# 1. load .env -------------------------------------------------------
$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) { ERR ".env not found"; exit 1 }
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        $envMap[$k] = $v
    }
}
if (-not $envMap["VOLCENGINE_VISUAL_AK"]) { ERR ".env missing VOLCENGINE_VISUAL_AK"; exit 1 }
OK ".env loaded"

$credInfo = $null

# 2. VCR provision step ---------------------------------------------
if (-not $OnlyProvision) {
    H1 "1/5  VCR namespace + repo (OpenAPI auto)"
    Push-Location $ProjectRoot
    try {
        $env:VEFAAS_REGION = $Region
        $env:VCR_NAMESPACE_NAME = $VcrNamespace
        $env:VCR_REPO_NAME = $VcrRepo
        if ($VcrRegistry) { $env:VCR_REGISTRY_NAME = $VcrRegistry }

        $output = python deploy/vefaas/provision.py --step credentials --json 2>&1
        if ($LASTEXITCODE -ne 0) {
            ERR "VCR provision failed"
            $output | ForEach-Object { Write-Host "  $_" }
            exit 1
        }
        $jsonMode = $false
        $jsonText = ""
        foreach ($ln in $output) {
            $s = "$ln"
            if ($s -eq "===JSON_RESULT===") { $jsonMode = $true; continue }
            if ($jsonMode) { $jsonText += $s; break }
            Write-Host "  $s"
        }
        if (-not $jsonText) { ERR "No JSON output"; exit 1 }
        $credInfo = $jsonText | ConvertFrom-Json
        OK "docker username = $($credInfo.username)"
        OK "image prefix    = $($credInfo.image_prefix)"
        OK "registry        = $($credInfo.registry)"
    } finally { Pop-Location }
}

# 3. GitHub secrets/vars --------------------------------------------
if (-not $SkipGhSecrets -and -not $OnlyProvision) {
    H1 "2/5  GitHub Secrets and Variables"
    $repo = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
    INFO "target repo = $repo"

    # 必备：build 阶段 GHA 拿 VCR 临时 docker token 用
    $mustSecrets = @(
        "VOLCENGINE_VISUAL_AK", "VOLCENGINE_VISUAL_SK"
    )
    # 选填：runtime function envs（缺失自动跳过，不报错）
    $optionalSecrets = @(
        "VOLCENGINE_ARK_API_KEY",
        "VOLCENGINE_TOS_AK", "VOLCENGINE_TOS_SK", "VOLCENGINE_TOS_BUCKET",
        "VOLCENGINE_TOS_REGION", "VOLCENGINE_TOS_ENDPOINT",
        "DASHSCOPE_API_KEY", "TONGYI_API_KEY",
        "DEEPSEEK_API_KEY", "GLM_API_KEY", "MOONSHOT_API_KEY",
        "MISTRAL_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "SPARK_API_KEY",
        "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
        "ELEVENLABS_API_KEY", "FAL_KEY"
    )

    foreach ($k in $mustSecrets) {
        $v = $envMap[$k]
        if (-not $v) { ERR ".env missing required key: $k"; exit 1 }
        # 双写 — VOLCENGINE_AK/SK 是 GHA workflow 引用的旧名字，向后兼容
        $kAlt = $k -replace "_VISUAL", ""
        gh secret set $k    --repo $repo --body $v 2>&1 | Out-Null
        gh secret set $kAlt --repo $repo --body $v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "secret $k / $kAlt (len=$($v.Length))" } else { ERR "secret $k FAILED"; exit 1 }
    }

    foreach ($k in $optionalSecrets) {
        $v = $envMap[$k]
        if (-not $v) { INFO "skip optional $k (not in .env)"; continue }
        gh secret set $k --repo $repo --body $v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "secret $k (len=$($v.Length))" } else { WARN "secret $k failed" }
    }

    # VCR_REGISTRY_HOST = 域名 (FQDN), e.g. cr-cn-beijing.volces.com — GHA docker login & image URL 用
    # VCR_REGISTRY      = 实例名, e.g. manhuaju — provision.py & vefaas image discovery 用
    $regHost = if ($credInfo.image_host) { $credInfo.image_host } else { "cr-$Region.volces.com" }
    $regName = $credInfo.registry
    gh variable set VCR_REGISTRY_HOST --repo $repo --body $regHost 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_REGISTRY_HOST=$regHost" } else { WARN "VCR_REGISTRY_HOST failed" }
    gh variable set VCR_REGISTRY --repo $repo --body $regName 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_REGISTRY=$regName" } else { WARN "VCR_REGISTRY failed" }
    gh variable set VCR_NAMESPACE --repo $repo --body $VcrNamespace 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_NAMESPACE=$VcrNamespace" } else { WARN "VCR_NAMESPACE failed" }
    gh variable set VCR_REPO --repo $repo --body $VcrRepo 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_REPO=$VcrRepo" } else { WARN "VCR_REPO failed" }
}

# 4. trigger GHA + wait ---------------------------------------------
if (-not $SkipBuild -and -not $OnlyProvision) {
    H1 "3/5  Trigger GitHub Actions build"
    Push-Location $ProjectRoot
    try {
        git commit --allow-empty -m "ci: trigger build for VeFaaS deploy" 2>&1 | Out-Null
        git push origin main 2>&1 | Out-Null
        OK "pushed empty commit"
    } finally { Pop-Location }

    INFO "polling GHA progress (max 20 minutes)..."
    $deadline = (Get-Date).AddMinutes(20)
    $runId = ""
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 15
        try {
            $latestJson = gh run list --workflow build-and-deploy.yml --limit 1 --json databaseId,status,conclusion,headSha,createdAt 2>$null
            if (-not $latestJson) { continue }
            $latest = $latestJson | ConvertFrom-Json
            if ($latest -and $latest.Count -gt 0) {
                $r = $latest[0]
                if (-not $runId) { $runId = $r.databaseId; INFO "run id = $runId" }
                $sha = $r.headSha.Substring(0, [Math]::Min(8, $r.headSha.Length))
                Write-Host "    ...status=$($r.status) (sha=$sha)" -ForegroundColor DarkGray
                if ($r.status -eq "completed") {
                    if ($r.conclusion -eq "success") { OK "GHA build succeeded"; break }
                    ERR "GHA build failed (conclusion=$($r.conclusion))"
                    $owner = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
                    Write-Host "    Log: https://github.com/$owner/actions/runs/$($r.databaseId)"
                    exit 1
                }
            }
        } catch {
            Write-Host "    poll fail (will retry): $_" -ForegroundColor DarkGray
        }
    }
    if ((Get-Date) -ge $deadline) { ERR "build timed out (>20min)"; exit 1 }
}

# 5. VeFaaS functions -----------------------------------------------
$FinalEndpoint = $null
if (-not $SkipProvision) {
    H1 "4/5  Create VeFaaS functions (api + worker)"
    Push-Location $ProjectRoot
    try {
        $env:VEFAAS_REGION = $Region
        $env:VCR_NAMESPACE_NAME = $VcrNamespace
        $env:VCR_REPO_NAME = $VcrRepo
        $env:IMAGE_TAG = "latest"
        $output = python deploy/vefaas/provision.py --step functions --json 2>&1
        $jsonMode = $false
        $jsonText = ""
        foreach ($ln in $output) {
            $s = "$ln"
            if ($s -eq "===JSON_RESULT===") { $jsonMode = $true; continue }
            if ($jsonMode) { $jsonText += $s; break }
            Write-Host "  $s"
        }
        if ($LASTEXITCODE -ne 0) { ERR "VeFaaS provision failed"; exit 1 }
        if ($jsonText) {
            $fn = $jsonText | ConvertFrom-Json
            $apiFid = $fn.api_fid
            $workerFid = $fn.worker_fid
            OK ("API    fn id: {0}" -f $apiFid)
            OK ("Worker fn id: {0}" -f $workerFid)
            if ($fn.api_summary) {
                $rs = $fn.api_summary.release_status
                $inst = ($fn.api_summary.instance_states -join ",")
                OK ("API    release={0} instances=[{1}]" -f $rs, $inst)
            }
            if ($fn.worker_summary) {
                $rs = $fn.worker_summary.release_status
                $inst = ($fn.worker_summary.instance_states -join ",")
                OK ("Worker release={0} instances=[{1}]" -f $rs, $inst)
            }
            if ($fn.api_endpoint) {
                OK ("API endpoint: {0}" -f $fn.api_endpoint)
                $FinalEndpoint = $fn.api_endpoint
            }
            $script:LastApiFid = $apiFid
            $script:LastApiConsole = $fn.api_summary.console_url
        }
    } finally { Pop-Location }
}

# 6. done -----------------------------------------------------------
H1 "5/5  Live"
if ($FinalEndpoint) {
    Write-Host ""
    Write-Host "  Public API endpoint:" -ForegroundColor Green
    Write-Host ("    {0}" -f $FinalEndpoint) -ForegroundColor White
    Write-Host ""
    Write-Host "  Health check:" -ForegroundColor Green
    Write-Host ("    curl {0}/health" -f $FinalEndpoint) -ForegroundColor White
    Write-Host ""
    Write-Host "  Web console:" -ForegroundColor Green
    Write-Host ("    Start-Process {0}/console.html" -f $FinalEndpoint) -ForegroundColor White

    INFO "Probing /health endpoint ..."
    $healthOk = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri ("{0}/health" -f $FinalEndpoint) -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { OK "/health returned 200"; $healthOk = $true; break }
        } catch {
            Start-Sleep -Seconds 6
        }
    }
    if (-not $healthOk) { WARN "/health did not return 200 within 180s — check function logs in console" }
} else {
    Write-Host ""
    Write-Host "  VeFaaS function deployed but no HTTP endpoint bound yet." -ForegroundColor Yellow
    Write-Host "  VeFaaS native/v1 requires an API Gateway trigger for public HTTP access," -ForegroundColor Yellow
    Write-Host "  which the SDK cannot auto-provision. Add one in 30s via the console:" -ForegroundColor Yellow
    Write-Host ""
    if ($script:LastApiConsole) {
        Write-Host "  Function detail:" -ForegroundColor Cyan
        Write-Host ("    {0}" -f $script:LastApiConsole) -ForegroundColor White
    } else {
        Write-Host "    https://console.volcengine.com/vefaas" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "  Steps:" -ForegroundColor Cyan
    Write-Host "    1. Open the function detail page (link above)" -ForegroundColor White
    Write-Host "    2. Click 'Triggers' tab -> 'Create Trigger' -> 'API Gateway'" -ForegroundColor White
    Write-Host "    3. If no API Gateway exists, create a Serverless tier instance (free quota)" -ForegroundColor White
    Write-Host "    4. Bind the gateway to '/' path -> save" -ForegroundColor White
    Write-Host "    5. Copy the generated public URL and run:  curl <URL>/health" -ForegroundColor White
}
Write-Host ""
