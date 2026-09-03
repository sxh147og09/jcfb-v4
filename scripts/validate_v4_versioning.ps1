[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository root does not exist: $RepoRoot"
}

$failures = [System.Collections.Generic.List[string]]::new()
$passes = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$Message) {
    [void]$script:failures.Add($Message)
}

function Add-Pass([string]$Message) {
    [void]$script:passes.Add($Message)
}

function Get-RepoPath([string]$RelativePath) {
    return Join-Path -Path $RepoRoot -ChildPath $RelativePath
}

function Read-RepoText([string]$RelativePath) {
    $path = Get-RepoPath $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Failure "Missing file: $RelativePath"
        return $null
    }
    return Get-Content -LiteralPath $path -Raw -Encoding utf8
}

function Require-Text([string]$RelativePath, [string]$Text) {
    $content = Read-RepoText $RelativePath
    if ($null -ne $content -and $content.Contains($Text)) {
        Add-Pass "$RelativePath contains '$Text'"
    } elseif ($null -ne $content) {
        Add-Failure "$RelativePath is missing required text: $Text"
    }
}

$requiredFiles = @(
    'docs/V4_VERSIONING_STANDARD.md',
    'docs/V4_VERSION_IDENTITY_CONTRACT.md',
    'docs/V4_COMPATIBILITY_POLICY.md',
    'docs/V4_RELEASE_NAMING.md',
    'scripts/validate_v4_versioning.ps1'
)

foreach ($relativePath in $requiredFiles) {
    if (Test-Path -LiteralPath (Get-RepoPath $relativePath) -PathType Leaf) {
        Add-Pass "Present: $relativePath"
    } else {
        Add-Failure "Missing required artifact: $relativePath"
    }
}

$requiredText = @{
    'docs/V4_VERSIONING_STANDARD.md' = @(
        'jcfb_version', 'engine_version', 'selector_version', 'config_version',
        'schema_version', 'migration_version', 'dataset_version', 'frozen_revision',
        'shadow_revision', 'experiment_revision', 'implementation_hash',
        'config_hash', 'input_hash', 'output_hash', 'Promotion', 'Retirement',
        'latest model', 'current version', 'Breaking Change'
    )
    'docs/V4_VERSION_IDENTITY_CONTRACT.md' = @(
        'model_name', 'model_version', 'major', 'minor', 'patch', 'revision',
        'engine_version', 'selector_version', 'config_version', 'schema_version',
        'migration_version', 'dataset_version', 'frozen_revision', 'shadow_revision',
        'experiment_revision', 'implementation_hash', 'config_hash', 'input_hash',
        'output_hash', 'role', 'status', 'NOT_APPLICABLE'
    )
    'docs/V4_COMPATIBILITY_POLICY.md' = @(
        'PATCH_COMPATIBLE', 'MINOR_COMPATIBLE', 'MAJOR_BREAKING',
        'schema_version', 'migration_version', 'ADAPTER_REQUIRED', 'BLOCKED'
    )
    'docs/V4_RELEASE_NAMING.md' = @(
        'jcfb-v4.0.0', 'score-engine-v4.0.0', 'fi-YYYYMMDD-NNNNNN',
        'sh-YYYYMMDD-NNNNNN', 'ex-YYYYMMDD-NNNNNN', 'latest', 'current',
        'Promotion', 'RETIRED'
    )
}

foreach ($relativePath in $requiredText.Keys) {
    foreach ($text in $requiredText[$relativePath]) {
        Require-Text $relativePath $text
    }
}

$crossFileRequirements = @{
    'README.md' = @('V4_VERSIONING_STANDARD.md', 'V4_VERSION_IDENTITY_CONTRACT.md', 'V4_COMPATIBILITY_POLICY.md', 'V4_RELEASE_NAMING.md', 'V4-006 COMPLETE')
    'AGENTS.md' = @('V4_VERSIONING_STANDARD.md', 'V4_VERSION_IDENTITY_CONTRACT.md', 'V4_COMPATIBILITY_POLICY.md')
    'CHANGELOG.md' = @('V4-006', 'V4_VERSIONING_STANDARD.md', 'validate_v4_versioning.ps1')
    'docs/V4_CONSTITUTION.md' = @('V4_VERSIONING_STANDARD.md', 'V4_VERSION_IDENTITY_CONTRACT.md')
    'docs/V4_MODEL_GOVERNANCE.md' = @('V4_VERSION_IDENTITY_CONTRACT.md', 'V4_COMPATIBILITY_POLICY.md')
    'docs/V4_INTEGRITY_RULES.md' = @('VERSION_IDENTITY_COMPLETE', 'COMPATIBILITY_DECLARED')
    'docs/V4_ARCHITECTURE_BLUEPRINT.md' = @('V4_VERSIONING_STANDARD.md')
    'docs/V4_MASTER_BUILD_CHECKLIST.md' = @('V4-006 Versioning Standard', 'validate_v4_versioning.ps1')
}

foreach ($relativePath in $crossFileRequirements.Keys) {
    foreach ($text in $crossFileRequirements[$relativePath]) {
        Require-Text $relativePath $text
    }
}

$textExtensions = @('.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.ps1', '.py', '.js', '.ts', '.sql', '.env', '.example')
$scanFiles = Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Force |
    Where-Object {
        $_.FullName -notmatch '\\.git\\' -and
        $_.FullName -notmatch '\\.runtime\\' -and
        ($textExtensions -contains $_.Extension.ToLowerInvariant() -or $_.Name -eq '.env.example' -or $_.Name -eq '.gitignore')
    }

$secretPatterns = @(
    '(?i)\bsk-[A-Za-z0-9]{20,}\b',
    '(?i)\bgh[pousr]_[A-Za-z0-9]{20,}\b',
    '(?i)\bglpat-[A-Za-z0-9_-]{20,}\b',
    '(?i)\bxox[baprs]-[A-Za-z0-9-]{20,}\b',
    '(?i)\bAIza[0-9A-Za-z_-]{20,}\b',
    '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    '(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b',
    '(?i)(?:api[_-]?key|secret|token|password|service[_-]?role[_-]?key)[ \t]*[:=][ \t]*["'']?[A-Za-z0-9./+=_-]{20,}'
)

$secretHits = 0
foreach ($file in $scanFiles) {
    try {
        $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8
    } catch {
        Add-Failure "Could not read text file for Secret Scan: $($file.FullName)"
        continue
    }
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            $secretHits++
            Add-Failure "Secret Scan match in $($file.FullName)"
            break
        }
    }
}
if ($secretHits -eq 0) {
    Add-Pass 'Secret Scan: no high-signal credential pattern found'
}

$operationalFiles = $scanFiles | Where-Object {
    $_.FullName -notmatch '\\docs\\' -and
    $_.Name -ne 'validate_v4_versioning.ps1'
}
$forbiddenOperationalPatterns = @(
    '(?i)\blatest[- ]model\b',
    '(?i)\blatest[- ]version\b',
    '(?i)\bcurrent[- ]model\b',
    '(?i)\bcurrent[- ]version\b',
    '(?i)\bthe[- ]current[- ]one\b',
    '(?i)\bthe[- ]model[- ]just[- ]changed\b'
)
$aliasHits = 0
foreach ($file in $operationalFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding utf8
    foreach ($pattern in $forbiddenOperationalPatterns) {
        if ($content -match $pattern) {
            $aliasHits++
            Add-Failure "Unqualified version alias in operational file: $($file.FullName)"
            break
        }
    }
}
if ($aliasHits -eq 0) {
    Add-Pass 'Operational alias audit: no unqualified model/version identity found'
}

$v333Files = @(git -C $RepoRoot diff --name-only -- 'docs/V333*' 'V333*')
if ($LASTEXITCODE -eq 0 -and $v333Files.Count -eq 0) {
    Add-Pass 'V3.3.3 protection audit: no V333 path changed in the working diff'
} else {
    Add-Failure 'V3.3.3 protection audit detected a changed V333 path'
}

Write-Output '=== JCFB V4 Versioning Validation ==='
foreach ($pass in $passes) {
    Write-Output "PASS: $pass"
}
foreach ($failure in $failures) {
    Write-Output "FAIL: $failure"
}

Write-Output "PASS_COUNT=$($passes.Count)"
Write-Output "FAIL_COUNT=$($failures.Count)"

if ($failures.Count -gt 0) {
    Write-Output 'V4_VERSIONING_VALIDATION=FAIL'
    exit 1
}

Write-Output 'V4_VERSIONING_VALIDATION=PASS'
