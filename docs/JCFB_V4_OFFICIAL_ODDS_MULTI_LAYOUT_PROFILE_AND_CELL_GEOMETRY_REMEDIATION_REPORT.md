# JCFB V4 OFFICIAL ODDS MULTI-LAYOUT PROFILE & CELL GEOMETRY REMEDIATION — ADDITIVE VERSIONED IMPLEMENTATION REPORT

## 1. Work-package identity, scope, and dependencies

This remediation is implemented as the additive sidecar `B15-EWP-007`, revision `r001`, under BATCH-15. The immutable EWP-001 through EWP-005 history and the completed EWP-006 scope were not reopened or edited. No V4-001..100 task identity was created or renumbered.

- Parent scope: `BATCH-15`, `V4-076`, `V4-052..055`.
- Dependency: `B15-EWP-006` remains `COMPLETE`.
- EWP-005 remains `execution_authorized=false`.
- Additive governance artifact: [`v4_batch15_layout_profile_remediation_amendment.json`](../config/prediction_training/v4_batch15_layout_profile_remediation_amendment.json).
- Profile registry artifact: [`layout_profile_remediation_1_1_0.json`](../config/official_odds_cell_extraction/layout_profile_remediation_1_1_0.json).
- The frozen [`official-odds-cell-extraction@1.0.0`](../config/official_odds_cell_extraction/official_odds_cell_extraction_contract.json) file and [`official-odds-cell-trace@1.0.0`](../config/official_odds_cell_extraction/official_odds_cell_trace_schema.json) semantics remain unchanged.

The only permitted historical operation in this work package was a no-write profile detection and geometry coverage smoke test. OCR values, OCR evidence records, accepted odds payloads, manual-review values, archives, and packages were not produced.

## 2. Layout profile identities and registry

`official-odds-layout-profiles@1.1.0` is `FROZEN_ADDITIVE`, compatible with the 1.0.0 extraction contract. Its canonical hash is:

```text
sha256:53fefc744aecfff947b46bd95caff7066d373fdc4bff5c4121108fc72b6e87d3
```

The two supported profiles are:

| Profile | Version | Structural layout | SPF | Other markets |
|---|---:|---|---|---|
| `china-sports-lottery-official-standard` | `1.1.0` | section bars `[220,248]`, `[517,545]`, `[622,650]` | available | available |
| `china-sports-lottery-official-spf-absent` | `1.0.0` | section bars `[203,231]`, `[500,528]`, `[605,633]` | unavailable | available |

Both profiles freeze the source dimension policy `440×982`, source identity `CHINA_SPORTS_LOTTERY_OFFICIAL_SCREENSHOT`, explicit market regions, explicit cell rectangles, and the `official-odds-grid-locator@1.1.0` locator identity. Geometry is bound to the immutable base inventory by `market_contract.inventories[market]` and `ordering_index`; source-visible and canonical labels are not rewritten.

## 3. Detector rules and evidence

The detector consumes raw PNG bytes and observable structural features. It extracts only source dimensions and dark section-bar spans; it does not inspect OCR text, filenames, upload dates, match numbers, aggregate baselines, or manual artifact lists.

- Exactly one profile anchor match: `SELECTED`.
- Zero matches: `UNSUPPORTED_LAYOUT`.
- Multiple matches: `AMBIGUOUS_LAYOUT`, fail-closed.
- Anchor tolerance: ±1 source pixel.
- Profile selection is never fit to `84/50`, `7/7`, `44/32` or any other baseline.

The implementation is in [`remediation.py`](../src/official_odds_cells/remediation.py), including a standard-library PNG decoder, structural feature hash, detector evidence, and ambiguity handling.

## 4. Full 55-cell geometry per profile

Each profile contains exactly 55 geometry entries bound to the five frozen inventories: SPF 3, RQSPF 4, TOTAL_GOALS 8, EXACT_SCORE 31, HTFT 9. The authoritative pixel rectangles for all 110 entries are stored in `cell_geometry_pixels` in the registry artifact; the runtime deterministically derives normalized rectangles by dividing the frozen source-pixel edges by `440` and `982`, and returns the same source-pixel projection.

The complete inventory geometry is:

| Market | Cells | Standard geometry | SPF-absent geometry |
|---|---:|---|---|
| SPF | 3 | three cells `[80,114,196,162]`, `[196,114,309,162]`, `[309,114,423,162]` | three ordered cells are explicitly `null`; market state is `UNAVAILABLE` |
| RQSPF | 4 | `[17,162,80,208]` plus three data cells from x=80..423 | `[17,114,80,190]` plus three data cells `[80,144,196,190]`, `[196,144,309,190]`, `[309,144,423,190]` |
| TOTAL_GOALS | 8 | 2×4 rows, y=`545..578` and `578..610`, x edges `35,132,229,327,425` | 2×4 rows, y=`528..562` and `562..595`, same x edges |
| EXACT_SCORE | 31 | seven visual rows: 5 + 5 + 3 + 5 + 5 + 5 + 3 ordered cells; y edges `248,285,322,359,396,433,470,506`, x edges `43,119,196,273,349,425`; `WIN_OTHER` and `LOSE_OTHER` use merged rectangles | same seven-row ordering and merged-cell semantics; y edges `231,268,305,342,379,416,453,490` |
| HTFT | 9 | 3×3 rows, y=`650..687`, `687..724`, `724..761`, x edges `43,170,297,425` | 3×3 rows, y=`633..670`, `670..706`, `706..743`, same x edges |

Geometry validation checks all 55 ordering indexes, region containment, positive area, and pairwise overlap. Shared borders are allowed; positive-area overlaps are rejected. SPF-absent geometry is intentionally null only for the SPF inventory, so RQSPF, TOTAL_GOALS, EXACT_SCORE, and HTFT remain independently addressable.

## 5. HTFT schema alias remediation

The additive contract declares:

```text
canonical field: htft
legacy alias:   half_full
precedence:     htft, then half_full
missing:        UNKNOWN
conflict:       BLOCKED / CONFLICT, fail-closed
UNKNOWN != UNAVAILABLE
```

When both fields exist with the same normalized state, `htft` is selected deterministically. When both exist with different states, no field is selected and the resolved state is `BLOCKED`. Missing coverage remains `UNKNOWN`; it is not silently converted into `MARKET_UNAVAILABLE`. The alias resolver is integrated into the in-memory trace runtime through `market_availability_fields` and is covered by focused tests.

## 6. Locator, trace, and hash compatibility

The existing 1.0.0 contract and trace schema remain loadable and continue to use `official-odds-grid-locator@1.0.0`. The remediation path uses `official-odds-grid-locator@1.1.0` and explicit profile rectangles. A trace built through the additive contract binds:

- selected profile identity/version;
- locator identity/version and deterministic locator key;
- normalized and source-pixel cell coordinates;
- additive layout/parser configuration hash;
- existing trace record hash boundary.

Changing profile identity/version or the effective layout/config hash changes trace identity and record hashes. Repeating the same raw bytes, profile, and config produces byte-identical trace output.

## 7. 64-artifact no-write profile coverage smoke test

Input: the existing handoff ZIP under `approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/`. The smoke test reads raw PNG members in memory and writes no approved-data artifact.

```text
profile registry: official-odds-layout-profiles@1.1.0
selected: 64/64
standard: 61
spf-absent: 3
unsupported: 0
ambiguous: 0
HTFT geometry-ready: 64/64
TOTAL_GOALS geometry-ready: 64/64
EXACT_SCORE geometry-ready: 64/64
RQSPF geometry-ready: 64/64
SPF geometry-ready: 61/64; 3/64 explicitly MARKET_UNAVAILABLE
```

The machine-readable no-write output is [`layout_profile_smoke_20260907.json`](../work/layout_profile_smoke_20260907.json). It contains only profile/geometry status and explicit safety flags; it contains no OCR values or accepted odds payload.

## 8. Tests and validators

Passed:

- `python -m unittest tests.unit.test_official_odds_layout_profile_remediation -v` — 8 tests.
- `python scripts/validate_v4_batch15_layout_profile_remediation.py`.
- `python scripts/validate_official_odds_cell_extraction.py` — EWP-006 validator remains PASS.
- Read-only 64-artifact profile/geometry smoke test — PASS.

The focused tests cover standard and shifted detection, unsupported and ambiguous fail-closed behavior, complete 55-cell inventory, exact-score/total-goals/HTFT geometry ordering and overlap, SPF-only unavailability, alias precedence/missing/unknown/conflict, normalized projection determinism, and profile/config hash change effects.

## 9. Remaining blockers and final decision

```text
MULTI_LAYOUT_PROFILE_REMEDIATION_STATUS = COMPLETE
LAYOUT_PROFILE_REGISTRY_VERSION = official-odds-layout-profiles@1.1.0
STANDARD_LAYOUT_PROFILE_STATUS = COMPLETE
SPF_ABSENT_LAYOUT_PROFILE_STATUS = COMPLETE
HTFT_SCHEMA_ALIAS_REMEDIATION = COMPLETE
CELL_GEOMETRY_REMEDIATION_STATUS = COMPLETE
PROFILE_DETECTOR_STATUS = COMPLETE
64_ARTIFACT_PROFILE_COVERAGE = PASS
OCR_EVIDENCE_REPLAY_READINESS = READY_FOR_SEPARATE_EXECUTION
MANUAL_REVIEW_LEDGER_RETRY_READINESS = BLOCKED
PACKAGE_R002_REBUILD_READINESS = BLOCKED
INTAKE_RUNTIME_AUTHORIZATION_READINESS = BLOCKED
Current Training Readiness = BLOCKED / TRAINING_DATA_INSUFFICIENT
```

Manual review remains blocked until a separately authorized OCR-enriched replay produces the final unresolved trace. No OCR enrichment, manual review, r002 rebuild, archive intake, EWP-002/EWP-003 rerun, EWP-005 execution, model fitting/calibration, production/shadow/public/Supabase/migration, or V3.3.3 action was performed.

## 10. Only allowed next step

The only allowed next step is a separately reviewed and explicitly executed OCR evidence enrichment run using the selected versioned profile and locator contract. That run must remain adapter-input-only and fail-closed, and must not be started automatically by this remediation.

## 11. Commit, HEAD, and working tree

- Starting/frozen HEAD observed: `89e784bd7247d2cd10b14b7f7924b6383ffc4ff7`.
- Final commit and final HEAD: `f79ede0ee51d836dfcf2cadf27994691d9731523`.
- Existing user-owned untracked staging and `work/` content was preserved; no existing approved-data history was rewritten.
- F-drive boundary remained active; no `database/migrations/` or V3.3.3 path was changed.
