# JCFB V4

Next-Generation Football Prediction System

Status:
EARLY DEVELOPMENT

Current Build Stage:
V4-005 COMPLETE
V4-006 NEXT

Legacy Production:
JCFB V3.3.3 remains independent and unchanged.

## Project position

JCFB V4.0 is an independent next-generation football prediction system. It is not a rename, replacement, or in-place rewrite of JCFB V3.3.3.

V4 owns its own code, configuration, model versions, predictions, frozen predictions, reviews, and sample qualification. Objective facts may be shared only when they are canonical, timestamped, provenance-preserving, and safe from future leakage. Model outputs and conclusions remain isolated by model version.

## Governance

Governance:

JCFB V4 is governed by:

[`docs/V4_CONSTITUTION.md`](docs/V4_CONSTITUTION.md)

The Constitution governs Production, Shadow, Experiment, data pipelines, engines, simulation, calibration, review, Tier A, promotion, Public Web, Codex Agents, and Human Operators.

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

- `docs/` — project charter, coexistence policy, architecture inventory, and build checklist
- `src/` — reserved boundaries for data, intelligence, markets, models, scoring, simulation, consensus, risk, freeze, and review
- `config/` — reserved engine, league, and model configuration boundaries
- `database/` — reserved migration and schema boundaries
- `tests/` — reserved unit, integration, reproducibility, and no-future-leakage test boundaries
- `scripts/` — reserved project utilities

## Current scope

V4-001 through V4-005 are complete. V4-006 Versioning Standard has not started.
