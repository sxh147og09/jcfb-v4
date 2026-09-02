[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$PrintOnly,
    [switch]$LoadRuntimeEnvironment
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..'
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$runtimeRoot = Join-Path $RepoRoot '.runtime'
$runtimeEnvFile = Join-Path $RepoRoot '.env.runtime-validation.local'

$paths = [ordered]@{
    JCFB_V4_REPO_ROOT            = $RepoRoot
    JCFB_V4_RUNTIME_ROOT         = $runtimeRoot
    JCFB_V4_CACHE_DIR            = (Join-Path $runtimeRoot 'cache')
    JCFB_V4_BUILD_DIR            = (Join-Path $runtimeRoot 'build')
    JCFB_V4_TEMP_DIR             = (Join-Path $runtimeRoot 'temp')
    JCFB_V4_LOG_DIR              = (Join-Path $runtimeRoot 'logs')
    JCFB_V4_DATA_DIR             = (Join-Path $runtimeRoot 'data')
    JCFB_V4_DEPENDENCIES_DIR     = (Join-Path $runtimeRoot 'deps')
    JCFB_V4_PYTHON_VENV          = (Join-Path $runtimeRoot 'python-venv')
    JCFB_V4_NPM_GLOBAL_DIR       = (Join-Path $runtimeRoot 'npm-global')
    JCFB_V4_PNPM_HOME            = (Join-Path $runtimeRoot 'pnpm-home')
    JCFB_V4_PNPM_STORE_DIR       = (Join-Path $runtimeRoot 'pnpm-store')
    JCFB_V4_YARN_CACHE_DIR       = (Join-Path $runtimeRoot 'yarn-cache')
    JCFB_V4_PLAYWRIGHT_DIR       = (Join-Path $runtimeRoot 'playwright')
    JCFB_V4_POSTGRES_DATA_DIR    = (Join-Path $runtimeRoot 'postgres')
    JCFB_V4_PYTHON_CACHE_DIR     = (Join-Path $runtimeRoot 'pycache')
    JCFB_V4_COREPACK_HOME        = (Join-Path $runtimeRoot 'corepack')
    TEMP                         = (Join-Path $runtimeRoot 'temp')
    TMP                          = (Join-Path $runtimeRoot 'temp')
    TMPDIR                       = (Join-Path $runtimeRoot 'temp')
    PIP_CACHE_DIR                = (Join-Path $runtimeRoot 'pip-cache')
    NPM_CONFIG_CACHE             = (Join-Path $runtimeRoot 'npm-cache')
    NPM_CONFIG_PREFIX            = (Join-Path $runtimeRoot 'npm-global')
    PNPM_HOME                    = (Join-Path $runtimeRoot 'pnpm-home')
    PNPM_STORE_DIR               = (Join-Path $runtimeRoot 'pnpm-store')
    npm_config_store_dir         = (Join-Path $runtimeRoot 'pnpm-store')
    YARN_CACHE_FOLDER            = (Join-Path $runtimeRoot 'yarn-cache')
    PLAYWRIGHT_BROWSERS_PATH     = (Join-Path $runtimeRoot 'playwright')
    PYTHONPYCACHEPREFIX          = (Join-Path $runtimeRoot 'pycache')
    COREPACK_HOME                = (Join-Path $runtimeRoot 'corepack')
}

$runtimeDirectories = @(
    $runtimeRoot,
    $paths['JCFB_V4_CACHE_DIR'],
    $paths['JCFB_V4_BUILD_DIR'],
    $paths['JCFB_V4_TEMP_DIR'],
    $paths['JCFB_V4_LOG_DIR'],
    $paths['JCFB_V4_DATA_DIR'],
    $paths['JCFB_V4_DEPENDENCIES_DIR'],
    $paths['JCFB_V4_PYTHON_VENV'],
    $paths['JCFB_V4_NPM_GLOBAL_DIR'],
    $paths['JCFB_V4_PNPM_HOME'],
    $paths['JCFB_V4_PNPM_STORE_DIR'],
    $paths['JCFB_V4_YARN_CACHE_DIR'],
    $paths['JCFB_V4_PLAYWRIGHT_DIR'],
    $paths['JCFB_V4_POSTGRES_DATA_DIR'],
    $paths['JCFB_V4_PYTHON_CACHE_DIR'],
    $paths['JCFB_V4_COREPACK_HOME'],
    $paths['PIP_CACHE_DIR'],
    $paths['NPM_CONFIG_CACHE']
) | Select-Object -Unique

$runtimeEnvironmentNames = @(
    'JCFB_V4_RUNTIME_DB_HOST',
    'JCFB_V4_RUNTIME_DB_PORT',
    'JCFB_V4_RUNTIME_DB_SSLMODE',
    'JCFB_V4_RUNTIME_DB_NAME',
    'JCFB_V4_RUNTIME_DB_USER',
    'JCFB_V4_RUNTIME_DB_PASSWORD',
    'JCFB_V4_RUNTIME_DB',
    'JCFB_V4_RUNTIME_OWNER',
    'JCFB_V4_RUNTIME_PASSWORD'
)

function Import-JcfbV4RuntimeEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw 'The local disposable runtime environment file is missing.'
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            if ($runtimeEnvironmentNames -notcontains $name) {
                continue
            }
            $value = $Matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$name] = $value
        }
    }

    if ([string]::IsNullOrWhiteSpace([string]$values['JCFB_V4_RUNTIME_DB_NAME']) -and $values.ContainsKey('JCFB_V4_RUNTIME_DB')) {
        $values['JCFB_V4_RUNTIME_DB_NAME'] = $values['JCFB_V4_RUNTIME_DB']
    }
    if ([string]::IsNullOrWhiteSpace([string]$values['JCFB_V4_RUNTIME_DB_USER']) -and $values.ContainsKey('JCFB_V4_RUNTIME_OWNER')) {
        $values['JCFB_V4_RUNTIME_DB_USER'] = $values['JCFB_V4_RUNTIME_OWNER']
    }
    if ([string]::IsNullOrWhiteSpace([string]$values['JCFB_V4_RUNTIME_DB_PASSWORD']) -and $values.ContainsKey('JCFB_V4_RUNTIME_PASSWORD')) {
        $values['JCFB_V4_RUNTIME_DB_PASSWORD'] = $values['JCFB_V4_RUNTIME_PASSWORD']
    }

    $required = @(
        'JCFB_V4_RUNTIME_DB_HOST',
        'JCFB_V4_RUNTIME_DB_PORT',
        'JCFB_V4_RUNTIME_DB_SSLMODE',
        'JCFB_V4_RUNTIME_DB_NAME',
        'JCFB_V4_RUNTIME_DB_USER',
        'JCFB_V4_RUNTIME_DB_PASSWORD'
    )
    $missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([string]$values[$_]) })
    if ($missing.Count -gt 0) {
        throw ('Required disposable runtime environment variables are missing: {0}' -f ($missing -join ', '))
    }
    if ([string]$values['JCFB_V4_RUNTIME_DB_HOST'] -ne '127.0.0.1') {
        throw 'Disposable runtime database host must be 127.0.0.1.'
    }
    if ([string]$values['JCFB_V4_RUNTIME_DB_PORT'] -ne '55432') {
        throw 'Disposable runtime database host port must be 55432.'
    }
    if ([string]$values['JCFB_V4_RUNTIME_DB_SSLMODE'] -notin @('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full')) {
        throw 'Disposable runtime database sslmode is not supported.'
    }

    foreach ($name in $values.Keys) {
        Set-Item -Path ("Env:{0}" -f $name) -Value ([string]$values[$name])
    }
    Write-Output 'JCFB_V4_RUNTIME_ENV_LOADING=PASS'
    Write-Output 'JCFB_V4_RUNTIME_ENV_SCOPE=Current PowerShell process and child processes only'
}

if (-not $PrintOnly) {
    foreach ($directory in $runtimeDirectories) {
        $null = New-Item -ItemType Directory -Force -Path $directory
    }

    if ($LoadRuntimeEnvironment) {
        Import-JcfbV4RuntimeEnvironment -Path $runtimeEnvFile
    }

    foreach ($name in $paths.Keys) {
        Set-Item -Path ("Env:{0}" -f $name) -Value ([string]$paths[$name])
    }
}

Write-Output 'JCFB_V4_PROJECT_STORAGE=F_DRIVE'
Write-Output ("JCFB_V4_REPO_ROOT={0}" -f $RepoRoot)
Write-Output ("JCFB_V4_RUNTIME_ROOT={0}" -f $runtimeRoot)
if ($PrintOnly) {
    Write-Output 'JCFB_V4_RUNTIME_ACTIVATION=PRINT_ONLY'
} else {
    Write-Output 'JCFB_V4_RUNTIME_ACTIVATION=PASS'
    Write-Output 'JCFB_V4_SCOPE=Current PowerShell process and child processes only'
    if (-not $LoadRuntimeEnvironment) {
        Write-Output 'JCFB_V4_RUNTIME_ENV_LOADING=NOT_REQUESTED'
    }
}
