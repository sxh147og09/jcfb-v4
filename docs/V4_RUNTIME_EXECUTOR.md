# JCFB V4 PostgreSQL Runtime Executor 1.0

## Purpose

`tools/migration_harness/runtime_executor.py` is the explicit runtime boundary
for the nine disposable/staging candidate migrations. The historical BATCH-02
dry-run runner remains no-write and is not replaced. This executor is a
separate opt-in path and defaults to a plan.

The flow is:

```text
candidate manifest
  -> canonical hash verification
  -> target descriptor validation
  -> static preflight (before connector invocation)
  -> environment-only connection settings
  -> read-only PostgreSQL catalog preflight (before DDL)
  -> one transaction per candidate plus immutable history row
  -> runtime-case adapter
  -> redacted local report
```

## Target boundary

Only `DISPOSABLE_LOCAL` and an explicitly approved `STAGING` descriptor are
allow-listed. `PRODUCTION`, `PRODUCTION_SUPABASE`, and
`PRODUCTION_APPLY` are hard-blocked before a driver connection is opened.
The target descriptor must assert the V3.3.3 boundary and the absence of
retained Production data. No V3.3.3 object or data is read or written.

The default descriptor produced by `default_disposable_target()` is local-only,
non-secret, and uses the database identity supplied by `--database-name`.
Staging requires a separate explicit target JSON file and independent review.

## Driver and credentials

The adapter lazily discovers `psycopg` first and `psycopg2` second. It does not
open a connection during discovery or plan generation. The recommended local
dependency is `psycopg[binary]` from `requirements-v4-runtime.txt`, installed
manually into the F-drive project environment. Codex does not install it in a
global Python environment.

Connection values are read only from the current process environment:

| Setting | Environment variable |
|---|---|
| host | `JCFB_V4_RUNTIME_DB_HOST` |
| port | `JCFB_V4_RUNTIME_DB_PORT` |
| database | `JCFB_V4_RUNTIME_DB_NAME` or legacy local alias `JCFB_V4_RUNTIME_DB` |
| user | `JCFB_V4_RUNTIME_DB_USER` or local owner alias `JCFB_V4_RUNTIME_OWNER` |
| password | `JCFB_V4_RUNTIME_DB_PASSWORD` or local password alias `JCFB_V4_RUNTIME_PASSWORD` |
| TLS mode | `JCFB_V4_RUNTIME_DB_SSLMODE` |

Reports contain only host, port, database, user, TLS mode, and the credential
variable name. Passwords and connection URLs are never serialized, printed,
or placed in a target descriptor.

## Apply transaction and history

The candidate SQL files retain one `BEGIN;` and one `COMMIT;` marker for static
validation. The executor strips only those wrapper lines and runs the SQL body
and its `governance.schema_migrations` history insert in one database
transaction. A migration is committed only after its immutable history row is
inserted. On failure it rolls back, then records a separate `BLOCKED` failure
row when the history table is available; it never edits or deletes a prior
history row. Each record contains migration identity/hash, start/end time,
status, and a redacted error type/code. The password and connection string are
not part of the record.

Before applying, preflight proves PostgreSQL 16 compatibility, target identity,
extension availability, V3.3.3 isolation, history shape, candidate hashes,
credential-variable identity, and the non-production allow-list. A partial or
unattributable history prefix blocks the run.

The executor has two deliberately separate preflight layers. Local hash,
manifest, target, and Production-boundary checks are recorded as static
preflight and must pass before `connect()` is called. The read-only PostgreSQL
catalog preflight runs only after an explicitly allow-listed connection exists
and must pass before any candidate DDL is sent.

## Modes

- `PLAN_ONLY` is the default. It loads and verifies local files and never
  constructs a connection.
- `DRY_RUN` emits the same no-write boundary with dry-run status.
- `APPLY` requires an explicit allow-listed target descriptor and is the only
  mode that may connect.
- `PRODUCTION_APPLY` is intentionally hard-blocked.

The executor never starts Docker, never discovers a Docker socket, and never
contacts Supabase from the Codex implementation environment.

## Failure taxonomy

Runtime reports retain only redacted error metadata. The connector invocation
boundary is recorded before `connect()` is called, so a refused or timed-out
socket is reported as an invoked connector failure rather than as
`CONNECTOR_NOT_INVOKED`. The supported apply failure codes are:

| Code | Meaning |
|---|---|
| `CONNECTOR_NOT_INVOKED` | A pre-connector gate stopped the run. |
| `RUNTIME_CONNECTION_CONFIG_INVALID` | A required host, port, database, user, password, or TLS setting is missing or invalid. |
| `CONNECTION_REFUSED` | The connector was called but the local endpoint was refused or unreachable, including a timeout. |
| `AUTH_FAILED` | The connector was called and PostgreSQL rejected authentication. |
| `DRIVER_MISSING` | No supported PostgreSQL driver is available in the project environment. |
| `TARGET_IDENTITY_MISMATCH` | Connected database identity differs from the explicit target descriptor. |
| `SQL_APPLY_FAILED` | Candidate SQL or its immutable history write failed. |

Passwords, URLs, and driver exception text are never serialized. The
disposable PowerShell readiness helper separately blocks a healthy container
unless both actual `NetworkSettings.Ports` and `docker port` report
`127.0.0.1:55432 -> 5432`; any missing, empty, wildcard, or other host
binding is blocked.

## Runtime case adapter

`tools/migration_harness/runtime_tests.py` discovers exactly 20 smoke bindings
from `v4_smoke_test_catalog.json` and exactly 15 database-enforcement bindings
(`NEG-08` through `NEG-22`) from `v4_negative_case_registry.json`. Each binding
preserves its source reference, expected result, caller-role contract, and a
stable hook name. The PostgreSQL adapter accepts a connection-level
`run_v4_runtime_case(binding)` hook; an absent hook is reported as pending,
never as a pass. This keeps case wiring auditable without claiming that a
database test ran in Codex.

## Reports and gate

Explicit local execution may write only redacted reports below
`.runtime/reports/prebatch04/`. A pending or failed runtime case blocks the
acceptance report. This executor does not change V4 task checkboxes, does not
approve BATCH-04, and does not perform Production or Supabase writes.
