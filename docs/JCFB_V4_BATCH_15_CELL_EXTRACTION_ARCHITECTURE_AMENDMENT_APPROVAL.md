# JCFB V4 BATCH-15 Cell Extraction Architecture Amendment Approval

Decision identity: `v4-batch-prerequisite-workpackages-amendment-001@1.0.0`

Decision: **APPROVED_FOR_ADDITIVE_IMPLEMENTATION_AND_FOCUSED_VALIDATION**

Date: `2026-09-07` (Asia/Shanghai)

## Scope decision

The existing `EXECUTION_WORK_PACKAGE` registry is active and contains five
historical identities. Its canonical hash, five-package cardinality, and the
COMPLETE facts for B15-EWP-001 through B15-EWP-004 must remain unchanged. The
formal-fit identity B15-EWP-005 remains `SEPARATE_APPROVAL_REQUIRED` and
`execution_authorized=false`.

The requested cell extraction work cannot be placed inside an existing package
without changing a completed scope or misrepresenting the formal-fit package.
This amendment therefore registers the next deterministic EWP namespace value
as an additive sidecar:

| Field | Decision |
|---|---|
| Additive package | `B15-EWP-006` |
| Package key | `historical-official-odds-cell-extraction-runtime` |
| Parent scope | `BATCH-15`, with the existing V4-076/V4-052..055 dependency boundary |
| Base registry | `v4-batch-prerequisite-workpackages@1.0.0` |
| Base registry hash | `sha256:2e8cc439675702173266398e632c6efbec3a283f769ac20db5432a9dece225e9` |
| Dependency | `B15-EWP-001` only; no EWP-002/003 rerun is implied |
| Authorization | Implementation, focused validation, and no-write runtime tests only |
| Historical replay | Not authorized in this amendment |

The sidecar is additive and deterministic. It does not replace, reopen, or
rewrite any existing registry entry. Its package identity is validated against
the immutable base registry hash by the focused validator.

## Non-authorized actions

This approval does not authorize accepted official odds payload writes,
historical source archive writes or revisions, r002 package generation,
EWP-002/EWP-003 reruns, EWP-005 execution, model fitting/calibration/promotion,
Production/Shadow/Public/Supabase/migration actions, or V3.3.3 modification.

## Approved outputs

The approved implementation outputs are the frozen cell extraction contract,
trace schema, versioned layout/locator registry, deterministic in-memory parser
runtime, mechanical unresolved-trace derivation, synthetic fixtures/tests,
focused validators, and the implementation report. The runtime is no-write and
does not create historical trace files as part of this amendment.
