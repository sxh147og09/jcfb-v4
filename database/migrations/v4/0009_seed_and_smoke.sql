-- DESIGN ONLY - DO NOT APPLY
-- migration_id: migration@20260901.009
-- sequence: 0009
-- name: v4-seed-smoke
-- migration_version: migration@20260901.009
-- depends_on: [migration@20260901.008]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- Candidate static registry/smoke DDL only; no matches, predictions, or
-- result rows are inserted. This file is not an execution script.

BEGIN;

-- Acceptance snapshots are append-only evidence of a future deployment gate.
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
-- retain PENDING_CANONICAL_HASH until the approved canonicalizer runs. There
-- is no ON CONFLICT fallback: history/preflight is the primary guard.
INSERT INTO governance.hash_algorithm_registry
  (hash_algorithm, hash_profile, canonicalization_version, status, notes)
VALUES
  ('SHA-256', 'v4-canonical-json@1.0', 'v4-canonical-json@1.0', 'DRAFT',
   'TODO_DECISION: approve target implementation and canonical byte profile');

INSERT INTO governance.v4_schema_registry
  (migration_id, sequence, name, migration_version, depends_on,
   schema_contract_version, authored_at, migration_hash, status, success, notes)
VALUES
  ('migration@20260901.001', 1, 'v4-prerequisites', 'migration@20260901.001', ARRAY[]::text[], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.002', 2, 'v4-registries-core', 'migration@20260901.002', ARRAY['migration@20260901.001'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.003', 3, 'v4-market-context', 'migration@20260901.003', ARRAY['migration@20260901.002'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.004', 4, 'v4-frozen-runtime', 'migration@20260901.004', ARRAY['migration@20260901.003'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.005', 5, 'v4-evaluation', 'migration@20260901.005', ARRAY['migration@20260901.004'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.006', 6, 'v4-governance-audit', 'migration@20260901.006', ARRAY['migration@20260901.005'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.007', 7, 'v4-security-rls', 'migration@20260901.007', ARRAY['migration@20260901.006'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.008', 8, 'v4-views-projections', 'migration@20260901.008', ARRAY['migration@20260901.007'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry'),
  ('migration@20260901.009', 9, 'v4-seed-smoke', 'migration@20260901.009', ARRAY['migration@20260901.008'], 'v4-database-schema@1.0.0', '2026-09-01T00:00:00+08:00', 'PENDING_CANONICAL_HASH', 'DRAFT', false, 'Design-only manifest entry');

-- Future smoke harness functions/scripts are specified in
-- docs/V4_MIGRATION_SMOKE_TESTS.md. They must run on a disposable target,
-- use real caller roles, and never be invoked by this design file.

COMMIT;
