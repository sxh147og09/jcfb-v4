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
  -> disposable role simulation
  -> one rollback-isolated transaction per executable runtime case
  -> catalog/schema and runtime gate checks
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
(`NEG-08` through `NEG-22`) from `v4_negative_case_registry.json`. The
machine-readable execution contract in
`config/migration_harness/v4_runtime_case_execution.json` is joined to those
registries by case ID. Every binding therefore has a concrete handler, setup,
action, expected outcome, governed mechanism, and cleanup strategy.

`tools/migration_harness/runtime_case_handlers.py` executes the handlers through
ordinary PostgreSQL statements. The runner starts a transaction for each case,
uses savepoints around rejected actions, records only SQLSTATE/constraint
metadata, and rolls back the complete fixture transaction before the next case.
The result vocabulary is deliberately closed:
`PASS_EXPECTED_ACCEPT`, `PASS_EXPECTED_REJECT`, `FAIL_UNEXPECTED_ACCEPT`,
`FAIL_UNEXPECTED_REJECT`, and `BLOCKED_ENVIRONMENT`. A negative case can pass
only when SQLSTATE and the contract's stable constraint/error marker match;
an arbitrary SQL error is never accepted as evidence.

The disposable container's first-time initialization installs `pgcrypto` in
the provider-compatible `extensions` schema and adds that schema to the
database search path. It also provisions a local compatibility `service_role`
with the platform-equivalent `BYPASSRLS` capability. Candidate 0001 verifies that the role already exists with
`rolbypassrls = true` and fails closed for a missing or false capability; it
does not create or alter the provider-owned role. It also fails closed if
`anon` or `authenticated` has `rolbypassrls = true`. The runtime case adapter
may then create the minimal local-only `backend`, `executor`, and `auditor`
no-login roles and grant them membership in `service_role`. Existing `anon`
and `authenticated` roles are used as public read/write-boundary fixtures. This
is reported as `DISPOSABLE_ROLE_SIMULATION`; it is not a Supabase auth runtime.
Supabase Advisor remains `NOT_RUN_IN_DISPOSABLE`.

The local role simulation records which `backend`, `executor`, and `auditor`
roles or `service_role` memberships were absent before preparation. After the
35 cases, it revokes and drops only those runner-created objects. A failed
case rollback or role teardown quarantines the connection and blocks further
case execution; the operator-owned container/data-directory teardown remains a
separate final reset boundary.

The runtime schema audit is read-only after migration apply. It checks the
candidate tables, functions, fixed `search_path` for security-definer
functions, security-invoker views, RLS, critical triggers, constraints,
production uniqueness indexes, no-future-leakage triggers, and the canonical
latest-business-timestamp view. Runtime preflight/postflight also records the
installed pgcrypto schema, and `SMOKE-16` is promoted to an explicit
`audit_trigger_execution` gate proving the repaired audit trigger path runs.

The disposable executor has one narrowly scoped bootstrap accommodation for
the immutable 0001-0008 prefix. Frozen 0007 installs the history audit trigger
with its historical `public.digest` body, so a provider-like `extensions`
installation would otherwise fail while the executor records the 0007 and
0008 history rows, before 0009 can apply the forward fix. For `DISPOSABLE_LOCAL`
only, the executor disables only `v4_schema_history_audit_event` around each of
those two bookkeeping inserts and re-enables it before the migration
transaction commits. It does not rewrite or rerun 0001-0008, move pgcrypto,
create a `public.digest` wrapper, or bypass the trigger for 0009 or runtime
data; `SMOKE-16` remains the executable audit-trigger gate.

## Reports and gate

Explicit local execution may write only redacted reports below
`.runtime/reports/prebatch04/`. A blocked or failed runtime case blocks staging
readiness. The PowerShell wrapper now accepts `-ApplyDisposable` only when all
35 executable cases pass, the schema/security gates pass, and the report says
`READY_FOR_PRODUCTION_REVIEW`. Each write gets a unique `run_id` and is stored
under `.runtime/reports/prebatch04/runs/<run_id>/`; `latest.json` is an atomic
pointer to the newest run. At runtime start, Git resolution uses the following
portable priority: the process-only `JCFB_V4_GIT_EXE` override, `shutil.which`,
and common Windows Git installation locations. The PowerShell activation script
also discovers a current-user Codex bundled Git helper when available and sets
that override only for the current PowerShell process and its children. The
executor captures `git_head`, `git_branch`,
`working_tree_clean`, `repo_root`, `run_id`, and timestamps. A missing or
invalid Git executable raises `GIT_EXECUTABLE_NOT_FOUND` with source categories
only. A missing or invalid Git HEAD blocks evidence persistence; it is never
serialized as a valid `null` identity. The JSON and Markdown files persist the same identity,
`smoke_passed`, `enforcement_passed`, and the exact PowerShell summary lines.
The pointer includes `report_json`, `report_markdown`, `runtime_status`, and
the same Git identity (with `json`/`markdown` aliases retained for local
compatibility). The read-only `runtime-review` command verifies that the
pointer, per-run JSON, per-run Markdown, and current repository all carry the
same Git HEAD; any missing or conflicting value is blocked. Report selection
compares all valid run files so a stale pointer or legacy fixed-name report
cannot hide a newer run. This executor does not change V4 task checkboxes, does
not approve BATCH-04, and does not perform Production or Supabase writes.
