# JCFB V4 V4-033 AVAILABILITY CONTEXT IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Task: `V4-033 — Availability, Injury & Suspension Intake 1.0`

Implementation Status: `COMPLETE` for the local, typed, cutoff-aware,
append-only availability context boundary.

## Files Added/Changed

- `tools/canonical_intake/team_context.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_033/availability_cases.json`
- `tests/unit/test_v4_033_availability_context.py`
- `docs/V4_033_AVAILABILITY_CONTEXT_IMPLEMENTATION.md`
- `docs/V4_033_ACCEPTANCE_EVIDENCE.json`

## Typed Availability Semantics

Injuries, suspensions, and availability are represented as independent
`TypedFactCollection` values. `UNKNOWN` omits `items`; it is never an empty
array or a claim of no absence. `NONE_CONFIRMED` permits `items=[]` only with
explicit basis references and a reason. `AVAILABLE` requires non-empty typed
items. `NOT_VERIFIED`, `CONFLICTED`, `STALE`, `FUTURE_DATA`, and `BLOCKED` stay
distinct and require reasons; conflict requires both claim references and
future data is rejected from the pre-match admitted record.

No default, zero, empty object, previous value, or silent status coercion is
used to cover missing availability information.

## Identity, Time, and Lineage

Each accepted record is bound to a resolved V4-020 canonical `match_id`,
canonical `team_id`, `HOME`/`AWAY` side, and an accepted V4-032 identity link.
The store validates source, source reference, source/observed/ingested/effective
times, cutoff, optional expiry, provenance, and `context_hash`/`payload_hash`.
The cutoff must precede kickoff; post-cutoff input and `FUTURE_DATA` are
blocked. A correction appends a new revision with `supersedes_object_id`,
leaving the prior record available for replay.

## Scope and Isolation

This task creates no Evidence Graph or conflict-resolution engine. Evidence is
represented only by basis/source references. It creates no feature,
recommendation, prediction, risk decision, or engine output, performs no
Production/Supabase or migration action, and does not modify V3.3.3.

## Acceptance

- Typed injury/suspension/availability collections: `PASS`
- UNKNOWN versus NONE_CONFIRMED semantics: `PASS`
- NOT_VERIFIED, STALE, FUTURE_DATA, CONFLICTED, and BLOCKED preservation: `PASS`
- Identity-link and canonical side binding: `PASS`
- Cutoff-before-kickoff and future-data fail-closed: `PASS`
- Source/provenance/hash lineage: `PASS`
- Append-only revision/supersedes: `PASS`
- Model/V3.3.3 isolation and F-drive boundary: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- V4-033 DoD: `PASS`
- V4-033 Status: `COMPLETE`

Next Task: `V4-034`.
