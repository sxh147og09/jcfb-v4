# JCFB V4 BATCH-11 Statistical Historical Input Governance Decision

Decision ID: `V4-011-ADR-001`
Status: `APPROVED / BLOCKER RESOLVED`
Decision date: `2026-09-04`
Baseline: `BATCH-10 COMPLETE / CLOSURE GATE PASS`; BATCH-11 Entry Review was blocked

## 1. Decision

Historical Official Results and historical match statistics remain `POSTMATCH_ONLY` for their own source match. They may be selected as pre-match statistical inputs for a different later target match only through `historical-statistical-input@1.0.0` and only when the target-cutoff eligibility predicate passes.

The source/target distinction is mandatory:

```text
source_match_id != target_match_id
source result/statistic remains postmatch for source match
source observation is canonical/evidence-backed and hashable
availability_at <= target_prediction_cutoff_at < target_kickoff_at
revision visible at target cutoff is retained
target match result/statistics are never eligible for target pre-match features
```

This resolves the prior ambiguity without changing the meaning of the existing source-match lifecycle states.

## 2. Contract decision

The new contract is:

`historical-statistical-input@1.0.0`

at [V4 Statistical Historical Input Contract](<F:/Projects/jcfb-v4/docs/V4_STATISTICAL_HISTORICAL_INPUT_CONTRACT.md>).

It defines the target-scoped manifest, exact historical observation fields, availability predicate, sample policy, sparse behavior, rolling/decay rules, competition/season scope, home/away handling, normalization, correction lineage, replay, and output boundary.

The existing Shared Facts, Time, Data Flow, Data Lifecycle, Data Contract, and Feature Bundle documents receive explicit cross-match clarification. Existing source-match enums and hash profiles are not renamed or reinterpreted. No old contract is overwritten and no migration is required.

## 3. Approved baseline configuration

The approved baseline is `statistical-strength-config@1.0.0`, recorded in [V4 BATCH-11 Statistical Historical Input Config](<F:/Projects/jcfb-v4/docs/V4_BATCH_11_STATISTICAL_HISTORICAL_INPUT_CONFIG.json>). Its canonical payload hash is `sha256:eadb7e85c4e170ba922f4a5a404e1f28861951c954bb8c1c06ea90ad3ceaf653`.

It fixes:

- minimum samples by feature family;
- no numeric value below the applicable minimum;
- explicit `UNKNOWN` / `INSUFFICIENT_SAMPLE` sparse semantics;
- maximum 20 eligible matches or 730 days;
- exponential rank decay with a 10-match half-life;
- competition-season baseline scope;
- explicit competition mapping requirement;
- neutral and unknown venue semantics;
- explicit promotion/relegation transition requirement.

The config version and hash are part of every BATCH-11 generator input identity. Any parameter, weight, prior, transition, threshold, horizon, unit, or normalization change requires a new config/version identity under the V4 Versioning Standard.

## 4. Feature Bundle relationship

The active `feature-bundle@2.0.0` contract remains the representation boundary. BATCH-11 statistical features may reference the exact historical manifest and its observation IDs/hashes through their source/derivation lineage, while the bundle's existing canonical fact references and `input_hash` retain the accepted source identities and hashes. No Frozen Input is introduced upstream.

## 5. Dependency and scope decision

The approved task graph remains unchanged:

```text
BATCH-10 / V4-040
       ├── V4-041
       └── V4-042
             \  /
              V4-043
```

No edge to BATCH-12, BATCH-15, V4-076, Prediction, Score Engine, or Frozen Input is added.

## 6. Boundary decisions

- No V4-041/V4-042/V4-043 implementation is included in this governance decision.
- No Prediction, Score Engine, betting recommendation, Shadow, Tier A, Public Page, Promotion, or Deployment is authorized.
- No Production/Supabase read or write is authorized.
- No migration is added or applied.
- V3.3.3 remains a protected independent model line and is not a valid V4 historical input source.
- Historical manifests, observations, corrections, and feature outputs are append-only.

## 7. Acceptance gate

The blocker is resolved only after:

1. contract consistency tests pass;
2. historical target eligibility and self-result leakage tests pass;
3. future/cutoff, sparse/missing, conflict, revision, and hash tests pass;
4. documentation and dependency consistency audits pass;
5. full repository tests pass;
6. `git diff --check` passes;
7. Production/migration/V3.3.3 isolation audits pass;
8. BATCH-11 Scope & Entry Review is re-run read-only.

Only a PASS from that re-review authorizes V4-041/V4-042/V4-043 implementation.
