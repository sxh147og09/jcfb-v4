[CmdletBinding()]
param(
    [switch]$SkipSecretScan
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$contractFiles = @(
    'docs/V4_DATA_CONTRACT.md',
    'docs/V4_CANONICAL_FACTS_SCHEMA.md',
    'docs/V4_ODDS_SNAPSHOT_CONTRACT.md',
    'docs/V4_TEAM_CONTEXT_CONTRACT.md',
    'docs/V4_EVIDENCE_CONTRACT.md',
    'docs/V4_FROZEN_INPUT_CONTRACT.md',
    'docs/V4_FEATURE_BUNDLE_CONTRACT.md',
    'docs/V4_STATISTICAL_HISTORICAL_INPUT_CONTRACT.md',
    'docs/V4_FOOTBALL_INTELLIGENCE_FEATURE_CONTRACT.md',
    'docs/V4_FOOTBALL_CONTEXT_INTEGRATION_CONTRACT.md',
    'docs/V4_ENGINE_OUTPUT_CONTRACT.md',
    'docs/V4_PREDICTION_CONTRACT.md',
    'docs/V4_RESULT_REVIEW_CONTRACT.md'
)

$requiredTerms = @{
    'docs/V4_DATA_CONTRACT.md' = @('contract_version', 'UNKNOWN', 'UNAVAILABLE', 'NOT_VERIFIED', 'BLOCKED', 'NOT_APPLICABLE', 'NULL', 'Objective Facts', 'Model Interpretation', 'Hash canonicalization', 'ID policy', 'MAJOR', 'MINOR', 'PATCH')
    'docs/V4_CANONICAL_FACTS_SCHEMA.md' = @('match_id', 'data_date', 'official_match_no', 'competition_id', 'competition_name', 'kickoff_at', 'timezone', 'home_team_id', 'away_team_id', 'official_handicap', 'match_status', 'identity_resolution_state=REQUIRES_REVIEW')
    'docs/V4_ODDS_SNAPSHOT_CONTRACT.md' = @('snapshot_id', 'snapshot_kind', 'captured_at', 'source_is_official', 'market_availability', 'market_unavailable_reason', 'spf', 'rqspf', 'total_goals', 'exact_score', 'half_full', 'EUROPEAN_1X2', 'ASIAN_HANDICAP', 'OVER_UNDER')
    'docs/V4_TEAM_CONTEXT_CONTRACT.md' = @('team-context@2.0.0', 'injuries', 'suspensions', 'lineup_status', 'starting_xi', 'coach', 'tactical_style', 'motivation', 'schedule_pressure', 'fatigue', 'travel', 'weather', 'pitch', 'source_summary', 'context_confidence', 'conflicts', 'NONE_CONFIRMED', 'bare `confidence` field is forbidden')
    'docs/V4_EVIDENCE_CONTRACT.md' = @('evidence_id', 'claim_type', 'claim', 'entity_refs', 'published_at', 'retrieved_at', 'valid_from', 'verification_state', 'contradiction_state', 'VERIFIED', 'NOT_VERIFIED', 'CONFLICTED', 'STALE', 'REJECTED')
    'docs/V4_FROZEN_INPUT_CONTRACT.md' = @('feature_bundle_id', 'feature_snapshot_hash', 'feature_bundle_contract_version', 'frozen_input_hash', 'immutable', 'FROZEN', 'pre-prediction freeze artifact')
    'docs/V4_FEATURE_BUNDLE_CONTRACT.md' = @('statistical_features', 'football_context_features', 'market_features', 'league_features', 'tactical_features', 'score_features', 'quality_features', 'feature_bundle_id', 'feature_schema_version', 'generator_version', 'input_hash', 'feature_hash', 'generated_at', 'missingness_summary', 'quality_flags')
    'docs/V4_STATISTICAL_HISTORICAL_INPUT_CONTRACT.md' = @('historical_input_id', 'source_match_id', 'target_match_id', 'availability_at', 'result_known_at', 'stat_available_at', 'INSUFFICIENT_SAMPLE', 'half_life_matches=10', 'competition_id + season_id', 'supersedes_id')
    'docs/V4_FOOTBALL_INTELLIGENCE_FEATURE_CONTRACT.md' = @('football-intelligence-feature@1.0.0', 'PRE_FREEZE_FEATURE_ARTIFACT', 'feature_bundle_id', 'feature_snapshot_hash', 'statistical_feature_refs', 'team_context_refs', 'evidence_refs', 'feature_quality', 'frozen_input_id', 'FUTURE_DATA', 'supersedes_artifact_id')
    'docs/V4_FOOTBALL_CONTEXT_INTEGRATION_CONTRACT.md' = @('football-context-integration@1.0.0', 'football_intelligence_artifact_ref', 'feature_bundle_ref', 'statistical_feature_refs', 'team_context_refs', 'evidence_refs', 'SEPARATE_DIMENSIONS_ONLY', 'PROJECTED', 'CONFLICTED', 'frozen_input_id')
    'docs/V4_ENGINE_OUTPUT_CONTRACT.md' = @('engine_run_id', 'role', 'model_version', 'engine_name', 'engine_version', 'revision', 'implementation_hash', 'config_hash', 'input_hash', 'output_hash', 'run_at', 'runtime_ms', 'status', 'warnings', 'errors', 'payload', 'Outcome', 'Handicap', 'Goals', 'HTFT', 'Score', 'Upset', 'Simulation', 'Consensus', 'Uncertainty', 'Risk')
    'docs/V4_PREDICTION_CONTRACT.md' = @('prediction_id', 'prediction_revision', 'frozen_input_id', 'engine_run_refs', 'market_predictions', 'consensus', 'disagreement', 'uncertainty', 'risk', 'confidence_grade', 'recommendation_state', 'recommendation_strength', 'SPF', 'RQSPF', 'Total Goals', 'Exact Score', 'Half-Full', 'Frozen Prediction', 'supersedes_frozen_prediction_id')
    'docs/V4_RESULT_REVIEW_CONTRACT.md' = @('result_id', 'full_time_home', 'full_time_away', 'half_time_home', 'half_time_away', 'result_scope', 'REGULATION_90_PLUS_STOPPAGE', 'official_result_payload', 'verified_at', 'result_hash', 'MODEL_EVALUATION', 'MATCH_EXPLANATION', 'market_hit_results', 'score_metrics', 'error_attribution', 'reviewed_at', 'review_hash')
}

$failures = [System.Collections.Generic.List[string]]::new()
$contents = @{}

foreach ($relativePath in $contractFiles) {
    $path = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $failures.Add("MISSING: $relativePath")
        continue
    }

    $text = Get-Content -LiteralPath $path -Raw -Encoding utf8
    $contents[$relativePath] = $text
    foreach ($term in $requiredTerms[$relativePath]) {
        if ($text.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            $failures.Add("TERM_MISSING: $relativePath -> $term")
        }
    }

    $jsonBlocks = [regex]::Matches($text, '(?ms)```json\s*(.*?)\s*```')
    if (($relativePath -ne 'docs/V4_DATA_CONTRACT.md') -and ($jsonBlocks.Count -eq 0)) {
        $failures.Add("JSON_EXAMPLE_MISSING: $relativePath")
    }
    foreach ($block in $jsonBlocks) {
        try {
            $null = $block.Groups[1].Value | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $failures.Add("JSON_INVALID: $relativePath -> $($_.Exception.Message)")
        }
    }
}

if (-not $SkipSecretScan) {
    $secretPattern = '(?i)(sk-[A-Za-z0-9]{20,}|sb_secret_[A-Za-z0-9]{12,}|(?:\b(?:supabase[_-]?)?service[_-]role[_-]key\b)[ \t]*[=:][ \t]*["'']?[A-Za-z0-9./+=_-]{20,}|password[ \t]*[=:][ \t]*["''][^"'']{8,}["'']|api[_-]?key[ \t]*[=:][ \t]*["''][^"'']{12,}["''])'
    $tracked = @(git -C $repoRoot ls-files)
    foreach ($relativePath in $tracked) {
        if ($relativePath -eq 'scripts/validate_v4_data_contracts.ps1') {
            continue
        }
        $path = Join-Path $repoRoot $relativePath
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $text = Get-Content -LiteralPath $path -Raw -Encoding utf8
            if ($text -match $secretPattern) {
                $failures.Add("SECRET_PATTERN: $relativePath")
            }
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Output 'V4-008 DATA CONTRACT VALIDATION: FAIL'
    $failures | ForEach-Object { Write-Output $_ }
    exit 1
}

Write-Output 'V4-008 DATA CONTRACT VALIDATION: PASS'
Write-Output ("Contract files checked: {0}" -f $contractFiles.Count)
Write-Output 'JSON examples: PASS'
Write-Output 'Required vocabulary and boundary terms: PASS'
if ($SkipSecretScan) {
    Write-Output 'Secret scan: SKIPPED'
}
else {
    Write-Output 'Secret scan: PASS'
}
