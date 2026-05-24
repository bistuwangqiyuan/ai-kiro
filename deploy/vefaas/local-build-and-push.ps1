# ============================================================
# local-build-and-push.ps1 — 本地构建并推送镜像到火山 VCR (在中国境内执行)
#
# Why: GitHub Actions runner (US/EU) → 火山 VCR (Beijing) 跨境推送 ~1-3 Mbps,
# 一个 400 MB 镜像通常要 1-2 小时, 经常超时. 本地 (中国境内) 推送 50-100 Mbps,
# 通常 3-5 分钟完成.
#
# 前置:
#   - 已安装 Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/
#   - 已申请 VCR 账号 (.env 中的 VCR_USERNAME / VCR_PASSWORD)
#   - 已运行过 deploy\vefaas\provision.py --step namespace (创建 VCR 命名空间)
#
# 用法:
#   .\deploy\vefaas\local-build-and-push.ps1
#   .\deploy\vefaas\local-build-and-push.ps1 -Tag v1.0.0
#   .\deploy\vefaas\local-build-and-push.ps1 -Tag latest -PushOnly  # 跳过构建, 只推送
# ============================================================

param(
    [string]$Tag = "",
    [string]$Registry = "manhuaju-cn-beijing.cr.volces.com",
    [string]$Namespace = "manhuaju",
    [string]$Repo = "manhuaju-autopilot",
    [switch]$PushOnly,
    [switch]$NoVerify
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
H1 "0/4  Tool check"

& docker --version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    ERR "Docker not found."
    Write-Host ""
    Write-Host "  1) Install Docker Desktop for Windows:" -ForegroundColor Yellow
    Write-Host "     https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    Write-Host "  2) Reboot and ensure Docker engine is running (system tray)." -ForegroundColor Yellow
    Write-Host "  3) Re-run this script." -ForegroundColor Yellow
    exit 1
}
OK "docker present"

# 1. read VCR credentials --------------------------------------------
H1 "1/4  Load VCR credentials from .env / user env"

$envPath = Join-Path $ProjectRoot ".env"
$vcrUser = $env:VCR_USERNAME
$vcrPass = $env:VCR_PASSWORD

if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
        if ($line -match '^\s*VCR_USERNAME\s*=\s*(.+?)\s*$') { if (-not $vcrUser) { $vcrUser = $matches[1] } }
        if ($line -match '^\s*VCR_PASSWORD\s*=\s*(.+?)\s*$') { if (-not $vcrPass) { $vcrPass = $matches[1] } }
        if ($line -match '^\s*VCR_REGISTRY_HOST\s*=\s*(.+?)\s*$') { if ($Registry -eq "manhuaju-cn-beijing.cr.volces.com") { $Registry = $matches[1] } }
    }
}
if (-not $vcrUser -or -not $vcrPass) {
    ERR "VCR_USERNAME / VCR_PASSWORD missing in .env or process env."
    Write-Host "  Get permanent VCR user from console: https://console.volcengine.com/cr" -ForegroundColor Yellow
    exit 2
}
OK "VCR_USERNAME=$vcrUser  registry=$Registry"

# 2. login + tag -----------------------------------------------------
H1 "2/4  Docker login"
$vcrPass | docker login $Registry -u $vcrUser --password-stdin
if ($LASTEXITCODE -ne 0) { ERR "docker login failed"; exit 3 }
OK "logged in to $Registry"

if (-not $Tag) {
    Push-Location $ProjectRoot
    $shaShort = (git rev-parse --short HEAD 2>$null).Trim()
    Pop-Location
    if ($shaShort) { $Tag = $shaShort } else { $Tag = "local-" + (Get-Date -Format "yyyyMMddHHmm") }
}
$fullTag = "$Registry/$Namespace/${Repo}:${Tag}"
$latestTag = "$Registry/$Namespace/${Repo}:latest"
INFO "image: $fullTag  (+ :latest)"

# 3. build -----------------------------------------------------------
if (-not $PushOnly) {
    H1 "3/4  docker build (linux/amd64 slim image)"
    Push-Location $ProjectRoot
    & docker buildx build `
        --platform linux/amd64 `
        --provenance=false `
        -t $fullTag `
        -t $latestTag `
        --load `
        .
    $buildCode = $LASTEXITCODE
    Pop-Location
    if ($buildCode -ne 0) { ERR "docker build failed"; exit 4 }
    OK "image built"
} else {
    INFO "skip build (using existing local image)"
}

# 4. push ------------------------------------------------------------
H1 "4/4  docker push"
& docker push $fullTag
if ($LASTEXITCODE -ne 0) { ERR "docker push $Tag failed"; exit 5 }
& docker push $latestTag
if ($LASTEXITCODE -ne 0) { ERR "docker push latest failed"; exit 6 }
OK "pushed $fullTag"
OK "pushed $latestTag"

# 5. summary ---------------------------------------------------------
H1 "Done"
Write-Host "  Image tag pushed:" -ForegroundColor Green
Write-Host "    $fullTag" -ForegroundColor White
Write-Host "    $latestTag" -ForegroundColor White
Write-Host ""
Write-Host "  Next: provision VeFaaS function with this image:" -ForegroundColor Cyan
Write-Host "    python deploy\vefaas\provision.py --step functions --image-tag $Tag" -ForegroundColor White
Write-Host ""
