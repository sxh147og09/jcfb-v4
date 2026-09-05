# JCFB V4 BATCH-13 MARKET INTELLIGENCE ARCHITECTURE & FEATURE SEMANTICS GOVERNANCE DECISION

Decision status: **APPROVED GOVERNANCE RESOLUTION**

Scope: BATCH-13 Entry Review blocker resolution only

Baseline: `9407350`
Workspace: `F:\Projects\jcfb-v4`

## 1. Decision

BATCH-13 is formally classified as a **pre-Frozen Market Feature Generation Layer**. V4-046, V4-047, and V4-048 are not formal Prediction Engine Runs and do not require or contain `frozen_input_id` or `frozen_input_hash`.

The approved path is:

```text
V4-040 + V4-027 + V4-031
        -> V4-046
        -> V4-047
        -> V4-048
        -> future quality / feature integration
        -> Frozen Input
        -> Prediction
```

The task-level dependency register controls acceptance order. The Batch Plan phrase that movement and risk components may develop in parallel is clarified to mean internal component preparation only; V4-048 cannot bypass its V4-047 acceptance dependency.

## 2. Blocker Resolution

The previous Entry Review was blocked because the repository had only high-level Market Intelligence names and architecture descriptions. This decision adds the missing versioned governance objects:

- `market-intelligence-feature@1.0.0`
- `market-movement@1.0.0`
- `market-risk-interpretation@1.0.0`
- `market-intelligence-config@1.0.0`
- `market-intelligence-mapping@1.0.0`

Their definitions are recorded in:

- `docs/V4_MARKET_INTELLIGENCE_FEATURE_CONTRACT.md`
- `docs/V4_MARKET_MOVEMENT_CONTRACT.md`
- `docs/V4_MARKET_RISK_INTERPRETATION_CONTRACT.md`
- `docs/V4_MARKET_INTELLIGENCE_CONFIG.json`
- `docs/V4_MARKET_INTELLIGENCE_MAPPING.json`

## 3. Approved v1 Semantics

- Official and external odds remain separate source roles.
- `OPENING`, `INTERMEDIATE`, `CURRENT`, `LATEST`, `FINAL`, and `CORRECTION` remain distinct.
- `LATEST_ELIGIBLE` is scoped to canonical match, market, provider/source, semantic line, and target cutoff.
- Movement is same-provider, same-market, same-semantic-line time-series analysis.
- Asian Handicap/O-U line movement and price movement are separate typed values.
- European 1X2 normalized market-implied probability is explicitly named `market_implied_probability`, never bare `probability`.
- Velocity is delta divided by elapsed hours.
- Acceleration requires at least three valid same-source snapshots; insufficient series remains `UNKNOWN` and is not extrapolated.
- Provider aggregation uses equal eligible provider contribution. No provider importance coefficient is approved.
- Median, IQR, MAD, eligible provider count, and direction agreement are approved descriptive aggregates.
- Official SPF versus external European 1X2 is the only v1 numeric official/external comparable mapping.
- RQSPF versus Asian Handicap and official Total Goals distribution versus external O/U line remain `NOT_COMPARABLE`.
- Heat and pressure are multidimensional/component objects, not single scores.
- Trap-risk is an evidence profile with structural anomaly flags, never bookmaker intent.
- `feature_quality` expresses data/evidence quality only and never prediction confidence.
- Default interaction remains `SEPARATE_DIMENSIONS_ONLY`.

## 4. Deliberately Disabled v1 Semantics

The following remain unavailable until a separately approved predicate/threshold contract exists:

- `LINE_PRICE_DISLOCATION`
- `RAPID_MOVEMENT`
- `MULTI_PROVIDER_DIRECTION_CONCENTRATION`
- `LATE_MOVEMENT`
- `heat_score`
- `pressure_score`
- `trap_risk_score`
- weighted bookmaker consensus
- provider importance coefficients
- bookmaker intent or certain-trap claims

This is intentional fail-closed behavior. A v1 implementation may emit raw continuous components and explicit insufficiency/conflict states, but may not invent arbitrary thresholds to claim feature completeness.

## 5. State, Time, and Append-only Rules

`AVAILABLE`, `UNAVAILABLE`, `SUSPENDED`, `UNKNOWN`, `NOT_VERIFIED`, `STALE`, `CONFLICTED`, `FUTURE_DATA`, and `BLOCKED` remain distinct. No old quote, other provider, official/external substitution, default line, default price, zero, average, or synthetic payload may fill a missing market.

Every pre-match feature satisfies the approved cutoff relationship. Unknown/conflicting time is blocked. Post-cutoff odds are `FUTURE_DATA` or `BLOCKED` and cannot enter the target feature. Corrections append a new artifact/revision/hash with an explicit supersedes pointer.

## 6. Independence and Downstream Boundary

Market Intelligence is independent-by-reference from BATCH-11 Statistical Strength and BATCH-12 Football Intelligence. It does not modify either output and no cross-dimension interaction is approved. BATCH-11 and BATCH-12 are sibling feature lines, not direct BATCH-13 prerequisites.

Market Intelligence output may later be consumed by approved downstream feature/quality layers and, much later, Frozen Input. This decision does not authorize BATCH-14, Prediction, Score Engine, Frozen Input, Shadow/Tier A, Public Page, Promotion, Deployment, Production/Supabase, or migration.

## 7. Versioning and Compatibility

The new contract/config/mapping identities are additive governance artifacts and start at `1.0.0`. Historical contracts remain unchanged. Any future change to state meaning, official/external isolation, required identity/time fields, formula, threshold, lifecycle, or hash boundary is a major semantic change and requires a new active version plus synchronized registry/dependency evidence.

## 8. Required Verification

The resolution is accepted only after contract consistency tests, dependency consistency and DAG checks, snapshot/time/state semantic tests, no-default/no-fallback tests, no-bookmaker-intent tests, deterministic hash checks, full repository tests, `git diff --check`, F-drive audit, Production/migration audit, and V3.3.3 isolation audit pass.

After those gates pass, BATCH-13 Scope & Entry Review must be rerun. Only a PASS result may authorize V4-046/V4-047/V4-048 implementation.

**Resolution output:** `BATCH-13 MARKET INTELLIGENCE BLOCKERS RESOLVED`

**Next gate:** Re-run `BATCH-13 Scope & Entry Review`
**Implementation status:** V4-046/V4-047/V4-048 remain **NOT IMPLEMENTED**
