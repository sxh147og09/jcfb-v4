-- DESIGN ONLY - DO NOT APPLY
-- JCFB V4-010 Database Schema Blueprint 1.0
--
-- This file is a physical design artifact, not a migration. It must never be
-- piped to psql, supabase db query, apply_migration, or any deployment tool.
-- It creates no real object in this task. TODO_DECISION markers identify
-- version/extension/function choices that require an approved V4-011 review.
-- No secret, password, token, service key, or database URL belongs here.

-- ============================================================================
-- PHASE 0 - prerequisites, extensions, and namespaces (candidate DDL)
-- ============================================================================

-- TODO_DECISION: verify the target PostgreSQL/Supabase version and choose an
-- approved UUIDv7 provider. The portable candidate default below is
-- gen_random_uuid(); changing the default later must not rewrite old IDs.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS context;
CREATE SCHEMA IF NOT EXISTS model;
CREATE SCHEMA IF NOT EXISTS evaluation;
CREATE SCHEMA IF NOT EXISTS governance;
CREATE SCHEMA IF NOT EXISTS public;

-- Format validation only. This function does NOT calculate or fake a hash.
CREATE OR REPLACE FUNCTION governance.is_v4_hash(value text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
  SELECT value ~ '^sha256:[0-9a-f]{64}$';
$$;

-- ============================================================================
-- PHASE 1 - registries and canonical core
-- ============================================================================

CREATE TABLE governance.model_versions (
  model_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_family text NOT NULL CHECK (btrim(model_family) <> ''),
  model_name text NOT NULL CHECK (btrim(model_name) <> ''),
  model_version text NOT NULL CHECK (btrim(model_version) <> ''),
  major integer NOT NULL CHECK (major >= 0),
  minor integer NOT NULL CHECK (minor >= 0),
  patch integer NOT NULL CHECK (patch >= 0),
  revision text NOT NULL CHECK (btrim(revision) <> ''),
  jcfb_version text NOT NULL CHECK (btrim(jcfb_version) <> ''),
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  canonical_output_channel text NOT NULL CHECK (btrim(canonical_output_channel) <> ''),
  implementation_hash text NOT NULL CHECK (governance.is_v4_hash(implementation_hash)),
  config_version text NOT NULL CHECK (btrim(config_version) <> ''),
  config_hash text NOT NULL CHECK (governance.is_v4_hash(config_hash)),
  schema_version text NOT NULL CHECK (btrim(schema_version) <> ''),
  dataset_version text NOT NULL CHECK (btrim(dataset_version) <> ''),
  migration_version text NOT NULL CHECK (btrim(migration_version) <> ''),
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
  CHECK (NOT is_canonical_active OR (role = 'PRODUCTION' AND status = 'PRODUCTION' AND effective_at IS NOT NULL)),
  CHECK (retired_at IS NULL OR effective_at IS NULL OR retired_at >= effective_at),
  CHECK ((status = 'PRODUCTION') = (approval_reference IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE UNIQUE INDEX model_versions_identity_uq
  ON governance.model_versions (model_family, model_name, model_version, role, revision);

CREATE TABLE governance.engine_versions (
  engine_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  model_family text NOT NULL CHECK (btrim(model_family) <> ''),
  engine_name text NOT NULL CHECK (btrim(engine_name) <> ''),
  engine_version text NOT NULL CHECK (btrim(engine_version) <> ''),
  major integer NOT NULL CHECK (major >= 0),
  minor integer NOT NULL CHECK (minor >= 0),
  patch integer NOT NULL CHECK (patch >= 0),
  revision text NOT NULL CHECK (btrim(revision) <> ''),
  jcfb_version text NOT NULL CHECK (btrim(jcfb_version) <> ''),
  role text NOT NULL CHECK (role IN ('PRODUCTION', 'SHADOW', 'EXPERIMENT')),
  canonical_output_channel text NOT NULL CHECK (btrim(canonical_output_channel) <> ''),
  implementation_hash text NOT NULL CHECK (governance.is_v4_hash(implementation_hash)),
  config_version text NOT NULL CHECK (btrim(config_version) <> ''),
  config_hash text NOT NULL CHECK (governance.is_v4_hash(config_hash)),
  schema_version text NOT NULL CHECK (btrim(schema_version) <> ''),
  dataset_version text NOT NULL CHECK (btrim(dataset_version) <> ''),
  migration_version text NOT NULL CHECK (btrim(migration_version) <> ''),
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
  CHECK (NOT is_canonical_active OR (role = 'PRODUCTION' AND status = 'PRODUCTION' AND effective_at IS NOT NULL)),
  CHECK (retired_at IS NULL OR effective_at IS NULL OR retired_at >= effective_at)
);

CREATE UNIQUE INDEX engine_versions_identity_uq
  ON governance.engine_versions (engine_name, engine_version, role, revision);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX competitions_source_key_uq
  ON core.competitions (governing_source, competition_key);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX teams_source_key_uq
  ON core.teams (source_namespace, canonical_team_key);

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
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX team_aliases_scope_uq
  ON core.team_aliases (team_id, normalized_alias, locale, source_scope, valid_from);

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
  CHECK (home_team_id <> away_team_id),
  CHECK (match_identity_key = (data_date::text || ':' || official_match_no))
);

CREATE UNIQUE INDEX matches_daily_business_key_uq
  ON core.matches (data_date, official_match_no);
CREATE INDEX matches_identity_key_idx
  ON core.matches (match_identity_key);

-- ============================================================================
-- PHASE 2 - market, context, and evidence
-- ============================================================================

CREATE TABLE context.evidence_items (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  team_id uuid REFERENCES core.teams(team_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  claim_type text NOT NULL CHECK (btrim(claim_type) <> ''),
  claim jsonb NOT NULL CHECK (jsonb_typeof(claim) = 'object'),
  entity_refs jsonb NOT NULL CHECK (jsonb_typeof(entity_refs) = 'array'),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  published_at timestamptz,
  published_time_state text NOT NULL CHECK (published_time_state IN ('KNOWN', 'UNKNOWN', 'BLOCKED')),
  retrieved_at timestamptz NOT NULL,
  valid_from timestamptz,
  valid_from_time_state text NOT NULL CHECK (valid_from_time_state IN ('KNOWN', 'UNKNOWN', 'BLOCKED')),
  expires_at timestamptz,
  time_reason text,
  confidence jsonb NOT NULL CHECK (jsonb_typeof(confidence) = 'object'),
  verification_state text NOT NULL CHECK (verification_state IN ('VERIFIED', 'NOT_VERIFIED', 'CONFLICTED', 'STALE', 'REJECTED')),
  contradiction_state text NOT NULL CHECK (contradiction_state IN ('NONE', 'PENDING', 'CONFLICTED', 'RESOLVED', 'NOT_APPLICABLE')),
  evidence_hash text NOT NULL CHECK (governance.is_v4_hash(evidence_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  supersedes_evidence_id uuid REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('AVAILABLE', 'UNKNOWN', 'BLOCKED', 'STALE', 'CONFLICT', 'REJECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK (match_id IS NOT NULL OR team_id IS NOT NULL),
  CHECK (expires_at IS NULL OR valid_from IS NULL OR expires_at > valid_from),
  CHECK ((published_time_state = 'KNOWN') = (published_at IS NOT NULL)),
  CHECK ((valid_from_time_state = 'KNOWN') = (valid_from IS NOT NULL)),
  CHECK ((published_time_state = 'KNOWN' AND valid_from_time_state = 'KNOWN') OR time_reason IS NOT NULL)
);

CREATE TABLE context.team_context_snapshots (
  team_context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  team_id uuid NOT NULL REFERENCES core.teams(team_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  side text NOT NULL CHECK (side IN ('HOME', 'AWAY')),
  as_of_at timestamptz NOT NULL,
  injuries jsonb NOT NULL CHECK (jsonb_typeof(injuries) = 'object'),
  suspensions jsonb NOT NULL CHECK (jsonb_typeof(suspensions) = 'object'),
  lineup_status jsonb NOT NULL CHECK (jsonb_typeof(lineup_status) = 'object'),
  starting_xi jsonb NOT NULL CHECK (jsonb_typeof(starting_xi) = 'object'),
  coach jsonb NOT NULL CHECK (jsonb_typeof(coach) = 'object'),
  tactical_style jsonb NOT NULL CHECK (jsonb_typeof(tactical_style) = 'object'),
  motivation jsonb NOT NULL CHECK (jsonb_typeof(motivation) = 'object'),
  schedule_pressure jsonb NOT NULL CHECK (jsonb_typeof(schedule_pressure) = 'object'),
  fatigue jsonb NOT NULL CHECK (jsonb_typeof(fatigue) = 'object'),
  travel jsonb NOT NULL CHECK (jsonb_typeof(travel) = 'object'),
  weather jsonb NOT NULL CHECK (jsonb_typeof(weather) = 'object'),
  pitch jsonb NOT NULL CHECK (jsonb_typeof(pitch) = 'object'),
  source_summary jsonb NOT NULL CHECK (jsonb_typeof(source_summary) = 'array'),
  conflicts jsonb NOT NULL CHECK (jsonb_typeof(conflicts) = 'array'),
  context_confidence jsonb NOT NULL CHECK (jsonb_typeof(context_confidence) = 'object'),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  availability_at timestamptz,
  availability_time_state text NOT NULL CHECK (availability_time_state IN ('KNOWN', 'UNKNOWN', 'BLOCKED')),
  availability_time_basis text CHECK (availability_time_basis IN ('SOURCE_TIMESTAMP', 'PUBLISHED_AT', 'OBSERVED_AT', 'UNKNOWN')),
  context_hash text NOT NULL CHECK (governance.is_v4_hash(context_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
  supersedes_team_context_id uuid REFERENCES context.team_context_snapshots(team_context_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('AVAILABLE', 'UNKNOWN', 'BLOCKED', 'STALE', 'CONFLICT')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK ((availability_time_state = 'KNOWN') = (availability_at IS NOT NULL)),
  CHECK (availability_time_state = 'UNKNOWN' OR availability_time_basis <> 'UNKNOWN')
);

CREATE UNIQUE INDEX team_context_revision_uq
  ON context.team_context_snapshots (match_id, team_id, side, revision);
CREATE INDEX team_context_match_asof_idx
  ON context.team_context_snapshots (match_id, team_id, as_of_at DESC);

-- Normalized evidence references keep context-to-evidence lineage out of JSONB.
CREATE TABLE context.team_context_evidence (
  team_context_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_context_id uuid NOT NULL REFERENCES context.team_context_snapshots(team_context_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_id uuid NOT NULL REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  source_role text NOT NULL CHECK (source_role IN ('PRIMARY', 'SUPPORTING', 'CONFLICTING')),
  used_evidence_hash text NOT NULL CHECK (governance.is_v4_hash(used_evidence_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX team_context_evidence_membership_uq
  ON context.team_context_evidence (team_context_id, evidence_id);
CREATE INDEX team_context_evidence_context_idx
  ON context.team_context_evidence (team_context_id, availability_at DESC);
CREATE INDEX team_context_evidence_evidence_idx
  ON context.team_context_evidence (evidence_id, team_context_id);

CREATE TABLE context.evidence_bundles (
  evidence_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  prediction_cutoff_at timestamptz NOT NULL,
  bundle_revision integer NOT NULL CHECK (bundle_revision > 0),
  inclusion_state text NOT NULL CHECK (btrim(inclusion_state) <> ''),
  gate_status text NOT NULL CHECK (btrim(gate_status) <> ''),
  bundle_hash text NOT NULL CHECK (governance.is_v4_hash(bundle_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('VALIDATED', 'BLOCKED', 'SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX evidence_bundle_revision_uq
  ON context.evidence_bundles (match_id, bundle_revision);

CREATE TABLE context.evidence_bundle_items (
  evidence_bundle_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_bundle_id uuid NOT NULL REFERENCES context.evidence_bundles(evidence_bundle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_id uuid NOT NULL REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  item_order integer NOT NULL CHECK (item_order > 0),
  inclusion_role text NOT NULL CHECK (inclusion_role IN ('REQUIRED', 'SUPPORTING', 'REJECTED')),
  used_evidence_hash text NOT NULL CHECK (governance.is_v4_hash(used_evidence_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX evidence_bundle_items_membership_uq
  ON context.evidence_bundle_items (evidence_bundle_id, evidence_id);
CREATE UNIQUE INDEX evidence_bundle_items_order_uq
  ON context.evidence_bundle_items (evidence_bundle_id, item_order);

CREATE INDEX evidence_match_published_idx
  ON context.evidence_items (match_id, published_at DESC)
  WHERE match_id IS NOT NULL;
CREATE INDEX evidence_bundle_match_cutoff_idx
  ON context.evidence_bundles (match_id, prediction_cutoff_at DESC);

CREATE TABLE market.official_odds_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_kind text NOT NULL CHECK (snapshot_kind IN ('OPENING', 'INTERMEDIATE', 'CURRENT', 'LATEST', 'FINAL', 'CORRECTION')),
  captured_at timestamptz NOT NULL,
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  availability_at timestamptz,
  availability_time_state text NOT NULL CHECK (availability_time_state IN ('KNOWN', 'UNKNOWN', 'BLOCKED')),
  availability_time_basis text CHECK (availability_time_basis IN ('SOURCE_TIMESTAMP', 'PUBLISHED_AT', 'OBSERVED_AT', 'UNKNOWN')),
  source_is_official boolean NOT NULL DEFAULT true CHECK (source_is_official),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  evidence_ref uuid REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  supersedes_snapshot_id uuid REFERENCES market.official_odds_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  market_availability jsonb NOT NULL CHECK (jsonb_typeof(market_availability) = 'object'),
  market_unavailable_reason jsonb NOT NULL CHECK (jsonb_typeof(market_unavailable_reason) = 'object'),
  spf jsonb,
  rqspf jsonb,
  total_goals jsonb,
  exact_score jsonb,
  half_full jsonb,
  snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(snapshot_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE', 'UNKNOWN', 'BLOCKED', 'NOT_APPLICABLE')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK (payload_hash = snapshot_hash),
  CHECK ((availability_time_state = 'KNOWN') = (availability_at IS NOT NULL))
);

CREATE UNIQUE INDEX official_odds_dedup_uq
  ON market.official_odds_snapshots (match_id, source, snapshot_kind, captured_at, snapshot_hash);
CREATE INDEX official_odds_match_captured_idx
  ON market.official_odds_snapshots (match_id, captured_at DESC);
CREATE INDEX official_odds_snapshot_hash_idx
  ON market.official_odds_snapshots (snapshot_hash);

CREATE TABLE market.external_market_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  provider text NOT NULL CHECK (btrim(provider) <> ''),
  market text NOT NULL CHECK (market IN ('EUROPEAN_1X2', 'ASIAN_HANDICAP', 'OVER_UNDER')),
  line_value numeric(8,3),
  normalized_line text NOT NULL CHECK (btrim(normalized_line) <> ''),
  prices jsonb NOT NULL CHECK (jsonb_typeof(prices) = 'object'),
  captured_at timestamptz NOT NULL,
  source_timestamp timestamptz,
  observed_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL,
  availability_at timestamptz,
  availability_time_state text NOT NULL CHECK (availability_time_state IN ('KNOWN', 'UNKNOWN', 'BLOCKED')),
  availability_time_basis text CHECK (availability_time_basis IN ('SOURCE_TIMESTAMP', 'PUBLISHED_AT', 'OBSERVED_AT', 'UNKNOWN')),
  liquidity_quality text NOT NULL CHECK (liquidity_quality IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')),
  source_is_official boolean NOT NULL DEFAULT false CHECK (NOT source_is_official),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_type text NOT NULL,
  source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
  supersedes_snapshot_id uuid REFERENCES market.external_market_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(snapshot_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('AVAILABLE', 'UNKNOWN', 'BLOCKED', 'UNAVAILABLE', 'NOT_VERIFIED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  CHECK ((market = 'EUROPEAN_1X2') = (line_value IS NULL AND normalized_line = 'NOT_APPLICABLE')),
  CHECK (market <> 'EUROPEAN_1X2' OR line_value IS NOT NULL),
  CHECK ((availability_time_state = 'KNOWN') = (availability_at IS NOT NULL))
);

CREATE UNIQUE INDEX external_market_dedup_uq
  ON market.external_market_snapshots (match_id, provider, market, normalized_line, captured_at, snapshot_hash);
CREATE INDEX external_market_match_captured_idx
  ON market.external_market_snapshots (match_id, captured_at DESC);
CREATE INDEX external_snapshot_hash_idx
  ON market.external_market_snapshots (snapshot_hash);

-- ============================================================================
-- PHASE 3 - Frozen Input, Feature Bundles, Engine Runs, Predictions
-- ============================================================================

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
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK ((status IN ('FROZEN', 'SUPERSEDED')) = immutable),
  CHECK (immutable = false OR frozen_at IS NOT NULL),
  CHECK (frozen_at IS NULL OR frozen_at < kickoff_at),
  CHECK ((comparison_mode = 'FORWARD_AB') = (ab_comparison_group_id IS NOT NULL)),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid AND immutable))
);

CREATE UNIQUE INDEX frozen_inputs_match_revision_uq
  ON model.frozen_inputs (match_id, revision);
CREATE INDEX frozen_inputs_hash_idx
  ON model.frozen_inputs (frozen_input_hash);

CREATE TABLE model.frozen_input_official_odds (
  frozen_input_official_odds_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_id uuid NOT NULL REFERENCES market.official_odds_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(used_snapshot_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_official_odds_uq
  ON model.frozen_input_official_odds (frozen_input_id, snapshot_id);

CREATE TABLE model.frozen_input_external_markets (
  frozen_input_external_market_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  snapshot_id uuid NOT NULL REFERENCES market.external_market_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_snapshot_hash text NOT NULL CHECK (governance.is_v4_hash(used_snapshot_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_external_markets_uq
  ON model.frozen_input_external_markets (frozen_input_id, snapshot_id);

CREATE TABLE model.frozen_input_contexts (
  frozen_input_context_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  team_context_id uuid NOT NULL REFERENCES context.team_context_snapshots(team_context_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_context_hash text NOT NULL CHECK (governance.is_v4_hash(used_context_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_contexts_uq
  ON model.frozen_input_contexts (frozen_input_id, team_context_id);

CREATE TABLE model.frozen_input_evidence_bundles (
  frozen_input_evidence_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_bundle_id uuid NOT NULL REFERENCES context.evidence_bundles(evidence_bundle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  used_bundle_hash text NOT NULL CHECK (governance.is_v4_hash(used_bundle_hash)),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_evidence_bundles_uq
  ON model.frozen_input_evidence_bundles (frozen_input_id, evidence_bundle_id);

CREATE TABLE model.frozen_input_model_refs (
  frozen_input_model_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_model_refs_uq
  ON model.frozen_input_model_refs (frozen_input_id, model_version_id);

CREATE TABLE model.frozen_input_engine_refs (
  frozen_input_engine_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frozen_input_id uuid NOT NULL REFERENCES model.frozen_inputs(frozen_input_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_version_id uuid NOT NULL REFERENCES governance.engine_versions(engine_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX frozen_input_engine_refs_uq
  ON model.frozen_input_engine_refs (frozen_input_id, engine_version_id);

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
  CHECK (prediction_cutoff_at < kickoff_at)
);
CREATE UNIQUE INDEX feature_bundles_identity_uq
  ON model.feature_bundles (frozen_input_id, role, generator_version, input_hash);

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
  runtime_ms double precision NOT NULL CHECK (runtime_ms = runtime_ms AND runtime_ms >= 0 AND runtime_ms <> 'Infinity'::double precision AND runtime_ms <> '-Infinity'::double precision),
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
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid AND run_completed_at < kickoff_at))
);

CREATE INDEX engine_runs_lineage_idx
  ON model.engine_runs (frozen_input_id, role, engine_version_id);
CREATE INDEX engine_runs_input_hash_idx
  ON model.engine_runs (input_hash);
CREATE INDEX engine_runs_output_hash_idx
  ON model.engine_runs (output_hash);
CREATE INDEX engine_runs_match_run_idx
  ON model.engine_runs (match_id, role, run_at DESC);

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
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (model_run_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid))
);

CREATE UNIQUE INDEX predictions_logical_uq
  ON model.predictions (match_id, model_version_id, role, stage, prediction_revision);
CREATE INDEX predictions_match_role_idx
  ON model.predictions (match_id, role, model_version_id, stage, prediction_revision DESC);

CREATE TABLE model.prediction_engine_runs (
  prediction_engine_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  engine_run_id uuid NOT NULL REFERENCES model.engine_runs(engine_run_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  market text NOT NULL CHECK (market IN ('spf', 'rqspf', 'total_goals', 'exact_score', 'half_full', 'consensus', 'uncertainty', 'risk')),
  lineage_purpose text NOT NULL CHECK (lineage_purpose IN ('PRIMARY_MARKET', 'CONSENSUS', 'UNCERTAINTY', 'RISK', 'SUPPORTING')),
  output_hash text NOT NULL CHECK (governance.is_v4_hash(output_hash)),
  sequence integer NOT NULL CHECK (sequence > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX prediction_engine_runs_membership_uq
  ON model.prediction_engine_runs (prediction_id, engine_run_id, market, lineage_purpose);
CREATE UNIQUE INDEX prediction_engine_runs_order_uq
  ON model.prediction_engine_runs (prediction_id, sequence);

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
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (frozen_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (NOT future_information_leakage AND NOT run_invalid))
);

CREATE UNIQUE INDEX frozen_predictions_revision_uq
  ON model.frozen_predictions (match_id, role, model_version_id, freeze_revision);
CREATE INDEX frozen_predictions_match_freeze_idx
  ON model.frozen_predictions (match_id, freeze_revision DESC);

-- ============================================================================
-- PHASE 4 - results, reviews, Tier A, promotion, calibration
-- ============================================================================

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX official_results_match_revision_uq
  ON evaluation.official_results (match_id, result_revision);
CREATE UNIQUE INDEX official_results_lineage_revision_uq
  ON evaluation.official_results (result_lineage_id, result_revision);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX postmatch_reviews_revision_uq
  ON evaluation.postmatch_reviews (frozen_prediction_id, review_type, review_revision);
CREATE INDEX postmatch_reviews_frozen_prediction_idx
  ON evaluation.postmatch_reviews (frozen_prediction_id, reviewed_at DESC);

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
  CHECK (prediction_cutoff_at < kickoff_at),
  CHECK (production_run_completed_at < kickoff_at AND shadow_run_completed_at < kickoff_at),
  CHECK (tier_a_eligible = false OR (pair_integrity_passed AND completeness_gate_passed AND pre_kickoff_gate_passed AND NOT future_information_leakage AND qualification_status = 'ELIGIBLE'))
);
CREATE UNIQUE INDEX tier_a_pair_uq
  ON evaluation.tier_a_samples (match_id, production_prediction_id, shadow_prediction_id, shadow_revision);
CREATE INDEX tier_a_shadow_qualified_idx
  ON evaluation.tier_a_samples (shadow_model_version_id, shadow_engine_version_id, shadow_revision, match_id)
  WHERE qualification_status = 'ELIGIBLE';
CREATE INDEX tier_a_frozen_input_hash_idx
  ON evaluation.tier_a_samples (frozen_input_hash, match_id);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX tier_a_run_members_role_prediction_uq
  ON evaluation.tier_a_run_members (tier_a_sample_id, role, prediction_id);
CREATE UNIQUE INDEX tier_a_run_members_order_uq
  ON evaluation.tier_a_run_members (tier_a_sample_id, member_order);

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
  CHECK ((status = 'APPROVED') = (manual_approver IS NOT NULL AND approved_at IS NOT NULL AND production_model_version_id IS NOT NULL))
);
CREATE UNIQUE INDEX promotion_reviews_revision_uq
  ON evaluation.promotion_reviews (candidate_model_version_id, review_revision);

CREATE TABLE evaluation.promotion_review_samples (
  promotion_review_sample_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  promotion_review_id uuid NOT NULL REFERENCES evaluation.promotion_reviews(promotion_review_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  tier_a_sample_id uuid NOT NULL REFERENCES evaluation.tier_a_samples(tier_a_sample_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_hash text NOT NULL CHECK (governance.is_v4_hash(evidence_hash)),
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX promotion_review_samples_uq
  ON evaluation.promotion_review_samples (promotion_review_id, tier_a_sample_id);

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
  CHECK (sample_window_start <= sample_window_end)
);
CREATE UNIQUE INDEX calibration_records_identity_uq
  ON evaluation.calibration_records (model_version_id, role, market, scope_key, confidence_band, sample_window_start, sample_window_end, record_revision);

-- ============================================================================
-- PHASE 5 - release pointers, incidents, and audit
-- ============================================================================

CREATE TABLE governance.release_pointer_events (
  release_pointer_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_family text NOT NULL,
  canonical_output_channel text NOT NULL,
  previous_model_version_id uuid REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  successor_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  action text NOT NULL CHECK (action IN ('ACTIVATE', 'RETIRE', 'ROLLBACK', 'WITHDRAW')),
  reason text NOT NULL,
  actor text NOT NULL,
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
  incident_class text NOT NULL,
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
  CHECK (known_at >= detected_at)
);
CREATE UNIQUE INDEX incidents_revision_uq
  ON governance.incidents (incident_lineage_id, incident_revision);
CREATE INDEX incidents_severity_status_time_idx
  ON governance.incidents (severity, status, created_at DESC);
CREATE INDEX incidents_entity_idx
  ON governance.incidents (affected_entity_type, affected_entity_id, created_at DESC);

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
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX audit_entry_hash_uq ON governance.audit_logs (entry_hash);
CREATE INDEX audit_entity_time_idx ON governance.audit_logs (entity_type, entity_id, happened_at);
CREATE INDEX audit_prev_hash_idx ON governance.audit_logs (prev_hash);

-- ============================================================================
-- PHASE 6 - candidate functions, triggers, RLS, and grants
-- ============================================================================

-- Production uniqueness. The pointer is a controlled cache; the event table
-- remains the append-only activation history.
CREATE UNIQUE INDEX active_production_model_uq
  ON governance.model_versions (model_family, canonical_output_channel)
  WHERE role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active;
CREATE UNIQUE INDEX active_production_engine_uq
  ON governance.engine_versions (engine_name, canonical_output_channel)
  WHERE role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active;

-- Generic strict mutation guard.
CREATE OR REPLACE FUNCTION governance.reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'V4 append-only violation on %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

-- Frozen Input has a narrower pre-freeze path. The reviewed implementation
-- must compare the exact field allow-list and controlled writer context.
CREATE OR REPLACE FUNCTION governance.protect_frozen_input_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- TODO_DECISION: implement the approved Draft-only field allow-list.
  IF OLD.immutable OR OLD.status = 'FROZEN' THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MUTATION is not allowed'
      USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'FROZEN_INPUT_DELETE is not allowed'
      USING ERRCODE = '55000';
  END IF;
  RAISE EXCEPTION 'TODO_DECISION: Frozen Input Draft mutation requires Freeze Gate'
    USING ERRCODE = '55000';
END;
$$;

-- Registry metadata guard. Identity, role, version, hashes, and predecessor
-- identity are immutable. Only the controlled release path may change lifecycle
-- metadata, and that path must append an audit event.
-- TODO_DECISION: implement governance.guard_registry_update() with the exact
-- field allow-list, actor context, predecessor lock, and audit call.

-- Complex function interfaces are intentionally fail-closed stubs here. Their
-- bodies must be implemented and reviewed before any V4-011 migration.
CREATE OR REPLACE FUNCTION governance.guard_registry_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: registry update requires approved actor, field allow-list, and audit event'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_source_separation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate official/external source separation before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_market_payload()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate market availability, payload, price, and line state before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_context_evidence_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate context/evidence match, hash, and as-of cutoff lineage before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_revision_chain()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-family monotonic revision chain before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_frozen_input_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate exact Frozen Input IDs, hashes, cutoff, and source times before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_runtime_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-match role/version/hash runtime lineage before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_prediction_engine_membership()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate prediction/engine membership match, role, and output hash before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_frozen_prediction_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate Prediction/Frozen Input/Frozen Prediction lineage before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_prematch_gate()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: fail closed on source availability, cutoff, kickoff, leakage, and forbidden postmatch refs'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_tier_a_pair()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-match same-frozen-input Production/Shadow pair before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_production_release()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate manual promotion evidence and unique active Production release before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_review_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate review result/frozen-prediction match and input-set separation before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_incident_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate incident entity family, match scope, revision, and secret boundary before apply'
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_public_projection()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate Production-only safe projection and real business timestamps before apply'
    USING ERRCODE = '55000';
END;
$$;

-- No canonical hash computation is included. The future implementation must
-- receive the V4 canonical JSON profile identity, recompute outside this
-- placeholder, and fail closed if the submitted hash does not match.
-- TODO_DECISION: implement the controlled audit append function with a
-- per-stream lock/serializable transaction, actor check, prev_hash check, and
-- caller-supplied canonical entry_hash. It must not hash arbitrary SQL/text.

CREATE TRIGGER model_registry_update_guard
BEFORE UPDATE ON governance.model_versions
FOR EACH ROW EXECUTE FUNCTION governance.guard_registry_update();
CREATE TRIGGER engine_registry_update_guard
BEFORE UPDATE ON governance.engine_versions
FOR EACH ROW EXECUTE FUNCTION governance.guard_registry_update();

CREATE TRIGGER official_source_separation_gate
BEFORE INSERT ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_source_separation();
CREATE TRIGGER official_market_payload_gate
BEFORE INSERT ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_market_payload();
CREATE TRIGGER external_source_separation_gate
BEFORE INSERT ON market.external_market_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_source_separation();
CREATE TRIGGER context_evidence_lineage_gate
BEFORE INSERT ON context.team_context_evidence
FOR EACH ROW EXECUTE FUNCTION governance.validate_context_evidence_lineage();

-- Strict append-only triggers (candidate list; repeat for every listed table).
CREATE TRIGGER official_odds_append_only
BEFORE UPDATE OR DELETE ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER external_market_append_only
BEFORE UPDATE OR DELETE ON market.external_market_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER team_context_append_only
BEFORE UPDATE OR DELETE ON context.team_context_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER team_context_evidence_append_only
BEFORE UPDATE OR DELETE ON context.team_context_evidence
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER evidence_append_only
BEFORE UPDATE OR DELETE ON context.evidence_items
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER evidence_bundle_append_only
BEFORE UPDATE OR DELETE ON context.evidence_bundles
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER evidence_bundle_items_append_only
BEFORE UPDATE OR DELETE ON context.evidence_bundle_items
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER frozen_input_mutation_guard
BEFORE UPDATE OR DELETE ON model.frozen_inputs
FOR EACH ROW EXECUTE FUNCTION governance.protect_frozen_input_mutation();
CREATE TRIGGER feature_bundle_append_only
BEFORE UPDATE OR DELETE ON model.feature_bundles
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER engine_run_append_only
BEFORE UPDATE OR DELETE ON model.engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER prediction_append_only
BEFORE UPDATE OR DELETE ON model.predictions
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER prediction_engine_runs_append_only
BEFORE UPDATE OR DELETE ON model.prediction_engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER prediction_engine_membership_gate
BEFORE INSERT ON model.prediction_engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.validate_prediction_engine_membership();
CREATE TRIGGER frozen_prediction_append_only
BEFORE UPDATE OR DELETE ON model.frozen_predictions
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER frozen_prediction_lineage_gate
BEFORE INSERT ON model.frozen_predictions
FOR EACH ROW EXECUTE FUNCTION governance.validate_frozen_prediction_lineage();
CREATE TRIGGER official_result_append_only
BEFORE UPDATE OR DELETE ON evaluation.official_results
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER review_append_only
BEFORE UPDATE OR DELETE ON evaluation.postmatch_reviews
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER review_scope_gate
BEFORE INSERT ON evaluation.postmatch_reviews
FOR EACH ROW EXECUTE FUNCTION governance.validate_review_scope();
CREATE TRIGGER tier_a_append_only
BEFORE UPDATE OR DELETE ON evaluation.tier_a_samples
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER tier_a_members_append_only
BEFORE UPDATE OR DELETE ON evaluation.tier_a_run_members
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER promotion_review_append_only
BEFORE UPDATE OR DELETE ON evaluation.promotion_reviews
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER promotion_samples_append_only
BEFORE UPDATE OR DELETE ON evaluation.promotion_review_samples
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER calibration_append_only
BEFORE UPDATE OR DELETE ON evaluation.calibration_records
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER release_pointer_append_only
BEFORE UPDATE OR DELETE ON governance.release_pointer_events
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER incident_append_only
BEFORE UPDATE OR DELETE ON governance.incidents
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER incident_scope_gate
BEFORE INSERT ON governance.incidents
FOR EACH ROW EXECUTE FUNCTION governance.validate_incident_scope();
CREATE TRIGGER audit_append_only
BEFORE UPDATE OR DELETE ON governance.audit_logs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();

-- Candidate lineage/time trigger attachments. The fail-closed stubs above are
-- intentionally not usable as a migration implementation.
CREATE CONSTRAINT TRIGGER evidence_revision_gate
AFTER INSERT ON context.evidence_items
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER context_revision_gate
AFTER INSERT ON context.team_context_snapshots
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER bundle_revision_gate
AFTER INSERT ON context.evidence_bundles
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER frozen_input_lineage_gate
AFTER INSERT ON model.frozen_inputs
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_frozen_input_lineage();
CREATE CONSTRAINT TRIGGER runtime_lineage_gate
AFTER INSERT ON model.engine_runs
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_runtime_lineage();
CREATE CONSTRAINT TRIGGER prematch_prediction_gate
AFTER INSERT ON model.predictions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER result_revision_gate
AFTER INSERT ON evaluation.official_results
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER review_revision_gate
AFTER INSERT ON evaluation.postmatch_reviews
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER promotion_revision_gate
AFTER INSERT ON evaluation.promotion_reviews
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER calibration_revision_gate
AFTER INSERT ON evaluation.calibration_records
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER incident_revision_gate
AFTER INSERT ON governance.incidents
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER tier_a_pair_gate
AFTER INSERT ON evaluation.tier_a_samples
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_tier_a_pair();

-- RLS enablement. The future migration repeats this for every candidate table.
ALTER TABLE core.competitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.team_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE market.official_odds_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market.external_market_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.team_context_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.team_context_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_bundle_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_inputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.feature_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.engine_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.prediction_engine_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.official_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.postmatch_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.tier_a_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.tier_a_run_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.promotion_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.promotion_review_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.calibration_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.engine_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.release_pointer_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.audit_logs ENABLE ROW LEVEL SECURITY;

-- Candidate default-deny grants. Custom backend roles are not created here.
REVOKE ALL ON SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;

-- ============================================================================
-- PHASE 7 - public projection ledger and read views
-- ============================================================================

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE TABLE public.public_read_projections (
  projection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  public_odds_snapshot_id uuid REFERENCES market.official_odds_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  competition_name text NOT NULL,
  home_team_name text NOT NULL,
  away_team_name text NOT NULL,
  kickoff_at timestamptz NOT NULL,
  match_status text NOT NULL,
  public_model_name text NOT NULL,
  public_model_version text NOT NULL,
  public_model_revision text NOT NULL,
  safe_odds_summary jsonb NOT NULL CHECK (jsonb_typeof(safe_odds_summary) = 'object'),
  safe_selection_summary jsonb NOT NULL CHECK (jsonb_typeof(safe_selection_summary) = 'object'),
  safe_result_summary jsonb,
  prediction_business_at timestamptz NOT NULL,
  frozen_business_at timestamptz NOT NULL,
  odds_business_at timestamptz NOT NULL,
  context_business_at timestamptz NOT NULL,
  result_business_at timestamptz,
  review_business_at timestamptz,
  projection_revision integer NOT NULL CHECK (projection_revision > 0),
  projection_hash text NOT NULL CHECK (governance.is_v4_hash(projection_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  publication_status text NOT NULL CHECK (publication_status IN ('PUBLISHED', 'WITHDRAWN', 'BLOCKED')),
  published_at timestamptz,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE UNIQUE INDEX public_projection_revision_uq
  ON public.public_read_projections (match_id, production_frozen_prediction_id, projection_revision);

ALTER TABLE public.public_read_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_read_projections FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.public_read_projections FROM PUBLIC, anon, authenticated;

CREATE POLICY public_projection_published_read
ON public.public_read_projections
FOR SELECT TO anon, authenticated
USING (publication_status = 'PUBLISHED');

GRANT SELECT (
  match_id,
  competition_name,
  home_team_name,
  away_team_name,
  kickoff_at,
  match_status,
  public_model_name,
  public_model_version,
  public_model_revision,
  safe_odds_summary,
  safe_selection_summary,
  safe_result_summary,
  prediction_business_at,
  frozen_business_at,
  odds_business_at,
  context_business_at,
  result_business_at,
  review_business_at,
  projection_revision,
  publication_status,
  created_at
)
ON public.public_read_projections TO anon, authenticated;

-- TODO_DECISION: verify deployed PostgreSQL security_invoker support before
-- exposure. These are candidate views and must be created only after the
-- projection validator and safe-column grants are approved.
CREATE OR REPLACE VIEW public.v_public_predictions
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id,
    p.competition_name,
    p.home_team_name,
    p.away_team_name,
    p.kickoff_at,
    p.match_status,
    p.public_model_name,
    p.public_model_version,
    p.public_model_revision,
    p.safe_odds_summary,
    p.safe_selection_summary,
    p.safe_result_summary,
    p.prediction_business_at,
    p.frozen_business_at,
    p.odds_business_at,
    p.context_business_at,
    p.result_business_at,
    p.review_business_at,
    p.projection_revision,
    p.publication_status,
    p.created_at,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.projection_revision DESC, p.created_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT
  r.match_id,
  r.competition_name,
  r.home_team_name,
  r.away_team_name,
  r.kickoff_at,
  r.match_status,
  r.safe_selection_summary,
  r.safe_odds_summary,
  r.frozen_business_at AS frozen_at,
  GREATEST(
    r.prediction_business_at,
    r.frozen_business_at,
    r.odds_business_at,
    r.context_business_at,
    COALESCE(r.result_business_at, '-infinity'::timestamptz),
    COALESCE(r.review_business_at, '-infinity'::timestamptz)
  ) AS canonical_latest_update_at
FROM ranked AS r
WHERE r.rn = 1;

CREATE OR REPLACE VIEW public.v_public_latest_odds
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id,
    p.kickoff_at,
    p.safe_odds_summary,
    p.odds_business_at,
    p.publication_status,
    p.projection_revision,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.odds_business_at DESC, p.projection_revision DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT match_id, kickoff_at, safe_odds_summary, odds_business_at, publication_status
FROM ranked
WHERE rn = 1;

CREATE OR REPLACE VIEW public.v_current_frozen_predictions
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id,
    p.kickoff_at,
    p.safe_selection_summary,
    p.prediction_business_at,
    p.frozen_business_at,
    p.projection_revision,
    p.publication_status,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.projection_revision DESC, p.frozen_business_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT
  match_id,
  kickoff_at,
  safe_selection_summary,
  frozen_business_at AS frozen_at,
  prediction_business_at,
  frozen_business_at,
  projection_revision
FROM ranked
WHERE rn = 1;

CREATE OR REPLACE VIEW public.v_canonical_latest_update
WITH (security_invoker = true)
AS
WITH business_updates AS (
  SELECT
    p.match_id,
    GREATEST(
      p.prediction_business_at,
      p.frozen_business_at,
      p.odds_business_at,
      p.context_business_at,
      COALESCE(p.result_business_at, '-infinity'::timestamptz),
      COALESCE(p.review_business_at, '-infinity'::timestamptz)
    ) AS business_update_at
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT match_id, MAX(business_update_at) AS canonical_latest_update_at
FROM business_updates
GROUP BY match_id;

-- Internal/approved-only views. No anon grant is implied.
CREATE OR REPLACE VIEW public.v_tier_a_progress
WITH (security_invoker = true)
AS
SELECT
  count(*) FILTER (WHERE qualification_status = 'ELIGIBLE') AS eligible_sample_count,
  count(*) FILTER (WHERE qualification_status = 'REJECTED') AS rejected_sample_count,
  count(*) FILTER (WHERE qualification_status = 'BLOCKED') AS blocked_sample_count,
  MAX(sample_no) FILTER (WHERE qualification_status = 'ELIGIBLE') AS last_eligible_sample_no,
  MAX(created_at) AS as_of_business_at
FROM evaluation.tier_a_samples;

CREATE OR REPLACE VIEW public.v_model_registry_public
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.public_model_name,
    p.public_model_version,
    p.public_model_revision,
    p.projection_revision,
    p.frozen_business_at,
    p.publication_status,
    p.created_at,
    row_number() OVER (
      PARTITION BY p.public_model_name, p.public_model_version
      ORDER BY p.projection_revision DESC, p.created_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT
  public_model_name,
  public_model_version,
  public_model_revision,
  publication_status,
  frozen_business_at AS effective_at
FROM ranked
WHERE rn = 1;

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON public.v_public_predictions,
               public.v_public_latest_odds,
               public.v_current_frozen_predictions,
               public.v_canonical_latest_update
  TO anon, authenticated;
-- v_tier_a_progress and v_model_registry_public require a separate
-- public-safe column review; do not grant them automatically.

-- Candidate latest-update expression index. It uses business timestamps only.
CREATE INDEX public_projection_business_latest_idx
ON public.public_read_projections
(
  GREATEST(
    prediction_business_at,
    frozen_business_at,
    odds_business_at,
    context_business_at,
    COALESCE(result_business_at, '-infinity'::timestamptz),
    COALESCE(review_business_at, '-infinity'::timestamptz)
  ) DESC,
  match_id
)
WHERE publication_status = 'PUBLISHED';

-- End of blueprint. No statement above is authorized for execution by V4-010.
