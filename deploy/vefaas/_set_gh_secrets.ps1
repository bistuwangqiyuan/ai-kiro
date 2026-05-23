# Helper script (one-shot): write VOLCENGINE_AK/SK to GitHub Secrets
param([string]$EnvPath = ".env")
$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null

$repo = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
Write-Host "repo = $repo"

$envMap = @{}
Get-Content $EnvPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $idx = $line.IndexOf("=")
        $envMap[$line.Substring(0, $idx).Trim()] = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
    }
}

$mapping = @{
    "VOLCENGINE_AK" = "VOLCENGINE_VISUAL_AK"
    "VOLCENGINE_SK" = "VOLCENGINE_VISUAL_SK"
}
foreach ($gh_name in $mapping.Keys) {
    $env_src = $mapping[$gh_name]
    $v = $envMap[$env_src]
    if (-not $v) { Write-Host "X .env missing $env_src"; continue }
    $v | gh secret set $gh_name --repo $repo --body - 2>&1 | Out-Null
    # gh secret set --body - reads from stdin via pipe
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK secret $gh_name (len=$($v.Length))" -ForegroundColor Green
    } else {
        # fallback: use --body inline (less secure since shows in process list, but works)
        gh secret set $gh_name --repo $repo --body $v 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK secret $gh_name (fallback)" -ForegroundColor Green
        } else {
            Write-Host "X secret $gh_name FAILED" -ForegroundColor Red
        }
    }
}

gh variable set VCR_REGISTRY --repo $repo --body "manhuaju" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "OK variable VCR_REGISTRY=manhuaju" -ForegroundColor Green }
gh variable set VCR_NAMESPACE --repo $repo --body "manhuaju" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "OK variable VCR_NAMESPACE=manhuaju" -ForegroundColor Green }

Write-Host ""
Write-Host "Current GitHub Secrets:"
gh secret list --repo $repo
Write-Host ""
Write-Host "Current GitHub Variables:"
gh variable list --repo $repo
