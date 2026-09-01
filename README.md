# JCFB V4

Next-Generation Football Prediction System

Status:
EARLY DEVELOPMENT

Current Build Stage:
V4-006 COMPLETE
V4-007 COMPLETE
V4-008 COMPLETE
V4-009 COMPLETE
V4-010 NEXT

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

V4-001 through V4-009 are complete. V4-010 has not started.
