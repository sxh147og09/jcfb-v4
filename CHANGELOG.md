# Changelog

## V4 Bootstrap

- Established V3.3.3 / V4 coexistence policy
- Defined V4 next-generation model positioning
- Added V3.3.3 architecture inventory
- Added master build checklist
- Added Codex/agent governance
- Initialized V4 engineering skeleton

## V4-006 Versioning Standard

## V4-007 Runtime Role Boundary

- Defined isolated PRODUCTION, SHADOW, and EXPERIMENT runtime roles and identities.
- Defined the same-frozen-input Forward A/B rule, pre-kickoff Shadow eligibility, and Experiment isolation.
- Defined Production uniqueness, strict Promotion Path, manual Promotion Gate, append-only rollback, Public Web isolation, Tier A eligibility, and the role-scoped access matrix.
- Added docs/V4_RUNTIME_ROLE_BOUNDARY.md, docs/V4_PRODUCTION_POLICY.md, docs/V4_SHADOW_POLICY.md, docs/V4_EXPERIMENT_POLICY.md, docs/V4_PROMOTION_PATH.md, and docs/V4_RUNTIME_ACCESS_MATRIX.md.

## V4-008 Data Contract 1.0

- Defined versioned, stable, hashable contracts for Canonical Facts, official/external odds, Team Context, Evidence, Frozen Input, Feature Bundle, Engine Output, Prediction/Frozen Prediction, Official Result, and Postmatch Review.
- Defined explicit UNKNOWN / UNAVAILABLE / NOT_VERIFIED / BLOCKED / NOT_APPLICABLE / NULL semantics, timezone-aware time boundaries, no-future-leakage checks, enum governance, ID policy, and canonical hash serialization.
- Defined independent five-market prediction interfaces, a shared Engine Output envelope, Production/Shadow/Experiment role lineage, and Model Evaluation versus Match Explanation separation.
- Added the ten V4-008 contract documents and `scripts/validate_v4_data_contracts.ps1`.

- Defined the auditable JCFB, model, engine, selector, config, schema, migration, dataset, Frozen, Shadow, and Experiment identities.
- Defined implementation, config, input, output, and Frozen Input hash boundaries.
- Defined compatibility, breaking-change, Promotion, Retirement, and release naming rules.
- Added `docs/V4_VERSIONING_STANDARD.md`, `docs/V4_VERSION_IDENTITY_CONTRACT.md`, `docs/V4_COMPATIBILITY_POLICY.md`, and `docs/V4_RELEASE_NAMING.md`.
- Added `scripts/validate_v4_versioning.ps1` and synchronized README, AGENTS, Constitution, architecture, model governance, integrity rules, and Checklist references.

## V4-009 Canonical Data Model 1.0

- Defined the logical entity catalog for canonical facts, snapshots, Frozen Input, Feature Bundles, Engine Runs, Predictions, Frozen Predictions, Results, Reviews, Tier A, Promotion, Calibration, Incidents, Audit Logs, and the Production-only public projection.
- Defined stable UUID primary keys, separate business keys, typed cross-entity relationships, same-match and same-`frozen_input_hash` checks, revision/supersedes chains, no-future-leakage persistence, and explicit Production/Shadow/Experiment isolation.
- Defined append-only boundaries, correction/deletion policy, lifecycle stages, index planning, and the future Supabase/Postgres blueprint with RLS, security-invoker view, trigger, and service-role boundaries.
- Added the seven V4-009 design documents; no database migration, Supabase write, model execution, or V3.3.3 change was performed.

## V4-010 Database Schema Blueprint 1.0

- Defined the seven-schema PostgreSQL/Supabase physical design for canonical core facts, market/context, model lineage, evaluation, governance, and Production-only public projections.
- Added the table, constraint, index, RLS/security, trigger, view, and migration-plan catalogs, including append-only/revision rules, frozen immutability, no-future-leakage gates, role isolation, Tier A pair integrity, audit-chain fields, and canonical latest-update sourcing.
- Added the design-only candidate SQL at `database/schema/v4_schema_blueprint.sql`; no database migration, Supabase write, SQL execution, model execution, or V3.3.3 change was performed.

## V4-011 Database Migration Design 1.0

- Defined the immutable `migration@20260901.001`–`.009` identity set, strict dependency graph, transaction boundaries, idempotency limits, preflight gate, roll-forward/forward-fix policy, schema version registry, and deployment roles.
- Added design-only migration files `database/migrations/v4/0001_prerequisites.sql` through `0009_seed_and_smoke.sql`, with `PENDING_CANONICAL_HASH` and no automatic execution path.
- Added the migration acceptance gate, 20-case smoke-test design, static migration-design validator, and explicit RLS/private-table, security-invoker, Production uniqueness, no-future-leakage, Tier A, audit, and V3.3.3 isolation checks.
- No migration, SQL statement, Supabase write, model execution, Shadow/Experiment run, Production release, or V3.3.3 change was performed.
