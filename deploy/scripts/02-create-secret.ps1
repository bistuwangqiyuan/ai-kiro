# =============================================================
# 02-create-secret.ps1 — 把本地 .env 转成 VKE 上的 K8s Secret
#
# 用法： .\deploy\scripts\02-create-secret.ps1 [-Namespace manhuaju] [-EnvFile .env]
# 前置：kubectl 已配置好，能 list ns
# =============================================================

param(
    [string]$Namespace = "manhuaju",
    [string]$EnvFile = ".env",
    [string]$SecretName = "manhuaju-secrets"
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    Write-Host "X $EnvFile 不存在" -ForegroundColor Red
    exit 1
}

# 创建 namespace（幂等）
Write-Host "→ 确保 namespace $Namespace 存在 ..." -ForegroundColor Cyan
$null = kubectl get ns $Namespace 2>&1
if ($LASTEXITCODE -ne 0) {
    kubectl create namespace $Namespace
}

# kubectl 要求 --from-env-file 是纯 KEY=VALUE 行（无引号、无 export、UTF-8）。
# 我们生成一份净化版临时文件再喂给 kubectl。
$tmp = New-TemporaryFile
$pairs = 0
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    if ($line -notmatch "^([A-Z][A-Z0-9_]*)=(.*)$") { return }
    $k = $matches[1]; $v = $matches[2]
    # strip wrap quotes
    if ($v -match '^"(.*)"$' -or $v -match "^'(.*)'$") { $v = $matches[1] }
    if ($v -eq "") { return }    # 跳过空值，避免覆盖 mock 默认
    "$k=$v" | Out-File -FilePath $tmp -Append -Encoding utf8
    $pairs++
}
Write-Host "  净化后有 $pairs 条非空键值对" -ForegroundColor Yellow

# 删旧的（如果存在），再 apply 新的
$exist = kubectl -n $Namespace get secret $SecretName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "→ 删除旧 Secret ..." -ForegroundColor Cyan
    kubectl -n $Namespace delete secret $SecretName | Out-Null
}

Write-Host "→ 创建 Secret $SecretName ..." -ForegroundColor Cyan
kubectl -n $Namespace create secret generic $SecretName --from-env-file="$tmp"
Remove-Item $tmp -Force

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK Secret 已创建，键值数：" -ForegroundColor Green
    kubectl -n $Namespace get secret $SecretName -o jsonpath='{.data}' | ConvertFrom-Json | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
    Write-Host "==> 可以继续 03-helm-install.ps1" -ForegroundColor Green
    exit 0
} else {
    Write-Host "X 创建失败" -ForegroundColor Red
    exit 2
}
