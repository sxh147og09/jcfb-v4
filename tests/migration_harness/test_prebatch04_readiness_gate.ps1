$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$modulePath = Join-Path $repoRoot 'scripts\v4_prebatch04_readiness_gate.psm1'
$wrapperPath = Join-Path $repoRoot 'scripts\v4_run_prebatch04_runtime_validation.ps1'
$helperPath = Join-Path $repoRoot 'scripts\v4_disposable_runtime.ps1'
$portContractPath = Join-Path $repoRoot 'scripts\v4_disposable_runtime_contract.psm1'
$activationPath = Join-Path $repoRoot 'scripts\activate_jcfb_v4_runtime.ps1'

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

$activationPassed = 0
$testRepoRoot = $repoRoot
$activationTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jcfb-v4-activation-" + [guid]::NewGuid().ToString('N'))
$fakeGitPath = Join-Path $activationTestRoot 'fake-git.exe'
$originalProcessGit = [Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'Process')
$originalProcessGitSource = [Environment]::GetEnvironmentVariable('JCFB_V4_GIT_SOURCE', 'Process')
$originalUserGit = [Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'User')
$originalMachineGit = [Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'Machine')
try {
    $null = New-Item -ItemType Directory -Force -Path $activationTestRoot
    $null = New-Item -ItemType File -Force -Path $fakeGitPath
    Set-Item -Path 'Env:JCFB_V4_GIT_EXE' -Value $fakeGitPath
    . $activationPath -RepoRoot $activationTestRoot | Out-Null
    if ([Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'Process') -ne (Resolve-Path -LiteralPath $fakeGitPath).Path) {
        throw 'Activation did not set the resolved Git path in the current process.'
    }
    if ([Environment]::GetEnvironmentVariable('JCFB_V4_GIT_SOURCE', 'Process') -ne 'ENV_OVERRIDE') {
        throw 'Activation did not record the explicit environment Git source.'
    }
    if ([Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'User') -ne $originalUserGit) {
        throw 'Activation changed the User Git environment scope.'
    }
    if ([Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'Machine') -ne $originalMachineGit) {
        throw 'Activation changed the Machine Git environment scope.'
    }
    $activationPassed++
}
finally {
    $repoRoot = $testRepoRoot
    if ($null -eq $originalProcessGit) {
        Remove-Item -Path 'Env:JCFB_V4_GIT_EXE' -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -Path 'Env:JCFB_V4_GIT_EXE' -Value $originalProcessGit
    }
    if ($null -eq $originalProcessGitSource) {
        Remove-Item -Path 'Env:JCFB_V4_GIT_SOURCE' -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -Path 'Env:JCFB_V4_GIT_SOURCE' -Value $originalProcessGitSource
    }
    Remove-Item -LiteralPath $activationTestRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$activationText = Get-Content -LiteralPath $activationPath -Raw -Encoding UTF8
$wrapperText = Get-Content -LiteralPath $wrapperPath -Raw -Encoding UTF8
$helperText = Get-Content -LiteralPath $helperPath -Raw -Encoding UTF8
$contractText = Get-Content -LiteralPath $portContractPath -Raw -Encoding UTF8
$composeText = Get-Content -LiteralPath (Join-Path $repoRoot 'docker-compose.runtime-validation.yml') -Raw -Encoding UTF8
$syntaxPaths = @($modulePath, $wrapperPath, $helperPath, $portContractPath, $activationPath)
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
    $wrapperText.Contains('RUNTIME_VALIDATION_PASS'),
    $wrapperText.Contains('READY_FOR_PRODUCTION_REVIEW'),
    $wrapperText.Contains('PRE_BATCH_04_SMOKE_EXECUTABLE_HANDLERS'),
    $wrapperText.Contains('PRE_BATCH_04_ENFORCEMENT_EXECUTABLE_HANDLERS'),
    $helperText.Contains('DISPOSABLE_RUNTIME_READINESS=PASS'),
    $helperText.Contains('exit 0'),
    $helperText.Contains('exit 2'),
    $helperText.Contains('.NetworkSettings.Ports'),
    $helperText.Contains('& docker port'),
    $helperText.Contains('Test-DisposableHostPortEvidence'),
    $contractText.Contains("ExpectedHostPort = '55432'"),
    $composeText.Contains('"127.0.0.1:55432:5432"'),
    $composeText.Contains('driver: bridge'),
    (-not $composeText.Contains('internal: true')),
    $activationText.Contains('Get-Command git'),
    $activationText.Contains('JCFB_V4_GIT_EXE'),
    $activationText.Contains('JCFB_V4_GIT_RESOLUTION=BLOCKED'),
    $activationText.Contains("Set-Item -Path 'Env:JCFB_V4_GIT_EXE'"),
    $activationText.Contains('Current PowerShell process and child processes only'),
    (-not ($activationText -match '(?i)(?:SetEnvironmentVariable|New-ItemProperty|Set-ItemProperty).*(?:User|Machine)'))
)
if (@($staticChecks | Where-Object { -not $_ }).Count -ne 0) {
    throw 'Readiness wrapper/helper static contract checks failed.'
}

Write-Output ("PRE_BATCH_04_READINESS_GATE_TESTS={0}/{0}" -f $passed)
Write-Output ("PRE_BATCH_04_PORT_EVIDENCE_TESTS={0}/{0}" -f $portEvidencePassed)
Write-Output ("PRE_BATCH_04_GIT_ACTIVATION_TESTS={0}/{0}" -f $activationPassed)
Write-Output 'PRE_BATCH_04_GIT_ACTIVATION_STATIC=PASS'
Write-Output 'PRE_BATCH_04_READINESS_GATE_STATIC=PASS'
exit 0
