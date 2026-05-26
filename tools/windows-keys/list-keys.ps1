# =====================================================================
# list-keys.ps1 — Tabular listing of manhuaju-related Windows User env
#                 Always masks middle of values; shows first/last 4 chars
# =====================================================================
[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Plain
)
$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

$candidates = @(
    "VOLCENGINE_VISUAL_AK","VOLCENGINE_VISUAL_SK","VOLCENGINE_VISUAL_REGION",
    "VOLCENGINE_ARK_API_KEY",
    "VOLCENGINE_TOS_AK","VOLCENGINE_TOS_SK","VOLCENGINE_TOS_BUCKET","VOLCENGINE_TOS_ENDPOINT","VOLCENGINE_TOS_REGION",
    "DASHSCOPE_API_KEY","TONGYI_API_KEY",
    "DEEPSEEK_API_KEY","GLM_API_KEY","MOONSHOT_API_KEY",
    "MISTRAL_API_KEY","GROQ_API_KEY","XAI_API_KEY","SPARK_API_KEY",
    "ANTHROPIC_API_KEY","ANTHROPIC_BASE_URL",
    "ELEVENLABS_API_KEY","FAL_KEY",
    "ALIBABA_CLOUD_ACCESS_KEY_ID","ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "TENCENTCLOUD_SECRET_ID","TENCENTCLOUD_SECRET_KEY",
    "VCR_USERNAME","VCR_PASSWORD"
)

$rows = @()
foreach ($k in $candidates) {
    $v = [Environment]::GetEnvironmentVariable($k, "User")
    if (-not $v) { continue }
    $len = $v.Length
    if ($Plain) { $masked = $v }
    elseif ($len -le 8) { $masked = '***' }
    else { $masked = $v.Substring(0,4) + '...' + $v.Substring($len-4) }
    $rows += [pscustomobject]@{
        Name   = $k
        Length = $len
        Value  = $masked
    }
}

if ($Json) {
    $rows | ConvertTo-Json -Depth 3
    return
}

if ($rows.Count -eq 0) {
    Write-Host "No manhuaju keys in User env. Run .\install-keys-to-user-env.ps1 first." -ForegroundColor Yellow
    return
}
$rows | Format-Table -AutoSize
Write-Host ""
Write-Host ("  Total: {0} keys present in User env" -f $rows.Count) -ForegroundColor Green
