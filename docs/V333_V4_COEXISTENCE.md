# JCFB V3.3.3 / V4 Coexistence Policy

Status: V4-001 COMPLETE

## Independent model definitions

JCFB V3.3.3
=
STABLE INDEPENDENT MODEL

JCFB V4.0
=
NEXT GENERATION INDEPENDENT MODEL

V4 does not cover, rename, replace, or rewrite V3.3.3 in place. Both model lines are intended to coexist for the long term. V3.3.3 remains a protected legacy production model; V4 develops in its own repository, configuration space, model-version namespace, prediction records, frozen-prediction records, review records, and sample system.

## Formal relationship

```text
Shared Objective Facts
├── JCFB V3.3.3
│   ├── Prediction
│   ├── Score Output
│   ├── Frozen Prediction
│   └── Review
└── JCFB V4
    ├── Prediction
    ├── Engine Outputs
    ├── Frozen Prediction
    └── Review
```

The shared-facts layer is not a shared-prediction layer. Every consumer must retain the producing model version and provenance.

## Facts that may be shared in the future

Only the following objective facts may be shared, subject to canonical identity, timestamp, provenance, and no-future-leakage checks:

- Canonical Match Identity
- Official Odds
- External Market Facts
- Official Results
- Other timestamp-protected objective match facts

Sharing a fact does not authorize sharing a derived prediction or conclusion. A fact that cannot be time-bounded or provenance-verified is `UNKNOWN` and must not enter a production run.

## Outputs that must remain isolated

The following must never be shared as model data or silently reused across V3.3.3 and V4:

- Prediction
- Model Output
- Frozen Prediction
- Confidence
- Review Conclusion
- Tier A Qualification
- Model Parameters

V3.3.3 historical records and frozen predictions are immutable from V4 work. V4 must create its own records even when both models evaluate the same canonical match.

## A/B comparison boundary

V3.3.3 and V4 may later produce independent predictions for the same match. A benchmark may compare them through shared canonical match identity, official odds, official result, and time-protected objective facts. The benchmark must not merge prediction records, model parameters, confidence, freeze state, or review conclusions.

## Bootstrap acceptance evidence

| Requirement | Evidence | Status |
|---|---|---|
| V3.3.3 remains independent | This policy and `AGENTS.md` | PASS |
| V4 has an independent boundary | Repository-local skeleton and namespace policy | PASS |
| Shared data is limited to objective facts | Shared-facts and isolation sections above | PASS |
| Derived outputs remain isolated | Output isolation section above | PASS |
| No V3 mutation in this bootstrap | Git-scoped V4-only change | PASS |
