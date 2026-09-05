# JCFB V4 Market Movement Contract 1.0

Status: **BATCH-13 GOVERNANCE RESOLUTION — APPROVED FOR V4-047**
Contract version: `market-movement@1.0.0`

## 1. Alignment boundary

Movement is computed only within the same canonical `match_id`, provider/source, market, semantic selection, and semantic line. Different providers are not adjacent points in one time series. A source's availability time is authoritative for eligibility; `captured_at`, `retrieved_at`, and `ingested_at` cannot replace it.

The ordered series uses eligible source time, then captured time, then stable snapshot hash. Unknown or conflicting time is `BLOCKED`. Post-cutoff data is `FUTURE_DATA` or `BLOCKED` and is excluded from the target feature set.

## 2. Movement types

Every movement object declares `movement_type` and carries `line_before`, `line_after`, `price_before`, `price_after`, `elapsed_hours`, provider/source, snapshot refs/hashes, and basis refs.

- `PRICE_MOVEMENT`: price changes while the semantic line/selection is unchanged.
- `LINE_MOVEMENT`: `line_after - line_before` for Asian Handicap or O/U.
- `IMPLIED_PROBABILITY_MOVEMENT`: normalized market-implied probability change for European 1X2.

An Asian Handicap line change such as `-0.5 -> -0.75` and a price change such as `0.92 -> 0.84` remain separate typed observations. They must not be merged into an opaque single movement.

## 3. European 1X2 normalization

For a valid same-snapshot European 1X2 quote:

```text
raw_i = 1 / decimal_odds_i
market_implied_probability_i = raw_i / sum(raw_H, raw_D, raw_A)
```

The field is named `market_implied_probability`. The unqualified field name `probability` is forbidden because it can be confused with model prediction probability. These values are market-derived representations, not model outputs.

## 4. Velocity and acceleration

For each approved observable component:

```text
velocity = value_delta / elapsed_hours
```

Separate velocity components are retained for price, market-implied probability, Asian Handicap line, and O/U line. `elapsed_hours <= 0` is `BLOCKED`. No silent time substitution, bucket such as “fast”, extrapolation, or default is allowed.

Acceleration is permitted only with at least three valid same-source snapshots. It is the adjacent velocity delta divided by the elapsed hours between the two velocity points. Fewer than three valid snapshots produces `UNKNOWN` with reason `INSUFFICIENT_SERIES`; no extrapolation is performed.

## 5. Provider aggregates

Only eligible, semantically comparable, non-stale, non-blocked observations participate. V1 uses `EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION`; no provider importance coefficient is emitted. Approved descriptive aggregates are median, IQR, MAD, eligible provider count, and direction agreement count/rate. A majority is not truth, and weighted bookmaker consensus is forbidden.

Source confidence is used only for source/evidence eligibility and `feature_quality`. It is never copied into prediction confidence or treated as a probability.

## 6. Official/external divergence

Numeric divergence is permitted only for an approved comparable mapping. V1 permits official SPF versus external European 1X2 normalized market-implied probabilities. The divergence object must retain official refs/hashes, external eligible consensus refs/hashes, semantic mapping, aligned timestamps, and cutoff identity.

Unmapped comparisons produce `NOT_COMPARABLE` with the structured relationship preserved. RQSPF versus Asian Handicap and official Total Goals distribution versus O/U line are not silently forced into one numeric object.

## 7. Failure semantics

Missing, suspended, delayed, stale, conflicted, future, unavailable, or ambiguous snapshots remain explicitly represented or block the affected feature. A previous value or another provider cannot be used as a current replacement. Corrections append new movement/revision objects and retain the predecessor through `supersedes_*`.
