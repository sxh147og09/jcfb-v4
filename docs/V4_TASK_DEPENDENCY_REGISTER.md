# JCFB V4 Task Dependency Register 001–100 1.0

Status: `PASS` for registry coverage and acyclic planning graph; `V4-012` through `V4-019 COMPLETE`; BATCH-05 is the next execution boundary.

Dependency Identity: `v4-task-dependency-register-001-100@1.0.0`
Revision: `r002`
Audit Date: `2026-09-04` (`Asia/Shanghai`)

## 1. Dependency source and semantics

`docs/V4_TASK_REGISTRY_001_100.md` is the source of task dependencies. An upstream dependency means its contract, artifact, and acceptance evidence must be available before the dependent task can be accepted. Dependencies are planning edges, not evidence that any task ran.

The verified historical edge is V4-011 -> V4-012. Edges from V4-013 onward are reconstructed from the approved architecture and explicit domain contracts, and are marked as planned dependencies rather than recovered history.

## 2. Complete task dependency register

| Task ID | Task Name | Primary Batch | Upstream Dependencies | Downstream Tasks | Dependency Rule | Status |
|---|---|---|---|---|---|---|
| V4-001 | V3.3.3 与 V4 长期并存 | BASELINE | — | V4-002, V4-003 | Root baseline task. | COMPLETE |
| V4-002 | 定义 V4 Next Generation 技术定位 | BASELINE | V4-001 | — | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-003 | V3.3.3 Architecture Inventory | BASELINE | V4-001 | V4-004 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-004 | Architecture Blueprint 1.0 | BASELINE | V4-003 | V4-005 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-005 | Constitution 1.0 | BASELINE | V4-004 | V4-006, V4-007, V4-008 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-006 | Versioning Standard | BASELINE | V4-005 | V4-007, V4-008 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-007 | Production / Shadow / Experiment Boundary | BASELINE | V4-005, V4-006 | V4-008 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-008 | Data Contract 1.0 | BASELINE | V4-005, V4-006, V4-007 | V4-009 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-009 | Canonical Data Model 1.0 | BASELINE | V4-008 | V4-010 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-010 | Database Schema Blueprint 1.0 | BASELINE | V4-009 | V4-011 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-011 | Database Migration Design 1.0 | BASELINE | V4-010 | V4-012 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-012 | Migration Dry-Run & Validation Harness Design 1.0 | BATCH-01 | V4-011 | V4-013 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-013 | V4-013｜Migration Dry-Run Harness Implementation 1.0 | BATCH-02 | V4-012 | V4-014, V4-015 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-014 | V4-014｜Migration Preflight & Schema-Diff Validator 1.0 | BATCH-02 | V4-013 | V4-016 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-015 | V4-015｜Migration Smoke, RLS & Trigger Test Suite 1.0 | BATCH-02 | V4-013 | V4-016 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-016 | V4-016｜Staging Readiness & Disposable Target Contract 1.0 | BATCH-03 | V4-014, V4-015 | V4-017 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-017 | V4-017｜Migration Acceptance Package & Roll-forward Drill 1.0 | BATCH-03 | V4-016 | V4-018 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-018 | V4-018｜Formal Supabase Schema Apply HARD_GATE 1.0 | BATCH-04 | V4-017 | V4-019 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-019 | V4-019｜Production Database Write Activation HARD_GATE 1.0 | BATCH-04 | V4-018 | V4-020 | Consumes accepted upstream contract and preserves its identity/hash. | COMPLETE |
| V4-020 | V4-020｜Canonical Match Identity & Schedule Intake 1.0 | BATCH-05 | V4-019 | V4-021, V4-022, V4-023 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-021 | V4-021｜Canonical Fact Envelope & Availability Semantics 1.0 | BATCH-05 | V4-020 | V4-022, V4-023, V4-038, V4-050 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-022 | V4-022｜Cutoff, Timestamp & Provenance Lineage 1.0 | BATCH-05 | V4-020, V4-021 | V4-023, V4-038, V4-050, V4-076 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-023 | V4-023｜Canonical Intake Orchestrator & Deduplication 1.0 | BATCH-05 | V4-020, V4-021, V4-022 | V4-024, V4-025, V4-028, V4-029, V4-030, V4-032 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-024 | V4-024｜Official Lottery Five-Market Feed Adapter 1.0 | BATCH-06 | V4-023 | V4-026, V4-027 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-025 | V4-025｜Official Screenshot Intake & OCR Verification 1.0 | BATCH-06 | V4-023 | V4-026, V4-027 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-026 | V4-026｜Official Market Availability & Missingness Gate 1.0 | BATCH-06 | V4-024, V4-025 | V4-027 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-027 | V4-027｜Official Odds Timestamp & Provenance Ledger 1.0 | BATCH-06 | V4-024, V4-025, V4-026 | V4-038, V4-046, V4-050 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-028 | V4-028｜External European 1X2 Intake 1.0 | BATCH-07 | V4-023 | V4-031 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-029 | V4-029｜External Asian Handicap Intake 1.0 | BATCH-07 | V4-023 | V4-031 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-030 | V4-030｜External O/U Intake 1.0 | BATCH-07 | V4-023 | V4-031 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-031 | V4-031｜External Source-Time Normalization 1.0 | BATCH-07 | V4-028, V4-029, V4-030 | V4-038, V4-046, V4-050 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-032 | V4-032｜Team Context Intake & Identity Linker 1.0 | BATCH-08 | V4-023 | V4-033, V4-034, V4-035 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-033 | V4-033｜Availability, Injury & Suspension Intake 1.0 | BATCH-08 | V4-032 | — | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-034 | V4-034｜Lineup, Coach & Tactical Context Intake 1.0 | BATCH-08 | V4-032 | V4-036 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-035 | V4-035｜Schedule, Travel, Weather & Pitch Context Intake 1.0 | BATCH-08 | V4-032 | — | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-036 | V4-036｜Evidence Graph Claim & Evidence Model 1.0 | BATCH-09 | V4-034 | V4-037 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-037 | V4-037｜Source Quality, Expiry & Conflict Resolver 1.0 | BATCH-09 | V4-036 | V4-038, V4-049, V4-050 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-038 | V4-038｜Feature Bundle Contract & Version Registry 1.0 | BATCH-10 | V4-021, V4-022, V4-027, V4-031, V4-037 | V4-039, V4-076 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-039 | V4-039｜Feature Snapshot Hash & Reproducibility 1.0 | BATCH-10 | V4-038 | V4-040, V4-076 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-040 | V4-040｜Feature Assembly & Schema Adapter Layer 1.0 | BATCH-10 | V4-039 | V4-041, V4-042, V4-044, V4-046, V4-049 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-041 | V4-041｜Dynamic Team Rating Feature Engine 1.0 | BATCH-11 | V4-040 | V4-043, V4-052, V4-053, V4-054, V4-055, V4-056 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-042 | V4-042｜Attack, Defence & Home Advantage Model 1.0 | BATCH-11 | V4-040 | V4-043, V4-052, V4-053, V4-054, V4-055, V4-056 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-043 | V4-043｜Opponent Adjustment, Form Decay & League Strength 1.0 | BATCH-11 | V4-041, V4-042 | V4-044, V4-052, V4-053, V4-054, V4-055, V4-056 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-044 | V4-044｜Football Intelligence Engine 4.0 1.0 | BATCH-12 | V4-040, V4-043 | V4-045, V4-052, V4-053, V4-054, V4-055, V4-067 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-045 | V4-045｜Football Context Feature Integration 1.0 | BATCH-12 | V4-044 | V4-049, V4-052, V4-053, V4-054, V4-055, V4-067 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-046 | V4-046｜Market Intelligence Engine 4.0 1.0 | BATCH-13 | V4-040, V4-027, V4-031 | V4-047, V4-048, V4-052, V4-053, V4-054, V4-055 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-047 | V4-047｜Market Movement, Velocity & Divergence Features 1.0 | BATCH-13 | V4-046 | V4-048, V4-052, V4-053, V4-054, V4-055 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-048 | V4-048｜Market Heat & Trap-Risk Interpretation 1.0 | BATCH-13 | V4-046, V4-047 | V4-052, V4-053, V4-054, V4-055 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-049 | V4-049｜Tactical Matchup & League Profile Features 1.0 | BATCH-14 | V4-040, V4-045, V4-037 | V4-051, V4-052, V4-053, V4-054, V4-055 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-050 | V4-050｜Data Quality Engine 4.0 1.0 | BATCH-14 | V4-021, V4-022, V4-027, V4-031, V4-037 | V4-051, V4-052, V4-053, V4-054, V4-055 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-051 | V4-051｜Provenance & Quality Gate Enforcement 1.0 | BATCH-14 | V4-049, V4-050 | V4-052, V4-053, V4-054, V4-055, V4-072 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-052 | V4-052｜Outcome Engine 4.0 1.0 | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | V4-056, V4-065, V4-068, V4-069, V4-073, V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-053 | V4-053｜Handicap Engine 4.0 1.0 | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | V4-069, V4-073, V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-054 | V4-054｜Goals Engine 4.0 1.0 | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | V4-056, V4-069, V4-073, V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-055 | V4-055｜HTFT Engine 4.0 1.0 | BATCH-15 | V4-041, V4-042, V4-043, V4-044, V4-045, V4-046, V4-047, V4-048, V4-049, V4-050, V4-051 | V4-069, V4-073, V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-056 | V4-056｜Dynamic Lambda Engine 4.0 1.0 | BATCH-16 | V4-041, V4-042, V4-043, V4-052, V4-054 | V4-057, V4-058, V4-059, V4-065 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-057 | V4-057｜Score Distribution Candidate Ensemble 4.0 | BATCH-16 | V4-056 | V4-058, V4-059, V4-062 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-058 | V4-058｜Score Variance, Correlation, BTTS & Clean Sheet Layer 4.0 | BATCH-16 | V4-056, V4-057 | V4-059 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-059 | V4-059｜Score Distribution Interface Validation 4.0 | BATCH-16 | V4-056, V4-057, V4-058 | V4-060, V4-062, V4-065 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-060 | V4-060｜Score Matrix 4.0 | BATCH-17 | V4-059 | V4-061 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-061 | V4-061｜Score Candidate Generator 4.0 | BATCH-17 | V4-060 | V4-062 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-062 | V4-062｜Score Re-ranker 4.0 | BATCH-17 | V4-057, V4-059, V4-061 | V4-063, V4-064 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-063 | V4-063｜Exact Score Selector 4.0 | BATCH-17 | V4-062 | V4-064 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-064 | V4-064｜Scenario Diversity Selector 4.0 | BATCH-17 | V4-062, V4-063 | V4-069, V4-073, V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-065 | V4-065｜Match Simulation Engine 1.0 | BATCH-18 | V4-052, V4-056, V4-059 | V4-066, V4-067, V4-068, V4-069, V4-071 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-066 | V4-066｜Simulation Reproducibility & Performance Harness 1.0 | BATCH-18 | V4-065 | — | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-067 | V4-067｜Match Script Engine 4.0 1.0 | BATCH-18 | V4-044, V4-045, V4-065 | V4-068 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-068 | V4-068｜Upset Engine 4.0 1.0 | BATCH-18 | V4-052, V4-065, V4-067 | V4-069, V4-072 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-069 | V4-069｜Cross-Model Consensus Engine 4.0 1.0 | BATCH-19 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-065, V4-068 | V4-070, V4-071, V4-072, V4-073 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-070 | V4-070｜Model Disagreement Index 1.0 | BATCH-19 | V4-069 | V4-071, V4-072, V4-073 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-071 | V4-071｜Uncertainty Engine 4.0 1.0 | BATCH-19 | V4-069, V4-070, V4-065 | V4-072 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-072 | V4-072｜Risk & Abstention Engine 4.0 1.0 | BATCH-19 | V4-069, V4-070, V4-071, V4-068, V4-051 | V4-075 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-073 | V4-073｜Prediction Consistency Engine 1.0 | BATCH-19 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-069, V4-070 | V4-074 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-074 | V4-074｜Five-Market Orchestrator 4.0 1.0 | BATCH-20 | V4-052, V4-053, V4-054, V4-055, V4-064, V4-073 | V4-075 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-075 | V4-075｜Final Prediction Gate 4.0 1.0 | BATCH-20 | V4-074, V4-072 | V4-076 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-076 | V4-076｜Frozen Input & Immutable Lineage 4.0 1.0 | BATCH-20 | V4-022, V4-038, V4-039, V4-075 | V4-077 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-077 | V4-077｜Frozen Prediction & Revision Chain 4.0 1.0 | BATCH-20 | V4-076 | V4-078, V4-079, V4-085, V4-090 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-078 | V4-078｜Official Result Intake 1.0 | BATCH-21 | V4-077 | V4-079, V4-086 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-079 | V4-079｜Postmatch Review Engine 4.0 1.0 | BATCH-21 | V4-077, V4-078 | V4-080, V4-081, V4-082, V4-086 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-080 | V4-080｜Model Evaluation & Match Explanation Separation 1.0 | BATCH-21 | V4-079 | V4-081 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-081 | V4-081｜Error Attribution Engine 1.0 | BATCH-21 | V4-079, V4-080 | V4-082 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-082 | V4-082｜Calibration Engine & Reliability Metrics 1.0 | BATCH-22 | V4-079, V4-081 | V4-083, V4-084, V4-088 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-083 | V4-083｜League Profiles & Sample Quality 1.0 | BATCH-22 | V4-079, V4-081 | V4-084 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-084 | V4-084｜Regression Suite & Performance Benchmarks 1.0 | BATCH-22 | V4-082, V4-083 | V4-085, V4-088 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-085 | V4-085｜Forward Shadow Pair Infrastructure 1.0 | BATCH-23 | V4-077, V4-084 | V4-086, V4-098 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-086 | V4-086｜V4 Tier A Qualification Contract 1.0 | BATCH-23 | V4-085, V4-078, V4-079 | V4-087, V4-088 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-087 | V4-087｜Forward Sample Registration Interface 1.0 | BATCH-23 | V4-086 | V4-089, V4-098 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-088 | V4-088｜Cross-Version Benchmark V3.3.3 vs V4 1.0 | BATCH-24 | V4-082, V4-084, V4-086 | V4-089, V4-090, V4-095, V4-097 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-089 | V4-089｜Promotion Evaluation Evidence Package 1.0 | BATCH-24 | V4-088, V4-087 | V4-097, V4-098 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-090 | V4-090｜Public Read Projection 1.0 | BATCH-25 | V4-077, V4-088 | V4-091, V4-094, V4-100 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-091 | V4-091｜Canonical Data Center API 1.0 | BATCH-25 | V4-090 | V4-092, V4-094 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-092 | V4-092｜Public UI, Data Center & Prediction Pages 1.0 | BATCH-26 | V4-091 | V4-093, V4-100 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-093 | V4-093｜Observability, PostHog & Web Vitals 1.0 | BATCH-26 | V4-092 | V4-094, V4-100 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-094 | V4-094｜Caching & Compute Once Read Many 1.0 | BATCH-26 | V4-090, V4-091, V4-093 | V4-095, V4-097 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-095 | V4-095｜Security Hardening & Audit Integrity 1.0 | BATCH-27 | V4-088, V4-094 | V4-096, V4-097 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-096 | V4-096｜Disaster Recovery, Release Candidate & Operator Runbook 1.0 | BATCH-27 | V4-095 | V4-097 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-097 | V4-097｜End-to-End Dry Run & Production Readiness Review HARD_GATE 1.0 | BATCH-27 | V4-095, V4-096, V4-088, V4-089, V4-094 | V4-098, V4-099 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-098 | V4-098｜Shadow-Only Pilot & Promotion Review HARD_GATE 1.0 | BATCH-28 | V4-097, V4-085, V4-087, V4-089 | V4-099 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-099 | V4-099｜Production Activation & Rollback HARD_GATE 1.0 | BATCH-29 | V4-098, V4-097 | V4-100 | Consumes accepted upstream contract and preserves its identity/hash. | TODO |
| V4-100 | V4-100｜Final Production Release, Canonical Pointer Switch & Post-Release Closure HARD_GATE 1.0 | BATCH-30 | V4-099, V4-090, V4-092, V4-093 | — | Consumes accepted upstream contract and preserves its identity/hash. | TODO |

## 3. Batch-level dependency register

| Batch | Upstream Batches | Primary Tasks | Gate Notes |
|---|---|---|---|
| BATCH-01 | V4-011 | V4-012 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-02 | BATCH-01 | V4-013–V4-015 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-03 | BATCH-02 | V4-016–V4-017 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-04 | BATCH-03 | V4-018–V4-019 | COMPLETE under explicit approval and final Production verification. |
| BATCH-05 | BATCH-04 | V4-020–V4-023 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-06 | BATCH-05 | V4-024–V4-027 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-07 | BATCH-05 | V4-028–V4-031 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-08 | BATCH-05 | V4-032–V4-035 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-09 | BATCH-08 | V4-036–V4-037 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-10 | BATCH-06, BATCH-07, BATCH-09 | V4-038–V4-040 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-11 | BATCH-10 | V4-041–V4-043 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-12 | BATCH-10 | V4-044–V4-045 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-13 | BATCH-06, BATCH-07, BATCH-10 | V4-046–V4-048 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-14 | BATCH-09, BATCH-10, BATCH-12 | V4-049–V4-051 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-15 | BATCH-11, BATCH-12, BATCH-13, BATCH-14 | V4-052–V4-055 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-16 | BATCH-11, BATCH-15 | V4-056–V4-059 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-17 | BATCH-16 | V4-060–V4-064 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-18 | BATCH-15, BATCH-16, BATCH-17 | V4-065–V4-068 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-19 | BATCH-15, BATCH-17, BATCH-18 | V4-069–V4-073 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-20 | BATCH-19 | V4-074–V4-077 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-21 | BATCH-20 | V4-078–V4-081 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-22 | BATCH-21 | V4-082–V4-084 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-23 | BATCH-20, BATCH-22 | V4-085–V4-087 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-24 | BATCH-22, BATCH-23 | V4-088–V4-089 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-25 | BATCH-20, BATCH-24 | V4-090–V4-091 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-26 | BATCH-25 | V4-092–V4-094 | Ordinary dependency edge; child acceptance remains independent. |
| BATCH-27 | BATCH-24, BATCH-25, BATCH-26 | V4-095–V4-097 | Gate-bearing; separate approval required. |
| BATCH-28 | BATCH-23, BATCH-24, BATCH-27 | V4-098 | Gate-bearing; separate approval required. |
| BATCH-29 | BATCH-28 | V4-099 | Gate-bearing; separate approval required. |
| BATCH-30 | BATCH-25, BATCH-26, BATCH-29 | V4-100 | Gate-bearing; separate approval required. |

## 4. Cycle audit

- Task nodes: `100`; task edges are derived from the upstream column above.
- Kahn-style topological processing removes all 100 nodes with no residual edges.
- Batch nodes: `30`; every batch edge points to a later topological position.
- Residual nodes after processing: `0`. Dependency cycles: `0`.
- Primary assignment conflicts: `0`; every V4-012–V4-100 task appears in one and only one primary batch.

Topological task/batch order is documented in `docs/V4_DEPENDENCY_GRAPH_012_100.md`. The register contains no execution result and cannot authorize BATCH-01.
