# JCFB V4 Migration Manifest 1.0

Status: V4-011 DESIGN-ONLY / ALL ENTRIES DRAFT

## 1. Manifest boundary

This manifest reserves the V4-011 migration identities and records the review order. It is not an apply plan and does not authorize a database write. All candidate SQL is non-executable design material. The canonical SQL hashes are intentionally not calculated in this task.

Canonical hash status for every entry: `PENDING_CANONICAL_HASH`.

Schema contract: `v4-database-schema@1.0.0`.

Migration grammar: `migration@20260901.NNN`.

## 2. Migration inventory

| Sequence | File | migration_id / migration_version | Name | Depends on | Expected objects | Status |
|---:|---|---|---|---|---|---|
| 0001 | `0001_prerequisites.sql` | `migration@20260901.001` | `v4-prerequisites` | none | approved extension candidate, seven schemas, hash helper, migration/schema registries | DRAFT |
| 0002 | `0002_registries_core.sql` | `migration@20260901.002` | `v4-registries-core` | 0001 | model/engine versions, competitions, teams, aliases, matches | DRAFT |
| 0003 | `0003_market_context.sql` | `migration@20260901.003` | `v4-market-context` | 0002 | official/external markets, context, evidence, bundles and joins | DRAFT |
| 0004 | `0004_frozen_runtime.sql` | `migration@20260901.004` | `v4-frozen-runtime` | 0003 | Frozen Inputs, selections, features, runs, predictions, freezes | DRAFT |
| 0005 | `0005_evaluation.sql` | `migration@20260901.005` | `v4-evaluation` | 0004 | results, reviews, Tier A, promotion, calibration | DRAFT |
| 0006 | `0006_governance_audit.sql` | `migration@20260901.006` | `v4-governance-audit` | 0005 | release events, incidents, audit log, active indexes | DRAFT |
| 0007 | `0007_security_rls.sql` | `migration@20260901.007` | `v4-security-rls` | 0006 | validators, triggers, RLS, revokes, controlled grants | DRAFT |
| 0008 | `0008_views_projections.sql` | `migration@20260901.008` | `v4-views-projections` | 0007 | projection ledger and six read views | DRAFT |
| 0009 | `0009_seed_and_smoke.sql` | `migration@20260901.009` | `v4-seed-smoke` | 0008 | static registry seed, smoke manifest, acceptance snapshot | DRAFT |

## 3. Approval conditions

Each entry may move to `APPROVED_FOR_DEPLOYMENT` only when:

1. the target identity and PostgreSQL/Supabase compatibility preflight pass;
2. all `TODO_DECISION` items are resolved and recorded;
3. canonical SQL bytes and immutable metadata are frozen and hashed;
4. the dependency graph is acyclic and the preceding migration is accepted;
5. constraints, triggers, RLS, grants, views, and smoke tests have an approved test plan;
6. the V3.3.3 boundary, Secret Scan, and advisor review pass;
7. a Human Approver authorizes the named deployment target.

No entry may be marked `APPLIED` from repository state alone. `schema_migrations` must contain a matching immutable execution record and the acceptance gate must be complete.

## 4. Transaction/parallelism note

0001–0009 are designed for serial application. Ordinary DDL is one transaction per migration. Non-transactional index/view optimizations, if ever approved, receive separate identities. No parallel execution is authorized by this manifest.

## 5. Current execution declaration

Database writes performed: **NO**.
