# JCFB V4 Table Catalog 1.0

Status: V4-010 TABLE AND COLUMN BLUEPRINT (DESIGN-ONLY)

This catalog is the physical companion to `V4_DATABASE_SCHEMA_BLUEPRINT.md`. All tables below are candidates only. No table is created by this task. `uuid` defaults use `gen_random_uuid()` as a portable placeholder; UUIDv7 is preferred when the target Supabase/PostgreSQL version and extension are approved in Phase 0.

## 1. Common column vocabulary

The following fields are repeated where applicable. The named entity ID is the `object_id` for that row.

| Field | PostgreSQL type | NULL/default | Rule |
|---|---|---|---|
| entity ID | `uuid` | `NOT NULL DEFAULT gen_random_uuid()` | Stable PK; UUID/UUIDv7 contract identity, never a display key. |
| `contract_version` | `text` | `NOT NULL` | Qualified contract such as `prediction@1.0.0`; format and registry validation required. |
| `schema_version` | `text` | `NOT NULL` where the record shape is versioned | Qualified persisted shape identity; not a model or migration identity. |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | Insertion time only; never source availability, kickoff, prediction, or page time. |
| `updated_at` | `timestamptz` | registry tables only, `NOT NULL DEFAULT now()` | Controlled metadata pointer/status update; never used on immutable history. |
| `source` | `text` | required on source-bound rows | Attributable authority/provider; `UNKNOWN` blocks formal use. |
| `source_type` | `text` | required when source is present | Exact V4 source enum spelling. |
| `source_reference` | `text` | required on source-bound rows | Replayable reference; secrets are forbidden. |
| `source_timestamp` | `timestamptz` | nullable only with explicit time state | Time asserted by source; NULL is not an implicit UNKNOWN. |
| `observed_at` | `timestamptz` | required on source observations | Time V4 observed/captured the source. |
| `ingested_at` | `timestamptz` | required on persisted intake | System acceptance time; never a substitute for availability. |
| `availability_at` | `timestamptz` | nullable only when state is UNKNOWN/BLOCKED | Source-semantic availability time selected by policy. |
| `availability_time_state` | `text` | `NOT NULL` | `KNOWN`, `UNKNOWN`, or `BLOCKED`; known requires `availability_at`. |
| `availability_time_basis` | `text` | nullable when unknown | `SOURCE_TIMESTAMP`, `PUBLISHED_AT`, `OBSERVED_AT`, or `UNKNOWN`. |
| `status` | `text` | `NOT NULL` | Table-specific governed state with explicit `CHECK`; no silent default. |
| `metadata` | `jsonb` | `NOT NULL DEFAULT '{}'::jsonb` | Non-authoritative extension/trace data only; must be an object. |
| hash fields | `text` | required when named by the contract | `sha256:<64 lowercase hex>`; `hash_algorithm` and `hash_profile` are stored with key hashes. Relation-only `used_*_hash` fields inherit the referenced envelope's metadata. |

All `metadata` and variable `payload` columns have `CHECK (jsonb_typeof(...) = 'object')` unless the contract explicitly requires an array. Core FKs and business keys never live only inside JSONB.

## 2. Governance registries

### 2.1 `governance.model_versions`

Registry identity is immutable. Only controlled lifecycle/pointer metadata may be updated through the approved release function, with an audit event.

| Field | Type | NULL/default | PK/FK/check/meaning |
|---|---|---|---|
| `model_version_id` | `uuid` | `NOT NULL DEFAULT gen_random_uuid()` | PK. |
| `model_family` | `text` | NOT NULL | Stable family key; non-empty. |
| `model_name` | `text` | NOT NULL | Qualified model name; non-empty. |
| `model_version` | `text` | NOT NULL | SemVer text; exact version identity. |
| `major`, `minor`, `patch` | `integer` | NOT NULL | Non-negative and must agree with `model_version`. |
| `revision` | `text` | NOT NULL | Immutable registry revision; never reused. |
| `jcfb_version` | `text` | NOT NULL | Qualified product version. |
| `role` | `text` | NOT NULL | `PRODUCTION`, `SHADOW`, or `EXPERIMENT`; immutable. |
| `canonical_output_channel` | `text` | NOT NULL | Production uniqueness scope; non-empty. |
| `implementation_hash` | `text` | NOT NULL | V4 hash format. |
| `config_version` | `text` | NOT NULL | Qualified non-secret config identity. |
| `config_hash` | `text` | NOT NULL | V4 hash format; no config secret. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | `SHA-256` and `v4-canonical-json@1.0`; computation remains outside this blueprint. |
| `schema_version` | `text` | NOT NULL | Registry/output schema identity. |
| `dataset_version` | `text` | NOT NULL | Exact accepted dataset identity. |
| `migration_version` | `text` | NOT NULL | Storage identity used by the release. |
| `compatibility_level` | `text` | NOT NULL | `PATCH_COMPATIBLE`, `MINOR_COMPATIBLE`, or `MAJOR_BREAKING`, per the V4-006 identity contract. |
| `status` | `text` | NOT NULL | `DRAFT`, `EXPERIMENT`, `SHADOW`, `PROMOTION_REVIEW`, `PRODUCTION`, `RETIRED`, `BLOCKED`. |
| `is_canonical_active` | `boolean` | `NOT NULL DEFAULT false` | Pointer cache; true only for active Production. Partial unique index enforces one per family/channel. |
| `effective_at` | `timestamptz` | nullable | Required for activation; must precede retirement. |
| `retired_at` | `timestamptz` | nullable | Required for `RETIRED`; after effective time. |
| `supersedes_model_version_id` | `uuid` | nullable | Self-FK; same family and earlier revision; root is NULL/`NOT_APPLICABLE` by metadata. |
| `approval_reference` | `text` | nullable | Required for Production; no secret. |
| `approved_at` | `timestamptz` | nullable | Required for Production. |
| `retirement_reason` | `text` | nullable | Required for retirement. |
| `created_at`, `updated_at` | `timestamptz` | defaults above | `updated_at` only controlled lifecycle metadata. |
| `metadata` | `jsonb` | `{}` | Non-authoritative registry annotations. |

Unique: `(model_family, model_name, model_version, role, revision)`. Checks: SemVer components agree; active implies `role=PRODUCTION`, `status=PRODUCTION`, `effective_at IS NOT NULL`; `retired_at` is after `effective_at`; all hashes have the V4 format.

### 2.2 `governance.engine_versions`

| Field | Type | NULL/default | PK/FK/check/meaning |
|---|---|---|---|
| `engine_version_id` | `uuid` | `NOT NULL DEFAULT gen_random_uuid()` | PK. |
| `model_version_id` | `uuid` | NOT NULL | FK to `governance.model_versions`. Registry role/family agreement is trigger-checked. |
| `model_family` | `text` | NOT NULL | Denormalized lookup key; must match model registry. |
| `engine_name` | `text` | NOT NULL | Exact independent engine name. |
| `engine_version` | `text` | NOT NULL | Qualified SemVer identity. |
| `major`, `minor`, `patch` | `integer` | NOT NULL | Non-negative and agree with `engine_version`. |
| `revision` | `text` | NOT NULL | Immutable role-scoped engine revision. |
| `jcfb_version` | `text` | NOT NULL | Qualified product version. |
| `role` | `text` | NOT NULL | `PRODUCTION`, `SHADOW`, or `EXPERIMENT`; immutable. |
| `canonical_output_channel` | `text` | NOT NULL | Engine activation scope. |
| `implementation_hash` | `text` | NOT NULL | V4 hash format. |
| `config_version`, `config_hash` | `text` | NOT NULL | Non-secret config identity and hash. |
| `schema_version`, `dataset_version`, `migration_version` | `text` | NOT NULL | Exact schema/data/storage identities. |
| `compatibility_level` | `text` | NOT NULL | `PATCH_COMPATIBLE`, `MINOR_COMPATIBLE`, or `MAJOR_BREAKING`; must agree with the model registry contract. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | `SHA-256` and `v4-canonical-json@1.0`; no hash computation is implied by the field. |
| `status` | `text` | NOT NULL | Governed lifecycle state. |
| `is_canonical_active` | `boolean` | `NOT NULL DEFAULT false` | Active Production pointer cache; controlled only. |
| `effective_at`, `retired_at` | `timestamptz` | nullable | Lifecycle times; retirement is append-only evidence. |
| `supersedes_engine_version_id` | `uuid` | nullable | Self-FK predecessor; same engine family and earlier revision. |
| `approval_reference`, `approved_at`, `retirement_reason` | `text`, `timestamptz`, `text` | nullable | Gate evidence; no secret. |
| `created_at`, `updated_at`, `metadata` | common | defaults above | Registry timestamp/metadata policy. |

Unique: `(engine_name, engine_version, role, revision)`. Checks: role/status, model role agreement, active Production predicate, and hash format.

### 2.3 `governance.release_pointer_events` (supporting table)

Append-only activation, retirement, and rollback pointer history.

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `release_pointer_event_id` | `uuid` | PK/default | Stable event identity. |
| `model_family`, `canonical_output_channel` | `text` | NOT NULL | Pointer scope. |
| `previous_model_version_id` | `uuid` | nullable | Prior active identity; NULL only at first activation. |
| `successor_model_version_id` | `uuid` | NOT NULL | New Production identity. |
| `action` | `text` | NOT NULL | `ACTIVATE`, `RETIRE`, `ROLLBACK`, or `WITHDRAW`. |
| `reason`, `actor` | `text` | NOT NULL | Human/governed reason and actor identity. |
| `effective_at`, `created_at` | `timestamptz` | NOT NULL/default | Business activation and insertion times. |
| `evidence` | `jsonb` | NOT NULL | Gate evidence object; no secrets. |
| `event_hash`, `prev_hash` | `text` | NOT NULL/nullable | Hash-chain/event identity; format checked. |

FKs to both model versions; same-family/role and exactly-one-active transition are trigger-checked.

## 3. Canonical core

### 3.1 `core.competitions`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `competition_id` | `uuid` | PK/default | Stable identity. |
| `competition_key` | `text` | NOT NULL | Stable source-scoped business key. |
| `governing_source` | `text` | NOT NULL | Authority namespace. |
| `display_name`, `normalized_name` | `text` | NOT NULL | Labels; normalized value is not a global identity. |
| `timezone` | `text` | NOT NULL | IANA timezone policy. |
| `identity_resolution_state` | `text` | NOT NULL | `RESOLVED`, `REQUIRES_REVIEW`, `BLOCKED`, or `UNKNOWN`. |
| `revision` | `integer` | `NOT NULL DEFAULT 1` | Non-negative chain revision. |
| `source`, `source_type`, `source_reference` | common | required | Attributable source lineage. |
| `source_timestamp`, `observed_at`, `ingested_at` | common | required/nullable per time state | Source and observation ordering. |
| `provenance_hash`, `payload_hash`, `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonical hash metadata. |
| `contract_version`, `schema_version`, `status`, `created_at`, `metadata` | common | required/default | Append-only fact policy; no mutable `updated_at`. |

Unique: `(governing_source, competition_key)`. Status check allows `ACTIVE`, `BLOCKED`, `RETIRED`, `UNKNOWN`.

### 3.2 `core.teams`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `team_id` | `uuid` | PK/default | Stable canonical team identity. |
| `canonical_team_key` | `text` | NOT NULL | Source-independent canonical key after identity resolution. |
| `source_namespace` | `text` | NOT NULL | Namespace used to validate the key. |
| `canonical_name`, `normalized_name` | `text` | NOT NULL | Display labels; never primary identity. |
| `identity_resolution_state` | `text` | NOT NULL | `RESOLVED`, `REQUIRES_REVIEW`, `BLOCKED`, `UNKNOWN`. |
| `revision` | `integer` | `NOT NULL DEFAULT 1` | Canonical fact revision. |
| source/time/hash/common fields | common | required as applicable | Attributable identity evidence. |

Unique: `(source_namespace, canonical_team_key)`. Home/away references always use `team_id`.

### 3.3 `core.team_aliases`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `team_alias_id` | `uuid` | PK/default | Stable alias row. |
| `team_id` | `uuid` | NOT NULL | FK to `core.teams`. |
| `alias_text`, `normalized_alias` | `text` | NOT NULL | Non-empty source/locale-scoped labels. |
| `locale`, `source_scope` | `text` | NOT NULL | Alias resolution scope. |
| `valid_from`, `valid_to` | `timestamptz` | `valid_from` required; end nullable | If both set, `valid_to > valid_from`. |
| `verification_state` | `text` | NOT NULL | `VERIFIED`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`, `REJECTED`. |
| source/time/hash/common fields | common | required as applicable | Alias evidence; append-only correction path. |

Unique: `(team_id, normalized_alias, locale, source_scope, valid_from)`.

### 3.4 `core.matches`

| Field | Type | NULL/default | PK/FK/check/meaning |
|---|---|---|---|
| `match_id` | `uuid` | PK/default | Permanent cross-contract match identity. |
| `data_date` | `date` | NOT NULL | Official lottery data day. |
| `official_match_no` | `text` | NOT NULL | Preserve leading zeros; digits only. |
| `match_identity_key` | `text` | NOT NULL | Must equal `YYYY-MM-DD:official_match_no`. |
| `competition_id` | `uuid` | NOT NULL | FK to `core.competitions`. |
| `home_team_id`, `away_team_id` | `uuid` | NOT NULL | FKs to `core.teams`; must differ. |
| `kickoff_at` | `timestamptz` | NOT NULL | Canonical scheduled kickoff. |
| `timezone` | `text` | NOT NULL | Interpretation timezone for data date/cutoff. |
| `match_status` | `text` | NOT NULL | V4 match enum, including `IN_PROGRESS`, `FINISHED`, `BLOCKED`. |
| `intake_status` | `text` | NOT NULL | `OPEN`, `CLOSED`, or `NOT_APPLICABLE`; separate from match status. |
| `identity_resolution_state` | `text` | NOT NULL | `RESOLVED`, `REQUIRES_REVIEW`, `BLOCKED`, `UNKNOWN`. |
| `canonical_facts_hash` | `text` | NOT NULL | V4 hash format. |
| `revision` | `integer` | `NOT NULL DEFAULT 1` | Canonical identity revision; correction history is append-only. |
| source/time/hash/common fields | common | required as applicable | Source authority and audit. |

Unique: `(data_date, official_match_no)`. Checks: official number is non-empty digits; identity key is derived-equivalent; `home_team_id <> away_team_id`; `data_date` interpretation and timezone are validated. Once downstream-used, identity fields are immutable; an approved match identity revision/history relation is required for correction rather than in-place mutation.

## 4. Market source snapshots

### 4.1 `market.official_odds_snapshots`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `snapshot_id` | `uuid` | PK/default | Official snapshot identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`. |
| `snapshot_kind` | `text` | NOT NULL | `OPENING`, `INTERMEDIATE`, `CURRENT`, `LATEST`, `FINAL`, `CORRECTION`. |
| `captured_at` | `timestamptz` | NOT NULL | Capture/screenshot time. |
| `source_timestamp`, `observed_at`, `ingested_at` | `timestamptz` | NOT NULL/required | Distinct source and system times. |
| `availability_at`, `availability_time_state`, `availability_time_basis` | common | required | Time gate input. |
| `source_is_official` | `boolean` | `NOT NULL DEFAULT true` | CHECK must be true. |
| `source`, `source_type`, `source_reference` | common | NOT NULL | Official authority; screenshot may require evidence FK. |
| `evidence_ref` | `uuid` | nullable | FK to `context.evidence_items`; required for official screenshot extraction. |
| `supersedes_snapshot_id` | `uuid` | nullable | Self-FK correction predecessor; correction is a new immutable snapshot. |
| `market_availability` | `jsonb` | NOT NULL | Object for exactly five market keys and explicit states. |
| `market_unavailable_reason` | `jsonb` | NOT NULL | Reason per unavailable market; `NOT_APPLICABLE` for available market. |
| `spf`, `rqspf`, `total_goals`, `exact_score`, `half_full` | `jsonb` | conditional | Payload only when market is available; no empty-object substitute. |
| `snapshot_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | `payload_hash = snapshot_hash` for this contract; format checked. |
| `hash_algorithm`, `hash_profile` | `text` | default/NOT NULL | `SHA-256`, `v4-canonical-json@1.0`. |
| `status` | `text` | NOT NULL | Availability/gate state; invalid/future rows remain stored. |
| `contract_version`, `schema_version`, `created_at`, `metadata` | common | required/default | Append-only; no `updated_at`. |

Unique dedup key: `(match_id, source, snapshot_kind, captured_at, snapshot_hash)`. A trigger validates five-market availability/payload alignment, official source, and `availability_at <= captured_at` where policy requires.

### 4.2 `market.external_market_snapshots`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `snapshot_id` | `uuid` | PK/default | External snapshot identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`. |
| `provider` | `text` | NOT NULL | Named non-official provider. |
| `market` | `text` | NOT NULL | `EUROPEAN_1X2`, `ASIAN_HANDICAP`, `OVER_UNDER`. |
| `line_value` | `numeric(8,3)` | nullable | Required for line markets; NULL only for 1X2. |
| `normalized_line` | `text` | NOT NULL | Stable dedup value; `NOT_APPLICABLE` for 1X2. |
| `prices` | `jsonb` | NOT NULL | Provider labels/prices; object, never official payload. |
| `captured_at`, `source_timestamp`, `observed_at`, `ingested_at` | `timestamptz` | required as applicable | External chronology. |
| `availability_at`, `availability_time_state`, `availability_time_basis` | common | required | No-future gate input. |
| `liquidity_quality` | `text` | NOT NULL | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` or governed provider state. |
| `source_is_official` | `boolean` | `NOT NULL DEFAULT false` | CHECK must be false. |
| `source`, `source_type`, `source_reference`, hashes/common fields | common | required | External provenance and append-only policy. |
| `supersedes_snapshot_id` | `uuid` | nullable | Self-FK correction predecessor; it cannot convert external data to official data. |

Unique dedup key: `(match_id, provider, market, normalized_line, captured_at, snapshot_hash)`. A trigger rejects any official-source coercion.

## 5. Context and evidence

### 5.1 `context.team_context_snapshots`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `team_context_id` | `uuid` | PK/default | Stable context identity. |
| `match_id`, `team_id` | `uuid` | NOT NULL | FKs to `core.matches` and `core.teams`; match/team/side agreement trigger. |
| `side` | `text` | NOT NULL | `HOME` or `AWAY`; must match the canonical match. |
| `as_of_at` | `timestamptz` | NOT NULL | Context validity boundary. |
| `injuries`, `suspensions`, `starting_xi` | `jsonb` | NOT NULL | Fact collections with explicit state; empty arrays do not mean UNKNOWN. |
| `lineup_status`, `coach`, `tactical_style`, `motivation`, `schedule_pressure`, `fatigue`, `travel`, `weather`, `pitch` | `jsonb` | NOT NULL | Context values with state/source semantics. |
| `source_summary`, `conflicts` | `jsonb` | NOT NULL | Source refs and contradiction state. |
| `context_confidence` | `jsonb` | NOT NULL | Provenance/completeness confidence, not probability. |
| `source`, `source_type`, `source_reference`, time fields | common | required | Source/availability lineage. |
| `context_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | V4 hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| `revision` | `integer` | `NOT NULL DEFAULT 1` | Context correction revision. |
| `supersedes_team_context_id` | `uuid` | nullable | Self-FK predecessor; same match/team/side and earlier revision. |
| `status` | `text` | NOT NULL | `AVAILABLE`, `UNKNOWN`, `BLOCKED`, `STALE`, `CONFLICT`. |
| contract/schema/created/metadata | common | required/default | Formal snapshots append-only. |

Unique: `(match_id, team_id, side, revision)`; optional exact dedup `(match_id, team_id, side, as_of_at, context_hash)`.

### 5.2 `context.evidence_items`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `evidence_id` | `uuid` | PK/default | Stable evidence identity. |
| `match_id`, `team_id` | `uuid` | nullable | Typed optional scope FKs; at least one typed/entity scope is required by trigger. |
| `claim_type` | `text` | NOT NULL | Governed category such as `INJURY_STATUS`, `LINEUP_STATUS`, `ODDS_OBSERVATION`, `MATCH_IDENTITY`, `RESULT`. |
| `claim` | `jsonb` | NOT NULL | Atomic observation/claim object; not a free-form interpretation. |
| `entity_refs` | `jsonb` | NOT NULL | Non-empty typed reference array; generic player refs are validated by contract. |
| `source`, `source_type`, `source_reference` | common | NOT NULL | Attributable evidence source. |
| `published_at`, `valid_from`, `expires_at` | `timestamptz` | nullable with explicit state | Source validity; unknown time uses explicit state/reason. |
| `published_time_state`, `valid_from_time_state` | `text` | NOT NULL | `KNOWN`, `UNKNOWN`, or `BLOCKED`; `KNOWN` requires the corresponding timestamp. |
| `time_reason` | `text` | conditional | Required when publication or validity time is unknown/blocked. |
| `retrieved_at` | `timestamptz` | NOT NULL | System retrieval time. |
| `confidence` | `jsonb` | NOT NULL | Evidence confidence object, not prediction probability. |
| `verification_state` | `text` | NOT NULL | `VERIFIED`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`, `REJECTED`. |
| `contradiction_state` | `text` | NOT NULL | `NONE`, `PENDING`, `CONFLICTED`, `RESOLVED`, `NOT_APPLICABLE`. |
| `evidence_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | V4 hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata; recomputation is outside this blueprint. |
| `revision` | `integer` | `NOT NULL DEFAULT 1` | Correction revision. |
| `supersedes_evidence_id` | `uuid` | nullable | Self-FK predecessor. |
| `status`, contract/schema/created/metadata | common | required/default | Append-only even when rejected/conflicted. |

### 5.3 `context.evidence_bundles`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `evidence_bundle_id` | `uuid` | PK/default | Stable cutoff-scoped bundle identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`. |
| `prediction_cutoff_at` | `timestamptz` | NOT NULL | Last eligible evidence boundary. |
| `bundle_revision` | `integer` | NOT NULL | Unique per match. |
| `inclusion_state`, `gate_status` | `text` | NOT NULL | Explicit selection and validation states. |
| `bundle_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | V4 hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| source/time/common fields | common | required | Bundle provenance and creation. |

Unique: `(match_id, bundle_revision)`.

### 5.4 `context.team_context_evidence`

This supporting table normalizes context-to-evidence references so source lineage is not hidden in `source_summary` JSONB.

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `team_context_evidence_id` | `uuid` | PK/default | Stable membership identity. |
| `team_context_id`, `evidence_id` | `uuid` | NOT NULL | FKs to `context.team_context_snapshots` and `context.evidence_items`; same match is trigger-checked. |
| `source_role` | `text` | NOT NULL | `PRIMARY`, `SUPPORTING`, or `CONFLICTING`. |
| `used_evidence_hash` | `text` | NOT NULL | Must equal the referenced evidence hash. |
| `availability_at` | `timestamptz` | NOT NULL | Must be no later than the context `as_of_at` and any downstream cutoff. |
| `created_at`, `metadata` | common | default/required | Membership is append-only. |

Unique: `(team_context_id, evidence_id)`.

### 5.5 `context.evidence_bundle_items`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `evidence_bundle_item_id` | `uuid` | PK/default | Stable membership identity. |
| `evidence_bundle_id`, `evidence_id` | `uuid` | NOT NULL | FKs to bundle/item. |
| `item_order` | `integer` | NOT NULL | Positive stable order. |
| `inclusion_role` | `text` | NOT NULL | `REQUIRED`, `SUPPORTING`, `REJECTED`, or governed state. |
| `used_evidence_hash` | `text` | NOT NULL | Must equal referenced item hash. |
| `availability_at` | `timestamptz` | NOT NULL | Must be <= bundle cutoff. |
| `created_at`, `metadata` | common | default/required | Membership append-only. |

Unique: `(evidence_bundle_id, evidence_id)` and `(evidence_bundle_id, item_order)`.

## 6. Model lineage and runtime

### 6.1 `model.frozen_inputs`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `frozen_input_id` | `uuid` | PK/default | Immutable lineage identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`. |
| `revision` | `integer` | NOT NULL | Unique `(match_id, revision)`; monotonic. |
| `frozen_input_revision` | `text` | NOT NULL | `fi-YYYYMMDD-NNNNNN` identity alias; never reused. |
| `canonical_match_hash` | `text` | NOT NULL | Exact match identity hash used. |
| `feature_schema_version` | `text` | NOT NULL | Qualified feature shape identity. |
| `dataset_version`, `schema_version`, `migration_version` | `text` | NOT NULL | Dataset/persisted shape/storage identities. |
| `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | Cutoff must precede kickoff. |
| `owner_role` | `text` | NOT NULL | `PRODUCTION` for shared Production/Shadow input or `EXPERIMENT` for research-only input. Not part of substantive hash. |
| `comparison_mode` | `text` | NOT NULL | `FORWARD_AB`, `EXPERIMENT_ONLY`, or `NOT_APPLICABLE`. |
| `ab_comparison_group_id` | `uuid` | conditional | Required for `FORWARD_AB`; shared by pair. |
| `frozen_at` | `timestamptz` | conditional | Required when status is `FROZEN`; must precede kickoff. |
| `immutable` | `boolean` | `NOT NULL DEFAULT false` | Must be true after formation/FROZEN. |
| `future_information_leakage`, `run_invalid`, `tier_a_eligible` | `boolean` | false defaults | Gate flags; eligibility cannot be manually raised without gate validation. |
| `status` | `text` | NOT NULL | `DRAFT`, `VALIDATED`, `FROZEN`, `SUPERSEDED`, `BLOCKED`, `REJECTED`. |
| `frozen_input_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL when validated/frozen | Exact canonical hashes. |
| `hash_algorithm`, `hash_profile` | `text` | default/NOT NULL | `SHA-256`, V4 canonical profile. |
| `supersedes_frozen_input_id` | `uuid` | nullable | Self-FK prior input; same match and earlier revision. |
| `gate_reason`, `source_summary` | `text`, `jsonb` | gate reason conditional; summary required | Gate evidence; normalized selected references are in child tables below. |
| contract/schema/created/metadata | common | required/default | Update allowed only in controlled DRAFT state. |

Normalized child tables (all append-only) carry exact FKs and used hashes: `model.frozen_input_official_odds`, `model.frozen_input_external_markets`, `model.frozen_input_contexts`, `model.frozen_input_evidence_bundles`, `model.frozen_input_model_refs`, and `model.frozen_input_engine_refs`. Unique: `(match_id, revision)`; non-unique hash index on `frozen_input_hash`.

### 6.2 Frozen Input selection child tables

Each child has a UUID membership PK, parent FK, referenced object FK, copied `used_*_hash`, `availability_at`, `created_at`, and metadata. The parent and child `match_id` are trigger-checked. Exact tables:

| Table | Referenced FK | Required uniqueness/check |
|---|---|---|
| `model.frozen_input_official_odds` | `market.official_odds_snapshots(snapshot_id)` | unique `(frozen_input_id, snapshot_id)`; hash equality; source is official. |
| `model.frozen_input_external_markets` | `market.external_market_snapshots(snapshot_id)` | unique `(frozen_input_id, snapshot_id)`; hash equality; source is external. |
| `model.frozen_input_contexts` | `context.team_context_snapshots(team_context_id)` | unique `(frozen_input_id, team_context_id)`; hash/effective time/cutoff check. |
| `model.frozen_input_evidence_bundles` | `context.evidence_bundles(evidence_bundle_id)` | unique `(frozen_input_id, evidence_bundle_id)`; bundle cutoff check. |
| `model.frozen_input_model_refs` | `governance.model_versions(model_version_id)` | unique `(frozen_input_id, model_version_id)`; approved role/version check. |
| `model.frozen_input_engine_refs` | `governance.engine_versions(engine_version_id)` | unique `(frozen_input_id, engine_version_id)`; approved role/version check. |

These tables are preferred to UUID arrays or a JSONB relationship list.

### 6.3 `model.feature_bundles`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `feature_bundle_id` | `uuid` | PK/default | Stable feature artifact identity. |
| `frozen_input_id` | `uuid` | NOT NULL | FK to `model.frozen_inputs`. |
| `frozen_input_hash` | `text` | NOT NULL | Must equal parent hash. |
| `role` | `text` | NOT NULL | Explicit role; immutable. |
| `shadow_revision`, `experiment_revision`, `experiment_id` | `text`, `text`, `uuid` | conditional | Required/not applicable by role. |
| `feature_schema_version`, `generator_version` | `text` | NOT NULL | Exact feature shape/generator identity. |
| `input_hash`, `feature_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | V4 hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| `generated_at`, `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | Generated time distinct from source; cutoff < kickoff. |
| `feature_values`, `missingness_summary`, `quality_flags` | `jsonb` | NOT NULL | Seven governed categories, typed missingness, and gate flags. |
| `status` | `text` | NOT NULL | `CREATED`, `VALIDATED`, `BLOCKED`, `INVALID`, `SUPERSEDED`. |
| contract/schema/created/metadata | common | required/default | Immutable once used by formal run. |

Unique: `(frozen_input_id, role, generator_version, input_hash)`.

### 6.4 `model.engine_runs`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `engine_run_id` | `uuid` | PK/default | Stable run identity. |
| `match_id`, `frozen_input_id`, `feature_bundle_id` | `uuid` | NOT NULL | FKs to match/input/features; same-match trigger. |
| `role` | `text` | NOT NULL | Immutable `PRODUCTION`, `SHADOW`, or `EXPERIMENT`. |
| `model_version_id`, `engine_version_id` | `uuid` | NOT NULL | FKs to registries; role/status agreement trigger. |
| `role_revision` | `text` | NOT NULL | Exact registry revision. |
| `shadow_revision`, `experiment_revision`, `experiment_id`, `build_id` | `text`, `text`, `uuid`, `text` | conditional | Shadow/Experiment identity envelope. |
| `frozen_input_hash`, `input_hash`, `output_hash` | `text` | NOT NULL | Exact source/input/output identities. |
| `implementation_hash`, `config_version`, `config_hash` | `text` | NOT NULL | Reproducibility identity; config is non-secret. |
| `schema_version`, `migration_version`, `dataset_version` | `text` | NOT NULL | Exact interface/storage/data identities. |
| `run_at`, `run_completed_at`, `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | Pre-match run gate requires run/completion before kickoff. |
| `runtime_ms` | `double precision` | NOT NULL | Finite non-negative telemetry; excluded from output hash by contract. |
| `runtime_environment` | `jsonb` | NOT NULL | Non-secret descriptor. |
| `random_seed` | `bigint` | conditional | Required for stochastic runs. |
| `simulation_version` | `text` | conditional | Required for simulation engines. |
| `status` | `text` | NOT NULL | V4 `run_status` values. |
| `future_information_leakage`, `run_invalid`, `tier_a_eligible`, `promotion_evidence` | `boolean` | false defaults | Gate outcome flags; invalid remains auditable. |
| `warnings`, `errors`, `payload` | `jsonb` | required/conditional | Payload required on success; errors required on invalid/blocked/failed. |
| common contract/provenance/hash/created/metadata fields | common | required/default | Append-only formal run. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata for the run envelope. |

### 6.5 `model.predictions`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `prediction_id` | `uuid` | PK/default | Stable prediction identity. |
| `match_id`, `frozen_input_id` | `uuid` | NOT NULL | FKs; same-match trigger. |
| `frozen_input_hash` | `text` | NOT NULL | Must equal Frozen Input. |
| `model_version_id` | `uuid` | NOT NULL | FK to model registry. |
| `role` | `text` | NOT NULL | Immutable role. |
| `prediction_revision` | `integer` | NOT NULL | Append-only revision. |
| `stage` | `text` | NOT NULL | Governed stage such as `PREMATCH_FORMAL`; non-empty. |
| `role_revision`, `shadow_revision`, `experiment_revision`, `experiment_id` | `text`, `text`, `text`, `uuid` | conditional | Exact role identity. |
| `model_run_at`, `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | `model_run_at < kickoff_at`; cutoff < kickoff. |
| `market_predictions`, `consensus`, `disagreement`, `uncertainty`, `risk` | `jsonb` | NOT NULL | Independent five-market payload and distinct interpretation layers. |
| `confidence_grade` | `text` | NOT NULL | `VERY_HIGH`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`, `BLOCKED`. |
| `recommendation_state` | `text` | NOT NULL | `PASS`, `NO_STRONG_RECOMMENDATION`, `BLOCKED`, `INSUFFICIENT_DATA`. |
| `recommendation_strength` | `text` | NOT NULL | `NONE`, `WEAK`, `MODERATE`, `STRONG`, `NOT_APPLICABLE`. |
| `input_hash`, `output_hash`, `prediction_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | Exact lineage hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| `future_information_leakage`, `run_invalid`, `tier_a_eligible`, `promotion_evidence` | `boolean` | false defaults | Gate flags. |
| `status` | `text` | NOT NULL | `DRAFT`, `FORMAL`, `FROZEN`, `SUPERSEDED`, `INVALID`, `BLOCKED`. |
| `supersedes_prediction_id` | `uuid` | nullable | Self-FK prior revision; same match/model/role/stage. |
| contract/schema/created/metadata | common | required/default | Append-only formal history. |

Unique logical key: `(match_id, model_version_id, role, stage, prediction_revision)`.

### 6.6 `model.prediction_engine_runs`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `prediction_engine_run_id` | `uuid` | PK/default | Stable join identity. |
| `prediction_id`, `engine_run_id` | `uuid` | NOT NULL | FKs; same match and compatible role trigger. |
| `market` | `text` | NOT NULL | One of five market keys or governed cross-market layer. |
| `lineage_purpose` | `text` | NOT NULL | `PRIMARY_MARKET`, `CONSENSUS`, `UNCERTAINTY`, `RISK`, `SUPPORTING`. |
| `output_hash` | `text` | NOT NULL | Must equal referenced run output hash. |
| `sequence` | `integer` | NOT NULL | Positive deterministic order. |
| `created_at`, `metadata` | common | default/required | Membership append-only. |

Unique: `(prediction_id, engine_run_id, market, lineage_purpose)` and `(prediction_id, sequence)`.

### 6.7 `model.frozen_predictions`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `frozen_prediction_id` | `uuid` | PK/default | Permanent immutable freeze identity. |
| `match_id`, `prediction_id`, `frozen_input_id` | `uuid` | NOT NULL | FKs; same-match trigger. |
| `model_version_id` | `uuid` | NOT NULL | FK; must match Prediction. |
| `role` | `text` | NOT NULL | Immutable; public path requires `PRODUCTION`. |
| `freeze_revision` | `integer` | NOT NULL | Append-only freeze revision. |
| `prediction_hash`, `frozen_snapshot_hash`, `frozen_input_hash` | `text` | NOT NULL | Exact unfrozen/frozen/source hashes. |
| `snapshot` | `jsonb` | NOT NULL | Immutable embedded Prediction snapshot; object. |
| `frozen_at`, `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | `frozen_at < kickoff_at`; cutoff < kickoff. |
| `immutable` | `boolean` | `NOT NULL DEFAULT true` | Must remain true. |
| `future_information_leakage`, `run_invalid`, `tier_a_eligible`, `promotion_evidence` | `boolean` | false defaults | Frozen gate flags. |
| `status` | `text` | `NOT NULL DEFAULT 'FROZEN'` | `FROZEN`, `SUPERSEDED`, `BLOCKED`, `INVALID`. |
| `supersedes_frozen_prediction_id` | `uuid` | nullable | Self-FK predecessor. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| contract/schema/provenance/payload/created/metadata | common | required/default | Strict append-only. |

Unique: `(match_id, role, model_version_id, freeze_revision)`. A trigger enforces Prediction/Frozen Input match, role, and hash equality.

## 7. Evaluation

### 7.1 `evaluation.official_results`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `result_id` | `uuid` | PK/default | Stable result revision identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`. |
| `result_lineage_id` | `uuid` | NOT NULL | Stable correction chain identity. |
| `result_revision` | `integer` | NOT NULL | Monotonic chain revision. |
| `supersedes_result_id` | `uuid` | nullable | Self-FK prior result; same match/lineage. |
| `full_time_home`, `full_time_away`, `half_time_home`, `half_time_away` | `integer` | NOT NULL | Non-negative regulation scores. |
| `result_scope` | `text` | NOT NULL | Default `REGULATION_90_PLUS_STOPPAGE`; explicit override only by rules. |
| `official_result_payload` | `jsonb` | NOT NULL | Source-normalized result plus raw reference; no pre-match use. |
| `source`, `source_type`, `source_reference` | common | NOT NULL | Official result authority. |
| `source_timestamp`, `observed_at`, `ingested_at`, `verified_at` | `timestamptz` | NOT NULL | Postmatch result lineage. |
| `result_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | V4 hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |
| `status` | `text` | NOT NULL | `VERIFIED`, `BLOCKED`, `CORRECTED`, `REJECTED`. |
| contract/schema/created/metadata | common | required/default | Strict append-only; current row derived from terminal chain. |

Unique: `(match_id, result_revision)` and `(result_lineage_id, result_revision)`. No `is_current` mutable flag is required; current is the terminal revision not superseded by another row.

### 7.2 `evaluation.postmatch_reviews`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `review_id` | `uuid` | PK/default | Stable review revision identity. |
| `match_id`, `frozen_prediction_id`, `result_id` | `uuid` | NOT NULL | FKs; all resolve to same match. |
| `review_type` | `text` | NOT NULL | Exactly `MODEL_EVALUATION` or `MATCH_EXPLANATION`. |
| `review_revision` | `integer` | NOT NULL | Append-only review revision. |
| `supersedes_review_id` | `uuid` | nullable | Self-FK same review lineage. |
| `market_hit_results` | `jsonb` | required for Model Evaluation | Immutable per-market comparison. |
| `score_metrics` | `jsonb` | required for Model Evaluation | Brier/Log Loss/MAE/coverage or explicit N/A. |
| `error_attribution` | `jsonb` | NOT NULL | Diagnostic only; never auto-changes model. |
| `postmatch_evidence_refs` | `jsonb` | required for Explanation; forbidden for Model Evaluation | Separate explanation branch. |
| `allowed_input_set` | `text` | NOT NULL | `FROZEN_PREDICTION_RESULT_ONLY` or `POSTMATCH_EXPLANATION_EVIDENCE`. |
| `reviewed_at` | `timestamptz` | NOT NULL | Review business time. |
| hashes/source/status/contract/schema/created/metadata | common | required/default | Append-only correction path. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata. |

Unique: `(frozen_prediction_id, review_type, review_revision)`.

### 7.3 `evaluation.tier_a_samples`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `tier_a_sample_id` | `uuid` | PK/default | Stable sample identity. |
| `sample_no` | `bigint GENERATED ALWAYS AS IDENTITY` | NOT NULL | Unique V4 sequence beginning at #001. |
| `match_id`, `frozen_input_id` | `uuid` | NOT NULL | FKs; shared source boundary. |
| `production_prediction_id`, `production_frozen_prediction_id` | `uuid` | NOT NULL | FKs; role must be Production. |
| `shadow_prediction_id`, `shadow_frozen_prediction_id` | `uuid` | NOT NULL | FKs; role must be Shadow and pre-kickoff. |
| `shadow_model_version_id`, `shadow_engine_version_id` | `uuid` | NOT NULL | Denormalized qualified Shadow registry refs for pair lookup; FKs and equality to the Shadow Prediction/Engine Run are trigger-checked. |
| `result_id`, `review_id` | `uuid` | NOT NULL | FKs; result/review same match and eligible review. |
| `shadow_revision` | `text` | NOT NULL | Shadow identity part of pair uniqueness. |
| `frozen_input_hash` | `text` | NOT NULL | Must equal both paired frozen artifacts. |
| Production/Shadow implementation/config/input/output hashes | `text` | NOT NULL | All required identity evidence for both sides. |
| `production_run_completed_at`, `shadow_run_completed_at` | `timestamptz` | NOT NULL | Both `< kickoff_at`. |
| `prediction_cutoff_at`, `kickoff_at` | `timestamptz` | NOT NULL | Pair shares cutoff/kickoff interpretation. |
| `pair_integrity_passed`, `completeness_gate_passed`, `pre_kickoff_gate_passed` | `boolean` | false default | Must all be true for eligible. |
| `future_information_leakage`, `tier_a_eligible`, `promotion_evidence` | `boolean` | false default | Any failure forces false. |
| `qualification_status` | `text` | NOT NULL | `ELIGIBLE`, `REJECTED`, `BLOCKED`. |
| `exclusion_rule_version` | `text` | NOT NULL | Declared before evaluation. |
| hashes/contract/schema/created/metadata | common | required/default | Strict append-only evidence. |

Unique pair identity: `(match_id, production_prediction_id, shadow_prediction_id, shadow_revision)` and unique `sample_no`. Experiment is rejected by trigger.

### 7.4 `evaluation.tier_a_run_members`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `tier_a_run_member_id` | `uuid` | PK/default | Stable membership. |
| `tier_a_sample_id`, `prediction_id`, `frozen_prediction_id`, `engine_run_id` | `uuid` | NOT NULL | Exact member FKs. |
| `role` | `text` | NOT NULL | Only `PRODUCTION` or `SHADOW`; no Experiment. |
| `member_order` | `integer` | NOT NULL | Stable order. |
| `frozen_input_hash`, `output_hash` | `text` | NOT NULL | Same-hash pair evidence. |
| `pre_kickoff_completed_at` | `timestamptz` | NOT NULL | Must precede match kickoff. |
| `created_at`, `metadata` | common | default/required | Append-only. |

Unique: `(tier_a_sample_id, role, prediction_id)` and `(tier_a_sample_id, member_order)`.

### 7.5 `evaluation.promotion_reviews`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `promotion_review_id` | `uuid` | PK/default | Stable review identity. |
| `candidate_model_version_id` | `uuid` | NOT NULL | FK to Shadow candidate registry row. |
| `candidate_engine_version_id` | `uuid` | nullable | Optional candidate engine; role checked. |
| `source_role` | `text` | `NOT NULL DEFAULT 'SHADOW'` | Must be `SHADOW`. |
| `review_revision` | `integer` | NOT NULL | Append-only decision revision. |
| `status` | `text` | NOT NULL | `OPEN`, `APPROVED`, `REJECTED`, `WITHDRAWN`. |
| `forward_evidence`, `calibration_evidence`, `regression_evidence`, `integrity_evidence`, `leakage_evidence`, `performance_evidence` | `jsonb` | NOT NULL | Immutable evidence objects; all required before approval. |
| `manual_approver`, `approval_reason` | `text` | conditional/nullable | Required for approval. |
| `approved_at` | `timestamptz` | conditional | Required for approval. |
| `production_model_version_id` | `uuid` | conditional | FK to new Production identity when approved; never a role conversion. |
| `auto_promotion` | `boolean` | `NOT NULL DEFAULT false` | CHECK must remain false. |
| `supersedes_promotion_review_id` | `uuid` | nullable | Prior review revision. |
| hashes/contract/schema/created/metadata | common | required/default | Strict append-only. |

Unique: `(candidate_model_version_id, review_revision)`. Approval requires candidate role Shadow, all evidence gates true, manual approver, and a new Production identity.

### 7.6 `evaluation.promotion_review_samples`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `promotion_review_sample_id` | `uuid` | PK/default | Stable membership. |
| `promotion_review_id`, `tier_a_sample_id` | `uuid` | NOT NULL | FKs; sample must be eligible and immutable. |
| `evidence_hash` | `text` | NOT NULL | Hash of the cited sample evidence. |
| `created_at`, `metadata` | common | default/required | Append-only. |

Unique: `(promotion_review_id, tier_a_sample_id)`.

### 7.7 `evaluation.calibration_records`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `calibration_record_id` | `uuid` | PK/default | Stable evidence identity. |
| `model_version_id` | `uuid` | NOT NULL | FK to registry. |
| `engine_version_id` | `uuid` | nullable | Optional exact engine. |
| `role` | `text` | NOT NULL | Role-scoped; immutable. |
| `market` | `text` | NOT NULL | One governed market key. |
| `scope_key`, `confidence_band` | `text` | NOT NULL | Stratification identity; confidence is not probability. |
| `sample_window_start`, `sample_window_end` | `date` | NOT NULL | Evaluation period; start <= end. |
| `sample_count` | `bigint` | NOT NULL | Non-negative; declared sample scope. |
| `metric_payload` | `jsonb` | NOT NULL | Brier/calibration metrics; not editable. |
| `dataset_version`, `input_hash` | `text` | NOT NULL | Exact evaluation input identity. |
| `record_revision`, `supersedes_calibration_record_id` | `integer`, `uuid` | revision required; predecessor conditional | Correction/recalculation chain. |
| `status`, hashes/contract/schema/created/metadata | common | required/default | Append-only role/model namespace. |

Unique logical identity: `(model_version_id, role, market, scope_key, confidence_band, sample_window_start, sample_window_end, record_revision)`.

## 8. Governance history

### 8.1 `governance.incidents`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `incident_id` | `uuid` | PK/default | Stable incident identity. |
| `incident_lineage_id` | `uuid` | NOT NULL | Append-only incident chain. |
| `incident_revision` | `integer` | NOT NULL | Monotonic revision. |
| `incident_class` | `text` | NOT NULL | `TIME_LEAKAGE_INCIDENT`, `PUBLICATION_INCIDENT`, `SECURITY_INCIDENT`, `MODEL_INCIDENT`, etc. |
| `severity` | `text` | NOT NULL | `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`; optional policy maps SEV-1..3. |
| `status` | `text` | NOT NULL | `OPEN`, `MITIGATED`, `RESOLVED`, `CLOSED`. |
| `affected_entity_type`, `affected_entity_id` | `text` | NOT NULL | Typed entity name plus opaque ID; trigger validates allowed entity family. |
| `match_id` | `uuid` | nullable | Optional FK to canonical match. |
| `affected_role` | `text` | nullable | Role if runtime-related. |
| `detected_at`, `known_at` | `timestamptz` | NOT NULL | Detected <= known when both applicable. |
| `containment`, `resolution`, `owner` | `jsonb`, `jsonb`, `text` | conditional | Before/after remediation evidence. |
| `before_state`, `after_state` | `jsonb` | NOT NULL | Evidence snapshots; no secrets. |
| `supersedes_incident_id` | `uuid` | nullable | Prior event/revision. |
| hashes/contract/schema/created/metadata | common | required/default | Strict append-only event history. |

Unique: `(incident_lineage_id, incident_revision)`.

### 8.2 `governance.audit_logs`

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `audit_log_id` | `bigint GENERATED ALWAYS AS IDENTITY` | PK | Monotonic append sequence; not a substitute for UUID business IDs. |
| `actor` | `text` | NOT NULL | Service/user/operator identity; no secret/token. |
| `actor_role` | `text` | NOT NULL | Controlled writer role. |
| `action` | `text` | NOT NULL | `INSERT`, `UPDATE`, `STATUS_CHANGE`, `CORRECTION`, `FREEZE`, `RUN`, `PROMOTION`, `ROLLBACK`, `PUBLICATION`, `INCIDENT`, etc. |
| `entity_type` | `text` | NOT NULL | Allow-listed V4 entity type. |
| `entity_id` | `text` | NOT NULL | Canonical text rendering of referenced UUID/bigint; validated by action/entity contract. |
| `match_id` | `uuid` | nullable | Optional typed FK for match-scoped events. |
| `before_state`, `after_state`, `metadata` | `jsonb` | NOT NULL | Before/after/trace metadata; secrets forbidden. |
| `happened_at` | `timestamptz` | NOT NULL | Business event time; must not precede prior chain event for same stream. |
| `prev_hash` | `text` | nullable | Previous chain entry; NULL only at stream root. |
| `entry_hash` | `text` | NOT NULL | Canonical hash of declared audit envelope; format/chain checked. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Algorithm and canonical profile metadata. |
| `created_at` | `timestamptz` | default | Insertion time, not event time. |

Unique: `entry_hash`; index/trigger enforces append-only and per-stream chain. Audit creation is performed by a controlled backend path; direct client table writes are denied.

## 9. Public projection

### 9.1 `public.public_read_projections`

This is a safe projection ledger, not a canonical source. It is append-only and has no public write policy.

| Field | Type | NULL/default | Rule |
|---|---|---|---|
| `projection_id` | `uuid` | PK/default | Stable projection revision identity. |
| `match_id` | `uuid` | NOT NULL | FK to `core.matches`; safe match identity. |
| `production_model_version_id`, `production_prediction_id`, `production_frozen_prediction_id` | `uuid` | NOT NULL | Internal proof refs; role/active Production checked; not exposed to anon. |
| `public_odds_snapshot_id` | `uuid` | nullable | Internal official snapshot ref; external source prohibited. |
| safe display fields | `text`, `timestamptz` | required | Competition/home/away labels, kickoff, match status. |
| `public_model_name`, `public_model_version`, `public_model_revision` | `text` | NOT NULL | Public-safe Production registry display fields; no internal implementation/config hash. |
| `safe_odds_summary`, `safe_selection_summary`, `safe_result_summary` | `jsonb` | required/conditional | Public allow-list only; no raw features/debug/risk decomposition. |
| `prediction_business_at` | `timestamptz` | NOT NULL | Exact Prediction business timestamp used by publication gate. |
| `frozen_business_at` | `timestamptz` | NOT NULL | Exact Frozen Prediction timestamp. |
| `odds_business_at`, `context_business_at` | `timestamptz` | NOT NULL | Exact source business timestamps. |
| `result_business_at`, `review_business_at` | `timestamptz` | nullable | Exact postmatch source times where present. |
| `projection_revision` | `integer` | NOT NULL | Unique per Production Frozen Prediction. |
| `projection_hash`, `payload_hash`, `provenance_hash` | `text` | NOT NULL | Public projection hashes. |
| `hash_algorithm`, `hash_profile` | `text` | NOT NULL/default | Canonicalization metadata; not exposed to anon/public views. |
| `publication_status` | `text` | NOT NULL | `PUBLISHED`, `WITHDRAWN`, `BLOCKED`. |
| `published_at` | `timestamptz` | nullable | Publication event time; not used as canonical latest business time. |
| `contract_version`, `schema_version`, `created_at`, `metadata` | common | required/default | Append-only publication history. |

Unique: `(match_id, production_frozen_prediction_id, projection_revision)`. Triggers verify every internal ref is Production and every business time equals a real upstream record time. Only the Production publication gate can insert.

## 10. Cross-table timestamp/update policy

- `updated_at` is absent from append-only history and never used for latest business data.
- Registry `updated_at` is not a release identity and is excluded from content hashes.
- `created_at` is not a substitute for `source_timestamp`, `observed_at`, `run_at`, `frozen_at`, `verified_at`, or `reviewed_at`.
- A correction creates a new revision row. No table in this catalog uses a mutable `deleted_at` shortcut to hide history.
- The physical schema contains no V3.3.3 FK, copy, import, or shared output column.
