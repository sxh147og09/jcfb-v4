# Changelog

## JCFB V4 RESERVED SERVICE_ROLE Forward-Fix 1.0

- Recorded the failed Production attempt as `RESERVED_ROLE_MUTATION`: migration 0001 rolled back, migrations 0002-0009 were not run, the official migration history remained unchanged, and no Production/Supabase committed write occurred.
- Replaced the unapplied candidate's `ALTER ROLE service_role BYPASSRLS` mutation with a fail-closed verification that the provider-owned role exists with `rolbypassrls=true`; `anon` and `authenticated` must retain `rolbypassrls=false`.
- Added the separate disposable-only local compatibility-role bootstrap, regression coverage, reserved-role static auditing, and the forward-fix report at `docs/V4_RESERVED_SERVICE_ROLE_FORWARD_FIX.md`.
- Recomputed canonical hashes: 0001 changed for the prerequisite repair and 0009 changed only because its registry seed embeds the 0001 hash; 0002-0008 remain unchanged. A fresh approval chain is required before any second Production Apply.
- No V3.3.3 object/history, V4-018/V4-019 item, or BATCH-04 status was changed.

## JCFB V4 Supabase Preflight Plan Completion 1.0

- Recorded the supplied read-only Production baseline for Supabase project ref `icndieflfvydixtehgzu`, PostgreSQL 17.6, nine existing V3.3.3-era migration rows, public schema counts, named identity samples, and stable Security/Performance advisor fingerprints.
- Added the apply-before checklist, object-identity schema diff and V3.3.3 isolation contract, advisor before/after policy, partial-apply detector, forward-fix/recovery contract, fourteen post-apply verifications, and explicit human-approval separation.
- Added repository-only validation for the completed preflight plan and canonical-hash 9/9 verification. Production hard block remains closed; no Supabase/Production write, BATCH-04 execution, V4-018/V4-019 change, or V3.3.3 mutation occurred.

## JCFB V4 Production Target Binding 1.0

- Bound the sole non-secret Production target identity to Supabase project ref `icndieflfvydixtehgzu`, region `us-west-2`, and PostgreSQL major `17` after explicit human confirmation.
- Added exactly-one-Production, project-ref format, disposable/staging isolation, no-secret, and explicit-apply-approval validators plus an identity-only Production Readiness input.
- Preserved the Production hard block; no Production/Supabase write, BATCH-04 execution, V4-018/V4-019 completion, or V3.3.3 change occurred.
- Scoped the legacy design validator to `database/schema` and `database/migrations/v4`; runtime candidates remain under their separate candidate validator.

## V4-016 / V4-017 — BATCH-03 Staging Readiness & Migration Acceptance Package

- Added the three-environment staging/disposable target readiness contract with fail-closed states, explicit identity/isolation/reset/teardown/retention rules, environment-only secret references, and a Production hard block.
- Added the no-write acceptance package schema, evidence index, manifest 0001–0009 binding, preflight/smoke/negative/runtime-pending matrix, schema/RLS/trigger/view/security/no-future/Tier-A/history expectations, roll-forward control-flow drill, and separated signoff placeholders.
- Recorded `RUNTIME_PENDING_DISPOSABLE_DB`, `NO_PRODUCTION_APPLY_IN_THIS_BATCH`, and no database/Supabase/Production/Shadow/V3.3.3 execution.

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

## V4-012 Migration Dry-Run & Validation Harness Design 1.0

- Defined the fail-closed `PLAN_ONLY`/`DRY_RUN` boundary, explicit disposable-local and staging target contract, hard-blocked Production adapter, environment-only secret reference, and no automatic installation/start path.
- Added deterministic manifest-loader, preflight, transaction/failure, validation, 20-case smoke, schema snapshot/diff, append-only history, RLS/security, trigger/view, no-future-leakage, role-isolation, Tier A same-frozen-input, and canonical-latest-update interfaces.
- Added machine-readable harness policy, target/manifest/smoke/schema-diff/acceptance-report contracts and a local static design validator; V4-012 is accepted design-only and requires a disposable database later for runtime evidence.
- No database connection, SQL execution, migration apply, Supabase write, model/runtime run, Shadow/Experiment run, Production operation, or V3.3.3 change was performed.
