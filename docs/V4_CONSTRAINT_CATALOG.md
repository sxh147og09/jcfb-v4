# JCFB V4 Constraint Catalog 1.0

Status: V4-010 CONSTRAINT AND INTEGRITY BLUEPRINT (DESIGN-ONLY)

This catalog defines database-enforceable checks and the trigger/function checks that are required where a plain PostgreSQL FK or CHECK cannot express V4 semantics. It must be read with `V4_CONSTITUTION.md`, `V4_DATA_CONTRACT.md`, `V4_CANONICAL_DATA_MODEL.md`, and `V4_TABLE_CATALOG.md`. It does not execute SQL.

## 1. Constraint conventions

- Constraint names use `<schema>_<table>_<rule>_ck|uq|fk`.
- `NULL` is a technical empty value only. Business unknown/unavailable/not-verified/blocked/not-applicable states are explicit text fields or typed state objects.
- `ON DELETE` is `RESTRICT`/`NO ACTION` for audit-critical history. Cascading deletion is not allowed across V4 evidence, frozen, runtime, evaluation, incident, audit, or public projection rows.
- Every FK column has a supporting B-tree index unless a reviewed advisor result documents why it is unnecessary.
- All role, state, market, side, source, hash, numeric-range, and JSONB-shape checks are fail closed.
- Cross-table checks must reject the write or set an explicit non-eligible `BLOCKED`/`INVALID` outcome. They must never repair mismatched IDs or copy a value from a different match.

## 2. Direct primary keys and foreign keys

### 2.1 Primary keys

Every candidate business row uses a UUID PK: `competition_id`, `team_id`, `team_alias_id`, `match_id`, both snapshot IDs, `team_context_id`, `evidence_id`, `evidence_bundle_id`, `evidence_bundle_item_id`, both registry IDs, `frozen_input_id`, child membership IDs, `feature_bundle_id`, `engine_run_id`, `prediction_id`, `prediction_engine_run_id`, `frozen_prediction_id`, `result_id`, `review_id`, `tier_a_sample_id`, `tier_a_run_member_id`, promotion IDs/memberships, `calibration_record_id`, `incident_id`, and `projection_id`.

The two intentional sequence exceptions are `evaluation.tier_a_samples.sample_no` and `governance.audit_logs.audit_log_id`; each is monotonic and unique, while the row still has a UUID identity where the entity contract requires one.

### 2.2 Required FKs

| Constraint | Child | Parent | Delete/update rule |
|---|---|---|---|
| `matches_competition_fk` | `core.matches.competition_id` | `core.competitions.competition_id` | RESTRICT / RESTRICT |
| `matches_home_team_fk`, `matches_away_team_fk` | `core.matches.home_team_id`, `away_team_id` | `core.teams.team_id` | RESTRICT / RESTRICT |
| `team_aliases_team_fk` | `core.team_aliases.team_id` | `core.teams.team_id` | RESTRICT / RESTRICT |
| `official_odds_match_fk` | `market.official_odds_snapshots.match_id` | `core.matches.match_id` | RESTRICT / RESTRICT |
| `external_market_match_fk` | `market.external_market_snapshots.match_id` | `core.matches.match_id` | RESTRICT / RESTRICT |
| `official_odds_evidence_fk` | official `evidence_ref` | `context.evidence_items.evidence_id` | RESTRICT / RESTRICT |
| `official_odds_supersedes_fk`, `external_market_supersedes_fk` | snapshot correction predecessor | same snapshot table | RESTRICT / RESTRICT |
| `team_context_match_fk`, `team_context_team_fk` | context match/team | core match/team | RESTRICT / RESTRICT |
| `team_context_evidence_fks` | context/evidence membership | context snapshot/evidence item | RESTRICT / RESTRICT |
| `evidence_scope_match_fk`, `evidence_scope_team_fk` | optional evidence scope | core match/team | RESTRICT / RESTRICT |
| `bundle_match_fk` | `context.evidence_bundles.match_id` | `core.matches.match_id` | RESTRICT / RESTRICT |
| `bundle_item_bundle_fk`, `bundle_item_evidence_fk` | bundle membership | bundle/evidence | RESTRICT / RESTRICT |
| `registry_predecessor_fk` | model/engine self predecessor | same registry table | RESTRICT / RESTRICT |
| `engine_model_fk` | `governance.engine_versions.model_version_id` | model registry | RESTRICT / RESTRICT |
| `frozen_input_match_fk` | `model.frozen_inputs.match_id` | core match | RESTRICT / RESTRICT |
| `frozen_input_supersedes_fk` | Frozen Input predecessor | Frozen Input | RESTRICT / RESTRICT |
| `frozen_input_selection_fks` | six normalized selection tables | exact market/context/evidence/registry parents | RESTRICT / RESTRICT |
| `feature_bundle_input_fk` | Feature Bundle input | Frozen Input | RESTRICT / RESTRICT |
| `engine_run_fks` | Engine Run match/input/feature/model/engine | exact parents | RESTRICT / RESTRICT |
| `prediction_fks` | Prediction match/input/model/predecessor | exact parents | RESTRICT / RESTRICT |
| `prediction_engine_run_fks` | join prediction/run | exact parents | RESTRICT / RESTRICT |
| `frozen_prediction_fks` | Frozen Prediction match/prediction/input/model/predecessor | exact parents | RESTRICT / RESTRICT |
| `result_match/supersedes_fks` | Result match/predecessor | core match/result | RESTRICT / RESTRICT |
| `review_fks` | Review match/frozen prediction/result/predecessor | exact parents | RESTRICT / RESTRICT |
| `tier_a_fks` | sample match/input/predictions/frozen predictions/result/review | exact parents | RESTRICT / RESTRICT |
| `tier_a_member_fks` | member sample/prediction/frozen/run | exact parents | RESTRICT / RESTRICT |
| `promotion_fks` | candidate releases, production release, predecessor | registries/reviews | RESTRICT / RESTRICT |
| `calibration_fks` | calibration model/engine/predecessor | registries/calibration | RESTRICT / RESTRICT |
| `incident_match/supersedes_fks` | optional match/prior incident | core match/incident | RESTRICT / RESTRICT |
| `projection_fks` | projection match/Production refs/official odds | exact parents | RESTRICT / RESTRICT |

Generic `entity_type + entity_id` fields in Incidents and Audit Logs are intentionally not untyped business FKs. Their allowed entity families and same-match scope are validated by trigger functions, preventing a generic text field from bypassing typed relationships.

## 3. Business-key and dedup constraints

| ID | Constraint | Database form | Purpose |
|---|---|---|---|
| C-001 | Match business key | `UNIQUE (data_date, official_match_no)` on `core.matches` | Preserves leading zeros and prevents duplicate daily fixture rows. |
| C-002 | Match identity key | CHECK/trigger `match_identity_key = YYYY-MM-DD:official_match_no` | Prevents a key for another date or an unqualified match number. |
| C-003 | Home/away identity | CHECK `home_team_id <> away_team_id` | A match cannot use the same team twice. |
| C-004 | Competition/team source key | unique source-scoped keys | Display names remain labels, not permanent IDs. |
| C-005 | Alias dedup | `UNIQUE (team_id, normalized_alias, locale, source_scope, valid_from)` | Scope aliases by team, locale, source, and validity. |
| C-006 | Official snapshot dedup | `UNIQUE (match_id, source, snapshot_kind, captured_at, snapshot_hash)` | Replaying the same official observation is idempotent without collapsing revisions. |
| C-007 | External snapshot dedup | `UNIQUE (match_id, provider, market, normalized_line, captured_at, snapshot_hash)` | Keeps provider, market, line, capture, and content identity separate from official odds. |
| C-008 | Team context revision | `UNIQUE (match_id, team_id, side, revision)` | One immutable revision identity per context chain. |
| C-009 | Evidence bundle revision | `UNIQUE (match_id, bundle_revision)` | Bundle membership/cutoff corrections append a new bundle. |
| C-010 | Context evidence membership | `UNIQUE (team_context_id, evidence_id)` | Prevents duplicate context evidence references. |
| C-011 | Evidence membership | unique bundle/evidence and bundle/order pairs | Prevents duplicate or ambiguous membership ordering. |
| C-012 | Frozen Input revision | `UNIQUE (match_id, revision)` | Required immutable input revision uniqueness. `frozen_input_hash` gets a non-unique index because equal hash is required for A/B. |
| C-013 | Feature identity | `UNIQUE (frozen_input_id, role, generator_version, input_hash)` | Prevents duplicate formal feature artifacts. |
| C-014 | Prediction logical key | `UNIQUE (match_id, model_version_id, role, stage, prediction_revision)` | Exact requested match + model + role + stage + revision uniqueness. |
| C-015 | Prediction engine membership | unique `(prediction_id, engine_run_id, market, lineage_purpose)` plus `(prediction_id, sequence)` | Preserves normalized many-to-many lineage/order. |
| C-016 | Frozen Prediction revision | `UNIQUE (match_id, role, model_version_id, freeze_revision)` | One immutable freeze identity per model/role revision. |
| C-017 | Official Result revision | unique `(match_id, result_revision)` and `(result_lineage_id, result_revision)` | Corrections append; result chain stays unambiguous. |
| C-018 | Review revision | `UNIQUE (frozen_prediction_id, review_type, review_revision)` | Model Evaluation and Match Explanation histories cannot overwrite each other. |
| C-019 | Tier A sequence | `UNIQUE (sample_no)` | V4 sequence starts at #001 and never reuses a number. |
| C-020 | Tier A pair | `UNIQUE (match_id, production_prediction_id, shadow_prediction_id, shadow_revision)` | Prevents double registration of the same immutable pair. |
| C-021 | Tier A membership | unique sample/role/prediction and sample/order | Preserves exact Production/Shadow members. |
| C-022 | Promotion sample membership | `UNIQUE (promotion_review_id, tier_a_sample_id)` | A sample is cited once per promotion review. |
| C-023 | Calibration identity | scoped unique key including model, role, market, band, date window, revision | Calibration evidence cannot overwrite another role/model scope. |
| C-024 | Incident chain | `UNIQUE (incident_lineage_id, incident_revision)` | Incident status changes are new events. |
| C-025 | Projection revision | `UNIQUE (match_id, production_frozen_prediction_id, projection_revision)` | Public publication corrections append a new projection row. |
| C-026 | Audit entry | `UNIQUE (entry_hash)` | Prevents duplicate hash-chain entries. |

## 4. Direct CHECK constraints

### 4.1 Identity, text, and hash checks

- All required identity/text keys satisfy `btrim(value) <> ''`; official match numbers are digits and retain leading zeros.
- SemVer components are non-negative and agree with the qualified version text; registry revision is non-empty and immutable.
- Every persisted V4 hash named by its contract satisfies `^sha256:[0-9a-f]{64}$`.
- `hash_algorithm = 'SHA-256'` and `hash_profile = 'v4-canonical-json@1.0'` for the first blueprint profile. A profile change requires a new contract/identity, not a reinterpretation of old hashes.
- `metadata`, `runtime_environment`, warnings/errors, and named payload objects have the required JSONB type. JSONB does not carry an FK or primary relationship.

### 4.2 Role/status checks

- `role IN ('PRODUCTION','SHADOW','EXPERIMENT')` on all role-owned tables.
- `owner_role IN ('PRODUCTION','EXPERIMENT')` on Frozen Inputs; a shared Forward A/B input is owned by the Production freeze gate and read by Shadow.
- `shadow_revision` is required only for `SHADOW`; `experiment_revision`, `experiment_id`, and `build_id` are required only for `EXPERIMENT`; the inapplicable fields are explicitly NULL with a governed `NOT_APPLICABLE` reason in the role envelope.
- Production rows use `role=PRODUCTION`; Shadow and Experiment rows cannot carry a Production active pointer or public status.
- `auto_promotion = false` is a hard check on Promotion Reviews.
- Public rows use `publication_status IN ('PUBLISHED','WITHDRAWN','BLOCKED')`; public views filter to `PUBLISHED`.

### 4.3 Market/source/availability checks

- Official odds `source_is_official = true`; external market `source_is_official = false`.
- External `market` is one of the three contract values; 1X2 uses `normalized_line='NOT_APPLICABLE'` and line value NULL; line markets require a line value.
- Decimal odds/prices are finite and `> 0`; handicap/total lines satisfy the declared numeric precision.
- Official market availability contains exactly `spf`, `rqspf`, `total_goals`, `exact_score`, `half_full`. An available market requires its payload; an unavailable market requires a non-empty reason and no fabricated payload.
- `availability_time_state='KNOWN'` requires non-NULL `availability_at` and a non-UNKNOWN basis. `UNKNOWN`/`BLOCKED` requires an explicit reason and cannot pass a formal pre-match gate.
- `availability_at <= captured_at`/`as_of_at` where the contract defines the observation boundary; source time is not silently copied from system ingestion.

### 4.4 Score, result, and evaluation checks

- Score fields are integers `>= 0`.
- `result_scope='REGULATION_90_PLUS_STOPPAGE'` is the default; extra time/penalties remain in payload but do not change default evaluation.
- Model Evaluation requires `market_hit_results` and `score_metrics`, forbids postmatch evidence refs, and uses `allowed_input_set='FROZEN_PREDICTION_RESULT_ONLY'`.
- Match Explanation uses the separate allowed input set and cannot populate or mutate Model Evaluation metrics.
- Probability columns are between 0 and 1; the exact market distribution normalization and five-market independence checks are trigger/function checks over JSONB payloads and normalized run refs.

## 5. Cross-table relationship checks

### 5.1 `governance.validate_frozen_input_lineage()`

Deferred/constraint-triggered validation must verify:

1. Parent `core.matches` exists and `canonical_match_hash` matches the selected match revision.
2. Every selected official/external snapshot, context, and evidence bundle exists, its copied hash equals the parent row hash, and its `match_id` equals the Frozen Input `match_id`.
3. Official refs point only to `market.official_odds_snapshots`; external refs cannot satisfy an official selection.
4. Every selected source `availability_at` is known and `<= prediction_cutoff_at`; bundle cutoff is within the same boundary.
5. All registry refs resolve to the declared role/version identities; no V3.3.3 relation is accepted.
6. `prediction_cutoff_at < kickoff_at`, `frozen_at < kickoff_at` when frozen, `future_information_leakage=false`, and `immutable=true` when status is `FROZEN`.
7. A `FORWARD_AB` input has an `ab_comparison_group_id`; an `EXPERIMENT_ONLY` input cannot be used for Forward Tier A.

Failure is a rejected write or `BLOCKED`/`REJECTED` input. No trigger may replace a missing snapshot with the newest row.

### 5.2 `governance.validate_runtime_lineage()`

For Feature Bundles, Engine Runs, and Predictions:

- the exact Frozen Input exists and copied `frozen_input_hash` equals it;
- Feature Bundle parent, Engine Run, Prediction, and all normalized child refs resolve to the same `match_id`;
- model/engine registry roles and revisions match the row role;
- Production uses the approved active Production registry identity; Shadow/Experiment cannot use a Production label;
- Prediction engine membership has the same match, compatible role, exact output hash, and allowed `lineage_purpose`;
- five independent market keys are present; a downstream market cannot silently reuse SPF output;
- supersedes predecessor is same match/model/role/stage and has a lower revision.

This function is a trigger/function blueprint. It must fail closed if a relationship or hash cannot be proven.

### 5.3 `governance.validate_frozen_prediction_lineage()`

Reject unless:

- `frozen_predictions.match_id = predictions.match_id = frozen_inputs.match_id`;
- model version, role, `prediction_hash`, `frozen_input_hash`, cutoff, and kickoff agree;
- the embedded snapshot hash is the hash of the declared freeze boundary (recomputed by the approved canonicalization implementation, not a database approximation);
- `frozen_at < kickoff_at`, `immutable=true`, and no leakage/invalid flag is true for an eligible freeze;
- predecessor is same identity family and lower `freeze_revision`.

## 6. No-future-leakage constraints

`governance.validate_prematch_gate()` is required on Frozen Input formation, Feature Bundle validation, Engine Run completion, Prediction formation, Frozen Prediction formation, and Tier A registration. It must check:

```text
all selected availability_at <= prediction_cutoff_at
AND prediction_cutoff_at < kickoff_at
AND model_run_at < kickoff_at
AND run_completed_at < kickoff_at when pre-match eligibility is claimed
AND frozen_at < kickoff_at when frozen
AND no result/event/postmatch evidence reference exists in the accepted input set
AND future_information_leakage = FALSE
AND run_invalid = FALSE
AND all IDs and hashes resolve exactly
```

Database behavior:

- Unknown/conflicting source time, missing hash, or unresolved ref: fail closed as `BLOCKED`/`NOT_VERIFIED`.
- A discovered future fact may be stored only as `INVALID`/`BLOCKED` evidence with `future_information_leakage=true`, `tier_a_eligible=false`, and `promotion_evidence=false`.
- A post-kickoff Shadow completion is never Forward evidence, even if its payload is otherwise valid.
- `ingested_at`, `generated_at`, `created_at`, and page/deploy time cannot satisfy an availability or business-update check.

## 7. Tier A integrity constraints

`governance.validate_tier_a_pair()` must reject or mark ineligible unless all conditions pass:

1. Pair row, Production Prediction/Frozen Prediction, Shadow Prediction/Frozen Prediction, and Frozen Input have the same `match_id`.
2. Production role is exactly `PRODUCTION`; Shadow role is exactly `SHADOW`; no Experiment row is referenced.
3. Both sides reference the same exact `frozen_input_id` and `frozen_input_hash`, `prediction_cutoff_at`, and `kickoff_at` interpretation.
4. Both run completions and freezes are strictly before kickoff.
5. Required implementation/config/input/output hashes exist and match the respective referenced rows.
6. Official Result and the eligible Postmatch Review resolve to the same match; review type is allowed for Tier A evaluation.
7. `pair_integrity_passed`, `completeness_gate_passed`, `pre_kickoff_gate_passed`, and `tier_a_eligible` are true only after validation; Experiment can never satisfy the check.
8. `sample_no` is assigned once and never reused; a rejected sample remains rejected history.

If any item fails, `qualification_status` is `REJECTED`/`BLOCKED`, `tier_a_eligible=false`, and the original evidence remains append-only.

## 8. Production uniqueness constraints

The registry uses two layers:

1. A partial unique index on `governance.model_versions(model_family, canonical_output_channel)` where `role='PRODUCTION' AND status='PRODUCTION' AND is_canonical_active=true`.
2. A controlled activation function that locks the family/channel, verifies Promotion Review/manual approval, appends a `release_pointer_event` and audit event, marks the predecessor inactive/retired through the approved metadata path, and inserts/activates the successor.

The same pattern may be applied to `engine_versions` by engine/channel. A transaction that cannot prove one active Production release fails closed with `PRODUCTION_UNIQUENESS_FAILURE`; a rollback creates a new Production identity rather than silently reactivating an old row.

## 9. Revision and correction constraints

- Every `supersedes_*_id` points to the same family/lineage and a strictly lower revision; a recursive cycle check is required.
- `official_results` correction is `INSERT` of a new result revision with same match/lineage, prior result FK, before/after evidence, reason, actor, time, and new hash. No UPDATE/DELETE path exists.
- `postmatch_reviews` correction is `INSERT` of a new review revision with prior review FK; it cannot alter the evaluated Frozen Prediction or historical KPI.
- Frozen Input is mutable only in an approved, not-yet-frozen `DRAFT`; after `status='FROZEN'` or `immutable=true`, any change is rejected and the correction path is a new row.
- Frozen Prediction is permanently immutable; a new freeze is a new row/revision.
- Promotion evidence membership and calibration evidence are append-only; a changed scope or metric is a new record.
- Registry `status`, active pointer, effective, and retirement metadata are the only controlled updates. Registry identity/hashes/role/version fields remain immutable and every allowed update is audited.

## 10. Audit and V3 isolation constraints

Every lifecycle operation has a required audit event with `actor`, `action`, `entity_type`, `entity_id`, `before_state`, `after_state`, `metadata`, `happened_at`, `prev_hash`, and `entry_hash`. The audit stream is append-only and hash chained.

No V4 FK, policy, view, function, seed, or payload is allowed to reference a V3.3.3 table, ID, model output, result, review, sample, parameter, or audit history. A benchmark, if later authorized, is an external read adapter and not a V4 relation.

## 11. Validation outcome vocabulary

| Failure | Required outcome |
|---|---|
| duplicate daily match or snapshot | database uniqueness error; retain the original row |
| missing/unavailable official market payload | explicit `UNAVAILABLE` plus reason; no fabricated odds |
| mismatched match/hash/role FK | reject or `BLOCKED`; open incident when admitted through a privileged path |
| post-kickoff or post-cutoff input | `FUTURE_INFORMATION_LEAKAGE`, `RUN_INVALID`, `TIER_A_ELIGIBLE=false` |
| frozen mutation | reject with `FROZEN_INPUT_MUTATION`/`FROZEN_PREDICTION_MUTATION` |
| duplicate active Production | `PRODUCTION_UNIQUENESS_FAILURE`; fail closed |
| Experiment in public/Tier A | `ROLE_VIOLATION`; reject and preserve audit/incident |
| failed/unknown critical security gate | deny by default; no fallback policy |
