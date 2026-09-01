# JCFB V4 Migration Preflight 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY; PREFLIGHT NOT RUN)

## 1. Purpose

Preflight is a deployment gate, not a best-effort checklist. It runs against the explicitly named target and produces an attributed result for every critical item. Any critical failure is `BLOCKED`; the executor must not continue to the next migration.

This repository run did not contact a database. Every target-dependent item below is `NOT_RUN` for V4-011.

## 2. Required preflight checks

| ID | Check | Required evidence | Failure outcome |
|---|---|---|---|
| PF-01 | Target project identity | Human-confirmed Supabase project/environment/ref; no secret value | `BLOCKED` if absent, ambiguous, or wrong environment |
| PF-02 | Database version | `server_version_num`, major version, provider/runtime | `BLOCKED` if outside approved compatibility range |
| PF-03 | Required extensions | Availability/owner/version for `pgcrypto` or approved UUIDv7 provider; no silent assumption | `BLOCKED` if unavailable or unapproved |
| PF-04 | Security-invoker support | Target version proves `security_invoker=true`, or approved old-version fallback | `BLOCKED` if neither path is proven |
| PF-05 | Existing conflicting schemas/tables | Catalog report for `core`, `market`, `context`, `model`, `evaluation`, `governance`, `public`, and migration tables | `BLOCKED` on unapproved collision |
| PF-06 | V3.3.3 isolation | Read-only catalog/path review proving no V4 rename/drop/alter/FK/import path to V3.3.3 | `BLOCKED` on any overlap |
| PF-07 | V4 namespace state | Empty/new V4 namespace, or explicit coexistence approval with object-by-object diff | `BLOCKED` when state is unknown |
| PF-08 | Role and permission availability | `service_role`/approved backend writer, executor, auditor, schema owners, and function privileges | `BLOCKED` if actor boundary is not attributable |
| PF-09 | Migration history state | `schema_migrations`/equivalent is absent or matches the manifest exactly; no partial row | `BLOCKED` on drift or partial state |
| PF-10 | Backup/snapshot decision | Backup ID/time or written decision that no backup is required for an empty disposable target | `BLOCKED` if risk decision is missing |
| PF-11 | Maintenance window | Approved window, lock budget, timeout/rollback owner | `BLOCKED` if live target has no window |
| PF-12 | Current migrations clean | No failed/partial migration, dirty local state, or unrecorded manual DDL | `BLOCKED` until reconciled by approved forward fix |
| PF-13 | Manifest and hash readiness | Exact files, dependencies, canonical hashes, and status match the approved manifest | `BLOCKED` while any hash is pending or drifted |
| PF-14 | Runtime secrets | Required credentials exist only in runtime secret storage; repository scan is clean | `BLOCKED` if a secret is in files, logs, or command arguments |
| PF-15 | Data API exposure | Explicit schema/table/view exposure configuration; internal tables not accidentally exposed | `BLOCKED` if public exposure is unreviewed |
| PF-16 | Default privileges | `PUBLIC`, `anon`, and ordinary `authenticated` grants reviewed before RLS/policy work | `BLOCKED` if default access cannot be closed |
| PF-17 | Search path and function security | Function owner, fixed search path, execute grants, and no arbitrary SQL/table parameters | `BLOCKED` for unsafe or unreviewed function security |
| PF-18 | Production release state | No active V4 Production pointer is unintentionally replaced; first deployment has no auto-promotion | `BLOCKED` on ambiguity |

## 3. Preflight output contract

The executor records:

```text
target_project_identity
target_environment
database_version
extension_report
namespace_report
v333_isolation_report
migration_history_report
backup_decision
maintenance_window
manifest_hash_report
secret_scan_report
actor_identity
started_at
completed_at
overall_status = PRECHECK_PASS | BLOCKED
```

The report contains references and hashes, not tokens, passwords, service keys, database URLs, or cookies. `NOT_RUN` is not a pass. An unresolved check remains `BLOCKED`.

## 4. First-deployment stop conditions

Do not apply 0001 if the target project is not explicitly identified, if `pgcrypto`/UUID provider approval is unknown, if a V3.3.3 object could be affected, if a namespace conflict is not approved, if migration history is dirty, if a backup/maintenance decision is missing, if a required server actor is unavailable, or if any candidate hash is still `PENDING_CANONICAL_HASH`.

## 5. V4-011 evidence

Preflight execution: **NOT RUN by design**.

No database connection, catalog query, SQL execution, or Supabase write occurred in this task.
