# JCFB V4 Market Risk Interpretation Contract 1.0

Status: **BATCH-13 GOVERNANCE RESOLUTION — APPROVED FOR V4-048**  
Contract version: `market-risk-interpretation@1.0.0`

## 1. Purpose and boundary

V4-048 produces a typed Market Anomaly / Trap-Risk Evidence Profile. It describes observable market structure and uncertainty. It does not assert bookmaker intent, manipulation, a certain trap, a betting decision, a final risk decision, or any prediction.

`Trap Risk != Bookmaker Intent` is a hard boundary.

## 2. Activity and pressure representation

Market heat is a multidimensional activity object, not a single score. Approved components include:

- snapshot count;
- price-change count;
- line-change count;
- total absolute price movement;
- total absolute line movement;
- movement velocity components;
- provider breadth;
- direction agreement;
- observation span;
- minutes to kickoff.

Pressure is a component object containing direction, persistence, breadth, velocity, line-change presence, and reversal presence. `heat_score` and `pressure_score` are not approved in v1.

No coefficient or cross-dimension interaction is implied. The default remains `SEPARATE_DIMENSIONS_ONLY`.

## 3. Approved anomaly flags

The following structural flags may be emitted only when their predicate, source refs, timestamps, config/mapping identity, and deterministic inputs are present:

- `DIRECTION_REVERSAL`: adjacent valid same-source movement direction changes sign;
- `PROVIDER_DISPERSION`: at least two eligible comparable provider observations are retained and their values are not identical;
- `OFFICIAL_EXTERNAL_DIVERGENCE`: an approved comparable official/external mapping produces a retained market-derived divergence relationship;
- `SPARSE_MARKET`: the requested feature cannot be computed from the required valid series;
- `STALE_MARKET`: an input is explicitly stale under the upstream contract;
- `CONFLICTED_MARKET`: source or snapshot conflict remains unresolved.

The flags `LINE_PRICE_DISLOCATION`, `RAPID_MOVEMENT`, `MULTI_PROVIDER_DIRECTION_CONCENTRATION`, and `LATE_MOVEMENT` are disabled in v1 until market-specific predicates and thresholds are separately approved. They must not be guessed.

## 4. Interpretation states

The profile uses one of:

`NONE_OBSERVED`, `SIGNAL_PRESENT`, `MULTIPLE_SIGNALS`, `INSUFFICIENT_DATA`, `CONFLICTED`, or `BLOCKED`.

Missing or conflicting evidence lowers feature quality or blocks the profile. No state may be converted into certainty.

## 5. Required lineage

Each flag/profile retains exact market snapshot refs/hashes, provider/source identity, source and observation timestamps, cutoff/kickoff, config/mapping/generator identity, predicate inputs, basis refs, feature quality, and deterministic hashes. Corrections append a new revision and `supersedes_*` pointer.

## 6. Forbidden semantics

The following are never valid outputs:

- `trap_risk_score`;
- `heat_score`;
- `pressure_score`;
- `BOOKMAKER_INTENT_CONFIRMED`;
- `CERTAIN_TRAP`;
- `MANIPULATION_CONFIRMED`;
- betting recommendation;
- model confidence;
- Prediction or Score Engine output.
