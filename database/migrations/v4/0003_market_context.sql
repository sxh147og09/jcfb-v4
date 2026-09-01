-- DESIGN ONLY - DO NOT APPLY
-- migration_id: migration@20260901.003
-- sequence: 0003
-- name: v4-market-context
-- migration_version: migration@20260901.003
-- depends_on: [migration@20260901.002]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- Candidate source/evidence DDL only; do not execute or load market data.

BEGIN;

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

CREATE TABLE context.team_context_evidence (
  team_context_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_context_id uuid NOT NULL REFERENCES context.team_context_snapshots(team_context_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_id uuid NOT NULL REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  source_role text NOT NULL CHECK (source_role IN ('PRIMARY', 'SUPPORTING', 'CONFLICTING')),
  used_evidence_hash text NOT NULL CHECK (governance.is_v4_hash(used_evidence_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (team_context_id, evidence_id)
);

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
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, bundle_revision)
);

CREATE TABLE context.evidence_bundle_items (
  evidence_bundle_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_bundle_id uuid NOT NULL REFERENCES context.evidence_bundles(evidence_bundle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  evidence_id uuid NOT NULL REFERENCES context.evidence_items(evidence_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  item_order integer NOT NULL CHECK (item_order > 0),
  inclusion_role text NOT NULL CHECK (inclusion_role IN ('REQUIRED', 'SUPPORTING', 'REJECTED')),
  used_evidence_hash text NOT NULL CHECK (governance.is_v4_hash(used_evidence_hash)),
  availability_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (evidence_bundle_id, evidence_id),
  UNIQUE (evidence_bundle_id, item_order)
);

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
  UNIQUE (match_id, source, snapshot_kind, captured_at, snapshot_hash),
  CHECK (payload_hash = snapshot_hash),
  CHECK ((availability_time_state = 'KNOWN') = (availability_at IS NOT NULL))
);

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
  UNIQUE (match_id, provider, market, normalized_line, captured_at, snapshot_hash),
  CHECK ((market = 'EUROPEAN_1X2') = (line_value IS NULL AND normalized_line = 'NOT_APPLICABLE')),
  CHECK (market <> 'EUROPEAN_1X2' OR line_value IS NOT NULL),
  CHECK ((availability_time_state = 'KNOWN') = (availability_at IS NOT NULL))
);

CREATE INDEX evidence_match_published_idx ON context.evidence_items (match_id, published_at DESC) WHERE match_id IS NOT NULL;
CREATE INDEX evidence_team_published_idx ON context.evidence_items (team_id, published_at DESC) WHERE team_id IS NOT NULL;
CREATE INDEX context_match_asof_idx ON context.team_context_snapshots (match_id, team_id, as_of_at DESC);
CREATE INDEX context_evidence_evidence_idx ON context.team_context_evidence (evidence_id, team_context_id);
CREATE INDEX evidence_bundle_match_cutoff_idx ON context.evidence_bundles (match_id, prediction_cutoff_at DESC);
CREATE INDEX evidence_bundle_items_evidence_idx ON context.evidence_bundle_items (evidence_id, evidence_bundle_id);
CREATE INDEX official_odds_match_captured_idx ON market.official_odds_snapshots (match_id, captured_at DESC);
CREATE INDEX official_odds_snapshot_hash_idx ON market.official_odds_snapshots (snapshot_hash);
CREATE INDEX external_market_match_captured_idx ON market.external_market_snapshots (match_id, captured_at DESC);
CREATE INDEX external_snapshot_hash_idx ON market.external_market_snapshots (snapshot_hash);

COMMIT;
