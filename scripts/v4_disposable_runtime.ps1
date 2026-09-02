param(
    [ValidateSet('start', 'readiness', 'stop', 'destroy')]
    [string]$Action = 'readiness',
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$ConfirmDestroy
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path $RepoRoot).Path
$composeFile = Join-Path $RepoRoot 'docker-compose.runtime-validation.yml'
$localEnvFile = Join-Path $RepoRoot '.env.runtime-validation.local'
$containerName = 'jcfb-v4-disposable-pg'
$projectRuntimeRoot = Join-Path $RepoRoot '.runtime'
$postgresDataDir = Join-Path $projectRuntimeRoot 'postgres'

# The compose file uses a repository-relative bind mount. Create the host
# directory explicitly so the runtime cannot fall back to a Docker named
# volume whose storage location is controlled by Docker Desktop.
$null = New-Item -ItemType Directory -Force -Path $postgresDataDir

function Stop-WithStatus {
    param(
        [string]$Status,
        [string]$Message
    )
    Write-Output $Status
    Write-Output $Message
    exit 2
}

if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) {
    Stop-WithStatus 'BLOCKED_RUNTIME_COMPOSE_MISSING' 'The disposable runtime compose file is missing.'
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    Stop-WithStatus 'BLOCKED_DOCKER_NOT_INSTALLED' 'Install Docker Desktop manually, start it, then rerun this wrapper.'
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$null = & docker info 2>$null
$dockerInfoExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($dockerInfoExitCode -ne 0) {
    Stop-WithStatus 'BLOCKED_DOCKER_DAEMON_UNAVAILABLE' 'Docker is installed but its local daemon is not available. Start Docker Desktop and retry.'
}

if (-not (Test-Path -LiteralPath $localEnvFile -PathType Leaf)) {
    Stop-WithStatus 'BLOCKED_RUNTIME_ENV_FILE_MISSING' 'Copy .env.runtime-validation.example to .env.runtime-validation.local and set a local ephemeral password.'
}

$passwordLine = Get-Content -LiteralPath $localEnvFile -Encoding UTF8 |
    Where-Object { $_ -match '^\s*JCFB_V4_RUNTIME_PASSWORD\s*=' } |
    Select-Object -First 1
if ($null -eq $passwordLine -or $passwordLine -notmatch '^\s*JCFB_V4_RUNTIME_PASSWORD\s*=\s*[^#\s].*$') {
    Stop-WithStatus 'BLOCKED_RUNTIME_EPHEMERAL_PASSWORD_MISSING' 'Set a non-empty ephemeral local password in .env.runtime-validation.local; its value is never printed.'
}

$composeArgs = @(
    'compose',
    '--env-file', $localEnvFile,
    '-f', $composeFile,
    '--project-name', 'jcfb-v4-disposable-runtime'
)

switch ($Action) {
    'start' {
        & docker @composeArgs up -d
        if ($LASTEXITCODE -ne 0) {
            Stop-WithStatus 'BLOCKED_DISPOSABLE_RUNTIME_START' 'Docker Compose could not start the local disposable PostgreSQL container.'
        }
        Write-Output 'DISPOSABLE_RUNTIME_START=PASS'
        Write-Output 'TARGET_IDENTITY=DISPOSABLE_LOCAL'
        Write-Output 'CONTAINER=jcfb-v4-disposable-pg'
        Write-Output 'BOUND_ADDRESS=127.0.0.1:5433'
        Write-Output 'MIGRATIONS_APPLIED=NO'
    }
    'readiness' {
        & docker @composeArgs ps
        $health = (& docker inspect --format '{{.State.Health.Status}}' $containerName 2>$null | Select-Object -First 1)
        $health = if ($null -eq $health) { '' } else { $health.ToString().Trim() }
        if ($health -ne 'healthy') {
            Stop-WithStatus 'BLOCKED_DISPOSABLE_POSTGRES_NOT_READY' ("Container health is '{0}'. Run the start action and retry." -f $health)
        }
        Write-Output 'DISPOSABLE_RUNTIME_READINESS=PASS'
        Write-Output 'TARGET_IDENTITY=DISPOSABLE_LOCAL'
        Write-Output 'MIGRATIONS_APPLIED=NO'
    }
    'stop' {
        & docker @composeArgs stop
        if ($LASTEXITCODE -ne 0) {
            Stop-WithStatus 'BLOCKED_DISPOSABLE_RUNTIME_STOP' 'Docker Compose could not stop the local disposable PostgreSQL container.'
        }
        Write-Output 'DISPOSABLE_RUNTIME_STOP=PASS'
        Write-Output 'VOLUME_PRESERVED=YES'
    }
    'destroy' {
        if (-not $ConfirmDestroy) {
            Stop-WithStatus 'DESTROY_CONFIRMATION_REQUIRED' 'Repeat with -ConfirmDestroy to remove only the disposable container and F-drive runtime data directory.'
        }
        & docker @composeArgs down --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            Stop-WithStatus 'BLOCKED_DISPOSABLE_RUNTIME_DESTROY' 'Docker Compose could not remove the local disposable runtime.'
        }
        $resolvedPostgresDataDir = (Resolve-Path -LiteralPath $postgresDataDir).Path
        $resolvedRuntimeRoot = (Resolve-Path -LiteralPath $projectRuntimeRoot).Path
        if ($resolvedPostgresDataDir -eq $resolvedRuntimeRoot -or -not $resolvedPostgresDataDir.StartsWith($resolvedRuntimeRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            Stop-WithStatus 'BLOCKED_RUNTIME_DATA_SCOPE' 'The resolved disposable data path is outside the project runtime directory.'
        }
        Remove-Item -LiteralPath $resolvedPostgresDataDir -Recurse -Force
        Write-Output 'DISPOSABLE_RUNTIME_DESTROY=PASS'
        Write-Output 'REMOVED_SCOPE=jcfb-v4-disposable-runtime and F-drive .runtime/postgres data'
    }
}
