# =============================================================
# 04-release-gate.ps1 — 上线后验收
#
# 用法（两种之一）：
#   .\deploy\scripts\04-release-gate.ps1 -ExternalIp 1.2.3.4
#   .\deploy\scripts\04-release-gate.ps1 -BaseUrl http://1.2.3.4
#
# 默认自动从 K8s Service 取 EXTERNAL-IP（若未传参）。
# =============================================================

param(
    [string]$ExternalIp = "",
    [string]$BaseUrl = "",
    [string]$Namespace = "manhuaju"
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Continue"

if (-not $BaseUrl) {
    if (-not $ExternalIp) {
        Write-Host "→ 自动从 K8s Service 读 EXTERNAL-IP ..." -ForegroundColor Cyan
        $svc = kubectl -n $Namespace get svc -l app.kubernetes.io/component=api -o json 2>$null | ConvertFrom-Json
        if (-not $svc -or $svc.items.Count -eq 0) {
            $svc = kubectl -n $Namespace get svc manhuaju-manhuaju-api -o json 2>$null | ConvertFrom-Json
            if (-not $svc) {
                Write-Host "X 找不到 api Service" -ForegroundColor Red
                kubectl -n $Namespace get svc
                exit 1
            }
            $svc = @{items = @($svc)}
        }
        $ip = $svc.items[0].status.loadBalancer.ingress[0].ip
        if (-not $ip) {
            Write-Host "i LoadBalancer 还在分配 EXTERNAL-IP，请 1-3 分钟后再跑" -ForegroundColor Yellow
            kubectl -n $Namespace get svc
            exit 2
        }
        $ExternalIp = $ip
    }
    $BaseUrl = "http://$ExternalIp"
}

Write-Host "→ 测试 BaseUrl = $BaseUrl" -ForegroundColor Cyan

$pass = 0; $fail = 0

function Check($label, $scriptblock) {
    Write-Host -NoNewline "  $label ... "
    try {
        & $scriptblock
        Write-Host "OK" -ForegroundColor Green
        $script:pass++
    } catch {
        Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
        $script:fail++
    }
}

Check "/health 200 + status=ok" {
    $r = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 10
    if ($r.status -ne "ok") { throw "status=$($r.status)" }
}
Check "/v1/kpi 返回 v4_acceptance 8 项" {
    $r = Invoke-RestMethod "$BaseUrl/v1/kpi" -TimeoutSec 10
    if (-not $r.v4_acceptance) { throw "v4_acceptance 缺失" }
    if ($r.v4_acceptance.PSObject.Properties.Count -lt 8) { throw "v4_acceptance 不够 8 项" }
}
Check "/v1/genres 列出题材库" {
    $r = Invoke-RestMethod "$BaseUrl/v1/genres" -TimeoutSec 10
    if (-not $r.genres) { throw "genres 缺失" }
}
Check "/v1/platforms 列出分发平台" {
    $r = Invoke-RestMethod "$BaseUrl/v1/platforms" -TimeoutSec 10
    if (-not $r.platforms) { throw "platforms 缺失" }
}
Check "/ 静态 Web 控制台" {
    $r = Invoke-WebRequest "$BaseUrl/" -TimeoutSec 10 -UseBasicParsing
    if ($r.StatusCode -ne 200) { throw "HTTP $($r.StatusCode)" }
    if ($r.Content -notmatch "manhuaju|漫剧|AI") { throw "页面内容不像控制台" }
}
Check "POST /v1/projects e2e（mock or live 看 .env）" {
    $body = @{
        title = "release-gate-pilot"
        genre = "modern"
        episodes_total = 1
        duration_per_episode = 30
        novel_text = "深夜的写字楼里，林晚秋整理着最后一份合同。"
        platforms = @("douyin")
    } | ConvertTo-Json
    $r = Invoke-RestMethod "$BaseUrl/v1/projects" -Method POST -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 60
    if (-not $r.project_id) { throw "未返回 project_id" }
}

Write-Host ""
Write-Host "==> 验收完成：$pass 通过 / $fail 失败" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "→ 现在可以访问：" -ForegroundColor Cyan
Write-Host "    Web 控制台 : $BaseUrl/" -ForegroundColor Green
Write-Host "    Swagger    : $BaseUrl/docs" -ForegroundColor Green
Write-Host "    KPI        : $BaseUrl/v1/kpi" -ForegroundColor Green

if ($fail -gt 0) { exit 4 }
exit 0
