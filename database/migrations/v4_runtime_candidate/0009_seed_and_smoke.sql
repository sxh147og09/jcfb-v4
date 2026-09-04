-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.009
-- source_design_file: database/migrations/v4/0009_seed_and_smoke.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: sha256:e4c96f434a8359b54e397f209e565b94162a01037c1cf91e9bd96bf0b948bc20
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.009
-- sequence: 0009
-- name: v4-seed-smoke
-- migration_version: migration@20260901.009
-- depends_on: [migration@20260901.008]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: sha256:e4c96f434a8359b54e397f209e565b94162a01037c1cf91e9bd96bf0b948bc20
-- status: DRAFT
-- This candidate records only DRAFT acceptance metadata; it inserts no match, prediction,
-- or result rows. It is executable only on the disposable target named by the manifest.
--
-- Forward-fix 1.0: the prior 0009 attempt rolled back on SQLSTATE 42883 because
-- the existing 0007 audit trigger function resolved the public.digest symbol, while
-- the provider-owned pgcrypto extension is installed in extensions. This
-- candidate replaces that still-unapplied function body before any 0009 audited
-- insert. It uses extensions.digest(...) explicitly, creates no public.digest
-- wrapper, and does not move the extension.
-- failure_provenance: PGCRYPTO_SCHEMA_MISMATCH / SQLSTATE 42883
-- production_resume_scope: 0009 ONLY
-- requires_new_explicit_resume_approval: YES

BEGIN;

SET LOCAL TIME ZONE 'UTC';

-- The function was created by the frozen 0007 candidate. Replacing its body is
-- the forward-only repair for the failed, unapplied 0009 path; existing trigger
-- bindings remain intact and V3.3.3 objects are not touched.
CREATE OR REPLACE FUNCTION governance.append_audit_event()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance
AS $$
DECLARE
  new_data jsonb := to_jsonb(NEW);
  old_data jsonb := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
  actor_value text := COALESCE(NULLIF(current_setting('v4.actor', true), ''), current_user);
  actor_role_value text := COALESCE(NULLIF(current_setting('v4.actor_role', true), ''), current_role);
  entity_type_value text := TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
  entity_id_value text;
  match_id_value uuid;
  previous_hash text;
  happened_at_value timestamptz := clock_timestamp();
  audit_metadata jsonb := jsonb_build_object(
    'trigger_name', TG_NAME,
    'candidate_manifest', 'v4-runtime-candidate-manifest@1.0.0',
    'hash_profile', 'disposable-runtime-audit-envelope@1.0'
  );
  audit_envelope jsonb;
  entry_hash_value text;
BEGIN
  entity_id_value := COALESCE(
    new_data->>'model_version_id', new_data->>'engine_version_id',
    new_data->>'match_id', new_data->>'evidence_id',
    new_data->>'team_context_id', new_data->>'evidence_bundle_id',
    new_data->>'frozen_input_id', new_data->>'feature_bundle_id',
    new_data->>'engine_run_id', new_data->>'prediction_id',
    new_data->>'frozen_prediction_id', new_data->>'result_id',
    new_data->>'review_id', new_data->>'tier_a_sample_id',
    new_data->>'promotion_review_id', new_data->>'calibration_record_id',
    new_data->>'release_pointer_event_id', new_data->>'incident_id',
    new_data->>'registry_record_id', new_data->>'migration_id',
    new_data->>'hash_algorithm', new_data->>'acceptance_snapshot_id',
    new_data->>'projection_id', 'unidentified'
  );
  IF (new_data->>'match_id') ~ '^[0-9a-fA-F-]{36}$' THEN
    match_id_value := (new_data->>'match_id')::uuid;
  END IF;
  PERFORM pg_advisory_xact_lock(pg_catalog.hashtext(entity_type_value || ':' || entity_id_value));
  SELECT entry_hash INTO previous_hash
    FROM governance.audit_logs
   WHERE entity_type = entity_type_value AND entity_id = entity_id_value
   ORDER BY happened_at DESC, audit_log_id DESC
   LIMIT 1
   FOR UPDATE;
  audit_envelope := jsonb_build_object(
    'actor', actor_value,
    'actor_role', actor_role_value,
    'action', TG_OP,
    'entity_type', entity_type_value,
    'entity_id', entity_id_value,
    'match_id', match_id_value,
    'before_state', old_data,
    'after_state', new_data,
    'metadata', audit_metadata,
    'happened_at', happened_at_value
  );
  entry_hash_value := 'sha256:' || encode(
    extensions.digest(convert_to(audit_envelope::text, 'UTF8'), 'sha256'), 'hex'
  );
  INSERT INTO governance.audit_logs (
    actor, actor_role, action, entity_type, entity_id, match_id,
    before_state, after_state, metadata, happened_at, prev_hash, entry_hash,
    hash_algorithm, hash_profile
  ) VALUES (
    actor_value, actor_role_value, TG_OP, entity_type_value, entity_id_value, match_id_value,
    old_data, new_data, audit_metadata, happened_at_value, previous_hash, entry_hash_value,
    'SHA-256', 'disposable-runtime-audit-envelope@1.0'
  );
  RETURN NEW;
END;
$$;

-- Acceptance snapshots are append-only evidence for the deployment acceptance gate.
CREATE TABLE governance.deployment_acceptance_snapshots (
  acceptance_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  migration_id text NOT NULL,
  migration_version text NOT NULL,
  migration_hash text NOT NULL,
  target_environment text NOT NULL,
  target_identity text NOT NULL,
  precheck_pass boolean NOT NULL DEFAULT false,
  ddl_apply_pass boolean NOT NULL DEFAULT false,
  constraint_pass boolean NOT NULL DEFAULT false,
  rls_pass boolean NOT NULL DEFAULT false,
  trigger_pass boolean NOT NULL DEFAULT false,
  view_pass boolean NOT NULL DEFAULT false,
  smoke_pass boolean NOT NULL DEFAULT false,
  advisor_review_pass boolean NOT NULL DEFAULT false,
  no_future_leakage_gate_pass boolean NOT NULL DEFAULT false,
  v333_isolation_pass boolean NOT NULL DEFAULT false,
  secret_scan_pass boolean NOT NULL DEFAULT false,
  migration_history_recorded boolean NOT NULL DEFAULT false,
  overall_status text NOT NULL CHECK (overall_status IN ('DRAFT', 'BLOCKED', 'ACCEPTED')),
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  notes text NOT NULL DEFAULT '',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK ((overall_status <> 'ACCEPTED' AND migration_hash = 'PENDING_CANONICAL_HASH') OR governance.is_v4_hash(migration_hash)),
  CHECK (overall_status <> 'ACCEPTED' OR (
    precheck_pass AND ddl_apply_pass AND constraint_pass AND rls_pass
    AND trigger_pass AND view_pass AND smoke_pass AND advisor_review_pass
    AND no_future_leakage_gate_pass AND v333_isolation_pass
    AND secret_scan_pass AND migration_history_recorded
  ))
);

ALTER TABLE governance.deployment_acceptance_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE governance.deployment_acceptance_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE governance.deployment_acceptance_snapshots TO service_role;
CREATE TRIGGER v4_acceptance_snapshot_append_only
BEFORE UPDATE OR DELETE ON governance.deployment_acceptance_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_acceptance_snapshot_audit_event
AFTER INSERT ON governance.deployment_acceptance_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();

-- Static registry candidates only. These rows deliberately remain DRAFT and
-- carry the generated candidate hashes without granting production approval.
-- There is no ON CONFLICT fallback: history/preflight is the primary guard.
INSERT INTO governance.hash_algorithm_registry
  (hash_algorithm, hash_profile, canonicalization_version, status, notes)
VALUES
  ('SHA-256', 'v4-canonical-json@1.0', 'v4-canonical-migration@1.0.0', 'DRAFT',
   'Disposable candidate records generated canonical hashes; production promotion and release profile remain PRODUCTION_REVIEW_REQUIRED');

INSERT INTO governance.v4_schema_registry
  (migration_id, sequence, name, migration_version, depends_on,
   schema_contract_version, authored_at, migration_hash, status, success, notes)
VALUES
  ('migration@20260901.001', 1, 'v4-prerequisites', 'migration@20260901.001', ARRAY[]::text[], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:1b959f089bc3f46e272ee7edc19b6a9665c78b4067cdad470a3ebc98a513f2bb', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.002', 2, 'v4-registries-core', 'migration@20260901.002', ARRAY['migration@20260901.001'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:7edfc9c4c2c0085f63d0e0860f0d2f74f6a1e85d9b1ac4e602571347e5dd332a', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.003', 3, 'v4-market-context', 'migration@20260901.003', ARRAY['migration@20260901.002'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:dc493407c012e1296b884ab64eaa251ee6b32fff6c0a9d5cacfe4860098db808', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.004', 4, 'v4-frozen-runtime', 'migration@20260901.004', ARRAY['migration@20260901.003'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.005', 5, 'v4-evaluation', 'migration@20260901.005', ARRAY['migration@20260901.004'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.006', 6, 'v4-governance-audit', 'migration@20260901.006', ARRAY['migration@20260901.005'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:85386b242f6f1ef8fabd1aa09b07f1b4c3082b589b0c6c320bb9705883a5a52d', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.007', 7, 'v4-security-rls', 'migration@20260901.007', ARRAY['migration@20260901.006'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:952ae622fba16f831389b8bfd3b0bfa05b6278f721c41c768532f37d6178a4b0', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.008', 8, 'v4-views-projections', 'migration@20260901.008', ARRAY['migration@20260901.007'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:f2ddf1fd7a69e38bc224c5e19c8db08824d76a6f566eae9fa722a52c644584e3', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.009', 9, 'v4-seed-smoke', 'migration@20260901.009', ARRAY['migration@20260901.008'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:e4c96f434a8359b54e397f209e565b94162a01037c1cf91e9bd96bf0b948bc20', 'DRAFT', false, 'disposable-candidate manifest entry');

-- Runtime smoke harness functions/scripts are specified in
-- docs/V4_MIGRATION_SMOKE_TESTS.md. They must run on a disposable target,
-- use real caller roles, and never be invoked by this candidate file.

COMMIT;
