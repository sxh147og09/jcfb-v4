$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$modulePath = Join-Path $repoRoot 'scripts\v4_prebatch04_readiness_gate.psm1'
$wrapperPath = Join-Path $repoRoot 'scripts\v4_run_prebatch04_runtime_validation.ps1'
$helperPath = Join-Path $repoRoot 'scripts\v4_disposable_runtime.ps1'
$portContractPath = Join-Path $repoRoot 'scripts\v4_disposable_runtime_contract.psm1'

Import-Module -Name $modulePath -Force
Import-Module -Name $portContractPath -Force

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

$portEvidenceCases = @(
    [pscustomobject]@{
        Name = 'Actual NetworkSettings.Ports mapping passes with exact docker port output'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55432"}]}'
        DockerPortLines = @('127.0.0.1:55432')
        Expected = $true
        ExpectedStatus = 'PASS'
    },
    [pscustomobject]@{
        Name = 'Actual NetworkSettings.Ports missing mapping blocks'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[]}'
        DockerPortLines = @('127.0.0.1:55432')
        Expected = $false
        ExpectedStatus = 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING'
    },
    [pscustomobject]@{
        Name = '0.0.0.0 actual host address blocks'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[{"HostIp":"0.0.0.0","HostPort":"55432"}]}'
        DockerPortLines = @('0.0.0.0:55432')
        Expected = $false
        ExpectedStatus = 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST'
    },
    [pscustomobject]@{
        Name = 'Empty actual host address blocks'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[{"HostIp":"","HostPort":"55432"}]}'
        DockerPortLines = @(':55432')
        Expected = $false
        ExpectedStatus = 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST'
    },
    [pscustomobject]@{
        Name = 'Missing docker port output blocks even when inspect reports mapping'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55432"}]}'
        DockerPortLines = @()
        Expected = $false
        ExpectedStatus = 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING'
    },
    [pscustomobject]@{
        Name = 'Non-loopback docker port output blocks'
        NetworkSettingsPorts = ConvertFrom-Json '{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55432"}]}'
        DockerPortLines = @('0.0.0.0:55432')
        Expected = $false
        ExpectedStatus = 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST'
    }
)

$portEvidencePassed = 0
foreach ($testCase in $portEvidenceCases) {
    $result = Test-DisposableHostPortEvidence `
        -NetworkSettingsPorts $testCase.NetworkSettingsPorts `
        -DockerPortLines $testCase.DockerPortLines `
        -ExpectedHostAddress '127.0.0.1' `
        -ExpectedHostPort '55432' `
        -ExpectedContainerPort '5432'
    if ([bool]$result.Passed -ne [bool]$testCase.Expected) {
        throw ("{0}: expected Passed={1}, got Passed={2}; status={3}" -f $testCase.Name, $testCase.Expected, $result.Passed, $result.Status)
    }
    if ([string]$result.Status -ne [string]$testCase.ExpectedStatus) {
        throw ("{0}: expected Status={1}, got Status={2}" -f $testCase.Name, $testCase.ExpectedStatus, $result.Status)
    }
    $portEvidencePassed++
}

$wrapperText = Get-Content -LiteralPath $wrapperPath -Raw -Encoding UTF8
$helperText = Get-Content -LiteralPath $helperPath -Raw -Encoding UTF8
$contractText = Get-Content -LiteralPath $portContractPath -Raw -Encoding UTF8
$composeText = Get-Content -LiteralPath (Join-Path $repoRoot 'docker-compose.runtime-validation.yml') -Raw -Encoding UTF8
$syntaxPaths = @($modulePath, $wrapperPath, $helperPath, $portContractPath)
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
    $helperText.Contains('exit 2'),
    $helperText.Contains('.NetworkSettings.Ports'),
    $helperText.Contains('& docker port'),
    $helperText.Contains('Test-DisposableHostPortEvidence'),
    $contractText.Contains("ExpectedHostPort = '55432'"),
    $composeText.Contains('"127.0.0.1:55432:5432"'),
    $composeText.Contains('driver: bridge'),
    (-not $composeText.Contains('internal: true'))
)
if (@($staticChecks | Where-Object { -not $_ }).Count -ne 0) {
    throw 'Readiness wrapper/helper static contract checks failed.'
}

Write-Output ("PRE_BATCH_04_READINESS_GATE_TESTS={0}/{0}" -f $passed)
Write-Output ("PRE_BATCH_04_PORT_EVIDENCE_TESTS={0}/{0}" -f $portEvidencePassed)
Write-Output 'PRE_BATCH_04_READINESS_GATE_STATIC=PASS'
exit 0
