# JCFB V4 Odds Snapshot Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Scope and isolation

This contract defines official China Sports Lottery odds snapshots and a separate future-ready external market snapshot. It preserves exact source, capture, availability, and hash boundaries. It does not fabricate odds, infer an official market from external prices, or select a Production algorithm.

The official and external objects are separate contract families. `source_is_official=true` is allowed only for an attributable official source; an external provider can never be relabeled as official.

The five official markets are exactly:

```text
spf, rqspf, total_goals, exact_score, half_full
```

## 2. Official Odds Snapshot Contract

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` | UUID/UUIDv7 | REQUIRED | Stable snapshot object identity. |
| `snapshot_id` | UUID/UUIDv7 | REQUIRED | Canonical snapshot identity used by Frozen Input. |
| `contract_version` | string | REQUIRED | `official-odds-snapshot@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 | REQUIRED | Must resolve to one Canonical Match Identity. |
| `snapshot_kind` | enum | REQUIRED | `OPENING`, `INTERMEDIATE`, `CURRENT`, `LATEST`, `FINAL`, or `CORRECTION`. |
| `captured_at` | timezone-aware timestamp | REQUIRED | Time the official screen/feed was captured. |
| `source_timestamp` | timezone-aware timestamp or state | REQUIRED | Time asserted by the official source; never silently copied from `captured_at`. |
| `observed_at` | timezone-aware timestamp | REQUIRED | System observation/capture time. |
| `ingested_at` | timezone-aware timestamp | REQUIRED for persisted intake | System acceptance time. |
| `source_is_official` | boolean | REQUIRED | Must be `true` for this object. |
| `source` / `source_type` / `source_reference` | typed metadata | REQUIRED | Official source and replayable screenshot/feed reference. |
| `evidence_ref` | stable Evidence ref | CONDITIONAL | REQUIRED for `OFFICIAL_SCREENSHOT` extraction; preserves the source evidence object alongside the screenshot reference. |
| `market_availability` | object keyed by five markets | REQUIRED | Each market explicitly states `available` and a governed status. |
| `market_unavailable_reason` | object keyed by unavailable markets | REQUIRED | Non-empty reason for each unavailable market; available markets use `NOT_APPLICABLE`. |
| `spf`, `rqspf`, `total_goals`, `exact_score`, `half_full` | typed payloads | CONDITIONAL | Required only when the corresponding market is available; never use `{}` as unavailable. |
| `snapshot_hash` | SHA-256 string | REQUIRED | Hash of the exact logical official snapshot. |
| `payload_hash` | SHA-256 string | REQUIRED | Must equal `snapshot_hash` for this contract. |
| `provenance_hash` / `status` / `metadata` | common fields | REQUIRED | Provenance and gate state. |

### 2.1 Availability

Each `market_availability[market]` has:

```json
{
  "available": true,
  "status": "AVAILABLE",
  "reason": "NOT_APPLICABLE"
}
```

When a market is not supplied or not open:

```json
{
  "available": false,
  "status": "UNAVAILABLE",
  "reason": "OFFICIAL_MARKET_NOT_ON_SALE"
}
```

`market_unavailable_reason` repeats the reason by market for simple gate queries. It must contain a non-empty reason for `available=false`; it must contain `NOT_APPLICABLE` for an available market. An unavailable market has no odds payload. A missing key, empty object, zero odds, or fabricated default is invalid.

### 2.2 Payload shapes

All official prices are numeric positive values and retain the source's displayed precision. A payload is present only when its availability is `AVAILABLE`.

| Market | Minimum payload | Additional rules |
|---|---|---|
| `spf` | `{ "home": number, "draw": number, "away": number }` | H/D/A labels are official outcomes; no external prices may be substituted. |
| `rqspf` | `{ "official_handicap": number, "home": number, "draw": number, "away": number }` | `official_handicap` is required whenever RQSPF is available and must match the canonical official handicap snapshot. |
| `total_goals` | `{ "0": number, "1": number, ..., "7+": number }` | Preserve the official total-goals labels; missing labels require an explicit source reason. |
| `exact_score` | `{ "home:away": number, ... }` | Preserve exact source score labels. Do not generate missing score prices. |
| `half_full` | `{ "H/H": number, "H/D": number, "H/A": number, "D/H": number, "D/D": number, "D/A": number, "A/H": number, "A/D": number, "A/A": number }` | The nine official half/full states are independent values. |

`CURRENT` and `LATEST` are ordered data concepts, not aliases. `LATEST` must have the greatest accepted `captured_at` for the declared snapshot family. `OPENING` must be the earliest accepted official snapshot for that match and market family.

### 2.3 Correction and chronology

- All snapshots for a match must reference the same `match_id` and timezone-aware timeline.
- A snapshot's `source_timestamp` and `captured_at` are retained separately.
- `OPENING.captured_at <= INTERMEDIATE.captured_at <= CURRENT.captured_at <= LATEST.captured_at` when the respective records exist. `FINAL` and `CORRECTION` retain their own declared chronology and references.
- A correction creates a new `snapshot_id`, `snapshot_kind=CORRECTION`, `supersedes_snapshot_id`, reason, and new hashes. It never edits the old snapshot.
- An official screenshot extraction must retain `source_type=OFFICIAL_SCREENSHOT`, `source_reference`, screenshot/capture time, extraction status, and evidence reference. OCR or manual transcription cannot remove the original provenance.
- If the official source time is unknown, conflicting, or after the declared prediction cutoff, the snapshot is `UNKNOWN`, `CONFLICTED`, or `BLOCKED` for that pre-match run; it is not silently accepted.

## 3. External Market Snapshot Contract

The external contract is intentionally separate:

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `snapshot_id` | UUID/UUIDv7 | REQUIRED | Stable external snapshot identity. |
| `contract_version` | string | REQUIRED | `external-market-snapshot@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 | REQUIRED | Canonical match reference. |
| `provider` | string | REQUIRED | Named external provider. |
| `market` | enum | REQUIRED | `EUROPEAN_1X2`, `ASIAN_HANDICAP`, or `OVER_UNDER`. |
| `line` | number/string/state | CONDITIONAL | Required for handicap and totals; explicit `NOT_APPLICABLE` for 1X2. |
| `prices` | typed object | REQUIRED | Provider prices with labels preserved. |
| `captured_at` | timezone-aware timestamp | REQUIRED | Capture time. |
| `source_timestamp` | timezone-aware timestamp or state | REQUIRED | Provider time, if supplied; unknown remains `UNKNOWN`. |
| `liquidity_quality` | enum/object/state | OPTIONAL | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`, or provider-specific governed detail. |
| `source_confidence` | `ConfidenceValue` | REQUIRED | Confidence in provider provenance, not model confidence. |
| `snapshot_hash` / `payload_hash` | SHA-256 string | REQUIRED | Hash of the external payload; never reused as an official hash. |
| `source_is_official` | boolean | REQUIRED | Must be `false`. |
| common provenance/status fields | typed metadata | REQUIRED | Source and gate lineage. |

External objects may inform Market Intelligence only. They must not populate an official five-market payload, official availability, or official handicap field.

## 4. Minimum legal JSON examples

### 4.1 Official snapshot

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000101",
  "snapshot_id": "019a0000-0000-7000-8000-000000000101",
  "contract_version": "official-odds-snapshot@1.0.0",
  "created_at": "2026-09-01T10:00:00+08:00",
  "source_timestamp": "2026-09-01T09:59:30+08:00",
  "observed_at": "2026-09-01T10:00:00+08:00",
  "ingested_at": "2026-09-01T10:00:02+08:00",
  "source": "China Sports Lottery official odds screen",
  "source_type": "OFFICIAL_SCREENSHOT",
  "source_reference": "ref://official/odds/screenshot/20260901-001-100000",
  "evidence_ref": "evidence:019a0000-0000-7000-8000-000000000301",
  "confidence": {
    "state": "ASSESSED",
    "score": 0.98,
    "basis": "Official screenshot with visible match number and capture time"
  },
  "provenance_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "payload_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "status": "AVAILABLE",
  "metadata": {
    "hash_exclusions": ["created_at", "ingested_at"]
  },
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "snapshot_kind": "CURRENT",
  "captured_at": "2026-09-01T10:00:00+08:00",
  "source_is_official": true,
  "market_availability": {
    "spf": {"available": true, "status": "AVAILABLE", "reason": "NOT_APPLICABLE"},
    "rqspf": {"available": true, "status": "AVAILABLE", "reason": "NOT_APPLICABLE"},
    "total_goals": {"available": true, "status": "AVAILABLE", "reason": "NOT_APPLICABLE"},
    "exact_score": {"available": true, "status": "AVAILABLE", "reason": "NOT_APPLICABLE"},
    "half_full": {"available": true, "status": "AVAILABLE", "reason": "NOT_APPLICABLE"}
  },
  "market_unavailable_reason": {
    "spf": "NOT_APPLICABLE",
    "rqspf": "NOT_APPLICABLE",
    "total_goals": "NOT_APPLICABLE",
    "exact_score": "NOT_APPLICABLE",
    "half_full": "NOT_APPLICABLE"
  },
  "spf": {"home": 2.10, "draw": 3.20, "away": 3.15},
  "rqspf": {"official_handicap": -1.0, "home": 3.50, "draw": 3.70, "away": 1.62},
  "total_goals": {"0": 8.00, "1": 3.80, "2": 3.20, "3": 3.40, "4": 5.50, "5": 9.00, "6": 16.00, "7+": 20.00},
  "exact_score": {"1:0": 7.50, "2:0": 8.00, "2:1": 8.50, "1:1": 6.80},
  "half_full": {"H/H": 3.20, "H/D": 12.00, "H/A": 18.00, "D/H": 4.50, "D/D": 5.00, "D/A": 7.00, "A/H": 20.00, "A/D": 15.00, "A/A": 8.50},
  "snapshot_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

### 4.2 Explicitly unavailable market fragment

```json
{
  "market_availability": {
    "rqspf": {"available": false, "status": "UNAVAILABLE", "reason": "OFFICIAL_MARKET_NOT_ON_SALE"}
  },
  "market_unavailable_reason": {
    "rqspf": "OFFICIAL_MARKET_NOT_ON_SALE"
  }
}
```

In this fragment, the `rqspf` payload is omitted. `{}` would be invalid because it hides whether the market is unavailable or merely empty.

### 4.3 External market snapshot

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000102",
  "snapshot_id": "019a0000-0000-7000-8000-000000000102",
  "contract_version": "external-market-snapshot@1.0.0",
  "created_at": "2026-09-01T10:01:00+08:00",
  "source_timestamp": "2026-09-01T10:00:45+08:00",
  "observed_at": "2026-09-01T10:01:00+08:00",
  "ingested_at": "2026-09-01T10:01:01+08:00",
  "source": "Example External Provider",
  "source_type": "EXTERNAL_FEED",
  "source_reference": "ref://external/example-provider/match-001/100045",
  "confidence": {"state": "ASSESSED", "score": 0.87, "basis": "Provider response with match mapping"},
  "provenance_hash": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "payload_hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "status": "AVAILABLE",
  "metadata": {},
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "provider": "Example External Provider",
  "market": "ASIAN_HANDICAP",
  "line": -1.0,
  "prices": {"home": 1.92, "away": 1.94},
  "captured_at": "2026-09-01T10:00:45+08:00",
  "liquidity_quality": "UNKNOWN",
  "source_confidence": {"state": "ASSESSED", "score": 0.87, "basis": "Provider response"},
  "source_is_official": false,
  "snapshot_hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
}
```

## 5. Validation rules

- All common required fields, `snapshot_id`, `match_id`, `snapshot_kind`, `captured_at`, `source_is_official`, the five availability keys, and both specialized hashes are required.
- Every official price must be numeric and strictly greater than zero; no `NaN`, infinity, negative, or invented price is accepted.
- `source_is_official=true` requires an official `source_type` and source reference. External provider names in an official object are a role/source violation.
- `market_availability` and `market_unavailable_reason` must cover exactly the five official markets. An unavailable market must have `available=false`, `status=UNAVAILABLE`, and a non-empty reason; its payload must be absent.
- If `rqspf.available=true`, `rqspf.official_handicap` is required and must equal the accepted official handicap for that match/snapshot.
- `OPENING` and `LATEST` order is validated by `captured_at`; `LATEST` cannot be older than a valid accepted current snapshot.
- A pre-match consumer rejects any snapshot with defensible availability after `prediction_cutoff_at`, unknown/conflicting source time, or `captured_at >= kickoff_at` unless an explicitly governed post-kickoff path is being used.
- Official screenshot extraction retains `source_reference` and evidence/provenance reference. OCR text alone is not sufficient provenance.
- `evidence_ref` is required for `OFFICIAL_SCREENSHOT`; it must resolve to the Evidence object that preserves the source image/extraction lineage.
- `snapshot_hash`, `payload_hash`, and `provenance_hash` must match the declared canonical format. `snapshot_hash=payload_hash` for official and external snapshot objects.
- External `source_is_official=false`; external objects cannot satisfy the official odds gate.

## 6. Hash and compatibility boundary

The official snapshot hash includes `snapshot_id`, `match_id`, `snapshot_kind`, `captured_at`, source-time fields, source identity, all availability records, all available official payloads, correction/supersedes references, and the declared precision of numeric prices. It excludes transport-only `created_at`, `ingested_at`, and UI trace metadata.

Adding an optional market annotation is `MINOR`. Changing a market key, payload type, availability meaning, official/external separation, RQSPF handicap rule, chronology rule, or hash boundary is `MAJOR`. A documentation clarification is `PATCH`. Historical snapshot IDs and hashes are immutable.
