# JCFB V4-011 Database Migration Design 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY; NO DATABASE EXECUTION)

## 1. Scope and hard boundary

This document defines the migration architecture, dependency graph, deployment gates, transaction boundaries, version registry, smoke-test design, and roll-forward policy for JCFB V4. It is a review artifact. It does not connect to Supabase, execute SQL, create a table, seed a match, run a model, run Shadow or Experiment, publish Production, tune parameters, or modify JCFB V3.3.3.

Every SQL file under `database/migrations/v4/` begins with `DESIGN ONLY - DO NOT APPLY`. The files are candidate DDL shapes for a later, separately approved deployment. A file containing executable-looking SQL is not authorization to run it.

The authority order is:

1. `docs/V4_CONSTITUTION.md`.
2. The affected V4-008 contract and `docs/V4_CANONICAL_DATA_MODEL.md`.
3. `docs/V4_VERSIONING_STANDARD.md`, the identity contract, runtime boundary, and governance policies.
4. `docs/V4_DATABASE_SCHEMA_BLUEPRINT.md` and its V4-010 catalogs.
5. This V4-011 design and the candidate migration files.

If a migration convenience conflicts with a higher rule, the migration is `BLOCKED` until the conflict is resolved through an auditable governance decision.

## 2. Migration identity standard

The nine design files use the canonical V4 migration grammar `migration@YYYYMMDD.NNN`:

| Field | Rule | V4-011 value pattern |
|---|---|---|
| `migration_id` | Immutable canonical migration identity; never reused | `migration@20260901.001` through `.009` |
| `sequence` | Four-digit dependency order; unique in this design | `0001` through `0009` |
| `name` | Stable lower-kebab migration name | `v4-prerequisites`, `v4-registries-core`, etc. |
| `migration_version` | Ordered storage identity; distinct field even when equal to `migration_id` | `migration@20260901.001` through `.009` |
| `depends_on` | Exact predecessor migration IDs; empty only for 0001 | See dependency graph |
| `schema_contract_version` | Version of the physical V4 schema contract | `v4-database-schema@1.0.0` |
| `authored_at` | Design authoring timestamp; not an apply timestamp | `2026-09-01T00:00:00+08:00` |
| `migration_hash` | Canonical SQL plus immutable metadata digest | `PENDING_CANONICAL_HASH` until canonicalization |
| `status` | Governed lifecycle state | `DRAFT` in this repository |

Allowed lifecycle values are `DRAFT`, `APPROVED_FOR_DEPLOYMENT`, `APPLIED`, `FAILED`, and `SUPERSEDED`. `APPLIED` is never inferred from a file being present. It requires every acceptance gate and a recorded history row. A migration that has entered Production is immutable forever. A correction receives a new migration identity and number; the original file and history row are not edited.

The filename number is permanently reserved as soon as that migration is approved for deployment. A failed or superseded migration number is not recycled.

## 3. Hash and canonicalization decision

The hash input is:

```text
UTF-8 bytes of canonical SQL with LF line endings
+ canonical immutable metadata:
   migration_id, sequence, name, migration_version,
   depends_on, schema_contract_version, authored_at, file path
```

The canonicalizer uses the V4 JSON profile and SHA-256, serialized as `sha256:<64 lowercase hexadecimal characters>`. `authored_at` is immutable design metadata and is included; volatile deployment fields are excluded from this digest: `applied_at`, `applied_by`, execution duration, deployment host, and mutable lifecycle/status fields. No hash is fabricated in V4-011. Until canonical bytes are frozen and independently recomputed, the value remains `PENDING_CANONICAL_HASH` and the migration cannot be `APPROVED_FOR_DEPLOYMENT` or `APPLIED`.

The hash algorithm registry is a separate decision from the migration history. The only approved candidate in this design is `SHA-256` with profile `v4-canonical-json@1.0`; extension or database functions are not allowed to invent a digest.

## 4. Ordered migration plan

| Sequence | File | Dependency | Design purpose | Primary objects | Transaction shape |
|---:|---|---|---|---|---|
| 0001 | `0001_prerequisites.sql` | none | Validateable prerequisites, namespaces, hash helper, migration registries | seven schemas, `governance.schema_migrations`, `governance.v4_schema_registry`, hash registry | one transaction if the target supports the approved extension operation |
| 0002 | `0002_registries_core.sql` | 0001 | Version registries and canonical identities | model/engine versions, competitions, teams, aliases, matches | one transaction |
| 0003 | `0003_market_context.sql` | 0002 | Source-isolated facts and evidence | official/external snapshots, context, evidence, bundles | one transaction |
| 0004 | `0004_frozen_runtime.sql` | 0003 | Frozen lineage and runtime output structure | Frozen Inputs, features, runs, predictions, Frozen Predictions | one transaction |
| 0005 | `0005_evaluation.sql` | 0004 | Results, correction chains, review, Tier A, promotion evidence | evaluation tables and memberships | one transaction |
| 0006 | `0006_governance_audit.sql` | 0005 | Release pointers, incidents, append-only audit chain | release events, incidents, audit log, active-pointer indexes | one transaction |
| 0007 | `0007_security_rls.sql` | 0006 | RLS, grants, fail-closed functions, trigger installation | security functions, RLS and internal grants; public trigger attachment deferred | one transaction |
| 0008 | `0008_views_projections.sql` | 0007 | Production-only read ledger and views | projection ledger and six allow-listed views | one transaction where view replacement is supported |
| 0009 | `0009_seed_and_smoke.sql` | 0008 | Static registry seed and acceptance snapshot shape | registry rows, smoke manifest, deployment snapshot | one transaction in an isolated acceptance database |

The files are ordered design artifacts, not an execution request. The exact edge list and parallelism decision are in `docs/V4_MIGRATION_DEPENDENCY_GRAPH.md`.

## 5. Prerequisite decisions

The following remain explicit `TODO_DECISION` items until deployment:

- Target project identity, environment, database major version, and migration owner.
- Whether `pgcrypto` is available and approved for `gen_random_uuid()`; UUIDv7 requires a separately approved provider and compatibility test.
- Whether the target PostgreSQL version supports `security_invoker=true` views. A pre-15 target must use the documented private-schema/revoked-grant fallback.
- All instants are stored as `timestamptz`; the deployment/session timezone must be explicitly approved (UTC is the candidate). `data_date` and display timezones remain explicit and are never inferred from the host.
- Whether Supabase Data API exposure is disabled for the internal projection ledger and whether only the allow-listed view surface is exposed.
- Which project-managed server role is used. `service_role` is server-side only; a least-privilege custom backend role may be preferred after review.
- Whether a backup/snapshot and maintenance window are required before first deployment.
- Whether the target has any pre-existing V4 namespaces or tables that are approved for coexistence.

No migration proceeds while a required decision is unresolved. The preflight form records `PASS`, `BLOCKED`, or `NOT_RUN` for each item.

## 6. Installation and trigger order

The future deployment order is deliberately strict:

1. Verify project, version, extension, privileges, namespace, history, backup, and secret prerequisites.
2. Apply 0001 and record its immutable history row only after the transaction succeeds.
3. Apply 0002–0006 in sequence, with direct PK/FK/unique/check validation at each boundary.
4. Apply 0007 helper functions in dependency order: hash/utility helpers, append-only guard, frozen-input guard, registry guard, source/market gates, revision/lineage gates, no-future gate, Tier A gate, review/incident/release gates, audit append contract, then trigger attachments.
5. Enable RLS before any client grant. Revoke default `PUBLIC`, `anon`, and ordinary `authenticated` access before granting allow-listed public views.
6. Apply 0008 projection ledger and views. Attach the public projection trigger after the ledger exists, and grant only the reviewed safe columns/views.
7. Apply 0009 only in an isolated validation transaction after the migration and schema registries are consistent; static registry seed cannot activate a Production release.
8. Run the smoke and advisor suites with real caller roles in a disposable/staging target. Stop on any failure.

The 0007 audit bindings cover canonical intake, registry lifecycle, freeze, runtime, result/review, Tier A, promotion, release-pointer, incident, and migration-history events. Because the public projection and acceptance snapshot tables are created later, their publication/audit bindings are attached in 0008 and 0009 only after those tables exist. No audit trigger is attached to `governance.audit_logs` itself; the controlled append function owns that insert to avoid recursion.

Deferred constraint triggers are reserved for relationships that cannot be validated until normalized child rows and parent rows exist. A deferred trigger never turns a bad record into an eligible record; it rejects it or preserves it as `BLOCKED`/`INVALID` with evidence.

## 7. Transaction boundaries and failure handling

- Each ordinary DDL migration should run as one transaction so a failure rolls back the migration's own uncommitted DDL.
- Extension operations, `CREATE INDEX CONCURRENTLY`, long-running validation, and other non-transactional operations must be declared in a separate, explicitly approved phase. None is executed or silently embedded here.
- A migration failure stops the chain. The executor must not continue to the next sequence or retry the same identity by relying on `IF NOT EXISTS`.
- A partial external operation is recorded as `FAILED`/`PARTIAL` in an append-only incident/history channel, followed by a reviewed remediation migration with a new number.
- A transaction rollback is not permission to delete or rewrite data that was already committed by an earlier migration.

## 8. Idempotency policy

`IF NOT EXISTS` is permitted only for an empty, preflight-approved namespace or extension when the existence check proves the existing object is the exact approved V4 object. It is not a recovery strategy.

Tables, constraints, indexes, policies, triggers, views, and functions must not use idempotent syntax to conceal a partial application, a definition mismatch, or a conflicting V3.3.3 object. A mismatch is `BLOCKED`. `ON CONFLICT DO NOTHING` is not used for migration history or acceptance evidence. History plus preflight, not repeatability, is the primary safety mechanism.

## 9. Role and approval boundary

| Role | Responsibility | Prohibited combination |
|---|---|---|
| Human Approver | Reviews design, preflight, risk, backup, and acceptance evidence; explicitly authorizes first deployment | Cannot be omitted for first V4 Production migration |
| Migration Executor | Runs only the approved immutable files in the approved target and records history | Cannot approve its own Production run |
| Auditor | Independently verifies history, hashes, gates, RLS, advisor results, V3 isolation, and smoke evidence | Cannot silently alter a failed record |

One automated agent must not both approve and execute a Production migration without human approval. `service_role` is a runtime database identity, not a human approval identity, and its secret never enters Git or SQL.

## 10. Compatibility audit result

The V4-010 physical blueprint, V4-009 logical model, V4-008 data contract, V4-006 versioning standard, Constitution, and `AGENTS.md` agree on:

- seven namespaces with private internal tables and a safe `public` read surface;
- typed UUID identities plus separate business keys;
- append-only corrections and immutable Frozen Input/Frozen Prediction;
- source availability and cutoff/kickoff ordering with fail-closed leakage gates;
- explicit `PRODUCTION`, `SHADOW`, and `EXPERIMENT` roles;
- same-match and same-`frozen_input_hash` Tier A pairing;
- manual promotion and one active Production revision;
- RLS/grant separation, security-invoker view protection when supported, and no secrets in repository content;
- no V3.3.3 foreign key, copy, import, rename, or mutation path.

The V4-010 candidate SQL header was normalized to the same `DESIGN ONLY - DO NOT APPLY` wording used by the V4-011 migration design files. Its physical `compatibility_level` check was also aligned to the V4-006 canonical values (`PATCH_COMPATIBLE`, `MINOR_COMPATIBLE`, `MAJOR_BREAKING`). No schema object was created by either documentation-only correction.

## 11. Future dry-run and validation strategy

The first executable rehearsal is a separate, optional staging/local PostgreSQL dry run. It must use a disposable database or isolated project with no V3.3.3 objects and no retained Production data:

1. Freeze the approved manifest, canonical SQL bytes, metadata, dependency order, and real migration hashes.
2. Apply the exact files in sequence inside the disposable target, stopping on the first transaction or catalog error.
3. Run the 20 smoke cases with real `anon`, `authenticated`, `service_role`/backend, executor, and auditor caller contexts.
4. Compare the resulting `pg_catalog` object inventory, columns, constraints, indexes, functions, triggers, RLS/policies, grants, and view options with the expected schema catalog.
5. Produce a schema-only dump/diff and archive the migration history, acceptance snapshot, smoke evidence, advisor output, and diff hashes.
6. Resolve every drift or failure with a new forward-fix design. Only after the disposable run, diff, smoke suite, advisor review, and V3.3.3 isolation evidence pass may a Human Approver authorize a named Production deployment.

This dry-run strategy is design-only in V4-011. No local, staging, Supabase, or Production database was contacted or modified here; the validation harness belongs to the next task and is not started.

## 12. Current execution declaration

Database writes performed in this task: **NO**.

No Supabase project was contacted, no SQL was run, no migration was applied, no registry row was inserted into a real database, and no V3.3.3 artifact was read for mutation or changed. V4-011 is complete only as migration architecture and deployment-gate design. The next task is `V4-012 Migration Dry-Run & Validation Harness Design 1.0`; it is not started by this document.
