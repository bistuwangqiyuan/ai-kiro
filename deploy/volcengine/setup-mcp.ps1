# =============================================================
# setup-mcp.ps1 — 从 .env 生成 Cursor MCP 配置（火山引擎官方 MCP）
#
# 用法：.\deploy\volcengine\setup-mcp.ps1
# 输出：.cursor/mcp.json（已在 .gitignore，不会提交）
# =============================================================

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

$ProjectRoot = (Get-Item (Join-Path $PSScriptRoot "..\..")).FullName
$envFile = Join-Path $ProjectRoot ".env"
$cursorDir = Join-Path $ProjectRoot ".cursor"
$mcpFile = Join-Path $cursorDir "mcp.json"

if (-not (Test-Path $envFile)) {
    Write-Error ".env not found: $envFile"
}

$cfg = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
        $cfg[$matches[1]] = $matches[2].Trim()
    }
}

$ak = $cfg["VOLCENGINE_VISUAL_AK"]
$sk = $cfg["VOLCENGINE_VISUAL_SK"]
$tosRegion = $cfg["VOLCENGINE_TOS_REGION"]
$tosEndpoint = $cfg["VOLCENGINE_TOS_ENDPOINT"]
$tosBucket = $cfg["VOLCENGINE_TOS_BUCKET"]

if (-not $ak -or -not $sk) {
    Write-Error "VOLCENGINE_VISUAL_AK/SK missing in .env"
}

$gitBase = "git+https://github.com/volcengine/mcp-server#subdirectory=server"

function Make-UvxServer {
    param(
        [string]$Name,
        [string]$Subdir,
        [string]$Entry,
        [hashtable]$ExtraEnv = @{}
    )
    $envBlock = @{
        VOLCENGINE_ACCESS_KEY = $ak
        VOLCENGINE_SECRET_KEY = $sk
    }
    foreach ($k in $ExtraEnv.Keys) { $envBlock[$k] = $ExtraEnv[$k] }

    return @{
        command = "uvx"
        args    = @("--from", "$gitBase/$Subdir", $Entry)
        env     = $envBlock
    }
}

$servers = @{
    "volcengine-tos" = Make-UvxServer -Name "tos" -Subdir "mcp_server_tos" -Entry "mcp-server-tos" -ExtraEnv @{
        VOLCENGINE_REGION = $tosRegion
        TOS_ENDPOINT      = $tosEndpoint
        TOS_BUCKET        = $tosBucket
    }
    "volcengine-vefaas" = Make-UvxServer -Name "vefaas" -Subdir "mcp_server_vefaas_function" -Entry "mcp-server-vefaas-function"
    "volcengine-tls" = Make-UvxServer -Name "tls" -Subdir "mcp_server_tls" -Entry "mcp-server-tls"
    "volcengine-apmplus" = Make-UvxServer -Name "apmplus" -Subdir "mcp_server_apmplus" -Entry "mcp-server-apmplus"
    "volcengine-cdn" = Make-UvxServer -Name "cdn" -Subdir "mcp_server_cdn" -Entry "mcp_cdn"
    "volcengine-vke" = Make-UvxServer -Name "vke" -Subdir "mcp_server_vke" -Entry "mcp-server-vke"
    "volcengine-ecs" = Make-UvxServer -Name "ecs" -Subdir "mcp_server_ecs" -Entry "mcp-server-ecs"
    "volcengine-veimagex" = Make-UvxServer -Name "veimagex" -Subdir "mcp_server_veimagex" -Entry "mcp-server-veimagex"
    "volcengine-iam" = Make-UvxServer -Name "iam" -Subdir "mcp_server_iam" -Entry "mcp-server-iam"
    "volcengine-billing" = Make-UvxServer -Name "billing" -Subdir "mcp_server_billing" -Entry "mcp-server-billing"
}

$mcp = @{ mcpServers = $servers }
New-Item -ItemType Directory -Force -Path $cursorDir | Out-Null
$mcp | ConvertTo-Json -Depth 6 | Set-Content -Path $mcpFile -Encoding UTF8

Write-Host "[OK] wrote $mcpFile with $($servers.Count) Volcengine MCP servers" -ForegroundColor Green
Write-Host "     Restart Cursor -> Settings -> MCP to load them." -ForegroundColor Cyan
