[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    Write-Output 'JCFB_V4_PRODUCTION_TARGET_BINDING=FAIL'
    Write-Output 'FAIL: Python is unavailable for the read-only binding validator.'
    exit 1
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $RepoRoot
    $jsonOutput = & $python.Source -m tools.migration_harness --repo-root $RepoRoot production-binding
    if ($LASTEXITCODE -ne 0) {
        Write-Output 'JCFB_V4_PRODUCTION_TARGET_BINDING=FAIL'
        Write-Output 'FAIL: Binding validator process failed.'
        exit 1
    }
    try {
        $report = ($jsonOutput -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-Output 'JCFB_V4_PRODUCTION_TARGET_BINDING=FAIL'
        Write-Output 'FAIL: Binding validator output was not valid JSON.'
        exit 1
    }
}
finally {
    Set-Location -LiteralPath $previousLocation
}

if ($report.status -ne 'PASS' -or $report.production_target_identity -ne 'KNOWN' -or $report.exactly_one_production_target -ne 'PASS' -or $report.disposable_production_isolation -ne 'PASS' -or $report.secrets_stored -ne 'NO' -or $report.production_apply_gate.status -ne 'PASS') {
    Write-Output 'JCFB_V4_PRODUCTION_TARGET_BINDING=FAIL'
    foreach ($issue in @($report.issues)) {
        Write-Output ("FAIL: {0} {1}" -f $issue.code, $issue.message)
    }
    exit 1
}

Write-Output 'JCFB_V4_PRODUCTION_TARGET_BINDING=PASS'
Write-Output 'PRODUCTION_TARGET_IDENTITY=KNOWN'
Write-Output 'EXACTLY_ONE_PRODUCTION_TARGET=PASS'
Write-Output 'DISPOSABLE_PRODUCTION_ISOLATION=PASS'
Write-Output 'SECRETS_STORED_IN_BINDING=NO'
Write-Output 'PRODUCTION_HARD_BLOCK=PASS'
Write-Output 'EXPLICIT_PRODUCTION_APPLY_APPROVAL_REQUIRED=PASS'
exit 0
