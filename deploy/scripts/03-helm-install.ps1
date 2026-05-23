# =============================================================
# 03-helm-install.ps1 — Helm 一键安装/升级到 VKE（无域名 bootstrap 配置）
#
# 用法：
#   .\deploy\scripts\03-helm-install.ps1 -Registry cr-cn-beijing.volces.com `
#       -Repository <你的命名空间>/manhuaju-autopilot `
#       -Tag <git-short-sha 或 latest>
# =============================================================

param(
    [Parameter(Mandatory=$true)][string]$Registry,
    [Parameter(Mandatory=$true)][string]$Repository,
    [string]$Tag = "latest",
    [string]$Namespace = "manhuaju",
    [string]$Release = "manhuaju",
    [int]$TimeoutMinutes = 15
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Stop"

# 检查 VCR 镜像拉取凭证 (vcr-pull)
$null = kubectl -n $Namespace get secret vcr-pull 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "i 未发现 vcr-pull (镜像拉取凭证)。" -ForegroundColor Yellow
    Write-Host "  你可以选择：" -ForegroundColor Yellow
    Write-Host "  A) 如果 VCR 仓库是 public，可以跳过此步" -ForegroundColor Yellow
    Write-Host "  B) 现在创建 docker-registry secret（推荐）：" -ForegroundColor Yellow
    Write-Host "     kubectl -n $Namespace create secret docker-registry vcr-pull \\" -ForegroundColor Yellow
    Write-Host "       --docker-server=$Registry --docker-username=<VCR用户名> --docker-password=<VCR密码>" -ForegroundColor Yellow
    Write-Host ""
    $a = Read-Host "现在创建 vcr-pull? (y/N)"
    if ($a -match "^[yY]") {
        $u = Read-Host "VCR 用户名"
        $p = Read-Host "VCR 密码（输入会隐藏）" -AsSecureString
        $pPlain = [System.Net.NetworkCredential]::new("", $p).Password
        kubectl -n $Namespace create secret docker-registry vcr-pull `
            --docker-server=$Registry `
            --docker-username=$u `
            --docker-password=$pPlain
    }
}

Write-Host ""
Write-Host "→ Helm upgrade --install $Release" -ForegroundColor Cyan
Write-Host "    namespace : $Namespace"
Write-Host "    image     : $Registry/${Repository}:$Tag"
Write-Host ""

$chartRoot = (Resolve-Path "./deploy/helm/manhuaju").Path
helm upgrade --install $Release $chartRoot `
    --namespace $Namespace --create-namespace `
    -f "$chartRoot/values.yaml" `
    -f "$chartRoot/values-bootstrap.yaml" `
    --set "image.registry=$Registry" `
    --set "image.repository=$Repository" `
    --set "image.tag=$Tag" `
    --wait --timeout "${TimeoutMinutes}m"

if ($LASTEXITCODE -ne 0) {
    Write-Host "X helm upgrade 失败，查看日志：" -ForegroundColor Red
    kubectl -n $Namespace get all
    exit 3
}

Write-Host ""
Write-Host "OK 部署完成。" -ForegroundColor Green
Write-Host "→ 当前 Pod：" -ForegroundColor Cyan
kubectl -n $Namespace get pods -o wide

Write-Host "→ Service（等 1-3 分钟让 CLB 拿到公网 IP）：" -ForegroundColor Cyan
kubectl -n $Namespace get svc

Write-Host ""
Write-Host "==> 拿到 EXTERNAL-IP 后运行：" -ForegroundColor Green
Write-Host "    .\deploy\scripts\04-release-gate.ps1 -ExternalIp <你的IP>" -ForegroundColor Green
