# JCFB V4

Next-Generation Football Prediction System

Status:
BLUEPRINT AND MIGRATION DESIGN COMPLETE / MIGRATION NOT APPLIED

Current Build Stage:
V4-006 COMPLETE
V4-007 COMPLETE
V4-008 COMPLETE
V4-009 COMPLETE
V4-010 COMPLETE
V4-011 COMPLETE
V4-012 NEXT

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

V4-001 through V4-011 are complete as governance and design artifacts. V4-011 defines the ordered PostgreSQL/Supabase migration architecture, preflight, roll-forward policy, registry/history, RLS/trigger/view deployment gates, and future smoke validation only. No database migration, Supabase write, model execution, or V3.3.3 change was performed.
