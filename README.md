# JCFB V4

Next-Generation Football Prediction System

Status:
BATCH-04 PRODUCTION SCHEMA APPLY AND V4 WRITE BOUNDARY COMPLETE / BATCH-05 COMPLETE — BATCH-06 V4-024 COMPLETE

Current Build Stage:
V4-006 COMPLETE
V4-007 COMPLETE
V4-008 COMPLETE
V4-009 COMPLETE
V4-010 COMPLETE
V4-011 COMPLETE
V4-012 COMPLETE
V4-013 COMPLETE
V4-014 COMPLETE
V4-015 COMPLETE
V4-016 COMPLETE
V4-017 COMPLETE
V4-018 COMPLETE
V4-019 COMPLETE
BATCH-06 V4-024 COMPLETE
BATCH-06 V4-025 NEXT
BATCH-05 CLOSURE REVIEW PASS

Legacy Production:
JCFB V3.3.3 remains independent and unchanged.

## Project position

JCFB V4.0 is an independent next-generation football prediction system. It is not a rename, replacement, or in-place rewrite of JCFB V3.3.3.

V4 owns its own code, configuration, model versions, predictions, frozen predictions, reviews, and sample qualification. Objective facts may be shared only when they are canonical, timestamped, provenance-preserving, and safe from future leakage. Model outputs and conclusions remain isolated by model version.

## Governance

Governance:

JCFB V4 is governed by:

[`docs/V4_CONSTITUTION.md`](docs/V4_CONSTITUTION.md)

Exact version identity, hash, compatibility, and release naming are governed by [`docs/V4_VERSIONING_STANDARD.md`](docs/V4_VERSIONING_STANDARD.md), [`docs/V4_VERSION_IDENTITY_CONTRACT.md`](docs/V4_VERSION_IDENTITY_CONTRACT.md), [`docs/V4_COMPATIBILITY_POLICY.md`](docs/V4_COMPATIBILITY_POLICY.md), and [`docs/V4_RELEASE_NAMING.md`](docs/V4_RELEASE_NAMING.md).

The Constitution governs Production, Shadow, Experiment, data pipelines, engines, simulation, calibration, review, Tier A, promotion, Public Web, Codex Agents, and Human Operators.

Runtime role boundaries, Production uniqueness, Shadow forward evidence, Experiment isolation, Promotion, rollback, and role-scoped access are defined in docs/V4_RUNTIME_ROLE_BOUNDARY.md, docs/V4_PRODUCTION_POLICY.md, docs/V4_SHADOW_POLICY.md, docs/V4_EXPERIMENT_POLICY.md, docs/V4_PROMOTION_PATH.md, and docs/V4_RUNTIME_ACCESS_MATRIX.md.

The V4-008 versioned data interfaces are defined in [`docs/V4_DATA_CONTRACT.md`](docs/V4_DATA_CONTRACT.md) and its Canonical Facts, Odds Snapshot, Team Context, Evidence, Frozen Input, Feature Bundle, Engine Output, Prediction, and Result/Review companion contracts. Formal Production, Shadow, and Experiment paths must consume these contracts; free-form unversioned payloads are forbidden.

The V4-009 logical persistence model is defined in [`docs/V4_CANONICAL_DATA_MODEL.md`](docs/V4_CANONICAL_DATA_MODEL.md), [`docs/V4_ENTITY_RELATIONSHIP_MODEL.md`](docs/V4_ENTITY_RELATIONSHIP_MODEL.md), [`docs/V4_PERSISTENCE_BOUNDARIES.md`](docs/V4_PERSISTENCE_BOUNDARIES.md), [`docs/V4_APPEND_ONLY_POLICY.md`](docs/V4_APPEND_ONLY_POLICY.md), [`docs/V4_MODEL_DATA_ISOLATION.md`](docs/V4_MODEL_DATA_ISOLATION.md), [`docs/V4_DATA_LIFECYCLE.md`](docs/V4_DATA_LIFECYCLE.md), and [`docs/V4_FUTURE_SUPABASE_BLUEPRINT.md`](docs/V4_FUTURE_SUPABASE_BLUEPRINT.md). These are design-only artifacts; no database migration or Supabase write has been executed.

V4-010 physical schema design is documented in [`docs/V4_DATABASE_SCHEMA_BLUEPRINT.md`](docs/V4_DATABASE_SCHEMA_BLUEPRINT.md), [`docs/V4_TABLE_CATALOG.md`](docs/V4_TABLE_CATALOG.md), [`docs/V4_CONSTRAINT_CATALOG.md`](docs/V4_CONSTRAINT_CATALOG.md), [`docs/V4_INDEX_BLUEPRINT.md`](docs/V4_INDEX_BLUEPRINT.md), [`docs/V4_RLS_SECURITY_BLUEPRINT.md`](docs/V4_RLS_SECURITY_BLUEPRINT.md), [`docs/V4_TRIGGER_BLUEPRINT.md`](docs/V4_TRIGGER_BLUEPRINT.md), [`docs/V4_VIEW_BLUEPRINT.md`](docs/V4_VIEW_BLUEPRINT.md), and [`docs/V4_MIGRATION_PLAN.md`](docs/V4_MIGRATION_PLAN.md). The candidate SQL at [`database/schema/v4_schema_blueprint.sql`](database/schema/v4_schema_blueprint.sql) is blueprint-only and must never be auto-applied; V4-011 is the separate migration-design task.

V4-011 migration architecture is documented in [`docs/V4_DATABASE_MIGRATION_DESIGN.md`](docs/V4_DATABASE_MIGRATION_DESIGN.md), [`docs/V4_MIGRATION_DEPENDENCY_GRAPH.md`](docs/V4_MIGRATION_DEPENDENCY_GRAPH.md), [`docs/V4_MIGRATION_PREFLIGHT.md`](docs/V4_MIGRATION_PREFLIGHT.md), [`docs/V4_MIGRATION_ROLLFORWARD_POLICY.md`](docs/V4_MIGRATION_ROLLFORWARD_POLICY.md), [`docs/V4_MIGRATION_SMOKE_TESTS.md`](docs/V4_MIGRATION_SMOKE_TESTS.md), [`docs/V4_SCHEMA_VERSION_REGISTRY.md`](docs/V4_SCHEMA_VERSION_REGISTRY.md), and [`docs/V4_MIGRATION_ACCEPTANCE_GATE.md`](docs/V4_MIGRATION_ACCEPTANCE_GATE.md). The candidate migration files under [`database/migrations/v4/`](database/migrations/v4/) are design-only, use pending canonical hashes, and cannot be applied without explicit deployment approval.

The Production target identity is bound in [`docs/V4_PRODUCTION_TARGET_BINDING.md`](docs/V4_PRODUCTION_TARGET_BINDING.md) and [`config/migration_harness/v4_production_target_identity.json`](config/migration_harness/v4_production_target_identity.json): Supabase project ref `icndieflfvydixtehgzu`, region `us-west-2`, PostgreSQL major `17`, role `PRODUCTION`. Target identity alone never equals Production apply approval. The BATCH-04 approval was satisfied separately and is recorded in the final 0009 apply report; every future Production change still requires its own applicable approval.

The Supabase Production baseline and completed read-only preflight plan are recorded in [`docs/V4_MIGRATION_PREFLIGHT.md`](docs/V4_MIGRATION_PREFLIGHT.md) and [`config/migration_harness/v4_supabase_preflight_plan.json`](config/migration_harness/v4_supabase_preflight_plan.json). `Supabase Preflight Plan: PASS` feeds `BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3`; it does not open the Production hard block or authorize a database write.

V4-012 is complete as a design-only artifact in [`docs/V4_MIGRATION_DRY_RUN_HARNESS.md`](docs/V4_MIGRATION_DRY_RUN_HARNESS.md) with machine-readable target, manifest, smoke, schema-diff, policy, and acceptance-report contracts under [`config/migration_harness/`](config/migration_harness/). BATCH-03 adds [`docs/V4_STAGING_READINESS.md`](docs/V4_STAGING_READINESS.md), [`docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md`](docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md), and the no-write acceptance harness. No database or Supabase was contacted.

Pre-BATCH-04 Remediation 2 is a separate remediation package, not a new V4 task ID. It adds the canonical hash verifier and generated hashes for the nine runtime candidates, an optional environment-only PostgreSQL executor, and the local PowerShell validation entry point. Read [`docs/V4_CANONICAL_MIGRATION_HASH.md`](docs/V4_CANONICAL_MIGRATION_HASH.md), [`docs/V4_RUNTIME_EXECUTOR.md`](docs/V4_RUNTIME_EXECUTOR.md), and [`docs/V4_PRE_BATCH_04_LOCAL_EXECUTION.md`](docs/V4_PRE_BATCH_04_LOCAL_EXECUTION.md) before using it. The default remains `PLAN_ONLY`; explicit local apply is limited to `DISPOSABLE_LOCAL` or separately approved `STAGING`. The separate Production approval and apply path is now closed in [`docs/JCFB_V4_PRODUCTION_0009_FINAL_APPLY_REPORT.md`](docs/JCFB_V4_PRODUCTION_0009_FINAL_APPLY_REPORT.md).

## First-version architecture target

Canonical Data
↓
Football Intelligence
↓
Market Intelligence
↓
Multi-Model Prediction
↓
Score Engine
↓
Simulation
↓
Consensus
↓
Risk / Uncertainty
↓
Final Prediction
↓
Frozen Prediction
↓
Postmatch Review

The architecture target is a design direction only at this bootstrap stage. Production engines, schemas, model promotion, and historical-data migration are intentionally out of scope.

## Repository layout

- `docs/` — project charter, coexistence policy, architecture, data contracts, and build checklist
- `src/` — reserved boundaries for data, intelligence, markets, models, scoring, simulation, consensus, risk, freeze, and review
- `config/` — reserved engine, league, and model configuration boundaries
- `database/` — reserved migration and schema boundaries
- `tests/` — reserved unit, integration, reproducibility, and no-future-leakage test boundaries
- `scripts/` — reserved project utilities

## Current scope

V4-001 through V4-023 are complete as local/no-write task boundaries. BATCH-04 applied the approved V4 migration chain to the bound Supabase Production project and closed with the exact `0009 ONLY` resume recorded in [`docs/JCFB_V4_PRODUCTION_0009_FINAL_APPLY_REPORT.md`](docs/JCFB_V4_PRODUCTION_0009_FINAL_APPLY_REPORT.md). V4-020 through V4-023 were then completed as local, no-write canonical intake implementations with independent evidence in the V4-020, V4-021, V4-022, and V4-023 reports. Official migration history is 18 rows: the nine V3.3.3 rows are unchanged and the nine V4 rows are applied. No prediction, Shadow run, public deployment, canonical pointer switch, or V3.3.3 mutation occurred. BATCH-05 task acceptance is complete; Closure Review is the next gate before BATCH-06/07/08 work.

## Local storage on the project drive

Project-scoped local runtime paths are documented in [`docs/JCFB_V4_LOCAL_STORAGE.md`](docs/JCFB_V4_LOCAL_STORAGE.md). Before running project tooling from PowerShell, activate them with:

```powershell
Set-Location F:\Projects\jcfb-v4
. .\scripts\activate_jcfb_v4_runtime.ps1
```

This keeps JCFB V4 temporary files and tool caches under `.runtime\` on F:, without changing global Windows temporary paths. The disposable PostgreSQL compose runtime also uses the repository-relative `.runtime\postgres` bind directory.
