# JCFB V4 Append-Only Policy 1.0

Status: V4-009 APPEND-ONLY GOVERNANCE DESIGN ARTIFACT

## 1. Core rule

Audit-critical V4 history is append-only. Once a formal record is accepted, hashed, frozen, evaluated, or used as evidence, its original payload, identity, role, timestamps, and hashes remain available forever under normal model maintenance.

An update request is therefore classified as:

1. a new immutable revision with a direct `supersedes_*_id` pointer;
2. a correction/event record that describes before and after state; or
3. a permitted non-historical registry/pointer update accompanied by an audit event.

It is never a silent overwrite.

## 2. Mandatory APPEND_ONLY entities

The following entities are APPEND_ONLY in their formal/audit-critical form:

- `official_odds_snapshots`;
- `external_market_snapshots`;
- formal `team_context_snapshots`;
- `evidence_items` (corrections use a new revision or status/correction event);
- `frozen_inputs`;
- `engine_runs`;
- formal `predictions`;
- `frozen_predictions`;
- `official_results` (correction is a new result revision);
- `postmatch_reviews`;
- `tier_a_samples`;
- `promotion_reviews`;
- `calibration_records`;
- `incidents`;
- `audit_logs`.

The following are also append-only when they represent a formal publication or release history: `model_versions`, `engine_versions`, active-release pointer events, and `public_read_projections`.

## 3. Immutable versus revisioned artifacts

| Artifact | After acceptance | Legal correction path |
|---|---|---|
| Official/external snapshot | immutable source observation | new snapshot, new hash, `supersedes_snapshot_id`, reason and source evidence |
| Team Context | immutable formal context snapshot | new context revision; preserve prior state and cutoff |
| Evidence Item | immutable claim/provenance record | new item with `supersedes_evidence_id` or correction event; retain contradiction history |
| Evidence Bundle | immutable membership/cutoff selection | new bundle revision; never edit membership used by a Frozen Input |
| Frozen Input | immutable after `FROZEN` | new `frozen_input_id/revision` and `supersedes_frozen_input_id`; old input remains replayable |
| Engine Run | immutable envelope and payload | new run identity; failed/invalid run remains evidence |
| Prediction | immutable formal run result | pre-match replacement only as a new prediction revision; no post-result KPI correction |
| Frozen Prediction | write-once snapshot | new pre-match freeze revision only when permitted; never change old snapshot |
| Official Result | immutable result revision | new result revision with before/after correction evidence |
| Postmatch Review | immutable evaluation/explanation artifact | new review revision only for factual entry correction; never improve KPI by editing history |
| Tier A Sample | immutable qualification decision | new sample/correction event; do not relabel failed evidence |
| Promotion Review | immutable decision/evidence package | new review revision or withdrawal event; no silent status mutation |
| Calibration Record | immutable metric calculation | new calculation/revision with exact scope and input identities |
| Incident | immutable incident history | append status transition, containment, recovery, or closure event |
| Audit Log | immutable chain entry | append a correction/audit event; never edit or remove a prior entry |

## 4. Revision and supersedes contract

Every revisioned entity uses:

```text
entity_id                 new UUID/UUIDv7
entity_revision           immutable sequence or qualified revision
supersedes_entity_id      immediate predecessor or NOT_APPLICABLE at root
revision_reason           typed reason code plus human explanation
revision_actor            authenticated actor/service identity
revision_at               timezone-aware event time
previous_hash             predecessor hash when applicable
new_hash                  hash of the new logical payload
```

The chain is complete and navigable:

```text
current -> supersedes -> previous -> ... -> root
```

The old record is never deleted, detached, or made to point to a future revision. A current pointer is optional convenience metadata; it cannot replace the chain.

## 5. Required revision chains

### Frozen Input

A changed accepted source, cutoff, match identity, feature schema, version registry reference, or A/B boundary creates a new Frozen Input revision and a new `frozen_input_hash`. Existing Engine Runs and Predictions continue to point to the original input. No new run may reuse the old input hash for changed content.

### Prediction

A genuine pre-match replacement creates a new `prediction_revision` with `supersedes_prediction_id`, new input/output/prediction hashes, reason, actor, and time. A historical prediction cannot be changed after kickoff/result merely because it was wrong.

### Frozen Prediction

Frozen Prediction is immutable. If an applicable pre-kickoff freeze correction is allowed by governance, append a new Frozen Prediction with a new `freeze_revision`, exact new snapshot hash, supersession pointer, and correction reason. After the freeze boundary/result, the old frozen snapshot remains the evaluated historical record.

### Official Result

An official correction appends a result revision with `supersedes_result_id`, result hash, source reference, before/after values, reason, actor, and time. A downstream re-evaluation is a new Review revision; the original review remains visible and cannot be replaced by the corrected score.

### Postmatch Review

Only a factual entry error may be corrected. The new review must state the exact corrected field and preserve original evaluation inputs and historical output. A new result or changed interpretation is not a license to alter old metrics, sample qualification, or promotion evidence.

### Model/Engine release identity

A model or engine change creates a new role-scoped registry row and revision with `supersedes_model_version_id` or `supersedes_engine_version_id`, new implementation/config/schema identity as applicable, approval/evidence refs, and an effective time. A Shadow/Experiment row is not renamed into Production. Production activation appends a new release/pointer event.

## 6. State transitions are events

State changes for append-only entities are recorded by one of:

- an immutable new revision containing the new state;
- a typed transition event linked to the immutable entity;
- an append-only pointer/registry event for non-historical control state.

The event includes actor, reason, predecessor state, successor state, time, evidence, and hash-chain references. A mutable `status` column may be a derived read projection, but it is not the only history.

Examples:

```text
Promotion Review OPEN -> APPROVED
  requires gates, manual approval, production_release_id, audit event

Incident OPEN -> MITIGATED -> RESOLVED -> CLOSED
  requires containment, evidence preservation, owner, and closure criteria

Production pointer A -> B
  append activation event that supersedes A; never overwrite A's release history
```

## 7. Limited UPDATE exceptions

In-place UPDATE is allowed only for non-historical metadata that is not part of a formal payload or identity, such as:

- a registry's current pointer/lease, with an append-only pointer event;
- an operational ingestion cursor or retry counter outside formal records;
- a rebuildable cache or materialized projection marker;
- display metadata that cannot alter source truth or public business timestamps.

Every exception must pass:

1. explicit allow-list classification;
2. actor and authorization check;
3. before/after audit event;
4. no change to identity, hash, role, source time, cutoff, kickoff, result, output, or qualification;
5. ability to reconstruct the pre-update state from the event log.

No update exception permits a model output, Frozen Input, Frozen Prediction, evaluation, Tier A, incident, or audit entry to be overwritten.

## 8. Delete policy

Default: `NO HARD DELETE` for audit-critical records. Failed, blocked, conflicted, stale, superseded, invalid, rejected, and withdrawn records remain queryable under their status.

If GDPR, security containment, or another binding legal requirement later forces deletion, it must use a separate compliance workflow with documented scope, data-minimization decision, authorized actor, reason, time, tombstone or deletion evidence, affected hash-chain impact, and independent audit. It is not ordinary model maintenance and cannot be performed by a runtime role.

## 9. Future database enforcement

A future Postgres/Supabase implementation should enforce this policy with:

- insert-only privileges for audit-critical tables;
- denial of `UPDATE`/`DELETE` to runtime roles;
- triggers that reject mutation after formal acceptance/freeze;
- immutable hash and supersedes checks;
- state transition functions that append events;
- foreign keys and same-match checks;
- one active Production pointer constraint;
- audit events for every permitted pointer/metadata update.

No trigger, table, policy, or migration is created in V4-009.

## 10. V3.3.3 protection

This policy applies only to V4. It does not permit copying, correcting, deleting, or re-hashing any JCFB V3.3.3 record. V3.3.3 history remains outside the V4 persistence boundary.
