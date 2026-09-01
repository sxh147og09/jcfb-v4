# JCFB V4 BATCH-03 Implementation Note

Batch: `BATCH-03 — Staging Readiness & Migration Acceptance Package`
Tasks: `V4-016`, `V4-017`
Boundary: local static/no-write package only

## Artifact map

| Task | Implementation | Contract/config | Evidence |
|---|---|---|---|
| V4-016 | `tools/migration_harness/readiness.py` | `v4_batch_03_readiness_contract.json`; `v4_batch_03_staging_target.template.json` | `docs/V4_STAGING_READINESS.md`; readiness unit tests |
| V4-017 | `tools/migration_harness/acceptance.py` and CLI commands | `v4_batch_03_acceptance_package.schema.json`; `v4_batch_03_evidence_index.json` | `docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md`; JSON/Markdown acceptance report |

## Verified behavior

- Environment classification covers `DISPOSABLE_LOCAL`, `STAGING`, and `PRODUCTION`.
- Readiness states are explicit: `NOT_READY`, `READY_FOR_DISPOSABLE_DRY_RUN`, `READY_FOR_STAGING_DRY_RUN`, `READY_FOR_PRODUCTION_REVIEW`, and `BLOCKED`; `READY_FOR_PRODUCTION_APPLY` is prohibited.
- The target template has safe identity fields, distinct role placeholders, PostgreSQL/extension/network/permission/namespace/history/backup/partial-state/reset/teardown/retention fields, and an environment-variable-only credential reference.
- The absent disposable database remains `RUNTIME_PENDING_DISPOSABLE_DB`; no connector, database, SQL, migration apply, or service installation is attempted.
- The acceptance packet assembles manifest 0001–0009, expected schema/object catalog, PF-01..PF-18, smoke/negative matrices, RLS/trigger/view/security, no-future, Tier A, migration history, schema diff, roll-forward, signoff, and evidence hashes.
- The evidence index resolves all 80 registered references to checked-in contracts or governance sources without storing secrets.
- Twenty smoke runtime cases and fifteen database-enforcement negative cases are registered as pending. The 22 pure negative refusal contracts are actual local unit results, not database claims.
- The report records `Production DB Writes Performed = NO`, `Supabase Writes Performed = NO`, `V3.3.3 mutation = NO`, and `NO_PRODUCTION_APPLY_IN_THIS_BATCH = TRUE`.

## Handoff

Human approval, migration execution, and audit signoff remain separate pending roles. BATCH-04 is a separate HARD_GATE and is not executed or entered automatically.
