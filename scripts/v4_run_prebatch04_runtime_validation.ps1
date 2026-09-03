[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$PlanOnly,
    [switch]$DryRun,
    [switch]$ApplyDisposable
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..'
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$selectedModes = @($PlanOnly.IsPresent, $DryRun.IsPresent, $ApplyDisposable.IsPresent) | Where-Object { $_ }
if ($selectedModes.Count -gt 1) {
    throw 'Choose only one of -PlanOnly, -DryRun, or -ApplyDisposable.'
}
if ($selectedModes.Count -eq 0) {
    $PlanOnly = $true
}

$activateScript = Join-Path $RepoRoot 'scripts\activate_jcfb_v4_runtime.ps1'
$disposableScript = Join-Path $RepoRoot 'scripts\v4_disposable_runtime.ps1'
$readinessGateModule = Join-Path $RepoRoot 'scripts\v4_prebatch04_readiness_gate.psm1'
if (-not (Test-Path -LiteralPath $activateScript -PathType Leaf)) {
    throw 'The project runtime activation script is missing.'
}
if (-not (Test-Path -LiteralPath $readinessGateModule -PathType Leaf)) {
    throw 'The disposable runtime readiness gate module is missing.'
}

Import-Module -Name $readinessGateModule -Force

# Dot-source the activation script so every directory used by this wrapper and
# its child Python process remains under the project .runtime directory. Apply
# additionally imports and validates the ignored disposable env file without
# echoing any of its values.
if ($ApplyDisposable) {
    . $activateScript -RepoRoot $RepoRoot -LoadRuntimeEnvironment
} else {
    . $activateScript -RepoRoot $RepoRoot
}

$python = Join-Path $env:JCFB_V4_PYTHON_VENV 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The project-scoped F-drive Python virtual environment is missing; create .runtime\python-venv before running this wrapper.'
}
$python = (Resolve-Path -LiteralPath $python).Path

function Invoke-HarnessJson {
    param([string[]]$Arguments)
    $output = & $python -m tools.migration_harness @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw ("The migration harness returned exit code {0}." -f $exitCode)
    }
    try {
        return (($output -join [Environment]::NewLine) | ConvertFrom-Json)
    }
    catch {
        throw 'The migration harness returned an unreadable JSON report.'
    }
}

Push-Location -LiteralPath $RepoRoot
try {
    $hashReport = Invoke-HarnessJson @('--repo-root', '.', 'canonical-hash')
    if ($hashReport.status -ne 'PASS' -or $hashReport.matched_count -ne 9 -or $hashReport.pending_count -ne 0) {
        throw 'Canonical candidate hash verification did not pass; apply is blocked.'
    }

    $mode = if ($ApplyDisposable) { 'APPLY' } elseif ($DryRun) { 'DRY_RUN' } else { 'PLAN_ONLY' }
    if ($ApplyDisposable) {
        if (-not (Test-Path -LiteralPath $disposableScript -PathType Leaf)) {
            throw 'The disposable runtime readiness script is missing.'
        }

        $powerShellCommand = Get-Command powershell.exe -ErrorAction SilentlyContinue
        if ($null -eq $powerShellCommand) {
            $powerShellCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
        }
        if ($null -eq $powerShellCommand) {
            throw 'A PowerShell executable is unavailable for the disposable readiness helper.'
        }

        # Run the helper out of process so its explicit exit status cannot be
        # confused with a previous native command in this wrapper scope.
        $readinessOutput = @(
            & $powerShellCommand.Source -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $disposableScript -Action readiness -RepoRoot $RepoRoot 2>&1
        )
        $readinessExitCode = $LASTEXITCODE
        foreach ($readinessLine in $readinessOutput) {
            Write-Output ([string]$readinessLine)
        }

        $readinessGate = Test-DisposableReadinessOutput -OutputLines $readinessOutput -ExitCode $readinessExitCode
        if (-not $readinessGate.Passed) {
            throw ("The disposable PostgreSQL readiness gate did not pass: {0}" -f $readinessGate.Reason)
        }
    }

    $databaseName = if ($ApplyDisposable) { $env:JCFB_V4_RUNTIME_DB_NAME } else { 'jcfb_v4_runtime' }
    $report = Invoke-HarnessJson @(
        '--repo-root', '.',
        'runtime-validate',
        '--mode', $mode,
        '--database-name', $databaseName,
        '--write-report'
    )
    Write-Output ("PRE_BATCH_04_RUNTIME_MODE={0}" -f $mode)
    Write-Output ("PRE_BATCH_04_RUNTIME_STATUS={0}" -f $report.status)
    Write-Output ("PRE_BATCH_04_HASHES={0}/{1}" -f $report.hash_verification.matched_count, $report.hash_verification.candidate_count)
    Write-Output ("PRE_BATCH_04_SMOKE_EXECUTABLE_HANDLERS={0}/20" -f $report.runtime_case_wiring.smoke_executable_handler_count)
    Write-Output ("PRE_BATCH_04_ENFORCEMENT_EXECUTABLE_HANDLERS={0}/15" -f $report.runtime_case_wiring.enforcement_executable_handler_count)
    Write-Output ("PRE_BATCH_04_SMOKE_PASSED={0}/20" -f $report.runtime_validation.passed_smoke)
    Write-Output ("PRE_BATCH_04_ENFORCEMENT_PASSED={0}/15" -f $report.runtime_validation.passed_enforcement)
    Write-Output ("PRE_BATCH_04_STAGING_READINESS={0}" -f $report.staging_readiness.status)
    Write-Output ("PRE_BATCH_04_RUN_ID={0}" -f $report.run_id)
    Write-Output ("PRE_BATCH_04_STARTED_AT={0}" -f $report.started_at)
    Write-Output ("PRE_BATCH_04_FINISHED_AT={0}" -f $report.finished_at)
    Write-Output ("PRE_BATCH_04_GIT_HEAD={0}" -f $report.git_head)
    Write-Output ("PRE_BATCH_04_REPORT_JSON={0}" -f $report.report_paths.json)
    Write-Output ("PRE_BATCH_04_REPORT_MARKDOWN={0}" -f $report.report_paths.markdown)
    Write-Output ("PRE_BATCH_04_REPORT_LATEST={0}" -f $report.report_paths.latest)
    Write-Output 'PRE_BATCH_04_REPORT_SCOPE=.runtime/reports/prebatch04'
    if ($mode -eq 'APPLY' -and ($report.status -ne 'RUNTIME_VALIDATION_PASS' -or $report.staging_readiness.status -ne 'READY_FOR_PRODUCTION_REVIEW')) {
        exit 1
    }
}
finally {
    Pop-Location
}
