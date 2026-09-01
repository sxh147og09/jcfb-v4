# JCFB V4 Result and Postmatch Review Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Scope and postmatch boundary

This contract defines the Official Result object and the Postmatch Review object. It preserves the separation between deterministic model evaluation and explanatory postmatch analysis.

The default official football result scope for JCFB evaluation is `REGULATION_90_PLUS_STOPPAGE`: regulation 90 minutes plus officially specified stoppage time. Extra time and penalty shootouts are excluded unless the applicable lottery market rules explicitly require them. A result that cannot be matched exactly to Canonical Match Identity is `BLOCKED` and cannot be used for evaluation.

## 2. Official Result Contract

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `result_id` | UUID/UUIDv7 | REQUIRED | Stable result identity. |
| `contract_version` | string | REQUIRED | `official-result@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 | REQUIRED | Must exactly match Canonical Match Identity. |
| `full_time_home` / `full_time_away` | non-negative integer | REQUIRED | Regulation result used for SPF/RQSPF/Goals/Score evaluation. |
| `half_time_home` / `half_time_away` | non-negative integer | REQUIRED | Regulation first-half result used for Half-Full evaluation. |
| `result_scope` | enum | REQUIRED | Default `REGULATION_90_PLUS_STOPPAGE`; explicit rule override if applicable. |
| `official_result_payload` | structured source payload | REQUIRED | Preserve normalized values plus source/raw reference; no postmatch inference. |
| `source` / `source_type` / `source_reference` | typed metadata | REQUIRED | Official result authority and replayable reference. |
| `verified_at` | timezone-aware timestamp | REQUIRED | Verification time, separate from kickoff/result event time. |
| `source_timestamp` / `observed_at` / `ingested_at` | timestamps | REQUIRED | Source and intake lineage. |
| `result_hash` / `payload_hash` / `provenance_hash` | SHA-256 strings | REQUIRED | Hash exact result and provenance. |
| `status` / `metadata` | typed metadata | REQUIRED | `VERIFIED`, `BLOCKED`, or governed result state. |

`official_result_payload` may retain extra-time or shootout fields for audit when the source supplies them, but the default `result_scope` excludes them from JCFB evaluation. A market-specific rule may opt in only through an explicit, versioned contract/configuration.

### 2.1 Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000801",
  "result_id": "019a0000-0000-7000-8000-000000000801",
  "contract_version": "official-result@1.0.0",
  "created_at": "2026-09-01T21:45:00+08:00",
  "source_timestamp": "2026-09-01T21:40:00+08:00",
  "observed_at": "2026-09-01T21:44:00+08:00",
  "ingested_at": "2026-09-01T21:45:01+08:00",
  "source": "Example official competition result source",
  "source_type": "OFFICIAL_FEED",
  "source_reference": "ref://official/result/20260901/001/214000",
  "confidence": {"state": "ASSESSED", "score": 0.99, "basis": "Official result matched canonical match identity"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
  "status": "VERIFIED",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "full_time_home": 1,
  "full_time_away": 0,
  "half_time_home": 0,
  "half_time_away": 0,
  "result_scope": "REGULATION_90_PLUS_STOPPAGE",
  "official_result_payload": {
    "canonical_match_ref": "019a0000-0000-7000-8000-000000000002",
    "normalized_score": {"ft": "1:0", "ht": "0:0"},
    "extra_time": "NOT_APPLICABLE",
    "penalty_shootout": "NOT_APPLICABLE"
  },
  "verified_at": "2026-09-01T21:45:00+08:00",
  "result_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
}
```

## 3. Postmatch Review Contract

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `review_id` | UUID/UUIDv7 | REQUIRED | Stable review identity. |
| `contract_version` | string | REQUIRED | `postmatch-review@MAJOR.MINOR.PATCH`. |
| `review_type` | enum | REQUIRED | Exactly `MODEL_EVALUATION` or `MATCH_EXPLANATION`. |
| `frozen_prediction_id` | stable ref | REQUIRED | Exact immutable prediction being reviewed. |
| `result_id` | stable ref | REQUIRED | Exact Official Result used. |
| `market_hit_results` | structured object | REQUIRED for `MODEL_EVALUATION`; CONDITIONAL for explanation | Per-market comparison against official result, never retroactively edited. |
| `score_metrics` | structured object | REQUIRED for `MODEL_EVALUATION`; CONDITIONAL for explanation | Brier/Log Loss/MAE/score coverage or declared `NOT_APPLICABLE`. |
| `error_attribution` | diagnostic object | REQUIRED | Diagnostic labels, not automatic parameter changes. |
| `reviewed_at` | timezone-aware timestamp | REQUIRED | Review time, separate from result verification. |
| `review_hash` / `payload_hash` / `provenance_hash` | SHA-256 strings | REQUIRED | Hash exact review artifact. |
| `source` / `source_reference` / `status` / `metadata` | typed metadata | REQUIRED | Review provenance and lifecycle. |
| `postmatch_evidence_refs` | array | REQUIRED for `MATCH_EXPLANATION`; forbidden for MODEL_EVALUATION inputs | xG/events/red cards/technical stats/interviews, kept out of model evaluation. |

### 3.1 MODEL_EVALUATION boundary

`MODEL_EVALUATION` can read only:

- the immutable `Frozen Prediction` snapshot and its engine/prediction hashes;
- the verified `Official Result` and its result hash;
- deterministic evaluation code/config identities.

It may calculate market hit/miss, score metrics, calibration metrics, and output-vs-result diagnostic attribution. It must not read postmatch xG, events, red cards, substitutions, technical statistics, interviews, or a later market narrative. It cannot update the Frozen Prediction or model parameters.

### 3.2 MATCH_EXPLANATION boundary

`MATCH_EXPLANATION` may read postmatch evidence such as xG, goal/event timeline, red cards, substitutions, technical statistics, and postmatch interviews. It explains match circumstances and may identify a diagnostic hypothesis, but it must not write to `market_hit_results`, `score_metrics`, Frozen Input, Frozen Prediction, model parameters, calibration history, or promotion evidence. Any model change is a future version with new forward evidence.

### 3.3 Minimum MODEL_EVALUATION JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000901",
  "review_id": "019a0000-0000-7000-8000-000000000901",
  "contract_version": "postmatch-review@1.0.0",
  "created_at": "2026-09-01T22:00:00+08:00",
  "source_timestamp": "2026-09-01T21:45:00+08:00",
  "observed_at": "2026-09-01T22:00:00+08:00",
  "ingested_at": "2026-09-01T22:00:01+08:00",
  "source": "JCFB V4 deterministic evaluator",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/review/evaluation/20260901/001/220000",
  "confidence": {"state": "ASSESSED", "score": 0.99, "basis": "Only Frozen Prediction and Official Result were read"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:dededededededededededededededededededededededededededededededede",
  "status": "VERIFIED",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "review_type": "MODEL_EVALUATION",
  "frozen_prediction_id": "019a0000-0000-7000-8000-000000000702",
  "result_id": "019a0000-0000-7000-8000-000000000801",
  "market_hit_results": {
    "spf": {"predicted": "H", "actual": "H", "hit": true},
    "rqspf": {"predicted": "NO_STRONG_RECOMMENDATION", "actual": "H", "hit": "NOT_APPLICABLE"},
    "total_goals": {"predicted": "2-3", "actual": 1, "hit": false},
    "exact_score": {"predicted": ["1:0", "1:1"], "actual": "1:0", "hit": true},
    "half_full": {"predicted": "NO_STRONG_RECOMMENDATION", "actual": "D/H", "hit": "NOT_APPLICABLE"}
  },
  "score_metrics": {
    "spf_brier": 0.19,
    "spf_log_loss": 0.65,
    "total_goals_mae": 0.0,
    "exact_score_top2_hit": true,
    "calculation_scope": "FROZEN_PREDICTION_PLUS_OFFICIAL_RESULT"
  },
  "error_attribution": {
    "state": "DIAGNOSTIC_ONLY",
    "labels": ["GOALS_DISTRIBUTION_MISALIGNMENT"],
    "basis_refs": ["frozen-prediction:019a0000-0000-7000-8000-000000000702", "result:019a0000-0000-7000-8000-000000000801"]
  },
  "reviewed_at": "2026-09-01T22:00:00+08:00",
  "review_hash": "sha256:dededededededededededededededededededededededededededededededede",
  "postmatch_evidence_refs": []
}
```

### 3.4 Minimum MATCH_EXPLANATION JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000902",
  "review_id": "019a0000-0000-7000-8000-000000000902",
  "contract_version": "postmatch-review@1.0.0",
  "created_at": "2026-09-01T22:10:00+08:00",
  "source_timestamp": "2026-09-01T22:05:00+08:00",
  "observed_at": "2026-09-01T22:10:00+08:00",
  "ingested_at": "2026-09-01T22:10:01+08:00",
  "source": "JCFB V4 match explanation process",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/review/explanation/20260901/001/221000",
  "confidence": {"state": "ASSESSED", "score": 0.82, "basis": "Postmatch evidence references are attributed but explanatory"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef",
  "status": "AVAILABLE",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "review_type": "MATCH_EXPLANATION",
  "frozen_prediction_id": "019a0000-0000-7000-8000-000000000702",
  "result_id": "019a0000-0000-7000-8000-000000000801",
  "market_hit_results": "NOT_APPLICABLE",
  "score_metrics": "NOT_APPLICABLE",
  "error_attribution": {"state": "DIAGNOSTIC_ONLY", "labels": ["LATE_GAME_STATE_CHANGE"], "basis_refs": ["postmatch-evidence:event-001"]},
  "postmatch_evidence_refs": ["postmatch-evidence:event-001", "postmatch-evidence:xg-001", "postmatch-evidence:red-card-001"],
  "explanation": "A late state change and a red-card event altered the match script after the pre-match cutoff.",
  "reviewed_at": "2026-09-01T22:10:00+08:00",
  "review_hash": "sha256:efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef"
}
```

## 4. Validation rules

### Official Result

- All fields in section 2 marked required and common required metadata are present.
- `match_id` resolves exactly to one Canonical Match Identity; an unmatched or ambiguous result is `BLOCKED`.
- Scores are finite non-negative integers. `result_scope` is explicit; default evaluation excludes extra time and penalties.
- A post-kickoff result cannot appear in any pre-match Frozen Input, Feature Bundle, Engine Output, or Prediction.
- `verified_at` is not substituted for the source result time. Source and observation times remain separate.
- `result_hash`, `payload_hash`, and `provenance_hash` are format-valid and recomputable.

### Postmatch Review

- `MODEL_EVALUATION` has only Frozen Prediction and Official Result references as data inputs. `postmatch_evidence_refs` must be absent or an explicit empty array and cannot contain xG/events/red-card evidence.
- `MATCH_EXPLANATION` must identify postmatch evidence references and must not write back into model evaluation or frozen artifacts.
- `market_hit_results` uses the applicable official result scope and preserves `NOT_APPLICABLE` for abstained/unavailable markets; it does not convert abstention into a miss.
- `score_metrics` declare their calculation scope and exact input hashes. `error_attribution` is diagnostic only and cannot auto-change parameters or promotion status.
- Review timestamps are timezone-aware and review hashes are present. A new review revision appends; it does not update an old evaluation.

### No-future-leakage and role checks

- No Review object is readable by a pre-match contract. A review or result reference in a pre-match input is a future-information violation.
- Review cannot alter Production/Shadow/Experiment role identity, Frozen Prediction, confidence, or public projection.
- V3.3.3 results/reviews remain separate model-line artifacts and cannot be copied into a V4 review.

## 5. Hash and compatibility boundary

The Official Result hash includes canonical match ref, full/half scores, result scope, normalized official payload, source identity, and verification lineage. Review hashes include review type, frozen prediction/result refs, allowed metrics/diagnostics, evidence refs for explanations, and review status. Transport timestamps are excluded only where declared volatile.

Adding an optional metric or explanation annotation is `MINOR`; changing result scope, evaluation inputs, review-type permissions, score meanings, hash boundaries, or immutability is `MAJOR`; documentation clarification is `PATCH`.
