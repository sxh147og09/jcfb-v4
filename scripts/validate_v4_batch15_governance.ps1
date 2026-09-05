[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$evidencePath = Join-Path $repoRoot 'docs/V4_BATCH_15_GOVERNANCE_EVIDENCE.json'
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$message) { $failures.Add($message) }
function Read-RepoFile([string]$relativePath) {
    $path = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Failure "MISSING: $relativePath"
        return ''
    }
    return Get-Content -LiteralPath $path -Raw -Encoding utf8
}

try {
    $evidence = Get-Content -LiteralPath $evidencePath -Raw -Encoding utf8 | ConvertFrom-Json
}
catch {
    Add-Failure "INVALID_JSON: docs/V4_BATCH_15_GOVERNANCE_EVIDENCE.json -> $($_.Exception.Message)"
    $evidence = $null
}

$requiredDocs = @(
    'docs/JCFB_V4_BATCH_15_PREDICTION_ARCHITECTURE_GOVERNANCE_DECISION.md',
    'docs/V4_BATCH_15_FROZEN_INPUT_ORDERING_AMENDMENT.md',
    'docs/V4_PREDICTION_INPUT_FEATURE_PROFILE_CONTRACT.md',
    'docs/V4_GATE_TO_PREDICTION_INTERFACE_CONTRACT.md',
    'docs/V4_PREDICTION_FUSION_GOVERNANCE.md',
    'docs/V4_BATCH_15_ENGINE_CONTRACTS.md',
    'docs/V4_PROBABILITY_SEMANTICS_CONTRACT.md',
    'docs/V4_PREDICTION_MODEL_ARTIFACT_REGISTRY_CONTRACT.md',
    'docs/V4_DETERMINISTIC_REPLAY_HASH_PROFILE.md',
    'docs/V4_BATCH_15_ENTRY_REVIEW.md',
    'docs/JCFB_V4_BATCH_15_PREDICTION_MODEL_TRAINING_GOVERNANCE_DECISION.md',
    'docs/V4_BATCH_15_MODEL_TRAINING_TASK_REGISTRY_AMENDMENT.md',
    'docs/V4_BATCH_15_ENGINE_TRAINING_PROFILES.md',
    'docs/V4_BATCH_15_PREDICTION_TRAINING_READINESS_REVIEW.md'
)
foreach ($relativePath in $requiredDocs) { $null = Read-RepoFile $relativePath }

$trainingConfigPaths = @(
    'config/prediction_training/v4_prediction_training_governance.json',
    'config/prediction_training/v4_prediction_model_registry.json',
    'config/prediction_training/v4_prediction_training_readiness_review.json'
)
foreach ($relativePath in $trainingConfigPaths) { $null = Read-RepoFile $relativePath }

$trainingGovernance = $null
$modelRegistry = $null
$readinessReview = $null
try { $trainingGovernance = Get-Content -LiteralPath (Join-Path $repoRoot $trainingConfigPaths[0]) -Raw -Encoding utf8 | ConvertFrom-Json } catch { Add-Failure "INVALID_JSON: $($trainingConfigPaths[0])" }
try { $modelRegistry = Get-Content -LiteralPath (Join-Path $repoRoot $trainingConfigPaths[1]) -Raw -Encoding utf8 | ConvertFrom-Json } catch { Add-Failure "INVALID_JSON: $($trainingConfigPaths[1])" }
try { $readinessReview = Get-Content -LiteralPath (Join-Path $repoRoot $trainingConfigPaths[2]) -Raw -Encoding utf8 | ConvertFrom-Json } catch { Add-Failure "INVALID_JSON: $($trainingConfigPaths[2])" }

$frozen = Read-RepoFile 'docs/V4_FROZEN_INPUT_CONTRACT.md'
$decision = Read-RepoFile 'docs/JCFB_V4_BATCH_15_PREDICTION_ARCHITECTURE_GOVERNANCE_DECISION.md'
$ordering = Read-RepoFile 'docs/V4_BATCH_15_FROZEN_INPUT_ORDERING_AMENDMENT.md'
$review = Read-RepoFile 'docs/V4_BATCH_15_ENTRY_REVIEW.md'
$statusDocs = @(
    (Read-RepoFile 'docs/V4_TASK_REGISTRY_001_100.md'),
    (Read-RepoFile 'docs/V4_TASK_DEPENDENCY_REGISTER.md'),
    (Read-RepoFile 'docs/V4_DEPENDENCY_GRAPH_012_100.md'),
    (Read-RepoFile 'docs/V4_BATCH_EXECUTION_PLAN.md'),
    (Read-RepoFile 'docs/V4_MASTER_BUILD_CHECKLIST.md'),
    (Read-RepoFile 'docs/V4_EXECUTION_CLASSIFICATION.md')
)
$registryText = $statusDocs[0]
$dependencyText = $statusDocs[1]
$classificationText = $statusDocs[5]

foreach ($term in @('frozen-input@2.0.0', 'pre-prediction', 'Frozen Input', 'Prediction')) {
    if ($frozen.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { Add-Failure "FROZEN_CONTRACT_TERM_MISSING: $term" }
}
foreach ($term in @('PREDICTION_MODEL_ARTIFACT_NOT_APPROVED', 'UPSTREAM_IMPLEMENTATION_NOT_ACCEPTED', 'FROZEN_INPUT_NOT_IMPLEMENTED', 'BLOCKED')) {
    if ($decision.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0 -and $review.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { Add-Failure "ENTRY_BLOCKER_MISSING: $term" }
}
foreach ($term in @('prediction-input@1.0.0', 'gate-to-prediction@1.0.0', 'prediction-fusion@1.0.0', 'engine-feature-profile@1.0.0', 'prediction-probability@1.0.0', 'prediction-model-artifact@1.0.0', 'deterministic-replay@1.0.0')) {
    if ($decision.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { Add-Failure "CONTRACT_NOT_REFERENCED: $term" }
}
if ($ordering -notmatch '(?s)V4-076.*V4-052.*V4-053.*V4-054.*V4-055') { Add-Failure 'ORDERING_EDGE_MISSING: V4-076 -> V4-052..055' }
if ($ordering -match 'V4-076.*depends on.*V4-075') { Add-Failure 'REVERSE_EDGE_PRESENT: V4-076 -> V4-075' }

if ($null -ne $evidence) {
    if ($evidence.decision -ne 'BATCH-15_ENTRY_REVIEW_BLOCKED') { Add-Failure "WRONG_REVIEW_DECISION: $($evidence.decision)" }
    foreach ($task in @('V4-049','V4-050','V4-051')) {
        if ($evidence.batch_14.tasks.$task -ne 'COMPLETE') { Add-Failure "BATCH14_STATUS_NOT_COMPLETE: $task" }
    }
    if ($evidence.batch_14.status -ne 'COMPLETE' -or $evidence.batch_14.closure_gate -ne 'PASS') { Add-Failure 'BATCH14_CLOSURE_NOT_COMPLETE_PASS' }
    foreach ($task in @('V4-076','V4-052','V4-053','V4-054','V4-055')) {
        if ($evidence.tasks.$task.primary_batch -ne 'BATCH-15') { Add-Failure "PRIMARY_BATCH_NOT_B15: $task" }
        if ($evidence.tasks.$task.status -ne 'TODO') { Add-Failure "IMPLEMENTATION_STATUS_NOT_TODO: $task" }
    }
    if ($evidence.tasks.'V4-076'.depends_on -contains 'V4-075') { Add-Failure 'EVIDENCE_REVERSE_EDGE: V4-076 depends on V4-075' }
    foreach ($task in @('V4-052','V4-053','V4-054','V4-055')) {
        if (-not ($evidence.tasks.$task.depends_on -contains 'V4-076')) { Add-Failure "ENGINE_MISSING_FROZEN_INPUT_DEPENDENCY: $task" }
    }
}

if ($null -ne $trainingGovernance) {
    if ($trainingGovernance.decision -ne 'PREDICTION_MODEL_TRAINING_GOVERNANCE_RESOLVED') { Add-Failure 'TRAINING_GOVERNANCE_NOT_RESOLVED' }
    if ($trainingGovernance.task_identity.new_task_ids_created -ne $false) { Add-Failure 'TRAINING_CREATED_UNAPPROVED_TASK_ID' }
    if ($trainingGovernance.task_identity.execution_authorized -ne $false) { Add-Failure 'TRAINING_EXECUTION_SHOULD_BE_PAUSED' }
    if ($trainingGovernance.training_dataset_contract.version -ne 'prediction-training-dataset@1.0.0') { Add-Failure 'TRAINING_DATASET_CONTRACT_VERSION_INVALID' }
    if ($trainingGovernance.temporal_split_contract.random_split -ne 'FORBIDDEN') { Add-Failure 'RANDOM_SPLIT_NOT_FORBIDDEN' }
    if ($trainingGovernance.boundary_rules.manual_fusion_weights -ne $false) { Add-Failure 'MANUAL_FUSION_WEIGHTS_NOT_FORBIDDEN' }
    if ($trainingGovernance.boundary_rules.quality_score_as_numeric_feature -ne $false) { Add-Failure 'QUALITY_SCORE_FEATURE_NOT_FORBIDDEN' }
    if ($trainingGovernance.boundary_rules.silent_imputation -ne $false) { Add-Failure 'SILENT_IMPUTATION_NOT_FORBIDDEN' }
    if ($trainingGovernance.canonicalization.algorithm -ne 'SHA-256' -or $trainingGovernance.canonicalization.profile -ne 'v4-canonical-json@1.0' -or $trainingGovernance.canonical_hash -notmatch '^sha256:[0-9a-f]{64}$') { Add-Failure 'TRAINING_GOVERNANCE_CANONICAL_HASH_INVALID' }
    foreach ($role in @('OUTCOME','HANDICAP','GOALS','HTFT')) {
        if ($null -eq $trainingGovernance.engine_training_profiles.$role) { Add-Failure "ENGINE_TRAINING_PROFILE_MISSING: $role" }
    }
}
if ($null -ne $modelRegistry) {
    if ($modelRegistry.status -ne 'NO_APPROVED_ARTIFACTS_PRESENT') { Add-Failure 'MODEL_REGISTRY_STATUS_INVALID' }
    if ($modelRegistry.artifacts.Count -ne 0) { Add-Failure 'MODEL_REGISTRY_MUST_BE_EMPTY_BEFORE_FIT' }
    if ($modelRegistry.canonical_hash -notmatch '^sha256:[0-9a-f]{64}$') { Add-Failure 'MODEL_REGISTRY_CANONICAL_HASH_INVALID' }
    foreach ($role in @('OUTCOME','HANDICAP','GOALS','HTFT')) {
        if ($modelRegistry.role_readiness.$role -ne 'NO_TRAINING_PIPELINE') { Add-Failure "MODEL_ROLE_READINESS_INVALID: $role" }
    }
}
if ($null -ne $readinessReview) {
    if ($readinessReview.decision -ne 'PREDICTION_TRAINING_READINESS_BLOCKED') { Add-Failure 'TRAINING_READINESS_MUST_BE_BLOCKED' }
    if ($readinessReview.pipeline_readiness.formal_model_fit_allowed -ne $false) { Add-Failure 'FORMAL_MODEL_FIT_MUST_BE_BLOCKED' }
    if ($readinessReview.pipeline_readiness.formal_engine_implementation_allowed -ne $false) { Add-Failure 'FORMAL_ENGINE_IMPLEMENTATION_MUST_BE_BLOCKED' }
    if ($readinessReview.historical_as_of_dataset.constructible_now -ne $false) { Add-Failure 'DATASET_MUST_NOT_BE_CLAIMED_CONSTRUCTIBLE' }
    if ($readinessReview.canonical_hash -notmatch '^sha256:[0-9a-f]{64}$') { Add-Failure 'READINESS_CANONICAL_HASH_INVALID' }
    foreach ($role in @('OUTCOME','HANDICAP','GOALS','HTFT')) {
        if ($readinessReview.engine_readiness.$role.status -ne 'BLOCKED') { Add-Failure "ENGINE_READINESS_NOT_BLOCKED: $role" }
        if ($readinessReview.engine_readiness.$role.usable_sample_count -ne 'UNKNOWN') { Add-Failure "ENGINE_SAMPLE_COUNT_MUST_BE_UNKNOWN: $role" }
    }
}

foreach ($task in @('V4-049','V4-050','V4-051')) {
    if ($registryText -notmatch "(?m)^\| $task \|.*\| COMPLETE \|$") { Add-Failure "REGISTRY_TASK_NOT_COMPLETE: $task" }
    if ($dependencyText -notmatch "(?m)^\| $task \|.*\| COMPLETE \|$") { Add-Failure "DEPENDENCY_TASK_NOT_COMPLETE: $task" }
    if ($classificationText -notmatch "(?m)^\| $task \|.*\| COMPLETE[; ]") { Add-Failure "CLASSIFICATION_TASK_NOT_COMPLETE: $task" }
}
if ($registryText -notmatch '(?m)^\| V4-076 \|.*\| BATCH-15 \|') { Add-Failure 'REGISTRY_V4-076_PRIMARY_BATCH_NOT_B15' }
if ($dependencyText -notmatch '(?m)^\| V4-076 \|.*\| V4-022, V4-038, V4-039, V4-049, V4-050, V4-051 \|') { Add-Failure 'DEPENDENCY_V4-076_UPSTREAM_NOT_AMENDED' }
foreach ($task in @('V4-052','V4-053','V4-054','V4-055')) {
    if ($dependencyText -notmatch "(?m)^\| $task \|.*V4-076.*\|") { Add-Failure "DEPENDENCY_ENGINE_MISSING_V4-076: $task" }
}
$v076Line = @($dependencyText -split "`r?`n" | Where-Object { $_ -match '^\| V4-076 \|' }) | Select-Object -First 1
if ($v076Line) {
    $v076Fields = $v076Line.Split('|')
    if ($v076Fields.Count -gt 4 -and $v076Fields[4].Trim() -match 'V4-075') { Add-Failure 'DEPENDENCY_REVERSE_EDGE_IN_LIVE_TABLE: V4-076 -> V4-075' }
}

foreach ($text in $statusDocs) {
    if ($text -notmatch 'BATCH-14' -or $text -notmatch 'COMPLETE' -or $text -notmatch 'Closure Gate PASS') { Add-Failure 'STATUS_SOURCE_MISSING: BATCH-14 COMPLETE / Closure Gate PASS' }
    if ($text -notmatch 'V4-049' -or $text -notmatch 'V4-050' -or $text -notmatch 'V4-051' -or $text -notmatch 'COMPLETE') { Add-Failure 'STATUS_SOURCE_MISSING: V4-049/050/051 COMPLETE' }
}

$changed = @(git -C $repoRoot diff --name-only HEAD)
$forbiddenChanged = @($changed | Where-Object {
    $_ -match '^(tools/|database/migrations/|migrations/)' -or
    $_ -match '(?i)v3\.3\.3|v333' -or
    ($_ -match '(?i)supabase' -and $_ -notmatch '^docs/')
})
if ($forbiddenChanged.Count -gt 0) { Add-Failure "FORBIDDEN_CHANGED_PATHS: $($forbiddenChanged -join ', ')" }

if ($failures.Count -gt 0) {
    Write-Output 'V4 BATCH-15 GOVERNANCE VALIDATION: FAIL'
    $failures | ForEach-Object { Write-Output $_ }
    exit 1
}

Write-Output 'V4 BATCH-15 GOVERNANCE VALIDATION: PASS'
Write-Output 'Ordering: V4-076 -> V4-052/V4-053/V4-054/V4-055'
Write-Output 'BATCH-14 status consistency: COMPLETE / Closure Gate PASS'
Write-Output 'Entry Review: BLOCKED with explicit remaining blockers'
Write-Output 'Safety boundary: no engine implementation, Score/Risk/Production/Supabase/migration/V3.3.3 change'
