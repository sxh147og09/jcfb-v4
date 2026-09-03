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

function Test-JcfbV4GitCandidate {
    param(
        [AllowEmptyString()]
        [string]$Candidate
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $false
    }
    try {
        return [bool](Test-Path -LiteralPath $Candidate -PathType Leaf)
    }
    catch {
        return $false
    }
}

function New-JcfbV4GitResolution {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$Source
    )

    if (-not (Test-JcfbV4GitCandidate -Candidate $Candidate)) {
        return $null
    }
    try {
        $resolvedPath = (Resolve-Path -LiteralPath $Candidate -ErrorAction Stop).Path
    }
    catch {
        $resolvedPath = $Candidate
    }
    return [pscustomobject]@{
        Path   = $resolvedPath
        Source = $Source
    }
}

function Get-JcfbV4GitResolution {
    # An explicit process override remains the highest-priority source.  It is
    # intentionally never written to User or Machine environment scopes.
    $explicit = [Environment]::GetEnvironmentVariable('JCFB_V4_GIT_EXE', 'Process')
    if (-not [string]::IsNullOrWhiteSpace($explicit)) {
        $explicit = $explicit.Trim()
        if (($explicit.StartsWith('"') -and $explicit.EndsWith('"')) -or ($explicit.StartsWith("'") -and $explicit.EndsWith("'"))) {
            $explicit = $explicit.Substring(1, $explicit.Length - 2).Trim()
        }
        $resolved = New-JcfbV4GitResolution -Candidate $explicit -Source 'ENV_OVERRIDE'
        if ($null -ne $resolved) {
            return $resolved
        }
    }

    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if ($null -ne $gitCommand -and $gitCommand.CommandType -eq 'Application') {
        $resolved = New-JcfbV4GitResolution -Candidate ([string]$gitCommand.Source) -Source 'PATH'
        if ($null -ne $resolved) {
            return $resolved
        }
    }

    $commonCandidates = @()
    foreach ($rootName in @('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)')) {
        $root = [Environment]::GetEnvironmentVariable($rootName, 'Process')
        if ([string]::IsNullOrWhiteSpace($root)) {
            continue
        }
        $commonCandidates += Join-Path $root 'Git\cmd\git.exe'
        $commonCandidates += Join-Path $root 'Git\bin\git.exe'
    }
    $localAppData = [Environment]::GetEnvironmentVariable('LocalAppData', 'Process')
    if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
        $commonCandidates += Join-Path $localAppData 'Programs\Git\cmd\git.exe'
        $commonCandidates += Join-Path $localAppData 'Programs\Git\bin\git.exe'
    }
    foreach ($candidate in @($commonCandidates | Select-Object -Unique)) {
        $resolved = New-JcfbV4GitResolution -Candidate $candidate -Source 'WINDOWS_COMMON_PATH'
        if ($null -ne $resolved) {
            return $resolved
        }
    }

    # Codex bundled runtimes are discovered from the current user's/runtime
    # environment only.  No username or concrete cache path is embedded here.
    $codexRoots = @()
    foreach ($rootName in @('CODEX_RUNTIME_ROOT', 'CODEX_RUNTIME_DIR', 'CODEX_HOME')) {
        $root = [Environment]::GetEnvironmentVariable($rootName, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($root)) {
            $codexRoots += $root
        }
    }
    $userProfile = [Environment]::GetEnvironmentVariable('USERPROFILE', 'Process')
    if (-not [string]::IsNullOrWhiteSpace($userProfile)) {
        $codexRoots += Join-Path $userProfile '.cache\codex-runtimes'
    }
    if (-not [string]::IsNullOrWhiteSpace($localAppData)) {
        $codexRoots += Join-Path $localAppData 'codex-runtimes'
    }

    foreach ($root in @($codexRoots | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        try {
            $gitFiles = @(
                Get-ChildItem -LiteralPath $root -Filter 'git.exe' -File -Recurse -Depth 8 -ErrorAction SilentlyContinue |
                    Where-Object { $_.FullName -match '(?i)\\git\\(?:cmd|bin|mingw64\\bin)\\git\.exe$' } |
                    Sort-Object -Property FullName
            )
        }
        catch {
            $gitFiles = @()
        }
        foreach ($gitFile in $gitFiles) {
            $resolved = New-JcfbV4GitResolution -Candidate ([string]$gitFile.FullName) -Source 'CODEX_RUNTIME'
            if ($null -ne $resolved) {
                return $resolved
            }
        }
    }

    return $null
}

$gitResolution = Get-JcfbV4GitResolution
if (-not $PrintOnly) {
    if ($null -ne $gitResolution) {
        Set-Item -Path 'Env:JCFB_V4_GIT_EXE' -Value ([string]$gitResolution.Path)
        Set-Item -Path 'Env:JCFB_V4_GIT_SOURCE' -Value ([string]$gitResolution.Source)
    }
    else {
        Remove-Item -Path 'Env:JCFB_V4_GIT_EXE' -ErrorAction SilentlyContinue
        Set-Item -Path 'Env:JCFB_V4_GIT_SOURCE' -Value 'BLOCKED'
    }
}

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
if ($null -eq $gitResolution) {
    Write-Output 'JCFB_V4_GIT_RESOLUTION=BLOCKED'
    Write-Output 'JCFB_V4_GIT_SOURCE=NONE'
}
else {
    Write-Output 'JCFB_V4_GIT_RESOLUTION=PASS'
    Write-Output ("JCFB_V4_GIT_SOURCE={0}" -f $gitResolution.Source)
    Write-Output 'JCFB_V4_GIT_PATH=REDACTED'
}
if ($PrintOnly) {
    Write-Output 'JCFB_V4_RUNTIME_ACTIVATION=PRINT_ONLY'
} else {
    Write-Output 'JCFB_V4_RUNTIME_ACTIVATION=PASS'
    Write-Output 'JCFB_V4_SCOPE=Current PowerShell process and child processes only'
    if (-not $LoadRuntimeEnvironment) {
        Write-Output 'JCFB_V4_RUNTIME_ENV_LOADING=NOT_REQUESTED'
    }
}
