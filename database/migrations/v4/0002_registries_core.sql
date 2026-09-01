-- DESIGN ONLY - DO NOT APPLY
-- migration_id: migration@20260901.002
-- sequence: 0002
-- name: v4-registries-core
-- migration_version: migration@20260901.002
-- depends_on: [migration@20260901.001]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- Candidate DDL only; do not connect, apply, or seed runtime data.

BEGIN;

CREATE TABLE governance.model_versions (
  model_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_family text NOT NULL CHECK (btrim(model_family) <> ''),
  model_name text NOT NULL CHECK (model_name ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  model_version text NOT NULL CHECK (btrim(model_version) <> ''),
  major integer NOT NULL CHECK (major >= 0),
  minor integer NOT NULL CHECK (minor >= 0),
  patch integer NOT NULL CHECK (patch >= 0),
  revision text NOT NULL CHECK (revision ~ '^r[0-9]+$'),
  jcfb_version text NOT NULL,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  canonical_output_channel text NOT NULL CHECK (btrim(canonical_output_channel) <> ''),
  implementation_hash text NOT NULL CHECK (governance.is_v4_hash(implementation_hash)),
  config_version text NOT NULL,
  config_hash text NOT NULL CHECK (governance.is_v4_hash(config_hash)),
  schema_version text NOT NULL,
  dataset_version text NOT NULL,
  migration_version text NOT NULL,
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  compatibility_level text NOT NULL CHECK (compatibility_level IN ('PATCH_COMPATIBLE', 'MINOR_COMPATIBLE', 'MAJOR_BREAKING')),
  status text NOT NULL CHECK (status IN ('DRAFT', 'EXPERIMENT', 'SHADOW', 'PROMOTION_REVIEW', 'PRODUCTION', 'RETIRED', 'BLOCKED')),
  is_canonical_active boolean NOT NULL DEFAULT false,
  effective_at timestamptz,
  retired_at timestamptz,
  supersedes_model_version_id uuid REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  approval_reference text,
  approved_at timestamptz,
  retirement_reason text,
  contract_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (model_name, model_version, role, revision),
  CHECK (model_version = model_name || '@' || major::text || '.' || minor::text || '.' || patch::text),
  CHECK (NOT is_canonical_active OR (role = 'PRODUCTION' AND status = 'PRODUCTION' AND effective_at IS NOT NULL)),
  CHECK (retired_at IS NULL OR effective_at IS NULL OR retired_at >= effective_at),
  CHECK ((status = 'PRODUCTION') = (approval_reference IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE governance.engine_versions (
  engine_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  model_family text NOT NULL CHECK (btrim(model_family) <> ''),
  engine_name text NOT NULL CHECK (engine_name ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  engine_version text NOT NULL CHECK (btrim(engine_version) <> ''),
  major integer NOT NULL CHECK (major >= 0),
  minor integer NOT NULL CHECK (minor >= 0),
  patch integer NOT NULL CHECK (patch >= 0),
  revision text NOT NULL CHECK (revision ~ '^r[0-9]+$'),
  jcfb_version text NOT NULL,
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  canonical_output_channel text NOT NULL CHECK (btrim(canonical_output_channel) <> ''),
  implementation_hash text NOT NULL CHECK (governance.is_v4_hash(implementation_hash)),
  config_version text NOT NULL,
  config_hash text NOT NULL CHECK (governance.is_v4_hash(config_hash)),
  schema_version text NOT NULL,
  dataset_version text NOT NULL,
  migration_version text NOT NULL,
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  compatibility_level text NOT NULL CHECK (compatibility_level IN ('PATCH_COMPATIBLE', 'MINOR_COMPATIBLE', 'MAJOR_BREAKING')),
  status text NOT NULL CHECK (status IN ('DRAFT', 'EXPERIMENT', 'SHADOW', 'PROMOTION_REVIEW', 'PRODUCTION', 'RETIRED', 'BLOCKED')),
  is_canonical_active boolean NOT NULL DEFAULT false,
  effective_at timestamptz,
  retired_at timestamptz,
  supersedes_engine_version_id uuid REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  approval_reference text,
  approved_at timestamptz,
  retirement_reason text,
  contract_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (engine_name, engine_version, role, revision),
  CHECK (engine_version = engine_name || '@' || major::text || '.' || minor::text || '.' || patch::text),
  CHECK (NOT is_canonical_active OR (role = 'PRODUCTION' AND status = 'PRODUCTION' AND effective_at IS NOT NULL)),
  CHECK (retired_at IS NULL OR effective_at IS NULL OR retired_at >= effective_at)
);

CREATE TABLE core.competitions (
  competition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  competition_key text NOT NULL CHECK (btrim(competition_key) <> ''),
  governing_source text NOT NULL CHECK (btrim(governing_source) <> ''),
  display_name text NOT NULL CHECK (btrim(display_name) <> ''),
  normalized_name text NOT NULL CHECK (btrim(normalized_name) <> ''),
  timezone text NOT NULL CHECK (btrim(timezone) <> ''),
  identity_resolution_state text NOT NULL CHECK (identity_resolution_state IN ('RESOLVED', 'REQUIRES_REVIEW', 'BLOCKED', 'UNKNOWN')),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE', 'BLOCKED', 'RETIRED', 'UNKNOWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (governing_source, competition_key)
);

CREATE TABLE core.teams (
  team_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_team_key text NOT NULL CHECK (btrim(canonical_team_key) <> ''),
  source_namespace text NOT NULL CHECK (btrim(source_namespace) <> ''),
  canonical_name text NOT NULL CHECK (btrim(canonical_name) <> ''),
  normalized_name text NOT NULL CHECK (btrim(normalized_name) <> ''),
  identity_resolution_state text NOT NULL CHECK (identity_resolution_state IN ('RESOLVED', 'REQUIRES_REVIEW', 'BLOCKED', 'UNKNOWN')),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE', 'BLOCKED', 'RETIRED', 'UNKNOWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (source_namespace, canonical_team_key)
);

CREATE TABLE core.team_aliases (
  team_alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id uuid NOT NULL REFERENCES core.teams(team_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  alias_text text NOT NULL CHECK (btrim(alias_text) <> ''),
  normalized_alias text NOT NULL CHECK (btrim(normalized_alias) <> ''),
  locale text NOT NULL CHECK (btrim(locale) <> ''),
  source_scope text NOT NULL CHECK (btrim(source_scope) <> ''),
  valid_from timestamptz NOT NULL,
  valid_to timestamptz,
  verification_state text NOT NULL CHECK (verification_state IN ('VERIFIED', 'NOT_VERIFIED', 'CONFLICTED', 'STALE', 'REJECTED')),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (team_id, normalized_alias, locale, source_scope, valid_from),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE core.matches (
  match_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  data_date date NOT NULL,
  official_match_no text NOT NULL CHECK (official_match_no ~ '^[0-9]+$'),
  match_identity_key text NOT NULL,
  competition_id uuid NOT NULL REFERENCES core.competitions(competition_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  home_team_id uuid NOT NULL REFERENCES core.teams(team_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  away_team_id uuid NOT NULL REFERENCES core.teams(team_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  kickoff_at timestamptz NOT NULL,
  timezone text NOT NULL CHECK (btrim(timezone) <> ''),
  match_status text NOT NULL CHECK (match_status IN ('SCHEDULED', 'POSTPONED', 'CANCELLED', 'IN_PROGRESS', 'FINISHED', 'ABANDONED', 'UNKNOWN', 'BLOCKED')),
  intake_status text NOT NULL CHECK (intake_status IN ('OPEN', 'CLOSED', 'NOT_APPLICABLE')),
  identity_resolution_state text NOT NULL CHECK (identity_resolution_state IN ('RESOLVED', 'REQUIRES_REVIEW', 'BLOCKED', 'UNKNOWN')),
  canonical_facts_hash text NOT NULL CHECK (governance.is_v4_hash(canonical_facts_hash)),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (data_date, official_match_no),
  CHECK (home_team_id <> away_team_id),
  CHECK (match_identity_key = data_date::text || ':' || official_match_no)
);

CREATE INDEX model_versions_family_status_idx
  ON governance.model_versions (model_family, status, role, revision);
CREATE INDEX engine_versions_model_role_idx
  ON governance.engine_versions (model_version_id, role, revision);
CREATE INDEX team_aliases_team_idx ON core.team_aliases (team_id, normalized_alias);
CREATE INDEX matches_competition_idx ON core.matches (competition_id, kickoff_at);
CREATE INDEX matches_home_team_idx ON core.matches (home_team_id, kickoff_at);
CREATE INDEX matches_away_team_idx ON core.matches (away_team_id, kickoff_at);
CREATE INDEX matches_identity_key_idx ON core.matches (match_identity_key);

COMMIT;
