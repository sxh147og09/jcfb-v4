# JCFB V4 V4-022 CUTOFF, TIMESTAMP & PROVENANCE LINEAGE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch/HEAD: `main` / `6473a1f` (`feat(v4-022): add cutoff time lineage gate`)

Implementation Status: `COMPLETE` for the V4-022 local, no-write implementation boundary

## Files Added/Changed

- `tools/canonical_intake/time_lineage.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_022/time_lineage_cases.json`
- `tests/unit/test_v4_022_time_lineage.py`
- `docs/V4_022_TIME_LINEAGE_IMPLEMENTATION.md`
- `docs/V4_022_ACCEPTANCE_EVIDENCE.json`
- V4 task-status documents updated to record V4-022 acceptance and V4-023 as the next task

## Time Lineage Contract

`time-lineage@1.0.0` consumes one V4-021 fact envelope by exact `fact_object_id`. The typed request and decision preserve:

- `source_timestamp`
- `source_published_at`
- `observed_at`
- `ingested_at`
- `availability_at`
- explicit `availability_time_basis`
- `prediction_cutoff_at`
- canonical `kickoff_at`
- V4-021 fact observation/object references
- source reference, provenance hash, and lineage hash

The source-time basis is explicit and must be one of `SOURCE_PUBLISHED_AT`, `SOURCE_TIMESTAMP`, or `OBSERVED_AT`. `ingested_at` is retained for audit only and is never used as a substitute for source availability.

## Availability-Time Policy

The selected `availability_at` comes only from the declared basis. Missing selected time, missing/ambiguous timezone, contradictory source ordering, or absent fact reference fails closed. Equivalent timezone representations are compared as timezone-aware instants and canonicalized to UTC for deterministic decision/provenance hashes.

## Cutoff and Kickoff Gate

For a formal pre-match input, V4-022 enforces:

```text
availability_at <= prediction_cutoff_at < kickoff_at
```

The outcomes are:

- `PREMATCH_ALLOWED` when the inequality passes and the V4-021 fact is `AVAILABLE`.
- `FUTURE_INFORMATION_LEAKAGE` when availability is after the declared cutoff but before kickoff, or the fact is explicitly `FUTURE_DATA`.
- `POSTMATCH_ONLY` when availability is at or after kickoff.
- `BLOCKED` for missing/invalid lineage, cutoff ordering, source-time ordering, reference mismatch, or non-eligible V4-021 fact status.

Future/post-match outcomes append the decision and set `future_information_leakage=true`, `run_invalid=true`, `tier_a_eligible=false`, and `promotion_evidence=false`. The offending fact and decision remain available for audit.

## Source/Provenance Rules

The V4-021 fact object supplies attributable `source` and `source_ref`; V4-022 verifies the exact fact object, observation reference, match identity, and optional source reference supplied by the caller. All source, publication, observation, ingestion, cutoff, kickoff, selected basis, and decision fields are retained. No page-build, generated, run, or ingestion time is promoted to source availability.

## Append-Only Boundary

`TimeLineageStore` retains immutable decisions and append-only events for accepted, blocked, future, post-match, and duplicate evaluations. Re-evaluation with a different cutoff/time lineage appends a distinct decision identity; identical evaluation produces a `DUPLICATE_NOOP` event without mutating the original decision. No update/delete API, migration, database adapter, Supabase connection, or V4-023 orchestrator was added.

## V4-021 and Role Boundary

V4-022 accepts only V4-021 `CanonicalFactStore` references. Non-`AVAILABLE` facts are not promoted into a formal pre-match path. The module does not run Prediction, Score Engine, Shadow, Public Page, Promotion, or any model interpretation.

## Acceptance

- Targeted V4-022 suite: `19/19 PASS`
- Full repository suite: recorded in `V4_022_ACCEPTANCE_EVIDENCE.json`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`

V4-022 DoD: `PASS`

V4-022 Status: `COMPLETE`

Next Recommended Task: `V4-023` only; V4-024 and later tasks remain outside this execution boundary.

Git Commit: `6473a1f` (`feat(v4-022): add cutoff time lineage gate`)
