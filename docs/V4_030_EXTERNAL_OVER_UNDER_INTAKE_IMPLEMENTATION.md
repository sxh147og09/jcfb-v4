# JCFB V4 V4-030 EXTERNAL OVER/UNDER INTAKE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Task: `V4-030 — External O/U Intake 1.0`

Implementation Status: `COMPLETE` for the local, in-memory, append-only external Over/Under intake boundary.

## Files Added/Changed

- `tools/canonical_intake/external_market.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_030/external_over_under_cases.json`
- `tests/unit/test_v4_030_external_over_under.py`
- `docs/V4_030_EXTERNAL_OVER_UNDER_INTAKE_IMPLEMENTATION.md`
- `docs/V4_030_ACCEPTANCE_EVIDENCE.json`

## Over/Under Contract

The adapter accepts only `market=OVER_UNDER`, requires a typed numeric goal `line`, and validates typed positive `over` and `under` provider prices. It requires provider identity, source/source reference, explicit availability status, source/capture/observation/ingestion timestamps, source provenance confidence, payload/provenance hashes, and `source_is_official=false`.

Missing or unavailable goal lines are represented by an explicit `UNKNOWN` or `CONFLICTED` line state together with a non-AVAILABLE status and reason. Numeric strings, empty prices, wrong price labels, and default goal lines are rejected.

## Official Isolation and Identity

Accepted observations resolve to an existing V4-020 canonical `match_id` with `AVAILABLE` and `RESOLVED` identity state. The adapter rejects official lottery fields and never creates an official `total_goals` payload. External O/U remains a separate attributed market fact.

## Availability, Time, and Append-Only Boundary

Non-AVAILABLE states require explicit reason codes. An unknown source timestamp is retained as `UNKNOWN` and is never coerced to `AVAILABLE`. Corrections and duplicate observations follow the shared append-only store boundary.

## Scope and Safety

This task does not connect to a live provider, write Production/Supabase, add or apply a migration, run Prediction/Score/Shadow/Public/Promotion, implement V4-031+, or modify V3.3.3. All test/output paths remain on the F drive.

## Acceptance

- Targeted V4-030 suite: `7/7 PASS`
- Full repository suite: recorded in `V4_030_ACCEPTANCE_EVIDENCE.json`
- External/official isolation: `PASS`
- V4-020 identity binding: `PASS`
- Typed line and price semantics: `PASS`
- Explicit missingness and time state: `PASS`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- V4-030 DoD: `PASS`
- V4-030 Status: `COMPLETE`

Next Task: `V4-031 — External Source-Time Normalization 1.0`.
