-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.001
-- source_design_file: database/migrations/v4/0001_prerequisites.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: PENDING_CANONICAL_HASH
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
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
-- Candidate PostgreSQL DDL only. It has no connection directive, psql meta command,
-- or automatic execution path. Apply only after the V4 preflight, canonical hash,
-- human approval, and acceptance gates pass.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

-- Disposable-safe decision: target is a fresh local PostgreSQL container; pgcrypto is
-- installed in public. Production extension availability/version remains PRODUCTION_REVIEW_REQUIRED.
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- Disposable-only role bootstrap. These roles have no login and no password.
-- Production role mapping, ownership, and BYPASSRLS policy remain
-- PRODUCTION_REVIEW_REQUIRED. A fresh local target may use service_role as the
-- server-side test principal so the RLS deny-by-default boundary is testable.
DO $$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'anon',
    'authenticated',
    'service_role',
    'v4_fact_intake',
    'v4_production_runtime',
    'v4_shadow_runtime',
    'v4_experiment_runtime',
    'v4_review_promotion',
    'v4_registry_admin',
    'v4_incident_admin'
  ]::text[] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
      EXECUTE format(
        'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
        role_name
      );
    END IF;
  END LOOP;
  EXECUTE 'ALTER ROLE service_role BYPASSRLS';
END;
$$;

-- Disposable-safe decision: the fresh target owns these V4-only namespaces. Production
-- coexistence and namespace ownership remain PRODUCTION_REVIEW_REQUIRED. All session instants
-- are explicitly UTC; data_date and display timezone remain explicit business fields.
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
