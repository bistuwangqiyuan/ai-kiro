# =============================================================
# go-live.ps1 — 一键上线指挥脚本（顺序串起 01-04）
#
# 用法： .\deploy\scripts\go-live.ps1 -Registry cr-cn-beijing.volces.com `
#           -Repository <namespace>/manhuaju-autopilot -Tag latest
# =============================================================

param(
    [Parameter(Mandatory=$true)][string]$Registry,
    [Parameter(Mandatory=$true)][string]$Repository,
    [string]$Tag = "latest",
    [string]$Namespace = "manhuaju"
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "===========================================" -ForegroundColor Magenta
Write-Host "  AI 漫剧 Autopilot v4 — 一键上线" -ForegroundColor Magenta
Write-Host "  Registry  : $Registry" -ForegroundColor Magenta
Write-Host "  Repository: $Repository" -ForegroundColor Magenta
Write-Host "  Tag       : $Tag" -ForegroundColor Magenta
Write-Host "===========================================" -ForegroundColor Magenta
Write-Host ""

& "$here\01-check-prereqs.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "X 前置检查未通过，请按上方提示处理后重试" -ForegroundColor Red
    exit 1
}

& "$here\02-create-secret.ps1" -Namespace $Namespace
if ($LASTEXITCODE -ne 0) {
    Write-Host "X Secret 创建失败" -ForegroundColor Red
    exit 2
}

& "$here\03-helm-install.ps1" -Registry $Registry -Repository $Repository -Tag $Tag -Namespace $Namespace
if ($LASTEXITCODE -ne 0) {
    Write-Host "X Helm 部署失败" -ForegroundColor Red
    exit 3
}

Write-Host ""
Write-Host "等待 LoadBalancer 拿到公网 EIP（最多 5 分钟）..." -ForegroundColor Cyan
for ($i=1; $i -le 30; $i++) {
    Start-Sleep -Seconds 10
    $ip = kubectl -n $Namespace get svc -l app.kubernetes.io/component=api -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>$null
    if ($ip) {
        Write-Host "OK EXTERNAL-IP = $ip" -ForegroundColor Green
        break
    }
    Write-Host -NoNewline "."
}
if (-not $ip) {
    Write-Host ""
    Write-Host "i EIP 还在分配中。稍后手动跑：" -ForegroundColor Yellow
    Write-Host "    .\deploy\scripts\04-release-gate.ps1" -ForegroundColor Yellow
    exit 0
}

Start-Sleep -Seconds 15  # 等 Pod 完全 ready
& "$here\04-release-gate.ps1" -ExternalIp $ip -Namespace $Namespace
