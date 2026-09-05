# JCFB V4 V4-047 MARKET MOVEMENT IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`
Task: `V4-047 — Market Movement, Velocity & Divergence Features 1.0`
Upstream: accepted V4-046 Market Intelligence artifacts only

## Implementation status

V4-047 is implemented as a pre-Frozen movement and market-comparison layer.
It consumes normalized V4-046 artifacts and never re-reads raw official or
external source data.

Implemented capabilities:

- same-provider/source, same-market movement series;
- explicit `PRICE_MOVEMENT`, `LINE_MOVEMENT`, and
  `IMPLIED_PROBABILITY_MOVEMENT` objects;
- separate line and price before/after values with source snapshot refs;
- elapsed-hour-normalized movement and approved acceleration with minimum
  three-snapshot enforcement;
- European 1X2 market-implied probability normalization and delta;
- equal eligible provider median, IQR, MAD, count, and source lineage;
- official SPF versus external European 1X2 numeric divergence;
- structured `NOT_COMPARABLE` relations for unapproved official/external
  market pairs;
- explicit block/unknown semantics for mixed providers, future data,
  non-consumable states, invalid time intervals, and insufficient series;
- append-only movement artifact storage and duplicate no-op behavior.

V4-048 heat, pressure, anomaly, and trap-risk interpretation was not
implemented or imported.

## Files

- `tools/canonical_intake/market_movement.py`
- `tools/canonical_intake/__init__.py`
- `tests/unit/test_v4_047_market_movement.py`
- `tests/fixtures/v4_047/market_movement_cases.json`
- `docs/V4_047_MARKET_MOVEMENT_IMPLEMENTATION.md`
- `docs/V4_047_ACCEPTANCE_EVIDENCE.json`

## Contract and semantic boundary

Active contract: `market-movement@1.0.0`

Movement is computed only from accepted V4-046 artifacts with the same
canonical match, provider/source, market, role, and appropriate semantic
alignment. Different providers cannot be adjacent points in one movement
series. Price movement requires the same semantic line; explicit line
movement is used for approved Asian Handicap/O-U/RQSPF line transitions.

Source availability time is authoritative. Post-cutoff input, unresolved time,
non-positive elapsed time, and non-AVAILABLE input fail closed. Captured,
observed, or ingested timestamps do not replace source time.

European 1X2 outputs use `market_implied_probability`, never a bare
`probability` or prediction probability. Provider aggregates use
`EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION`; no arbitrary bookmaker/provider weight
is created. Numeric official/external divergence is restricted to the approved
SPF-to-European-1X2 mapping. All other cross-market relations remain
`NOT_COMPARABLE` with both source references retained.

## Safety boundaries

- no V4-048 heat, pressure, anomaly, or trap-risk implementation;
- no bookmaker intent, trap certainty, betting advice, prediction, Score
  Engine, Frozen Input, Shadow/Tier A, Public Page, or Promotion;
- no provider weighting or majority-as-truth semantics;
- no synthetic movement, missing-value fallback, or time substitution;
- no migration and no Production/Supabase access;
- no V3.3.3 modification;
- all runtime/test/output activity remains under `F:\Projects\jcfb-v4`.

## Verification

- targeted V4-047 tests: **11/11 PASS**;
- full repository tests: **442/442 PASS**;
- V4 data contract validation: **PASS**;
- V4 versioning validation: **85 PASS / 0 FAIL**;
- same-source and semantic-line audit: **PASS**;
- line/price separation: **PASS**;
- cutoff/future-data and elapsed-time audit: **PASS**;
- acceleration minimum-series and no-extrapolation audit: **PASS**;
- provider consensus/dispersion and no-weight audit: **PASS**;
- official/external comparability and `NOT_COMPARABLE` audit: **PASS**;
- deterministic hash and append-only audit: **PASS**;
- Prediction/Score/Frozen Input boundary: **PASS**;
- V3.3.3 isolation: **PASS**;
- F-drive policy: **PASS**;
- Production/Supabase writes: **NO**;
- migration added/applied: **NO**;

## DoD

**V4-047 DoD: PASS**

**V4-047 Status: COMPLETE**

The next approved task is V4-048 only.
