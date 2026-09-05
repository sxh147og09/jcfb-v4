# JCFB V4 BATCH-15 B15-EWP-003 Contract Remediation & Re-Entry Review

Review identity: `B15-EWP-003-contract-remediation-reentry-r002`

Review date: `2026-09-05` (`Asia/Shanghai`)

Baseline HEAD: `74971cafbfce1db16e8281a3165ca1c2aed83f4a`

Working tree at review start: `CLEAN`

## Decision summary

The six EWP-003 implementation-entry contract blockers are resolved by the
versioned machine-readable contract at
`config/prediction_training/v4_batch15_ewp003_temporal_split_contract.json`.

**Runtime Implementation Readiness:** `B15-EWP-003 READY FOR IMPLEMENTATION`

This is a scope/entry result only. `execution_authorized=false` remains in the
registry. No EWP-003 runtime, temporal split, model fitting, or model artifact
was created.

**Current Real Dataset Split Readiness:** `BLOCKED / TRAINING_DATA_INSUFFICIENT`

The active EWP-002 dataset is available and hash-bound, but it contains zero
candidate samples and zero usable samples. The only current output is the
blocked readiness report at
`config/prediction_training/v4_batch15_ewp003_readiness_report.json`.

**Formal Model Fit Readiness:** `BLOCKED`

EWP-003 implementation entry does not promote data readiness or model-fit
readiness. EWP-004 and EWP-005 remain unauthorized.

## Contract remediation

| Former blocker | Frozen resolution |
|---|---|
| `TIME_ORDERED_BOUNDARY_SELECTION_NOT_FROZEN` | `EXPLICIT_TEMPORAL_BOUNDARIES` is the governed first strategy; train/validation/holdout boundaries, ordering, tie-break, positive separation, and interval semantics are explicit config fields. |
| `WALK_FORWARD_ROLLING_ORIGIN_PARAMETERS_NOT_FROZEN` | Expanding/sliding mode, initial train period, origin step, validation/holdout horizon, sliding width, minimum folds, incomplete-final-fold policy, grouping policy, and fold readiness policy are schema-required; no numeric defaults exist. Missing config fails closed as `SPLIT_CONFIG_NOT_DECLARED`. |
| `MINIMUM_SAMPLE_READINESS_RULE_NOT_EXECUTABLE` | Frozen class minimums remain train `>=5`, validation `>=3`, holdout `>=3`. Diagnostic windows and class-rate/feature-availability formulas are explicit. Stability has `PASS`/`UNSTABLE`/`UNKNOWN` states; unapproved numeric thresholds are not invented. |
| `LEAGUE_SCOPE_DECLARATION_NOT_EXECUTABLE` | League scope is required and canonicalized from the dataset manifest. `SINGLE_LEAGUE` and `DECLARED_MULTI_LEAGUE` fields and coverage requirements are machine-readable; missing scope fails as `LEAGUE_SCOPE_NOT_DECLARED`; content inference is forbidden. |
| `ZERO_DATA_READINESS_OUTPUT_CONTRACT_NOT_FROZEN` | Zero data emits `split_status=NOT_PERFORMABLE`, `readiness_state=BLOCKED`, `reason_code=TRAINING_DATA_INSUFFICIENT`, zero counts, and `split_artifact_generated=false`; no fake split is created. |
| `DATASET_REVISION_BINDING_NOT_EXPLICIT_IN_SPLIT_CONTRACT` | Every split must bind `dataset_id`, revision, manifest hash, and substantive hash. Mixed/superseded revisions reject; historical replay requires explicit mode and exact identity. |

## Cross-reference reconciliation

The active dataset reference is now:

- dataset: `dataset-13c4b050dc50e2de3ec8a961a9c9b029`
- revision: `r001`
- manifest hash: `sha256:417cf5108ba30142f4cbfa244b53b07f85bbe77ce1aa7de0c0ad2c99ab93bf23`
- substantive hash: `sha256:5da31e18e1aa6bc494386b841b400ff4a137885b67badeb55e030b2d7780d933`
- candidate samples: `0`
- usable samples: `0`
- dataset reason: `ZERO_ARCHIVED_CANDIDATES`

The registry advances EWP-003 to contract revision `r002` while retaining
`REGISTERED_NOT_EXECUTABLE`, `execution_authorized=false`, and
`artifact_hash=NOT_GENERATED`. The prior
`docs/JCFB_V4_BATCH_15_B15_EWP_003_SCOPE_ENTRY_READINESS_ASSESSMENT.md` remains
an historical `r001` snapshot and is superseded by this review; its facts are
not rewritten.

## Artifact and hash boundary

The readiness report includes dataset identity/hashes, split contract identity,
status, reason codes, per-engine counts, class-support state, temporal/league/
feature coverage, stability state, leakage-check state, and a deterministic
report hash. It deliberately contains no accuracy or model metric.

The formal split artifact schema includes membership, boundaries, folds,
grouping, ordering, revision, supersession, and artifact hash fields. Its
substantive hash excludes timestamps, absolute paths, logging metadata, host,
process, and duration. With zero or insufficient data, the schema requires a
blocked readiness report only and forbids a formal split artifact.

## Strict-boundary verification

This remediation changed governance/configuration, validation, tests, and
reports only. It did not:

- implement or authorize EWP-003 runtime;
- generate a formal temporal split or split artifact;
- fit a model or create model artifacts;
- authorize EWP-004/EWP-005, V4-076, V4-052..055, Score, Calibration, Shadow,
  Production, or Public;
- modify Supabase, migrations, or V3.3.3;
- allow synthetic fixtures to affect formal readiness.

## Re-entry disposition

`B15-EWP-003 READY FOR IMPLEMENTATION` is valid only for the contract-defined
implementation scope and does not change the explicit authorization flag.

`CURRENT_REAL_DATASET_SPLIT_READINESS = BLOCKED / TRAINING_DATA_INSUFFICIENT`

`FORMAL_MODEL_FIT_READINESS = BLOCKED`

The next separately authorized implementation, if approved, must consume an
explicit split config and must fail closed when it is absent. No production
numeric walk-forward parameters are implied by this remediation.
