# JCFB V4.0 Project Charter

Status: V4-002 ARTIFACT VALIDATED; INITIAL COMMIT BLOCKED

## Formal definition

JCFB V4.0
Next-Generation Football Prediction System

V4 is an independent research-to-production system for football prediction. Its purpose is to make evidence, model boundaries, uncertainty, freezing, and post-match learning explicit and auditable. It is not defined as a simple hit-rate optimization exercise.

## Core objective

Build a traceable pipeline in which time-bounded objective data is transformed into independent football and market intelligence, multiple model judgments, score distributions, simulation results, consensus, uncertainty, a final prediction, a frozen prediction, and post-match learning.

```text
Data
  ↓
Football Intelligence
  ↓
Market Intelligence
  ↓
Independent Prediction Engines
  ↓
Score Distribution
  ↓
Match Simulation
  ↓
Cross-Model Consensus
  ↓
Uncertainty / Risk
  ↓
Final Prediction
  ↓
Freeze
  ↓
Postmatch Learning
```

## Target capabilities

The eventual V4 system is expected to provide:

- Independent judgments from multiple models
- Independent models for the five official market types
- An independent Score Engine
- Market Intelligence
- Team Intelligence
- Tactical Matchup analysis
- Match Simulation
- Consensus Engine
- Disagreement Index
- Uncertainty Engine
- Upset Engine
- Calibration
- Frozen Prediction
- Shadow Experiment support
- Tier A Qualification
- Error Attribution
- V3.3.3 vs V4 Benchmarking

These are target capabilities, not claims that the bootstrap repository already implements them.

## Design principles

1. Independence: V4 code, configuration, outputs, and parameters are separate from V3.3.3.
2. Time integrity: a pre-match run may use only information available by its declared cutoff.
3. Provenance: objective facts and odds require source, timestamp, identity, and integrity metadata.
4. Explicit availability: unavailable markets are recorded as unavailable; missing odds are never fabricated.
5. Reproducibility: model runs are designed to support model, implementation, configuration, input, and output hashes.
6. Controlled promotion: experiments and shadow results cannot affect Production without a formal Promotion Gate.
7. Honest status: unfinished work is recorded as `UNKNOWN`, `BLOCKED`, or `NOT_IMPLEMENTED`.

## Bootstrap scope and non-goals

V4-001 through V4-003 establish coexistence policy, technical positioning, the legacy architecture inventory, repository governance, and the engineering skeleton.

This bootstrap does not implement a Score Engine, Prediction Engine, Supabase schema, Production Model, Shadow Model, historical import, V3.3.3 migration, or V4-004 Architecture Blueprint 1.0.

## Delivery gates

Each future build item requires all five forms of evidence:

1. Design finalized
2. Engineering artifact exists
3. Validation completed
4. Documentation completed
5. Git traceability exists
