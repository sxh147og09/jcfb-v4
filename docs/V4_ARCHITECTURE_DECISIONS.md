# JCFB V4.0 Architecture Decisions

Status: V4-004 COMPLETE

This file records the architecture decisions accepted for V4-004. These decisions define boundaries and interfaces; they do not claim that the corresponding implementation exists.

## ADR-001 — V3.3.3 and V4 coexist

**Status:** ACCEPTED

**Context:** V3.3.3 is a stable independent model that must remain available while V4 is developed.

**Decision:** V3.3.3 and V4 are permanent independent model lines. V4 has its own repository-local code, configuration, model versions, predictions, Frozen Prediction, reviews, and sample qualification.

**Consequences:** V4 work cannot modify or rename V3.3.3. Long-term comparison uses shared objective facts and separate model artifacts.

## ADR-002 — Shared facts, isolated predictions

**Status:** ACCEPTED

**Context:** Both model lines need canonical match, odds, market, team, and result facts, but derived conclusions must not contaminate one another.

**Decision:** Establish a read-only Shared Objective Facts Layer. Share only canonical, timestamped, provenance-preserving objective facts. Keep predictions, model outputs, Frozen Input, Frozen Prediction, confidence, reviews, Tier A qualification, and parameters isolated.

**Consequences:** A common match identity does not imply a common feature set or prediction. Cross-version benchmarks must preserve model lineage.

## ADR-003 — Multi-engine architecture

**Status:** ACCEPTED

**Context:** One engine must not mechanically determine all five official market outputs or hide disagreement.

**Decision:** Use independent Outcome, Handicap, Goals, HTFT, Score, and Upset engines. Retain raw outputs and per-engine hashes before consensus and orchestration.

**Consequences:** Each engine requires explicit contracts, versions, configurations, inputs, outputs, and evaluation. The Five-Market Orchestrator assembles outputs only after independent runs.

## ADR-004 — Score distribution separated from selector

**Status:** ACCEPTED

**Context:** A probability distribution and the act of choosing a small displayed candidate set answer different questions.

**Decision:** Separate Dynamic Lambda, distribution ensemble, score matrix, candidate generation, reranking, scenario diversity, and exact-score selection. Candidate generation produces at least Top20; selection may expose Top1, Top2, Top3, Top5, and Top10.

**Consequences:** A selector cannot rewrite the distribution. Selector changes may later be recomputed without repeating unchanged upstream work.

## ADR-005 — Frozen Input before Frozen Prediction

**Status:** ACCEPTED

**Context:** A prediction is not reproducible if the facts, odds, features, versions, or configs used to create it can drift before freeze.

**Decision:** Create immutable `Frozen Input 4.0` before formal prediction freeze. Record match identity, exact snapshots, context, feature snapshot, model versions, engine configs, cutoff, and `frozen_input_hash`.

**Consequences:** Production, Shadow, and Experiment A/B comparisons require the same frozen input hash. A later change creates a new run rather than mutating historical input.

## ADR-006 — Simulation as independent layer

**Status:** ACCEPTED

**Context:** Match-state paths and stochastic factors add information that should not be hidden inside a single deterministic prediction engine.

**Decision:** Treat Match Simulation Engine 1.0 and Match Script Engine 4.0 as independent layers with explicit inputs and outputs. Simulation may affect consensus, reranking, scenario diversity, and risk, but cannot replace Score Distribution.

**Consequences:** Simulation run count and Production algorithm remain deferred. State transitions, variance, and scripts are separately auditable.

## ADR-007 — Consensus is not probability averaging

**Status:** ACCEPTED

**Context:** Equal averages can hide whether models agree or cancel one another.

**Decision:** Consensus retains raw engine votes, support, conflicts, and disagreement. `Cross-Model Consensus Engine 4.0` is not defined as a simple average.

**Consequences:** `Model Disagreement Index 1.0` becomes a first-class artifact. Downstream risk may abstain when apparent consensus is unstable.

## ADR-008 — Probability is not confidence

**Status:** ACCEPTED

**Context:** A model probability describes an estimated event distribution; confidence also depends on data quality, evidence, calibration, disagreement, and uncertainty.

**Decision:** Keep probability, uncertainty, confidence interval, and confidence grade as separate fields and layers. Confidence cannot be copied directly from the largest probability.

**Consequences:** Calibration and quality evidence are required before a strong confidence grade. A high probability may still lead to caution or abstention.

## ADR-009 — Explicit abstention is allowed

**Status:** ACCEPTED

**Context:** Forcing every match to produce a strong recommendation rewards overstatement and hides data or model risk.

**Decision:** Risk & Abstention Engine 4.0 may return `NO STRONG RECOMMENDATION` alongside formal risk states such as `PASS`, `CAUTION`, `ELIGIBLE`, and `HIGH_CONFIDENCE`.

**Consequences:** A missing market, blocked quality gate, high disagreement, or inadequate evidence can stop formal recommendation without being converted into a fabricated pick.

## ADR-010 — V4 Tier A starts at Sample #001

**Status:** ACCEPTED

**Context:** V3.3.3 Tier A labels and historical numbering are not valid evidence for a new model line.

**Decision:** V4 qualification restarts at `V4 Tier A Sample #001`. A candidate requires Frozen Input, required Production and Shadow evidence, pre-kickoff outputs, Official Result, no-future-leakage proof, implementation/config/input/output hashes, and a passing completeness gate.

**Consequences:** V3.3.3 Tier A samples cannot be migrated or relabeled as V4 samples. Qualification is an append-only V4-owned process.

## Decision boundary for later work

These ADRs intentionally do not select a Production Score algorithm, model parameters, database, training method, simulation run count, or promotion threshold. Those decisions require later artifacts, validation, and formal review.
