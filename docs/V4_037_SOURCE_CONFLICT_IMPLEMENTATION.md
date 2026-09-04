# JCFB V4 V4-037 SOURCE QUALITY, EXPIRY & CONFLICT RESOLVER IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch: `main`

Implementation Status: `COMPLETE` for the V4-037 local, append-only, no-write boundary

## Scope

V4-037 consumes the V4-036 `EvidenceGraphStore` and adds source-quality assessment, expiry/future-data evaluation, contradiction detection, and an explicit conflict-resolution record. It never rewrites or deletes Evidence items and does not invent an authoritative source precedence rule.

## Files Added/Changed

- `tools/canonical_intake/source_conflict.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_037/source_conflict_cases.json`
- `tests/unit/test_v4_037_source_conflict.py`
- `docs/V4_037_SOURCE_CONFLICT_IMPLEMENTATION.md`
- `docs/V4_037_ACCEPTANCE_EVIDENCE.json`

## Source Quality Boundary

`SourceQualityAssessment` is an independently addressed, append-only quality record. It carries a quality band, explicit quality basis, assessor, assessment time, revision, supersession reference, and quality hash.

The quality band is evidence/source quality only: `HIGH`, `MEDIUM`, `LOW`, or `UNKNOWN`. It is not a source-precedence order and cannot be interpreted as prediction probability, model confidence, recommendation grade, or betting confidence.

Quality changes append a new assessment revision. The predecessor remains in the quality history.

## Expiry and Future-Data Boundary

The resolver evaluates evidence against an explicit `as_of` time and optional cutoff/kickoff times:

- missing `valid_from` remains `UNKNOWN_TIME` and is ineligible;
- `valid_from` after `as_of` is `FUTURE_DATA`;
- an expired item is `STALE` and remains auditable;
- invalid cutoff/kickoff ordering is `BLOCKED`;
- a valid-from or retrieved time after cutoff is not eligible at cutoff;
- `NOT_VERIFIED`, `REJECTED`, and stale verification states remain blocked;
- unknown source quality remains blocked from trusted use.

The resolver does not replace V4-022's canonical time-lineage gate.

## Conflict and Resolution Boundary

All Evidence items for a claim remain in the graph. Different claim payloads, explicit `CONTRADICTS` relations, or conflicted/pending contradiction state produce `CONFLICTED` until an explicit resolution record exists.

Resolution requires:

- a stable resolution ID;
- the complete retained Evidence set for the claim;
- basis Evidence references;
- an explicit reason;
- actor and resolved time;
- policy reference;
- optional selected Evidence ID only when it is inside the retained set.

There is no automatic source ranking or silent authoritative override. A selected Evidence record is an explicit, auditable resolution outcome; competing Evidence remains immutable and queryable.

## Append-only and Isolation Rules

- Evidence is consumed through V4-036 and never updated or deleted.
- Quality changes append a new assessment with `supersedes_assessment_id`.
- Conflict resolution is an additional audit record and does not erase contradiction history.
- No synthetic claim, default value, source substitution, or status coercion is performed.
- No Feature, Market Intelligence, Prediction, Score Engine, Shadow, Public Page, Promotion, or BATCH-10 output was created.
- No migration, persistence adapter, Supabase connection, or Production access was added.

## Acceptance Evidence

- Targeted V4-037 tests: `5/5 PASS`
- Full repository tests after implementation: `328/328 PASS`
- source quality assessment and append-only revision: `PASS`
- expiry, unknown-time, future-data, and cutoff checks: `PASS`
- conflict preservation and explicit resolution: `PASS`
- no silent source selection: `PASS`
- source confidence / prediction confidence separation: `PASS`
- F-drive policy: `PASS`
- V3.3.3 isolation: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`

V4-037 DoD: `PASS`

V4-037 Status: `COMPLETE`

Git commit: recorded in `V4_037_ACCEPTANCE_EVIDENCE.json`

Next step: BATCH-09 Closure Review only. BATCH-10 remains out of scope.
