-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.005
-- source_design_file: database/migrations/v4/0005_evaluation.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.005
-- sequence: 0005
-- name: v4-evaluation
-- migration_version: migration@20260901.005
-- depends_on: [migration@20260901.004]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394
-- status: DRAFT
-- Candidate postmatch/evaluation DDL only; no results or reviews are seeded.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

CREATE TABLE evaluation.official_results (
  result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  result_lineage_id uuid NOT NULL DEFAULT gen_random_uuid(),
  result_revision integer NOT NULL CHECK (result_revision > 0),
  supersedes_result_id uuid REFERENCES evaluation.official_results(result_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  full_time_home integer NOT NULL CHECK (full_time_home >= 0),
  full_time_away integer NOT NULL CHECK (full_time_away >= 0),
  half_time_home integer NOT NULL CHECK (half_time_home >= 0),
  half_time_away integer NOT NULL CHECK (half_time_away >= 0),
  result_scope text NOT NULL CHECK (result_scope IN ('REGULATION_90_PLUS_STOPPAGE', 'GOVERNED_MARKET_OVERRIDE')),
  official_result_payload jsonb NOT NULL CHECK (jsonb_typeof(official_result_payload) = 'object'),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  verified_at timestamptz NOT NULL,
  result_hash text NOT NULL CHECK (governance.is_v4_hash(result_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('VERIFIED', 'BLOCKED', 'CORRECTED', 'REJECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, result_revision),
  UNIQUE (result_lineage_id, result_revision)
);

CREATE TABLE evaluation.postmatch_reviews (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  result_id uuid NOT NULL REFERENCES evaluation.official_results(result_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  review_type text NOT NULL CHECK (review_type IN ('MODEL_EVALUATION', 'MATCH_EXPLANATION')),
  review_revision integer NOT NULL CHECK (review_revision > 0),
  supersedes_review_id uuid REFERENCES evaluation.postmatch_reviews(review_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  market_hit_results jsonb,
  score_metrics jsonb,
  error_attribution jsonb NOT NULL CHECK (jsonb_typeof(error_attribution) = 'object'),
  postmatch_evidence_refs jsonb,
  allowed_input_set text NOT NULL CHECK (allowed_input_set IN ('FROZEN_PREDICTION_RESULT_ONLY', 'POSTMATCH_EXPLANATION_EVIDENCE')),
  reviewed_at timestamptz NOT NULL,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  review_hash text NOT NULL CHECK (governance.is_v4_hash(review_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('VALID', 'BLOCKED', 'SUPERSEDED', 'REJECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (frozen_prediction_id, review_type, review_revision),
  CHECK ((review_type = 'MODEL_EVALUATION') = (allowed_input_set = 'FROZEN_PREDICTION_RESULT_ONLY')),
  CHECK ((review_type = 'MATCH_EXPLANATION') = (allowed_input_set = 'POSTMATCH_EXPLANATION_EVIDENCE'))
);

CREATE TABLE evaluation.tier_a_samples (
  tier_a_sample_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sample_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  shadow_prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  shadow_frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  shadow_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  shadow_engine_version_id uuid NOT NULL REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  result_id uuid NOT NULL REFERENCES evaluation.official_results(result_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  review_id uuid NOT NULL REFERENCES evaluation.postmatch_reviews(review_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  shadow_revision text NOT NULL,
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  production_implementation_hash text NOT NULL CHECK (governance.is_v4_hash(production_implementation_hash)),
  production_config_hash text NOT NULL CHECK (governance.is_v4_hash(production_config_hash)),
  production_input_hash text NOT NULL CHECK (governance.is_v4_hash(production_input_hash)),
  production_output_hash text NOT NULL CHECK (governance.is_v4_hash(production_output_hash)),
  shadow_implementation_hash text NOT NULL CHECK (governance.is_v4_hash(shadow_implementation_hash)),
  shadow_config_hash text NOT NULL CHECK (governance.is_v4_hash(shadow_config_hash)),
  shadow_input_hash text NOT NULL CHECK (governance.is_v4_hash(shadow_input_hash)),
  shadow_output_hash text NOT NULL CHECK (governance.is_v4_hash(shadow_output_hash)),
  production_run_completed_at timestamptz NOT NULL,
  shadow_run_completed_at timestamptz NOT NULL,
  prediction_cutoff_at timestamptz NOT NULL,
  kickoff_at timestamptz NOT NULL,
  pair_integrity_passed boolean NOT NULL DEFAULT false,
  completeness_gate_passed boolean NOT NULL DEFAULT false,
  pre_kickoff_gate_passed boolean NOT NULL DEFAULT false,
  future_information_leakage boolean NOT NULL DEFAULT false,
  tier_a_eligible boolean NOT NULL DEFAULT false,
  promotion_evidence boolean NOT NULL DEFAULT false,
  qualification_status text NOT NULL CHECK (qualification_status IN ('ELIGIBLE', 'REJECTED', 'BLOCKED')),
  exclusion_rule_version text NOT NULL,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, production_prediction_id, shadow_prediction_id, shadow_revision),
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (production_run_completed_at < kickoff_at AND shadow_run_completed_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (pair_integrity_passed AND completeness_gate_passed AND pre_kickoff_gate_passed AND NOT future_information_leakage AND qualification_status = 'ELIGIBLE'))
);

CREATE TABLE evaluation.tier_a_run_members (
  tier_a_run_member_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tier_a_sample_id uuid NOT NULL REFERENCES evaluation.tier_a_samples(tier_a_sample_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_run_id uuid NOT NULL REFERENCES model.engine_runs(engine_run_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW')),
  member_order integer NOT NULL CHECK (member_order > 0),
  frozen_input_hash text NOT NULL CHECK (governance.is_v4_hash(frozen_input_hash)),
  output_hash text NOT NULL CHECK (governance.is_v4_hash(output_hash)),
  pre_kickoff_completed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (tier_a_sample_id, role, prediction_id),
  UNIQUE (tier_a_sample_id, member_order)
);

CREATE TABLE evaluation.promotion_reviews (
  promotion_review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  candidate_engine_version_id uuid REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  source_role text NOT NULL DEFAULT 'SHADOW' CHECK (source_role = 'SHADOW'),
  review_revision integer NOT NULL CHECK (review_revision > 0),
  status text NOT NULL CHECK (status IN ('OPEN', 'APPROVED', 'REJECTED', 'WITHDRAWN')),
  forward_evidence jsonb NOT NULL CHECK (jsonb_typeof(forward_evidence) = 'object'),
  calibration_evidence jsonb NOT NULL CHECK (jsonb_typeof(calibration_evidence) = 'object'),
  regression_evidence jsonb NOT NULL CHECK (jsonb_typeof(regression_evidence) = 'object'),
  integrity_evidence jsonb NOT NULL CHECK (jsonb_typeof(integrity_evidence) = 'object'),
  leakage_evidence jsonb NOT NULL CHECK (jsonb_typeof(leakage_evidence) = 'object'),
  performance_evidence jsonb NOT NULL CHECK (jsonb_typeof(performance_evidence) = 'object'),
  manual_approver text,
  approval_reason text,
  approved_at timestamptz,
  production_model_version_id uuid REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  auto_promotion boolean NOT NULL DEFAULT false CHECK (NOT auto_promotion),
  supersedes_promotion_review_id uuid REFERENCES evaluation.promotion_reviews(promotion_review_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (candidate_model_version_id, review_revision),
  CHECK ((status = 'APPROVED') = (manual_approver IS NOT NULL AND approved_at IS NOT NULL AND production_model_version_id IS NOT NULL))
);

CREATE TABLE evaluation.promotion_review_samples (
  promotion_review_sample_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  promotion_review_id uuid NOT NULL REFERENCES evaluation.promotion_reviews(promotion_review_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  tier_a_sample_id uuid NOT NULL REFERENCES evaluation.tier_a_samples(tier_a_sample_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_hash text NOT NULL CHECK (governance.is_v4_hash(evidence_hash)),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (promotion_review_id, tier_a_sample_id)
);

CREATE TABLE evaluation.calibration_records (
  calibration_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_version_id uuid REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  market text NOT NULL CHECK (market IN ('spf', 'rqspf', 'total_goals', 'exact_score', 'half_full')),
  scope_key text NOT NULL,
  confidence_band text NOT NULL,
  sample_window_start date NOT NULL,
  sample_window_end date NOT NULL,
  sample_count bigint NOT NULL CHECK (sample_count >= 0),
  metric_payload jsonb NOT NULL CHECK (jsonb_typeof(metric_payload) = 'object'),
  dataset_version text NOT NULL,
  input_hash text NOT NULL CHECK (governance.is_v4_hash(input_hash)),
  record_revision integer NOT NULL CHECK (record_revision > 0),
  supersedes_calibration_record_id uuid REFERENCES evaluation.calibration_records(calibration_record_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  status text NOT NULL CHECK (status IN ('VALID', 'BLOCKED', 'SUPERSEDED', 'REJECTED')),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (model_version_id, role, market, scope_key, confidence_band, sample_window_start, sample_window_end, record_revision),
  CHECK (sample_window_start <= sample_window_end)
);

CREATE INDEX result_match_verified_idx ON evaluation.official_results (match_id, verified_at DESC);
CREATE INDEX review_frozen_prediction_idx ON evaluation.postmatch_reviews (frozen_prediction_id, reviewed_at DESC);
CREATE INDEX tier_a_shadow_qualified_idx ON evaluation.tier_a_samples (shadow_model_version_id, shadow_engine_version_id, shadow_revision, match_id) WHERE qualification_status = 'ELIGIBLE';
CREATE INDEX tier_a_frozen_input_hash_idx ON evaluation.tier_a_samples (frozen_input_hash, match_id);
CREATE INDEX tier_a_member_engine_idx ON evaluation.tier_a_run_members (engine_run_id, tier_a_sample_id);
CREATE INDEX promotion_candidate_status_idx ON evaluation.promotion_reviews (candidate_model_version_id, status, review_revision DESC);
CREATE INDEX promotion_sample_tier_idx ON evaluation.promotion_review_samples (tier_a_sample_id, promotion_review_id);

-- Result/review/Tier A correction, same-match, role, hash, and no-leakage
-- triggers are installed only by the reviewed 0007 security design.

COMMIT;
