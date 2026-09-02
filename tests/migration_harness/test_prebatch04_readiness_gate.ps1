$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$modulePath = Join-Path $repoRoot 'scripts\v4_prebatch04_readiness_gate.psm1'
$wrapperPath = Join-Path $repoRoot 'scripts\v4_run_prebatch04_runtime_validation.ps1'
$helperPath = Join-Path $repoRoot 'scripts\v4_disposable_runtime.ps1'

Import-Module -Name $modulePath -Force

$testCases = @(
    [pscustomobject]@{
        Name = 'PASS + DISPOSABLE_LOCAL + MIGRATIONS_APPLIED=NO allows continuation'
        ExitCode = 0
        Expected = $true
        OutputLines = @(
            'NAME                 IMAGE',
            'DISPOSABLE_RUNTIME_READINESS=PASS',
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'PASS + wrong target blocks'
        ExitCode = 0
        Expected = $false
        OutputLines = @(
            'DISPOSABLE_RUNTIME_READINESS=PASS',
            'TARGET_IDENTITY=PRODUCTION',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'FAIL readiness blocks'
        ExitCode = 0
        Expected = $false
        OutputLines = @(
            'DISPOSABLE_RUNTIME_READINESS=FAIL',
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'Missing readiness key blocks'
        ExitCode = 0
        Expected = $false
        OutputLines = @(
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'Nonzero helper exit blocks even with PASS keys'
        ExitCode = 2
        Expected = $false
        OutputLines = @(
            'DISPOSABLE_RUNTIME_READINESS=PASS',
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'Multiline output parses as structured fields'
        ExitCode = 0
        Expected = $true
        OutputLines = @(
            "docker compose ps`r`nDISPOSABLE_RUNTIME_READINESS=PASS`r`nTARGET_IDENTITY=DISPOSABLE_LOCAL`r`nMIGRATIONS_APPLIED=NO"
        )
    },
    [pscustomobject]@{
        Name = 'Duplicate readiness key is ambiguous and blocks'
        ExitCode = 0
        Expected = $false
        OutputLines = @(
            'DISPOSABLE_RUNTIME_READINESS=PASS',
            'DISPOSABLE_RUNTIME_READINESS=FAIL',
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=NO'
        )
    },
    [pscustomobject]@{
        Name = 'MIGRATIONS_APPLIED=YES blocks pre-apply gate'
        ExitCode = 0
        Expected = $false
        OutputLines = @(
            'DISPOSABLE_RUNTIME_READINESS=PASS',
            'TARGET_IDENTITY=DISPOSABLE_LOCAL',
            'MIGRATIONS_APPLIED=YES'
        )
    }
)

$passed = 0
foreach ($testCase in $testCases) {
    $result = Test-DisposableReadinessOutput -OutputLines $testCase.OutputLines -ExitCode $testCase.ExitCode
    if ([bool]$result.Passed -ne [bool]$testCase.Expected) {
        throw ("{0}: expected Passed={1}, got Passed={2}; reason={3}" -f $testCase.Name, $testCase.Expected, $result.Passed, $result.Reason)
    }
    if (-not $result.Passed -and [string]::IsNullOrWhiteSpace($result.Reason)) {
        throw ("{0}: blocked result did not include a reason." -f $testCase.Name)
    }
    $passed++
}

$wrapperText = Get-Content -LiteralPath $wrapperPath -Raw -Encoding UTF8
$helperText = Get-Content -LiteralPath $helperPath -Raw -Encoding UTF8
$syntaxPaths = @($modulePath, $wrapperPath, $helperPath)
foreach ($syntaxPath in $syntaxPaths) {
    $tokens = $null
    $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($syntaxPath, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count -ne 0) {
        throw ("PowerShell syntax parsing failed for {0}." -f $syntaxPath)
    }
}
$staticChecks = @(
    $wrapperText.Contains('$readinessOutput = @('),
    $wrapperText.Contains('Test-DisposableReadinessOutput'),
    $wrapperText.Contains('-ExitCode $readinessExitCode'),
    $wrapperText.Contains('if (-not $readinessGate.Passed)'),
    $helperText.Contains('DISPOSABLE_RUNTIME_READINESS=PASS'),
    $helperText.Contains('exit 0'),
    $helperText.Contains('exit 2')
)
if (@($staticChecks | Where-Object { -not $_ }).Count -ne 0) {
    throw 'Readiness wrapper/helper static contract checks failed.'
}

Write-Output ("PRE_BATCH_04_READINESS_GATE_TESTS={0}/{0}" -f $passed)
Write-Output 'PRE_BATCH_04_READINESS_GATE_STATIC=PASS'
exit 0
