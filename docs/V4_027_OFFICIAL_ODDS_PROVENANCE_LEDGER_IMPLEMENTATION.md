# JCFB V4 V4-027 OFFICIAL ODDS TIMESTAMP & PROVENANCE LEDGER IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch/HEAD: recorded in the acceptance evidence after the V4-027 implementation commit

Implementation Status: `COMPLETE` for the V4-027 local, append-only, no-write official odds provenance boundary

## Files Added/Changed

- `tools/canonical_intake/official_ledger.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_027/official_ledger_cases.json`
- `tests/unit/test_v4_027_official_ledger.py`
- `docs/V4_027_OFFICIAL_ODDS_PROVENANCE_LEDGER_IMPLEMENTATION.md`
- `docs/V4_027_ACCEPTANCE_EVIDENCE.json`
- BATCH-06 status documents updated to record V4-027 acceptance; Closure Review remains the next gate

## Provenance Ledger Contract

`official-odds-provenance-ledger@1.0.0` consumes a typed V4-024 `OfficialOddsSnapshot`, a matching V4-026 `AvailabilityGateResult`, and an optional V4-025 `OfficialScreenshotEvidence`. It preserves the canonical `match_id`, snapshot and observation references, gate reference, official source identity, source reference, five-market statuses, snapshot/payload/provenance hashes, and screenshot provenance/hash references.

The ledger retains source timestamp, screenshot published timestamp when supplied, capture time, observation time, and ingestion time. The selected `availability_at` is explicit and uses only the reused V4-022 `AvailabilityTimeBasis`: `SOURCE_TIMESTAMP`, `SOURCE_PUBLISHED_AT`, or `OBSERVED_AT`. `ingested_at` is retained for audit and is never selected as source availability.

## Cutoff and Future-Information Semantics

The existing V4-022 time statuses and rule are reused without changing the frozen enum:

```text
availability_at <= prediction_cutoff_at < kickoff_at
```

- `PREMATCH_ALLOWED` is accepted only after V4-026 `PASSED` and a known selected source time.
- `UNKNOWN` or `CONFLICTED` selected source time is retained and returns `BLOCKED` with `UNKNOWN_TIME_BLOCKED`; it is never replaced by capture, observation, or ingestion time.
- Availability after cutoff returns `FUTURE_INFORMATION_LEAKAGE` and sets `future_information_leakage=true` and `run_invalid=true`.
- Availability at or after kickoff returns `POSTMATCH_ONLY` with the same invalid-for-prematch flags.
- V4-026 blocked or explicit missingness outcomes remain `BLOCKED` and are never promoted to available odds.

## Identity, Conflict, and Append-Only Boundary

The ledger requires the snapshot, gate, and optional screenshot evidence to refer to the same resolved V4-020 canonical match. Feed and screenshot source timestamps are compared when both are known; a mismatch is blocked. Competing screenshot evidence remains reachable through the V4-025 evidence reference and causes the V4-026 gate to remain blocked.

Each accepted or blocked decision is retained in a local append-only event ledger. Identical source/gate/cutoff/basis inputs return `DUPLICATE_NOOP`. Corrections append a new ledger entry with `supersedes_ledger_id` and an incremented revision; no update or delete API exists.

## Scope and Safety

This task records official odds time and provenance only. It does not connect to a live official feed, run OCR, add or apply a migration, write Production/Supabase, run Prediction/Score/Shadow/Public/Promotion, implement V4-028+, or modify V3.3.3.

## Acceptance

- Targeted V4-027 suite: `12/12 PASS`
- Full repository suite: recorded in `V4_027_ACCEPTANCE_EVIDENCE.json`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Contract/boundary audit: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- V4-027 DoD: `PASS`
- V4-027 Status: `COMPLETE`

Next Task: `BATCH-06 Closure Review` only.
