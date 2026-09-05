# JCFB V4 Prediction Fusion Governance 1.0

Status: **BATCH-15 ARCHITECTURE GOVERNANCE / ACTIVE / IMPLEMENTATION NOT STARTED**
Contract version: `prediction-fusion@1.0.0`

## 1. Boundary

Upstream BATCH-11 statistical, BATCH-12 football/context, BATCH-13 market,
and BATCH-14 tactical/quality artifacts remain independent and immutable by
reference under `SEPARATE_DIMENSIONS_ONLY`. BATCH-15 does not create a
feature-layer composite score.

`DECLARED_MODEL_FUSION_ONLY` is the first permitted cross-domain policy. A
registered Prediction Model may consume multiple domains only when its model
manifest declares the exact feature schema, feature list, normalization,
parameters, and artifact hashes. This is model-owned fusion, not manual
arithmetic in the engine.

The following are forbidden unless encoded by an approved versioned model
artifact: Statistical 40% / Football 30% / Market 30%, tactical bonus,
quality penalty, arbitrary source weight, or hand-authored logistic
coefficient.

## 2. Lineage rule

Every cross-domain input is retained as an independent ref/hash in Frozen
Input and Engine Output. Fusion cannot overwrite source features, gate states,
or raw engine outputs. Consensus and risk are downstream layers and cannot
retroactively change an engine probability.
