# JCFB V4-012 Migration Dry-Run & Validation Harness Design 1.0

Status: `V4-012 COMPLETE` / `DESIGN-ONLY; NO HARNESS RUN`

Task: `V4-012`

Contract identity: `v4-migration-dry-run-harness@1.0.0`

Design revision: `r001`

This is the V4-012 engineering artifact. It defines the future isolated
migration runner, disposable-target boundary, validation interfaces, smoke
catalog, schema diff, failure state machine, and structured evidence report.
It does not implement a database connector, execute SQL, create a database,
contact Supabase, or apply a migration. Those implementation operations begin
in BATCH-02 and remain separately gated.

## 1. Authority and scope

The authority order is Constitution, versioning and identity contracts, V4
data/runtime/schema contracts, the V4-011 migration design documents, and
then this V4-012 design. The task-definition authority is
`docs/V4_TASK_REGISTRY_001_100.md`. The migration source authority is
`database/migrations/v4/0000_manifest.md` plus the nine numbered SQL files.
The schema expected-object authority is
`database/schema/v4_schema_blueprint.sql` and the V4-010 catalogs.

V4-012 delivers:

- this design and target-isolation contract;
- `config/migration_harness/v4_harness_policy.json`;
- `config/migration_harness/v4_target_descriptor.schema.json`;
- `config/migration_harness/v4_manifest_contract.schema.json`;
- `config/migration_harness/v4_manifest_loader_fixture.json`;
- `config/migration_harness/v4_smoke_test_catalog.json`;
- `config/migration_harness/v4_schema_snapshot_contract.json`;
- `config/migration_harness/v4_acceptance_report.schema.json`;
- `scripts/validate_v4_migration_harness_design.ps1`, a local static design
  validator that never opens a database connection or executes SQL.

The loader fixture is explicitly non-authoritative. It is a static projection
for validating the future loader contract; future code must parse the Markdown
manifest and SQL header metadata rather than using the fixture as a second
source of truth.

## 2. Execution modes and fail-closed boundary

| Mode | Target required | Intended environment | V4-012 status | Connector | DDL apply |
|---|---:|---|---|---|---|
| `PLAN_ONLY` | no | repository-only | allowed for static planning | never invoked | blocked |
| `DRY_RUN` | yes | `DISPOSABLE_LOCAL` or `STAGING` | interface only | future adapter | blocked in V4-012 |
| `APPLY` | yes | none in this task | blocked | never invoked | blocked |
| `PRODUCTION_APPLY` | yes | `PRODUCTION` | hard-blocked | blocked null adapter | blocked |

There is no implicit database mode. A future invocation must provide an
explicit execution mode, target descriptor, environment, provider allowlist,
and connection permission before an adapter can be considered. The default
state is `BLOCKED_UNTIL_EXPLICIT_REQUEST`.

These conditions stop before connector construction and emit only a redacted
report:

- missing or ambiguous target or environment;
- environment `PRODUCTION`, provider outside the allowlist, or unknown target;
- missing disposal, identity, isolation, or credential-reference evidence;
- `APPLY` or `PRODUCTION_APPLY` mode;
- missing or mismatched migration metadata, pending apply hash, dirty history,
  or schema drift;
- any V3.3.3 object/path/data overlap or any preflight/apply/validation failure.

No `IF NOT EXISTS`, retry, automatic repair, rollback shortcut, or default
target may convert one of these conditions into a pass.

## 3. Target descriptor and adapter boundary

The future adapter accepts only the validated descriptor described by
`config/migration_harness/v4_target_descriptor.schema.json`. It contains an
opaque `target_id`, environment, provider, non-secret database identity,
disposal/isolation assertions, a credential environment-variable name, and
explicit connection permission. It never contains a URL, password, token,
service key, cookie, or raw secret.

Future adapter types are `LOCAL_POSTGRES`, `DOCKER_POSTGRES`,
`STAGING_POSTGRES`, and `STAGING_SUPABASE`. Every adapter must:

1. refuse to install software, start an unknown database, discover a target,
   or infer an environment;
2. refuse `PRODUCTION`, `PRODUCTION_SUPABASE`, retained Production data, or
   any descriptor that claims V3.3.3 objects;
3. accept only an environment-variable name and never return or log its value;
4. expose catalog/transaction operations only after preflight; V4-012 invokes
   neither; and
5. reset or destroy a disposable target only under an explicit operator-owned
   lifecycle contract after evidence capture.

`PRODUCTION` is represented by a blocked null adapter. A staging Supabase
adapter is a future boundary, not evidence that Supabase was contacted here.

## 4. Manifest loader interface

The future loader is text-only and deterministic. It reads, in order:

```text
database/migrations/v4/0000_manifest.md
database/migrations/v4/0001_prerequisites.sql
database/migrations/v4/0002_registries_core.sql
database/migrations/v4/0003_market_context.sql
database/migrations/v4/0004_frozen_runtime.sql
database/migrations/v4/0005_evaluation.sql
database/migrations/v4/0006_governance_audit.sql
database/migrations/v4/0007_security_rls.sql
database/migrations/v4/0008_views_projections.sql
database/migrations/v4/0009_seed_and_smoke.sql
```

For each entry it parses and cross-checks:

```text
sequence, file, migration_id, migration_version, name, depends_on,
schema_contract_version, authored_at, migration_hash, status
```

The parsed output conforms to
`config/migration_harness/v4_manifest_contract.schema.json`. The loader must:

- require exactly `0001` through `0009` with unique files, IDs, versions,
  names, and sequence numbers;
- require the exact `migration@20260901.NNN` grammar and exact predecessor
  dependency for `0002` through `0009`, with no dependency for `0001`;
- reject missing parents, duplicate nodes, forward references, and cycles;
- preserve `DRAFT` and `PENDING_CANONICAL_HASH` as design state;
- compare the Markdown row to each SQL header before planning;
- never execute or parse SQL as a command; and
- never turn a pending hash into an approved or applied hash.

The dependency order is strictly serial:

```text
0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 -> 0007 -> 0008 -> 0009
```

A mismatch is `BLOCKED` and requires a new forward identity or reviewed
design correction; it is never fixed by rewriting an applied history row.

## 5. Preflight validator interface

The future preflight adapter implements PF-01 through PF-18 from
`docs/V4_MIGRATION_PREFLIGHT.md`. Each check returns an attributed result,
evidence reference, and redacted reason. `NOT_RUN` is not a pass; a critical
failure stops the chain before the next migration.

| ID | Check | V4-012 boundary | Future evidence |
|---|---|---|---|
| PF-01 | target project identity | interface only | named project/environment/ref, no secret |
| PF-02 | PostgreSQL version | interface only | server version and provider |
| PF-03 | required extensions | interface only | owner/version and approved provider |
| PF-04 | security-invoker support | interface only | capability or approved fallback |
| PF-05 | conflicting schemas/tables | interface only | catalog diff for V4 namespaces |
| PF-06 | V3.3.3 isolation | interface only | read-only before/after proof |
| PF-07 | V4 namespace state | interface only | empty/new or approved coexistence |
| PF-08 | roles and permissions | interface only | attributable actor and grants |
| PF-09 | migration history | interface only | exact immutable history comparison |
| PF-10 | backup/snapshot decision | interface only | backup evidence or disposable decision |
| PF-11 | maintenance window | interface only | owner, lock budget, timeout, rollback owner |
| PF-12 | current migration cleanliness | interface only | no partial/manual/failed state |
| PF-13 | manifest/hash readiness | static shape checked; apply blocked by pending hash | exact files and canonical hashes |
| PF-14 | runtime secrets | repository scan only | env-only presence, never secret value |
| PF-15 | Data API exposure | interface only | explicit public exposure and safe views |
| PF-16 | default privileges | interface only | `PUBLIC`, `anon`, `authenticated` grants |
| PF-17 | function security/search path | interface only | owner, fixed search path, execute grants |
| PF-18 | Production release state | interface only | no unintended active pointer replacement |

The report is compatible with the existing preflight output contract:
`target_project_identity`, `target_environment`, `database_version`,
`extension_report`, `namespace_report`, `v333_isolation_report`,
`migration_history_report`, `backup_decision`, `maintenance_window`,
`manifest_hash_report`, `secret_scan_report`, `actor_identity`,
`started_at`, `completed_at`, and `overall_status`.

## 6. Runner and failure interface

The future runner is an adapter boundary, not a shell command:

```text
load_manifest(request) -> ParsedManifest
validate_request(request, policy) -> RequestDecision
validate_preflight(target, manifest) -> PreflightReport
plan(manifest, target_identity?) -> MigrationPlan
run_dry_run(manifest, target, preflight) -> MigrationRunReport
capture_catalog(target) -> ActualCatalog
compare_snapshot(expected, actual) -> SchemaDiffReport
run_validation_suite(target, manifest) -> ValidationReport
build_acceptance_report(all_evidence) -> AcceptanceReport
```

`apply(manifest, target)` is not a V4-012 operation. No default command may
expose it or silently map `DRY_RUN` to apply.

```text
REQUESTED -> MANIFEST_VALIDATED -> PREFLIGHT_PASS -> APPLYING
         -> APPLIED -> VALIDATING -> ACCEPTED
```

| Outcome | Meaning | Required behavior |
|---|---|---|
| `PRECHECK_FAIL` | request, target, manifest, or preflight failed | do not connect or start |
| `APPLY_FAIL` | a migration transaction failed | stop at sequence; preserve evidence |
| `PARTIAL_FAIL` | external/non-transactional action left partial state | stop; append evidence; use new forward identity |
| `VALIDATION_FAIL` | catalog, smoke, security, or gate failed | do not accept or continue |
| `ACCEPTED` | every required gate passed in isolated target | record evidence; never imply Production approval |

The runner records stopped sequence, attempt identity, failure code, redacted
reason, evidence hashes, and history-write status. It never reports
`ACCEPTED` after a failure and never continues after a failed sequence.

## 7. Validation harness contract

V4-012 defines future-runtime validation; it does not claim PostgreSQL,
Supabase, RLS, triggers, views, advisor, or smoke tests passed. Every runtime
result binds migration identity, schema contract, target ID, caller role, test
transaction ID, expected result, actual result, and evidence hash.

| Group | Required checks | V4-012 runtime status |
|---|---|---|
| schema/catalog | schemas, tables, columns, types, PK/FK, indexes, functions, triggers, policies, RLS, grants | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| constraints | FK, unique, check, same-match, revision, identity | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| append-only/frozen | append-only, Frozen Input, Frozen Prediction, no-op update | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| no-future leakage | cutoff/kickoff, availability, run/freeze, result/event exclusion, hashes | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| role isolation | `PRODUCTION`, `SHADOW`, `EXPERIMENT`, public, Tier A | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| Tier A pairing | same match, same `frozen_input_hash`, distinct roles, pre-kickoff, no Experiment | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| RLS/permission | `anon`, `authenticated`, backend/service, executor, auditor | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| SECURITY DEFINER | fixed `search_path`, owner, actor check, restricted `EXECUTE` | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| security-invoker views | `security_invoker=true` or approved fallback, safe grants/columns | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| canonical latest update | `canonical_latest_update_at` is the max real Prediction/Frozen/Odds/Context/Result/Review time, not build time | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| advisor review | critical finding blocks; INFO/approved exceptions attributed | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |

The suite is fail-closed: a missing catalog, unknown caller result, unresolved
hash, or unverified security property is not a pass. The 20-case catalog is
the non-authoritative machine-readable projection of
`docs/V4_MIGRATION_SMOKE_TESTS.md`; no case is claimed executed here.

## 8. Schema snapshot and diff contract

`config/migration_harness/v4_schema_snapshot_contract.json` records the
expected catalog derived from the blueprint: seven schemas, 36 tables, 64
indexes, 18 functions, six views, 45 triggers, one policy, and 30
RLS-enabled tables. The static validator checks the names against the SQL.

The future actual catalog is read-only data from `pg_catalog` and
`information_schema` on the named isolated target. Each comparison result
uses exactly one classification:

- `MISSING` — expected object or property is absent;
- `EXTRA` — unapproved object or property exists;
- `TYPE_MISMATCH` — object or column type differs;
- `CONSTRAINT_MISMATCH` — PK, FK, unique, check, index, or revision differs;
- `SECURITY_MISMATCH` — RLS, policy, grant, function, trigger, view security,
  or exposure differs.

An empty diff is `PASS`; a non-empty or unavailable diff is `BLOCKED`. The
contract never auto-drops, rewrites, disables, or repairs an object. Drift
requires attributed review and a new forward migration/design identity.

## 9. Structured acceptance report

The machine-readable report contract is
`config/migration_harness/v4_acceptance_report.schema.json`; JSON is the
primary record and Markdown is the human-readable projection. It includes:

- exact Batch ID and Task IDs from the registry;
- target identity/environment without credential values;
- manifest sequence, dependency, hash, and status evidence;
- PF-01 through PF-18, migration sequence, apply status, stop sequence, and
  transaction evidence;
- schema/catalog, constraint, RLS/security, trigger/view, no-future, role,
  Tier A, advisor, smoke, and schema-diff results;
- failures, blocking reasons, Secret Scan, Self Audit, Cross-Doc Consistency,
  and Git traceability; and
- explicit Production/Supabase/V3.3.3 write or mutation fields.

A design-only V4-012 report must declare:

```text
design_only = true
sql_executed = false
database_connected = false
production_db_writes_performed = NO
supabase_writes_performed = NO
v333_mutated = NO
requires_disposable_db_later = true
```

## 10. Secrets, history, and V3.3.3 isolation

Only environment-variable names may appear in a target descriptor. Secret
values remain in runtime secret storage and are excluded from repository files,
logs, JSON, Markdown reports, hashes, fixtures, and command arguments.
`.env.example` remains placeholder-only.

The design validator and future harness operate only on declared V4 manifest,
schema, and harness-contract paths. They do not scan, import, copy, rename,
compare, or mutate V3.3.3 artifacts. Any V3.3.3 overlap returns `BLOCKED`.
There is no automatic cleanup or repair of the conflict.

Migration history verification is append-only against
`governance.schema_migrations`. A failed/partial record is retained; an
applied row is never updated or deleted. Remediation uses a new migration ID
and higher sequence. `PENDING_CANONICAL_HASH` cannot be applied.

## 11. V4-012 acceptance boundary

Static acceptance requires: BATCH-01 contains only V4-012; this design covers
target, manifest, preflight, runner, validation, smoke, schema diff, failure,
report, secret, history, and isolation interfaces; the JSON contracts parse
and cross-check against the manifest, smoke design, and schema blueprint; the
existing V4-011/data/versioning validators remain passing; Secret Scan and
`git diff --check` pass; and no database connection, SQL execution, migration
apply, Supabase write, model/runtime run, Shadow/Experiment run, Production
operation, or V3.3.3 mutation occurs.

Target-dependent preflight, migration execution, catalog capture, RLS,
trigger, view, advisor, and 20-case smoke evidence remain
`NOT_EXECUTED_REQUIRES_DISPOSABLE_DB`. They are future validation evidence,
not missing V4-012 design deliverables.

Next execution boundary: `BATCH-02` (`V4-013` through `V4-015`).
