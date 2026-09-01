# JCFB V4 Execution Classification 012–100 1.0

Status: `PASS` for complete classification and unique primary mapping; `V4-012 COMPLETE`; V4-013+ execution remains not started.

Classification Identity: `v4-execution-classification-012-100@1.0.0`
Revision: `r002`
Audit Date: `2026-09-01` (`Asia/Shanghai`)
Source of truth: `docs/V4_TASK_REGISTRY_001_100.md`
Execution Declaration: **V4-012 EXECUTED DESIGN-ONLY; NO DATABASE EXECUTION**

## 1. Classification semantics

- `BATCHABLE`: may share a controlled implementation cycle with adjacent tasks.
- `PARALLEL`: may develop concurrently after its declared upstream contract is ready.
- `SERIAL`: acceptance must follow its declared dependency order.
- `HARD_GATE`: separate evidence, acceptance, and explicit approval are required; ordinary batch success cannot cross it.

The classification below is a complete register, not a candidate envelope. Every row is a TODO task and every row has exactly one primary batch.

## 2. Complete classification register

| Task ID | Task Name | Classification | Primary Batch | Upstream Dependencies | Supabase Write Allowed? | Production/Shadow Runtime Allowed? | Explicit User Approval Required? | Status |
|---|---|---|---|---|---|---|---|---|
| V4-012 | Migration Dry-Run & Validation Harness Design 1.0 | BATCHABLE + SERIAL | BATCH-01 | V4-011 | NO | NO | NO | COMPLETE |
| V4-013 | V4-013｜Migration Dry-Run Harness Implementation 1.0 | BATCHABLE + SERIAL | BATCH-02 | V4-012 | NO | NO | NO | TODO |
| V4-014 | V4-014｜Migration Preflight & Schema-Diff Validator 1.0 | BATCHABLE + PARALLEL | BATCH-02 | V4-013 | NO | NO | NO | TODO |
| V4-015 | V4-015｜Migration Smoke, RLS & Trigger Test Suite 1.0 | BATCHABLE + PARALLEL | BATCH-02 | V4-013 | NO | NO | NO | TODO |
| V4-016 | V4-016｜Staging Readiness & Disposable Target Contract 1.0 | BATCHABLE + SERIAL | BATCH-03 | V4-014, V4-015 | NO | NO | NO | TODO |
| V4-017 | V4-017｜Migration Acceptance Package & Roll-forward Drill 1.0 | SERIAL | BATCH-03 | V4-016 | NO | NO | NO | TODO |
| V4-018 | V4-018｜Formal Supabase Schema Apply HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-04 | V4-017 | YES | NO | YES | TODO |
| V4-019 | V4-019｜Production Database Write Activation HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-04 | V4-018 | YES | YES | YES | TODO |
| V4-020 | V4-020｜Canonical Match Identity & Schedule Intake 1.0 | BATCHABLE + SERIAL | BATCH-05 | V4-019 | YES | NO | NO | TODO |
| V4-021 | V4-021｜Canonical Fact Envelope & Availability Semantics 1.0 | BATCHABLE + PARALLEL | BATCH-05 | V4-020 | YES | NO | NO | TODO |
| V4-022 | V4-022｜Cutoff, Timestamp & Provenance Lineage 1.0 | BATCHABLE + PARALLEL | BATCH-05 | V4-020, V4-021 | YES | NO | NO | TODO |
| V4-023 | V4-023｜Canonical Intake Orchestrator & Deduplication 1.0 | BATCHABLE + SERIAL | BATCH-05 | V4-020, V4-021, V4-022 | YES | NO | NO | TODO |
| V4-024 | V4-024｜Official Lottery Five-Market Feed Adapter 1.0 | BATCHABLE + PARALLEL | BATCH-06 | V4-023 | YES | NO | NO | TODO |
| V4-025 | V4-025｜Official Screenshot Intake & OCR Verification 1.0 | BATCHABLE + PARALLEL | BATCH-06 | V4-023 | YES | NO | NO | TODO |
| V4-026 | V4-026｜Official Market Availability & Missingness Gate 1.0 | BATCHABLE + SERIAL | BATCH-06 | V4-024, V4-025 | YES | NO | NO | TODO |
| V4-027 | V4-027｜Official Odds Timestamp & Provenance Ledger 1.0 | BATCHABLE + SERIAL | BATCH-06 | V4-024, V4-025, V4-026 | YES | NO | NO | TODO |
| V4-028 | V4-028｜External European 1X2 Intake 1.0 | BATCHABLE + PARALLEL | BATCH-07 | V4-023 | YES | NO | NO | TODO |
| V4-029 | V4-029｜External Asian Handicap Intake 1.0 | BATCHABLE + PARALLEL | BATCH-07 | V4-023 | YES | NO | NO | TODO |
| V4-030 | V4-030｜External O/U Intake 1.0 | BATCHABLE + PARALLEL | BATCH-07 | V4-023 | YES | NO | NO | TODO |
| V4-031 | V4-031｜External Source-Time Normalization 1.0 | BATCHABLE + SERIAL | BATCH-07 | V4-028, V4-029, V4-030 | YES | NO | NO | TODO |
| V4-032 | V4-032｜Team Context Intake & Identity Linker 1.0 | BATCHABLE + SERIAL | BATCH-08 | V4-023 | YES | NO | NO | TODO |
| V4-033 | V4-033｜Availability, Injury & Suspension Intake 1.0 | BATCHABLE + PARALLEL | BATCH-08 | V4-032 | YES | NO | NO | TODO |
| V4-034 | V4-034｜Lineup, Coach & Tactical Context Intake 1.0 | BATCHABLE + PARALLEL | BATCH-08 | V4-032 | YES | NO | NO | TODO |
| V4-035 | V4-035｜Schedule, Travel, Weather & Pitch Context Intake 1.0 | BATCHABLE + PARALLEL | BATCH-08 | V4-032 | YES | NO | NO | TODO |
| V4-036 | V4-036｜Evidence Graph Claim & Evidence Model 1.0 | BATCHABLE + SERIAL | BATCH-09 | V4-034 | YES | NO | NO | TODO |
| V4-037 | V4-037｜Source Quality, Expiry & Conflict Resolver 1.0 | BATCHABLE + SERIAL | BATCH-09 | V4-036 | YES | NO | NO | TODO |
| V4-038 | V4-038｜Feature Bundle Contract & Version Registry 1.0 | BATCHABLE + SERIAL | BATCH-10 | V4-021, V4-022, V4-027, V4-031, V4-037 | YES | NO | NO | TODO |
| V4-039 | V4-039｜Feature Snapshot Hash & Reproducibility 1.0 | BATCHABLE + SERIAL | BATCH-10 | V4-038 | YES | NO | NO | TODO |
| V4-040 | V4-040｜Feature Assembly & Schema Adapter Layer 1.0 | SERIAL | BATCH-10 | V4-039 | YES | NO | NO | TODO |
| V4-041 | V4-041｜Dynamic Team Rating Feature Engine 1.0 | BATCHABLE + PARALLEL | BATCH-11 | V4-040 | YES | NO | NO | TODO |
| V4-042 | V4-042｜Attack, Defence & Home Advantage Model 1.0 | BATCHABLE + PARALLEL | BATCH-11 | V4-040 | YES | NO | NO | TODO |
| V4-043 | V4-043｜Opponent Adjustment, Form Decay & League Strength 1.0 | BATCHABLE + SERIAL | BATCH-11 | V4-041, V4-042 | YES | NO | NO | TODO |
| V4-044 | V4-044｜Football Intelligence Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-12 | V4-040, V4-043 | YES | NO | NO | TODO |
| V4-045 | V4-045｜Football Context Feature Integration 1.0 | BATCHABLE + PARALLEL | BATCH-12 | V4-044 | YES | NO | NO | TODO |
| V4-046 | V4-046｜Market Intelligence Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-13 | V4-040, V4-027, V4-031 | YES | NO | NO | TODO |
| V4-047 | V4-047｜Market Movement, Velocity & Divergence Features 1.0 | BATCHABLE + PARALLEL | BATCH-13 | V4-046 | YES | NO | NO | TODO |
| V4-048 | V4-048｜Market Heat & Trap-Risk Interpretation 1.0 | BATCHABLE + PARALLEL | BATCH-13 | V4-046, V4-047 | YES | NO | NO | TODO |
| V4-049 | V4-049｜Tactical Matchup & League Profile Features 1.0 | BATCHABLE + PARALLEL | BATCH-14 | V4-040, V4-045, V4-037 | YES | NO | NO | TODO |
| V4-050 | V4-050｜Data Quality Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-14 | V4-021, V4-022, V4-027, V4-031, V4-037 | YES | NO | NO | TODO |
| V4-051 | V4-051｜Provenance & Quality Gate Enforcement 1.0 | SERIAL | BATCH-14 | V4-049, V4-050 | YES | NO | NO | TODO |
| V4-052 | V4-052｜Outcome Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | YES | NO | NO | TODO |
| V4-053 | V4-053｜Handicap Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | YES | NO | NO | TODO |
| V4-054 | V4-054｜Goals Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | YES | NO | NO | TODO |
| V4-055 | V4-055｜HTFT Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | YES | NO | NO | TODO |
| V4-056 | V4-056｜Dynamic Lambda Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-16 | V4-041, V4-042, V4-043, V4-052, V4-054 | YES | NO | NO | TODO |
| V4-057 | V4-057｜Score Distribution Candidate Ensemble 4.0 | BATCHABLE + PARALLEL | BATCH-16 | V4-056 | YES | NO | NO | TODO |
| V4-058 | V4-058｜Score Variance, Correlation, BTTS & Clean Sheet Layer 4.0 | BATCHABLE + PARALLEL | BATCH-16 | V4-056, V4-057 | YES | NO | NO | TODO |
| V4-059 | V4-059｜Score Distribution Interface Validation 4.0 | SERIAL | BATCH-16 | V4-056, V4-057, V4-058 | YES | NO | NO | TODO |
| V4-060 | V4-060｜Score Matrix 4.0 | BATCHABLE + SERIAL | BATCH-17 | V4-059 | YES | NO | NO | TODO |
| V4-061 | V4-061｜Score Candidate Generator 4.0 | BATCHABLE + PARALLEL | BATCH-17 | V4-060 | YES | NO | NO | TODO |
| V4-062 | V4-062｜Score Re-ranker 4.0 | BATCHABLE + SERIAL | BATCH-17 | V4-057, V4-059, V4-061 | YES | NO | NO | TODO |
| V4-063 | V4-063｜Exact Score Selector 4.0 | BATCHABLE + SERIAL | BATCH-17 | V4-062 | YES | NO | NO | TODO |
| V4-064 | V4-064｜Scenario Diversity Selector 4.0 | SERIAL | BATCH-17 | V4-062, V4-063 | YES | NO | NO | TODO |
| V4-065 | V4-065｜Match Simulation Engine 1.0 | BATCHABLE + SERIAL | BATCH-18 | V4-052, V4-056, V4-059 | YES | NO | NO | TODO |
| V4-066 | V4-066｜Simulation Reproducibility & Performance Harness 1.0 | BATCHABLE + PARALLEL | BATCH-18 | V4-065 | YES | NO | NO | TODO |
| V4-067 | V4-067｜Match Script Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-18 | V4-044, V4-045, V4-065 | YES | NO | NO | TODO |
| V4-068 | V4-068｜Upset Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-18 | V4-052, V4-065, V4-067 | YES | NO | NO | TODO |
| V4-069 | V4-069｜Cross-Model Consensus Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-19 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-065, V4-068 | YES | NO | NO | TODO |
| V4-070 | V4-070｜Model Disagreement Index 1.0 | BATCHABLE + PARALLEL | BATCH-19 | V4-069 | YES | NO | NO | TODO |
| V4-071 | V4-071｜Uncertainty Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-19 | V4-069, V4-070, V4-065 | YES | NO | NO | TODO |
| V4-072 | V4-072｜Risk & Abstention Engine 4.0 1.0 | BATCHABLE + PARALLEL | BATCH-19 | V4-069, V4-070, V4-071, V4-068, V4-051 | YES | NO | NO | TODO |
| V4-073 | V4-073｜Prediction Consistency Engine 1.0 | SERIAL | BATCH-19 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-069, V4-070 | YES | NO | NO | TODO |
| V4-074 | V4-074｜Five-Market Orchestrator 4.0 1.0 | BATCHABLE + SERIAL | BATCH-20 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-073 | YES | NO | NO | TODO |
| V4-075 | V4-075｜Final Prediction Gate 4.0 1.0 | BATCHABLE + SERIAL | BATCH-20 | V4-074, V4-072 | YES | NO | NO | TODO |
| V4-076 | V4-076｜Frozen Input & Immutable Lineage 4.0 1.0 | BATCHABLE + SERIAL | BATCH-20 | V4-022, V4-038, V4-039, V4-075 | YES | NO | NO | TODO |
| V4-077 | V4-077｜Frozen Prediction & Revision Chain 4.0 1.0 | SERIAL | BATCH-20 | V4-076 | YES | NO | NO | TODO |
| V4-078 | V4-078｜Official Result Intake 1.0 | BATCHABLE + SERIAL | BATCH-21 | V4-077 | YES | NO | NO | TODO |
| V4-079 | V4-079｜Postmatch Review Engine 4.0 1.0 | BATCHABLE + SERIAL | BATCH-21 | V4-077, V4-078 | YES | NO | NO | TODO |
| V4-080 | V4-080｜Model Evaluation & Match Explanation Separation 1.0 | BATCHABLE + PARALLEL | BATCH-21 | V4-079 | YES | NO | NO | TODO |
| V4-081 | V4-081｜Error Attribution Engine 1.0 | SERIAL | BATCH-21 | V4-079, V4-080 | YES | NO | NO | TODO |
| V4-082 | V4-082｜Calibration Engine & Reliability Metrics 1.0 | BATCHABLE + PARALLEL | BATCH-22 | V4-079, V4-081 | YES | NO | NO | TODO |
| V4-083 | V4-083｜League Profiles & Sample Quality 1.0 | BATCHABLE + PARALLEL | BATCH-22 | V4-079, V4-081 | YES | NO | NO | TODO |
| V4-084 | V4-084｜Regression Suite & Performance Benchmarks 1.0 | BATCHABLE + PARALLEL | BATCH-22 | V4-082, V4-083 | YES | NO | NO | TODO |
| V4-085 | V4-085｜Forward Shadow Pair Infrastructure 1.0 | BATCHABLE + SERIAL | BATCH-23 | V4-077, V4-084 | YES | NO | NO | TODO |
| V4-086 | V4-086｜V4 Tier A Qualification Contract 1.0 | BATCHABLE + SERIAL | BATCH-23 | V4-085, V4-078, V4-079 | YES | NO | NO | TODO |
| V4-087 | V4-087｜Forward Sample Registration Interface 1.0 | SERIAL | BATCH-23 | V4-086 | YES | NO | NO | TODO |
| V4-088 | V4-088｜Cross-Version Benchmark V3.3.3 vs V4 1.0 | BATCHABLE + SERIAL | BATCH-24 | V4-082, V4-084, V4-086 | YES | NO | NO | TODO |
| V4-089 | V4-089｜Promotion Evaluation Evidence Package 1.0 | SERIAL | BATCH-24 | V4-088, V4-087 | YES | NO | NO | TODO |
| V4-090 | V4-090｜Public Read Projection 1.0 | BATCHABLE + SERIAL | BATCH-25 | V4-077, V4-088 | YES | NO | NO | TODO |
| V4-091 | V4-091｜Canonical Data Center API 1.0 | SERIAL | BATCH-25 | V4-090 | YES | NO | NO | TODO |
| V4-092 | V4-092｜Public UI, Data Center & Prediction Pages 1.0 | BATCHABLE + SERIAL | BATCH-26 | V4-091 | YES | NO | NO | TODO |
| V4-093 | V4-093｜Observability, PostHog & Web Vitals 1.0 | BATCHABLE + PARALLEL | BATCH-26 | V4-092 | YES | NO | NO | TODO |
| V4-094 | V4-094｜Caching & Compute Once Read Many 1.0 | BATCHABLE + PARALLEL | BATCH-26 | V4-090, V4-091, V4-093 | YES | NO | NO | TODO |
| V4-095 | V4-095｜Security Hardening & Audit Integrity 1.0 | BATCHABLE + PARALLEL | BATCH-27 | V4-088, V4-094 | NO | NO | NO | TODO |
| V4-096 | V4-096｜Disaster Recovery, Release Candidate & Operator Runbook 1.0 | BATCHABLE + SERIAL | BATCH-27 | V4-095 | NO | NO | NO | TODO |
| V4-097 | V4-097｜End-to-End Dry Run & Production Readiness Review HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-27 | V4-095, V4-096, V4-088, V4-089, V4-094 | NO | NO | YES | TODO |
| V4-098 | V4-098｜Shadow-Only Pilot & Promotion Review HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-28 | V4-097, V4-085, V4-087, V4-089 | YES | YES | YES | TODO |
| V4-099 | V4-099｜Production Activation & Rollback HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-29 | V4-098, V4-097 | YES | YES | YES | TODO |
| V4-100 | V4-100｜Final Production Release, Canonical Pointer Switch & Post-Release Closure HARD_GATE 1.0 | SERIAL + HARD_GATE | BATCH-30 | V4-099, V4-090, V4-092, V4-093 | YES | YES | YES | TODO |

## 3. Classification audit

| Check | Result | Evidence |
|---|---|---|
| Requested scope | PASS: V4-012–V4-100, 89 tasks | Registry and this complete table |
| Missing IDs | PASS: 0 | Exact sequence V4-012 through V4-100 |
| Duplicate IDs | PASS: 0 | One row per task ID |
| Missing classification | PASS: 0 | Every row has one or more permitted labels |
| Primary batch uniqueness | PASS: 0 conflicts | Every row has one primary Batch ID |
| Orphan tasks | PASS: 0 | Every task appears in registry, checklist, classification, and batch plan |
| HARD_GATE explicit | PASS: 6 tasks | V4-018, V4-019, V4-097, V4-098, V4-099, V4-100 |
| Supabase write isolation | PASS | Writes are conditional and downstream of named gate; current recovery performs none |
| Production/Shadow isolation | PASS | Runtime YES appears only on approved V4-098, V4-099, V4-100 paths; current recovery performs none |
| V3.3.3 isolation | PASS | Benchmark is read-only and no task mutates V3.3.3 |

## 4. Batch mapping disposition

The mapping remains the authoritative classification register. V4-012 is independently accepted as a design-only task; V4-013 through V4-100 remain TODO and no downstream batch is authorized by this status update.
