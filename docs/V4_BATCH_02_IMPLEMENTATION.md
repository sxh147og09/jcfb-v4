# JCFB V4 BATCH-02 Implementation 1.0

Status: `V4-013 PASS` / `V4-014 PASS` / `V4-015 PASS` with database runtime evidence explicitly pending

Batch: `BATCH-02｜Dry-Run, Preflight & Negative Test Harness`

Task IDs: `V4-013`, `V4-014`, `V4-015`

## 1. Scope and boundary

This document records the BATCH-02 implementation boundary. It does not
authorize a migration apply, a Supabase write, a Production or Shadow model
run, a prediction, Promotion, or a V3.3.3 operation.

The implementation is repository-local and standard-library-only. It has no
database driver, connector discovery, installation path, automatic service
start, SQL executor, or apply method. A database connection is not attempted
unless a future task supplies an explicitly proven disposable target and a
separate approved runtime adapter.

## 2. V4-013 — Migration Dry-Run Harness Implementation

`tools/migration_harness/manifest.py` reads the authoritative Markdown
manifest and the numbered SQL files as text metadata. It verifies:

- exactly `0001` through `0009`, with unique sequence, file, ID, version, and name;
- exact `migration@20260901.NNN` identity grammar and predecessor dependency;
- missing parent, forward reference, duplicate node, and cycle rejection;
- Markdown-to-SQL header identity and `DESIGN ONLY - DO NOT APPLY` safety markers;
- transaction-boundary metadata of one transaction per ordinary migration;
- preservation of `DRAFT` and `PENDING_CANONICAL_HASH` as non-apply design state.

`tools/migration_harness/runner.py` emits a deterministic plan hash and
supports the governed status vocabulary:

`PLANNED`, `PRECHECK_BLOCKED`, `READY_FOR_DISPOSABLE`, `APPLYING`,
`VALIDATING`, `ACCEPTED`, `FAILED`, and `PARTIAL_FAIL`.

The default mode is `PLAN_ONLY`. `DRY_RUN` without an explicit target is
`PRECHECK_BLOCKED`; `APPLY` and `PRODUCTION_APPLY` are always blocked in this
batch. The emitted boundary proves `connector_invoked=false`,
`database_connected=false`, `sql_executed=false`, `ddl_applied=false`, and
`production_db_writes_performed=NO`.

## 3. V4-014 — Preflight and schema diff

`tools/migration_harness/preflight.py` implements PF-01 through PF-18 in the
order defined by `docs/V4_MIGRATION_PREFLIGHT.md`. Static manifest and
repository checks run locally. Target, catalog, role, extension, privilege,
history, backup, Data API, function-security, and release-state checks require
read-only disposable-target evidence; absent evidence is
`NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` or `BLOCKED`, never PASS.

`tools/migration_harness/schema_diff.py` compares a supplied read-only catalog
with `config/migration_harness/v4_schema_snapshot_contract.json`. It emits
only the contract classifications `MISSING`, `EXTRA`, `TYPE_MISMATCH`,
`CONSTRAINT_MISMATCH`, and `SECURITY_MISMATCH`. An absent catalog is
`NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` with an `UNKNOWN_CATALOG` evidence item;
the comparator never repairs or drops objects.

The nine checked-in migration hashes remain pending by design, so PF-13 is
`BLOCKED` for apply readiness. This is expected evidence for the current
design-only migration line, not a fabricated hash or runtime pass.

## 4. V4-015 — Smoke, RLS, trigger, and negative tests

The existing 20-case smoke catalog remains the source projection of
`docs/V4_MIGRATION_SMOKE_TESTS.md`. Its shape is validated locally, while all
20 PostgreSQL/RLS/trigger/view cases are reported as
`NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` until a proven disposable target exists.

`config/migration_harness/v4_negative_case_registry.json` defines all 22
required refusal paths. `tools/migration_harness/negative.py` executes pure
unit-level refusal contracts for every case. Cases that ultimately require
database constraint, RLS, trigger, or view enforcement additionally retain
`RUNTIME_NEGATIVE_TEST_PENDING`; unit contract PASS is not reported as a
database runtime PASS.

The negative registry covers missing/duplicate sequence, dependency and hash
integrity, target and secret boundaries, official-market payload semantics,
post-kickoff execution, Frozen Input/Prediction immutability, review lineage,
Tier A hash/role integrity, public projection isolation, Production
uniqueness, SECURITY DEFINER safety, public internal writes, business-time
latest semantics, and UNKNOWN coercion.

## 5. Evidence semantics

The BATCH-02 report distinguishes:

- `PASS`: the stated local contract or static check actually ran and passed;
- `FAIL`: the stated local check actually ran and behaved incorrectly;
- `BLOCKED`: a required safety condition rejects the request;
- `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB`: no real target evidence was supplied;
- `RUNTIME_NEGATIVE_TEST_PENDING`: the unit refusal contract ran, but database enforcement remains unverified;
- `NOT_APPLICABLE`: the check is outside the requested role or path.

No result in this batch claims PostgreSQL, Supabase, RLS, triggers, views,
advisor output, migration apply, Production, Shadow, Experiment, or model
runtime execution.

