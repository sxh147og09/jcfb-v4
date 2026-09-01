-- DESIGN ONLY - DO NOT APPLY
-- migration_id: migration@20260901.001
-- sequence: 0001
-- name: v4-prerequisites
-- migration_version: migration@20260901.001
-- depends_on: []
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
--
-- Candidate PostgreSQL/Supabase DDL only. No connection directive, psql meta
-- command, or automatic execution path is present. Apply only after the V4
-- preflight, canonical hash, human approval, and acceptance gates pass.

BEGIN;

-- TODO_DECISION: confirm the target owner, extension availability, and
-- provider policy before applying. Supabase extension versions are not pinned
-- here; the target's approved default version must be recorded by preflight.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- TODO_DECISION: confirm these namespaces are either empty/new or explicitly
-- approved for exact-object coexistence. They are V4-only boundaries.
-- Time policy: persist instants as timestamptz; deployment/session timezone is
-- TODO_DECISION and must be confirmed as UTC. `data_date` and any display
-- timezone remain explicit business fields; Asia/Shanghai is not inferred.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS context;
CREATE SCHEMA IF NOT EXISTS model;
CREATE SCHEMA IF NOT EXISTS evaluation;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS public;

-- Format validation only. This helper never calculates a digest.
CREATE FUNCTION governance.is_v4_hash(value text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
  SELECT value ~ '^sha256:[0-9a-f]{64}$';
$$;

-- The manifest registry describes immutable migration definitions. It permits
-- PENDING_CANONICAL_HASH only while the row is DRAFT; an applied history row
-- must contain a real canonical hash.
CREATE TABLE governance.v4_schema_registry (
  registry_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  migration_id text NOT NULL,
  sequence integer NOT NULL CHECK (sequence > 0),
  name text NOT NULL CHECK (btrim(name) <> ''),
  migration_version text NOT NULL,
  depends_on text[] NOT NULL DEFAULT ARRAY[]::text[],
  schema_contract_version text NOT NULL,
  authored_at timestamptz NOT NULL,
  migration_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT', 'APPROVED_FOR_DEPLOYMENT', 'APPLIED', 'FAILED', 'SUPERSEDED')),
  app_version text,
  applied_at timestamptz,
  applied_by text,
  success boolean NOT NULL DEFAULT false,
  notes text NOT NULL DEFAULT '',
  prev_migration_hash text,
  chain_hash text,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (migration_id),
  UNIQUE (sequence),
  UNIQUE (migration_version),
  CHECK (array_position(depends_on, '') IS NULL),
  CHECK (migration_id ~ '^migration@[0-9]{8}\.[0-9]{3}$'),
  CHECK (migration_version ~ '^migration@[0-9]{8}\.[0-9]{3}$'),
  CHECK ((status IN ('DRAFT', 'SUPERSEDED') AND migration_hash = 'PENDING_CANONICAL_HASH') OR governance.is_v4_hash(migration_hash)),
  CHECK (prev_migration_hash IS NULL OR governance.is_v4_hash(prev_migration_hash)),
  CHECK (chain_hash IS NULL OR governance.is_v4_hash(chain_hash)),
  CHECK (status <> 'APPLIED' OR (success AND applied_at IS NOT NULL AND applied_by IS NOT NULL)),
  CHECK (status <> 'DRAFT' OR NOT success),
  CHECK (status <> 'FAILED' OR NOT success)
);

-- One terminal execution outcome per migration identity. This is intentionally
-- separate from the manifest so a draft is never mutated into applied history.
CREATE TABLE governance.schema_migrations (
  migration_id text PRIMARY KEY,
  sequence integer NOT NULL UNIQUE CHECK (sequence > 0),
  name text NOT NULL CHECK (btrim(name) <> ''),
  migration_version text NOT NULL UNIQUE,
  schema_contract_version text NOT NULL,
  migration_hash text NOT NULL CHECK (governance.is_v4_hash(migration_hash)),
  applied_at timestamptz,
  applied_by text,
  app_version text,
  success boolean NOT NULL,
  status text NOT NULL CHECK (status IN ('APPLIED', 'FAILED', 'BLOCKED', 'SUPERSEDED')),
  partial_state boolean NOT NULL DEFAULT false,
  notes text NOT NULL DEFAULT '',
  prev_migration_hash text CHECK (prev_migration_hash IS NULL OR governance.is_v4_hash(prev_migration_hash)),
  chain_hash text CHECK (chain_hash IS NULL OR governance.is_v4_hash(chain_hash)),
  recorded_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK (migration_id ~ '^migration@[0-9]{8}\.[0-9]{3}$'),
  CHECK (migration_version ~ '^migration@[0-9]{8}\.[0-9]{3}$'),
  CHECK ((status = 'APPLIED') = success),
  CHECK ((success AND applied_at IS NOT NULL AND applied_by IS NOT NULL) OR NOT success),
  CHECK (status <> 'APPLIED' OR NOT partial_state)
);

CREATE TABLE governance.hash_algorithm_registry (
  hash_algorithm text NOT NULL,
  hash_profile text NOT NULL,
  canonicalization_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT', 'APPROVED', 'RETIRED')),
  approved_by text,
  approved_at timestamptz,
  notes text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  PRIMARY KEY (hash_algorithm, hash_profile),
  CHECK ((status = 'APPROVED') = (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

-- No history row is seeded here. A controlled executor records one exact,
-- real-hash row after each accepted migration; 0009 only designs static
-- manifest seed entries and an acceptance snapshot shape.

COMMIT;
