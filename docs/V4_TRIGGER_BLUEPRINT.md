# JCFB V4 Trigger Blueprint 1.0

Status: V4-010 TRIGGER AND FUNCTION DESIGN (DESIGN-ONLY)

This document defines the future database enforcement strategy. It is not an implementation and no trigger/function is installed by V4-010. The companion SQL contains candidate names and DDL shapes only.

## 1. Trigger principles

1. Reject unsafe writes before the protected row changes. Do not silently repair a wrong match, role, time, or hash.
2. Audit successful inserts, approved registry metadata updates, corrections, promotions, pointer changes, withdrawals, and incident transitions.
3. An append-only trigger is not a substitute for RLS/grants. Both layers are required.
4. Any function that cannot prove a required identity, source time, role, hash, or gate returns a failure and leaves the operation ineligible.
5. The database never fabricates canonical hashes. It validates format and declared algorithm/profile; canonical bytes and SHA-256 recomputation must be supplied by the approved versioned implementation.

## 2. Function catalog

| Function | Security/timing | Contract |
|---|---|---|
| `governance.is_v4_hash(text)` | `SECURITY INVOKER`, immutable format helper | Accept only `sha256:<64 lowercase hex>`. It does not calculate a hash. |
| `governance.reject_append_only_mutation()` | `BEFORE UPDATE OR DELETE` | Raise a stable error code for protected history. |
| `governance.protect_frozen_input_mutation()` | `BEFORE UPDATE OR DELETE` | Allow only approved pre-freeze Draft changes; reject any mutation after `FROZEN` or `immutable=true`, and protect identity/hash/cutoff fields. |
| `governance.guard_registry_update()` | `BEFORE UPDATE` | Permit only approved status/active/effective/retirement metadata with a controlled writer context; reject role/version/hash/payload changes; update `updated_at`. |
| `governance.validate_revision_chain()` | `BEFORE INSERT` / deferred constraint trigger | Same family/lineage, predecessor exists, predecessor revision is lower, no self/cycle/forward pointer, correction reason and actor/time evidence present. |
| `governance.validate_source_separation()` | `BEFORE INSERT` | Official rows are official; external rows are non-official; source type/reference and evidence rules agree. |
| `governance.validate_market_payload()` | `BEFORE INSERT` | Exactly five official market keys; available market has payload, unavailable market has reason and no fabricated payload; price/line ranges are valid. |
| `governance.validate_frozen_input_lineage()` | `BEFORE INSERT` and deferred after selection rows | Exact IDs/hashes, same match, selected source availability <= cutoff, no forbidden postmatch references, approved registry identities, and Freeze Gate conditions. |
| `governance.validate_runtime_lineage()` | `BEFORE INSERT`/completion transition | Feature/Engine/Prediction parent match, role, version, frozen hash, input/output hash and time agreement; no successful output for an invalid run. |
| `governance.validate_prediction_engine_membership()` | `BEFORE INSERT` | Prediction/run same match and compatible role; output hash equality; allowed market/purpose/order. |
| `governance.validate_frozen_prediction_lineage()` | `BEFORE INSERT` | Prediction/Input same match, role, hashes, cutoff/kickoff; freeze before kickoff; snapshot hash is recomputable by the approved canonicalization implementation. |
| `governance.validate_prematch_gate()` | deferred constraint trigger | Fail closed on unknown time, post-cutoff/post-kickoff source, result/postmatch reference, leakage flag, unresolved hash/ref, or invalid run. |
| `governance.validate_review_scope()` | `BEFORE INSERT` | Review Result/Frozen Prediction same match; Model Evaluation excludes postmatch evidence; Explanation cannot write evaluation facts. |
| `governance.validate_tier_a_pair()` | deferred constraint trigger | Production/Shadow same match and Frozen Input hash, distinct roles, both pre-kickoff, complete hashes, result/review valid, no Experiment. |
| `governance.validate_production_release()` | activation function/transaction | Candidate is a new Production identity with Promotion Review/manual approval; one active family/channel; no role conversion. |
| `governance.validate_public_projection()` | `BEFORE INSERT` | Only Production active release/prediction/freeze/official odds, safe columns, and copied real business timestamps; no Shadow/Experiment/raw payload. |
| `governance.append_audit_event()` | controlled backend path/after successful operation | Requires actor/action/entity/before/after/metadata/time/prev_hash/entry_hash; serializes the chain and excludes audit recursion. |
| `governance.validate_incident_scope()` | `BEFORE INSERT` | Allowed incident class/entity family, role/match scope, before/after evidence, revision chain, no secret material. |

The complex functions are intentionally named contracts. Their canonical hash portion is a TODO implementation decision and may not be replaced with a placeholder digest.

## 3. Append-only enforcement matrix

### 3.1 Strict `INSERT`-only history

The following tables receive `BEFORE UPDATE OR DELETE` `governance.reject_append_only_mutation()` and an `AFTER INSERT` audit event (with an audit recursion guard):

- `market.official_odds_snapshots`;
- `market.external_market_snapshots`;
- formal `context.team_context_snapshots`;
- `context.evidence_items`;
- `context.team_context_evidence`;
- `context.evidence_bundles` and `context.evidence_bundle_items`;
- `model.feature_bundles` once used by a formal run;
- `model.engine_runs`;
- `model.predictions` and `model.prediction_engine_runs`;
- `model.frozen_predictions`;
- `evaluation.official_results`;
- `evaluation.postmatch_reviews`;
- `evaluation.tier_a_samples` and `evaluation.tier_a_run_members`;
- `evaluation.promotion_reviews` and `evaluation.promotion_review_samples`;
- `evaluation.calibration_records`;
- `governance.release_pointer_events`;
- `governance.incidents`;
- `governance.audit_logs`;
- formal `public.public_read_projections`.

The trigger does not provide a privileged bypass to runtime roles. A correction is a new row with a new revision, `supersedes_*_id`, reason, actor/time evidence, and new hashes.

### 3.2 Frozen Input state boundary

`model.frozen_inputs` has a dedicated trigger:

- `DRAFT` rows may be changed only through the Freeze Gate writer before they are referenced by a formal run;
- once `status='FROZEN'` or `immutable=true`, all updates/deletes are rejected;
- even before freeze, `match_id`, revision identity, role scope, selected hash fields, and predecessor identity cannot be changed casually;
- a source correction after freeze creates a new Frozen Input identity/revision and preserves the old row;
- an update cannot set `immutable=false`, clear a leakage flag, or raise `tier_a_eligible` without a full gate validation;
- every accepted freeze writes a `FREEZE` audit event.

### 3.3 Controlled registry updates

`governance.model_versions` and `governance.engine_versions` may receive only an approved metadata update:

- allowed fields: `status`, `is_canonical_active`, `effective_at`, `retired_at`, `retirement_reason`, approval metadata, and `updated_at`;
- forbidden fields after insert: ID, family/name/version components, role, revision, model/engine link, schema/dataset/migration identity, implementation/config/hash fields;
- the writer must hold the registry boundary and set a transaction-local approved context;
- activation also writes an append-only pointer event, predecessor/successor evidence, and an audit event;
- a role or hash change is rejected and requires a new registry identity.

There is no direct status update path for a runtime role to turn Shadow/Experiment into Production.

## 4. Immutability and revision triggers

### 4.1 Frozen Prediction

`model.frozen_predictions` is permanently immutable. A trigger rejects every UPDATE/DELETE, including attempts that set a field to its existing value. A correction or new pre-match revision inserts a new Frozen Prediction with a new `freeze_revision`, new hash, reason, actor, and `supersedes_frozen_prediction_id`.

### 4.2 Official Result

`evaluation.official_results` is INSERT-only. A correction insert must satisfy:

```text
new.match_id = predecessor.match_id
new.result_lineage_id = predecessor.result_lineage_id
new.result_revision > predecessor.result_revision
new.supersedes_result_id = predecessor.result_id
new.result_hash != predecessor.result_hash when logical result changed
correction reason + actor + source/time evidence are present
```

The current result is derived as the terminal row with no successor; a mutable `is_current` flag is not required.

### 4.3 Postmatch Review

Review corrections are INSERT-only with `supersedes_review_id`, same match/Frozen Prediction scope, a higher `review_revision`, new review hash, and explicit reason. The correction cannot mutate a Frozen Prediction, Result, prior review, KPI, or Promotion evidence. Model Evaluation and Match Explanation remain separate histories.

### 4.4 Promotion and Calibration evidence

Promotion Review, promotion sample membership, and Calibration records are INSERT-only. Changing a sample scope, metric, approval, or evidence set creates a new revision/event; an existing evidence row cannot be overwritten. `auto_promotion=true` is always rejected.

### 4.5 Snapshot and context corrections

Official and external market snapshot corrections, and formal Team Context corrections, are new immutable rows with a predecessor pointer, higher governed revision/identity, new hashes, and correction evidence. `supersedes_snapshot_id` cannot change the source class or turn an external row into official odds. Context-to-evidence membership is also append-only; a changed source set creates a new context revision or new membership evidence and never edits the prior row.

## 5. Role and cross-entity triggers

### 5.1 Role immutability

All role-owned tables validate explicit role on insert and reject any role change. Registry role, run role, Prediction role, Frozen Prediction role, and Tier A member role must agree. A missing role is `BLOCKED`/`NOT_AUDITABLE`, never inferred from a schema or path.

### 5.2 Same-match enforcement

Deferred relationship triggers compare the redundant typed `match_id` columns and parent rows:

```text
feature.frozen_input.match_id = feature.match_id
engine_run.frozen_input.match_id = engine_run.feature_bundle.match_id = engine_run.match_id
prediction.frozen_input.match_id = prediction.match_id
prediction_engine_run.prediction.match_id = engine_run.match_id
frozen_prediction.prediction.match_id = frozen_prediction.match_id
review.frozen_prediction.match_id = review.result.match_id = review.match_id
tier_a.production.match_id = tier_a.shadow.match_id = tier_a.match_id
projection.match_id = projection.production_frozen_prediction.match_id
team_context_evidence.team_context.match_id = team_context_evidence.evidence.match_id when both scopes are present
```

Any mismatch is rejected. A generic `entity_id` text field in an Incident/Audit row cannot satisfy a same-match relationship.

### 5.3 Same Frozen Input A/B

`governance.validate_tier_a_pair()` requires:

```text
production.role = PRODUCTION
shadow.role = SHADOW
production.match_id = shadow.match_id = tier_a.match_id
production.frozen_input_id = shadow.frozen_input_id = tier_a.frozen_input_id
production.frozen_input_hash = shadow.frozen_input_hash = tier_a.frozen_input_hash
production.prediction_cutoff_at = shadow.prediction_cutoff_at
production.kickoff_at = shadow.kickoff_at
production_completed_at < kickoff_at
shadow_completed_at < kickoff_at
```

`input_hash` and `output_hash` remain distinct role-specific identities. An Experiment member is always rejected, even when its hash happens to match.

## 6. Timestamp and no-future trigger

`governance.validate_prematch_gate()` runs at Frozen Input validation, Feature Bundle validation, Engine Run completion, Prediction formation, Frozen Prediction formation, and Tier A registration. It fails closed unless:

```text
all selected availability_at <= prediction_cutoff_at
AND prediction_cutoff_at < kickoff_at
AND model_run_at < kickoff_at
AND run_completed_at < kickoff_at when forward eligibility is claimed
AND frozen_at < kickoff_at when frozen
AND future_information_leakage = FALSE
AND run_invalid = FALSE
AND no result/event/postmatch evidence is in the pre-match reference set
AND all selected IDs, versions, and hashes resolve exactly
```

If a violation is intentionally persisted for incident evidence, it must be `BLOCKED`/`INVALID` with `future_information_leakage=true`, `run_invalid=true`, `tier_a_eligible=false`, and `promotion_evidence=false`. The trigger never flips a bad row into a good row.

## 7. Official/external market trigger

`governance.validate_source_separation()` and `validate_market_payload()` enforce:

- official snapshots have `source_is_official=true` and official source types;
- external snapshots have `source_is_official=false` and provider identity;
- external price/handicap payload cannot satisfy the official odds relationship;
- unavailable official markets carry `available=false`, a governed `UNAVAILABLE` status, a non-empty reason, and no fake payload;
- available official markets carry their typed/structured payload and valid positive prices;
- unknown or unreadable markets remain `UNKNOWN`/`NOT_VERIFIED`/`BLOCKED`.

## 8. Audit trigger and chain

Every successful critical event produces one audit row containing:

```text
actor
action
entity_type
entity_id
before_state
after_state
metadata
happened_at
prev_hash
entry_hash
```

Required events include source intake, canonical identity resolution, snapshot/context/evidence intake, validation/gate rejection, Freeze, feature generation, run creation/completion/failure, Prediction/Frozen Prediction, result intake/correction, Review, Tier A registration/rejection, Promotion, release activation/retirement/rollback, calibration, incident lifecycle, and public publication/withdrawal.

The append function obtains a per-stream lock or uses a serializable transaction, reads the last `entry_hash`, requires it as `prev_hash`, and inserts the new row with a caller-supplied canonical `entry_hash`. The function must not invent a digest. `audit_logs` is excluded from its own row-change audit trigger to avoid recursion; audit row insertion itself is append-only and validated.

A trigger that raises an exception cannot commit a failure audit row in the same rolled-back transaction. Therefore the controlled service must record rejected-attempt telemetry/audit in a separate transaction or external incident channel after the database rejection; the protected predecessor remains unchanged.

## 9. Fail-closed and rollback behavior

- Missing gate function, missing canonicalizer, missing time, unresolved FK, ambiguous role, or absent audit context blocks the write.
- Trigger order is: source/shape checks, direct constraints, lineage/cross-match checks, time gate, role/public checks, then audit append.
- Deferred constraints are used for normalized child inserts that are valid only after their parent selection set is complete.
- Production rollback uses a new Production release identity and pointer event; it never deletes or reactivates historical rows in place.
- No trigger or function may read, write, import, or expose V3.3.3 artifacts.
