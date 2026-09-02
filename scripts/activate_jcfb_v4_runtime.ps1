[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$PrintOnly
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..'
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$runtimeRoot = Join-Path $RepoRoot '.runtime'

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

if (-not $PrintOnly) {
    foreach ($directory in $runtimeDirectories) {
        $null = New-Item -ItemType Directory -Force -Path $directory
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
}
