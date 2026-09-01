# JCFB V4 Experiment Policy 1.0

Status: V4-007 COMPLETE

## 1. Purpose and authority

EXPERIMENT is the V4 research and development role. It permits controlled exploration without granting Production, Public Web, Shadow, or Tier A authority. This policy is governed by docs/V4_CONSTITUTION.md, docs/V4_MODEL_GOVERNANCE.md, docs/V4_VERSIONING_STANDARD.md, and docs/V4_RUNTIME_ROLE_BOUNDARY.md.

This policy does not implement training, backtesting, parameter tuning, a model registry, or a runtime. It defines the boundary those future systems must obey.

## 2. Required experiment identity

Every experiment carries:

- role=EXPERIMENT
- experiment_id
- build_id
- experiment_revision in the ex-YYYYMMDD-NNNNNN form
- model_name, model_version, major, minor, patch, and revision
- engine_version and selector identity when applicable
- implementation_hash
- config_hash
- input_hash
- output_hash for every produced output
- run_at and runtime_environment
- dataset_version, schema_version, migration_version, and config_version
- declared input mode and cutoff semantics
- status=EXPERIMENT or a governed gate state

An experiment cannot be identified only by a notebook name, branch, date, operator, or phrase such as current model.

## 3. Permitted research

EXPERIMENT may perform:

- offline development and feature research
- historical backtesting and historical recomputation
- parameter scans and selector comparisons
- simulation and score-distribution studies
- calibration studies
- ablation and regression studies
- controlled comparison against separately frozen artifacts

Experiment outputs are retained in an Experiment namespace with separate identities. A failed experiment does not alter Production or Shadow configuration, active pointers, frozen outputs, public projection, Tier A records, or historical reviews.

## 4. Input modes and comparison labeling

An experiment must declare one of these input modes:

| Input mode | Requirement | Eligible use |
|---|---|---|
| EXPERIMENTAL_INPUT | Uses a research input or a different fact, feature, cutoff, or dataset identity; the reason and input_hash are required | Research only; never a formal Forward A/B pair |
| FROZEN_RESEARCH_INPUT | Uses a separately frozen Experiment input; frozen_revision and frozen_input_hash are required | Controlled research comparison only |
| FROZEN_AB_REFERENCE | References the same frozen_input_hash as a Production/Shadow pair | Research comparison only; never Tier A or Promotion evidence as an Experiment sample |

Using the same frozen_input_hash does not turn an Experiment into SHADOW. The role, experiment_revision, experiment_id, build_id, and output identity remain Experiment-scoped.

An Experiment that claims to be pre-match must obey the V4 time inequality. A historical run may use historical data only when its retrospective time semantics and dataset identity are explicit; it cannot be described as a Forward Shadow run.

## 5. Isolation from formal output

EXPERIMENT is denied any write path that can:

- create or replace canonical Production Prediction
- modify Production Frozen Prediction
- change Production confidence, risk, review, or Tier A qualification
- change the active Production pointer
- write the Production Public Read Projection
- overwrite Shadow evidence
- erase an earlier Experiment failure or output

An Experiment may read approved artifacts only within a declared research or post-match review scope. A pre-match Experiment must not consume a Production or Shadow prediction for the same match and then claim independent model evidence. Post-match comparison reads are labeled as review inputs, not pre-match inputs.

## 6. Public Web and Tier A prohibition

Experiment outputs are never valid inputs to the Production canonical public projection. If a future research page is needed, it must use a distinct non-formal projection, distinct route and identity, and explicit research labeling. It must not use a Production URL, canonical public identifier, or Production latest marker.

Experiment samples can never:

- be counted as Forward Tier A
- be relabeled as Shadow
- repair a missing or invalid Shadow pair
- qualify a Production release by themselves

V4 Tier A starts at V4 Tier A Sample #001. Only the formal Forward A/B conditions and Promotion Review rules can admit evidence; an Experiment sample is permanently excluded from that category.

## 7. Experiment to Shadow boundary

Research may produce a candidate for SHADOW, but EXPERIMENT -> SHADOW is a new governed transition, not a rename. It requires:

1. a new Shadow revision
2. a new Shadow identity and implementation/configuration hashes
3. a declared pre-match cutoff and Frozen Input contract
4. a real pre-kickoff Shadow run
5. a separate output identity
6. the Shadow admission and Forward evidence gates

EXPERIMENT -> PRODUCTION is prohibited. A candidate must pass SHADOW, PROMOTION_REVIEW, manual approval, and the explicit Production release process.

## 8. Experiment failure and recovery

An Experiment failure is isolated to the experiment_id and build_id. It is recorded as evidence and does not block Production or Shadow unless a separately proven shared global input or security incident exists.

Recovery creates a new build_id, experiment_revision, and hashes. It does not change the failed output, input, review, or audit record. A post-match rerun is labeled post-match and cannot become a Forward sample.

## 9. References

- docs/V4_RUNTIME_ROLE_BOUNDARY.md
- docs/V4_SHADOW_POLICY.md
- docs/V4_PROMOTION_PATH.md
- docs/V4_RUNTIME_ACCESS_MATRIX.md
- docs/V4_CONSTITUTION.md
- docs/V4_MODEL_GOVERNANCE.md
- docs/V4_TIME_AND_INFORMATION_POLICY.md
- docs/V4_VERSIONING_STANDARD.md
