-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.004
-- source_design_file: database/migrations/v4/0004_frozen_runtime.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.004
-- sequence: 0004
-- name: v4-frozen-runtime
-- migration_version: migration@20260901.004
-- depends_on: [migration@20260901.003]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb
-- status: DRAFT
-- This candidate creates Frozen Input/runtime schema only; it performs no model execution.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

CREATE TABLE model.frozen_inputs (
  frozen_input_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  revision integer NOT NULL CHECK (revision > 0),
  frozen_input_revision text NOT NULL CHECK (frozen_input_revision ~ '^fi-[0-9]{8}-[0-9]{6}$'),
  canonical_match_hash text NOT NULL CHECK (governance.is_v4_hash(canonical_match_hash)),
  feature_schema_version text NOT NULL,
  dataset_version text NOT NULL,
  schema_version text NOT NULL,
  migration_version text NOT NULL,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  owner_role text NOT NULL CHECK (owner_role IN ('PRODUCTION', 'EXPERIMENT')),
  comparison_mode text NOT NULL CHECK (comparison_mode IN ('FORWARD_AB', 'EXPERIMENT_ONLY', 'NOT_APPLICABLE')),
  ab_comparison_group_id uuid,
  frozen_at timestamptz,
  immutable boolean NOT NULL DEFAULT false,
  future_information_leakage boolean NOT NULL DEFAULT false,
  run_invalid boolean NOT NULL DEFAULT false,
  tier_a_eligible boolean NOT NULL DEFAULT false,
  status text NOT NULL CHECK (status IN ('DRAFT', 'VALIDATED', 'FROZEN', 'SUPERSEDED', 'BLOCKED', 'REJECTED')),
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  supersedes_frozen_input_id uuid REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  gate_reason text,
  source_summary jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_summary) = 'object'),
  contract_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, revision),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK ((status IN ('FROZEN', 'SUPERSEDED')) = immutable),
  CHECK (immutable = false OR frozen_at IS NOT NULL),
  CHECK (frozen_at IS NULL OR frozen_at < kickoff_at),
  CHECK ((comparison_mode = 'FORWARD_AB') = (ab_comparison_group_id IS NOT NULL)),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid AND immutable))
);

CREATE TABLE model.frozen_input_official_odds (
  frozen_input_official_odds_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_id uuid NOT NULL REFERENCES market.official_odds_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(used_snapshot_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, snapshot_id)
);

CREATE TABLE model.frozen_input_external_markets (
  frozen_input_external_market_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_id uuid NOT NULL REFERENCES market.external_market_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(used_snapshot_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, snapshot_id)
);

CREATE TABLE model.frozen_input_contexts (
  frozen_input_context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  team_context_id uuid NOT NULL REFERENCES context.team_context_snapshots(team_context_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_context_hash text NOT NULL CHECK (governance.is_v4_hash(used_context_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, team_context_id)
);

CREATE TABLE model.frozen_input_evidence_bundles (
  frozen_input_evidence_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_bundle_id uuid NOT NULL REFERENCES context.evidence_bundles(evidence_bundle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_bundle_hash text NOT NULL CHECK (governance.is_v4_hash(used_bundle_hash)),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, evidence_bundle_id)
);

CREATE TABLE model.frozen_input_model_refs (
  frozen_input_model_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, model_version_id)
);

CREATE TABLE model.frozen_input_engine_refs (
  frozen_input_engine_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_version_id uuid NOT NULL REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, engine_version_id)
);

CREATE TABLE model.feature_bundles (
  feature_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  shadow_revision text,
  experiment_revision text,
  experiment_id uuid,
  feature_schema_version text NOT NULL,
  generator_version text NOT NULL,
  input_hash text NOT NULL CHECK (governance.is_v4_hash(input_hash)),
  feature_hash text NOT NULL CHECK (governance.is_v4_hash(feature_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  generated_at timestamptz NOT NULL,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  feature_values jsonb NOT NULL CHECK (jsonb_typeof(feature_values) = 'object'),
  missingness_summary jsonb NOT NULL CHECK (jsonb_typeof(missingness_summary) = 'object'),
  quality_flags jsonb NOT NULL CHECK (jsonb_typeof(quality_flags) = 'array'),
  status text NOT NULL CHECK (status IN ('CREATED', 'VALIDATED', 'BLOCKED', 'INVALID', 'SUPERSEDED')),
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_input_id, role, generator_version, input_hash),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK ((role = 'SHADOW') = (shadow_revision IS NOT NULL)),
  CHECK ((role = 'EXPERIMENT') = (experiment_revision IS NOT NULL)),
  CHECK (role <> 'PRODUCTION' OR (shadow_revision IS NULL AND experiment_revision IS NULL AND experiment_id IS NULL))
);

CREATE TABLE model.engine_runs (
  engine_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  feature_bundle_id uuid NOT NULL REFERENCES model.feature_bundles(feature_bundle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_version_id uuid NOT NULL REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role_revision text NOT NULL,
  shadow_revision text,
  experiment_revision text,
  experiment_id uuid,
  build_id text,
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  implementation_hash text NOT NULL CHECK (governance.is_v4_hash(implementation_hash)),
  config_version text NOT NULL,
  config_hash text NOT NULL CHECK (governance.is_v4_hash(config_hash)),
  schema_version text NOT NULL,
  migration_version text NOT NULL,
  dataset_version text NOT NULL,
  input_hash text NOT NULL CHECK (governance.is_v4_hash(input_hash)),
  output_hash text NOT NULL CHECK (governance.is_v4_hash(output_hash)),
  run_at timestamptz NOT NULL,
  run_completed_at timestamptz,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  runtime_ms double precision NOT NULL CHECK (runtime_ms >= 0 AND runtime_ms <> 'Infinity'::double precision AND runtime_ms <> '-Infinity'::double precision),
  runtime_environment jsonb NOT NULL CHECK (jsonb_typeof(runtime_environment) = 'object'),
  random_seed bigint,
  simulation_version text,
  status text NOT NULL CHECK (status IN ('CREATED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'INVALID', 'CANCELLED')),
  future_information_leakage boolean NOT NULL DEFAULT false,
  run_invalid boolean NOT NULL DEFAULT false,
  tier_a_eligible boolean NOT NULL DEFAULT false,
  promotion_evidence boolean NOT NULL DEFAULT false,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warnings) = 'array'),
  errors jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(errors) = 'array'),
  payload jsonb,
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (status <> 'SUCCEEDED' OR (payload IS NOT NULL AND run_completed_at IS NOT NULL)),
  CHECK (status IN ('FAILED', 'BLOCKED', 'INVALID') OR jsonb_array_length(errors) = 0 OR run_invalid),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid AND run_completed_at < kickoff_at)),
  CHECK ((role = 'SHADOW') = (shadow_revision IS NOT NULL)),
  CHECK ((role = 'EXPERIMENT') = (experiment_revision IS NOT NULL)),
  CHECK (role <> 'PRODUCTION' OR (shadow_revision IS NULL AND experiment_revision IS NULL AND experiment_id IS NULL))
);

CREATE TABLE model.predictions (
  prediction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  prediction_revision integer NOT NULL CHECK (prediction_revision > 0),
  stage text NOT NULL CHECK (btrim(stage) <> ''),
  role_revision text NOT NULL,
  shadow_revision text,
  experiment_revision text,
  experiment_id uuid,
  model_run_at timestamptz NOT NULL,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  market_predictions jsonb NOT NULL CHECK (jsonb_typeof(market_predictions) = 'object'),
  consensus jsonb NOT NULL CHECK (jsonb_typeof(consensus) = 'object'),
  disagreement jsonb NOT NULL CHECK (jsonb_typeof(disagreement) = 'object'),
  uncertainty jsonb NOT NULL CHECK (jsonb_typeof(uncertainty) = 'object'),
  risk jsonb NOT NULL CHECK (jsonb_typeof(risk) = 'object'),
  confidence_grade text NOT NULL CHECK (confidence_grade IN ('VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN', 'BLOCKED')),
  recommendation_state text NOT NULL CHECK (recommendation_state IN ('PASS', 'NO_STRONG_RECOMMENDATION', 'BLOCKED', 'INSUFFICIENT_DATA')),
  recommendation_strength text NOT NULL CHECK (recommendation_strength IN ('NONE', 'WEAK', 'MODERATE', 'STRONG', 'NOT_APPLICABLE')),
  input_hash text NOT NULL CHECK (governance.is_v4_hash(input_hash)),
  output_hash text NOT NULL CHECK (governance.is_v4_hash(output_hash)),
  prediction_hash text NOT NULL CHECK (governance.is_v4_hash(prediction_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  future_information_leakage boolean NOT NULL DEFAULT false,
  run_invalid boolean NOT NULL DEFAULT false,
  tier_a_eligible boolean NOT NULL DEFAULT false,
  promotion_evidence boolean NOT NULL DEFAULT false,
  status text NOT NULL CHECK (status IN ('DRAFT', 'FORMAL', 'FROZEN', 'SUPERSEDED', 'INVALID', 'BLOCKED')),
  supersedes_prediction_id uuid REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, model_version_id, role, stage, prediction_revision),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (model_run_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid)),
  CHECK ((role = 'SHADOW') = (shadow_revision IS NOT NULL)),
  CHECK ((role = 'EXPERIMENT') = (experiment_revision IS NOT NULL)),
  CHECK (role <> 'PRODUCTION' OR (shadow_revision IS NULL AND experiment_revision IS NULL AND experiment_id IS NULL))
);

CREATE TABLE model.prediction_engine_runs (
  prediction_engine_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_run_id uuid NOT NULL REFERENCES model.engine_runs(engine_run_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  market text NOT NULL CHECK (market IN ('spf', 'rqspf', 'total_goals', 'exact_score', 'half_full', 'consensus', 'uncertainty', 'risk')),
  lineage_purpose text NOT NULL CHECK (lineage_purpose IN ('PRIMARY_MARKET', 'CONSENSUS', 'UNCERTAINTY', 'RISK', 'SUPPORTING')),
  output_hash text NOT NULL CHECK (governance.is_v4_hash(output_hash)),
  sequence integer NOT NULL CHECK (sequence > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (prediction_id, engine_run_id, market, lineage_purpose),
  UNIQUE (prediction_id, sequence)
);

CREATE TABLE model.frozen_predictions (
  frozen_prediction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  freeze_revision integer NOT NULL CHECK (freeze_revision > 0),
  prediction_hash text NOT NULL CHECK (governance.is_v4_hash(prediction_hash)),
  frozen_snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_snapshot_hash)),
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
  frozen_at timestamptz NOT NULL,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  immutable boolean NOT NULL DEFAULT true CHECK (immutable),
  future_information_leakage boolean NOT NULL DEFAULT false,
  run_invalid boolean NOT NULL DEFAULT false,
  tier_a_eligible boolean NOT NULL DEFAULT false,
  promotion_evidence boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'FROZEN' CHECK (status IN ('FROZEN', 'SUPERSEDED', 'BLOCKED', 'INVALID')),
  supersedes_frozen_prediction_id uuid REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, role, model_version_id, freeze_revision),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (frozen_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid))
);

CREATE INDEX frozen_inputs_hash_idx ON model.frozen_inputs (frozen_input_hash);
CREATE INDEX frozen_input_official_snapshot_idx ON model.frozen_input_official_odds (snapshot_id);
CREATE INDEX frozen_input_external_snapshot_idx ON model.frozen_input_external_markets (snapshot_id);
CREATE INDEX frozen_input_context_idx ON model.frozen_input_contexts (team_context_id);
CREATE INDEX frozen_input_bundle_idx ON model.frozen_input_evidence_bundles (evidence_bundle_id);
CREATE INDEX frozen_input_model_ref_idx ON model.frozen_input_model_refs (model_version_id);
CREATE INDEX frozen_input_engine_ref_idx ON model.frozen_input_engine_refs (engine_version_id);
CREATE INDEX feature_bundles_frozen_role_idx ON model.feature_bundles (frozen_input_id, role, generated_at DESC);
CREATE INDEX engine_runs_lineage_idx ON model.engine_runs (frozen_input_id, role, engine_version_id);
CREATE INDEX engine_runs_input_hash_idx ON model.engine_runs (input_hash);
CREATE INDEX engine_runs_output_hash_idx ON model.engine_runs (output_hash);
CREATE INDEX engine_runs_match_run_idx ON model.engine_runs (match_id, role, run_at DESC);
CREATE INDEX predictions_match_role_idx ON model.predictions (match_id, role, model_version_id, stage, prediction_revision DESC);
CREATE INDEX prediction_engine_runs_engine_idx ON model.prediction_engine_runs (engine_run_id, prediction_id);
CREATE INDEX frozen_predictions_match_freeze_idx ON model.frozen_predictions (match_id, freeze_revision DESC);

-- Trigger/function installation is intentionally deferred to 0007. The
-- tables above carry direct checks; cross-table same-match, role, hash, and
-- no-future-leakage rules are installed by candidate 0007 and exercised by the runtime gate.

COMMIT;
