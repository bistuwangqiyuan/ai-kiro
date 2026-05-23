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
    $secrets = @{
        "VOLCENGINE_AK" = $envMap["VOLCENGINE_VISUAL_AK"]
        "VOLCENGINE_SK" = $envMap["VOLCENGINE_VISUAL_SK"]
    }
    foreach ($k in $secrets.Keys) {
        $v = $secrets[$k]
        # 直接 --body 传字符串；不要用 stdin 管道（PS 会加 \r\n 污染 secret 末尾，导致 HMAC 签名错）
        gh secret set $k --repo $repo --body $v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "secret $k (len=$($v.Length))" } else { ERR "secret $k FAILED"; exit 1 }
    }
    gh variable set VCR_REGISTRY --repo $repo --body $credInfo.registry 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_REGISTRY=$($credInfo.registry)" } else { WARN "VCR_REGISTRY failed" }
    gh variable set VCR_NAMESPACE --repo $repo --body $VcrNamespace 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "variable VCR_NAMESPACE=$VcrNamespace" } else { WARN "VCR_NAMESPACE failed" }
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
            OK "API   fn id: $($fn.api_fid)"
            OK "Worker fn id: $($fn.worker_fid)"
            if ($fn.api_endpoint) {
                OK "API endpoint: $($fn.api_endpoint)"
                $FinalEndpoint = $fn.api_endpoint
            }
        }
    } finally { Pop-Location }
}

# 6. done -----------------------------------------------------------
H1 "5/5  Live"
if ($FinalEndpoint) {
    Write-Host ""
    Write-Host "  Public API endpoint:" -ForegroundColor Green
    Write-Host "    $FinalEndpoint" -ForegroundColor White
    Write-Host ""
    Write-Host "  Health check:" -ForegroundColor Green
    Write-Host "    curl $FinalEndpoint/health" -ForegroundColor White
    Write-Host ""
    Write-Host "  Web console:" -ForegroundColor Green
    Write-Host "    Start-Process $FinalEndpoint/console.html" -ForegroundColor White
} else {
    Write-Host "  Go to https://console.volcengine.com/vefaas , click manhuaju-api -> Triggers tab -> copy URL" -ForegroundColor Yellow
}
Write-Host ""
