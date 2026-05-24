# =============================================================
# aliyun-fc-go-live.ps1 — 阿里云 FC 3.0 一键全自动上线
#
# 流程：
#   0) 检查工具 (gh + python + 阿里云 SDK)
#   1) 检查 .env 是否有 ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET (引导用户)
#   2) 调 ACR OpenAPI: 发现实例 + 建命名空间 + 建仓库 + 拿临时 docker token
#   3) gh CLI: 写 GitHub Secrets (ACR_USERNAME/ACR_PASSWORD + ALIBABA_CLOUD_AK/SK)
#   4) push 空 commit -> GHA build + push 镜像到 ACR
#   5) 轮询 GHA build 直到完成
#   6) 调 FC OpenAPI: 创建 manhuaju-api + manhuaju-worker 函数 + 触发器
#   7) 输出公网 URL
#
# 用法：
#   .\deploy\aliyun-fc\aliyun-fc-go-live.ps1
#   .\deploy\aliyun-fc\aliyun-fc-go-live.ps1 -Region cn-beijing
#   .\deploy\aliyun-fc\aliyun-fc-go-live.ps1 -SkipBuild   # 镜像已 push，跳到建函数
# =============================================================

param(
    [string]$Namespace = "manhuaju",
    [string]$Repo = "manhuaju-autopilot",
    [string]$Region = "cn-hangzhou",
    [string]$AcrInstanceId = "",
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

python -c "import alibabacloud_cr20181201, alibabacloud_fc20230330" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    INFO "Installing Aliyun SDK ..."
    pip install --quiet alibabacloud-cr20181201 alibabacloud-fc20230330 alibabacloud-credentials
    if ($LASTEXITCODE -ne 0) { ERR "pip install failed"; exit 1 }
}
OK "Aliyun SDK"

# 1. load .env -------------------------------------------------------
$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) { ERR ".env not found"; exit 1 }
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim()
        $v = $v.Trim([char]34).Trim([char]39)
        $envMap[$k] = $v
    }
}

if (-not $envMap["ALIBABA_CLOUD_ACCESS_KEY_ID"] -or -not $envMap["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]) {
    Write-Host ""
    Write-Host "  你的 .env 还没填 ALIBABA_CLOUD_ACCESS_KEY_ID / SECRET" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  请去 https://ram.console.aliyun.com/manage/ak 拿你的阿里云主账号 AccessKey:" -ForegroundColor Cyan
    Write-Host "    1. 用阿里云账号登录" -ForegroundColor White
    Write-Host "    2. 「用户AccessKey」-> 「创建AccessKey」" -ForegroundColor White
    Write-Host "    3. 保存 AccessKey ID 和 Secret" -ForegroundColor White
    Write-Host ""
    Write-Host "  然后把这两行加到 .env 末尾：" -ForegroundColor Cyan
    Write-Host '    ALIBABA_CLOUD_ACCESS_KEY_ID=LTAI5tXXXXXXXXXXXX' -ForegroundColor White
    Write-Host '    ALIBABA_CLOUD_ACCESS_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXX' -ForegroundColor White
    Write-Host ""
    Write-Host "  填完后重跑这个脚本" -ForegroundColor Yellow
    exit 1
}
OK ".env loaded (Aliyun AK present)"

$credInfo = $null

# 2. ACR provision step ---------------------------------------------
if (-not $OnlyProvision) {
    H1 "1/5  Aliyun ACR namespace + repo + temp docker token"
    Push-Location $ProjectRoot
    try {
        $env:ALIBABA_CLOUD_ACCESS_KEY_ID = $envMap["ALIBABA_CLOUD_ACCESS_KEY_ID"]
        $env:ALIBABA_CLOUD_ACCESS_KEY_SECRET = $envMap["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
        $env:ALIBABA_CLOUD_REGION = $Region
        $env:ACR_NAMESPACE_NAME = $Namespace
        $env:ACR_REPO_NAME = $Repo
        if ($AcrInstanceId) { $env:ACR_INSTANCE_ID = $AcrInstanceId }

        $output = python deploy/aliyun-fc/provision.py --step credentials --json 2>&1
        if ($LASTEXITCODE -ne 0) {
            ERR "ACR provision failed"
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
        OK "ACR instance  : $($credInfo.instance_name) (id=$($credInfo.instance_id))"
        OK "ACR username  : $($credInfo.username)"
        $pwdLen = $credInfo.password.Length
        OK "ACR password  : hidden, length=$pwdLen"
        OK "image prefix  : $($credInfo.image_prefix)"
    } finally { Pop-Location }
}

# 3. GitHub secrets/vars --------------------------------------------
if (-not $SkipGhSecrets -and -not $OnlyProvision) {
    H1 "2/5  GitHub Secrets + Variables"
    $repo = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
    INFO "target repo = $repo"
    $secrets = @{
        "ALIBABA_CLOUD_ACCESS_KEY_ID"     = $envMap["ALIBABA_CLOUD_ACCESS_KEY_ID"]
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET" = $envMap["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
        "ACR_USERNAME"                    = $credInfo.username
        "ACR_PASSWORD"                    = $credInfo.password
    }
    foreach ($k in $secrets.Keys) {
        $v = $secrets[$k]
        gh secret set $k --repo $repo --body $v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "secret $k (len=$($v.Length))" } else { ERR "secret $k FAILED"; exit 1 }
    }
    gh variable set ACR_REGISTRY_HOST --repo $repo --body $credInfo.registry_host 2>&1 | Out-Null
    OK "variable ACR_REGISTRY_HOST=$($credInfo.registry_host)"
    gh variable set ACR_NAMESPACE --repo $repo --body $Namespace 2>&1 | Out-Null
    OK "variable ACR_NAMESPACE=$Namespace"
    gh variable set ACR_REPO --repo $repo --body $Repo 2>&1 | Out-Null
    OK "variable ACR_REPO=$Repo"
    gh variable set ACR_INSTANCE_ID --repo $repo --body $credInfo.instance_id 2>&1 | Out-Null
    OK "variable ACR_INSTANCE_ID=$($credInfo.instance_id)"
    gh variable set ALIBABA_CLOUD_REGION --repo $repo --body $Region 2>&1 | Out-Null
    OK "variable ALIBABA_CLOUD_REGION=$Region"
}

# 4. trigger GHA + wait ---------------------------------------------
if (-not $SkipBuild -and -not $OnlyProvision) {
    H1 "3/5  Trigger GitHub Actions build (push image to ACR)"
    Push-Location $ProjectRoot
    try {
        git commit --allow-empty -m "ci: aliyun-fc go-live build trigger" 2>&1 | Out-Null
        git push origin main 2>&1 | Out-Null
        OK "pushed empty commit"
    } finally { Pop-Location }

    INFO "polling GHA progress (max 25 minutes)..."
    $deadline = (Get-Date).AddMinutes(25)
    $runId = ""
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 20
        try {
            $latestJson = gh run list --workflow build-aliyun-fc.yml --limit 1 --json databaseId,status,conclusion,headSha 2>$null
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
            Write-Host "    poll fail (will retry)" -ForegroundColor DarkGray
        }
    }
    if ((Get-Date) -ge $deadline) { ERR "build timed out (>25min)"; exit 1 }
}

# 5. FC functions ---------------------------------------------------
$FinalEndpoint = $null
if (-not $SkipProvision) {
    H1 "4/5  Create FC functions (api + worker + triggers)"
    Push-Location $ProjectRoot
    try {
        $env:ALIBABA_CLOUD_REGION = $Region
        $env:ACR_NAMESPACE_NAME = $Namespace
        $env:ACR_REPO_NAME = $Repo
        $env:IMAGE_TAG = "latest"
        if ($credInfo) { $env:ACR_INSTANCE_ID = $credInfo.instance_id }

        $output = python deploy/aliyun-fc/provision.py --step functions --json 2>&1
        $jsonMode = $false
        $jsonText = ""
        foreach ($ln in $output) {
            $s = "$ln"
            if ($s -eq "===JSON_RESULT===") { $jsonMode = $true; continue }
            if ($jsonMode) { $jsonText += $s; break }
            Write-Host "  $s"
        }
        if ($LASTEXITCODE -ne 0) { ERR "FC provision failed"; exit 1 }
        if ($jsonText) {
            $fn = $jsonText | ConvertFrom-Json
            OK "API     fn arn: $($fn.api_arn)"
            OK "Worker  fn arn: $($fn.worker_arn)"
            if ($fn.api_endpoint) {
                OK "API endpoint: $($fn.api_endpoint)"
                $FinalEndpoint = $fn.api_endpoint
            }
        }
    } finally { Pop-Location }
}

# 6. done -----------------------------------------------------------
H1 '5/5  Live!'
if ($FinalEndpoint) {
    Write-Host ''
    Write-Host '  Public API endpoint:' -ForegroundColor Green
    Write-Host "    $FinalEndpoint" -ForegroundColor White
    Write-Host ''
    Write-Host '  Health check:' -ForegroundColor Green
    Write-Host "    curl $FinalEndpoint/health" -ForegroundColor White
    Write-Host ''
    Write-Host '  Web console:' -ForegroundColor Green
    Write-Host "    Start-Process $FinalEndpoint/console.html" -ForegroundColor White
} else {
    Write-Host '  Console: https://fc.console.aliyun.com -> manhuaju-api -> triggers -> URL' -ForegroundColor Yellow
}
Write-Host ''
