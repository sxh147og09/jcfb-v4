# JCFB V4 Constitution 1.0

Status: V4-005 GOVERNANCE ARTIFACT

## Authority and scope

This Constitution is the highest governance rule for JCFB V4. It binds every Production Model, Shadow Model, Experiment, Data Pipeline, Score Engine, Simulation, Calibration process, Postmatch Review, Tier A process, Promotion process, Public Web projection, Codex Agent, and Human Operator.

If an implementation, instruction, convenience, performance optimization, or human preference conflicts with this Constitution, the Constitution wins. A conflict is recorded as `BLOCKED` until formally resolved through a new, auditable governance decision.

This document defines integrity and governance rules. It does not implement a model, select Production parameters, create a database schema, run a prediction, or authorize V4-006.

## Article 1 — Truth Before Prediction

**Verified Data First.** V4 must never invent a value to make a prediction possible.

The system must not guess missing odds, fabricate an official market, fabricate a starting lineup, fabricate injuries or suspensions, fabricate a handicap, fabricate match time, fabricate a result, or backfill a historical Shadow Output that was never produced.

If a fact is unknown or unavailable, the system records one of `UNKNOWN`, `UNAVAILABLE`, `BLOCKED`, or `NOT_VERIFIED` with provenance and a reason. It does not fill the field with a guess, average, stale value, or plausible-looking placeholder.

## Article 2 — Objective Facts and Model Interpretation Separation

`OBJECTIVE FACT` and `MODEL INTERPRETATION` are different data classes and different ownership boundaries.

For example, “odds moved from 1.80 to 1.65” is a fact when the two snapshots are sourced and timestamped. “The bookmaker deliberately induced funds” is not a fact; it may only be a `MODEL RISK INTERPRETATION` with uncertainty and evidence references.

No interpretation, prediction, or review conclusion may overwrite, relabel, or retroactively alter the objective facts layer.

## Article 3 — No Future Information

The formal pre-match boundary is:

```text
input_timestamp <= prediction_cutoff_time < kickoff_at
```

Pre-match inputs must be available by the declared cutoff. The following are forbidden in a pre-match run: odds after the cutoff or after kickoff, match events, post-match lineup confirmation, post-match injuries, post-match xG, post-match statistics, red-card results, goal times, final scores, and post-match media analysis.

If any future information enters a run:

```text
FUTURE_INFORMATION_LEAKAGE = TRUE
RUN_INVALID = TRUE
TIER_A_ELIGIBLE = FALSE
PROMOTION_EVIDENCE = FALSE
```

Deleting the evidence cannot restore eligibility. The invalid run and its evidence remain auditable.

## Article 4 — Immutable Frozen Input

`Frozen Input 4.0` becomes immutable when formed. It must reference match identity, exact odds snapshots, market snapshots, team context, Evidence Graph claims, feature snapshot, engine versions, configurations, and prediction cutoff.

The record produces `frozen_input_hash`. Production and Shadow in the same A/B comparison must use the same `frozen_input_hash`; otherwise `PAIR_INVALID = TRUE`. An Experiment must also declare its input identity and may not silently substitute a different snapshot.

## Article 5 — Immutable Frozen Prediction

A formal Frozen Prediction is append-only and never updated in place. Probability, score, confidence, market direction, risk, model version, and historical result cannot be changed to match a later outcome.

If a new pre-match version is genuinely required before the applicable freeze boundary, it creates a new revision containing `supersedes_prediction_id`. Every earlier revision remains permanently available with its original input, output, and audit trail.

## Article 6 — No Outcome Fitting

After a result is known, V4 must not modify historical parameters, outputs, sample qualification, selected failures, retained hits, lambdas, historical Score Top2, or historical Market Interpretation to improve apparent performance.

Any parameter, feature, selector, calibration, or weighting change is a `FUTURE MODEL VERSION` and must not rewrite the past. Historical failures cannot be excluded merely because they are inconvenient.

## Article 7 — Reproducibility

Every formal Engine Run must support:

```text
model_version
engine_version
implementation_hash
config_hash
input_hash
output_hash
run_at
runtime_environment
```

Same implementation, same configuration, and same Frozen Input must produce the same deterministic output. Runs containing randomness must additionally store `random_seed` and `simulation_version` so that the stochastic result can be replayed.

## Article 8 — Explicit Model Versioning

“Latest model”, “the model just changed”, and “the current version” are not auditable identities. Every model and engine must identify `model_name`, `major`, `minor`, `patch`, `revision`, `engine_version`, `config_version`, and `status`.

Examples include `JCFB V4.0.0`, `Score Engine 4.0.0`, and `Exact Score Selector 4.0.0`. A parameter, feature, algorithm, selector, threshold, or calibration change cannot remain under the same version identity silently.

## Article 9 — No Silent Defaults

When key data is missing, V4 must not silently use zero, an average, the previous match value, a default team state, fabricated odds, or an assumed complete lineup.

A default is permitted only when it is formally defined, versioned, recorded in configuration, written to the audit record, and explicitly allowed by the model contract. Otherwise the value remains `UNKNOWN`, `UNAVAILABLE`, or `BLOCKED`.

## Article 10 — Official Odds Integrity

The five China Sports Lottery markets are:

- SPF
- RQSPF
- Total Goals
- Exact Score
- Half-Full

Each market must support `AVAILABLE` and `UNAVAILABLE`. If an official market is not on sale or not supplied, `market_available = FALSE` and `unavailable_reason` are required. V4 must never create odds merely because an engine needs an input, and external odds must never be relabeled as official odds.

## Article 11 — Timestamp Integrity

Critical records distinguish `source_timestamp`, `published_at`, `observed_at`, `ingested_at`, `run_at`, `frozen_at`, and `reviewed_at`. Kickoff Time, Screenshot Time, Odds Time, Prediction Time, Freeze Time, and Public Page Time are not interchangeable.

`canonical_latest_update_at` may be derived only from the maximum real business-data update time covered by the projection. Page build time cannot be used as a data update time.

## Article 12 — Provenance First

Critical inputs support `source`, `source_type`, `source_reference`, `observed_at`, `confidence`, and `hash`. Important information whose source cannot be confirmed must not be marked `HIGH_CONFIDENCE` and must not silently enter a formal Production run.

## Article 13 — Production / Shadow / Experiment Isolation

V4 defines three roles:

- `PRODUCTION` — the only formal prediction source.
- `SHADOW` — a pre-match comparison run that cannot affect formal output.
- `EXPERIMENT` — a research run that cannot appear in Production Output.

Shadow cannot cover Production, modify Frozen Prediction, auto-deploy, or rerun after the result and present the result as a pre-match output. Experiment cannot silently alter Production configuration, thresholds, or public output.

## Article 14 — Promotion Requires Evidence

No Engine or Model is promoted because of one good match, a short hit streak, human intuition, a sudden Top2 hit, or user preference.

Promotion requires Frozen Forward Samples, Statistical Evaluation, Calibration Evaluation, Integrity Audit, No Future Leakage Audit, Regression Test, Performance Test, and Promotion Review. `MANUAL_APPROVAL_REQUIRED` is the default. `AUTO_PROMOTION = TRUE` is prohibited.

## Article 15 — Forward Evaluation First

Promotion evidence prioritizes a `FORWARD FROZEN DATASET`. Historical backtesting is supporting evidence only and cannot replace a genuine pre-match Shadow Run. A Shadow Prediction generated only after the match cannot be recorded as Forward Tier A evidence.

## Article 16 — Tier A Integrity

V4 Tier A restarts at `V4 Tier A Sample #001`. A candidate requires Frozen Input, Production Output, Shadow Output when required, all outputs pre-kickoff, Official Result, no future leakage, implementation hash, config hash, input hash, output hash, and a passing completeness gate.

If qualification fails, a human may not relabel the sample as Tier A. V3.3.3 Tier A numbers, labels, and records are not V4 samples.

## Article 17 — Probability Is Not Confidence

`Home Win Probability = 70%` does not mean `Confidence = 70%`. Confidence separately considers data quality, model agreement, market conflict, context uncertainty, calibration reliability, and simulation variance.

The system must preserve:

```text
Probability != Confidence != Recommendation Strength
```

## Article 18 — Abstention Is Valid

The model may return `PASS`, `NO STRONG RECOMMENDATION`, `BLOCKED`, or `INSUFFICIENT_DATA`. No process may force every match to produce a “稳胆”, a high-confidence direction, or a betting recommendation.

## Article 19 — Independent Five-Market Modeling

SPF, RQSPF, Total Goals, Exact Score, and Half-Full use independent prediction engines before cross-market checks. SPF Home Win cannot mechanically generate the other four markets.

The required ordering is:

```text
Independent Prediction First
Consistency Check Second
```

## Article 20 — Score Independence

Exact Score must originate from a score probability distribution. “Home Win therefore 2:0” is not an acceptable score-generation method.

Score Distribution and Score Selector are separate. Selection may choose candidates from a distribution, but it may not rewrite the distribution to support a preferred result.

## Article 21 — Simulation Integrity

Monte Carlo or Match Simulation must preserve `simulation_engine_version`, configuration, seed, `number_of_runs`, and `input_hash`.

```text
simulation_engine_version
config
seed
number_of_runs
input_hash
```

Simulation is an `Independent Evidence Layer`; it does not replace underlying model facts and is not an `Outcome Truth Generator`.

## Article 22 — Consensus Must Preserve Disagreement

Consensus must retain `individual_engine_outputs` and emit `disagreement_score`. Averaging must not hide whether models agree or cancel each other.

When conflict is large, Risk Engine must be able to lower confidence, return caution, or abstain. A consensus label cannot erase the underlying disagreement.

## Article 23 — Market Interpretation Safety

Price drops, price rises, line movement, water-level changes, and market heat cannot be mechanically labeled as “certain win”, “trap”, “manipulation”, or “harvesting”. Trap Risk is only a probabilistic risk indicator and must retain uncertainty.

## Article 24 — Human Override Policy

Any human change to a model conclusion must be explicit. Silent override is prohibited. If overrides are later permitted, the record must preserve `original_output`, `override_output`, `actor`, `reason`, and `timestamp`.

Human Override must not modify model historical performance metrics, historical Frozen Prediction, or the underlying model output lineage.

## Article 25 — Correction Policy

Fact correction and prediction revision are different operations. A spelling or confirmed source correction may create an audited canonical revision. A wrong Frozen Prediction direction cannot be corrected in place; the original remains.

All corrections follow `docs/V4_CORRECTION_POLICY.md`, including append-only history, old value, new value, reason, actor, time, and new hash where applicable.

## Article 26 — Result Integrity

For official football evaluation, the default result is regulation 90 minutes plus officially specified stoppage time. Extra time and penalty shootouts are excluded unless the applicable market rules explicitly require them.

Official Result must match Canonical Match Identity exactly. An unmatched result is `BLOCKED` and cannot be used for evaluation.

## Article 27 — Postmatch Separation

Postmatch work has two separate concepts:

1. **MODEL EVALUATION** — Frozen Prediction plus Official Result only.
2. **MATCH EXPLANATION** — may read match events, xG, red cards, technical statistics, and post-match interviews.

Match Explanation cannot write back into historical Prediction Evaluation, Frozen Input, or Frozen Prediction.

## Article 28 — Error Attribution Is Diagnostic

Error Attribution creates diagnostic evidence only. It cannot automatically change parameters, weights, promotion, or demotion. Any model change creates a new version and new evidence period.

## Article 29 — Data Correction Cannot Erase Audit

Every correction retains `before`, `after`, `reason`, `actor`, and `timestamp`. Deleting old evidence to create a clean-looking history is prohibited.

## Article 30 — Security and Secrets

API keys, passwords, tokens, cookies, Supabase Service Role Keys, database passwords, and private credentials must never enter Git. Local secrets belong in `.env`, which must be protected by `.gitignore`. Only `.env.example` with empty template fields may be committed.

## Article 31 — Public Web Is Read Only

The public path is:

```text
Model Compute
    ↓
Prediction Store
    ↓
Read Projection
    ↓
Public Web
```

Public Web cannot execute models, modify Production, modify Frozen Prediction, or bypass a gate.

## Article 32 — Fail Closed

When a safe state is uncertain, V4 executes `FAIL CLOSED`. Uncertain odds time becomes `BLOCKED`; incomplete critical data becomes `BLOCKED` or an explicitly governed `PASS` only when the model contract permits it. “Predict first and check later” is prohibited.

## Article 33 — Auditability

Data Intake, Model Run, Freeze, Correction, Result Intake, Review, Tier A Registration, and Promotion must produce audit records. A production operation without a traceable audit event is invalid.

## Article 34 — Performance Cannot Override Integrity

Caching, reuse, and incremental computation are allowed, but they cannot skip Validation, Timestamp Gate, Hash, Provenance, or Freeze Gate. `Integrity > Speed`.

## Article 35 — Reuse Requires Input Identity

Cached computation may be reused only when `input_hash` is confirmed equal and the implementation/configuration identity is compatible. Same teams, same date, or apparently unchanged odds are not sufficient.

## Article 36 — Model Changes Require New Evidence

Any change to Algorithm, Weights, Features, Selector, Calibration, Simulation, League Profile, or Threshold creates a new implementation/config/version identity and requires new Forward Evidence.

## Article 37 — Regression Protection

New models are not evaluated by overall hit rate alone. Regression checks must cover league degradation, score distribution, BTTS, calibration, upset recognition, abstention behavior, and material runtime degradation.

## Article 38 — No Cherry Picking

It is forbidden to delete difficult matches, select only clear favorites, retain only complete or winning matches, or exclude failures for promotion. Exclusion rules must be declared before the sample is observed and applied consistently.

## Article 39 — Unknown Must Remain Unknown

`UNKNOWN` is not `FALSE`, `0`, `No Injury`, `No Rotation`, or `Stable Lineup`. Unknown and negative facts remain different states throughout ingestion, features, prediction, review, and evaluation.

## Article 40 — V3.3.3 Protection

JCFB V4 must not modify JCFB V3.3.3 code, model parameters, predictions, Frozen Prediction, reviews, samples, or audit history. V3.3.3 is available only as an independent benchmark and legacy reference.

## Enforcement and precedence

Constitutional violations default to `BLOCKED`, `RUN_INVALID`, or `NOT_VERIFIED` according to the affected lifecycle. No downstream layer may silently repair or hide a violation. Machine-oriented rules are catalogued in `docs/V4_INTEGRITY_RULES.md`; temporal decisions are defined in `docs/V4_TIME_AND_INFORMATION_POLICY.md`; lifecycle, correction, and incident handling are defined in the companion governance documents.
