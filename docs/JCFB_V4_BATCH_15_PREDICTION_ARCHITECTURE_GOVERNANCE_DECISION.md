# JCFB V4 BATCH-15 Prediction Architecture & Frozen Input Ordering Governance Decision

Decision ID: `V4-015-ADR-001`
Status: **APPROVED FOR GOVERNANCE / BATCH-15 ENTRY REVIEW BLOCKED**
Decision date: `2026-09-05`
Scope: architecture, contracts, dependency/status consistency only

## 1. Decision

The canonical pre-match path is:

```text
accepted facts / official markets / external intelligence / context / evidence
  -> Feature Bundle and feature snapshot
  -> BATCH-11 statistical features
  -> BATCH-12 football/context features
  -> BATCH-13 market features
  -> BATCH-14 tactical features, quality assessment, and Pre-Freeze Quality Gate
  -> V4-076 Frozen Input (frozen-input@2.0.0)
  -> V4-052 Outcome   ┐
  -> V4-053 Handicap  ├ independent formal Engine Runs
  -> V4-054 Goals     │
  -> V4-055 HTFT      ┘
  -> Score / Simulation / Consensus / Risk / Final Gate / Frozen Prediction
```

`frozen-input@2.0.0` already defines Frozen Input as the exact immutable
source boundary consumed by Prediction and Engine Output. This decision fixes
the execution graph to match that data contract. Task number `V4-076` does not
imply that it executes after V4-052 through V4-055.

V4-076 is retained as the sole Frozen Input task. It is moved into the
BATCH-15 pre-prediction freeze wave for planning purposes; no mock, temporary,
or duplicate freeze task is created.

## 2. V4-076 responsibility split

V4-076 owns only the immutable pre-prediction Frozen Input: canonical match
identity, accepted snapshots and evidence, Feature Bundle identity/hash,
feature snapshot hash, BATCH-14 gate record, cutoff/kickoff, exact revisions,
and supersession lineage.

Downstream responsibilities remain with approved task IDs:

- V4-074 remains Five-Market Orchestrator.
- V4-075 remains Final Prediction Gate and final prediction eligibility.
- V4-077 remains Frozen Prediction and revision-chain persistence.

The former V4-076 -> V4-075 edge is removed. V4-075 may validate the already
existing Frozen Input, but V4-076 does not depend on Final Gate or Prediction.

## 3. Governance boundaries resolved

The following contracts are active for future implementation, but their
runtime implementation is not authorized by this decision:

1. `prediction-input@1.0.0` defines immutable input identity and exact
   per-engine feature profiles.
2. `gate-to-prediction@1.0.0` defines BLOCKED, INELIGIBLE, and
   PARTIALLY_ELIGIBLE behavior without silent imputation.
3. `prediction-fusion@1.0.0` keeps upstream
   `SEPARATE_DIMENSIONS_ONLY` and permits only declared model fusion.
4. `prediction-model-artifact@1.0.0` requires an approved artifact manifest
   for each engine.
5. `prediction-probability@1.0.0` separates raw score/logit, normalized
   probability, and calibrated probability.
6. `engine-feature-profile@1.0.0` defines independent Outcome, Handicap,
   Goals, and HTFT profiles and output payloads.
7. `deterministic-replay@1.0.0` defines substantive hash inputs and volatile
   metadata exclusions.

`V4-052` through `V4-055` remain unimplemented. No model artifact with
approved identity, parameters, training data, and hashes exists in this
repository. Therefore a future implementation must return the explicit
blocker `PREDICTION_MODEL_ARTIFACT_NOT_APPROVED` until model-fit/training
governance supplies four approved artifacts. It must not create baseline
weights, empirical coefficients, tactical bonuses, quality penalties, or
manual fusion weights.

## 4. BATCH-14 canonicalization

The existing closure report and machine evidence are authoritative evidence
that V4-049, V4-050, and V4-051 are `COMPLETE` and BATCH-14 is `COMPLETE /
Closure Gate PASS`. This decision synchronizes the live registry, execution
classification, dependency register, batch plan, and checklist to that
evidence. The frozen execution manifest and historical review evidence are
not rewritten.

## 5. Explicit non-scope

This decision does not implement V4-076, V4-052, V4-053, V4-054, V4-055,
Score, Simulation, Consensus, Risk/Abstention, Public, Production/Shadow,
Supabase, migrations, or V3.3.3. It does not declare BATCH-15 ready for
continuous execution.

## 6. Acceptance disposition

Architecture and dependency consistency are resolved. BATCH-15 Entry Review
remains **BLOCKED** by:

- `PREDICTION_MODEL_ARTIFACT_NOT_APPROVED`: no four-engine approved model
  artifact/parameter registry exists;
- `TRAINING_PIPELINE_NOT_IMPLEMENTED` and `TRAINING_DATASET_NOT_AVAILABLE`:
  no legal historical as-of fitting inputs or training runtime exists;
- `FROZEN_INPUT_NOT_IMPLEMENTED`: V4-076 is correctly ordered but remains
  unimplemented;
- `BATCH_14_STATUS_SOURCE_DRIFT`: resolved in this governance change and
  covered by the status consistency validator.

`UPSTREAM_IMPLEMENTATION_NOT_ACCEPTED` is resolved as status drift by the
live V4-038..V4-048 acceptance reconciliation. The remaining blockers are
genuine implementation-entry blockers, not reasons to invent fixtures as
formal inputs. The required result is
`BATCH-15 ENTRY REVIEW = BLOCKED`, not `BATCH-15 READY FOR CONTINUOUS
EXECUTION`.

## 7. Training governance resolution

The separate BATCH-15 training governance decision resolves
`PREDICTION_MODEL_TRAINING_GOVERNANCE_GAP` without claiming that a training
pipeline or model exists. The current blockers are now the absence of the
pipeline and dataset, the absence of four approved model artifacts, and the
unimplemented V4-076. The upstream acceptance blocker is resolved as status
drift by the live V4-038..V4-048 reconciliation.

## 8. Impact audit

- Production/Supabase: no access, read, write, deployment, or credential use.
- Migration: none added or applied.
- V3.3.3: no source, path, data, contract, or runtime modified.
- Git boundary: changes are governance documents, a static validator, and
  focused governance tests only.

## 9. Current BATCH-15 training cross-reference

The current active training status is maintained by the EWP-003 `r002`
contract remediation review. Its runtime contract entry is
`B15-EWP-003 READY FOR IMPLEMENTATION`, but no execution authorization is
granted. The current EWP-002 dataset is hash-bound with zero candidate and
zero usable samples (`ZERO_ARCHIVED_CANDIDATES`); real-data split readiness
and formal model-fit readiness remain `BLOCKED`.
