# JCFB V4.0 Shared Objective Facts Contract

Status: V4-004 COMPLETE

## 1. Contract purpose

The Shared Objective Facts Layer is a read-only factual boundary that can support both JCFB V3.3.3 and JCFB V4. Facts may be shared. Derived explanations, predictions, model outputs, confidence, review conclusions, qualification decisions, and model parameters may not be shared.

This contract defines source-of-truth ownership, required provenance, time eligibility, availability states, and isolation rules. It does not define a database schema.

## 2. Shareable objective facts

The following fact classes are shareable when identity, timestamp, provenance, and integrity checks pass:

### SHAREABLE

- Canonical Match Identity
- Competition
- Kickoff Time
- Timezone
- Home Team
- Away Team
- Official Handicap
- China Sports Lottery Official Odds: SPF, RQSPF, Total Goals, Exact Score, Half-Full
- Market Availability
- Opening Snapshot
- Intermediate Snapshot
- Current Snapshot
- Latest Snapshot
- Final Snapshot
- External Market Facts: European 1X2, Asian Handicap, Over / Under
- Team / Match Facts: injuries, suspensions, lineup status, coach, schedule, weather, pitch
- Official Result
- Other objective facts that retain time and source boundaries

Sharing a fact does not share the interpretation made from that fact. Every consumer must preserve the fact snapshot identity it read.

## 3. Non-shareable derived artifacts

### NON_SHAREABLE

- Prediction
- Model Output
- Engine Output
- Frozen Input
- Frozen Prediction
- Confidence, uncertainty, risk, or abstention decision
- Review Conclusion
- Match Explanation
- Tier A Qualification
- Model Parameters
- Engine Configuration
- Implementation Hash as a model identity
- Calibration decision or Promotion Review

V3.3.3 and V4 may benchmark these artifacts side by side, but they must not merge, overwrite, or use one model's derived artifact as the other's model input.

## 4. Source-of-truth ownership

| Fact class | Source-of-truth owner | Consumer rule |
|---|---|---|
| Canonical Match Identity | Canonical identity authority established by the data layer | V3.3.3 and V4 read the same identity; unresolved collisions are blocked |
| Competition | Official competition metadata or explicitly attributed source | Preserve source and effective time |
| Kickoff / Timezone | Official schedule authority, with source-specific fallback only when attributed | Store timezone and cutoff interpretation explicitly |
| Home / Away Team | Canonical identity authority plus official fixture source | No model may infer a team identity from its own output |
| Official Handicap | China Sports Lottery official source | Preserve exact snapshot and source timestamp; never rewrite |
| Official China Sports Lottery Odds | China Sports Lottery official source | Missing market is `UNAVAILABLE`; no fabrication or cross-market substitution |
| Market Availability | Official intake and quality layer | Availability is a fact about the snapshot, not a predicted value |
| External Market Facts | Attributed external market source | May inform Market Intelligence; never relabeled as official odds |
| Team / Match Facts | Attributed source per claim | Conflicts and expiry remain visible in Evidence Graph |
| Official Result | Official result authority | Post-match only for model evaluation and review |

The shared layer owns facts and provenance. It does not own V3.3.3 or V4 predictions.

## 5. Required fact metadata

Every shareable fact or snapshot must support the following metadata:

| Field | Meaning | Required rule |
|---|---|---|
| `source` | Originating organization, feed, screenshot, or record | Must be attributable; `UNKNOWN` blocks formal use |
| `source_timestamp` | Timestamp associated with the source observation or publication | Must be timezone-aware or explicitly unresolved |
| `observed_at` | Time the fact was observed or captured | Used in future-information checks |
| `ingested_at` | Time the system accepted the record | Audit metadata; never replaces availability time |
| `confidence` | Confidence in the fact record, not a prediction probability | Must be separate from model confidence |
| `provenance` | Evidence chain and source details | Must permit replay of the source snapshot |
| `hash` | Integrity identity of the exact fact payload | Must change when the payload changes |

Where the source supplies publication and observation times separately, both are retained. A missing or contradictory time is recorded as `UNKNOWN` or `CONFLICT`, not guessed.

## 6. Availability and conflict states

The contract uses explicit states:

- `AVAILABLE` — the fact is present, attributable, and eligible for the declared cutoff
- `UNAVAILABLE` — the market or context was not supplied; no substitute is created
- `UNKNOWN` — the system cannot establish a required property
- `CONFLICT` — sources disagree and the conflict has not been resolved
- `STALE` — the fact exceeds the declared freshness policy
- `FUTURE_DATA` — the fact was not eligible at the pre-match cutoff
- `BLOCKED` — a quality or governance gate prevents use

These states are factual data-quality states. They are not model predictions and must not be converted into a forced probability.

## 7. Time and no-future-leakage contract

Each pre-match run declares `cutoff_at`. A fact is eligible only if its defensible availability time is at or before the cutoff and its identity matches the canonical fixture. `published_at`, `source_timestamp`, and `observed_at` are considered according to source semantics; `ingested_at` alone is insufficient.

The following are prohibited in a pre-match shared snapshot:

- Official Result or post-match statistics
- Post-kickoff lineup or event facts that were unavailable at cutoff
- Future odds snapshots
- Review conclusions or calibration outcomes
- Facts backfilled from a later source without the original availability time

The result source is shareable as an objective fact only after the match and only for the postmatch path.

## 8. Read boundary for V3.3.3 and V4

```text
Shared Objective Facts (read-only)
├── JCFB V3.3.3 fact reader
│   └── V3.3.3-owned features, prediction, freeze, and review
└── JCFB V4 fact reader
    └── V4-owned features, engines, prediction, freeze, and review
```

Both readers may use the same canonical fact snapshot and official odds snapshot. Their downstream feature hashes, model versions, engine configurations, input hashes, output hashes, Frozen Input records, Frozen Predictions, and reviews remain separate.

## 9. Hash and reproducibility contract

At minimum, a model run references:

- canonical fact snapshot hash
- exact odds snapshot hash(es)
- evidence or context references
- `feature_snapshot_hash`
- `frozen_input_hash`
- model or engine version
- implementation hash
- config hash
- input hash
- output hash

The same `frozen_input_hash` is required for valid Production / Shadow / Experiment A/B comparisons. A different fact snapshot, feature bundle, cutoff, or configuration is a different run even when the match identity is the same.

The full V4 run identity, including dataset/schema/migration versions, role-scoped revisions, and hash canonicalization, is defined in `docs/V4_VERSION_IDENTITY_CONTRACT.md` and must remain private to the consuming model line.

## 10. Isolation and benchmark rules

V3.3.3 and V4 may produce independent predictions for the same canonical match. A Cross-Version Benchmark may read both frozen records and the official result to calculate comparison metrics. It must not:

- copy V3.3.3 predictions into V4
- copy V4 predictions into V3.3.3
- share confidence or Tier A labels
- modify historical Frozen Prediction
- use a benchmark result as a pre-match feature
- allow one model's parameters to become the other's parameters

## 11. Evidence and correction rules

Corrections to objective facts are append-only observations with source, timestamp, reason, and new hash. A correction after a run does not silently rewrite that run's Frozen Input. The original fact snapshot remains available for reproducibility, and a later run must receive a new input identity.

For team or tactical facts, the Evidence Graph additionally records claim, published time, retrieval time, valid-from, expiry, confidence, contradiction state, and evidence hash. Unsupported, expired, or contradictory claims cannot silently become valid shared facts.

## 12. Contract acceptance

The contract is satisfied when:

1. shareable and non-shareable classes are explicit
2. every fact has source and time metadata
3. official odds and external facts remain distinguishable
4. missing markets are explicit and never fabricated
5. V3.3.3 and V4 share facts only through a read-only boundary
6. downstream predictions and model outputs remain isolated
7. future-information risk is a hard gate
8. fact corrections preserve old snapshot hashes
