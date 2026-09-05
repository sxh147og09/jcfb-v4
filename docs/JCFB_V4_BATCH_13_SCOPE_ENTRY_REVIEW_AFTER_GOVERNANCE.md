# JCFB V4 BATCH-13 Scope & Entry Review After Governance Resolution

Review type: post-governance re-review only
Workspace: `F:\Projects\jcfb-v4`
Review baseline: `85096b1`
Prior decision: BATCH-13 Entry Review BLOCKED
Governance decision: `docs/JCFB_V4_BATCH_13_MARKET_INTELLIGENCE_GOVERNANCE_DECISION.md`
Implementation status: V4-046/V4-047/V4-048 NOT IMPLEMENTED in this review

## Entry decision

**PASS — BATCH-13 READY FOR CONTINUOUS EXECUTION**

The former blocker is resolved. Versioned Market Intelligence contracts,
configuration, mapping, lifecycle, hash, state, source, and dependency
semantics are now explicit and consistent across the approved documents.

## 1. Objective and approved scope

BATCH-13 establishes the pre-Frozen Market Intelligence Feature Generation
layer. It transforms accepted official and external market snapshots into
typed, auditable market structure, movement, divergence, heat, pressure, and
anomaly evidence profiles. It does not run Prediction, Score Engine, Frozen
Input, or any public/promotion workflow.

Approved tasks, in acceptance order:

1. `V4-046` — Market Intelligence Engine 4.0 1.0
2. `V4-047` — Market Movement, Velocity & Divergence Features 1.0
3. `V4-048` — Market Heat & Trap-Risk Interpretation 1.0

No V4-049+, BATCH-14, or later task is included.

## 2. Dependency graph and data flow

Batch-level upstreams are BATCH-06, BATCH-07, and BATCH-10. The task-level
acceptance path is explicitly serial:

```text
V4-040 + V4-027 + V4-031
  -> V4-046
  -> V4-047
  -> V4-048
  -> BATCH-13 Closure Review
```

V4-027 and V4-031 supply time-normalized official/external odds snapshots;
V4-040 supplies the accepted Feature Bundle boundary. V4-046 establishes
market-intelligence artifacts, V4-047 consumes accepted same-source series,
and V4-048 consumes accepted movement/quality evidence. The Batch Plan's
parallel-development wording is limited to non-overlapping internal
preparation and cannot bypass the V4-047 prerequisite of V4-048.

## 3. Contract and semantic entry gates

- Active contracts/configuration are `market-intelligence-feature@1.0.0`,
  `market-movement@1.0.0`, `market-risk-interpretation@1.0.0`,
  `market-intelligence-config@1.0.0`, and
  `market-intelligence-mapping@1.0.0`.
- Every output binds canonical match identity, market/provider/source
  identity, exact snapshot refs/hashes, source/captured/observed/ingested
  times, cutoff/kickoff, generator/config/mapping identities, typed state or
  value, basis/source refs, quality, and deterministic hashes.
- `LATEST_ELIGIBLE` is cutoff-bounded and source-time ordered. Unknown time is
  blocked; post-cutoff information remains future/blocked; captured or
  ingested time cannot substitute for source availability time.
- Movement is same-provider, same-market, same-semantic-line only. Line and
  price movement are separate. Velocity and acceleration are time-normalized;
  insufficient series are explicit and never extrapolated.
- Official and external markets remain isolated. Numeric divergence is allowed
  only for official SPF versus external European 1X2 market-implied
  probability. RQSPF versus Asian Handicap and official Total Goals versus
  external O/U line remain structured `NOT_COMPARABLE` relationships.
- Provider contribution uses equal eligible observations only; no subjective
  bookmaker/provider weight or majority-as-truth rule is approved.
- Heat and pressure are multidimensional descriptive objects. Trap risk is a
  structural anomaly/evidence profile, never bookmaker intent, certainty, or a
  single score. Threshold-dependent flags remain disabled until separately
  governed.
- `feature_quality` expresses coverage, verification, freshness, completeness,
  conflict, and provenance only; it is not prediction confidence or betting
  confidence.
- Missing, unavailable, suspended, stale, conflicted, future, delayed, and
  blocked states remain explicit. No synthetic quote, default line/price,
  historical fallback, or silent coercion is permitted.
- Corrections are append-only with a new identity/output hash and explicit
  `supersedes` lineage.

## 4. Lifecycle and downstream boundary

BATCH-13 is pre-Frozen Market Feature Generation. It does not require or emit
`frozen_input_id`, `frozen_input_hash`, formal `engine-output@1.0.0`, Prediction,
Score Engine, recommendation, public output, or Promotion. V4-076 remains the
downstream Frozen Input task. BATCH-11 statistical features and BATCH-12
football-intelligence/context features are independent-by-reference siblings;
no cross-domain interaction is introduced by this entry review.

## 5. Impact and isolation

- Migration impact: none; no migration is added or applied.
- Production/Supabase impact: none; no reads or writes are authorized or
  performed.
- V3.3.3: strict isolation remains required; no V3.3.3 path or artifact may be
  modified or imported as a runtime dependency.
- Runtime, test, cache, and output paths remain on `F:\Projects\jcfb-v4`.
- BATCH-14 and BATCH-10+ downstream implementation are not entered by this
  review.

## 6. Acceptance criteria and blocking conditions

Each task must independently pass implementation, targeted tests, full
repository tests, contract/boundary audit, canonical identity audit,
time/cutoff audit, append-only audit, F-drive audit, V3.3.3 isolation audit,
acceptance evidence, DoD verification, and focused commit.

Execution must pause for test or DoD failure; missing canonical identity;
ambiguous provider/source/line/price/hash; implicit state conversion; future
data; unresolved time; cross-source misalignment; silent conflict selection;
subjective provider weighting; bookmaker-intent or trap-score semantics;
contract/enum/hash-boundary/major-version change; migration or Production/
Supabase access; V3.3.3 risk; incomplete evidence; or any scope expansion.

## Final gate

**BATCH-13 ENTRY GATE: PASS**

**BATCH-13 READY FOR CONTINUOUS EXECUTION**

This document records the fresh Entry Review only. V4-046/V4-047/V4-048
implementation has not started.
