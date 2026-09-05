# JCFB V4 BATCH-15 Model Training Architecture Amendment Approval Decision

Decision ID: `V4-015-TRAINING-ARCH-APPROVAL-001`

Decision date: `2026-09-05` (`Asia/Shanghai`)

Baseline reviewed: `6691ae6` (`Phase 0` review documents committed)

Decision: **APPROVED FOR GOVERNANCE ACTIVATION ONLY**

## Resolution

The registry owner approves a separate execution entity type:

`EXECUTION_WORK_PACKAGE`

Its contract is `execution-work-package@1.0.0` and its active registry is
`v4-batch-prerequisite-workpackages@1.0.0`. This resolves the missing formal
training execution identity without creating a V4 task.

`MODEL_TRAINING_TASK_REGISTRY_AMENDMENT: RESOLVED`

`MODEL_TRAINING_EXECUTION_IDENTITY RESOLVED`

The entity is outside the authoritative `v4-task-registry-001-100@1.0.0`
namespace. It cannot create, rename, split, reclassify, or complete any
`V4-001` through `V4-100` task. It must bind a parent batch and explicit parent
task scope. A work package is a prerequisite or implementation sub-work
container only; `COMPLETE` for a work package never means `COMPLETE` for its
parent V4 task.

## Activation boundary

The amendment activates governance contracts, deterministic identities,
dependency declarations, status rules, evidence rules, and approved storage
boundaries. It does not authorize implementation or execution of any of the
five registered work packages. All registry entries keep
`execution_authorized=false`; formal model fit has an additional
`SEPARATE_APPROVAL_REQUIRED` status.

The prospective capture mode is approved as a future append-only acquisition
mode. It does not turn an empty archive into a dataset and does not permit
historical reconstruction from present-day revisions.

## Historical entry review

| Review item | Decision |
|---|---|
| Work Package mechanism | `ACTIVE_GOVERNANCE_ONLY` |
| Historical Source Archive contract | `READY` as a governance contract |
| Approved source storage location | `F:\Projects\jcfb-v4\approved_data\historical_source_archive\` |
| Verified historical backfill source | `NOT_FOUND` |
| Prospective accumulation | `YES; GOVERNANCE APPROVED` |
| Historical as-of reconstruction | `BLOCKED` |
| Dataset Builder | `NOT_READY_FOR_IMPLEMENTATION` |
| Temporal Split Builder | `NOT_READY_FOR_IMPLEMENTATION` |
| Training/Fitting Infrastructure | `NOT_READY_FOR_IMPLEMENTATION` |
| Formal Model Fit & Validation | `SEPARATE_APPROVAL_REQUIRED` |
| Outcome/Handicap/Goals/HTFT usable samples | `UNKNOWN` |

`src/data` contains only `.gitkeep`; `.runtime/data` is empty; no approved
historical archive, official odds archive, external market archive, Team
Context revision archive, Evidence Graph revision archive, or BATCH-14 Gate
Record population was found. Test fixtures remain synthetic test inputs and
are excluded.

## Raw fact / model isolation decision

Verified external objective facts may be re-ingested into V4 only through the
`historical-source-archive@1.0.0` contract, with source reference, source or
observation time, original payload/file hash, match identity, revision
identity, and provenance. Direct references to V3.3.3 runtime, model
parameters, predictions, Frozen Predictions, confidence, calibration, or
review-derived parameters remain forbidden.

## Remaining blockers

`TRAINING_DATASET_NOT_AVAILABLE`, `HISTORICAL_SOURCE_LINEAGE_NOT_AVAILABLE`,
`TRAINING_PIPELINE_NOT_IMPLEMENTED`,
`PREDICTION_MODEL_ARTIFACT_NOT_APPROVED`, and
`FROZEN_INPUT_NOT_IMPLEMENTED` remain active. The correct readiness decision is
still `PREDICTION_TRAINING_READINESS_BLOCKED`.

No dataset construction, import, model fitting, V4-076, V4-052 through
V4-055, Score, Calibration, Shadow, Production, Public, Supabase, migration,
or V3.3.3 operation is authorized by this decision.

## Evidence and cross-references

- `config/prediction_training/execution_work_package_schema.json`
- `config/prediction_training/v4_batch15_execution_work_package_registry.json`
- `config/prediction_training/historical_source_archive_contract.json`
- `docs/JCFB_V4_BATCH_15_EXECUTION_WORK_PACKAGE_CONTRACT.md`
- `docs/JCFB_V4_HISTORICAL_SOURCE_ACQUISITION_MODE_POLICY.md`
- `docs/JCFB_V4_HISTORICAL_BACKFILL_ELIGIBILITY_POLICY.md`
- `docs/JCFB_V4_PROSPECTIVE_TRAINING_ARCHIVE_POLICY.md`
- `docs/JCFB_V4_RAW_FACT_REINGESTION_DECISION.md`
- `docs/JCFB_V4_BATCH_15_MODEL_TRAINING_DEPENDENCY_AMENDMENT.md`
- `docs/JCFB_V4_F_DRIVE_HISTORICAL_ARCHIVE_STORAGE_POLICY.md`
