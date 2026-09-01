# JCFB V4 Prediction Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and independent-market rule

This contract defines the V4 Prediction envelope and the immutable Frozen Prediction envelope. A Prediction is an auditable assembly of independently produced market outputs, consensus, disagreement, uncertainty, and risk. It is not a raw Engine Output and it is not an Official Result.

The five official lottery markets are independently modeled:

1. SPF
2. RQSPF
3. Total Goals
4. Exact Score
5. Half-Full

The required order is `Independent Prediction First -> Consistency Check Second`. SPF output cannot mechanically generate RQSPF, Total Goals, Exact Score, or Half-Full. Exact Score selection must originate from a score probability distribution; a preferred score cannot be backfilled from an outcome label.

## 2. Prediction fields

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `prediction_id` | UUID/UUIDv7 | REQUIRED | Stable prediction identity. |
| `contract_version` | string | REQUIRED | `prediction@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 | REQUIRED | Canonical match reference. |
| `role` | enum | REQUIRED | `PRODUCTION`, `SHADOW`, or `EXPERIMENT`; never inferred. |
| `model_version` | qualified identity | REQUIRED | Exact model identity, not `latest`/`current`. |
| `prediction_revision` | immutable revision | REQUIRED | Role/model-scoped revision; revisions append-only. |
| `frozen_input_id` / `frozen_input_hash` | stable ref/hash | REQUIRED for formal prediction | Exact source boundary. Production/Shadow A/B uses the same frozen hash. |
| `engine_run_refs` | non-empty array | REQUIRED | Exact Engine Output IDs/hashes supporting each market and cross-market layer. |
| `market_predictions` | object | REQUIRED | Contains all five independent market keys, each with its own state and engine lineage. |
| `consensus` | structured object | REQUIRED | Preserves individual engine refs, support, conflicts, and score. |
| `disagreement` | structured object | REQUIRED | Numeric/graded disagreement; cannot be hidden by averaging. |
| `uncertainty` | structured object | REQUIRED | Components, interval, and grade separate from probability. |
| `risk` | structured object | REQUIRED | Risk flags and abstention state. |
| `confidence_grade` | enum | REQUIRED | `VERY_HIGH`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`, or `BLOCKED`; not a probability. |
| `recommendation_state` | enum | REQUIRED | `PASS`, `NO_STRONG_RECOMMENDATION`, `BLOCKED`, or `INSUFFICIENT_DATA`. |
| `recommendation_strength` | enum | REQUIRED | `NONE`, `WEAK`, `MODERATE`, `STRONG`, or `NOT_APPLICABLE`; separate from state and probability. |
| `created_at` | timezone-aware timestamp | REQUIRED | Prediction creation time, not source time or kickoff. |
| `prediction_hash` / `payload_hash` | SHA-256 string | REQUIRED | Hash of the logical prediction payload; must be recomputable. |
| common provenance/status fields | typed metadata | REQUIRED | Source, provenance, status, and metadata. |

## 3. Five-market payloads

Each market prediction has at least `market`, `market_state`, `engine_run_ref`, `probabilities` or a distribution, `selection` when a recommendation is made, `consistency_state`, and a market-specific `reason_codes` array. `market_state=UNAVAILABLE` is a formal availability outcome and never creates synthetic odds or a synthetic selection.

| Market | Minimum payload | Independence rule |
|---|---|---|
| `spf` | H/D/A probability distribution and optional `selection` | Uses Outcome Engine lineage; no downstream market is copied from it. |
| `rqspf` | Official handicap ref/value, handicap outcome distribution, optional selection | Must reference official RQSPF availability/handicap; external handicap cannot satisfy it. |
| `total_goals` | `0..7+` distribution, goal bands, optional selection | Uses Goals Engine lineage; does not derive from SPF. |
| `exact_score` | Score matrix reference/hash, lambda home/away references/values, BTTS/clean-sheet outputs, top candidates, optional selection | Selector reads the distribution; it cannot rewrite the matrix or infer a score from SPF. |
| `half_full` | Nine-state H/H through A/A distribution, optional selection | Uses HTFT Engine lineage; no two-stage shortcut from full-time SPF is allowed. |

`probability`, `confidence_grade`, and `recommendation_strength` have different meanings. For example, a 0.70 H probability can coexist with `confidence_grade=LOW`, `recommendation_state=NO_STRONG_RECOMMENDATION`, and `recommendation_strength=NONE`.

## 4. Consensus, disagreement, uncertainty, and risk

### 4.1 Consensus

`consensus` must include `consensus_score`, directional or market-level consensus, `votes`, `support`, `conflicts`, and `individual_engine_output_refs`. It cannot be a single average without the contributing outputs. Consensus is a downstream interpretation; it cannot overwrite raw engine outputs.

### 4.2 Disagreement

`disagreement` includes `numeric_disagreement_score`, `grade` (`LOW`, `MEDIUM`, `HIGH`, `EXTREME`), market/engine conflict refs, and a statement of how the conflict affects the gate. A high conflict may lower confidence or produce abstention.

### 4.3 Uncertainty

`uncertainty` includes components for data quality, context, market conflict, engine disagreement, distribution entropy, simulation variance, calibration reliability, missing evidence, and league sample quality when applicable. `confidence_interval` and `grade` are not probability values and do not alter the underlying distributions.

### 4.4 Risk and abstention

`risk` includes typed risk flags, severity, evidence/engine refs, and `abstention_state`. Valid outcomes include `PASS`, `NO_STRONG_RECOMMENDATION`, `BLOCKED`, and `INSUFFICIENT_DATA`. The contract permits abstention and never forces a “strong” output.

## 5. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000701",
  "prediction_id": "019a0000-0000-7000-8000-000000000701",
  "contract_version": "prediction@1.0.0",
  "created_at": "2026-09-01T13:00:00+08:00",
  "source_timestamp": "2026-09-01T12:50:00+08:00",
  "observed_at": "2026-09-01T13:00:00+08:00",
  "ingested_at": "2026-09-01T13:00:01+08:00",
  "source": "JCFB V4 prediction orchestrator",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/prediction/20260901/001/130000",
  "confidence": {"state": "ASSESSED", "score": 0.78, "basis": "Input and engine lineage resolved; context uncertainty remains"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
  "status": "AVAILABLE",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "role": "PRODUCTION",
  "model_version": "jcfb-v4-orchestrator@4.0.0",
  "prediction_revision": "pr-20260901-000001",
  "frozen_input_id": "019a0000-0000-7000-8000-000000000401",
  "frozen_input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "engine_run_refs": [
    {"market": "spf", "engine_run_id": "019a0000-0000-7000-8000-000000000601", "output_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"},
    {"market": "rqspf", "engine_run_id": "019a0000-0000-7000-8000-000000000602", "output_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111"},
    {"market": "total_goals", "engine_run_id": "019a0000-0000-7000-8000-000000000603", "output_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222"},
    {"market": "exact_score", "engine_run_id": "019a0000-0000-7000-8000-000000000604", "output_hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333"},
    {"market": "half_full", "engine_run_id": "019a0000-0000-7000-8000-000000000605", "output_hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444"}
  ],
  "market_predictions": {
    "spf": {
      "market": "spf",
      "market_state": "AVAILABLE",
      "engine_run_ref": "019a0000-0000-7000-8000-000000000601",
      "probabilities": {"H": 0.52, "D": 0.26, "A": 0.22},
      "selection": {"outcome": "H", "state": "PASS"},
      "consistency_state": "ACCEPTABLE",
      "reason_codes": []
    },
    "rqspf": {
      "market": "rqspf",
      "market_state": "AVAILABLE",
      "engine_run_ref": "019a0000-0000-7000-8000-000000000602",
      "official_handicap": -1.0,
      "probabilities": {"H": 0.34, "D": 0.28, "A": 0.38},
      "selection": {"outcome": "A", "state": "NO_STRONG_RECOMMENDATION"},
      "consistency_state": "ACCEPTABLE",
      "reason_codes": ["HANDICAP_CONFLICT"]
    },
    "total_goals": {
      "market": "total_goals",
      "market_state": "AVAILABLE",
      "engine_run_ref": "019a0000-0000-7000-8000-000000000603",
      "probabilities": {"0": 0.08, "1": 0.22, "2": 0.30, "3": 0.22, "4": 0.10, "5": 0.05, "6": 0.02, "7+": 0.01},
      "goal_bands": {"0-1": 0.30, "2-3": 0.52, "4+": 0.18},
      "selection": {"band": "2-3", "state": "PASS"},
      "consistency_state": "ACCEPTABLE",
      "reason_codes": []
    },
    "exact_score": {
      "market": "exact_score",
      "market_state": "AVAILABLE",
      "engine_run_ref": "019a0000-0000-7000-8000-000000000604",
      "score_probability_matrix_ref": {"engine_run_id": "019a0000-0000-7000-8000-000000000604", "matrix_hash": "sha256:5555555555555555555555555555555555555555555555555555555555555555"},
      "lambda_home": 1.42,
      "lambda_away": 0.86,
      "btts_probability": 0.48,
      "clean_sheet_probability": {"home": 0.42, "away": 0.21},
      "top_candidates": [{"score": "1:0", "probability": 0.14}, {"score": "1:1", "probability": 0.12}],
      "selection": {"scores": ["1:0", "1:1"], "state": "NO_STRONG_RECOMMENDATION"},
      "consistency_state": "ACCEPTABLE",
      "reason_codes": ["TOP_SCORE_CONVERGENCE_NOT_SUFFICIENT"]
    },
    "half_full": {
      "market": "half_full",
      "market_state": "AVAILABLE",
      "engine_run_ref": "019a0000-0000-7000-8000-000000000605",
      "probabilities": {"H/H": 0.22, "H/D": 0.08, "H/A": 0.04, "D/H": 0.18, "D/D": 0.20, "D/A": 0.08, "A/H": 0.06, "A/D": 0.08, "A/A": 0.06},
      "selection": {"state": "NO_STRONG_RECOMMENDATION"},
      "consistency_state": "ACCEPTABLE",
      "reason_codes": ["NINE_STATE_DISPERSION"]
    }
  },
  "consensus": {
    "consensus_score": 0.71,
    "directional_consensus": "HOME_LEAN",
    "votes": {"home": 4, "draw": 2, "away": 1},
    "support": [{"direction": "HOME", "engine_refs": ["019a0000-0000-7000-8000-000000000601", "019a0000-0000-7000-8000-000000000603"]}],
    "conflicts": [{"engines": ["019a0000-0000-7000-8000-000000000601", "019a0000-0000-7000-8000-000000000602"], "state": "CONFLICTED", "reason": "Full-time and handicap directions differ"}],
    "individual_engine_output_refs": ["019a0000-0000-7000-8000-000000000601", "019a0000-0000-7000-8000-000000000602", "019a0000-0000-7000-8000-000000000603", "019a0000-0000-7000-8000-000000000604", "019a0000-0000-7000-8000-000000000605"]
  },
  "disagreement": {"numeric_disagreement_score": 0.31, "grade": "MEDIUM", "conflicts": ["HANDICAP_CONFLICT"]},
  "uncertainty": {
    "components": {"data_quality": 0.08, "context": 0.24, "market_conflict": 0.18, "engine_disagreement": 0.31, "simulation_variance": "NOT_APPLICABLE"},
    "confidence_interval": {"target": "spf.H", "lower": 0.45, "upper": 0.59},
    "grade": "MEDIUM"
  },
  "risk": {
    "risk_flags": [{"code": "HANDICAP_CONFLICT", "severity": "MEDIUM", "refs": ["019a0000-0000-7000-8000-000000000602"]}],
    "abstention_state": "NO_STRONG_RECOMMENDATION"
  },
  "confidence_grade": "MEDIUM",
  "recommendation_state": "PASS",
  "recommendation_strength": "MODERATE",
  "prediction_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
}
```

## 6. Frozen Prediction Contract

Frozen Prediction is the immutable public/audit record of a passed Prediction. It contains:

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `frozen_prediction_id` | UUID/UUIDv7 | REQUIRED | Stable immutable identity. |
| `contract_version` | string | REQUIRED | `frozen-prediction@MAJOR.MINOR.PATCH`. |
| `prediction_id` | stable ref | REQUIRED | Exact Prediction being frozen. |
| `freeze_revision` | immutable revision | REQUIRED | Append-only freeze identity. |
| `frozen_at` | timezone-aware timestamp | REQUIRED | Freeze time, separate from prediction creation and kickoff. |
| `snapshot` | immutable embedded prediction snapshot | REQUIRED | Exact prediction payload used for evaluation/public read. |
| `prediction_hash` | SHA-256 string | REQUIRED | Hash of the unfrozen Prediction payload. |
| `frozen_snapshot_hash` | SHA-256 string | REQUIRED | Hash of the exact `snapshot` plus declared freeze boundary. |
| `supersedes_frozen_prediction_id` | stable ref/state | REQUIRED | Previous frozen identity or `NOT_APPLICABLE` for first revision. |
| common metadata | typed metadata | REQUIRED | Provenance, status, and hashes. |

After freeze, no field in `snapshot`, `prediction_hash`, `frozen_snapshot_hash`, result lineage, confidence, risk, or recommendation may be updated. A correction or pre-kickoff replacement creates a new Frozen Prediction with a new freeze revision, explicit supersession, reason, actor, time, and hashes. The old record remains immutable.

### 6.1 Minimum Frozen Prediction JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000702",
  "frozen_prediction_id": "019a0000-0000-7000-8000-000000000702",
  "contract_version": "frozen-prediction@1.0.0",
  "created_at": "2026-09-01T13:01:00+08:00",
  "source_timestamp": "2026-09-01T13:00:00+08:00",
  "observed_at": "2026-09-01T13:01:00+08:00",
  "ingested_at": "2026-09-01T13:01:01+08:00",
  "source": "JCFB V4 final prediction freeze gate",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/freeze-prediction/20260901/001/130100",
  "confidence": {"state": "ASSESSED", "score": 0.99, "basis": "Prediction gate passed and snapshot was sealed"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:dededededededededededededededededededededededededededededededede",
  "status": "FROZEN",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "prediction_id": "019a0000-0000-7000-8000-000000000701",
  "freeze_revision": "fp-20260901-000001",
  "frozen_at": "2026-09-01T13:01:00+08:00",
  "snapshot": {
    "prediction_id": "019a0000-0000-7000-8000-000000000701",
    "match_id": "019a0000-0000-7000-8000-000000000002",
    "role": "PRODUCTION",
    "model_version": "jcfb-v4-orchestrator@4.0.0",
    "prediction_revision": "pr-20260901-000001",
    "frozen_input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
    "market_predictions": {"spf": {"selection": "H"}, "rqspf": {"selection": "NO_STRONG_RECOMMENDATION"}, "total_goals": {"selection": "2-3"}, "exact_score": {"selection": ["1:0", "1:1"]}, "half_full": {"selection": "NO_STRONG_RECOMMENDATION"}},
    "confidence_grade": "MEDIUM",
    "recommendation_state": "PASS",
    "recommendation_strength": "MODERATE"
  },
  "prediction_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
  "frozen_snapshot_hash": "sha256:dededededededededededededededededededededededededededededededede",
  "supersedes_frozen_prediction_id": "NOT_APPLICABLE"
}
```

## 7. Validation rules

### Required and type checks

- All Prediction fields marked required, common metadata, and all five `market_predictions` keys are present.
- All market distributions have finite values in `[0,1]` and reconcile to one within the declared tolerance. The nine Half-Full states and `0..7+` goal buckets are complete when their market is available.
- `selection` is optional only when state is `NO_STRONG_RECOMMENDATION`, `BLOCKED`, `INSUFFICIENT_DATA`, or market unavailable; it must not be fabricated to fill a display slot.
- `confidence_grade`, `recommendation_state`, and `recommendation_strength` are separate typed fields. No validator may derive one by copying another.

### Referential and independence checks

- Every market has its own Engine Output reference and exact hash. Cross-market consistency annotations run after independent outputs and cannot replace them.
- Exact Score `top_candidates` resolve to a Score matrix/output; the selector cannot change the matrix probabilities.
- RQSPF references an official handicap/availability record; external odds cannot satisfy the official market requirement.
- Consensus retains all contributing engine refs, support, votes, and conflicts. Disagreement and uncertainty retain their component details.
- `frozen_input_id/hash` resolves to an immutable Frozen Input. Production/Shadow A/B predictions use the same frozen hash.

### Timestamp and no-future-leakage checks

- The referenced Frozen Input proves `prediction_cutoff_at < kickoff_at` and all source availability times are at or before cutoff.
- Result, postmatch event, xG, red-card, final-score, post-kickoff lineup, and future odds records are forbidden in a pre-match Prediction. Their presence sets `future_information_leakage=true`, invalidates the run, and removes Tier A/promotion eligibility.
- `created_at` and engine `run_at` are not substitutes for source availability.

### Role and immutability checks

- `role` is explicit. Shadow and Experiment predictions cannot enter Production public projection or mutate Production/Frozen Prediction.
- Frozen Prediction is write-once. An attempted update is a role/governance violation; the correction path is a new append-only revision.
- A Prediction or Frozen Prediction cannot reference V3.3.3 model output, parameters, confidence, or historical Frozen Prediction.

## 8. Hash and compatibility boundary

`prediction_hash` includes match/role/model/revision/frozen input refs, all five market payloads, engine refs, consensus, disagreement, uncertainty, risk, confidence grade, recommendation state/strength, and logical reason codes. It excludes transport-only creation/ingestion timestamps and UI fields. `frozen_snapshot_hash` includes the exact embedded snapshot and freeze revision/supersession boundary; it is never recalculated to match a result.

Adding an optional market annotation is `MINOR`. Changing market independence, probability keys, confidence/recommendation semantics, freeze mutability, required refs, or hash boundary is `MAJOR`. Clarification is `PATCH`. A model, selector, engine, config, or calibration behavior change requires a new version/revision and forward evidence even when this shape is unchanged.
