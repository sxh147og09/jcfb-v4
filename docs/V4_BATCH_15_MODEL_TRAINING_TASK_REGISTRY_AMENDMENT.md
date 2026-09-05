# V4 BATCH-15 Model Training Task Registry Amendment

Amendment ID: `V4-015-TRAINING-TASK-001`
Status: **GOVERNANCE ACTIVE / EXECUTION IDENTITY NOT GRANTED**

## Decision

Training dataset construction, fitting, and out-of-time evaluation are a
mandatory BATCH-15 readiness phase before V4-052 through V4-055. This
amendment creates no task ID and does not rename or split an existing task.

The current registry has no formal training task identity. Therefore the
execution disposition is:

`MODEL_TRAINING_TASK_REGISTRY_AMENDMENT_REQUIRED`

Actual training/fitting is paused until the registry owner either confirms
that the BATCH-15 prerequisite identity is sufficient or adds a separately
approved identity through the normal governance process. An agent must not
invent `V4-101`, `V4-052A`, or an equivalent node.

This amendment does not authorize V4-052/V4-053/V4-054/V4-055, V4-076,
Score, Risk/Abstention, Shadow, Production, Public, Supabase, migrations, or
any V3.3.3 change.

## 2026-09-05 registry-owner assessment

The current governance framework does not define a batch-local prerequisite or
work-package identity outside the `v4-task-registry-001-100@1.0.0` task rows.
The BATCH-15 plan and dependency register explicitly describe training as a
prerequisite phase and prohibit adding a task node. Therefore this amendment
cannot grant an execution identity by itself, and the disposition remains
`MODEL_TRAINING_TASK_REGISTRY_AMENDMENT_REQUIRED`.

A formal architecture amendment proposal has been recorded in
`docs/JCFB_V4_BATCH_15_MODEL_TRAINING_ARCHITECTURE_AMENDMENT_PROPOSAL.md`.
It is a proposal only: no batch-local identity is active, and no runtime work
package or training implementation is authorized.
