param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path $RepoRoot).Path
$candidateDir = Join-Path $RepoRoot 'database/migrations/v4_runtime_candidate'
$sourceDir = Join-Path $RepoRoot 'database/migrations/v4'
$jsonManifestPath = Join-Path $candidateDir '0000_runtime_candidate_manifest.json'
$markdownManifestPath = Join-Path $candidateDir '0000_runtime_candidate_manifest.md'
$failures = [System.Collections.Generic.List[string]]::new()

function Assert-Check {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        $failures.Add($Message)
    }
}

function Read-Utf8 {
    param([string]$Path)
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8
}

Assert-Check (Test-Path -LiteralPath $candidateDir -PathType Container) 'Candidate directory is missing'
Assert-Check (Test-Path -LiteralPath $jsonManifestPath -PathType Leaf) 'JSON candidate manifest is missing'
Assert-Check (Test-Path -LiteralPath $markdownManifestPath -PathType Leaf) 'Markdown candidate manifest is missing'

$expectedNames = @(
    '0001_prerequisites.sql',
    '0002_registries_core.sql',
    '0003_market_context.sql',
    '0004_frozen_runtime.sql',
    '0005_evaluation.sql',
    '0006_governance_audit.sql',
    '0007_security_rls.sql',
    '0008_views_projections.sql',
    '0009_seed_and_smoke.sql'
)
$expectedMigrationNames = @(
    'v4-prerequisites',
    'v4-registries-core',
    'v4-market-context',
    'v4-frozen-runtime',
    'v4-evaluation',
    'v4-governance-audit',
    'v4-security-rls',
    'v4-views-projections',
    'v4-seed-smoke'
)

$candidateFiles = @()
if (Test-Path -LiteralPath $candidateDir -PathType Container) {
    $candidateFiles = @(Get-ChildItem -LiteralPath $candidateDir -File -Filter '*.sql' | Sort-Object Name)
}
Assert-Check ($candidateFiles.Count -eq 9) ("Expected 9 candidate SQL files, found {0}" -f $candidateFiles.Count)
Assert-Check ((@($candidateFiles.Name) -join '|') -eq ($expectedNames -join '|')) 'Candidate SQL sequence or filenames are incomplete'

$allCandidateText = ''
for ($i = 0; $i -lt $expectedNames.Count; $i++) {
    $relative = 'database/migrations/v4_runtime_candidate/' + $expectedNames[$i]
    $path = Join-Path $RepoRoot $relative
    Assert-Check (Test-Path -LiteralPath $path -PathType Leaf) ("Missing candidate {0}" -f $relative)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        continue
    }

    $text = Read-Utf8 $path
    $allCandidateText += [Environment]::NewLine + $text
    $expectedSequence = '{0:D4}' -f ($i + 1)
    $expectedId = 'migration@20260901.{0:D3}' -f ($i + 1)

    foreach ($marker in @(
        'JCFB V4 RUNTIME VALIDATION CANDIDATE',
        'RUNTIME VALIDATION CANDIDATE',
        'DISPOSABLE/STAGING ONLY',
        'NOT APPROVED FOR PRODUCTION',
        'status: DRAFT',
        'production_status: PRODUCTION_REVIEW_REQUIRED'
    )) {
        Assert-Check ($text.Contains($marker)) ("{0} is missing marker: {1}" -f $relative, $marker)
    }

    Assert-Check ($text -match '(?m)^-- source_design_file: database/migrations/v4/000[1-9]_[a-z0-9_]+\.sql$') ("{0} has invalid source design provenance" -f $relative)
    Assert-Check ($text -match '(?m)^-- source_design_commit: [0-9a-f]{40}$') ("{0} has invalid source commit provenance" -f $relative)
    Assert-Check ($text -match ('(?m)^-- migration_id: ' + [regex]::Escape($expectedId) + '$')) ("{0} has incorrect migration id" -f $relative)
    Assert-Check ($text -match ('(?m)^-- sequence: ' + $expectedSequence + '$')) ("{0} has incorrect sequence" -f $relative)
    Assert-Check ($text -match ('(?m)^-- name: ' + [regex]::Escape($expectedMigrationNames[$i]) + '$')) ("{0} has incorrect migration name" -f $relative)
    Assert-Check ($text -match '(?m)^-- schema_contract_version: v4-database-schema@1\.0\.0$') ("{0} has incorrect schema contract version" -f $relative)
    Assert-Check ($text -match '(?m)^-- canonical_migration_hash: sha256:[0-9a-f]{64}$') ("{0} has no generated canonical_migration_hash" -f $relative)
    Assert-Check ($text -match '(?m)^-- migration_hash: sha256:[0-9a-f]{64}$') ("{0} has no generated migration_hash" -f $relative)
    Assert-Check (([regex]::Matches($text, '(?im)^\s*BEGIN;\s*$')).Count -eq 1) ("{0} must contain one top-level BEGIN" -f $relative)
    Assert-Check (([regex]::Matches($text, '(?im)^\s*COMMIT;\s*$')).Count -eq 1) ("{0} must contain one top-level COMMIT" -f $relative)
    Assert-Check (([regex]::Matches($text, '\$\$')).Count % 2 -eq 0) ("{0} has unbalanced dollar-quoted blocks" -f $relative)
}

$forbiddenCandidatePatterns = @(
    '(?i)\bTODO_DECISION\b',
    '(?i)\bPLACEHOLDER\b',
    '(?i)\bSTUB\b',
    '(?i)DESIGN ONLY',
    '(?i)DO NOT APPLY',
    '(?i)NOT AN EXECUTION',
    '(?i)\\connect\b',
    '(?i)\bCREATE\s+DATABASE\b',
    '(?i)\bALTER\s+SYSTEM\b',
    '(?i)\bCOPY\b[^\r\n;]*\bPROGRAM\b',
    '(?i)\bpostgres(?:ql)?://',
    '(?i)\bsupabase\b[^\r\n;]*\bapply\b'
)
foreach ($pattern in $forbiddenCandidatePatterns) {
    Assert-Check (-not ($allCandidateText -match $pattern)) ("Candidate SQL contains forbidden runtime marker or connection path: {0}" -f $pattern)
}

Assert-Check (-not ($allCandidateText -match '(?i)\b(?:ALTER|CREATE|SET)\s+ROLE\s+service_role\b')) 'Candidate SQL must not mutate the Supabase-reserved service_role'
$prerequisitePath = Join-Path $candidateDir '0001_prerequisites.sql'
if (Test-Path -LiteralPath $prerequisitePath -PathType Leaf) {
    $prerequisiteText = Read-Utf8 $prerequisitePath
    foreach ($requiredServiceRoleCheck in @(
        'pg_catalog\.pg_roles',
        'rolname\s*=\s*''service_role''',
        'rolbypassrls',
        'IF\s+NOT\s+FOUND',
        'V4_PREREQUISITE_SERVICE_ROLE_MISSING',
        'V4_PREREQUISITE_SERVICE_ROLE_BYPASSRLS_REQUIRED',
        'V4_PREREQUISITE_PUBLIC_ROLE_BYPASSRLS_FORBIDDEN',
        'anon',
        'authenticated'
    )) {
        Assert-Check ($prerequisiteText -match ('(?is)' + $requiredServiceRoleCheck)) ("0001 is missing service_role prerequisite check: {0}" -f $requiredServiceRoleCheck)
    }
}

Assert-Check ($allCandidateText -match '(?im)CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+pgcrypto') 'Candidate prerequisites do not install pgcrypto'
Assert-Check ($allCandidateText -match '(?im)SET\s+LOCAL\s+TIME\s+ZONE\s+''UTC''') 'Candidate SQL does not pin runtime timezone to UTC'
Assert-Check ($allCandidateText -match '(?im)CREATE\s+SCHEMA') 'Candidate SQL does not create V4 schemas'
Assert-Check ($allCandidateText -match '(?im)CREATE\s+(?:UNIQUE\s+)?INDEX') 'Candidate SQL does not create indexes'

$securityPath = Join-Path $candidateDir '0007_security_rls.sql'
if (Test-Path -LiteralPath $securityPath -PathType Leaf) {
    $securityText = Read-Utf8 $securityPath
    foreach ($requiredSecurityMarker in @(
        'CREATE OR REPLACE FUNCTION',
        'CREATE TRIGGER',
        'ENABLE ROW LEVEL SECURITY',
        'REVOKE ALL',
        'GRANT '
    )) {
        Assert-Check ($securityText.Contains($requiredSecurityMarker)) ("0007 is missing security marker: {0}" -f $requiredSecurityMarker)
    }
    foreach ($requiredFunction in @(
        'reject_append_only_mutation',
        'protect_frozen_input_mutation',
        'guard_registry_update',
        'validate_source_separation',
        'validate_market_payload',
        'validate_context_evidence_lineage',
        'validate_revision_chain',
        'validate_frozen_input_lineage',
        'validate_runtime_lineage',
        'validate_prediction_engine_membership',
        'validate_frozen_prediction_lineage',
        'validate_prematch_gate',
        'validate_tier_a_pair',
        'validate_production_release',
        'validate_review_scope',
        'validate_incident_scope',
        'validate_public_projection',
        'append_audit_event'
    )) {
        Assert-Check ($securityText -match ('(?im)CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?:[a-z0-9_]+\.)?' + [regex]::Escape($requiredFunction) + '\s*\(')) ("0007 is missing function implementation: {0}" -f $requiredFunction)
    }
}

if (Test-Path -LiteralPath $jsonManifestPath -PathType Leaf) {
    try {
        $manifest = (Read-Utf8 $jsonManifestPath | ConvertFrom-Json)
        Assert-Check ($manifest.'$id' -eq 'v4-runtime-candidate-manifest@1.0.0') 'Manifest identity is incorrect'
        Assert-Check ($manifest.task -eq 'PRE-BATCH-04 REMEDIATION') 'Manifest task is incorrect'
        Assert-Check ($manifest.candidate_directory -eq 'database/migrations/v4_runtime_candidate') 'Manifest candidate directory is incorrect'
        Assert-Check ($manifest.candidate_count -eq 9) 'Manifest candidate count is not 9'
        Assert-Check ($manifest.production_apply -eq 'HARD_BLOCK') 'Manifest production apply is not hard-blocked'
        Assert-Check ($manifest.canonical_hash_status -eq 'GENERATED_CANONICAL_HASHES') 'Manifest canonical hash status is not generated'
        Assert-Check ($manifest.canonicalization.version -eq 'v4-canonical-migration@1.0.0') 'Manifest canonicalization version is invalid'
        Assert-Check ($manifest.canonicalization.algorithm -eq 'SHA-256') 'Manifest canonicalization algorithm is invalid'
        Assert-Check (@($manifest.environment_allowlist) -contains 'DISPOSABLE_LOCAL') 'Manifest omits DISPOSABLE_LOCAL'
        Assert-Check (@($manifest.environment_allowlist) -contains 'STAGING') 'Manifest omits STAGING'

        $manifestCandidates = @($manifest.candidates)
        Assert-Check ($manifestCandidates.Count -eq 9) 'Manifest candidate list is not 9'
        for ($i = 0; $i -lt [Math]::Min($manifestCandidates.Count, 9); $i++) {
            $item = $manifestCandidates[$i]
            $expectedId = 'migration@20260901.{0:D3}' -f ($i + 1)
            $expectedDependency = if ($i -eq 0) { @() } else { @('migration@20260901.{0:D3}' -f $i) }
            Assert-Check ($item.sequence -eq ($i + 1)) ("Manifest sequence mismatch at index {0}" -f $i)
            Assert-Check ($item.migration_id -eq $expectedId) ("Manifest migration id mismatch at index {0}" -f $i)
            Assert-Check ($item.candidate_file -eq ('database/migrations/v4_runtime_candidate/' + $expectedNames[$i])) ("Manifest candidate path mismatch at index {0}" -f $i)
            Assert-Check ($item.status -eq 'RUNTIME_VALIDATION_CANDIDATE') ("Manifest candidate status mismatch at index {0}" -f $i)
            Assert-Check ($item.production_approval -eq 'NOT_APPROVED_FOR_PRODUCTION') ("Manifest production approval mismatch at index {0}" -f $i)
            Assert-Check ($item.canonical_migration_hash -match '^sha256:[0-9a-f]{64}$') ("Manifest canonical hash is not generated at index {0}" -f $i)
            Assert-Check ($item.migration_version -eq $item.migration_id) ("Manifest migration version is missing at index {0}" -f $i)
            Assert-Check ($item.schema_contract_version -eq 'v4-database-schema@1.0.0') ("Manifest schema contract is missing at index {0}" -f $i)
            Assert-Check ($item.authored_at -eq '2026-09-01T00:00:00+08:00') ("Manifest authored_at is missing at index {0}" -f $i)
        Assert-Check ($item.source_design_commit -match '^[0-9a-f]{40}$') ("Manifest source commit is invalid at index {0}" -f $i)
        Assert-Check (@($item.depends_on).Count -eq $expectedDependency.Count) ("Manifest dependency count mismatch at index {0}" -f $i)
        if ($expectedDependency.Count -eq 1) {
                Assert-Check (@($item.depends_on)[0] -eq @($expectedDependency)[0]) ("Manifest dependency mismatch at index {0}" -f $i)
            }
            $candidatePath = Join-Path $RepoRoot $item.candidate_file
            if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
                $actualHash = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
                Assert-Check ($actualHash -eq $item.content_sha256_noncanonical) ("Manifest byte hash mismatch at index {0}" -f $i)
            }
        }

        Assert-Check ($manifest.runtime_execution_policy.production_apply -eq 'FORBIDDEN') 'Manifest runtime policy does not forbid production apply'
        Assert-Check ($manifest.runtime_execution_policy.v333_mutation -eq 'FORBIDDEN') 'Manifest runtime policy does not forbid V3.3.3 mutation'
        Assert-Check ($manifest.runtime_execution_policy.business_seed_data -eq 'NONE') 'Manifest runtime policy permits business seed data'
    }
    catch {
        $failures.Add("Manifest JSON parse/validation error: $($_.Exception.Message)")
    }
}

Assert-Check ($allCandidateText -match '(?im)CREATE\s+POLICY') 'Candidate SQL does not create an RLS policy'

$viewsPath = Join-Path $candidateDir '0008_views_projections.sql'
if (Test-Path -LiteralPath $viewsPath -PathType Leaf) {
    $viewsText = Read-Utf8 $viewsPath
    $v4ViewNames = @(
        'public.v4_public_predictions',
        'public.v4_public_latest_odds',
        'public.v4_current_frozen_predictions',
        'public.v4_canonical_latest_update',
        'public.v4_tier_a_progress',
        'public.v4_model_registry_public'
    )
    foreach ($viewName in $v4ViewNames) {
        Assert-Check ($viewsText -match ('(?im)^\s*CREATE\s+VIEW\s+' + [regex]::Escape($viewName) + '\s*$')) ("0008 is missing approved V4 view: {0}" -f $viewName)
        Assert-Check ($viewsText -match ('(?is)CREATE\s+VIEW\s+' + [regex]::Escape($viewName) + '\s+WITH\s*\(\s*security_invoker\s*=\s*true\s*\)')) ("0008 V4 view is not security_invoker: {0}" -f $viewName)
        Assert-Check ($viewsText -match ('(?is)GRANT\s+SELECT\s+ON\s+[^;]*' + [regex]::Escape($viewName))) ("0008 is missing a grant contract for V4 view: {0}" -f $viewName)
    }
    Assert-Check (-not ($viewsText -match '(?im)^\s*DROP\s+VIEW\b')) '0008 must not drop a pre-existing public view'
    Assert-Check (-not ($viewsText -match '(?im)^\s*CREATE\s+OR\s+REPLACE\s+VIEW\b')) '0008 must not replace a pre-existing public view'
    foreach ($legacyView in @(
        'public.v_canonical_latest_update',
        'public.v_current_frozen_predictions',
        'public.v_public_latest_odds',
        'public.v_public_predictions',
        'public.v_tier_a_progress'
    )) {
        Assert-Check (-not ($viewsText -match ('(?im)^\s*CREATE\s+VIEW\s+' + [regex]::Escape($legacyView) + '\s*$'))) ("0008 collides with the V3.3.3 public view: {0}" -f $legacyView)
    }
}

if (Test-Path -LiteralPath $markdownManifestPath -PathType Leaf) {
    $markdownManifest = Read-Utf8 $markdownManifestPath
    foreach ($manifestMarker in @(
        'RUNTIME VALIDATION CANDIDATE',
        'DISPOSABLE/STAGING ONLY',
        'Production apply: HARD BLOCK',
        'Canonical migration hashes: GENERATED_CANONICAL_HASHES',
        'v4-canonical-migration@1.0.0',
        'The original database/migrations/v4/0001-0009 design files remain immutable design artifacts.'
    )) {
        Assert-Check ($markdownManifest.Contains($manifestMarker)) ("Markdown manifest is missing marker: {0}" -f $manifestMarker)
    }
}

foreach ($sourceName in $expectedNames) {
    $sourcePath = Join-Path $sourceDir $sourceName
    Assert-Check (Test-Path -LiteralPath $sourcePath -PathType Leaf) ("Original design file is missing: {0}" -f $sourceName)
    if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
        $sourceText = Read-Utf8 $sourcePath
        Assert-Check ($sourceText.Contains('DESIGN ONLY - DO NOT APPLY')) ("Original design marker missing: {0}" -f $sourceName)
    }
}

$designDiff = & git -C $RepoRoot diff --quiet -- database/migrations/v4
Assert-Check ($LASTEXITCODE -eq 0) 'Original database/migrations/v4 design files have unstaged changes'
$designCachedDiff = & git -C $RepoRoot diff --cached --quiet -- database/migrations/v4
Assert-Check ($LASTEXITCODE -eq 0) 'Original database/migrations/v4 design files have staged changes'

$v3Diff = @(
    (& git -C $RepoRoot diff --name-only)
    (& git -C $RepoRoot diff --cached --name-only)
) | Where-Object { $_ -match '(?i)(^|[\\/])v3(?:\.3\.3)?([\\/]|$)' }
Assert-Check ($v3Diff.Count -eq 0) 'V3.3.3 paths have changed'

$python = Get-Command python -ErrorAction SilentlyContinue
Assert-Check ($null -ne $python) 'Python is unavailable for the repository secret scan'
if ($null -ne $python) {
    $secretOutput = & python -c "import json; from pathlib import Path; from tools.migration_harness.security import secret_scan; print(json.dumps(secret_scan(Path(r'$RepoRoot'))))"
    try {
        $secretResult = ($secretOutput -join [Environment]::NewLine) | ConvertFrom-Json
        Assert-Check ($secretResult.status -eq 'PASS') 'Repository secret scan failed'
        Assert-Check ($secretResult.values_logged -eq $false) 'Secret scan reported values logged'
    }
    catch {
        $failures.Add("Secret scan output could not be parsed: $($_.Exception.Message)")
    }

    $hashOutput = & python -c "import json; from pathlib import Path; from tools.migration_harness.canonical_hash import verify_candidate_hashes; print(json.dumps(verify_candidate_hashes(Path(r'$RepoRoot'))))"
    try {
        $hashResult = ($hashOutput -join [Environment]::NewLine) | ConvertFrom-Json
        Assert-Check ($hashResult.status -eq 'PASS') 'Canonical candidate hash verifier failed'
        Assert-Check ($hashResult.matched_count -eq 9) 'Canonical candidate hash verifier did not match 9/9 candidates'
        Assert-Check ($hashResult.pending_count -eq 0) 'Canonical candidate hash verifier still reports pending hashes'
        Assert-Check ($hashResult.dependency_status -eq 'PASS') 'Canonical candidate dependency verification failed'
    }
    catch {
        $failures.Add("Canonical hash verifier output could not be parsed: $($_.Exception.Message)")
    }
}

if ($failures.Count -eq 0) {
    Write-Output 'V4_RUNTIME_CANDIDATE_VALIDATION=PASS'
    Write-Output 'CANDIDATE_COUNT=9'
    Write-Output 'DEPENDENCY_GRAPH=PASS'
    Write-Output 'SQL_STATIC_VALIDATION=PASS'
    Write-Output 'PRODUCTION_APPLY_HARD_BLOCK=PASS'
    Write-Output 'ORIGINAL_DESIGN_FILES_PRESERVED=PASS'
    Write-Output 'V3_3_3_ISOLATION=PASS'
    Write-Output 'SECRET_SCAN=PASS'
    exit 0
}

Write-Output 'V4_RUNTIME_CANDIDATE_VALIDATION=FAIL'
foreach ($failure in $failures) {
    Write-Output ("FAIL: " + $failure)
}
exit 1
