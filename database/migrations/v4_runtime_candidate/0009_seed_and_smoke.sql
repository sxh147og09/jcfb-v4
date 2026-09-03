-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.009
-- source_design_file: database/migrations/v4/0009_seed_and_smoke.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: sha256:56c0ad2da49d0a169c080eca023a5a54af4c2089565c244fec5d88301bfd6448
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.009
-- sequence: 0009
-- name: v4-seed-smoke
-- migration_version: migration@20260901.009
-- depends_on: [migration@20260901.008]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: sha256:56c0ad2da49d0a169c080eca023a5a54af4c2089565c244fec5d88301bfd6448
-- status: DRAFT
-- This candidate records only DRAFT acceptance metadata; it inserts no match, prediction,
-- or result rows. It is executable only on the disposable target named by the manifest.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

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
  ('migration@20260901.001', 1, 'v4-prerequisites', 'migration@20260901.001', ARRAY[]::text[], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:c55c6d4a882691d9dc006d55915e8584a696de1c9fd9792243c0b0c50713bb28', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.002', 2, 'v4-registries-core', 'migration@20260901.002', ARRAY['migration@20260901.001'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:7edfc9c4c2c0085f63d0e0860f0d2f74f6a1e85d9b1ac4e602571347e5dd332a', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.003', 3, 'v4-market-context', 'migration@20260901.003', ARRAY['migration@20260901.002'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:dc493407c012e1296b884ab64eaa251ee6b32fff6c0a9d5cacfe4860098db808', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.004', 4, 'v4-frozen-runtime', 'migration@20260901.004', ARRAY['migration@20260901.003'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.005', 5, 'v4-evaluation', 'migration@20260901.005', ARRAY['migration@20260901.004'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.006', 6, 'v4-governance-audit', 'migration@20260901.006', ARRAY['migration@20260901.005'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:85386b242f6f1ef8fabd1aa09b07f1b4c3082b589b0c6c320bb9705883a5a52d', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.007', 7, 'v4-security-rls', 'migration@20260901.007', ARRAY['migration@20260901.006'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:952ae622fba16f831389b8bfd3b0bfa05b6278f721c41c768532f37d6178a4b0', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.008', 8, 'v4-views-projections', 'migration@20260901.008', ARRAY['migration@20260901.007'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:066964964caf34d44c80012120b79f1c09a9e246fe1125d1a7dbb2a88f2a3ce2', 'DRAFT', false, 'disposable-candidate manifest entry'),
  ('migration@20260901.009', 9, 'v4-seed-smoke', 'migration@20260901.009', ARRAY['migration@20260901.008'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'sha256:56c0ad2da49d0a169c080eca023a5a54af4c2089565c244fec5d88301bfd6448', 'DRAFT', false, 'disposable-candidate manifest entry');

-- Runtime smoke harness functions/scripts are specified in
-- docs/V4_MIGRATION_SMOKE_TESTS.md. They must run on a disposable target,
-- use real caller roles, and never be invoked by this candidate file.

COMMIT;
