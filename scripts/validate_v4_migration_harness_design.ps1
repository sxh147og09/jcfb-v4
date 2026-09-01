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

function Add-Pass([string]$Message) { [void]$script:passes.Add($Message) }
function Add-Failure([string]$Message) { [void]$script:failures.Add($Message) }
function Repo-Path([string]$RelativePath) { Join-Path -Path $RepoRoot -ChildPath $RelativePath }

function Read-RepoText([string]$RelativePath) {
    $path = Repo-Path $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Failure "Missing file: $RelativePath"
        return $null
    }
    return Get-Content -LiteralPath $path -Raw -Encoding utf8
}

function Read-RepoJson([string]$RelativePath) {
    $text = Read-RepoText $RelativePath
    if ($null -eq $text) { return $null }
    try {
        return $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Add-Failure "Invalid JSON: $RelativePath -> $($_.Exception.Message)"
        return $null
    }
}

function Require-Text([string]$Label, [string]$Text, [string]$Needle) {
    if ($null -ne $Text -and $Text.IndexOf($Needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        Add-Pass "$Label contains '$Needle'"
    }
    else {
        Add-Failure "$Label is missing '$Needle'"
    }
}

function Compare-StringSet([string]$Label, [object[]]$Expected, [object[]]$Actual) {
    $expectedValues = @($Expected | ForEach-Object { [string]$_ } | Sort-Object)
    $actualValues = @($Actual | ForEach-Object { [string]$_ } | Sort-Object)
    $difference = @(Compare-Object -ReferenceObject $expectedValues -DifferenceObject $actualValues)
    if ($difference.Count -eq 0) {
        Add-Pass "$Label matches expected source"
    }
    else {
        $diffText = @($difference | ForEach-Object { $_.InputObject + ':' + $_.SideIndicator }) -join ', '
        Add-Failure "$Label mismatch: $diffText"
    }
}

function Get-UniqueMatches([string]$Text, [string]$Pattern, [int]$FirstGroup = 1, [int]$SecondGroup = 0) {
    $values = [System.Collections.Generic.List[string]]::new()
    foreach ($match in [regex]::Matches($Text, $Pattern)) {
        $value = $match.Groups[$FirstGroup].Value
        if ($SecondGroup -gt 0) {
            $value = $value + '.' + $match.Groups[$SecondGroup].Value
        }
        if (-not $values.Contains($value)) { [void]$values.Add($value) }
    }
    return @($values)
}

$requiredFiles = @(
    'AGENTS.md',
    'docs/V4_TASK_REGISTRY_001_100.md',
    'docs/V4_TASK_DEPENDENCY_REGISTER.md',
    'docs/V4_DEPENDENCY_GRAPH_012_100.md',
    'docs/V4_TASK_RECOVERY_AUDIT.md',
    'docs/V4_BATCH_EXECUTION_PLAN.md',
    'docs/V4_MASTER_BUILD_CHECKLIST.md',
    'docs/V4_BATCH_ACCEPTANCE_RULES.md',
    'docs/V4_EXECUTION_CLASSIFICATION.md',
    'docs/V4_DATABASE_MIGRATION_DESIGN.md',
    'docs/V4_MIGRATION_PREFLIGHT.md',
    'docs/V4_MIGRATION_SMOKE_TESTS.md',
    'docs/V4_MIGRATION_ACCEPTANCE_GATE.md',
    'docs/V4_SCHEMA_VERSION_REGISTRY.md',
    'docs/V4_DATABASE_SCHEMA_BLUEPRINT.md',
    'docs/V4_CONSTITUTION.md',
    'docs/V4_VERSIONING_STANDARD.md',
    'database/schema/v4_schema_blueprint.sql',
    'database/migrations/v4/0000_manifest.md',
    'docs/V4_MIGRATION_DRY_RUN_HARNESS.md',
    'config/migration_harness/v4_harness_policy.json',
    'config/migration_harness/v4_target_descriptor.schema.json',
    'config/migration_harness/v4_manifest_contract.schema.json',
    'config/migration_harness/v4_manifest_loader_fixture.json',
    'config/migration_harness/v4_smoke_test_catalog.json',
    'config/migration_harness/v4_schema_snapshot_contract.json',
    'config/migration_harness/v4_acceptance_report.schema.json',
    'docs/V4_BATCH_01_ACCEPTANCE_REPORT.json',
    'docs/V4_BATCH_01_ACCEPTANCE_REPORT.md'
)
foreach ($relativePath in $requiredFiles) {
    if (Test-Path -LiteralPath (Repo-Path $relativePath) -PathType Leaf) { Add-Pass "Present: $relativePath" }
    else { Add-Failure "Missing required artifact: $relativePath" }
}

$registry = Read-RepoText 'docs/V4_TASK_REGISTRY_001_100.md'
$dependencyRegister = Read-RepoText 'docs/V4_TASK_DEPENDENCY_REGISTER.md'
$dependencyGraph = Read-RepoText 'docs/V4_DEPENDENCY_GRAPH_012_100.md'
$recoveryAudit = Read-RepoText 'docs/V4_TASK_RECOVERY_AUDIT.md'
$plan = Read-RepoText 'docs/V4_BATCH_EXECUTION_PLAN.md'
$checklist = Read-RepoText 'docs/V4_MASTER_BUILD_CHECKLIST.md'
$classification = Read-RepoText 'docs/V4_EXECUTION_CLASSIFICATION.md'
$design = Read-RepoText 'docs/V4_MIGRATION_DRY_RUN_HARNESS.md'
$manifestText = Read-RepoText 'database/migrations/v4/0000_manifest.md'
$blueprintText = Read-RepoText 'database/schema/v4_schema_blueprint.sql'

Require-Text 'Registry' $registry '| V4-012 | Migration Dry-Run & Validation Harness Design 1.0 |'
Require-Text 'Registry' $registry 'BATCH-01 | NO | NO | NO | COMPLETE'
Require-Text 'Task dependency register' $dependencyRegister 'V4-012 | Migration Dry-Run & Validation Harness Design 1.0 | BATCH-01 | V4-011 | V4-013 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE'
Require-Text 'Dependency graph' $dependencyGraph 'V4-012 Dry-Run Design COMPLETE'
Require-Text 'Dependency graph' $dependencyGraph 'next execution batch is BATCH-02'
Require-Text 'Recovery audit' $recoveryAudit 'NO V4-012+ TASK EXECUTED DURING THIS RECOVERY AUDIT'
Require-Text 'Recovery audit' $recoveryAudit 'V4-012 is accepted as design-only'
Require-Text 'Batch plan' $plan '| BATCH-01 | V4-012 |'
Require-Text 'Batch plan' $plan '| BATCH-02 | V4-013'
Require-Text 'Batch plan' $plan 'Next execution batch: **BATCH-02'
Require-Text 'Classification' $classification '| V4-012 | Migration Dry-Run & Validation Harness Design 1.0 | BATCHABLE + SERIAL | BATCH-01 | V4-011 | NO | NO | NO | COMPLETE |'
Require-Text 'Master Checklist' $checklist '- [x] V4-012 Migration Dry-Run & Validation Harness Design 1.0'
Require-Text 'Master Checklist mapping' $checklist '| [x] | V4-012 | Migration Dry-Run & Validation Harness Design 1.0 | BATCH-01 | BATCHABLE + SERIAL | RECOVERED_FROM_REPO_HISTORY |'
Require-Text 'Master Checklist' $checklist 'Next execution batch: **BATCH-02'
Require-Text 'Acceptance rules' (Read-RepoText 'docs/V4_BATCH_ACCEPTANCE_RULES.md') 'Next execution batch: **BATCH-02'

$designTokens = @(
    'DISPOSABLE_LOCAL', 'STAGING', 'PRODUCTION', 'BLOCKED_UNTIL_EXPLICIT_REQUEST',
    'FAIL-CLOSED', 'PF-01', 'PF-18', 'security-invoker', 'SECURITY DEFINER',
    'canonical_latest_update_at', 'frozen_input_hash', 'MISSING', 'EXTRA',
    'TYPE_MISMATCH', 'CONSTRAINT_MISMATCH', 'SECURITY_MISMATCH', 'PRECHECK_FAIL',
    'APPLY_FAIL', 'PARTIAL_FAIL', 'VALIDATION_FAIL', 'ACCEPTED',
    'PENDING_CANONICAL_HASH', 'governance.schema_migrations', 'V3.3.3',
    'NOT_EXECUTED_REQUIRES_DISPOSABLE_DB', 'BATCH-02'
)
foreach ($token in $designTokens) { Require-Text 'V4-012 design' $design $token }

$policy = Read-RepoJson 'config/migration_harness/v4_harness_policy.json'
$manifestFixture = Read-RepoJson 'config/migration_harness/v4_manifest_loader_fixture.json'
$manifestSchema = Read-RepoJson 'config/migration_harness/v4_manifest_contract.schema.json'
$targetSchema = Read-RepoJson 'config/migration_harness/v4_target_descriptor.schema.json'
$smoke = Read-RepoJson 'config/migration_harness/v4_smoke_test_catalog.json'
$snapshot = Read-RepoJson 'config/migration_harness/v4_schema_snapshot_contract.json'
$reportSchema = Read-RepoJson 'config/migration_harness/v4_acceptance_report.schema.json'
$acceptanceReport = Read-RepoJson 'docs/V4_BATCH_01_ACCEPTANCE_REPORT.json'

if ($null -ne $policy) {
    if ($policy.status -eq 'DESIGN_ONLY') { Add-Pass 'Policy status is DESIGN_ONLY' } else { Add-Failure 'Policy is not DESIGN_ONLY' }
    if ($policy.database_access.default_state -eq 'BLOCKED_UNTIL_EXPLICIT_REQUEST') { Add-Pass 'Default database state is fail-closed' } else { Add-Failure 'Default database state is not fail-closed' }
    if (@($policy.database_access.allowed_environments) -join ',' -eq 'DISPOSABLE_LOCAL,STAGING') { Add-Pass 'Only disposable local and staging environments are allowed' } else { Add-Failure 'Unexpected allowed environment set' }
    if (@($policy.database_access.hard_block_environments) -contains 'PRODUCTION') { Add-Pass 'PRODUCTION is hard-blocked' } else { Add-Failure 'PRODUCTION is not hard-blocked' }
    if ($policy.database_access.require_explicit_target_for_database -and $policy.database_access.require_explicit_environment_for_database -and $policy.database_access.require_explicit_execution_mode) { Add-Pass 'Explicit target/environment/mode are required' } else { Add-Failure 'Explicit database request requirements are incomplete' }
    if (-not $policy.database_access.connect_without_target -and -not $policy.database_access.connect_without_environment -and -not $policy.database_access.automatic_installation -and -not $policy.database_access.automatic_start) { Add-Pass 'No implicit connection, installation, or start path' } else { Add-Failure 'Unsafe implicit database path is enabled' }
    if (-not $policy.runner_contract.sql_execution_in_v4_012 -and -not $policy.runner_contract.ddl_apply_in_v4_012 -and -not $policy.runner_contract.connector_invocations_in_v4_012) { Add-Pass 'V4-012 has no SQL, DDL, or connector execution' } else { Add-Failure 'V4-012 execution boundary is too broad' }
    if ($policy.runner_contract.stop_on_first_failure -and -not $policy.runner_contract.continue_after_failure) { Add-Pass 'Failure state machine stops on first failure' } else { Add-Failure 'Failure state machine may continue after failure' }
    if ($policy.migration_history.verification_mode -eq 'APPEND_ONLY' -and -not $policy.migration_history.applied_row_update -and -not $policy.migration_history.applied_row_delete -and $policy.migration_history.mismatch_action -eq 'BLOCK') { Add-Pass 'Migration history is append-only and mismatch-blocking' } else { Add-Failure 'Migration history policy is unsafe' }
    if (-not $policy.secrets.persist_values -and -not $policy.secrets.log_values -and -not $policy.secrets.report_values -and -not $policy.secrets.repository_values) { Add-Pass 'Secret values are excluded from all persisted evidence' } else { Add-Failure 'Secret persistence policy is unsafe' }
    if ($policy.v333_isolation.conflict_action -eq 'BLOCK' -and -not $policy.v333_isolation.automatic_repair -and -not $policy.v333_isolation.automatic_copy_or_rename) { Add-Pass 'V3.3.3 conflict action is block-only' } else { Add-Failure 'V3.3.3 isolation policy permits repair or copy' }
}

if ($null -ne $targetSchema) {
    if (@($targetSchema.required) -contains 'credential_env_name' -and @($targetSchema.required) -contains 'connect_permission') { Add-Pass 'Target descriptor requires env reference and explicit permission' } else { Add-Failure 'Target descriptor omits secret/permission boundary' }
    if (@($targetSchema.properties.environment.enum) -contains 'PRODUCTION' -and @($targetSchema.allOf).Count -ge 1) { Add-Pass 'Target descriptor models PRODUCTION as a conditional hard block' } else { Add-Failure 'Target descriptor lacks PRODUCTION guard' }
}

$manifestRows = @($manifestText -split "`r?`n" | Where-Object { $_ -match '^\|\s*000[1-9]\s*\|' })
if ($manifestRows.Count -eq 9) { Add-Pass 'Manifest has exactly nine migration rows' } else { Add-Failure "Manifest row count is $($manifestRows.Count), expected 9" }
$manifestRecords = [System.Collections.Generic.List[object]]::new()
foreach ($row in $manifestRows) {
    $cells = @($row.Trim() -split '\|')
    if ($cells.Count -lt 8) { Add-Failure "Malformed manifest row: $row"; continue }
    $depends = $cells[5].Trim()
    $rawDependsIds = if ($depends -eq 'none') { @() } else { @($depends.Trim('[',']').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
    $dependsIds = @($rawDependsIds | ForEach-Object {
        if ($_ -match '^000[1-9]$') { 'migration@20260901.' + $_.Substring(1) } else { $_ }
    })
    $record = [pscustomobject]@{
        sequence = $cells[1].Trim()
        file = 'database/migrations/v4/' + $cells[2].Trim().Trim([char]96)
        migration_id = $cells[3].Trim().Trim([char]96).Split('/')[0]
        migration_version = $cells[3].Trim().Trim([char]96).Split('/')[0]
        name = $cells[4].Trim().Trim([char]96)
        depends_on = @($dependsIds)
        status = $cells[7].Trim()
    }
    [void]$manifestRecords.Add($record)
}

if ($null -ne $manifestFixture) {
    if (@($manifestFixture.entries).Count -eq 9) { Add-Pass 'Manifest loader fixture has nine entries' } else { Add-Failure 'Manifest loader fixture does not have nine entries' }
    Compare-StringSet 'Manifest fixture sequences' @($manifestFixture.entries.sequence) @($manifestRecords.sequence)
    Compare-StringSet 'Manifest fixture files' @($manifestFixture.entries.file) @($manifestRecords.file)
    Compare-StringSet 'Manifest fixture migration IDs' @($manifestFixture.entries.migration_id) @($manifestRecords.migration_id)
    Compare-StringSet 'Manifest fixture names' @($manifestFixture.entries.name) @($manifestRecords.name)
    $manifestDependencyKeys = @($manifestRecords | Sort-Object sequence | ForEach-Object { $_.sequence + ':' + (@($_.depends_on) -join ',') })
    $fixtureDependencyKeys = @($manifestFixture.entries | Sort-Object sequence | ForEach-Object { $_.sequence + ':' + (@($_.depends_on) -join ',') })
    Compare-StringSet 'Manifest fixture dependencies' $fixtureDependencyKeys $manifestDependencyKeys
}

$migrationFiles = @($manifestFixture.entries | Sort-Object sequence)
$expectedSequence = @('0001','0002','0003','0004','0005','0006','0007','0008','0009')
Compare-StringSet 'Manifest sequence order' $expectedSequence @($manifestRecords.sequence)
for ($i = 0; $i -lt $migrationFiles.Count; $i++) {
    $entry = $migrationFiles[$i]
    $sqlPath = Repo-Path ($entry.file -replace '/', '\')
    if (-not (Test-Path -LiteralPath $sqlPath -PathType Leaf)) { Add-Failure "Missing SQL source: $($entry.file)"; continue }
    $sql = Get-Content -LiteralPath $sqlPath -Raw -Encoding utf8
    if ($sql.StartsWith('-- DESIGN ONLY - DO NOT APPLY')) { Add-Pass "Safety marker: $($entry.file)" } else { Add-Failure "Missing safety marker: $($entry.file)" }
    foreach ($key in @('migration_id','sequence','name','migration_version','depends_on','schema_contract_version','authored_at','migration_hash','status')) {
        $metadataMatch = [regex]::Match($sql, ('(?m)^-- {0}: (.+)$' -f [regex]::Escape($key)))
        if (-not $metadataMatch.Success) { Add-Failure "Missing metadata $key in $($entry.file)"; continue }
        $actual = $metadataMatch.Groups[1].Value.Trim()
        $expected = [string]$entry.$key
        if ($key -eq 'depends_on') { $expected = if (@($entry.depends_on).Count -eq 0) { '[]' } else { '[' + (@($entry.depends_on) -join ',') + ']' } }
        if ($actual -eq $expected) { Add-Pass "$($entry.file) metadata $key matches" } else { Add-Failure "$($entry.file) metadata $key mismatch: $actual != $expected" }
    }
    foreach ($pattern in @('(?im)^\s*\\connect\b','(?im)^\s*\\(?:i|ir|include|copy|gexec)\b','(?im)^\s*supabase\s+(?:db\s+)?(?:push|query|reset)\b','(?im)\bapply_migration\b','(?is)\bDROP\s+.*?\bCASCADE\b')) {
        if ($sql -match $pattern) { Add-Failure "Forbidden SQL execution/destructive syntax in $($entry.file): $pattern" }
    }
}

$knownMigrationIds = @($migrationFiles | ForEach-Object { [string]$_.migration_id })
for ($i = 0; $i -lt $migrationFiles.Count; $i++) {
    $entry = $migrationFiles[$i]
    $actualParents = @()
    if ($null -ne $entry.depends_on) {
        $actualParents = @($entry.depends_on | ForEach-Object {
            if ($null -ne $_ -and [string]$_ -ne '') { [string]$_ }
        })
    }
    if ($i -eq 0) {
        if ($actualParents.Count -eq 0) { Add-Pass "Dependency parents for $($entry.sequence) are empty" }
        else { Add-Failure "Dependency parents for $($entry.sequence) are not empty: $($actualParents -join ',')" }
    }
    else {
        Compare-StringSet "Dependency parents for $($entry.sequence)" @([string]$migrationFiles[$i - 1].migration_id) $actualParents
    }
    foreach ($parent in $actualParents) {
        if ($knownMigrationIds -contains $parent) { Add-Pass "Dependency parent exists for $($entry.sequence): $parent" }
        else { Add-Failure "Dependency parent is missing for $($entry.sequence): $parent" }
    }
}

foreach ($sqlFile in @(Get-ChildItem -LiteralPath (Repo-Path 'database') -Recurse -File -Filter '*.sql')) {
    $sqlText = Get-Content -LiteralPath $sqlFile.FullName -Raw -Encoding utf8
    if (-not $sqlText.StartsWith('-- DESIGN ONLY - DO NOT APPLY')) { Add-Failure "SQL without design-only marker: $($sqlFile.FullName)" }
}

if ($null -ne $smoke) {
    $cases = @($smoke.cases)
    if ($cases.Count -eq 20) { Add-Pass 'Smoke catalog has exactly 20 cases' } else { Add-Failure "Smoke catalog has $($cases.Count) cases, expected 20" }
    $smokeIds = @($cases | Sort-Object source_case | ForEach-Object { $_.id })
    $expectedSmokeIds = 1..20 | ForEach-Object { 'SMOKE-{0:d2}' -f $_ }
    Compare-StringSet 'Smoke case IDs' $expectedSmokeIds $smokeIds
    $smokeDoc = Read-RepoText 'docs/V4_MIGRATION_SMOKE_TESTS.md'
    foreach ($case in $cases) { Require-Text "Smoke source case $($case.source_case)" $smokeDoc "| $($case.source_case) |" }
    if ($smoke.runtime_status -eq 'NOT_EXECUTED_REQUIRES_DISPOSABLE_DB' -and $smoke.execution_boundary.production_target -eq 'BLOCKED') { Add-Pass 'Smoke catalog preserves runtime-not-executed and production-blocked state' } else { Add-Failure 'Smoke catalog runtime boundary is unsafe' }
}

if ($null -ne $snapshot -and $null -ne $blueprintText) {
    $snapshotPatterns = [ordered]@{
        schemas = '(?im)^CREATE SCHEMA(?: IF NOT EXISTS)?\s+([a-z_][a-z0-9_]*)\s*;'
        tables = '(?im)^CREATE TABLE\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*\(';
        indexes = '(?im)^CREATE (?:UNIQUE )?INDEX\s+([a-z_][a-z0-9_]*)';
        functions = '(?im)^CREATE (?:OR REPLACE )?FUNCTION\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)';
        views = '(?im)^CREATE (?:OR REPLACE )?VIEW\s+([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)';
        triggers = '(?im)^CREATE (?:CONSTRAINT )?TRIGGER\s+([a-z_][a-z0-9_]*)';
        policies = '(?im)^CREATE POLICY\s+([a-z_][a-z0-9_]*)';
        rls_tables = '(?im)^ALTER TABLE\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s+(?:ENABLE|FORCE) ROW LEVEL SECURITY'
    }
    foreach ($kind in $snapshotPatterns.Keys) {
        $group2 = if ($kind -eq 'views') { 2 } else { 0 }
        $actualObjects = @(Get-UniqueMatches $blueprintText $snapshotPatterns[$kind] 1 $group2)
        $expectedObjects = @($snapshot.expected_catalog.$kind)
        Compare-StringSet "Schema snapshot $kind" $expectedObjects $actualObjects
        $expectedCount = [int]$snapshot.expected_counts.$kind
        if ($actualObjects.Count -eq $expectedCount) { Add-Pass "Schema snapshot count $kind = $expectedCount" } else { Add-Failure "Schema snapshot count $kind = $($actualObjects.Count), expected $expectedCount" }
    }
    if (@($snapshot.diff_contract.classifications) -join ',' -eq 'MISSING,EXTRA,TYPE_MISMATCH,CONSTRAINT_MISMATCH,SECURITY_MISMATCH') { Add-Pass 'Schema diff classifications are complete and ordered' } else { Add-Failure 'Schema diff classifications are incomplete or reordered' }
    if ($snapshot.diff_contract.non_empty_diff_status -eq 'BLOCKED' -and $snapshot.diff_contract.unknown_catalog_status -eq 'BLOCKED' -and $snapshot.diff_contract.never_auto_repair) { Add-Pass 'Schema diff is fail-closed and never auto-repairs' } else { Add-Failure 'Schema diff policy is unsafe' }
}

if ($null -ne $manifestSchema) {
    foreach ($required in @('contract_version','source_manifest','source_sql_directory','schema_contract_version','parse_mode','authoritative','entries','dependency_graph')) {
        if (@($manifestSchema.required) -contains $required) { Add-Pass "Manifest schema requires $required" } else { Add-Failure "Manifest schema omits $required" }
    }
}
if ($null -ne $reportSchema) {
    foreach ($required in @('report_contract_version','batch_id','task_ids','task_results','execution_boundary','manifest','target','preflight','migration_sequence','apply_status','validation','failures','blocking_reasons','secret_scan','self_audit','cross_doc_consistency','git_trace','requires_disposable_db_later')) {
        if (@($reportSchema.required) -contains $required) { Add-Pass "Acceptance report schema requires $required" } else { Add-Failure "Acceptance report schema omits $required" }
    }
    $statusValues = @($reportSchema.'$defs'.status.enum)
    if ($statusValues -contains 'NOT_EXECUTED_REQUIRES_DISPOSABLE_DB' -and $statusValues -contains 'BLOCKED') { Add-Pass 'Acceptance report schema has explicit blocked/not-executed states' } else { Add-Failure 'Acceptance report schema lacks blocked/not-executed states' }
}
if ($null -ne $acceptanceReport) {
    if ($acceptanceReport.batch_id -eq 'BATCH-01' -and @($acceptanceReport.task_ids) -join ',' -eq 'V4-012' -and $acceptanceReport.report_state -eq 'DESIGN_ACCEPTED') { Add-Pass 'Acceptance report binds BATCH-01, V4-012, and DESIGN_ACCEPTED' } else { Add-Failure 'Acceptance report has incorrect batch/task/state binding' }
    if ($acceptanceReport.execution_boundary.design_only -and -not $acceptanceReport.execution_boundary.sql_executed -and -not $acceptanceReport.execution_boundary.database_connected -and $acceptanceReport.execution_boundary.production_db_writes_performed -eq 'NO' -and $acceptanceReport.execution_boundary.supabase_writes_performed -eq 'NO' -and $acceptanceReport.execution_boundary.v333_mutated -eq 'NO') { Add-Pass 'Acceptance report records the no-write/no-connect boundary' } else { Add-Failure 'Acceptance report boundary is unsafe or incomplete' }
    if (@($acceptanceReport.preflight.checks).Count -eq 18 -and @($acceptanceReport.migration_sequence).Count -eq 9 -and $acceptanceReport.requires_disposable_db_later) { Add-Pass 'Acceptance report includes PF-01..PF-18, nine migration steps, and later DB requirement' } else { Add-Failure 'Acceptance report coverage is incomplete' }
}

$newArtifactPaths = @(
    'docs/V4_MIGRATION_DRY_RUN_HARNESS.md',
    'config/migration_harness/v4_harness_policy.json',
    'config/migration_harness/v4_target_descriptor.schema.json',
    'config/migration_harness/v4_manifest_contract.schema.json',
    'config/migration_harness/v4_manifest_loader_fixture.json',
    'config/migration_harness/v4_smoke_test_catalog.json',
    'config/migration_harness/v4_schema_snapshot_contract.json',
    'config/migration_harness/v4_acceptance_report.schema.json',
    'docs/V4_BATCH_01_ACCEPTANCE_REPORT.json',
    'docs/V4_BATCH_01_ACCEPTANCE_REPORT.md'
)
$secretPattern = '(?i)(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._-]{20,}|(?:api[_-]?key|secret|token|password|service[_-]?role[_-]?key)\s*[:=]\s*["''][A-Za-z0-9./+=_-]{20,}["''])'
$secretHits = 0
foreach ($relativePath in $newArtifactPaths) {
    $text = Read-RepoText $relativePath
    if ($null -ne $text -and $text -match $secretPattern) { Add-Failure "High-signal secret pattern in $relativePath"; $secretHits++ }
}
if ($secretHits -eq 0) { Add-Pass 'New V4-012 artifacts contain no high-signal secret pattern' }

$changedV333 = @(git -C $RepoRoot diff --name-only -- 'docs/V333*' 'V333*' | Where-Object { $_ })
if ($changedV333.Count -eq 0) { Add-Pass 'V3.3.3 diff path is unchanged' } else { Add-Failure 'V3.3.3 diff path changed' }

Write-Output '=== JCFB V4-012 Migration Harness Design Validation ==='
$passes | ForEach-Object { Write-Output "PASS: $_" }
$failures | ForEach-Object { Write-Output "FAIL: $_" }
Write-Output "PASS_COUNT=$($passes.Count)"
Write-Output "FAIL_COUNT=$($failures.Count)"
if ($failures.Count -gt 0) {
    Write-Output 'V4_MIGRATION_HARNESS_DESIGN_VALIDATION=FAIL'
    exit 1
}
Write-Output 'V4_MIGRATION_HARNESS_DESIGN_VALIDATION=PASS'
