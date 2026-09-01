# JCFB V4 Staging Readiness and Disposable Target Contract

Contract: `v4-batch-03-readiness-contract@1.0.0`
Task: `V4-016`
Batch: `BATCH-03`  
Status: `DESIGN_ONLY`

## Purpose

This document defines the safety envelope for a future migration-validation target. It does not create, discover, install, start, connect to, or mutate PostgreSQL, Supabase, Production, Shadow, or V3.3.3. The executable contract is [`config/migration_harness/v4_batch_03_readiness_contract.json`](../config/migration_harness/v4_batch_03_readiness_contract.json); the checked-in target is a non-secret template at [`config/migration_harness/v4_batch_03_staging_target.template.json`](../config/migration_harness/v4_batch_03_staging_target.template.json).

If the target cannot be proven disposable and non-Production, no database connection is allowed. The template therefore remains `NOT_READY` with `RUNTIME_PENDING_DISPOSABLE_DB` and `connect_permission=NOT_GRANTED`.

## Environment contract

| Environment | Allowed use in BATCH-03 | Provider boundary | Required isolation | Network rule |
|---|---|---|---|---|
| `DISPOSABLE_LOCAL` | Readiness design and later isolated dry-run | `LOCAL_POSTGRES` or `DOCKER_POSTGRES` | `non_production=true`, `disposable=true`, resettable and destroyable | Off or explicitly operator-approved local-only |
| `STAGING` | Readiness design and later staging dry-run | `STAGING_POSTGRES` or `STAGING_SUPABASE` | Named non-Production target with no retained Production/V3.3.3 state | `REQUIRE_VERIFY_FULL` whenever networked |
| `PRODUCTION` | Reference-only classification | `PRODUCTION_SUPABASE` | Not a validation target | Hard-blocked |

The readiness state machine is:

| State | Meaning in this batch |
|---|---|
| `NOT_READY` | Static contract is valid, but target/runtime proof or explicit connection permission is missing. |
| `READY_FOR_DISPOSABLE_DRY_RUN` | Disposable local identity and complete read-only evidence are present; this is not apply authorization. |
| `READY_FOR_STAGING_DRY_RUN` | Non-Production staging identity and complete read-only evidence are present; this is not apply authorization. |
| `READY_FOR_PRODUCTION_REVIEW` | Evidence can be handed to an independent human reviewer only. It never grants a Production connection or write. |
| `BLOCKED` | A safety, identity, namespace, permission, hash, or partial-state rule failed. Stop and retain evidence. |

`READY_FOR_PRODUCTION_APPLY` is explicitly prohibited in BATCH-03.

## Required target manifest fields

Every supplied manifest must contain the following non-secret evidence:

- target ID, environment, provider, `non_production`, and `disposable` assertions;
- server/database/project-or-cluster identity without a credential or connection URL;
- distinct Human Approver, Migration Executor, and Auditor placeholders or named roles;
- PostgreSQL major version, compatibility decision, and approved extension inventory including `pgcrypto`;
- network/SSL mode and certificate verification state;
- required roles (`backend`, `executor`, `auditor`) and closed default privileges;
- all seven V4 namespaces (`core`, `market`, `context`, `model`, `evaluation`, `governance`, `public`), conflict result, and explicit no-V3.3.3/no-Production-data result;
- migration-history state, exact-manifest result, dirty/partial-state result, and unresolved object list;
- backup/snapshot decision, reset-before-run, teardown/destroy-after-evidence, operator ownership, and retention policy;
- an uppercase environment-variable name only for credentials. Values must not be persisted, logged, or reported.

The validator in [`tools/migration_harness/readiness.py`](../tools/migration_harness/readiness.py) rejects raw credential fields, Production targets, namespace conflicts, V3.3.3 objects, retained Production data, partial state, missing reset/teardown rules, and ungoverned readiness states.

## Runtime gate

The checked-in template is a design fixture, not a database snapshot. Until a future operator supplies a disposable/staging read-only catalog with target identity, PostgreSQL version, extensions, roles, SSL, namespace, history, backup, partial-state, secret-presence, and Production-release evidence, runtime checks remain:

`RUNTIME_PENDING_DISPOSABLE_DB` / `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB`

Pending is never a PASS. No PostgreSQL, Docker, service, or Supabase installation is performed automatically. The package must remain unable to approve Production deployment while any runtime evidence is pending.

## Separation and boundary

The Human Approver authorizes a later named action, the Migration Executor performs only the approved action, and the Auditor independently verifies evidence. One unattended agent may not approve and execute a Production migration. BATCH-03 only prepares the package.

`NO_PRODUCTION_APPLY_IN_THIS_BATCH = TRUE`
`Production DB Writes Performed = NO`
`Supabase Writes Performed = NO`
`V3.3.3 mutation = NO`
