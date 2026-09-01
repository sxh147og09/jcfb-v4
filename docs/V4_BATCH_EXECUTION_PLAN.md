# JCFB V4 Batch Execution Plan 1.0

Status: V4-012–V4-100 PLANNING AUDIT BLOCKED (SOURCE TASK REGISTER INCOMPLETE)

Plan Identity: `v4-batch-execution-plan@1.0.0`

Plan Revision: `r001`

Audit Date: `2026-09-01` (`Asia/Shanghai`)

Source Repository Revision: `fa6a38d` (`main`)

Execution Declaration: **NO V4-012+ TASK EXECUTED**

## 1. Purpose and decision

This document defines a candidate batch execution plan for the work intended after V4-011. It is a planning artifact only. It does not execute V4-012, create a migration harness, contact Supabase, write a database, run a model, run Shadow, publish Production, or modify JCFB V3.3.3.

The audit found a source-register defect that prevents a truthful completed mapping:

- `docs/V4_MASTER_BUILD_CHECKLIST.md` contains checklist tasks V4-001 through V4-011 only.
- The repository-wide non-Git search found `V4-012` references, but no original task entries for V4-013 through V4-100.
- Reachable Git history, branches, and tags contain no V4-013 through V4-100 task register.
- The referenced `docs/V4_RUNTIME_BOUNDARY.md` does not exist; the current governed runtime document is `docs/V4_RUNTIME_ROLE_BOUNDARY.md`.

Therefore:

- V4-012 is the only future task whose name is verified from repository evidence: `Migration Dry-Run & Validation Harness Design 1.0`.
- V4-013 through V4-100 remain `UNRESOLVED` and `UNASSIGNED`; no invented task names or labels are treated as complete evidence.
- Thirty candidate batch envelopes are documented below so the intended engineering shape is preserved, but they are not an approved task-to-batch mapping.
- The plan cannot be declared complete and V4-012 must not start until the authoritative V4-012–V4-100 task register is restored or supplied.

## 2. Authority and non-negotiable boundaries

The governing order is:

1. `docs/V4_CONSTITUTION.md`.
2. `docs/V4_VERSIONING_STANDARD.md` and the linked V4 identity/compatibility contracts.
3. `docs/V4_ARCHITECTURE_BLUEPRINT.md` and `docs/V4_RUNTIME_ROLE_BOUNDARY.md`.
4. `docs/V4_DATA_CONTRACT.md` and `docs/V4_CANONICAL_DATA_MODEL.md`.
5. `docs/V4_DATABASE_SCHEMA_BLUEPRINT.md` and `docs/V4_DATABASE_MIGRATION_DESIGN.md`.
6. This planning artifact and its companion audit documents.

No batch may weaken these rules for speed. In particular:

- V3.3.3 remains an independent protected model line. Only an approved objective-facts read path may ever be shared.
- Blueprint SQL and candidate migration files remain design-only until a dedicated Human Approver gate authorizes an exact deployment.
- Production DB Migration Apply, Supabase Schema Apply, Production Model Activation, Promotion, historical Frozen Prediction integrity changes, and Public Production Release are gate-only actions.
- A batch label never changes a checklist state. Every subtask still requires its own evidence and PASS result.
- `UNKNOWN`, `UNAVAILABLE`, `BLOCKED`, `NOT_VERIFIED`, and `NOT_IMPLEMENTED` remain explicit; the missing task register is not filled with guesses.

## 3. Candidate batch register

The following 30 rows are candidate envelopes, not a claim that 30 verified task groups exist. `UNASSIGNED` means that the source task register is absent, not that the work is approved to begin.

| Batch ID | Included V4 Task IDs | Batch Name | Classification | Upstream Dependencies | Can Run In Parallel? | Hard Gate? | Deliverables | Acceptance Criteria | Git Strategy | Supabase Write Allowed? | Production/Shadow Execution Allowed? | Rollback / Stop Condition | Next Batch Dependency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BATCH-01 | `V4-012` (verified name only) | Migration Dry-Run & Validation Harness | `BATCHABLE + SERIAL` | V4-011 | PARTIAL; design interfaces may be split, but no target execution | NO | Future harness design, disposable-target contract, runner/report interfaces | V4-012 artifact is complete, target is disposable or isolated, no real DB write occurs, and every design gate is evidenced | One focused commit per accepted child artifact; no code execution in this audit | NO | NO | Stop on any attempt to connect to or write a real database; preserve `NOT_STARTED` | BATCH-02 |
| BATCH-02 | `UNASSIGNED (source register missing; no task IDs assigned)` | Preflight / Smoke / Constraint / RLS / Trigger Test Harness | `BATCHABLE + PARALLEL + SERIAL` | BATCH-01 | YES inside the harness after a frozen manifest | NO | Preflight runner, smoke cases, constraint/RLS/trigger test interfaces, evidence schema | Each child test is independently runnable, negative cases fail closed, and no test result is fabricated | Keep test and documentation changes traceable by child task; no checklist cascade | NO | NO | Stop on missing target identity, missing role context, or any destructive fixture | BATCH-03 |
| BATCH-03 | `UNASSIGNED (source register missing; no task IDs assigned)` | Database Deployment Readiness | `BATCHABLE + SERIAL` | BATCH-02 | NO; readiness is a single reviewed package | NO | Target identity form, extension/privilege review, backup decision, immutable manifest, deployment runbook | All critical preflight fields are PASS or explicitly BLOCKED; unresolved items cannot be treated as ready | Documentation-only commit with manifest hash placeholder until canonical bytes are frozen | NO | NO | Any unresolved critical decision blocks the package; no retry or implicit default | BATCH-04 |
| BATCH-04 | `UNASSIGNED (source register missing; no task IDs assigned)` | Production DB Migration Apply / Supabase Schema Apply | `SERIAL + HARD_GATE` | BATCH-03 | NO | YES | Approved migration manifest, Human Approver record, executor result, catalog diff, migration history, smoke evidence | Exact approved files and hashes match, all gates pass, history is recorded, and explicit approval exists before write | Separate gate commit for evidence only; never mix with ordinary implementation | YES, only after explicit Human Approver authorization | NO model or Shadow execution; schema apply is the only authorized action | Stop on first failure; do not continue, retry by identity, delete data, or edit an applied migration; use a new forward migration | BATCH-05 |
| BATCH-05 | `UNASSIGNED (source register missing; no task IDs assigned)` | Canonical Data Intake Pipeline | `BATCHABLE + SERIAL` | BATCH-04 | PARTIAL; identity, provenance, and quality components can be developed independently | NO | Canonical match identity, source envelope, time/availability gates, quality blockers, read-path contracts | Facts are typed, timestamped, provenance-preserving, no future information enters, and missing values remain explicit | Separate data-contract and pipeline commits; no historical import without a gate | NO under this plan | NO | Stop on identity conflict, future leakage, fabricated official odds, or any V3.3.3 access beyond an approved read contract | BATCH-06, BATCH-07, BATCH-08 |
| BATCH-06 | `UNASSIGNED (source register missing; no task IDs assigned)` | Official Odds Intake | `BATCHABLE + PARALLEL` | BATCH-05 | YES with BATCH-07 and BATCH-08 after canonical identity exists | NO | Official five-market snapshots, market availability, cutoff validation, odds provenance | SPF, RQSPF, Total Goals, Exact Score, and Half-Full remain official-only and may be `AVAILABLE` or `UNAVAILABLE` | One focused commit for intake contract/validator; keep source and model boundaries separate | NO | NO | Stop on missing official market, unverifiable timestamp, or external odds relabeled as official | BATCH-10 |
| BATCH-07 | `UNASSIGNED (source register missing; no task IDs assigned)` | External Market Intake | `BATCHABLE + PARALLEL` | BATCH-05 | YES with BATCH-06 and BATCH-08 | NO | External-market snapshots, movement features, source isolation, trap-risk signal contract | External data never overwrites or changes official odds identity; timestamps and uncertainty are retained | Separate commit from official odds work; no model output in the intake change | NO | NO | Stop on source ambiguity, future timestamp, or accidental official/external field collision | BATCH-10 |
| BATCH-08 | `UNASSIGNED (source register missing; no task IDs assigned)` | Team Context Intake | `BATCHABLE + PARALLEL` | BATCH-05 | YES with BATCH-06 and BATCH-07 | NO | Time-valid team context, availability, lineup/evidence references, conflict states | Context is evidence-backed, cutoff-valid, and never silently turns `UNKNOWN` into a negative fact | Separate context/evidence commits; corrections append new revisions | NO | NO | Stop on unsupported lineup/injury claims, post-cutoff data, or unresolved identity conflict | BATCH-09 and BATCH-10 |
| BATCH-09 | `UNASSIGNED (source register missing; no task IDs assigned)` | Evidence Graph | `BATCHABLE + PARALLEL` | BATCH-08 | PARTIAL; claim, source, contradiction, and expiry components can split | NO | Claim/evidence graph, evidence hashes, contradiction and expiry states | Every trusted context claim points to evidence, has lifecycle timestamps, and preserves contradiction state | Commit evidence schema and graph logic separately from feature consumers | NO | NO | Stop on unsupported claim promotion, silent contradiction removal, or missing provenance | BATCH-10 |
| BATCH-10 | `UNASSIGNED (source register missing; no task IDs assigned)` | Feature Representation Layer | `BATCHABLE + SERIAL` | BATCH-06, BATCH-07, BATCH-09 | NO across the assembled bundle; component serializers may be parallel | NO | Versioned statistical, football, market, tactical, quality, and score feature bundles | Bundles are typed, reproducible, hashable, cutoff-valid, and consumed through a versioned interface | One contract commit plus independently traceable component commits | NO | NO | Stop on feature leakage, missing required identity/hash, or incompatible contract change | BATCH-11, BATCH-12, BATCH-13, BATCH-14 |
| BATCH-11 | `UNASSIGNED (source register missing; no task IDs assigned)` | Statistical Feature Engines | `BATCHABLE + PARALLEL` | BATCH-10 | YES with BATCH-12 to BATCH-14 | NO | Dynamic ratings, attack/defence, home advantage, opponent adjustment, decay, league strength | Time-valid, sample-size-aware, opponent-adjusted features with version/hash lineage; no post-match leakage | Component-level commits with locked config identity and tests | NO | NO | Stop on leakage, unversioned weights, or a behavior change hidden under the same identity | BATCH-15 |
| BATCH-12 | `UNASSIGNED (source register missing; no task IDs assigned)` | Football Feature Engines | `BATCHABLE + PARALLEL` | BATCH-10 | YES with BATCH-11, BATCH-13, BATCH-14 | NO | Form, strength, availability, coach, tactics, fatigue, travel, weather, pitch features | Features remain interpretation-layer outputs with evidence/confidence and never become objective facts or final markets | Separate feature engine commit; no prediction output in this batch | NO | NO | Stop on unsupported interpretation, future context, or silent default | BATCH-15 |
| BATCH-13 | `UNASSIGNED (source register missing; no task IDs assigned)` | Market Feature Engines | `BATCHABLE + PARALLEL` | BATCH-06, BATCH-07, BATCH-10 | YES with BATCH-11, BATCH-12, BATCH-14 | NO | Movement, velocity, compression/expansion, divergence, heat, liquidity, risk indicators | Market interpretation retains uncertainty and never asserts bookmaker intent as fact | Separate market-feature commit; source identity and official/external boundary tested | NO | NO | Stop on market-source collision, future snapshot, or risk signal promoted to certainty | BATCH-15 |
| BATCH-14 | `UNASSIGNED (source register missing; no task IDs assigned)` | Tactical / Quality Feature Engines | `BATCHABLE + PARALLEL` | BATCH-08, BATCH-09, BATCH-10 | YES with BATCH-11 to BATCH-13 | NO | Tactical matchup, context quality, data quality, source confidence, blockers | Quality gates are explicit; uncertainty can block downstream work; no silent default or fabricated context | Separate quality/tactical commits with contract-level tests | NO | NO | Stop on critical quality blocker, missing evidence, or no-future gate failure | BATCH-15 |
| BATCH-15 | `UNASSIGNED (source register missing; no task IDs assigned)` | Core Prediction Engines: Outcome / Handicap / Goals / HTFT | `BATCHABLE + PARALLEL + SERIAL` | BATCH-11, BATCH-12, BATCH-13, BATCH-14 | YES among independent engines after the shared input contract passes | NO | Independent Outcome, Handicap, Goals, and HTFT engine outputs with hashes | Each engine preserves independent identity, input/output hashes, timestamp, and raw output; five-market independence is tested | Engine-by-engine commits; no consensus or selector shortcut | NO | NO | Stop on missing hashes, shared-output aliasing, or SPF mechanically producing other markets | BATCH-16 and BATCH-18 |
| BATCH-16 | `UNASSIGNED (source register missing; no task IDs assigned)` | Score Engine Part A: Lambda / Distributions / Variance / Correlation | `BATCHABLE + SERIAL` | BATCH-11, BATCH-15 | PARTIAL; distribution components can research in parallel but integration is serial | NO | Dynamic lambda inputs, goal distributions, variance/over-dispersion, correlation adjustment, score matrix contract | Exact Score originates from a distribution; candidate algorithms remain versioned research choices; raw distribution is immutable per run | Separate distribution and integration commits; no selector rewrite | NO | NO | Stop on distribution inconsistency, hidden parameter change, or outcome-to-score shortcut | BATCH-17 |
| BATCH-17 | `UNASSIGNED (source register missing; no task IDs assigned)` | Score Engine Part B: Candidate Generation / Reranker / Selector / Scenario Diversity | `BATCHABLE + SERIAL` | BATCH-16 | PARTIAL; candidate generation and selector tests can split, final integration is serial | NO | Top20 candidates, Top1/2/3/5/10 selections, reranker identity, scenario diversity | Selector only reads the approved distribution, cannot rewrite it, and preserves selector/config/output hashes | Separate selector commits; selector-version change creates new evidence | NO | NO | Stop on distribution mutation, non-diverse candidates, or hidden selector/config change | BATCH-18 and BATCH-19 |
| BATCH-18 | `UNASSIGNED (source register missing; no task IDs assigned)` | Match Simulation / Match Script / Upset | `BATCHABLE + PARALLEL` | BATCH-15, BATCH-16, BATCH-17 | YES among simulation, script, and upset components after shared input identity | NO | Replayable simulation envelope, match scripts, upset evidence and variance | Seed, run count, simulation version, input hash, and role are preserved; simulation remains independent evidence | Separate component commits and replay fixtures; no Shadow execution | NO | NO | Stop on post-match input, non-replayable randomness, or outcome-truth claims | BATCH-19 |
| BATCH-19 | `UNASSIGNED (source register missing; no task IDs assigned)` | Consensus / Disagreement / Uncertainty / Risk / Abstention / Consistency | `BATCHABLE + SERIAL` | BATCH-15, BATCH-17, BATCH-18 | PARTIAL; disagreement, uncertainty, risk, and consistency modules may be developed in parallel | NO | Raw engine votes, disagreement score, confidence separation, risk flags, abstention, cross-market consistency | Raw outputs remain visible; probability is not confidence; high conflict can lower confidence or abstain | One contract/integration commit plus component evidence; no auto-promotion | NO | NO | Stop on hidden averaging, erased disagreement, forced recommendation, or invalid confidence semantics | BATCH-20 |
| BATCH-20 | `UNASSIGNED (source register missing; no task IDs assigned)` | Final Prediction Gate / Frozen Input / Frozen Prediction | `BATCHABLE + SERIAL` | BATCH-19 | NO; gate and freeze ordering is serial | NO for design; freeze execution remains a governed operation | Gate decision, rejection reasons, Frozen Input identity/hash, immutable Frozen Prediction lineage | Identity, cutoff, odds, quality, consistency, risk, and no-future gates pass; Frozen Prediction is append-only | Separate gate contract and freeze implementation commits; no retroactive edit | NO | NO | Stop on any failed prerequisite, hash mismatch, post-kickoff completion, or attempted in-place update | BATCH-21, BATCH-23 |
| BATCH-21 | `UNASSIGNED (source register missing; no task IDs assigned)` | Official Result / Postmatch Review / Error Attribution | `BATCHABLE + SERIAL` | BATCH-20 | PARTIAL; result intake, evaluation, explanation, and attribution can split with strict boundaries | NO | Official Result, model evaluation, match explanation, review, diagnostic attribution | Result identity matches the match; evaluation uses Frozen Prediction plus Official Result; explanation cannot rewrite history | Separate result/review/diagnostic commits; correction is append-only | NO | NO | Stop on unmatched result, outcome fitting, historical overwrite, or explanation feeding pre-match data | BATCH-22 |
| BATCH-22 | `UNASSIGNED (source register missing; no task IDs assigned)` | Calibration / League Profiles / Regression Evaluation | `BATCHABLE + SERIAL` | BATCH-21 | PARTIAL; calibration, league profiles, and regression suites may run independently over frozen evidence | NO | Calibration metrics, league profiles, regression matrix, runtime/performance evidence | No cherry-picking; forward and historical samples are distinguished; changes create new versions and evidence | Evaluation-only commits with frozen dataset/version references | NO | NO | Stop on excluded failures, post-hoc parameter rewrite, or material unreviewed regression | BATCH-23 and BATCH-24 |
| BATCH-23 | `UNASSIGNED (source register missing; no task IDs assigned)` | Forward Shadow Pair / Tier A Collection Infrastructure | `BATCHABLE + SERIAL` | BATCH-20, BATCH-22 | PARTIAL; pair validator and collection infrastructure can split, actual Forward runs remain serial by evidence | NO | Pre-kickoff Shadow pairing, same `frozen_input_hash` validation, Tier A collection ledger | Shadow is truly pre-kickoff, role-separated, same-match/same-frozen-input where required, and Experiment cannot qualify | Infrastructure commits separate from any real run; no backfilled Shadow | NO | NO in this planning batch | Stop on late Shadow, hash mismatch, missing evidence, or any relabeling of Experiment as Shadow | BATCH-24 and BATCH-27 |
| BATCH-24 | `UNASSIGNED (source register missing; no task IDs assigned)` | Benchmark / Promotion Evaluation | `BATCHABLE + SERIAL` | BATCH-22, BATCH-23 | PARTIAL; benchmark metrics and promotion evidence assembly can split, review is serial | NO | Cross-version benchmark, statistical/calibration/integrity/regression/performance evidence package | V3.3.3 artifacts are read-only reference only; Forward evidence is separate from historical backtest; no auto-promotion | Evaluation evidence commit; never alter V3.3.3 or predecessor outputs | NO | NO | Stop on missing Forward samples, V3 boundary violation, cherry-picking, or incomplete evidence | BATCH-25, BATCH-27 |
| BATCH-25 | `UNASSIGNED (source register missing; no task IDs assigned)` | Public Read Projection / API / Data Center | `BATCHABLE + SERIAL` | BATCH-20, BATCH-24 | PARTIAL; read views/API/data-center components may split after canonical backend readiness | NO | Safe Production-only read projection, API contract, canonical latest-update path, data-center read surface | Public path is read-only, uses real business timestamps, exposes no Shadow/Experiment/private fields, and cannot run a model | Separate read-contract and UI-consumer commits; no release pointer switch | NO | NO publication; read surface only | Stop on unsafe field exposure, non-canonical latest time, or any client write path | BATCH-26 and BATCH-30 |
| BATCH-26 | `UNASSIGNED (source register missing; no task IDs assigned)` | UI / Observability / PostHog / Performance | `BATCHABLE + PARALLEL` | BATCH-25 | YES among UI, telemetry, and performance components after read contract is stable | NO | UI consumers, metrics, traces, PostHog events, performance budgets and alerts | UI remains read-only; telemetry excludes secrets/private payloads; performance cannot bypass integrity gates | Component commits with safe telemetry schema; no production release in this batch | NO | NO | Stop on secret/PII exposure, model execution from UI, or performance optimization that skips gates | BATCH-27 |
| BATCH-27 | `UNASSIGNED (source register missing; no task IDs assigned)` | Production Readiness & Frozen/Historical Integrity Gate | `SERIAL + HARD_GATE` | BATCH-24, BATCH-25, BATCH-26 | NO | YES | Production readiness report, rollback plan, historical integrity review, explicit decision for any Frozen Prediction/history migration | All readiness, security, integrity, backup, rollback, and public-safety evidence is PASS; any historical-data operation has its own approval record | Gate-only commit; no ordinary implementation changes mixed in | NO; approval evidence only | NO | Stop on any proposed historical overwrite, missing backup/rollback evidence, or unresolved V3 boundary | BATCH-28 |
| BATCH-28 | `UNASSIGNED (source register missing; no task IDs assigned)` | Shadow → Promotion Review | `SERIAL + HARD_GATE` | BATCH-23, BATCH-24, BATCH-27 | NO | YES | Promotion Review packet, Forward/Tier A evidence, integrity and no-future audit, reviewer decision | Human review confirms evidence, compatibility, regression, calibration, and role separation; no automatic transition | Gate-only review commit; preserve predecessor identities | NO | NO new Shadow run in the gate; review previously captured evidence only | Stop on missing Forward evidence, late Shadow, pair invalidity, or auto-promotion attempt | BATCH-29 |
| BATCH-29 | `UNASSIGNED (source register missing; no task IDs assigned)` | Promotion Review → Production / Production Model Activation | `SERIAL + HARD_GATE` | BATCH-28 | NO | YES | New immutable Production revision, activation event, predecessor/evidence links, active-pointer uniqueness proof | Explicit Human Approver authorization; one active Production revision; new identity is not a relabeled Shadow/Experiment revision | Gate-only commit and append-only activation evidence; no ordinary feature/model changes | YES only for the approved activation path | YES only after explicit approval; no Shadow/Experiment promotion shortcut | Stop on multiple active revisions, pointer mismatch, missing hashes, or any unattended activation | BATCH-30 |
| BATCH-30 | `UNASSIGNED (source register missing; no task IDs assigned)` | Public Production Release / Canonical Output Pointer Switch | `SERIAL + HARD_GATE` | BATCH-25, BATCH-26, BATCH-29 | NO | YES | Release identity, safe projection publication, canonical output pointer event, rollback target, release audit | Explicit release approval; only the approved Production output is public; pointer and business timestamps are consistent | Gate-only release commit; rollback by governed new pointer/release event, never by rewriting history | YES only for the approved release/projection path | Production release only after BATCH-29; no model compute from Public Web | Stop on unsafe projection, wrong pointer, missing audit, or inability to restore prior approved release | None; maintain incident/rollback path |

## 4. Candidate batch parallelism

The intended dependency shape is:

```text
BATCH-01 → BATCH-02 → BATCH-03 → BATCH-04(HARD_GATE)
                                      ↓
              BATCH-05 → {BATCH-06, BATCH-07, BATCH-08}
                                      ↓
                                  BATCH-09
                                      ↓
                                  BATCH-10
                                      ↓
              {BATCH-11, BATCH-12, BATCH-13, BATCH-14}
                                      ↓
                                  BATCH-15
                                      ↓
                         BATCH-16 → BATCH-17
                                      ↓
                                  BATCH-18
                                      ↓
                                  BATCH-19
                                      ↓
                                  BATCH-20
                                      ↓
                                  BATCH-21 → BATCH-22
                                      ↓
                                  BATCH-23 → BATCH-24
                                      ↓
                                  BATCH-25 → BATCH-26
                                      ↓
                       BATCH-27(HARD_GATE) → BATCH-28(HARD_GATE)
                                      ↓
                       BATCH-29(HARD_GATE) → BATCH-30(HARD_GATE)
```

This is a candidate DAG. It is not evidence that the missing source task register has these exact edges. The authoritative graph and cycle audit are in `docs/V4_DEPENDENCY_GRAPH_012_100.md`.

## 5. Batch completion and checklist behavior

The batch is a coordination unit, not a completion shortcut:

1. Each child task receives its own artifact, validation result, status, and Git evidence.
2. A child failure does not mark other children `COMPLETE` and does not permit the batch to claim full PASS.
3. A checklist checkbox is changed only after that task's completion rule is satisfied.
4. A HARD_GATE is never crossed by the batch runner or by a successful neighboring child.
5. This planning audit itself cannot authorize V4-012 execution.

## 6. Required next input

Before this plan can be accepted, restore or provide the original task register containing the exact names, scope, and intended dependencies for V4-013 through V4-100. Then rerun the classification, primary-batch uniqueness, and DAG checks. Until then, the only safe next state is:

```text
V4-012–V4-100 Batch Planning = BLOCKED
V4-012 Execution = NOT_STARTED
Supabase Write = NO
Production / Shadow Execution = NO
V3.3.3 Mutation = NO
```
