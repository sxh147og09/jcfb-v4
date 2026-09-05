# JCFB V4 BATCH-15 Prediction Model Training Governance Decision

Decision ID: `V4-015-TRAINING-001`
Status: **PREDICTION MODEL TRAINING GOVERNANCE RESOLVED / TRAINING READINESS BLOCKED**
Decision date: `2026-09-05`
Scope: governance and readiness only; no model fitting and no Prediction implementation

## 1. Decision and architecture

`PREDICTION MODEL TRAINING GOVERNANCE RESOLVED` is recorded for the following
architecture:

```text
Historical As-Of Feature Reconstruction
  -> Training Dataset Artifact
  -> Temporal Train/Validation/Test Split
  -> Candidate Model Fitting
  -> Out-of-Time Evaluation
  -> Approved Model Artifact
  -> Model Registry
  -> V4-076 Frozen Input
  -> V4-052/053/054/055 Formal Engine Run
```

Training/fitting is a mandatory BATCH-15 prerequisite phase. It is not a new
V4 task node, and it is not a Prediction Engine. V4-052 through V4-055 may
only consume an `APPROVED_FOR_ENGINE` artifact and the exact Frozen Input for
inference.

The machine-readable source of truth is:
`config/prediction_training/v4_prediction_training_governance.json`.
Its canonical hash uses `SHA-256` and `v4-canonical-json@1.0`, excluding only
its own `canonical_hash` field from the hash input.

## 2. Task identity amendment

No `V4-101`, `V4-052A`, or other task ID was created. Training governance and
fitting are registered as a mandatory readiness phase under BATCH-15. If a
future execution service requires a task identity to run fitting, it must
first obtain the explicit `MODEL_TRAINING_TASK_REGISTRY_AMENDMENT_REQUIRED`
decision described in `docs/V4_BATCH_15_MODEL_TRAINING_TASK_REGISTRY_AMENDMENT.md`.
Until then, actual fitting is paused.

## 3. Historical as-of dataset contract

The versioned contract is `prediction-training-dataset@1.0.0`. Each sample is
`match_id + prediction_cutoff_at + cutoff_profile + target_role` and records
the cutoff-visible Feature Bundle identity/hash, statistical/football/market/
tactical references and hashes, quality/gate state, source availability
timestamps, revision identity, label reference/hash, and dataset/schema
versions.

The hard predicate is:

```text
feature_availability_at <= prediction_cutoff_at < kickoff_at
```

Current final database state cannot be used to pretend to reconstruct a past
cutoff. A correction creates a new dataset ID/hash with explicit
`supersedes`; it never edits an earlier dataset artifact.

## 4. Independent label contracts

The versioned label contract is `prediction-training-labels@1.0.0`.

| Role | Target classes | Target construction |
|---|---|---|
| Outcome | `H`, `D`, `A` | Official final home/away result |
| Handicap | `H`, `D`, `A` | Official RQSPF handicap reference and exact cutoff value; `home_score + handicap` versus away score; sign `home_minus_away` |
| Goals | `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7+` | Official final total goals with a 7+ tail |
| HTFT | `H/H`, `H/D`, `H/A`, `D/H`, `D/D`, `D/A`, `A/H`, `A/D`, `A/A` | Official halftime state joined to official fulltime state |

Labels are post-match targets only. They are physically or logically separate
from pre-match features. A post-cutoff handicap or post-match fact cannot
replace the cutoff-bound input or enter its feature payload.

## 5. Leakage, eligibility, and deduplication

The leakage contract is `prediction-training-leakage@1.0.0`. Final score,
halftime result, post-cutoff red cards or lineups, future odds, post-match
statistics, future team matches, future league-table state, and later
revisions not visible at cutoff are forbidden feature inputs. Unknown or
conflicting timestamps are `BLOCKED`.

The sample eligibility contract is
`prediction-training-sample-eligibility@1.0.0`:

- `BLOCKED` never enters training;
- `INELIGIBLE` never enters the corresponding engine set;
- `PARTIALLY_ELIGIBLE` is allowed only when required features exist and
  missing values are approved optional states;
- `ELIGIBLE` enters only after target-specific time, feature, and gate rules
  pass.

Missing values are never silently imputed. BATCH-14 quality is used for
eligibility, blocker filtering, and warnings; `quality_score` cannot become a
numeric model feature in this version. The deduplication key is
`match_id + cutoff_profile + target_role`; multi-cutoff training is not
approved in V1, and the same match cannot cross temporal partitions.

## 6. Temporal validation and minimum readiness

The only allowed split strategies are `TIME_ORDERED_TRAIN_VALIDATION_HOLDOUT`
and `WALK_FORWARD_ROLLING_ORIGIN`. Random train/test splitting is forbidden.
The split artifact hash includes exact boundaries and ordering. The required
relations are:

```text
max(train.cutoff) < min(validation.cutoff)
max(validation.cutoff) < min(holdout.cutoff)
```

Holdout is used once for independent evaluation and never for fitting,
selection, or early stopping.

There is no arbitrary total-sample shortcut. Readiness requires every
declared class in every partition, at least 5 observations per class in
training and 3 per class in validation and holdout, at least 3 ordered
training periods plus later validation and holdout periods, declared league
coverage, 100% required-feature availability, and passing time-window
stability diagnostics. Unknown or unstable diagnostics produce
`TRAINING_DATA_INSUFFICIENT` or `BLOCKED`; rules are not relaxed to force a
fit.

## 7. Candidate families and model selection

The candidate family registry is `prediction-candidate-model-families@1.0.0`.
The governed candidate set is regularized multinomial logistic and
probabilistic gradient-boosted decision trees. Both are deterministic,
probability-producing families and are allowed independently for each of the
four roles. An unregistered complex black box is forbidden. No Production
Model is selected by this governance decision.

The selection protocol is `prediction-model-selection@1.0.0`:

- primary metric: mean out-of-time Log Loss;
- secondary metrics: mean out-of-time Brier Score and class-wise recall with
  support;
- tie-break: lower Brier, lower Log Loss variance, lower complexity, then
  lexicographic family ID;
- search space, budget, early stopping, library/version, seed, feature order,
  and label order are frozen before execution;
- final holdout is evaluated once and cannot drive further tuning.

Baseline distributions may be evaluated only as
`EVALUATION_BASELINE_ONLY`. A bookmaker implied probability is not a V4 model
baseline artifact. No baseline or hand-written coefficient can enter the
registry.

## 8. Four independent model artifacts

The four roles remain independent even when they share infrastructure:
Outcome, Handicap, Goals, and HTFT each receive their own target contract,
feature profile, fitted parameters, model identity, metrics, artifact hash,
and evidence. Outcome cannot mechanically derive Handicap, Goals, or HTFT.

The artifact contract is `prediction-model-artifact@1.0.0` and requires model
identity, algorithm/version, parameter identity/hash, exact feature profile
identity/hash, dataset and split identity/hash, cutoff, fitting implementation
hash, training config/hash, seed, selection results, validation/holdout
metrics, calibration state, creation metadata, artifact hash, revision, and
explicit supersession. Artifacts are append-only.

Lifecycle is `CANDIDATE -> VALIDATED -> APPROVED_FOR_ENGINE` or `REJECTED`.
Training completion is not approval. Only an explicit human promotion gate
may admit an artifact to the registry; automatic Production promotion is
forbidden. Calibration remains `NOT_CALIBRATED` in BATCH-15 and belongs to
V4-082.

## 9. Feature and deterministic boundaries

The feature policy is `DECLARED_MODEL_FUSION_ONLY`. A model manifest declares
the exact Statistical, Football, Market, and Tactical features it consumes.
No precomputed Statistical/Market/Football/Tactical weights, quality penalty,
or manual fusion ratio is permitted.

The deterministic training profile is `deterministic-training@1.0.0` with
SHA-256, canonical JSON, fixed feature/label ordering, library versions,
thread/determinism settings, seed, fitting implementation hash, dataset hash,
split hash, and config hash. Volatile host and timing metadata are excluded
from substantive artifact hashes. A same-input replay that cannot reproduce
the logical parameters/hash is `BLOCKED`.

## 10. V4-076 binding amendment

`frozen-input-model-binding@1.0.0` requires V4-076 to freeze, per engine, the
exact approved model artifact identity/revision/hash and engine config
identity/hash, in addition to the exact Feature Bundle, gate record,
cutoff, and kickoff. V4-076 does not freeze a training dataset as a substitute
for inference input. V4-076 implementation is not authorized until all four
roles are `APPROVED_FOR_ENGINE`.

## 11. V3.3.3 isolation and safety result

V3.3.3 coefficients, trained artifacts, prediction outputs, Frozen
Predictions, and calibration history are forbidden as V4 training input or
parameter initialization. A separately approved benchmark may read isolated
comparison data only; it cannot initialize or train V4. No V3.3.3 path was
modified.

This phase performed no model fit, created no model artifact, implemented no
Prediction Engine, implemented no V4-076, and touched no Score, Risk,
Production/Shadow, Public, Supabase, migration, or V3.3.3 scope.

## 12. Deliverable index

| Required deliverable | Governed identity/evidence |
|---|---|
| Training Governance Decision | `V4-015-TRAINING-001`, this document |
| Training Dataset Contract | `prediction-training-dataset@1.0.0` |
| Label Contract | `prediction-training-labels@1.0.0` |
| Temporal Split Contract | `prediction-training-temporal-split@1.0.0` |
| Leakage Prevention Contract | `prediction-training-leakage@1.0.0` |
| Sample Eligibility Contract | `prediction-training-sample-eligibility@1.0.0` |
| Candidate Model Family Registry | `prediction-candidate-model-families@1.0.0` |
| Hyperparameter Governance | `prediction-training-hyperparameters@1.0.0` |
| Model Selection Protocol | `prediction-model-selection@1.0.0` |
| Model Evaluation Contract | `prediction-model-evaluation@1.0.0` |
| Prediction Model Artifact Contract | `prediction-model-artifact@1.0.0` |
| Model Registry | `config/prediction_training/v4_prediction_model_registry.json` |
| Promotion State Contract | `prediction-model-promotion@1.0.0` |
| Deterministic Training/Hash Profile | `deterministic-training@1.0.0` |
| Four engine-specific training profiles | `OUTCOME`, `HANDICAP`, `GOALS`, `HTFT` in the canonical governance registry |
| V4-076 model binding amendment | `frozen-input-model-binding@1.0.0` |
| V3 isolation statement | `v4-v3333-isolation@1.0.0` |

All machine-readable governance/registry sources use canonical SHA-256 hashes.
