# JCFB V4 Batch Acceptance Rules 1.0

Status: `V4-012–V4-100 PLANNING AUDIT PASS` / `EXECUTION NOT AUTHORIZED`

Rules Identity: `v4-batch-acceptance-rules@1.0.0`
Revision: `r002`
Audit Date: `2026-09-01` (`Asia/Shanghai`)
Execution Declaration: **NO V4-012+ TASK EXECUTED**

## 1. Purpose, authority, and source of truth

These rules govern future grouping, execution, acceptance, commit traceability, and promotion. They do not authorize V4-012, database writes, model execution, Shadow, Promotion, Production activation, public release, or any V3.3.3 change.

Authority order:

1. `docs/V4_CONSTITUTION.md`.
2. `docs/V4_VERSIONING_STANDARD.md` and the V4 identity/compatibility contracts.
3. `docs/V4_ARCHITECTURE_BLUEPRINT.md` and `docs/V4_RUNTIME_ROLE_BOUNDARY.md`.
4. `docs/V4_DATA_CONTRACT.md` and `docs/V4_CANONICAL_DATA_MODEL.md`.
5. `docs/V4_DATABASE_SCHEMA_BLUEPRINT.md` and `docs/V4_DATABASE_MIGRATION_DESIGN.md`.
6. `docs/V4_TASK_REGISTRY_001_100.md` for task definitions and `docs/V4_BATCH_EXECUTION_PLAN.md` for coordination.
7. These batch rules.

If a batch convenience conflicts with a higher rule, the affected task is BLOCKED and the batch cannot claim PASS.

## 2. Task and batch semantics

### 2.1 Classification labels

- `BATCHABLE`: may share a controlled implementation cycle with adjacent tasks.
- `PARALLEL`: may develop concurrently after its declared upstream contract is ready.
- `SERIAL`: must follow its declared dependency in order.
- `HARD_GATE`: requires separate evidence, acceptance, and explicit Human Approver or reviewer authorization.

Labels describe execution constraints. They do not change task completion state.

### 2.2 Ordinary batch rule

An ordinary batch may coordinate multiple tasks, but:

1. every child task is named in the authoritative registry and assigned exactly one primary batch;
2. every child task has its own artifact, validation evidence, status, and Git trace;
3. every child task is independently accepted before its checkbox changes;
4. a successful child never implies another child passed;
5. the batch is not COMPLETE while any required child is FAIL, BLOCKED, NOT_VERIFIED, or NOT_IMPLEMENTED;
6. a child failure does not cascade COMPLETE to siblings;
7. a secondary parallel group never changes primary ownership.

### 2.3 Registry rule

`docs/V4_TASK_REGISTRY_001_100.md` is the authoritative definition source. The checklist is the status view. If the registry, checklist, classification register, dependency register, and batch plan disagree on a name, dependency, primary batch, or gate, the batch is BLOCKED until reconciled. No architecture noun or batch name may be promoted into an invented task.

## 3. Hard-gate rules

| Gate ID | Task | Hard-gate type | Batch | Required rule | Authorization |
|---|---|---|---|---|---|
| HG-01 | V4-018 | Formal Supabase Schema Apply | BATCH-04 | Apply only the exact approved immutable manifest after preflight, disposable validation, schema diff, smoke, RLS, trigger, and rollback evidence | Explicit Human Approver before write |
| HG-02 | V4-019 | Production Database Write Activation | BATCH-04 | Open only the named V4 namespace and role boundary; prove V3 isolation and audit event | Explicit Human Approver |
| HG-03 | V4-097 | Production Readiness Review | BATCH-27 | E2E dry run, security, restore, rollback, regression, public safety, and unresolved-risk review must PASS | Explicit Human Approver |
| HG-04 | V4-098 | Shadow-only Pilot / Promotion Review | BATCH-28 | Use real pre-kickoff Shadow evidence and required same-match/same-frozen-input pairing; no auto-promotion | Independent reviewer and explicit approval |
| HG-05 | V4-099 | Production Activation | BATCH-29 | Create one new immutable Production identity and prove exactly one active revision plus rollback | Explicit Human Approver |
| HG-06 | V4-100 | Final Production Release / canonical pointer switch | BATCH-30 | Publish only approved Production projection with release identity, business timestamps, monitoring, first sample, and rollback target | Explicit release approval |

Missing approval evidence means BLOCKED, not PASS. An unattended agent cannot approve and execute its own Production migration, Promotion, activation, pointer switch, or release.

## 4. Database and runtime isolation

The following remain forbidden in this recovery and in ordinary planning batches:

- applying `database/migrations/v4/` to Production or Supabase;
- treating blueprint SQL or a registry entry as authorization;
- creating or running a migration harness;
- writing a registry row, canonical fact, model row, or any database row;
- importing, rewriting, deleting, or migrating historical formal data;
- executing a model or producing a match prediction;
- executing or backfilling Shadow;
- activating Production or switching a release pointer;
- publishing a Public Production output;
- changing, copying, renaming, migrating, or overwriting JCFB V3.3.3.

Future staging validation must use an explicitly isolated target with no retained Production data and no V3.3.3 objects. A rollback of uncommitted DDL is not permission to rewrite committed history.

## 5. Information, role, and history rules

- Pre-match input must satisfy `input_timestamp <= prediction_cutoff_at < kickoff_at`.
- Unknown, unavailable, not-verified, conflicted, stale, blocked, and future data remain explicit.
- Official five-market odds remain separate from external market signals.
- Objective facts remain separate from model interpretation.
- Frozen Input precedes immutable Frozen Prediction; revisions append with explicit supersedes lineage.
- Production, Shadow, and Experiment identities and outputs remain separate.
- Experiment cannot become Forward Tier A by relabeling; late Shadow cannot become promotion evidence.
- Exact-score selection consumes an approved distribution and cannot rewrite it.
- Consensus preserves raw outputs and disagreement; probability is not confidence.
- Public Web is read-only and never runs a model or bypasses a gate.
- V3.3.3 can be read only through an approved objective-facts/benchmark boundary and is never mutated or copied into V4.

## 6. Per-batch acceptance procedure

1. Freeze the batch manifest: Batch ID, exact registry task IDs/names, classifications, upstream dependencies, artifacts, and allowed operations.
2. Verify every child exists in the registry and has one primary batch.
3. Confirm contract, version, schema, migration, configuration, dataset, role, and hash identities.
4. Execute only operations allowed for that batch and role.
5. Validate each child independently and record PASS/FAIL/BLOCKED/NOT_VERIFIED.
6. Run the batch-level cross-checks.
7. Run Secret Scan and `git diff --check`.
8. Commit focused evidence and require `Working Tree = CLEAN`.
9. Require all upstream batches PASS and all required approvals before crossing a gate.

## 7. Mandatory end-of-batch checks

| Check | Required result | Failure action |
|---|---|---|
| Secret Scan | PASS; no key, token, password, cookie, service key, private credential, or database URL introduced | Do not accept or commit the affected artifact; rotate/revoke any exposed credential outside Git |
| Self Audit | PASS for child scope, labels, dependencies, evidence, and boundary rules | Batch remains BLOCKED |
| Cross-Doc Consistency | PASS against Constitution, versioning, runtime, data, schema, migration, registry, checklist, and batch docs | Resolve contradiction |
| Child acceptance | Each child independently PASS or explicitly remains BLOCKED/NOT_VERIFIED | Never cascade COMPLETE |
| Git traceability | Focused commit records accepted artifact/evidence | Do not call batch accepted |
| Working Tree | CLEAN | Stop and inspect |

If remote push is unavailable in the Codex environment, report `Remote Push: BLOCKED_ENV`; retain local commits and use GitHub Desktop. Do not request or place a token in chat or repository files.

## 8. Stop conditions

Stop when a task name, scope, dependency, input time, provenance, hash, role, or version is missing; future information enters; official and external odds are conflated; a child fails; a gate lacks approval; history would be overwritten; two Production revisions exist; a Shadow/Experiment path can write Production; a secret appears; or a V3.3.3 path would be modified.

The safe outcome is BLOCKED, RUN_INVALID, or NOT_VERIFIED with retained evidence. Recovery uses a new forward identity or governed revision and does not erase the failed attempt.

## 9. Checklist and current disposition

Planning may update the mapping and registry, but may not mark V4-012–V4-100 `[x]`. The current registry and batch plan now provide complete definitions and unique primary mapping, so the planning audit is PASS. Execution remains NOT_STARTED.

Next execution batch: **BATCH-01 — Migration Dry-Run & Validation Harness**. No task from that batch has begun.
