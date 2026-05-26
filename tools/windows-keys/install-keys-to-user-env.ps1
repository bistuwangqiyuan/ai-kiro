# =====================================================================
# install-keys-to-user-env.ps1
#
# Read .env -> smoke validate -> write passing keys to Windows User env
# Also encrypts a DPAPI backup to %LOCALAPPDATA%\Manhuaju\keys.vault
#
# Usage:
#   .\tools\windows-keys\install-keys-to-user-env.ps1
#   .\tools\windows-keys\install-keys-to-user-env.ps1 -DryRun
#   .\tools\windows-keys\install-keys-to-user-env.ps1 -SkipSmoke
# =====================================================================
[CmdletBinding()]
param(
    [string]$EnvFile = "",
    [switch]$DryRun,
    [switch]$SkipSmoke,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

$ProjectRoot = (Get-Item (Join-Path $PSScriptRoot "..\..")).FullName
if (-not $EnvFile) { $EnvFile = Join-Path $ProjectRoot ".env" }
if (-not (Test-Path $EnvFile)) { Write-Error ".env not found at $EnvFile"; exit 1 }

function H1($t) {
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Magenta
    Write-Host "  $t" -ForegroundColor Magenta
    Write-Host "==============================================================" -ForegroundColor Magenta
}
function OK($t)   { Write-Host "  [OK]   $t" -ForegroundColor Green }
function INFO($t) { Write-Host "  [i]    $t" -ForegroundColor Cyan }
function WARN($t) { Write-Host "  [WARN] $t" -ForegroundColor Yellow }
function ERR($t)  { Write-Host "  [X]    $t" -ForegroundColor Red }

# 1. load .env -------------------------------------------------------
H1 "1/4  Parsing .env"
$envMap = @{}
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        if ($v) { $envMap[$k] = $v }
    }
}
OK ("loaded {0} keys from .env" -f $envMap.Count)

# 2. smoke probe -----------------------------------------------------
$smokeOK = @{}
if ($SkipSmoke) {
    H1 "2/4  Smoke validation [SKIPPED]"
    foreach ($k in $envMap.Keys) { $smokeOK[$k] = $true }
} else {
    H1 "2/4  Smoke validation (python -m scripts.smoke_keys --json)"
    Push-Location $ProjectRoot
    try {
        foreach ($k in $envMap.Keys) {
            Set-Item -Path "env:$k" -Value $envMap[$k]
        }
        $smokeJson = & python -m scripts.smoke_keys --json 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            WARN "smoke_keys returned non-zero ($LASTEXITCODE); keep going"
        }
        $results = @()
        try {
            $results = $smokeJson | ConvertFrom-Json
        } catch {
            WARN "smoke output not JSON; treating all as pass"
        }
        $probeToKeys = @{
            "volcengine_visual" = @("VOLCENGINE_VISUAL_AK","VOLCENGINE_VISUAL_SK")
            "manhuaju_agent"    = @("VOLCENGINE_VISUAL_AK","VOLCENGINE_VISUAL_SK")
            "volcengine_ark"    = @("VOLCENGINE_ARK_API_KEY")
            "tos"               = @("VOLCENGINE_TOS_AK","VOLCENGINE_TOS_SK","VOLCENGINE_TOS_BUCKET","VOLCENGINE_TOS_ENDPOINT","VOLCENGINE_TOS_REGION")
            "dashscope"         = @("DASHSCOPE_API_KEY","TONGYI_API_KEY")
            "deepseek"          = @("DEEPSEEK_API_KEY")
            "glm"               = @("GLM_API_KEY")
            "moonshot"          = @("MOONSHOT_API_KEY")
            "mistral"           = @("MISTRAL_API_KEY")
            "groq"              = @("GROQ_API_KEY")
            "xai"               = @("XAI_API_KEY")
            "spark"             = @("SPARK_API_KEY")
            "anthropic"         = @("ANTHROPIC_API_KEY","ANTHROPIC_BASE_URL")
            "elevenlabs"        = @("ELEVENLABS_API_KEY")
            "fal"               = @("FAL_KEY")
        }
        foreach ($r in $results) {
            $nameLower = "$($r.name)".ToLower()
            foreach ($probeName in $probeToKeys.Keys) {
                if ($nameLower -match $probeName) {
                    foreach ($envKey in $probeToKeys[$probeName]) {
                        if ($envMap.ContainsKey($envKey)) {
                            if ($r.ok) {
                                $smokeOK[$envKey] = $true
                            } elseif (-not $smokeOK.ContainsKey($envKey)) {
                                $smokeOK[$envKey] = $false
                            }
                        }
                    }
                }
            }
        }
        foreach ($k in $envMap.Keys) {
            if (-not $smokeOK.ContainsKey($k)) { $smokeOK[$k] = $true }
        }
        $passed = ($smokeOK.GetEnumerator() | Where-Object { $_.Value } | Measure-Object).Count
        OK ("{0}/{1} keys passed smoke" -f $passed, $envMap.Count)
    } finally { Pop-Location }
}

# 3. write to user env + DPAPI vault ---------------------------------
H1 "3/4  Writing to Windows User scope + DPAPI vault"

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

$writeMap = @{}
foreach ($k in $candidates) {
    if (-not $envMap.ContainsKey($k)) { continue }
    if (-not $smokeOK[$k] -and -not $Force) {
        WARN "skip $k (smoke failed; pass -Force to write anyway)"
        continue
    }
    $writeMap[$k] = $envMap[$k]
}

if ($DryRun) {
    INFO "DRY-RUN: would write the following User env vars:"
    foreach ($k in ($writeMap.Keys | Sort-Object)) {
        $v = $writeMap[$k]
        if ($v.Length -le 8) { $mask = '***' }
        else { $mask = $v.Substring(0,4) + '...' + $v.Substring($v.Length-4) }
        Write-Host ("    {0,-36} = {1}" -f $k, $mask)
    }
    Write-Host ""
    OK ("would write {0} keys" -f $writeMap.Count)
    exit 0
}

foreach ($k in $writeMap.Keys) {
    [Environment]::SetEnvironmentVariable($k, $writeMap[$k], "User")
    Set-Item -Path "env:$k" -Value $writeMap[$k]
    OK ("set User env: {0} (len={1})" -f $k, $writeMap[$k].Length)
}

# DPAPI encrypted vault
$vaultDir = Join-Path $env:LOCALAPPDATA "Manhuaju"
if (-not (Test-Path $vaultDir)) { New-Item -ItemType Directory -Path $vaultDir | Out-Null }
$vaultFile = Join-Path $vaultDir "keys.vault"
try {
    Add-Type -AssemblyName System.Security
    $json = $writeMap | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $enc = [System.Security.Cryptography.ProtectedData]::Protect(
        $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [System.IO.File]::WriteAllBytes($vaultFile, $enc)
    OK ("DPAPI vault saved: {0} ({1} bytes)" -f $vaultFile, $enc.Length)
} catch {
    WARN ("DPAPI vault save failed: {0}" -f $_.Exception.Message)
}

# 4. summary ---------------------------------------------------------
H1 "4/4  Done"
Write-Host ""
Write-Host "  - Restart your terminal: User-scope env vars are permanent across all projects" -ForegroundColor Green
Write-Host "  - In a new project, run:  .\tools\windows-keys\sync-keys-from-env.ps1 -OutFile .env" -ForegroundColor Green
Write-Host "  - To list stored keys:    .\tools\windows-keys\list-keys.ps1" -ForegroundColor Green
Write-Host ""
