# JCFB V4 BATCH-15 Model Training Architecture Amendment Proposal

Proposal ID: `V4-015-TRAINING-ARCH-001`

Proposal revision: `r001`

Review date: `2026-09-05` (`Asia/Shanghai`)

Status: **PROPOSED / NOT APPROVED / EXECUTION IDENTITY NOT GRANTED**

Baseline: `fbe4c5d145b0994afb5789c6b69b074c1cc71725`

## 1. Decision requested

The current JCFB V4 governance framework does not support a batch-local
prerequisite or work-package execution identity outside the authoritative
`v4-task-registry-001-100@1.0.0` registry. The existing BATCH-15 training
amendment therefore cannot grant an execution identity without a further
architecture amendment approved by the registry owner.

This document proposes that amendment. It does not create a V4 task ID,
authorize a runtime, create a dataset, or authorize model fitting.

## 2. Evidence that the current framework is insufficient

| Governing source | Current rule | Consequence |
|---|---|---|
| `docs/V4_TASK_REGISTRY_001_100.md` | The 100-row registry is the authoritative task-definition source; no training row exists. | A new training task cannot be inferred or inserted locally. |
| `docs/V4_BATCH_EXECUTION_PLAN.md` | Training is a BATCH-15 prerequisite phase and explicitly "not a new task ID". | The plan supplies no executable identity. |
| `docs/V4_TASK_DEPENDENCY_REGISTER.md` | The register intentionally adds no training task node and retains `MODEL_TRAINING_TASK_REGISTRY_AMENDMENT_REQUIRED`. | The DAG has no training work-package node or identity. |
| `docs/V4_EXECUTION_CLASSIFICATION.md` | Execution classifications are attached to the registered V4 task rows and batches. | No classification grammar exists for a batch-local work package. |
| `docs/V4_VERSION_IDENTITY_CONTRACT.md` | Formal artifacts and runs require exact identities, revisions, and hashes. | A descriptive label cannot substitute for a governed execution identity. |

The supported finding is therefore:

`CURRENT_GOVERNANCE_FRAMEWORK_DOES_NOT_SUPPORT_BATCH_LOCAL_EXECUTION_IDENTITY`

## 3. Proposed governance extension

Add a separately versioned, append-only registry for BATCH-15 prerequisite
work packages, for example:

`v4-batch-prerequisite-workpackages@1.0.0`

This registry must be an architecture/governance artifact, not a new row in
the V4-001 through V4-100 task registry. Its contract should require:

- a stable work-package identity and revision;
- `primary_batch = BATCH-15`;
- explicit relation to the existing V4-052 through V4-055 and V4-076 rows;
- classification, owner, scope, status, DoD, evidence manifest, and commit lineage;
- dependency references that do not alter the existing 100-node DAG unless a
  separately approved task-registry revision changes the DAG;
- append-only corrections and canonical content hash;
- an explicit `execution_authorized` flag that defaults to `false`;
- an explicit statement that the work package cannot authorize model fitting,
  inference, V4-076, Production, Shadow, Public, Supabase, migrations, or V3.3.3;
- validator coverage in the BATCH-15 governance validator and focused tests.

The proposed registry must be reviewed and accepted by the registry owner
before any proposed identity becomes active. Until then, the labels below are
descriptions only and must not be used as task IDs or runtime authorization.

## 4. Proposed BATCH-15 work-package decomposition

After approval, the registry may define exactly these four prerequisite units.
They are shown here for architecture review only; all four are **NOT
GRANTED**, **NOT IMPLEMENTED**, and **NOT EXECUTABLE** in this proposal.

| Unit | Proposed responsibility | Required evidence at completion |
|---|---|---|
| A | Historical As-Of Dataset Builder: cutoff reconstruction, Feature Bundle reconstruction, Statistical/Football/Market/Tactical references, BATCH-14 quality/gate reconstruction, labels, eligibility, deduplication, dataset artifact and hash. | Dataset manifest, per-sample lineage, eligibility decisions, label separation proof, leakage audit, artifact/hash replay evidence. |
| B | Temporal Split Builder: time-ordered train/validation/holdout and walk-forward/rolling-origin support, same-match partition protection, split artifact and hash. | Split manifest, boundary proof, same-match audit, holdout non-use proof, deterministic split hash. |
| C | Training/Fitting Infrastructure: candidate family execution, governed hyperparameter consumption, deterministic seeds, parameter artifact generation, metric computation, model artifact packaging. Formal four-engine fitting remains out of scope for the current entry review. | Implementation/config identities, deterministic replay evidence, parameter/artifact schema evidence, evaluation output contract evidence. |
| D | Training Readiness Evaluator: usable sample count, class distribution, temporal and league coverage, required feature coverage, blocked/ineligible/partial counts. | Readiness report with explicit `UNKNOWN`/`NOT_AVAILABLE` semantics and no conversion of unavailable data into usable samples. |

The unit decomposition does not change the ownership or implementation scope
of V4-052 through V4-055. It only supplies the missing prerequisite execution
identity after approval.

## 5. Approval and activation conditions

The amendment may move from `PROPOSED` to `APPROVED` only when all of the
following are recorded:

1. The registry owner approves the work-package registry contract and exact
   identity grammar.
2. The Task Registry, Batch Plan, Dependency Register, Execution Classification,
   and BATCH-15 governance evidence cross-reference the same approved registry
   revision.
3. A focused validator proves no V4-001 through V4-100 task ID was added,
   renamed, split, or silently reclassified.
4. Each of A-D has an independent status, DoD, evidence manifest, and Git
   commit lineage.
5. `execution_authorized` remains `false` until the historical source-lineage
   review and the next BATCH-15 readiness review pass.
6. The four engine-specific model artifacts remain empty and no formal fitting
   is executed as part of the amendment.

## 6. Current disposition

`ARCHITECTURE_AMENDMENT_REQUIRED`

`MODEL_TRAINING_TASK_REGISTRY_AMENDMENT_REQUIRED`

`PREDICTION_TRAINING_READINESS_BLOCKED`

The registry-owner decision is the only next action authorized by this
proposal. No dataset builder, split builder, fitting infrastructure, or
readiness runtime may be implemented under an unapproved identity.
