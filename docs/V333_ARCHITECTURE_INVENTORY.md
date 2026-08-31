# JCFB V3.3.3 Architecture Inventory

Status: V4-003 ARTIFACT VALIDATED; INITIAL COMMIT BLOCKED

## Purpose and evidence boundary

This document defines what V4 may inherit as a concept, what must be upgraded, what is reference-only, and what must not be inherited as an implementation. It is an inheritance boundary, not a claim that every V3.3.3 implementation or parameter is fully reproducible.

The V3.3.3 production system, historical records, frozen predictions, reviews, and parameters remain protected. Any legacy detail that is not directly evidenced, time-bounded, and reproducible is `UNKNOWN` and cannot be copied into V4 Production.

## Classification

- **A. DIRECT_INHERIT** — preserve the architectural invariant, while implementing it in V4-owned code and data boundaries.
- **B. UPGRADE** — retain the problem definition, but redesign, isolate, or extend it for V4.
- **C. REFERENCE_ONLY** — use as research or design context only; do not treat the legacy implementation as V4 Production evidence.
- **D. DO_NOT_INHERIT_IMPLEMENTATION** — do not copy the legacy artifact, parameter set, hidden behavior, or unverified production dependency.

## Capability inventory

| # | Capability | Class | V4 disposition and evidence requirement |
|---:|---|---|---|
| 1 | Canonical Match Identity | A. DIRECT_INHERIT | Preserve canonical identity and stable match keys; V4 must own the implementation and validate collisions. |
| 2 | Match Time / Timezone | A. DIRECT_INHERIT | Preserve explicit timezone and cutoff semantics; reject ambiguous timestamps. |
| 3 | Official Screenshot Intake | A. DIRECT_INHERIT | Preserve screenshot intake as an evidence path; retain source and capture time. |
| 4 | Opening / Latest Odds Snapshot | A. DIRECT_INHERIT | Preserve snapshot distinction and timestamp order; never use a future snapshot. |
| 5 | 体彩五大玩法 | B. UPGRADE | Preserve the five-market scope, but build independent V4 market models and availability handling. |
| 6 | Market Availability | A. DIRECT_INHERIT | Missing or unavailable markets remain explicit; no inferred official odds. |
| 7 | Official Odds Gate | A. DIRECT_INHERIT | Keep a pre-run gate for official odds presence, validity, and cutoff eligibility. |
| 8 | Odds Hash / Provenance | A. DIRECT_INHERIT | Preserve integrity and source metadata; V4 must hash the exact accepted snapshot. |
| 9 | Audit Ledger | A. DIRECT_INHERIT | Preserve append-only auditability; V4 records must remain separate from V3.3.3. |
| 10 | Production Model Registry | B. UPGRADE | Build a V4-owned registry with explicit Production, Shadow, and Experiment states. |
| 11 | Team Context | B. UPGRADE | Retain team facts while adding cutoff, source, freshness, and confidence metadata. |
| 12 | Five Market Prediction Structure | B. UPGRADE | Preserve the output contract concept while isolating each V4 market model and version. |
| 13 | Score Engine 2.0 | B. UPGRADE | Retain score modeling as a first-class engine; parameters and implementation must be rebuilt and evidenced. |
| 14 | λ Home / Away | B. UPGRADE | Retain home/away scoring-rate concepts only with an independently specified V4 estimation path. |
| 15 | Goal Distribution | B. UPGRADE | Rebuild distributions with documented inputs, calibration, and leakage tests. |
| 16 | Score Distribution | B. UPGRADE | Rebuild the distribution output and preserve uncertainty instead of copying opaque values. |
| 17 | BTTS | B. UPGRADE | Keep as an independently derived market output with its own validation and availability state. |
| 18 | Clean Sheet | B. UPGRADE | Keep as an independently derived output; document assumptions and calibration. |
| 19 | Exact Score Top2 | B. UPGRADE | Keep the Top2 contract only after V4 score-distribution validation; no legacy ranking is copied. |
| 20 | Frozen Prediction | A. DIRECT_INHERIT | Preserve immutable pre-match freeze semantics in a V4-owned record. |
| 21 | Final Freeze Gate | A. DIRECT_INHERIT | Preserve the final gate and record rejection reasons when prerequisites fail. |
| 22 | No Future Leakage | A. DIRECT_INHERIT | Preserve as a hard invariant with reproducibility and cutoff tests. |
| 23 | Shadow Model Framework | B. UPGRADE | Retain the shadow concept but make output class, promotion, and comparison boundaries explicit. |
| 24 | Tier A Samples | D. DO_NOT_INHERIT_IMPLEMENTATION | Do not import V3.3.3 Tier A samples or qualification labels; V4 must define its own sample policy later. |
| 25 | Postmatch Review | A. DIRECT_INHERIT | Preserve result-linked review as a separate post-match lifecycle, never as pre-match input. |
| 26 | Error Attribution | B. UPGRADE | Extend attribution to engine, market, data, calibration, and process causes. |
| 27 | League Calibration | B. UPGRADE | Rebuild calibration by league and time window with sample-size and drift controls. |
| 28 | Market Movement | B. UPGRADE | Retain movement as timestamped market intelligence, separated from future information. |
| 29 | Upset Engine | B. UPGRADE | Rebuild as an uncertainty-aware component with explicit abstention and evidence. |
| 30 | Consistency Engine | B. UPGRADE | Rebuild cross-output consistency checks without inheriting hidden thresholds. |
| 31 | Confidence / Abstention | B. UPGRADE | Preserve the need for confidence and abstention, with V4 calibration and audit fields. |
| 32 | Public Read Layer | B. UPGRADE | Preserve a separated presentation layer that cannot mutate model or frozen records. |
| 33 | Data Center | A. DIRECT_INHERIT | Preserve centralized objective-fact access, with V4-owned schemas and provenance. |
| 34 | Incremental Publish | B. UPGRADE | Rebuild publication stages around freeze gates, idempotency, and immutable history. |
| 35 | Performance / Reuse logic | B. UPGRADE | Retain safe reuse principles while validating cache keys, versioning, and invalidation. |

## Mandatory reference-only rule

**Score Engine 2.3 Shadow Revision 1 = C. REFERENCE_ONLY.**

Its research ideas may inform future V4 design, but the old implementation, parameters, thresholds, and claimed reproducibility must not be assumed. No part of it may be promoted into V4 Production without a separately specified implementation and validation record.

## Cross-cutting do-not-inherit boundary

Regardless of the capability class above, V4 must not inherit any unverified V3.3.3 implementation artifact, hidden parameter, undocumented threshold, historical Tier A label, frozen prediction, review conclusion, or production dependency. Such artifacts are **D. DO_NOT_INHERIT_IMPLEMENTATION** and remain `UNKNOWN` until independently specified and validated.

## V4-003 acceptance evidence

| Requirement | Evidence | Status |
|---|---|---|
| Four classes are defined | Classification section | PASS |
| Required capabilities are inventoried | Items 1–35 table | PASS |
| Score Engine 2.3 Shadow Revision 1 is reference-only | Mandatory rule section | PASS |
| Unknown or incomplete legacy details are not copied | Evidence boundary and D boundary | PASS |
| V3.3.3 remains protected | Repository governance and coexistence policy | PASS |
