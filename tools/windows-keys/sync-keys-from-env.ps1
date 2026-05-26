# =====================================================================
# sync-keys-from-env.ps1 — One-line .env restore for a new project
#
# Usage:
#   .\tools\windows-keys\sync-keys-from-env.ps1               # writes ./.env
#   .\tools\windows-keys\sync-keys-from-env.ps1 -OutFile .env -Force
#   .\tools\windows-keys\sync-keys-from-env.ps1 -Print        # print only
# =====================================================================
[CmdletBinding()]
param(
    [string]$OutFile = ".env",
    [switch]$Force,
    [switch]$Print
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

$existing = @{}
if (Test-Path $OutFile) {
    Get-Content $OutFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            $k = $line.Substring(0, $idx).Trim()
            $existing[$k] = $true
        }
    }
}

$newLines = @()
$newLines += "# === auto-synced from Windows User env by sync-keys-from-env.ps1 ==="
$newLines += "# === " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " ==="
$writtenCount = 0
$skippedCount = 0
foreach ($k in $candidates) {
    $v = [Environment]::GetEnvironmentVariable($k, "User")
    if (-not $v) { continue }
    if ($existing.ContainsKey($k) -and -not $Force) {
        Write-Host ("  [skip] {0} already exists in {1} (use -Force to overwrite)" -f $k, $OutFile) -ForegroundColor DarkGray
        $skippedCount++
        continue
    }
    $newLines += "$k=$v"
    $writtenCount++
}

if ($Print) {
    Write-Host ""
    $newLines | ForEach-Object { Write-Host $_ }
    Write-Host ""
    Write-Host ("  printed {0} keys" -f $writtenCount) -ForegroundColor Green
    return
}

if ($writtenCount -eq 0) {
    Write-Host ("No new keys to write (all already in {0}). Try -Force." -f $OutFile) -ForegroundColor Yellow
    return
}

if (Test-Path $OutFile) {
    $existingContent = Get-Content $OutFile -Raw -Encoding UTF8
    $resolved = (Resolve-Path $OutFile).Path
} else {
    $existingContent = ""
    $resolved = Join-Path (Get-Location) $OutFile
}
if ($existingContent -and -not $existingContent.EndsWith("`n")) { $existingContent += "`n" }
$existingContent += ($newLines -join "`n") + "`n"
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($resolved, $existingContent, $utf8Bom)

Write-Host ""
Write-Host ("  [OK] wrote {0} keys to {1}; skipped {2} already-existing" -f $writtenCount, $OutFile, $skippedCount) -ForegroundColor Green
Write-Host ""
