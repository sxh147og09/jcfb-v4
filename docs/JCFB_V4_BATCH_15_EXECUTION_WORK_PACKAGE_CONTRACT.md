# JCFB V4 Execution Work Package Contract

Contract identity: `execution-work-package@1.0.0`

Registry identity: `v4-batch-prerequisite-workpackages@1.0.0`

Status: **ACTIVE GOVERNANCE CONTRACT**

## Purpose and namespace

`EXECUTION_WORK_PACKAGE` is a governed execution container for a mandatory
prerequisite or implementation sub-work of an already approved batch or task.
It is not a V4 Task, does not consume `V4-001` through `V4-100`, and may not
replace a Task Registry row. The authoritative task registry remains
`v4-task-registry-001-100@1.0.0`.

The deterministic identity grammar is:

`work_package_id = B<parent_batch_number>-EWP-<sequence_3_digits>`

For example, `B15-EWP-001` is derived from the ordered registry sequence; it
is not a free-form runtime string. The key uses lowercase kebab case and the
revision uses `r###`. Duplicate IDs, task-shaped IDs, missing parent scope,
and unregistered temporary labels are rejected.

## Required envelope

Every work package requires the following immutable-or-append-only fields:

| Field | Rule |
|---|---|
| `work_package_key` / `work_package_id` | Deterministic identity; unique in the registry |
| `revision` | Append-only revision identity |
| `entity_type` | Exactly `EXECUTION_WORK_PACKAGE` |
| `parent_batch` | Required batch binding |
| `parent_task_scope` | One or more existing `V4-###` scopes |
| `status` | Controlled lifecycle state |
| `execution_authorized` | Explicit boolean; `false` until separate authorization |
| `dependencies` | Only registered work-package IDs; acyclic |
| `definition_of_done` | Concrete evidence-based completion conditions |
| `evidence_manifest` | Named evidence artifacts and hashes |
| `commit_lineage` | Required Git commit IDs; no completion without lineage |
| `output_artifacts` | Explicit logical output identities |
| `artifact_hash` | Output hash or `NOT_GENERATED` |
| `canonical_hash` | SHA-256 over the canonical envelope excluding itself |

## Lifecycle and authorization

Allowed governance states are `REGISTERED_NOT_EXECUTABLE`,
`READY_FOR_SEPARATE_AUTHORIZATION`, `EXECUTING`, `COMPLETE`, `BLOCKED`, and
`SEPARATE_APPROVAL_REQUIRED`. A status transition is append-only and must
include the actor, decision, evidence manifest, timestamp, and commit
lineage. A work package may not set `execution_authorized=true` merely
because its parent is approved.

`COMPLETE` requires the DoD, evidence, output hashes, canonical manifest hash,
and Git lineage. It never updates the parent V4 task status. Formal fitting
requires a new explicit approval after dataset and readiness gates pass.

## Boundary rules

The work-package mechanism cannot authorize V4-076, V4-052 through V4-055,
Score, Calibration, Shadow, Production, Public, Supabase, migrations, or any
V3.3.3 modification. It cannot consume V3 model artifacts or convert test
fixtures into historical training data. Unknown or unavailable evidence is
recorded as `UNKNOWN`, `NOT_AVAILABLE`, or `BLOCKED`.

## Canonical hash profile

All registry and manifest hashes use `SHA-256` and
`v4-canonical-json@1.0`: UTF-8, recursively lexicographic object-key order,
semantic array order preserved, compact separators, no BOM, and
`canonical_hash` omitted while computing the self-hash. Hashes are rendered as
`sha256:<64 lowercase hex characters>`. Output artifact hashes are separate
from the registry self-hash.

## BATCH-15 registration

The active registry contains five identities: historical data bootstrap and
archive, historical as-of dataset builder, temporal split and readiness,
training/fitting infrastructure, and formal model fit and validation. Their
dependency chain is strictly ordered and remains separate from the existing
100-task DAG.
