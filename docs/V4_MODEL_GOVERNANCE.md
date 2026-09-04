# JCFB V4 Model Governance 1.0

Status: V4-005 COMPLETE

## 1. Purpose

This policy governs model and engine identity, lifecycle, role separation, evaluation, promotion, retirement, and active-revision rules. It applies to statistical models, intelligence components, Outcome, Handicap, Goals, HTFT, Score, Upset, Simulation, Consensus, Uncertainty, Risk, and selector components.

## 2. Lifecycle

```text
DRAFT
  ↓
EXPERIMENT
  ↓
SHADOW
  ↓
PROMOTION_REVIEW
  ↓
PRODUCTION
  ↓
RETIRED
```

The following direct transitions are forbidden:

- `DRAFT → PRODUCTION`
- `EXPERIMENT → PRODUCTION`
- `SHADOW → PRODUCTION` without `PROMOTION_REVIEW`

The lifecycle state is part of the model registry identity and audit history. A label such as “latest model” is not a valid lifecycle state or version identity.

## 3. Model identity

Every registered model or engine must declare:

- `model_name`
- `major`
- `minor`
- `patch`
- `revision`
- `engine_version`
- `config_version`
- `status`
- `implementation_hash`
- owner and creation timestamp

Every formal run must additionally record `config_hash`, `input_hash`, `output_hash`, `run_at`, and `runtime_environment`. A random simulation records `random_seed` and `simulation_version`.

The complete field-level identity envelope, role-scoped revisions, canonical hash boundaries, compatibility outcomes, and release naming rules are defined in `docs/V4_VERSION_IDENTITY_CONTRACT.md`, `docs/V4_VERSIONING_STANDARD.md`, `docs/V4_COMPATIBILITY_POLICY.md`, and `docs/V4_RELEASE_NAMING.md`.

Changing an algorithm, feature, weight, selector, calibration method, simulation behavior, league profile, or threshold creates a new implementation/config/version identity. A parameter change cannot be hidden under an old version number.

For BATCH-11, the historical sample policy, sparse-data behavior, rolling window, decay function, normalization, priors, league/season transition, and home/away treatment are model-affecting configuration. They must use the approved `statistical-strength-config@1.0.0` identity and its exact `config_hash`; changing any of them creates a new configuration/revision identity.

## 4. Roles

### `PRODUCTION`

Production is the only formal prediction source. A Production run must use an approved active revision, an eligible Frozen Input, and all required quality, consistency, risk, and freeze gates.

### `SHADOW`

Shadow runs before kickoff for comparison and evaluation. Shadow output is isolated, cannot modify Production or Frozen Prediction, and cannot appear as formal public output. If A/B comparison is required, it uses the same `frozen_input_hash` as the paired Production run.

### `EXPERIMENT`

Experiment is a research role. It may test a new feature, algorithm candidate, selector, calibration method, or simulation setting. Experiment output must remain out of Production Output and public read projections.

## 5. Canonical active revision

Production has exactly one `Canonical Active Revision` for a declared model or engine at a time. Historical Production revisions remain permanently retained with their run, configuration, hashes, freeze, evaluation, and retirement evidence.

An active revision cannot be replaced by editing its record. A new revision is registered, evaluated, reviewed, and promoted; the old revision is retained and later marked `RETIRED` only through an explicit lifecycle transition.

## 6. Admission gates

Before Experiment, Shadow, or Production execution, the registry verifies:

1. model and engine identity is explicit
2. implementation and configuration are addressable
3. input and cutoff contract is declared
4. role is explicit
5. required dependencies are versioned
6. no forbidden future data is present
7. required audit fields are available

Before Production, the Final Prediction Gate and Frozen Input requirements also apply. A failed gate creates `BLOCKED`, not an inferred approval.

## 7. Promotion evidence

Promotion requires all of the following unless a formal governance decision documents an exception:

- Frozen Forward Samples
- Statistical Evaluation
- Calibration Evaluation
- Integrity Audit
- No Future Leakage Audit
- Regression Test
- Performance Test
- Promotion Review
- explicit human approval

Evidence must include sample scope, cutoff, model identity, role, input hashes, output hashes, exclusions, and failure handling. A single successful match, short hit streak, subjective preference, or one Top2 hit cannot qualify a promotion.

`MANUAL_APPROVAL_REQUIRED` is the default. `AUTO_PROMOTION = TRUE` is prohibited.

## 8. Forward evaluation and Tier A

Forward Frozen Data is primary promotion evidence. Historical backtesting is supporting evidence and cannot substitute for a genuine pre-match Shadow Run. V4 Tier A starts at `V4 Tier A Sample #001`; V3.3.3 samples and labels cannot be imported or relabeled.

An eligible Tier A record requires Frozen Input, required Production and Shadow output, pre-kickoff timestamps, Official Result, no leakage, implementation/config/input/output hashes, and a passing completeness gate.

## 9. Evaluation integrity

Postmatch evaluation reads the immutable Frozen Prediction and Official Result. Review and Error Attribution are diagnostic. They cannot alter the evaluated output, select only successful samples, remove difficult matches, or change a historical result to improve a KPI.

Calibration is stratified by league, market, confidence band, and model version. Overall hit rate alone is not sufficient evidence for promotion.

## 10. Human and agent responsibilities

Human Operators may approve a documented promotion, correction, or override only within this Constitution. Every override records original output, override output, actor, reason, and timestamp, and cannot rewrite model performance history.

Codex Agents may create declared artifacts and run validation within repository scope. They must not invent identity, secrets, parameters, results, or completion status. Agents must fail closed on unknown information and must not silently promote or modify Production.

## 11. Retirement and historical preservation

Retirement stops new Production use after an explicit decision. It does not delete historical runs, Frozen Inputs, Frozen Predictions, evaluations, or audit records. A retired revision remains reproducible using its original implementation, configuration, and input identities when available.

## 12. Prohibited shortcuts

- direct DRAFT or Experiment promotion
- changing a version in place after a run
- using post-match results to tune or reclassify a historical run
- merging Shadow output into Production without review
- hiding model conflict through a simple average
- replacing probability with confidence
- deleting failed samples from promotion evidence
