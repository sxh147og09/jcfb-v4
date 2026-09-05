# JCFB V4 BATCH-15 Model Training Dependency Amendment

Active status cross-reference: EWP-001 and EWP-002 are `COMPLETE`; EWP-003
contract revision `r002` is ready for implementation review but remains
`execution_authorized=false`; EWP-004 and EWP-005 remain unauthorized.

Amendment identity: `v4-batch15-training-dependency-amendment@1.0.0`

Status: **APPROVED GOVERNANCE DAG / IMPLEMENTATION BLOCKED**

The training prerequisite dependency path is:

`Historical Data Archive -> As-Of Dataset Builder -> Temporal Split / Readiness -> Training Infrastructure -> Formal Model Fit -> Approved Model Artifact -> V4-076 -> V4-052..055`

The first five nodes are `EXECUTION_WORK_PACKAGE` identities in
`v4-batch-prerequisite-workpackages@1.0.0`; they are not nodes in the
authoritative 100-task registry. The existing task dependency register and
the V4-001 through V4-100 namespace remain unchanged by this amendment.

| Work package | Parent scope | Dependency | Current state |
|---|---|---|---|
| `B15-EWP-001` | BATCH-15; V4-076, V4-052..055 | none | `COMPLETE; EWP-001 execution authorized only` |
| `B15-EWP-002` | BATCH-15; V4-076, V4-052..055 | `B15-EWP-001` | `COMPLETE; execution authorized for Historical As-Of Dataset Builder only` |
| `B15-EWP-003` | BATCH-15; V4-076, V4-052..055 | `B15-EWP-002` | `REGISTERED_NOT_EXECUTABLE; contract r002 READY_FOR_IMPLEMENTATION` |
| `B15-EWP-004` | BATCH-15; V4-052..055 | `B15-EWP-003` | `REGISTERED_NOT_EXECUTABLE` |
| `B15-EWP-005` | BATCH-15; V4-052..055 | `B15-EWP-004` | `SEPARATE_APPROVAL_REQUIRED` |

The work-package edges are acyclic, deterministic, and mandatory. No
downstream work may skip a missing archive, dataset, split, or readiness
artifact. A work-package status or hash cannot be used to infer completion of
its parent task.

Each transition requires the work-package identity/revision, decision actor,
timestamp, dependency evidence, DoD evidence manifest, output artifact
hashes, and Git commit lineage. The registry self-hash is computed with
`v4-canonical-json@1.0` and excludes only its own `canonical_hash` field.

The EWP-001 authorization and closure evidence are recorded in
`docs/JCFB_V4_BATCH_15_B15_EWP_001_AUTHORIZATION_DECISION.md`,
`docs/JCFB_V4_BATCH_15_B15_EWP_001_ACCEPTANCE_EVIDENCE.json`, and
`docs/JCFB_V4_BATCH_15_B15_EWP_001_CLOSURE_READINESS_REVIEW.md`. EWP-002 through
EWP-005 remain unauthorized.
