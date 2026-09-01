[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository root does not exist: $RepoRoot"
}

$jsonText = & python -m tools.migration_harness --repo-root $RepoRoot batch-03-validate
if ($LASTEXITCODE -ne 0) {
    throw "BATCH-03 static validator process failed with exit code $LASTEXITCODE"
}

try {
    $result = $jsonText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "BATCH-03 static validator did not emit valid JSON: $($_.Exception.Message)"
}

if ($result.status -ne 'PASS') {
    $failures = @($result.failures) -join ', '
    throw "BATCH-03 static validation failed: $failures"
}

Write-Output 'V4_BATCH_03_STATIC_VALIDATION=PASS'
Write-Output ("Checks: " + (@($result.checks.PSObject.Properties | Where-Object { $_.Value -eq 'PASS' }).Count) + ' PASS')
