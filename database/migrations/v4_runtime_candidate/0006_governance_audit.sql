-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.006
-- source_design_file: database/migrations/v4/0006_governance_audit.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: PENDING_CANONICAL_HASH
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.006
-- sequence: 0006
-- name: v4-governance-audit
-- migration_version: migration@20260901.006
-- depends_on: [migration@20260901.005]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- This candidate creates governance/audit schema only; it seeds no release or incident business rows.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

CREATE TABLE governance.release_pointer_events (
  release_pointer_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_family text NOT NULL CHECK (btrim(model_family) <> ''),
  canonical_output_channel text NOT NULL CHECK (btrim(canonical_output_channel) <> ''),
  previous_model_version_id uuid REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  successor_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  action text NOT NULL CHECK (action IN ('ACTIVATE', 'RETIRE', 'ROLLBACK', 'WITHDRAW')),
  reason text NOT NULL CHECK (btrim(reason) <> ''),
  actor text NOT NULL CHECK (btrim(actor) <> ''),
  effective_at timestamptz NOT NULL,
  evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
  event_hash text NOT NULL CHECK (governance.is_v4_hash(event_hash)),
  prev_hash text CHECK (prev_hash IS NULL OR governance.is_v4_hash(prev_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE governance.incidents (
  incident_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_lineage_id uuid NOT NULL DEFAULT gen_random_uuid(),
  incident_revision integer NOT NULL CHECK (incident_revision > 0),
  incident_class text NOT NULL CHECK (btrim(incident_class) <> ''),
  severity text NOT NULL CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  status text NOT NULL CHECK (status IN ('OPEN', 'MITIGATED', 'RESOLVED', 'CLOSED')),
  affected_entity_type text NOT NULL,
  affected_entity_id text NOT NULL,
  match_id uuid REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  affected_role text CHECK (affected_role IS NULL OR affected_role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  detected_at timestamptz NOT NULL,
  known_at timestamptz NOT NULL,
  containment jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(containment) = 'object'),
  resolution jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(resolution) = 'object'),
  owner text,
  before_state jsonb NOT NULL CHECK (jsonb_typeof(before_state) = 'object'),
  after_state jsonb NOT NULL CHECK (jsonb_typeof(after_state) = 'object'),
  supersedes_incident_id uuid REFERENCES governance.incidents(incident_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (incident_lineage_id, incident_revision),
  CHECK (known_at >= detected_at)
);

CREATE TABLE governance.audit_logs (
  audit_log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor text NOT NULL,
  actor_role text NOT NULL,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  match_id uuid REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  before_state jsonb NOT NULL CHECK (jsonb_typeof(before_state) = 'object'),
  after_state jsonb NOT NULL CHECK (jsonb_typeof(after_state) = 'object'),
  metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
  happened_at timestamptz NOT NULL,
  prev_hash text CHECK (prev_hash IS NULL OR governance.is_v4_hash(prev_hash)),
  entry_hash text NOT NULL CHECK (governance.is_v4_hash(entry_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entry_hash)
);

-- At most one active Production pointer per family/channel. The controlled
-- activation function must lock the scope, validate Promotion Review/manual
-- approval, append a pointer event, and then update only approved metadata.
CREATE UNIQUE INDEX active_production_model_uq
  ON governance.model_versions (model_family, canonical_output_channel)
  WHERE role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active;
CREATE UNIQUE INDEX active_production_engine_uq
  ON governance.engine_versions (engine_name, canonical_output_channel)
  WHERE role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active;

CREATE INDEX release_pointer_scope_idx
  ON governance.release_pointer_events (model_family, canonical_output_channel, effective_at DESC);
CREATE INDEX incidents_severity_status_time_idx
  ON governance.incidents (severity, status, created_at DESC);
CREATE INDEX incidents_entity_idx
  ON governance.incidents (affected_entity_type, affected_entity_id, created_at DESC);
CREATE INDEX audit_entity_time_idx
  ON governance.audit_logs (entity_type, entity_id, happened_at);
CREATE INDEX audit_prev_hash_idx ON governance.audit_logs (prev_hash);

-- Controlled audit append and append-only mutation functions are installed or
-- completed only after the security review in 0007. A caller-supplied digest
-- is required; this design never invents a canonical hash.

COMMIT;
