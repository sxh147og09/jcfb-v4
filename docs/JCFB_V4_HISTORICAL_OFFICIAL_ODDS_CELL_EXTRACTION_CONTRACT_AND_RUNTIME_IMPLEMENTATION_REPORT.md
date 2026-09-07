# JCFB V4 HISTORICAL OFFICIAL ODDS CELL EXTRACTION CONTRACT & DETERMINISTIC PARSER RUNTIME ARCHITECTURE AMENDMENT / IMPLEMENTATION REPORT

Date: `2026-09-07` (Asia/Shanghai)

## 1. Work package identity, scope, and dependencies

The implementation is recorded as additive `B15-EWP-006 r001`,
`historical-official-odds-cell-extraction-runtime`, under
`v4-batch-prerequisite-workpackages-amendment-001@1.0.0`. The immutable active
five-package registry is not modified. EWP-006 depends on B15-EWP-001 only and
does not reopen or rerun B15-EWP-002/003.

The package is complete for its declared implementation scope: contract,
layout/locator registry, parser, hashing, unresolved derivation, tests, and
focused validation. It is not a historical data import, odds acceptance path,
archive path, or training execution.

## 2. Contract identity and source boundary

The frozen contract is `official-odds-cell-extraction@1.0.0`, with trace schema
`official-odds-cell-trace@1.0.0`.

Source identity is `CHINA_SPORTS_LOTTERY_OFFICIAL_SCREENSHOT`. Raw image bytes
are hashed as supplied and are never rescaled, transcoded, or overwritten.
Normalized coordinates are a locator representation only. Unknown source times
remain the literal `UNKNOWN`; runtime ingestion time is never substituted.

## 3. Layout profile model

`official-odds-layout-profiles@1.0.0` currently registers one explicit profile:
`cn-sports-lottery-odds-grid-v1@1.0.0`. It defines normalized market regions
and grid dimensions for SPF, RQSPF, TOTAL_GOALS, EXACT_SCORE, and HTFT. Profile
detection is exact-match over the declared profile identity and all five region
anchors. Missing, unknown, or mismatching profiles emit `UNSUPPORTED_LAYOUT`;
there is no implicit fallback or hidden if/else branch.

Coordinates use the normalized interval `[0,1]` with six-decimal precision and
left/top-inclusive, right/bottom-exclusive rectangles. Source-pixel projection
uses `floor` for left/top and `ceil` for right/bottom, clamped to source
dimensions. The runtime requires explicit source width and height.

## 4. Complete market cell inventories

The frozen inventory contains 55 deterministic cells:

| Market | Count | Ordering |
|---|---:|---|
| SPF | 3 | 胜 → 平 → 负, canonical H/D/A |
| RQSPF | 4 | 让球数 → 让胜 → 让平 → 让负; line plus H/D/A |
| TOTAL_GOALS | 8 | 0, 1, 2, 3, 4, 5, 6, 7+ |
| EXACT_SCORE | 31 | standard numeric score cells with 胜其他/平其他/负其他 in fixed source order |
| HTFT | 9 | H/H, H/D, H/A, D/H, D/D, D/A, A/H, A/D, A/A |

Every item has a source-visible label, canonical outcome label, ordering index,
row, column, and value kind. Exact-score “other” labels are represented as
`WIN_OTHER`, `DRAW_OTHER`, and `LOSE_OTHER` canonical outcomes. This extraction
contract does not silently coerce those labels into the older V4-024 accepted
payload shape; a separately governed adapter is required if a future consumer
needs that representation.

## 5. Locator and coordinate semantics

The deterministic locator identity is:

```text
layout_profile_id + market + source_visible_label + official-odds-grid-locator@1.0.0
```

The locator registry derives region and cell rectangles only from the frozen
profile, inventory row/column, and explicit source dimensions. Locator keys are
unique across all 55 cells. Unsupported profiles retain the deterministic cell
identity but expose null coordinates and fail closed.

## 6. Parser status vocabulary and OCR semantics

The parser implementation is `official-odds-cell-parser@1.0.0`. It accepts OCR
as adapter-provided evidence, normalizes text deterministically with Unicode
NFKC and whitespace trimming, and parses only finite numeric odds tokens or
finite numeric handicap lines. It never guesses.

The status vocabulary is:

```text
PARSED
UNRESOLVED
AMBIGUOUS
NOT_PRESENT
MARKET_UNAVAILABLE
CONFLICT
UNSUPPORTED_LAYOUT
```

OCR evidence retains raw text, normalized text, engine identity/version/config
hash, confidence, candidate values, and contradiction state. Confidence is
evidence only; no automatic confidence threshold is used. Neighboring cells,
later snapshots, duplicate images, and historical aggregate baselines are
explicitly forbidden as inference sources.

## 7. Trace record and hash boundary

Each record carries the deterministic trace ID, artifact/raw-image identity,
layout profile identity, market/source/canonical labels, ordering index, locator
and coordinates, parser implementation/config identities and hashes, OCR
evidence, parsed value, parser status/reason, contradiction state, market
availability state, source timestamps, and `trace_record_sha256`.

`trace_record_sha256` is SHA-256 over the recursive lexicographic canonical JSON
of every trace field except itself. Volatile process ID, host name, wall-clock
extraction time, and temporary paths are excluded. Required absence is explicit
null where allowed; unknown timestamps are `UNKNOWN`; semantic array order is
preserved. Same raw bytes plus same layout/parser/config identities therefore
replay to the same trace record ID and hash.

## 8. Mechanical unresolved derivation

`full cell trace -> unresolved cell trace` retains only records whose status is
one of `UNRESOLVED`, `AMBIGUOUS`, `NOT_PRESENT`, `MARKET_UNAVAILABLE`,
`CONFLICT`, or `UNSUPPORTED_LAYOUT`. Original contract order is preserved.
`PARSED` is excluded. No aggregate count, including the frozen `84/7/44`
baseline, is consulted. No post-hoc cell selection is possible in the runtime.

## 9. Runtime implementation modules

- `src/official_odds_cells/contract.py`: frozen contract loading and safety validation.
- `src/official_odds_cells/layout.py`: versioned profile detection, normalized rectangles, pixel projection, and cell locators.
- `src/official_odds_cells/parser.py`: OCR evidence normalization and market-independent numeric parser.
- `src/official_odds_cells/runtime.py`: immutable raw-image hashing, full trace construction, record hashing, JSONL serialization in memory, and unresolved derivation.
- `scripts/validate_official_odds_cell_extraction.py`: focused governance, identity, inventory, hash, F-drive, archive, r002, and V3 isolation validation.

The runtime has no persistence API and does not call V4-024/V4-026/V4-027
accepted-value or ledger paths.

## 10. Tests and validators

Synthetic/local tests cover contract freeze, all five inventories, locator
uniqueness and pixel projection, unsupported layout fail-closed behavior, clean
OCR parsing, blur/unresolved, ambiguity, conflict, missing cell,
market-unavailable semantics, deterministic replay, config-change hash change,
mechanical unresolved filtering, and UNKNOWN timestamp preservation.

Focused validator coverage checks the additive amendment binding, contract and
schema identity, inventory completeness, locator/profile semantics, status
vocabulary, unresolved set, canonical hash boundary, safety boundary, F-drive
boundary, zero archive files, zero r002 ZIP files, and V3/migration isolation.

The existing B15-EWP-001/002/003/004 validators and BATCH-15 governance
validators remain untouched. They continue to validate their original five-item
registry facts. The current request's repository-wide legacy validation suite
is run separately after the focused suite.

## 11. Historical replay readiness

The implementation is ready for a separately authorized historical replay. A
future replay must supply each raw PNG's source dimensions, exact layout anchors,
and OCR adapter evidence. It will emit in-memory/full-trace readiness only under
the next authorization; this implementation run did not read or process the 64
historical PNGs and did not create `full_cell_extraction_trace.jsonl`,
`unresolved_cell_trace.jsonl`, or `evidence_regions/`.

`TRACE_BASELINE_REPRODUCIBILITY = NOT_EXECUTED`. The frozen `84/7/44` aggregate
baseline remains unchanged and was not used as a parser target.

## 12. Remaining blockers

Manual review remains blocked until a separately authorized historical replay
produces an immutable unresolved trace. Accepted odds payload integration,
archive revision, r002 rebuild, EWP-002/EWP-003 rerun, EWP-005 execution,
training, calibration, promotion, Production/Shadow/Public/Supabase/migration,
and V3.3.3 work remain outside this package.

## 13. Only allowed next step

Create a separate scope-entry and no-write replay authorization for historical
trace reconstruction. That next step may use only the current F-drive staging
raw PNG set and must preserve the fail-closed/no-archive/no-accepted-payload
boundary. It must not begin manual review or r002 generation automatically.

## 14. Commits, HEAD, and working tree

Implementation commit lineage is recorded in the additive EWP-006 sidecar as
`28e81e7` (`feat(v4): add official odds cell extraction runtime`). The closure
commit is the final handoff commit for this review. The user-owned pre-existing staging directory
under `approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/`
was not modified. No V3.3.3 path or database migration was changed.

Final readiness values for this implementation review:

```text
CELL_EXTRACTION_CONTRACT_STATUS = COMPLETE
CELL_EXTRACTION_CONTRACT_IDENTITY = official-odds-cell-extraction@1.0.0
LAYOUT_PROFILE_REGISTRY_STATUS = COMPLETE
DETERMINISTIC_PARSER_RUNTIME_STATUS = COMPLETE
TRACE_HASHING_READINESS = READY
UNRESOLVED_DERIVATION_READINESS = READY
HISTORICAL_TRACE_RECONSTRUCTION_READINESS = READY_FOR_SEPARATE_EXECUTION
TRACE_BASELINE_REPRODUCIBILITY = NOT_EXECUTED
MANUAL_REVIEW_LEDGER_RETRY_READINESS = BLOCKED
PACKAGE_R002_REBUILD_READINESS = BLOCKED
INTAKE_RUNTIME_AUTHORIZATION_READINESS = BLOCKED
Current Training Readiness = BLOCKED / TRAINING_DATA_INSUFFICIENT
```
