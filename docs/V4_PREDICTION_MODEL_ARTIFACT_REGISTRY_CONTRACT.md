# JCFB V4 Prediction Model Artifact Registry Contract 1.0

Status: **GOVERNANCE ACTIVE / NO APPROVED ARTIFACTS PRESENT**
Contract version: `prediction-model-artifact@1.0.0`

Each of Outcome, Handicap, Goals, and HTFT requires a separate approved model
artifact manifest declaring:

- model name/version and engine name/version;
- algorithm/model family;
- feature schema version and exact feature list;
- parameter artifact identity/hash;
- training dataset identity/hash and training cutoff;
- generator/training implementation hash;
- model configuration version/hash;
- normalization policy and missing-state handling;
- output schema version and calibration state.

No implementation may hard-code unapproved coefficients, baseline weights,
manual logistic parameters, tactical bonuses, or quality penalties. This
repository currently contains no legal trained/parameterized artifact for
these four engines. The formal admission state is
`PREDICTION_MODEL_ARTIFACT_NOT_APPROVED`; model-fit/training governance is
required before implementation can claim a successful run.

## BATCH-15 training-governed lifecycle

The complete training governance source is
`config/prediction_training/v4_prediction_training_governance.json`; the
append-only registry is
`config/prediction_training/v4_prediction_model_registry.json`. The only
allowed artifact lifecycle states are:

```text
CANDIDATE -> VALIDATED -> APPROVED_FOR_ENGINE
                     \-> REJECTED
```

`APPROVED_FOR_ENGINE` requires independent evidence for the target role,
out-of-time validation, one final holdout evaluation, exact dataset/split/
feature/config/implementation hashes, deterministic replay settings, and an
explicit promotion gate. Training completion is not approval, and no state
automatically promotes to Production.

The required artifact manifest additionally includes `model_artifact_id`,
`role`, `model_name`, `model_version`, `algorithm_family_and_version`,
`parameter_artifact_id`, `parameter_hash`, `feature_profile_version_and_hash`,
`training_dataset_id_and_hash`, `training_split_id_and_hash`,
`training_cutoff`, `fitting_implementation_hash`, `training_config_version_and_hash`,
`random_seed`, selection/validation/holdout evidence, `calibration_state`,
`created_at`, `artifact_hash`, `revision`, and
`supersedes_model_artifact_id`.
