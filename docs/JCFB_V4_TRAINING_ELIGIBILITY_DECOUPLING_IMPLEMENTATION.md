# JCFB V4 Training Eligibility Decoupling Implementation

Implementation identity: `MODEL_TRAINING_MINIMUM_FEATURE_SET@2.0.0` / `TRAINING_ELIGIBILITY_GATE@2.0.0`.

The active historical-training path is versioned and additive. The prior EWP-004 contract remains readable as its historical revision. The new path does not modify the prediction-time Feature Bundle or Batch-14 full-readiness semantics.

## Contract separation

| Layer | Active rule |
|---|---|
| `PREDICTION_TIME_FULL_READINESS` | Existing Feature Bundle + Batch-14 full gate; unchanged |
| `MODEL_TRAINING_MINIMUM_FEATURE_SET@2.0.0` | As-of reconstructible minimum features, required-field fail-closed, explicit availability masks |
| `INFERENCE_TIME_RICHER_OVERLAY` | Tactical, lineup, external market and context overlays may be absent and masked; base feature vector mutation is forbidden |

Tactical is optional and availability-aware. It is not a mandatory numeric training feature, and this implementation does not create tactical strength scores, multipliers, or league adjustments.

## Native market alignment

| Engine | Mandatory market core |
|---|---|
| OUTCOME | Official SPF H/D/A |
| HANDICAP | Official RQSPF handicap value plus H/D/A odds; `home_minus_away` |
| GOALS | Official Total Goals 0/1/2/3/4/5/6/7+ vector |
| HTFT | Official HTFT nine-state vector |

Exact Score and all external markets remain outside the minimum path.

## Runtime behavior

The dataset builder keeps `PREDICTION_FULL_READINESS` as its default compatibility mode. `MODEL_TRAINING_MINIMUM_FEATURE_SET` is explicit and uses only minimum feature provenance, canonical identity, cutoff binding, native market refs, post-match label separation, temporal/no-leakage checks, and deterministic reconstruction metadata. Each candidate/engine receives an independent append-only `TRAINING_GATE_RECORD@2.0.0`; it is never represented as a Batch-14 production gate.

Required features must have `AVAILABLE`, numeric value, `source_availability_at`, `information_time`, source refs/hashes, reconstruction rule/version/hash, and an explicit missingness mask. `UNAVAILABLE`/`UNKNOWN` are retained in the gate record; they cannot be silently replaced by zero, mean, default, or another observation. Missing optional overlays only set a mask.

The active rerun is intentionally pre-fit: no EWP-005 authorization, model training, parameter/model artifacts, registry writes, V3.3.3 use, Production, Supabase, public, or migration changes are part of this implementation.
