# JCFB V4

Next-Generation Football Prediction System

Status:
EARLY DEVELOPMENT

Current Build Stage:
V4-001 ~ V4-003 COMPLETE
V4-004 NEXT

Legacy Production:
JCFB V3.3.3 remains independent and unchanged.

## Project position

JCFB V4.0 is an independent next-generation football prediction system. It is not a rename, replacement, or in-place rewrite of JCFB V3.3.3.

V4 owns its own code, configuration, model versions, predictions, frozen predictions, reviews, and sample qualification. Objective facts may be shared only when they are canonical, timestamped, provenance-preserving, and safe from future leakage. Model outputs and conclusions remain isolated by model version.

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

This repository contains the V4-001 through V4-003 bootstrap artifacts only. V4-004 Architecture Blueprint 1.0 is the next task and has not been implemented in this change.
