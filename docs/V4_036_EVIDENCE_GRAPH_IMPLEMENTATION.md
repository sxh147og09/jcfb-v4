# JCFB V4 V4-036 EVIDENCE GRAPH CLAIM & EVIDENCE MODEL IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch: `main`

Implementation Status: `COMPLETE` for the V4-036 local, append-only, no-write boundary

## Scope

V4-036 establishes the first independently addressable Evidence Graph boundary. It represents a structured claim, its canonical entity references, source identity, time scope, provenance/hash lineage, verification state, contradiction state, basis references, and append-only supersession lineage.

V4-037 source-quality assessment, expiry evaluation, and conflict resolution are intentionally implemented separately and are not included in this task.

## Files Added/Changed

- `tools/canonical_intake/evidence_graph.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_036/evidence_cases.json`
- `tests/unit/test_v4_036_evidence_graph.py`
- `docs/V4_036_EVIDENCE_GRAPH_IMPLEMENTATION.md`
- `docs/V4_036_ACCEPTANCE_EVIDENCE.json`

## Evidence Object Contract

`evidence@1.0.0` / `evidence-graph@1.0.0` provides:

- stable `evidence_id` and `claim_id`
- structured `claim` and `claim_type`
- canonical `entity_refs`, including a valid V4-020 `match_id`
- explicit source, source type, and replayable source reference
- published/retrieved/valid-from/expiry carrying fields and explicit unknown-time states
- typed source/evidence quality object
- separate `verification_state` and `contradiction_state`
- `evidence_hash`, `payload_hash`, and `provenance_hash`
- `basis_refs`
- `revision` and `supersedes_evidence_id`
- immutable metadata and append events

The object rejects model interpretation, feature, recommendation, prediction, engine, probability, risk, score-selection, Frozen Input, and V3.3.3 fields. The top-level `confidence` field is accepted only as the governed Evidence quality object; prediction confidence is rejected.

## Relationship and Identity Rules

- Every Evidence item must resolve `entity_refs.match_id` through an accepted V4-020 identity.
- An unresolved, missing, or mismatched canonical identity is blocked.
- Display names cannot replace canonical IDs.
- A revision must point to an existing predecessor in the same claim/match family and increment the predecessor revision by exactly one.
- Reusing an existing `evidence_id` with a different hash is blocked.
- Identical delivery is an auditable `DUPLICATE_NOOP`.

## Verification and Contradiction Boundary

Verification states are explicit: `VERIFIED`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`, and `REJECTED`.

Contradiction states are independent: `NONE`, `PENDING`, `CONFLICTED`, `RESOLVED`, and `NOT_APPLICABLE`.

The implementation retains source-side relation values (`SUPPORTS`, `CONTRADICTS`, `CORROBORATES`, `NEUTRAL`) and basis references. It does not silently convert a claim to trusted context. Competing evidence is retained as separate immutable objects for V4-037 conflict handling.

## Hash and Time Rules

Payload hash covers the structured claim, canonical entity references, and evidence relation. Provenance hash covers source identity, source reference, published/retrieved/valid-from/expiry fields and their explicit state. Evidence hash covers the evidence identity, claim, relationship, hashes, confidence quality, lifecycle states, basis references, and supersession lineage.

The module carries time fields and explicit unknown-time states. Full cutoff admission and source-time selection remain V4-022 responsibilities.

## Append-only Boundary

The local `EvidenceGraphStore` has no update or delete API. Accepted revisions append a new Evidence item and event; predecessors remain addressable. Validation blocks and duplicate deliveries are retained as events. No persistence adapter, migration, Supabase connection, Feature, Prediction, Score Engine, Shadow, Public Page, or Promotion path was added.

## Acceptance Evidence

- Targeted V4-036 tests: `8/8 PASS`
- Full repository tests after implementation: `323/323 PASS`
- canonical identity binding: `PASS`
- source/claim/basis/time/hash lineage: `PASS`
- state and model-field fail-closed validation: `PASS`
- append-only revision and duplicate behavior: `PASS`
- F-drive policy: `PASS`
- V3.3.3 isolation: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- BATCH-10 / V4-038+ execution: `NO`

V4-036 DoD: `PASS`

V4-036 Status: `COMPLETE`

Git commit: recorded in `V4_036_ACCEPTANCE_EVIDENCE.json`

Next approved task: `V4-037` only.
