# JCFB V4 Schema Version Registry 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY)

## 1. Purpose and separation

Schema shape, migration identity, application history, and model identity are separate layers. `schema_version` describes a record/interface shape. `migration_version` describes an ordered storage transition. `migration_id` identifies one immutable migration file. A model, engine, dataset, or Git commit cannot substitute for any of them.

The future design uses two append-only control records:

1. `governance.v4_schema_registry` — the immutable manifest/approval registry for migration definitions and schema-contract metadata.
2. `governance.schema_migrations` — the terminal execution history for each migration attempt, including success/failure and actor evidence.

Neither table is a shortcut to alter an applied migration. An applied migration row is never edited to change its hash, status, actor, timestamp, or success value.

## 2. `v4_schema_registry` logical fields

| Field | Required | Meaning |
|---|---|---|
| `registry_record_id` | yes | Stable UUID row identity |
| `migration_id` | yes | Canonical `migration@YYYYMMDD.NNN`; never reused |
| `sequence` | yes | Four-digit dependency order; unique for the V4 line |
| `name` | yes | Immutable lower-kebab name |
| `migration_version` | yes | Ordered storage identity |
| `depends_on` | yes | Ordered array of exact migration IDs; empty only for 0001 |
| `schema_contract_version` | yes | `v4-database-schema@1.0.0` in this design |
| `authored_at` | yes | Design metadata, not deployment time |
| `migration_hash` | yes | Actual canonical hash or `PENDING_CANONICAL_HASH` while DRAFT |
| `status` | yes | `DRAFT`, `APPROVED_FOR_DEPLOYMENT`, `APPLIED`, `FAILED`, `SUPERSEDED` |
| `app_version` | conditional | Minimum/compatible application identity |
| `applied_at` | conditional | Set only on a separate recorded applied state/record |
| `applied_by` | conditional | Attributable executor identity, never a secret |
| `success` | yes | False until a fully accepted application is recorded |
| `notes` | yes | Non-authoritative review/deployment notes |
| `prev_migration_hash` | conditional | Previous successful migration hash in the declared chain |
| `chain_hash` | conditional | Optional chained digest over predecessor and current canonical identity |

The manifest rows in 0009 are static registry metadata only. In this repository they remain `DRAFT` and use `PENDING_CANONICAL_HASH`; that is not a deployment result.

## 3. `schema_migrations` execution fields

The future history table contains at least:

```text
migration_id
sequence
name
migration_version
schema_contract_version
migration_hash
applied_at
applied_by
app_version
success
status
notes
prev_migration_hash
chain_hash
```

There is one terminal history record per migration identity. A failed/partial attempt is not overwritten by a later success. Remediation receives a new migration identity and a higher sequence. The history table is `INSERT`-only for the executor and is protected against `UPDATE`/`DELETE` by an append-only guard after the bootstrap table is created.

`success=true` requires `status=APPLIED`, a real canonical hash, an attributable actor, and an acceptance report whose required gates all pass. `success=false` is retained for `FAILED`, `BLOCKED`, or `SUPERSEDED` outcomes. `PENDING_CANONICAL_HASH` is never valid in an applied history row.

## 4. Hash chain design

The required canonical digest is computed from canonical SQL bytes plus immutable metadata, including `authored_at` and the exact file path. A future optional chain digest may be computed from:

```text
canonical(prev_migration_hash, migration_id, sequence,
          migration_version, migration_hash, schema_contract_version)
```

`prev_migration_hash` is null only for 0001 or an explicitly documented chain root. The chain is evidence, not permission to change a predecessor. A chain mismatch is `BLOCKED` and requires a new remediation path.

Deployment timestamps, executor hostnames, runtime duration, and mutable status are excluded from the canonical migration hash. They remain in the history record for audit.

## 5. Registry insert and update rules

- The manifest can be seeded only with explicit static migration metadata; it cannot insert teams, matches, odds, predictions, results, or model outputs.
- `schema_migrations` rows are written by the controlled deployment executor after each accepted migration, not by an arbitrary SQL file.
- `v4_schema_registry` and `schema_migrations` are append-only evidence. A correction is a new registry/history record or a new migration, never an update to an applied row.
- Sequence and migration IDs are unique across the V4 migration line and cannot be reused after approval, failure, or supersession.
- `applied_by` identifies a role/account, not a credential. Secrets remain only in runtime secret storage.

## 6. Registry validation

The future registry check must prove:

- all 0001–0009 IDs, sequence numbers, names, dependencies, and filenames are unique and match the manifest;
- the dependency graph has no cycle and every parent is present;
- hashes are either actual `sha256:` values after canonicalization or explicitly pending only while DRAFT;
- app/schema/migration compatibility is declared;
- `success`, `status`, `applied_at`, and `applied_by` are mutually consistent;
- predecessor and chain hashes do not point to a future or changed row;
- no registry/history row references V3.3.3 or secrets.

## 7. Current status

Registry design: **PASS**. Real database registry state: **NOT RUN**. No applied row exists or was modified by V4-011.
