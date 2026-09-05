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
