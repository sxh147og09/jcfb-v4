[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$failures = [System.Collections.Generic.List[string]]::new()
$passes = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$Message) { [void]$script:failures.Add($Message) }
function Add-Pass([string]$Message) { [void]$script:passes.Add($Message) }
function RepoPath([string]$RelativePath) { Join-Path $RepoRoot $RelativePath }

$migrationDir = RepoPath 'database/migrations/v4'
$requiredDocs = @(
    'docs/V4_DATABASE_MIGRATION_DESIGN.md',
    'docs/V4_MIGRATION_DEPENDENCY_GRAPH.md',
    'docs/V4_MIGRATION_PREFLIGHT.md',
    'docs/V4_MIGRATION_ROLLFORWARD_POLICY.md',
    'docs/V4_MIGRATION_SMOKE_TESTS.md',
    'docs/V4_SCHEMA_VERSION_REGISTRY.md',
    'docs/V4_MIGRATION_ACCEPTANCE_GATE.md',
    'database/migrations/README.md'
)
foreach ($relative in $requiredDocs) {
    if (Test-Path -LiteralPath (RepoPath $relative) -PathType Leaf) { Add-Pass "Present: $relative" }
    else { Add-Failure "Missing required V4-011 artifact: $relative" }
}

$requiredDocTokens = @(
    @{ Relative = 'docs/V4_DATABASE_MIGRATION_DESIGN.md'; Tokens = @('TODO_DECISION', 'PENDING_CANONICAL_HASH', 'disposable', 'pg_catalog', 'schema-only dump', 'Human Approver') },
    @{ Relative = 'docs/V4_MIGRATION_DEPENDENCY_GRAPH.md'; Tokens = @('0001-0009', 'Cycle check: **PASS**', 'No 0001-0009 migration is approved for parallel execution') },
    @{ Relative = 'docs/V4_MIGRATION_PREFLIGHT.md'; Tokens = @('PF-01', 'PF-18', 'target_project_identity', 'not a pass') },
    @{ Relative = 'docs/V4_MIGRATION_ROLLFORWARD_POLICY.md'; Tokens = @('FAILED', 'SUPERSEDED', 'new forward migration', 'DROP ... CASCADE') },
    @{ Relative = 'docs/V4_MIGRATION_SMOKE_TESTS.md'; Tokens = @('| 20 |', 'security', 'V3.3.3') },
    @{ Relative = 'docs/V4_SCHEMA_VERSION_REGISTRY.md'; Tokens = @('migration_id', 'prev_migration_hash', 'PENDING_CANONICAL_HASH', 'never edited') },
    @{ Relative = 'docs/V4_MIGRATION_ACCEPTANCE_GATE.md'; Tokens = @('PRECHECK_PASS', 'NO_FUTURE_LEAKAGE_GATE_PASS', 'MIGRATION_HISTORY_RECORDED', 'INTERNAL_NO_POLICY_PRIVATE=ACCEPTED') },
    @{ Relative = 'database/migrations/README.md'; Tokens = @('0001 -> 0009', 'service_role', 'forward migrations') }
)
foreach ($entry in $requiredDocTokens) {
    $path = RepoPath $entry.Relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    $content = Get-Content -LiteralPath $path -Raw -Encoding utf8
    foreach ($token in $entry.Tokens) {
        if ($content.IndexOf($token, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            Add-Failure "Missing documentation token '$token': $($entry.Relative)"
        }
    }
}
if ($failures.Count -eq 0) { Add-Pass 'Required architecture, dry-run, preflight, gate, and registry tokens present' }

$migrationFiles = @(
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

$expectedNames = @(
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

$requiredTokens = @(
    @('CREATE EXTENSION', 'CREATE SCHEMA IF NOT EXISTS core', 'governance.is_v4_hash', 'schema_migrations', 'v4_schema_registry'),
    @('governance.model_versions', 'governance.engine_versions', 'core.competitions', 'core.teams', 'core.team_aliases', 'core.matches'),
    @('official_odds_snapshots', 'external_market_snapshots', 'team_context_snapshots', 'evidence_items', 'evidence_bundles', 'evidence_bundle_items'),
    @('frozen_inputs', 'feature_bundles', 'engine_runs', 'predictions', 'frozen_predictions', 'future_information_leakage'),
    @('official_results', 'postmatch_reviews', 'tier_a_samples', 'promotion_reviews', 'calibration_records'),
    @('release_pointer_events', 'governance.incidents', 'governance.audit_logs', 'active_production'),
    @('ENABLE ROW LEVEL SECURITY', 'REVOKE ALL', 'reject_append_only_mutation', 'append_audit_event', 'validate_prediction_engine_membership', 'validate_frozen_prediction_lineage', 'validate_review_scope', 'validate_incident_scope', 'validate_production_release', 'validate_prematch_gate', 'validate_tier_a_pair'),
    @('public_read_projections', 'v_public_predictions', 'v_public_latest_odds', 'v_current_frozen_predictions', 'v_canonical_latest_update', 'v_tier_a_progress', 'v_model_registry_public', 'security_invoker', 'v4_public_projection_audit_event'),
    @('INSERT INTO governance.v4_schema_registry', 'deployment_acceptance_snapshots', 'PENDING_CANONICAL_HASH', 'v4_acceptance_snapshot_audit_event')
)

$expectedDependencies = @(
    '[]',
    '[migration@20260901.001]',
    '[migration@20260901.002]',
    '[migration@20260901.003]',
    '[migration@20260901.004]',
    '[migration@20260901.005]',
    '[migration@20260901.006]',
    '[migration@20260901.007]',
    '[migration@20260901.008]'
)

$ids = [System.Collections.Generic.List[string]]::new()
$sequences = [System.Collections.Generic.List[int]]::new()

for ($i = 0; $i -lt $migrationFiles.Count; $i++) {
    $relative = "database/migrations/v4/$($migrationFiles[$i])"
    $path = RepoPath $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Failure "Missing migration design: $relative"
        continue
    }

    $content = Get-Content -LiteralPath $path -Raw -Encoding utf8
    if (-not $content.StartsWith('-- DESIGN ONLY - DO NOT APPLY')) {
        Add-Failure "Missing top safety marker: $relative"
    }
    else { Add-Pass "Safety marker: $relative" }

    $metadata = @{}
    foreach ($key in @('migration_id', 'sequence', 'name', 'migration_version', 'depends_on', 'schema_contract_version', 'authored_at', 'migration_hash', 'status')) {
        $match = [regex]::Match($content, "(?m)^-- ${key}: (.+)$")
        if (-not $match.Success) {
            Add-Failure "Missing metadata '$key': $relative"
        }
        else { $metadata[$key] = $match.Groups[1].Value.Trim() }
    }

    if ($metadata.ContainsKey('migration_id')) { [void]$ids.Add($metadata['migration_id']) }
    if ($metadata.ContainsKey('sequence')) {
        $number = 0
        if ([int]::TryParse($metadata['sequence'], [ref]$number)) { [void]$sequences.Add($number) }
        else { Add-Failure "Non-numeric sequence: $relative" }
    }
    if ($metadata.ContainsKey('migration_id') -and $metadata['migration_id'] -ne "migration@20260901.00$($i + 1)") {
        Add-Failure "Unexpected migration_id: $relative"
    }
    if ($metadata.ContainsKey('sequence') -and $metadata['sequence'] -ne ('000{0}' -f ($i + 1))) {
        Add-Failure "Unexpected sequence: $relative"
    }
    if ($metadata.ContainsKey('name') -and $metadata['name'] -ne $expectedNames[$i]) {
        Add-Failure "Unexpected name: $relative"
    }
    if ($metadata.ContainsKey('migration_version') -and $metadata['migration_version'] -ne "migration@20260901.00$($i + 1)") {
        Add-Failure "Unexpected migration_version: $relative"
    }
    if ($metadata.ContainsKey('depends_on') -and $metadata['depends_on'] -ne $expectedDependencies[$i]) {
        Add-Failure "Unexpected dependency: $relative"
    }
    if ($metadata.ContainsKey('schema_contract_version') -and $metadata['schema_contract_version'] -ne 'v4-database-schema@1.0.0') {
        Add-Failure "Unexpected schema contract: $relative"
    }
    if ($metadata.ContainsKey('migration_hash') -and $metadata['migration_hash'] -ne 'PENDING_CANONICAL_HASH') {
        Add-Failure "Design file must not claim a fabricated hash: $relative"
    }
    if ($metadata.ContainsKey('status') -and $metadata['status'] -ne 'DRAFT') {
        Add-Failure "Unapproved migration status: $relative"
    }

    foreach ($token in $requiredTokens[$i]) {
        if ($content.IndexOf($token, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            Add-Failure "Missing '$token': $relative"
        }
    }

    $forbidden = @(
        '(?im)^\s*\\connect\b',
        '(?im)^\s*\\(?:i|ir|include|copy|gexec)\b',
        '(?im)^\s*supabase\s+(?:db\s+)?(?:push|query|reset)\b',
        '(?im)^\s*apply_migration\b',
        '(?is)\bDROP\s+.*?\bCASCADE\b'
    )
    foreach ($pattern in $forbidden) {
        if ($content -match $pattern) {
            Add-Failure "Forbidden execution/destructive syntax '$pattern': $relative"
        }
    }
}

if (($ids | Sort-Object -Unique).Count -ne $ids.Count) { Add-Failure 'Migration IDs are not unique' }
else { Add-Pass 'Migration IDs unique' }
if (($sequences | Sort-Object -Unique).Count -ne $sequences.Count) { Add-Failure 'Migration sequences are not unique' }
elseif (($sequences | Sort-Object) -join ',' -ne '1,2,3,4,5,6,7,8,9') { Add-Failure 'Migration sequences are not 1..9' }
else { Add-Pass 'Migration sequences unique and ordered' }

$allSql = @(
    (Get-ChildItem -LiteralPath (RepoPath 'database') -Recurse -File -Filter '*.sql' |
        Where-Object {
            $_.FullName -notlike (Join-Path $migrationDir.Replace('\migrations\v4', '\migrations\v4_runtime_candidate') '*') -and
            $_.FullName -notlike (Join-Path (RepoPath 'database/runtime') '*')
        })
)
foreach ($sql in $allSql) {
    $content = Get-Content -LiteralPath $sql.FullName -Raw -Encoding utf8
    if (-not $content.StartsWith('-- DESIGN ONLY - DO NOT APPLY')) {
        Add-Failure "SQL safety marker missing: $($sql.FullName)"
    }
}
if ($failures.Count -eq 0) { Add-Pass 'All design SQL files carry the design-only marker; runtime candidates are validated separately' }

$localRoleBootstrap = RepoPath 'database/runtime/0000_service_role.sql'
if (Test-Path -LiteralPath $localRoleBootstrap -PathType Leaf) {
    $bootstrapText = Get-Content -LiteralPath $localRoleBootstrap -Raw -Encoding utf8
    if ($bootstrapText.StartsWith('-- JCFB V4 DISPOSABLE LOCAL ROLE BOOTSTRAP')) {
        Add-Pass 'Disposable local role bootstrap is explicitly separated from V4-011 design SQL'
    }
    else {
        Add-Failure 'Disposable local role bootstrap is missing its explicit support-file marker'
    }
}

$manifest = RepoPath 'database/migrations/v4/0000_manifest.md'
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    $manifestText = Get-Content -LiteralPath $manifest -Raw -Encoding utf8
    foreach ($file in $migrationFiles) {
        if ($manifestText.IndexOf($file, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            Add-Failure "Manifest missing $file"
        }
    }
    if ($manifestText.Contains('PENDING_CANONICAL_HASH') -and $manifestText.Contains('0009_seed_and_smoke.sql')) {
        Add-Pass 'Manifest covers 0001-0009 and pending hash state'
    }
}
else { Add-Failure 'Missing migration manifest' }

$changedV333 = @(
    git -C $RepoRoot diff --name-only -- 'docs/V333*' 'V333*'
    git -C $RepoRoot status --short | Where-Object { $_ -match '(?i)(docs[\\/]V333|V333)' }
)
if ($changedV333.Count -eq 0) { Add-Pass 'V3.3.3 protection: no changed V333 path' }
else { Add-Failure 'V3.3.3 protection detected a changed V333 path' }

Write-Output '=== JCFB V4 Migration Design Validation ==='
$passes | ForEach-Object { Write-Output "PASS: $_" }
$failures | ForEach-Object { Write-Output "FAIL: $_" }
Write-Output "PASS_COUNT=$($passes.Count)"
Write-Output "FAIL_COUNT=$($failures.Count)"
if ($failures.Count -gt 0) {
    Write-Output 'V4_MIGRATION_DESIGN_VALIDATION=FAIL'
    exit 1
}
Write-Output 'V4_MIGRATION_DESIGN_VALIDATION=PASS'
