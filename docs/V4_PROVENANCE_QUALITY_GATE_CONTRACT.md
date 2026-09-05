# JCFB V4 Provenance & Quality Gate Contract 1.0

Status: **BATCH-14 ARCHITECTURE GOVERNANCE / ACTIVE**  
Contract version: `provenance-quality-gate@1.0.0`  
Lifecycle: **PRE_PREDICTION_PRE_FREEZE**

## 1. Purpose and boundary

This contract governs the V4-051 Pre-Freeze Quality Gate Record. It binds the
quality assessment and upstream feature artifacts to a versioned, replayable,
append-only gate decision. It is a preparation gate, not a Prediction
Abstention Engine, Prediction, Score Engine, Frozen Input, or recommendation.

## 2. Required gate record

The active record kind is `PRE_FREEZE_QUALITY_GATE_RECORD` and must include:

```text
gate_record_id
contract_version
config_version / config_hash
gating_matrix_version / gating_matrix_hash
reason_registry_version / reason_registry_hash
match_id / canonical_entity_refs
prediction_cutoff_at / kickoff_at
assessment_input_refs / assessment_input_hashes
v4_049_refs / v4_049_hashes
v4_050_refs / v4_050_hashes
feature_eligibility_records
domain_eligibility_records
overall_gate_state
blockers[]
warning_nonblocking_reasons[]
evidence_refs / provenance_refs
input_hash / payload_hash / provenance_hash / output_hash
revision
supersedes_gate_record_id
```

The exact values of `overall_gate_state` are those in
`feature-eligibility@1.0.0`: `ELIGIBLE`, `PARTIALLY_ELIGIBLE`, `INELIGIBLE`,
or `BLOCKED`.

## 3. Hard and non-hard behavior

Every hard blocker from `quality-gate-matrix@1.0.0` must propagate with its
stable reason code and affected lineage. The gate must preserve the difference
between feature, domain, and candidate-set decisions.

Non-hard states remain explicit. `UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`,
`STALE`, and unresolved `CONFLICTED` inputs cannot be silently converted to
`AVAILABLE`; only the approved matrix may determine their eligibility level.

## 4. Provenance and hash boundary

The gate hash includes exact upstream IDs, revisions, hashes, typed states,
cutoff/kickoff, contract versions, config/matrix/reason-registry versions and
hashes, implementation/generator identity, and the complete decision payload.
Transport metadata is excluded only when explicitly declared volatile by the
V4 canonical hash profile.

Equal logical inputs and identities must replay to the same gate decision and
hash. A changed accepted input, matrix, reason registry, configuration, or
implementation creates a new identity and revision.

## 5. Append-only and downstream boundary

Gate records are append-only. Corrections append a new record with a new hash,
revision, reason, and `supersedes_gate_record_id`; the prior record is never
overwritten or removed.

V4-076 may later reference this gate record, its hash, and eligible/rejected
feature references. BATCH-14 does not create Frozen Input or claim final
Frozen Input eligibility.

The gate cannot emit or contain:

```text
prediction, recommendation, model_confidence, win_probability,
betting_confidence, risk_decision, abstention_decision, engine_output,
frozen_input_id, frozen_input_hash
```
