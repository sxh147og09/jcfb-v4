# JCFB V4 BATCH-13 Execution Manifest

Manifest status: **FROZEN**
Workspace: `F:\Projects\jcfb-v4`
Branch: `main`
Execution baseline: `b746bf0`

This manifest records the immutable BATCH-13 execution boundary. The
implementation run did not change contract versions, config semantics,
mapping semantics, thresholds, windows, enums, normalization, provider
weighting, or hash boundaries.

## Approved scope and order

```text
V4-046 -> V4-047 -> V4-048 -> BATCH-13 Closure Review
```

Approved tasks:

- `V4-046` — Market Intelligence Engine 4.0 1.0
- `V4-047` — Market Movement, Velocity & Divergence Features 1.0
- `V4-048` — Market Heat & Trap-Risk Interpretation 1.0

No V4-049+, BATCH-14, BATCH-15, or other downstream task is included.

## Direct dependencies

```text
V4-040 + V4-027 + V4-031 -> V4-046 -> V4-047 -> V4-048
```

Upstream data is consumed only through accepted, canonical, typed references:

- V4-020 canonical match identity;
- V4-024/V4-026/V4-027 official odds and provenance;
- V4-028/V4-029/V4-030/V4-031 external market snapshots;
- V4-040 Feature Bundle boundary for upstream identity/lineage.

BATCH-11 and BATCH-12 remain independent-by-reference. No cross-domain
interaction is enabled by this manifest.

## Active versions and hashes

- `market-intelligence-feature@1.0.0`
- `market-movement@1.0.0`
- `market-risk-interpretation@1.0.0`
- `market-intelligence-config@1.0.0`
- `market-intelligence-mapping@1.0.0`
- config hash: `sha256:e27a33f6b0d3b60dcab739b83e24cbeff8b4e94fcf2b3f8d5d553f5e5c66e3d2`
- mapping hash: `sha256:5acc53a615b00d88abd70b64b81a612adfa9964866bc07316f19f8192faf60bb`
- hash profile: SHA-256 over V4 canonical JSON

## Fixed semantics

- lifecycle: `PRE_FROZEN_MARKET_FEATURE_GENERATION`;
- source availability time is authoritative;
- `LATEST_ELIGIBLE` is scoped to canonical match, market, provider/source,
  semantic line, and cutoff;
- official/external roles remain isolated;
- movement series require same provider/source and market; price movement
  requires same semantic line;
- line movement and price movement remain separate;
- velocity is delta divided by elapsed hours;
- acceleration requires three consecutive valid same-source snapshots;
- provider aggregation is `EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION`;
- numeric divergence is allowed only for official SPF versus external European
  1X2 market-implied probability;
- all other unapproved comparisons remain structured `NOT_COMPARABLE`;
- heat is multidimensional, pressure is component-only, and trap-risk is an
  evidence profile;
- no bookmaker-intent assertion, certainty, arbitrary score, or hidden
  provider weight;
- `feature_quality` expresses data/evidence quality only;
- corrections are append-only with explicit `supersedes` lineage;
- `SEPARATE_DIMENSIONS_ONLY` remains the interaction policy.

## Fixed prohibitions

- no `frozen_input_id` or `frozen_input_hash`;
- no Prediction, Score Engine, recommendation, betting advice, Shadow/Tier A,
  Public Page, Promotion, or Deployment;
- no V4-049+ or BATCH-14 implementation;
- no Production/Supabase reads or writes;
- no migration add/apply;
- no V3.3.3 modification;
- no C-drive runtime, test, cache, or output paths.

## Acceptance gates

Each task must independently pass implementation, targeted tests, full
repository tests, contract/schema audit, canonical identity audit,
snapshot/time/cutoff audit, official/external isolation audit, no-fallback
audit, deterministic replay/hash audit, append-only audit, Prediction/Score/
Frozen boundary audit, V3.3.3 isolation, F-drive audit, acceptance evidence,
DoD verification, and focused Git commit.

Any test/DoD failure, contract/config/mapping drift, ambiguous identity/time,
implicit state conversion, future-data leakage, synthetic/default fallback,
unapproved comparison/threshold/weight, Production/Supabase access,
migration, V3.3.3 coupling, incomplete evidence, or scope expansion is a
mandatory pause condition.
