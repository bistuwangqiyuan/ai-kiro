# =============================================================
# cn-deploy-remote.ps1 — 本地 Windows 一键 SSH 部署到火山 ECS
#
# 前置：
#   - 已有一台火山 ECS（4c8g 起步，Ubuntu 22.04），并能 SSH 登录
#   - 本机有 ssh.exe（Win10+ 自带）
#
# 用法（推荐）：
#   .\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp 1.2.3.4 -EcsUser root
#
# 自定义 SSH Key：
#   .\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp 1.2.3.4 -EcsUser ubuntu -SshKey C:\path\id_rsa
#
# 跳过传 .env（用 ECS 上已有的）：
#   .\deploy\cn-easy\cn-deploy-remote.ps1 -EcsIp 1.2.3.4 -SkipEnvUpload
# =============================================================

param(
    [Parameter(Mandatory=$true)][string]$EcsIp,
    [string]$EcsUser = "root",
    [int]$EcsPort = 22,
    [string]$SshKey = "",
    [string]$ProjectDir = "/opt/manhuaju",
    [string]$GitBranch = "main",
    [switch]$SkipEnvUpload,
    [switch]$RestartOnly
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Stop"

$sshArgs = @("-p", $EcsPort, "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=20")
$scpArgs = @("-P", $EcsPort, "-o", "StrictHostKeyChecking=accept-new")
if ($SshKey) {
    if (-not (Test-Path $SshKey)) { Write-Host "X SSH key not found: $SshKey" -ForegroundColor Red; exit 1 }
    $sshArgs += @("-i", $SshKey)
    $scpArgs += @("-i", $SshKey)
}
$target = "$EcsUser@$EcsIp"

function Run-Remote([string]$cmd) {
    Write-Host ">> $cmd" -ForegroundColor DarkCyan
    & ssh @sshArgs $target $cmd
    if ($LASTEXITCODE -ne 0) { throw "remote command failed: $cmd" }
}

function Copy-To-Remote([string]$src, [string]$dst) {
    Write-Host ">> scp $src -> $($target):$dst" -ForegroundColor DarkCyan
    & scp @scpArgs $src "$($target):$dst"
    if ($LASTEXITCODE -ne 0) { throw "scp failed: $src" }
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Magenta
Write-Host "  AI 漫剧 v4 — 远程一键部署到 ECS" -ForegroundColor Magenta
Write-Host "  Target : $EcsUser@$EcsIp`:$EcsPort" -ForegroundColor Magenta
Write-Host "  Dir    : $ProjectDir" -ForegroundColor Magenta
Write-Host "===========================================" -ForegroundColor Magenta
Write-Host ""

if ($RestartOnly) {
    Run-Remote "cd $ProjectDir && bash deploy/cn-easy/cn-deploy.sh --restart"
    exit 0
}

# 1) 确认 ECS 可达
Write-Host "[1/4] ping ECS ..." -ForegroundColor Cyan
Run-Remote "uname -a && cat /etc/os-release | head -3"

# 2) 上传 .env（如果本地有）
if (-not $SkipEnvUpload) {
    if (Test-Path ".env") {
        Write-Host "[2/4] 上传本地 .env 到 ECS ..." -ForegroundColor Cyan
        Run-Remote "sudo mkdir -p $ProjectDir && sudo chown -R $EcsUser $ProjectDir"
        Copy-To-Remote ".env" "$ProjectDir/.env"
    } else {
        Write-Host "[2/4] 本地未发现 .env；ECS 上 deploy 时会从模板复制" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/4] 跳过 .env 上传（--SkipEnvUpload）" -ForegroundColor Yellow
}

# 3) 远程执行 cn-deploy.sh
Write-Host "[3/4] 在 ECS 上跑 cn-deploy.sh ..." -ForegroundColor Cyan
$bootCmd = @"
set -e
if [ ! -d $ProjectDir/.git ]; then
    sudo mkdir -p $ProjectDir
    sudo chown -R \$USER $ProjectDir
    git clone --depth 1 -b $GitBranch https://github.com/bistuwangqiyuan/ai-kiro.git $ProjectDir
fi
cd $ProjectDir
sudo bash deploy/cn-easy/cn-deploy.sh
"@
Run-Remote $bootCmd

# 4) 拿到 EIP + 健康检查
Write-Host "[4/4] 验收 ..." -ForegroundColor Cyan
$health = & ssh @sshArgs $target "curl -fsS -m 5 http://127.0.0.1/health || echo FAIL"
Write-Host "ECS internal /health : $health"

Write-Host ""
Write-Host "==> 验收链接：" -ForegroundColor Green
Write-Host "    Web 控制台 : http://$EcsIp/" -ForegroundColor Green
Write-Host "    API 文档   : http://$EcsIp/docs" -ForegroundColor Green
Write-Host "    KPI 看板   : http://$EcsIp/v1/kpi" -ForegroundColor Green
Write-Host ""
Write-Host "    实时日志   : ssh $target 'cd $ProjectDir && docker compose -f deploy/cn-easy/docker-compose.cn.yml logs -f'" -ForegroundColor Gray
