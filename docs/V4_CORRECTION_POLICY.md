# JCFB V4 Correction Policy 1.0

Status: V4-005 COMPLETE

## 1. Purpose

This policy distinguishes correction of objective data from revision of a pre-match prediction. It protects auditability, Frozen Input, Frozen Prediction, evaluation integrity, and model history.

## 2. Core rule

Objective data may be corrected only through an explicit, auditable, append-only path. A Frozen Input or Frozen Prediction is never edited in place. A corrected source observation creates a new canonical revision and a new downstream run identity where needed.

## 3. Correctable facts

### `CORRECTABLE`

The following may be corrected when evidence supports the change:

- team spelling
- competition spelling
- timezone normalization
- confirmed source correction
- duplicate metadata

The correction must preserve before, after, reason, actor, timestamp, source reference, and the resulting fact hash. If the correction affects a run that has already frozen, the old snapshot remains unchanged and the correction is a new canonical revision.

## 4. Append-revision-required facts

### `APPEND_REVISION_REQUIRED`

The following require a new canonical revision rather than an in-place replacement:

- official handicap correction
- official kickoff correction
- odds source correction
- market availability correction

The system records the old value, new value, source, source timestamp, observed time, reason, actor, correction time, and new hash. Any new model run uses a new `input_hash` and, where applicable, a new `frozen_input_hash`.

## 5. Prediction revisions

A genuine pre-match need for a new prediction creates a new prediction revision before the applicable freeze boundary. The new record includes `supersedes_prediction_id`, its own model/config/input/output hashes, and the reason. Earlier revisions remain immutable.

### `NEVER_CORRECT_HISTORY`

The following may never be corrected in place:

- Frozen Prediction direction
- model probability
- score prediction
- confidence
- risk or abstention decision
- postmatch hit result to improve KPI

A wrong Frozen Prediction remains wrong in the historical record. A later model change is a new version with new forward evidence, not a correction to history.

## 6. Correction workflow

1. Open a correction record with the affected identity and evidence.
2. Classify the request as `CORRECTABLE`, `APPEND_REVISION_REQUIRED`, or `NEVER_CORRECT_HISTORY`.
3. Validate source, time, identity, and conflict state.
4. Record before and after values without deleting the old record.
5. Generate a new fact hash and canonical revision when required.
6. Determine whether downstream features or runs require a new input identity.
7. Keep all prior Frozen Input and Frozen Prediction records unchanged.
8. Record the audit event and reviewer decision.

## 7. Result and evaluation corrections

Official Result must match Canonical Match Identity. If an official result is corrected, the result path appends a new result revision with source, before, after, reason, actor, timestamp, and hash. Historical evaluation output is not silently overwritten; any re-evaluation is explicitly identified as a new evaluation revision and cannot be used to erase the original outcome.

## 8. Correction audit fields

Every correction record supports:

```text
correction_id
entity_type
entity_id
field
before
after
reason
source
source_reference
source_timestamp
observed_at
actor
corrected_at
previous_hash
new_hash
supersedes_id when applicable
```

## 9. Forbidden correction behavior

- updating a Frozen Prediction to match the result
- changing historical probabilities or Score Top2
- changing historical market interpretation after seeing the outcome
- deleting old evidence or old snapshots
- backfilling an unrun Shadow Output
- excluding a failed match after promotion review starts
- changing a model parameter without a new version and new evidence

## 10. Correction and public read projection

The public projection may publish a new canonical latest revision only after the underlying correction and audit gates pass. It cannot rewrite an immutable prediction or use page build time as evidence of a business-data correction.
