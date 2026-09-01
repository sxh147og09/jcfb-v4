# JCFB V4.0 Master Build Checklist

## Build status

- [x] V4-001 V3.3.3 与 V4 长期并存
- [x] V4-002 定义 V4 Next Generation 技术定位
- [x] V4-003 V3.3.3 Architecture Inventory
- [x] V4-004 Architecture Blueprint 1.0
- [x] V4-005 Constitution 1.0
- [x] V4-006 Versioning Standard
- [x] V4-007 Production / Shadow / Experiment Boundary
- [x] V4-008 Data Contract 1.0
- [x] V4-009 Canonical Data Model 1.0
- [x] V4-010 Database Schema Blueprint 1.0
- [x] V4-011 Database Migration Design 1.0

## Completion rule

任务只有同时满足以下条件才能打勾：

1. Design finalized
2. Engineering artifact exists
3. Validation completed
4. Documentation completed
5. Git traceability exists

如果只是讨论完成，不得标记 COMPLETE。

## Evidence for completed items

| Item | Engineering and documentation evidence | Validation evidence |
|---|---|---|
| V4-001 | `docs/V333_V4_COEXISTENCE.md`, `AGENTS.md`, repository boundary | Required headings, isolation terms, and V3 protection checks; PASS |
| V4-002 | `docs/V4_PROJECT_CHARTER.md`, `README.md` | Required pipeline, target capabilities, and non-goal checks; PASS |
| V4-003 | `docs/V333_ARCHITECTURE_INVENTORY.md` | Four classes, items 1–35, and reference-only rule checks; PASS |
| V4-004 | Six architecture documents under `docs/` | Cross-file consistency, boundary, and Secret Scan checks; PASS |
| V4-005 | Six governance documents, `AGENTS.md`, and `README.md` | 40-Article Self Audit, Architecture Compatibility, and Secret Scan checks; PASS |
| V4-006 | `docs/V4_VERSIONING_STANDARD.md`, `docs/V4_VERSION_IDENTITY_CONTRACT.md`, `docs/V4_COMPATIBILITY_POLICY.md`, `docs/V4_RELEASE_NAMING.md`, `scripts/validate_v4_versioning.ps1`, and synchronized root/governance references | Version-field, hash, release-name, compatibility, cross-file, role-alias, V3.3.3 boundary, `git diff --check`, and Secret Scan checks; PASS |

| V4-007 | six runtime boundary contracts under docs/, AGENTS.md, README.md, and CHANGELOG.md | Production uniqueness, role isolation, same-frozen-input A/B, pre-kickoff Shadow, Experiment exclusion, Promotion Gate, rollback, Public Web, access matrix, Self Audit, Secret Scan, git diff --check, and V3.3.3 protection; PASS |
| V4-008 | `docs/V4_DATA_CONTRACT.md`, the nine companion contract documents, `AGENTS.md`, `README.md`, `CHANGELOG.md`, and `scripts/validate_v4_data_contracts.ps1` | Required fields, JSON examples, JSON duplicate/structure check, Cross-Contract Consistency, UNKNOWN/UNAVAILABLE separation, five-market completeness, official/external odds isolation, timezone/cutoff, immutable Frozen Input/Frozen Prediction, role/hash/version checks, Model Evaluation/Match Explanation separation, Secret Scan, `git diff --check`, and V3.3.3 protection; PASS |
| V4-009 | `docs/V4_CANONICAL_DATA_MODEL.md`, `docs/V4_ENTITY_RELATIONSHIP_MODEL.md`, `docs/V4_PERSISTENCE_BOUNDARIES.md`, `docs/V4_APPEND_ONLY_POLICY.md`, `docs/V4_MODEL_DATA_ISOLATION.md`, `docs/V4_DATA_LIFECYCLE.md`, `docs/V4_FUTURE_SUPABASE_BLUEPRINT.md`, `AGENTS.md`, `README.md`, and `CHANGELOG.md` | Entity/relationship coverage, stable PK/business-key separation, Frozen Input lineage, same-hash A/B, append-only/revision chains, role isolation, no-future-leakage persistence, Tier A/public boundaries, Cross-Contract Consistency, Constitution compatibility, Secret Scan, `git diff --check`, and V3.3.3 protection; PASS |
| V4-010 | `docs/V4_DATABASE_SCHEMA_BLUEPRINT.md`, `docs/V4_TABLE_CATALOG.md`, `docs/V4_CONSTRAINT_CATALOG.md`, `docs/V4_INDEX_BLUEPRINT.md`, `docs/V4_RLS_SECURITY_BLUEPRINT.md`, `docs/V4_TRIGGER_BLUEPRINT.md`, `docs/V4_VIEW_BLUEPRINT.md`, `docs/V4_MIGRATION_PLAN.md`, `database/schema/v4_schema_blueprint.sql`, `AGENTS.md`, `README.md`, and `CHANGELOG.md` | Namespace/table/PK/FK/unique/check coverage, append-only and frozen immutability, no-future-leakage DB gates, Production/Shadow/Experiment isolation, Tier A same-hash integrity, RLS/security-invoker/public read isolation, audit chain, canonical latest-update source, migration phases 0–8, Cross-Doc Consistency, Constitution compatibility, Secret Scan, `git diff --check`, and V3.3.3 protection; PASS |

| V4-011 | `docs/V4_DATABASE_MIGRATION_DESIGN.md`, `docs/V4_MIGRATION_DEPENDENCY_GRAPH.md`, `docs/V4_MIGRATION_PREFLIGHT.md`, `docs/V4_MIGRATION_ROLLFORWARD_POLICY.md`, `docs/V4_MIGRATION_SMOKE_TESTS.md`, `docs/V4_SCHEMA_VERSION_REGISTRY.md`, `docs/V4_MIGRATION_ACCEPTANCE_GATE.md`, `database/migrations/v4/0000_manifest.md`, `0001`-`0009`, `scripts/validate_v4_migration_design.ps1`, and synchronized governance references | Migration identity/hash, dependency/cycle, preflight, dry-run, transaction/roll-forward, 20 smoke cases, RLS/trigger/view/advisor, no-future-leakage, Tier A, V3.3.3 isolation, Secret Scan, `git diff --check`, and no-database-write checks; PASS |

## Traceability

V4-007 Runtime Boundary Commit: 4f77bda
V4-008 Data Contract Commit: `32646cb45377126f1816a0285934d705b4f9cec4`

V4-001 through V4-011 artifacts pass content, boundary, and governance validation and are included in Git commits. V4-005 is recorded in the Constitution commit and this follow-up documentation commit. Future items must add their own artifact and validation evidence before being marked.

V4-011 Database Migration Design Commit: `cd7ebfd5135275536c2d54ca1ecd980bb386dcfa`
V4-011 Checklist Confirmation Commit: this follow-up documentation commit
Initial Bootstrap Commit: `d2d51429cfe768ff47212f95066a0047b8fb766c`
Checklist Confirmation Commit: this follow-up documentation commit
V4-004 Architecture Commit: `271b999fe6152b9e87e4442aae95f8810327ce23`
V4-005 Constitution Commit: `87b72b091140773ebd50949ac320bc02f82333c2`
V4-006 Versioning Commit: `2f58974582d08edbb05c11d61d5605727c391c16`
V4-006 Checklist Confirmation Commit: this follow-up documentation commit
V4-007 Checklist Confirmation Commit: this follow-up documentation commit
V4-008 Checklist Confirmation Commit: this follow-up documentation commit
V4-009 Canonical Data Model Commit: `2dddc6c358cf873ccd3356be4f38e5a743fc476d`
V4-009 Checklist Confirmation Commit: this follow-up documentation commit
V4-010 Database Schema Blueprint Commit: `3ac871b`
V4-010 Checklist Confirmation Commit: this follow-up documentation commit

## V4-012–V4-100 Batch Mapping

Planning Audit Status: `BLOCKED` — the current repository contains no authoritative task entries for V4-013–V4-100. This section records the gap without changing any checklist completion state.

| Task ID range | Source task name status | Candidate Batch ID | Classification status |
|---|---|---|---|
| V4-012 | Verified: Migration Dry-Run & Validation Harness Design 1.0 | BATCH-01 (provisional) | `BATCHABLE + SERIAL` |
| V4-013–V4-100 | No source entries found in this checklist, repository, or reachable Git history | `UNASSIGNED` | `UNRESOLVED` — no permitted label assigned |

The complete per-ID audit is in `docs/V4_EXECUTION_CLASSIFICATION.md`. No V4-012+ item is marked `[x]`; this mapping is not permission to begin V4-012.
