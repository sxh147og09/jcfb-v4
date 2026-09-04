# JCFB V4 V4-028 EXTERNAL EUROPEAN 1X2 INTAKE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Task: `V4-028 — External European 1X2 Intake 1.0`

Implementation Status: `COMPLETE` for the local, in-memory, append-only external European 1X2 intake boundary.

## Files Added/Changed

- `tools/canonical_intake/external_market.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_028/external_european_1x2_cases.json`
- `tests/unit/test_v4_028_external_european_1x2.py`
- `docs/V4_028_EXTERNAL_EUROPEAN_1X2_INTAKE_IMPLEMENTATION.md`
- `docs/V4_028_ACCEPTANCE_EVIDENCE.json`

## External 1X2 Contract

The adapter accepts only `market=EUROPEAN_1X2`, requires `line=NOT_APPLICABLE`, and validates the typed `home`, `draw`, and `away` provider prices. It requires provider identity, source/source reference, explicit availability status, source/capture/observation/ingestion timestamps, source provenance confidence, payload/provenance hashes, and `source_is_official=false`.

All accepted observations must resolve to an existing V4-020 canonical `match_id` with `AVAILABLE` and `RESOLVED` identity state. Missing or unresolved identity returns a blocked result and creates no snapshot.

## Availability and Fail-Closed Rules

`AVAILABLE` requires a non-empty typed prices object. `UNKNOWN`, `UNAVAILABLE`, `CONFLICT`, `STALE`, `FUTURE_DATA`, and `BLOCKED` require an explicit uppercase `reason_code`; a null prices value is accepted only as an explicit non-AVAILABLE representation. No state is inferred from null, empty payload, missing source, or source time.

Model fields, official lottery fields, official source identity, malformed prices, and implicit line coercion are rejected.

## Append-Only and Provenance Boundary

The local store keeps immutable observations and snapshots. Duplicate observations return `DUPLICATE_NOOP`. Corrections append a new snapshot with `supersedes_snapshot_id`, a new revision, and new hashes; no update or delete operation exists. External snapshots never populate official lottery markets, official availability, or RQSPF.

## Scope and Safety

This task does not connect to an external live feed, write Production/Supabase, add or apply a migration, run Prediction/Score/Shadow/Public/Promotion, implement V4-029+, or modify V3.3.3. All test/output paths remain on the F drive.

## Acceptance

- Targeted V4-028 suite: `7/7 PASS`
- Full repository suite: recorded in `V4_028_ACCEPTANCE_EVIDENCE.json`
- External/official isolation: `PASS`
- V4-020 identity binding: `PASS`
- Append-only boundary: `PASS`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- V4-028 DoD: `PASS`
- V4-028 Status: `COMPLETE`

Next Task: `V4-029 — External Asian Handicap Intake 1.0`.
