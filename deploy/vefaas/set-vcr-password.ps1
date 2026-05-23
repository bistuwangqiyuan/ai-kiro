# =============================================================
# set-vcr-password.ps1 — 在你设完 VCR docker login 密码后，自动写入 GitHub Secrets
#
# 因为：
#   - 火山小微版 VCR (Micro) 的临时 token API 返回的 username 不能用于 docker login
#   - 必须在控制台「用户中心」手工设一个永久密码
#   - 这步是火山的限制（一辈子只做一次）
#
# 用法：
#   1. 打开 https://console.volcengine.com/cr/registry?registry=manhuaju
#      → 左侧「用户中心」
#      → 点「设置/更新密码」按钮，自己设一个强密码（至少 8 字符，含大小写+数字+符号）
#      → 复制 docker login 命令里的「用户名」（形如 cr-xxx@xxxxxxx 或 主账号ID）
#   2. 跑这个脚本：
#      .\deploy\vefaas\set-vcr-password.ps1
# =============================================================

param(
    [string]$Username = "",
    [string]$Password = "",
    [string]$Region = "cn-beijing",
    [string]$Registry = "manhuaju"
)

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host "  VCR docker login 凭证 → GitHub Secrets" -ForegroundColor Magenta
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host ""

# 1) 用户名：先从控制台直链取
if (-not $Username) {
    Write-Host "请打开下面 URL 设密码（如果已设跳过），并复制「用户名」：" -ForegroundColor Yellow
    Write-Host "  https://console.volcengine.com/cr/registry?registry=$Registry&action=cr_user_info" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  · 在「用户中心」面板找到「访问凭证」或「Docker login 用户名」" -ForegroundColor Yellow
    Write-Host "  · 形如：cr-xxxxxxxxxx@2101722825  或  2101722825" -ForegroundColor Yellow
    Write-Host ""
    $Username = Read-Host "粘贴 VCR docker login 用户名"
    if (-not $Username) { Write-Host "X 用户名不能为空"; exit 1 }
}

# 2) 密码：交互式输入（不会回显）
if (-not $Password) {
    Write-Host ""
    Write-Host "请在控制台「用户中心」→「设置密码」设一个强密码，然后粘贴到下面：" -ForegroundColor Yellow
    $sec = Read-Host "粘贴 VCR docker login 密码（不会显示）" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    if (-not $Password) { Write-Host "X 密码不能为空"; exit 1 }
}

# 3) 验证：本地试一下 docker login（如果有 docker）
$hasDocker = $false
docker --version > $null 2>&1
if ($LASTEXITCODE -eq 0) { $hasDocker = $true }

if ($hasDocker) {
    Write-Host ""
    Write-Host "本机有 docker，先做一次 login 验证 …" -ForegroundColor Cyan
    $Password | docker login "cr-$Region.volces.com" -u $Username --password-stdin 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "X docker login 失败 — 用户名或密码不对。请重跑本脚本。" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK docker login 成功" -ForegroundColor Green
    docker logout "cr-$Region.volces.com" > $null 2>&1
}

# 4) 写到 GitHub Secrets
Write-Host ""
Write-Host "写入 GitHub Secrets …" -ForegroundColor Cyan
$repo = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
Write-Host "  repo = $repo"

gh secret set VCR_USERNAME --repo $repo --body $Username 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "OK secret VCR_USERNAME (len=$($Username.Length))" -ForegroundColor Green } else { Write-Host "X VCR_USERNAME failed" -ForegroundColor Red; exit 1 }

gh secret set VCR_PASSWORD --repo $repo --body $Password 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "OK secret VCR_PASSWORD (len=$($Password.Length))" -ForegroundColor Green } else { Write-Host "X VCR_PASSWORD failed" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "完成！VCR 凭证已写入 GitHub Secrets。" -ForegroundColor Green
Write-Host ""
Write-Host "下一步：触发 GHA build："
Write-Host "  git commit --allow-empty -m 'ci: retry build with VCR creds'"
Write-Host "  git push origin main"
Write-Host ""
Write-Host "或者直接跑完整流程：" -ForegroundColor Yellow
Write-Host "  .\deploy\vefaas\serverless-go-live.ps1 -SkipGhSecrets" -ForegroundColor Yellow
Write-Host ""
