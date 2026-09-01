# JCFB V4 Migration Rollforward Policy 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY)

## 1. Non-negotiable policy

Migration history is append-only. A file that has been approved or applied is an immutable historical artifact. It is never edited to make a later state look correct, never reused under another meaning, and never repaired by rewriting its applied row.

The preferred repair is a new forward migration with a new `migration_id`, sequence, metadata, hash, review, and audit evidence. A failed gate remains visible. `DROP ... CASCADE`, destructive table recreation, hard-delete cleanup, and deletion of historical evidence are not routine repair strategies.

## 2. Lifecycle states

| State | Meaning | Allowed next action |
|---|---|---|
| `DRAFT` | Design exists but has not passed approval | Review, canonicalize, or supersede before approval |
| `APPROVED_FOR_DEPLOYMENT` | Human approval and all pre-apply gates passed | Execute exactly once in the named target |
| `APPLIED` | Apply and all acceptance gates passed; history recorded | No content change; later change is a new migration |
| `FAILED` | The migration or a gate failed | Record incident/partial state and design a remediation migration |
| `SUPERSEDED` | A new design replaces an un-applied draft | Preserve the old file and reason; do not reuse its number |

`APPLIED` is not a synonym for “SQL returned without an error.” It requires `PRECHECK_PASS`, DDL and constraint evidence, security and trigger evidence, view and smoke evidence, advisor review, no-future-leakage validation, V3.3.3 isolation, Secret Scan, and a migration history row.

## 3. Pre-production first deployment

Before any migration has entered Production and while the target contains no retained V4 data/evidence, a limited rollback may be approved for empty objects in reverse dependency order. This exception requires:

- explicit human approval and an audit event;
- proof that no later migration, application, view, audit row, or external consumer depends on the object;
- a disposable/staging target or a documented empty-target decision;
- preservation of the migration file and its DRAFT/FAILED history.

Rollback removes an empty deployment state; it does not rewrite history or alter V3.3.3. Extension removal or namespace removal is allowed only when it is unused and explicitly approved.

## 4. After Production acceptance

Once a migration or any object it created is accepted by Production:

- the original file, identity, hash, and history row are immutable;
- no down migration may delete or rewrite Frozen Inputs, Frozen Predictions, results, reviews, Tier A samples, audit rows, or public publication history;
- a defect creates a new forward migration and, if relevant, a new contract/schema/revision identity;
- a role, version, hash, or public-boundary mistake is an incident, not a reason to edit the old file;
- rollback of a model/release uses a new Production identity and pointer event, not silent reactivation of a historical row;
- public withdrawal is an append-only projection/status event followed by a reviewed forward view or grant change.

## 5. Partial apply and failure

If an operation cannot be atomically rolled back or the executor loses certainty about commit state:

1. Stop immediately; do not continue with the next sequence.
2. Record the target, migration identity, operation, actor, observed state, and uncertainty as `FAILED`/`PARTIAL` in the deployment incident channel.
3. Reconcile the catalog and migration history with read-only inspection.
4. Do not rerun the same migration identity with broader `IF NOT EXISTS` guards.
5. Design and review a new forward remediation migration that either completes or safely adapts the state without erasing evidence.
6. Re-run the acceptance gates for the repaired state.

A database transaction failure may roll back uncommitted DDL. It cannot undo a committed prior migration or erase a failed attempt record. A rejected write that rolls back cannot create an audit row in the same transaction; rejected-attempt telemetry must be recorded by a separate controlled channel without modifying the protected predecessor.

## 6. Correction examples

| Defect | Correct response | Forbidden response |
|---|---|---|
| Missing constraint in an unapplied draft | Fix the draft before approval, recanonicalize, or supersede it | Pretend the old hash was correct |
| Constraint missing after Production | New forward migration adds it, with advisor/smoke evidence | Edit the applied SQL or applied row |
| Result correction | New `official_results` revision and new review correction chain | Update/delete the old result |
| Frozen Prediction defect | New pre-match revision if contract permits; preserve predecessor | Update the historical Frozen Prediction |
| Public view leaks a field | Forward view/grant repair plus incident and withdrawal evidence | Delete publication history or rewrite the old migration |
| Failed partial DDL | Reconcile and remediate forward | Drop/recreate historical data to look clean |

## 7. Data and audit preservation

All audit-critical rows remain append-only: source snapshots, evidence, Frozen Input after freeze, Feature Bundles used formally, Engine Runs, Predictions, Frozen Predictions, results, reviews, Tier A, promotion, calibration, incidents, audit logs, and public projection revisions. Corrections include predecessor, reason, actor, time, before/after evidence, and new hashes where applicable.

The policy never authorizes a V3.3.3 import, rename, drop, alter, correction, or shared output write.
