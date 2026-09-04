# JCFB V4 V4-029 EXTERNAL ASIAN HANDICAP INTAKE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Task: `V4-029 — External Asian Handicap Intake 1.0`

Implementation Status: `COMPLETE` for the local, in-memory, append-only external Asian Handicap intake boundary.

## Files Added/Changed

- `tools/canonical_intake/external_market.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_029/external_asian_handicap_cases.json`
- `tests/unit/test_v4_029_external_asian_handicap.py`
- `docs/V4_029_EXTERNAL_ASIAN_HANDICAP_INTAKE_IMPLEMENTATION.md`
- `docs/V4_029_ACCEPTANCE_EVIDENCE.json`

## Asian Handicap Contract

The adapter accepts only `market=ASIAN_HANDICAP`, requires a typed numeric handicap `line`, and validates typed positive `home` and `away` provider prices. It requires provider identity, source/source reference, explicit availability status, source/capture/observation/ingestion timestamps, source provenance confidence, payload/provenance hashes, and `source_is_official=false`.

Missing or unavailable handicap lines are represented by an explicit `UNKNOWN` or `CONFLICTED` line state together with a non-AVAILABLE status and reason. Numeric strings and default lines are rejected; no line coercion or invention occurs.

## Official Isolation and Identity

Accepted observations resolve to an existing V4-020 canonical `match_id` with `AVAILABLE` and `RESOLVED` identity state. The adapter rejects official lottery fields and never creates an official RQSPF payload. External Asian Handicap data remains a separate attributed market fact.

## Availability and Append-Only Boundary

`AVAILABLE` requires non-empty typed prices. `UNKNOWN`, `UNAVAILABLE`, `CONFLICT`, `STALE`, `FUTURE_DATA`, and `BLOCKED` require explicit reason codes. A correction appends a new snapshot with `supersedes_snapshot_id`, incremented revision, and new hashes while retaining its predecessor. Duplicate observations are no-ops.

## Scope and Safety

This task does not connect to a live provider, write Production/Supabase, add or apply a migration, run Prediction/Score/Shadow/Public/Promotion, implement V4-030+, or modify V3.3.3. All test/output paths remain on the F drive.

## Acceptance

- Targeted V4-029 suite: `7/7 PASS`
- Full repository suite: recorded in `V4_029_ACCEPTANCE_EVIDENCE.json`
- External/official isolation: `PASS`
- V4-020 identity binding: `PASS`
- Explicit line and price semantics: `PASS`
- Append-only correction boundary: `PASS`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- V4-029 DoD: `PASS`
- V4-029 Status: `COMPLETE`

Next Task: `V4-030 — External O/U Intake 1.0`.
