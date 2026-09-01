# JCFB V4 Feature Bundle Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and hard boundary

Feature Bundle is the typed, versioned, reproducible representation consumed by independent V4 engines. It is generated from one accepted Frozen Input and never reads unversioned raw source directly in a formal Production or Shadow path.

This contract defines the shape and lineage of features, not their model weights, algorithm, or Production parameter values. A feature transformation is model-line private even when it starts from a shared objective fact.

## 2. Required fields and feature categories

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `feature_bundle_id` | UUID/UUIDv7 | REQUIRED | Stable bundle identity. |
| `contract_version` | string | REQUIRED | `feature-bundle@MAJOR.MINOR.PATCH`. |
| `feature_schema_version` | qualified version | REQUIRED | Exact feature shape/meaning identity. |
| `generator_version` | qualified version/revision | REQUIRED | Exact generator implementation identity. |
| `input_hash` | SHA-256 string | REQUIRED | Hash of the exact feature input envelope; must include the Frozen Input hash. |
| `frozen_input_id` / `frozen_input_hash` | stable ref/hash | REQUIRED | No feature bundle is formal without a frozen source boundary. |
| `generated_at` | timezone-aware timestamp | REQUIRED | Computation time, separate from source availability. |
| `prediction_cutoff_at` / `kickoff_at` | timezone-aware timestamps | REQUIRED for pre-match bundle | Used by the no-future-leakage gate. |
| `feature_values` | typed object | REQUIRED | Contains the seven governed categories below. |
| `missingness_summary` | structured object | REQUIRED | Counts and states by category/feature; no hidden null semantics. |
| `quality_flags` | array/object | REQUIRED | Quality and gate signals such as `PASS`, `UNKNOWN_INPUT`, `STALE_INPUT`, or `BLOCKED_INPUT`. |
| `feature_hash` | SHA-256 string | REQUIRED | Hash of the logical feature bundle payload. |
| `payload_hash` / `provenance_hash` / `status` / `metadata` | common fields | REQUIRED | Common lineage and state. |

The mandatory feature categories are:

- `statistical_features`
- `football_context_features`
- `market_features`
- `league_features`
- `tactical_features`
- `score_features`
- `quality_features`

Each category is an object of named feature records. A feature record should declare `value`, `state`, `unit` when numeric, `source_refs`, and a short `derivation` tied to the generator version. `value` is absent when the state is `UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`, `BLOCKED`, or `NOT_APPLICABLE`; zero is allowed only when zero is an observed/derived value and the state is `AVAILABLE`.

## 3. Feature semantics and missingness

Feature Bundle preserves the distinction between:

| Feature state | Meaning in a bundle |
|---|---|
| `AVAILABLE` | Derived feature has a valid typed value and accepted upstream lineage |
| `UNKNOWN` | Upstream property is not known; do not impute silently |
| `UNAVAILABLE` | Upstream market/context was explicitly not supplied |
| `NOT_VERIFIED` | An upstream claim exists but did not pass verification |
| `BLOCKED` | Gate prevents the feature from being used in the declared formal role |
| `NOT_APPLICABLE` | Feature does not apply to this role, market, or component |

`missingness_summary` must count states separately, for example:

```json
{
  "total_features": 42,
  "by_state": {"AVAILABLE": 35, "UNKNOWN": 3, "UNAVAILABLE": 2, "NOT_VERIFIED": 1, "BLOCKED": 1},
  "by_category": {"football_context_features": {"unknown": 2, "available": 8}}
}
```

The generator may use an explicitly versioned imputation/default policy only when that policy is part of the config identity, allowed by the engine contract, and recorded in `quality_flags`. Otherwise the feature remains in its original missing state and the consuming gate can return `PASS`, `NO_STRONG_RECOMMENDATION`, or `BLOCKED` according to the applicable contract.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000501",
  "feature_bundle_id": "019a0000-0000-7000-8000-000000000501",
  "contract_version": "feature-bundle@1.0.0",
  "created_at": "2026-09-01T12:40:00+08:00",
  "source_timestamp": "2026-09-01T12:00:00+08:00",
  "observed_at": "2026-09-01T12:40:00+08:00",
  "ingested_at": "2026-09-01T12:40:01+08:00",
  "source": "JCFB V4 versioned feature generator",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/feature-generator/4.0.0/r001/20260901/001",
  "confidence": {"state": "ASSESSED", "score": 0.91, "basis": "Frozen input resolved; some context fields remain unknown"},
  "provenance_hash": "sha256:8888888888888888888888888888888888888888888888888888888888888888",
  "payload_hash": "sha256:9999999999999999999999999999999999999999999999999999999999999999",
  "status": "AVAILABLE",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "feature_schema_version": "feature-bundle@1.0.0",
  "generator_version": "feature-generator@4.0.0#r001",
  "frozen_input_id": "019a0000-0000-7000-8000-000000000401",
  "frozen_input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "input_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prediction_cutoff_at": "2026-09-01T12:00:00+08:00",
  "kickoff_at": "2026-09-01T19:35:00+08:00",
  "generated_at": "2026-09-01T12:40:00+08:00",
  "feature_values": {
    "statistical_features": {
      "home_attack_rating": {"value": 0.72, "state": "AVAILABLE", "unit": "standardized_score", "source_refs": ["dataset:pre-match-facts@1.0.0#r001"], "derivation": "Versioned rating transform"}
    },
    "football_context_features": {
      "home_injury_count": {"value": 0, "state": "AVAILABLE", "unit": "players", "source_refs": ["team-context:019a0000-0000-7000-8000-000000000201"], "derivation": "NONE_CONFIRMED collection count"},
      "away_suspension_state": {"state": "UNKNOWN", "source_refs": ["team-context:away-unknown-001"], "derivation": "No verified source"}
    },
    "market_features": {
      "official_spf_home_price": {"value": 2.10, "state": "AVAILABLE", "unit": "decimal_odds", "source_refs": ["snapshot:019a0000-0000-7000-8000-000000000101"], "derivation": "Official snapshot read"}
    },
    "league_features": {
      "league_sample_quality": {"value": "MEDIUM", "state": "AVAILABLE", "source_refs": ["dataset:league-profile@1.0.0#r001"], "derivation": "Declared league profile"}
    },
    "tactical_features": {
      "home_pressing_intensity": {"state": "NOT_VERIFIED", "source_refs": ["evidence:tactical-001"], "derivation": "Claim not fully verified"}
    },
    "score_features": {
      "expected_home_goals_input": {"value": 1.42, "state": "AVAILABLE", "unit": "goals", "source_refs": ["feature:statistical_features/home_attack_rating"], "derivation": "Versioned score input transform"}
    },
    "quality_features": {
      "future_information_leakage": {"value": false, "state": "AVAILABLE", "source_refs": ["frozen-input:019a0000-0000-7000-8000-000000000401"], "derivation": "Cutoff gate passed"}
    }
  },
  "missingness_summary": {
    "total_features": 7,
    "by_state": {"AVAILABLE": 5, "UNKNOWN": 1, "NOT_VERIFIED": 1},
    "by_category": {"football_context_features": {"AVAILABLE": 1, "UNKNOWN": 1}, "tactical_features": {"NOT_VERIFIED": 1}}
  },
  "quality_flags": ["PASS", "UNKNOWN_CONTEXT_RETAINED", "NOT_VERIFIED_CONTEXT_RETAINED"],
  "future_information_leakage": false,
  "feature_hash": "sha256:9999999999999999999999999999999999999999999999999999999999999999"
}
```

## 5. Validation rules

### Required, type, and range checks

- All required fields and all seven categories exist, even if a category has only explicit missingness records.
- `feature_schema_version` and `generator_version` are exact registered identities; unqualified `latest`/`current` aliases are invalid.
- Numeric features declare units and finite numeric values. Probabilities are in `[0,1]`; counts are non-negative integers; odds are positive when used.
- Every feature has a state. A feature with `state=UNKNOWN`/`UNAVAILABLE`/`BLOCKED` has no fabricated numeric value.
- `missingness_summary` reconciles with the feature records and preserves states separately.

### Reference, timestamp, and hash checks

- `frozen_input_hash` and `input_hash` resolve to the exact Frozen Input and feature input envelope. A same-match but different snapshot is a different input.
- Every derived feature retains source/fact/evidence references required to reproduce the transformation.
- For pre-match use, all referenced source availability times are at or before `prediction_cutoff_at`; `generated_at` may be later than the cutoff but must be before kickoff and must not introduce a new source.
- `future_information_leakage=true` or an unresolved cutoff makes `status=BLOCKED` and the bundle ineligible for formal Production/Shadow use.
- `feature_hash`, `payload_hash`, and `provenance_hash` are format-valid and recomputable.

### Role and boundary checks

- Engines consume the Feature Bundle interface, not raw screenshots, free-form JSON, unversioned news, or direct external provider responses.
- Production and Shadow bundles in an A/B pair reference the same `frozen_input_hash`; role-specific engine input identity remains in the Engine Output envelope.
- An Experiment bundle is not a Production or Shadow feature bundle by relabeling.

## 6. Hash and compatibility boundary

The feature hash includes the feature schema/generator identities, Frozen Input ref/hash, typed feature values/states/units/source refs, missingness summary, quality flags, cutoff/kickoff, and declared derivation identities. It excludes `created_at`, `ingested_at`, and non-authoritative trace telemetry.

Adding an optional feature with an explicit missingness state is `MINOR`; changing a feature's meaning, unit, type, imputation rule, category, cutoff behavior, or hash boundary is `MAJOR`; clarification is `PATCH`. A new model-affecting generator or default policy requires a new generator/config/revision and forward evidence even when the schema remains backward-compatible.
