# JCFB V4 Batch Acceptance Rules 1.0

Status: V4-012–V4-100 PLANNING AUDIT BLOCKED (SOURCE TASK REGISTER INCOMPLETE)

Rules Identity: `v4-batch-acceptance-rules@1.0.0`

Revision: `r001`

Audit Date: `2026-09-01` (`Asia/Shanghai`)

Execution Declaration: **NO V4-012+ TASK EXECUTED**

## 1. Purpose and precedence

These rules govern how future V4 work may be grouped, executed, accepted, committed, and promoted. They are planning and governance rules only. They do not authorize V4-012, a migration harness, a database write, a model run, a Shadow run, a Production activation, a public release, or any change to JCFB V3.3.3.

The authority order is:

1. `docs/V4_CONSTITUTION.md`.
2. `docs/V4_VERSIONING_STANDARD.md` and the V4 identity/compatibility contracts.
3. `docs/V4_ARCHITECTURE_BLUEPRINT.md` and `docs/V4_RUNTIME_ROLE_BOUNDARY.md`.
4. `docs/V4_DATA_CONTRACT.md` and `docs/V4_CANONICAL_DATA_MODEL.md`.
5. `docs/V4_DATABASE_SCHEMA_BLUEPRINT.md` and `docs/V4_DATABASE_MIGRATION_DESIGN.md`.
6. These batch rules.

If a batch convenience conflicts with a higher rule, the affected task is `BLOCKED` and the batch cannot claim PASS.

## 2. Task and batch semantics

### 2.1 Classification labels

- `BATCHABLE`: the task may share a controlled implementation batch with adjacent tasks.
- `PARALLEL`: the task may run concurrently after its declared upstream contract is ready.
- `SERIAL`: the task must follow its declared dependency in order.
- `HARD_GATE`: the task or operation requires separate acceptance and explicit Human Approver authorization.

A task may have multiple labels. Labels describe execution constraints; they do not change the task's completion rule or checklist state.

### 2.2 Ordinary batch rule

An ordinary batch may complete multiple checklist items in one coordinated work cycle, but:

1. every child task is named and assigned one primary batch;
2. every child task has its own artifact, validation evidence, status, and Git trace;
3. every child task is independently marked PASS before its checkbox can be marked `[x]`;
4. a successful child never implies that another child passed;
5. the batch is not `COMPLETE` while any required child is `FAIL`, `BLOCKED`, `NOT_VERIFIED`, or `NOT_IMPLEMENTED`;
6. a child task failure must not automatically mark all other tasks in that batch `COMPLETE`;
7. a batch may be split or resumed, but it may not conceal a failed child by moving it to a neighboring batch.

### 2.3 Source-register rule

The authoritative task name and scope must come from the Master Checklist or an explicitly approved task register. Architecture nouns, suggested batch names, and guesses from task numbering are not substitutes. When a source task is missing, use `UNRESOLVED` and `UNASSIGNED`; do not assign one of the four execution labels and do not declare the plan complete.

## 3. Hard-gate rules

HARD_GATE operations are never crossed because an ordinary batch passed. Each gate has a separate evidence packet, approval event, acceptance result, and audit trail. A gate-only batch may contain multiple related approval events, but each event remains separately accepted.

| Gate ID | Hard-gate type | Candidate batch | Required rule | Ordinary task batching | Authorization |
|---|---|---|---|---|---|
| HG-01 | Production DB Migration Apply | BATCH-04 | Apply only the exact approved immutable migration files after all preflight, dry-run, catalog, smoke, RLS, trigger, and rollback evidence passes. | NO | Explicit Human Approver before write. |
| HG-02 | Supabase formal Schema Apply / write | BATCH-04 | A Supabase write is a named deployment event, not an inference from a SQL file or a successful local design check. | NO | Explicit Human Approver and named target. |
| HG-03 | Production Model Activation | BATCH-29 | Activation creates a new immutable Production identity and proves exactly one active Production revision. | NO | Explicit Human Approver after Promotion Review. |
| HG-04 | Shadow → Promotion Review | BATCH-28 | Review only uses real pre-kickoff Shadow evidence with required same-match and same-`frozen_input_hash` pairing. | NO | Independent reviewer decision. |
| HG-05 | Promotion Review → Production | BATCH-29 | No direct Experiment/Shadow-to-Production shortcut; compatibility, calibration, regression, integrity, and Forward evidence are required. | NO | Explicit Human Approver. |
| HG-06 | Frozen Prediction / Historical Integrity migration | BATCH-27 gate-only path | Any migration or operation that could affect Frozen Prediction, Frozen Input, historical Result, Review, Tier A, or audit lineage is isolated, append-only, and separately approved. | NO | Explicit Human Approver plus integrity review. |
| HG-07 | Any operation that may modify historical formal data | BATCH-27 gate-only path | Preserve predecessor rows and hashes; use a governed correction or new forward migration. No cleanup or overwrite is allowed. | NO | Explicit approval and rollback/incident plan. |
| HG-08 | Public Production Release / canonical output pointer switch | BATCH-30 | Publish only an approved Production projection with safe fields, real business timestamps, release identity, and a rollback target. | NO | Explicit release approval. |

Missing approval evidence means `BLOCKED`, not `PASS`. An unattended agent cannot approve and execute the same Production migration or promotion.

## 4. Database and execution isolation

The following are forbidden in an ordinary batch and forbidden in this planning audit:

- applying `database/migrations/v4/` to Production or Supabase;
- treating blueprint SQL as authorization;
- creating or running a migration harness;
- writing a registry row or any other database row;
- importing, rewriting, deleting, or migrating historical formal data;
- executing a model or producing a match prediction;
- executing or backfilling Shadow;
- activating Production or switching a release pointer;
- publishing a Public Production output;
- changing, copying, renaming, migrating, or overwriting JCFB V3.3.3.

Future disposable/staging validation must use an explicitly named isolated target, no retained Production data, and no V3.3.3 objects. A failure stops the chain and is preserved as evidence. A rollback of uncommitted DDL is not permission to rewrite earlier committed history.

## 5. Information, role, and history rules

Every future formal task must remain compatible with the existing V4 contracts:

- Pre-match input must satisfy `input_timestamp <= prediction_cutoff_at < kickoff_at`.
- Unknown or unavailable facts remain explicitly `UNKNOWN`, `UNAVAILABLE`, `BLOCKED`, or `NOT_VERIFIED`.
- Official five-market odds remain separate from external market signals.
- Objective facts remain separate from model interpretation.
- Frozen Input precedes Frozen Prediction; Frozen Prediction is append-only and immutable.
- Production, Shadow, and Experiment identities, outputs, and revisions remain separate.
- Experiment cannot become Forward Tier A by relabeling; late Shadow cannot become promotion evidence.
- Exact-score selection consumes a score distribution and cannot rewrite it.
- Consensus preserves individual outputs and disagreement; probability is not confidence.
- Public Web is read-only and never runs a model or bypasses a gate.
- V3.3.3 can be read only through an approved objective-facts/benchmark boundary and is never mutated or copied into V4.

## 6. Per-batch acceptance procedure

Every batch, including a gate-only batch, follows this sequence:

1. Freeze the batch manifest: Batch ID, source task IDs, exact names, classifications, upstream dependencies, expected artifacts, and allowed operations.
2. Verify that every source task exists and has exactly one primary batch. A missing task register blocks the batch.
3. Confirm the applicable version, contract, configuration, implementation, input, output, dataset, schema, and migration identities. Do not use `latest`, `current`, or a nickname as identity.
4. Execute only the operations allowed for that batch and role.
5. Validate each child task independently and record PASS/FAIL/BLOCKED/NOT_VERIFIED.
6. Run the batch-level cross-checks below.
7. Commit the accepted evidence with a focused message. Never use a checklist checkbox as a substitute for an artifact or test.
8. Require `Working Tree = CLEAN` before handing off to the next batch.
9. Require the next batch's upstream dependencies to be PASS and any required Human Approver decision to be present.

## 7. Mandatory end-of-batch checks

Every batch must finish with all of the following:

| Check | Required result | Failure action |
|---|---|---|
| Secret Scan | PASS; no key, token, password, cookie, service key, private credential, or database URL is introduced. | Do not commit the affected artifact; rotate/revoke any exposed credential outside Git. |
| Self Audit | PASS for the batch's own scope, labels, dependencies, evidence, and boundary rules. | Batch remains BLOCKED. |
| Cross-Doc Consistency | PASS against Constitution, versioning, runtime, data, schema, migration, and checklist documents. | Resolve the contradiction before acceptance. |
| Child-task acceptance | Every child task independently PASS or explicitly remains BLOCKED/NOT_VERIFIED. | Never cascade COMPLETE. |
| Git traceability | Focused commit exists on the intended branch and records the artifact/evidence. | Do not call the batch accepted. |
| Working Tree | `CLEAN`. | Stop; inspect and resolve uncommitted changes. |

`git diff --check` must pass for documentation or code changes. If Remote Push is unavailable in the Codex environment, report `Remote Push: BLOCKED_ENV`, retain local commits, and use GitHub Desktop to push before changing computers. Do not request or place a token in chat or repository files. A blocked remote push does not invalidate a locally complete batch when all other traceability conditions pass, but cross-computer synchronization remains required.

## 8. Failure, rollback, and stop conditions

Stop the current batch immediately when any of these occurs:

- a task name, scope, or dependency cannot be proven from the source register;
- a required input, time, provenance, hash, role, or version is missing;
- a future-information or post-kickoff condition is detected;
- official and external odds are conflated;
- a child task fails a required positive or negative test;
- a HARD_GATE is reached without explicit approval;
- a migration or runtime path would overwrite immutable history;
- more than one active Production revision exists or a pointer is ambiguous;
- a Shadow/Experiment path can write Production, Frozen Prediction, Tier A, Review, or Public Projection;
- a secret or unsafe private field appears in a tracked artifact;
- a proposed optimization skips provenance, validation, timestamp, hash, freeze, or audit checks;
- any V3.3.3 path would be modified, copied, renamed, migrated, or exposed.

The safe outcome is `BLOCKED`, `RUN_INVALID`, or `NOT_VERIFIED` with retained evidence. Recovery uses a new forward-fix identity or a new governed revision; it does not erase the failed attempt.

## 9. Master Checklist rule

This planning audit may add a Batch Mapping section but may not change the completion state of V4-012–V4-100. In particular:

- no V4-012+ item may receive `[x]` from a planning document;
- a batch name is not a completion claim;
- a task is checked only after design, engineering artifact, validation, documentation, and Git traceability all pass;
- a source-register gap must remain visible in the checklist and classification register.

## 10. Current audit disposition

The current repository provides one verified future task (`V4-012`) and no authoritative task entries for V4-013–V4-100. The four planning artifacts therefore remain `BLOCKED`, even though the candidate 30-node envelope graph is acyclic and the hard gates are explicitly isolated.

Required remediation: restore or supply the exact V4-012–V4-100 task register, replace every unresolved classification row, rerun the unique primary-batch audit and cycle check, and only then decide whether V4-012 may begin.
