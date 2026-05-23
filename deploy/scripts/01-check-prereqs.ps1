# =============================================================
# 01-check-prereqs.ps1 — 检查上线所需的所有前置条件
#
# 用法： .\deploy\scripts\01-check-prereqs.ps1
# 退出码：0 = 全绿 / 1 = 缺工具 / 2 = 缺凭证 / 3 = K8s 连不上
# =============================================================

$ErrorActionPreference = "Continue"
$chcp = chcp 65001 | Out-Null
$ok = $true

function Has($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "[1/5] 本地工具链 ..." -ForegroundColor Cyan
foreach ($t in @("git","python","kubectl","helm","ffmpeg")) {
    if (Has $t) { Write-Host "  OK  $t" -ForegroundColor Green } else { Write-Host "  X   $t (缺) " -ForegroundColor Red; $ok = $false }
}

Write-Host "[2/5] .env 文件 ..." -ForegroundColor Cyan
if (Test-Path .env) {
    $lines = (Get-Content .env -Encoding UTF8 | Where-Object { $_ -match "^[A-Z_]+=." -and $_ -notmatch "^#" }).Count
    Write-Host "  OK  .env ($lines 条非空配置)" -ForegroundColor Green
} else {
    Write-Host "  X   .env 不存在，请从 .env.example 复制并填好" -ForegroundColor Red
    $ok = $false
}

Write-Host "[3/5] kubeconfig（VKE 集群凭证） ..." -ForegroundColor Cyan
$kc = $env:KUBECONFIG
if (-not $kc) { $kc = Join-Path $env:USERPROFILE ".kube\config" }
if (Test-Path $kc) {
    $ctx = (kubectl config current-context 2>&1)
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK  current-context = $ctx" -ForegroundColor Green
        $ns = (kubectl get ns 2>&1 | Select-String "manhuaju" | Select-Object -First 1)
        if ($ns) { Write-Host "  OK  namespace manhuaju 已存在" -ForegroundColor Green }
        else { Write-Host "  i   namespace manhuaju 尚未创建（部署时自动建）" -ForegroundColor Yellow }

        Write-Host "  -> 集群节点："
        kubectl get nodes -o wide 2>&1 | Select-Object -First 4 | ForEach-Object { Write-Host "     $_" }
    } else {
        Write-Host "  X   kubeconfig 存在但连不上集群：$ctx" -ForegroundColor Red
        Write-Host "      请在火山 VKE 控制台下载新的 kubeconfig：" -ForegroundColor Yellow
        Write-Host "      https://console.volcengine.com/vke" -ForegroundColor Yellow
        $ok = $false
    }
} else {
    Write-Host "  X   $kc 不存在" -ForegroundColor Red
    Write-Host "      在火山 VKE 控制台 → 你的集群 → 集群信息 → 下载 kubeconfig" -ForegroundColor Yellow
    Write-Host "      放到 $kc 即可（或 set 环境变量 KUBECONFIG）" -ForegroundColor Yellow
    $ok = $false
}

Write-Host "[4/5] VCR 镜像仓库登录 ..." -ForegroundColor Cyan
$vcrHost = "cr-cn-beijing.volces.com"
$vcrUser = $env:VCR_USERNAME
if (-not $vcrUser) {
    Write-Host "  i   未设 VCR_USERNAME 环境变量；docker 直接 push 时需要登录" -ForegroundColor Yellow
    Write-Host "      若用 GitHub Actions 自动构建，无需本地登录 VCR" -ForegroundColor Yellow
} else {
    Write-Host "  OK  VCR_USERNAME = $vcrUser ($vcrHost)" -ForegroundColor Green
}

Write-Host "[5/5] 最新镜像可拉取性 ..." -ForegroundColor Cyan
$img = "$vcrHost/$($env:VCR_NAMESPACE)/manhuaju-autopilot:latest"
if (Has docker) {
    docker image inspect $img 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "  OK  本地已缓存 $img" -ForegroundColor Green } else { Write-Host "  i   本地未缓存 $img（部署时由 K8s 拉）" -ForegroundColor Yellow }
} else {
    Write-Host "  i   未装 docker；部署时由 K8s 直接从 VCR 拉，无需本地" -ForegroundColor Yellow
}

Write-Host ""
if ($ok) {
    Write-Host "==> 全部前置条件已就绪，可以继续 02-create-secret.ps1" -ForegroundColor Green
    exit 0
} else {
    Write-Host "==> 还有未就绪项，请按上方红 X 处理" -ForegroundColor Red
    exit 1
}
