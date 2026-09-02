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
$localEnvFile = Join-Path $RepoRoot '.env.runtime-validation.local'
if (-not (Test-Path -LiteralPath $activateScript -PathType Leaf)) {
    throw 'The project runtime activation script is missing.'
}
if (-not (Test-Path -LiteralPath $readinessGateModule -PathType Leaf)) {
    throw 'The disposable runtime readiness gate module is missing.'
}

Import-Module -Name $readinessGateModule -Force

# Dot-source the activation script so every directory used by this wrapper and
# its child Python process remains under the project .runtime directory.
. $activateScript -RepoRoot $RepoRoot

$python = Join-Path $env:JCFB_V4_PYTHON_VENV 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw 'Python is unavailable. Install Python or create the project-scoped F-drive virtual environment.'
    }
    $python = $pythonCommand.Source
}

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

function Import-DisposableEnvironment {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw 'Copy .env.runtime-validation.example to .env.runtime-validation.local and set a fresh disposable password.'
    }
    $allowed = @(
        'JCFB_V4_RUNTIME_DB',
        'JCFB_V4_RUNTIME_OWNER',
        'JCFB_V4_RUNTIME_PASSWORD',
        'JCFB_V4_RUNTIME_DB_NAME',
        'JCFB_V4_RUNTIME_DB_USER',
        'JCFB_V4_RUNTIME_DB_PASSWORD',
        'JCFB_V4_RUNTIME_DB_SSLMODE'
    )
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            if ($allowed -notcontains $name) {
                continue
            }
            $value = $Matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            Set-Item -Path ("Env:{0}" -f $name) -Value $value
        }
    }
    if ([string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_NAME)) {
        $env:JCFB_V4_RUNTIME_DB_NAME = $env:JCFB_V4_RUNTIME_DB
    }
    if ([string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_USER)) {
        $env:JCFB_V4_RUNTIME_DB_USER = $env:JCFB_V4_RUNTIME_OWNER
    }
    if ([string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_PASSWORD)) {
        $env:JCFB_V4_RUNTIME_DB_PASSWORD = $env:JCFB_V4_RUNTIME_PASSWORD
    }
    $env:JCFB_V4_RUNTIME_DB_HOST = '127.0.0.1'
    $env:JCFB_V4_RUNTIME_DB_PORT = '5433'
    $env:JCFB_V4_RUNTIME_DB_SSLMODE = if ($env:JCFB_V4_RUNTIME_DB_SSLMODE) { $env:JCFB_V4_RUNTIME_DB_SSLMODE } else { 'disable' }
    if ([string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_NAME) -or
        [string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_USER) -or
        [string]::IsNullOrWhiteSpace($env:JCFB_V4_RUNTIME_DB_PASSWORD)) {
        throw 'The disposable database name, owner, and password must be non-empty; the password value is never printed.'
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
        Import-DisposableEnvironment -Path $localEnvFile
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
    Write-Output ("PRE_BATCH_04_SMOKE_BINDINGS={0}/20" -f $report.runtime_case_wiring.smoke_count)
    Write-Output ("PRE_BATCH_04_ENFORCEMENT_BINDINGS={0}/15" -f $report.runtime_case_wiring.enforcement_count)
    Write-Output 'PRE_BATCH_04_REPORT_SCOPE=.runtime/reports/prebatch04'
    if ($mode -eq 'APPLY' -and $report.status -notin @('APPLIED', 'RUNTIME_VALIDATION_PENDING', 'RUNTIME_VALIDATION_PASS')) {
        exit 1
    }
}
finally {
    Pop-Location
}
