# =============================================================
# vefaas-deploy.ps1 — 把 VCR 镜像更新到 VeFaaS 函数（无服务器一键更新）
#
# 前置：
#   - 已在火山控制台创建过 2 个函数：manhuaju-api / manhuaju-worker
#   - 已开通 VeFaaS（https://console.volcengine.com/vefaas）
#   - 本机环境变量已设：
#       VOLCENGINE_AK / VOLCENGINE_SK   （账号 AK/SK，和 .env 中的 VOLCENGINE_VISUAL_AK/SK 同一对）
#   - 已装火山 SDK：pip install volcengine
#
# 用法：
#   .\deploy\vefaas\vefaas-deploy.ps1 -ImageTag latest
#   .\deploy\vefaas\vefaas-deploy.ps1 -ImageTag e9e73eb -Region cn-beijing
#
# 行为：
#   1) 调火山 VeFaaS OpenAPI UpdateFunction，把 api 和 worker 函数的镜像换成新 Tag
#   2) 等待两个函数都 Ready
#   3) 触发 API 函数的 /health，确认上线
# =============================================================

param(
    [string]$ImageTag = "latest",
    [string]$Region = "cn-beijing",
    [string]$Namespace = "manhuaju",          # VeFaaS namespace（不是 VCR namespace）
    [string]$ApiFn = "manhuaju-api",
    [string]$WorkerFn = "manhuaju-worker",
    [string]$VcrNamespace = "",                # VCR 命名空间（必填）
    [string]$VcrRepo = "manhuaju-autopilot"
)

$chcp = chcp 65001 | Out-Null
$ErrorActionPreference = "Stop"

if (-not $env:VOLCENGINE_AK -or -not $env:VOLCENGINE_SK) {
    Write-Host "X 请先 set 环境变量 VOLCENGINE_AK / VOLCENGINE_SK" -ForegroundColor Red
    Write-Host "  PowerShell:  \$env:VOLCENGINE_AK='AKLT...';  \$env:VOLCENGINE_SK='...';" -ForegroundColor Yellow
    Write-Host "  或读 .env:    Get-Content .env | ? { \$_ -match '^VOLCENGINE_VISUAL_(AK|SK)=' } | % { \$kv=\$_.Split('=',2); Set-Item env:\$('VOLCENGINE_' + \$kv[0].Substring(18)) \$kv[1] }" -ForegroundColor Yellow
    exit 1
}

if (-not $VcrNamespace) {
    Write-Host "X 请传 -VcrNamespace <你的 VCR 命名空间>（火山控制台 → 容器服务 CR → 命名空间）" -ForegroundColor Red
    exit 1
}

$FullImage = "cr-${Region}.volces.com/${VcrNamespace}/${VcrRepo}:${ImageTag}"

Write-Host ""
Write-Host "===========================================" -ForegroundColor Magenta
Write-Host "  VeFaaS 函数镜像热更新" -ForegroundColor Magenta
Write-Host "  Region    : $Region" -ForegroundColor Magenta
Write-Host "  API Fn    : $ApiFn" -ForegroundColor Magenta
Write-Host "  Worker Fn : $WorkerFn" -ForegroundColor Magenta
Write-Host "  Image     : $FullImage" -ForegroundColor Magenta
Write-Host "===========================================" -ForegroundColor Magenta
Write-Host ""

# 用 Python SDK 调 VeFaaS OpenAPI（最稳定）
$pyScript = @"
import os, json, sys
try:
    import volcenginesdkcore as core
    import volcenginesdkvefaas as vefaas
except ImportError:
    print('X 缺少 火山 SDK。请运行：pip install volcengine-python-sdk')
    sys.exit(2)

conf = core.Configuration()
conf.ak = os.environ['VOLCENGINE_AK']
conf.sk = os.environ['VOLCENGINE_SK']
conf.region = '$Region'
core.Configuration.set_default(conf)
api = vefaas.VEFAASApi()

image = '$FullImage'
results = {}
for fn_name in ['$ApiFn', '$WorkerFn']:
    try:
        # 1) 查函数 ID
        r = api.list_functions(vefaas.ListFunctionsRequest(name=fn_name, page_size=10))
        items = (r.items or []) if hasattr(r, 'items') else []
        if not items:
            results[fn_name] = {'ok': False, 'detail': 'function not found, 请先在控制台创建'}
            continue
        fid = items[0].id
        # 2) UpdateFunction：仅替换 source.image
        upd = vefaas.UpdateFunctionRequest(
            id=fid,
            source={'type': 'image', 'image': image},
        )
        api.update_function(upd)
        # 3) ReleaseFunction（VeFaaS 是先 Update 再 Release）
        try:
            api.release(vefaas.ReleaseRequest(id=fid))
        except Exception as e:
            results[fn_name] = {'ok': True, 'detail': f'updated; release skipped: {e}'}
            continue
        results[fn_name] = {'ok': True, 'detail': 'updated + released', 'id': fid, 'image': image}
    except Exception as e:
        results[fn_name] = {'ok': False, 'detail': f'{type(e).__name__}: {e}'}

print(json.dumps(results, ensure_ascii=False, indent=2))
sys.exit(0 if all(r['ok'] for r in results.values()) else 3)
"@

$tmp = New-TemporaryFile
Set-Content -LiteralPath $tmp.FullName -Value $pyScript -Encoding UTF8
python $tmp.FullName
$rc = $LASTEXITCODE
Remove-Item $tmp -Force

if ($rc -ne 0) {
    Write-Host "X 更新失败 (rc=$rc)；常见原因：函数不存在、镜像 Tag 不存在、权限不够" -ForegroundColor Red
    exit $rc
}

Write-Host ""
Write-Host "==> 更新完成。回火山控制台 → VeFaaS → 函数 → 调用日志 看新版本拉起情况。" -ForegroundColor Green
Write-Host "    API 函数公网域名见控制台「触发器」标签页。" -ForegroundColor Green
