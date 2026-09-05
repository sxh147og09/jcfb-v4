# JCFB V4 Engine Output Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and common envelope

Every independent V4 Engine emits the same auditable envelope. A consumer can therefore identify the role, model, engine, revision, implementation, configuration, input, output, runtime, warnings, errors, and payload without inspecting a path or guessing from a filename.

This contract defines interfaces only. It does not implement engines, choose algorithms, run Production or Shadow, or perform a database write.

## 2. Unified Engine Output envelope

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `engine_run_id` | UUID/UUIDv7 | REQUIRED | Stable run identity; never generated from display text alone. |
| `contract_version` | string | REQUIRED | `engine-output@MAJOR.MINOR.PATCH`. |
| `role` | enum | REQUIRED | Exactly `PRODUCTION`, `SHADOW`, or `EXPERIMENT`; never inferred from path/name. |
| `model_name` / `model_version` | qualified identities | REQUIRED | Exact model registry identity. |
| `engine_name` / `engine_version` | qualified identities | REQUIRED | Exact independent engine identity. |
| `revision` | immutable registry revision | REQUIRED | Role-scoped revision identity. |
| `shadow_revision` | role-scoped ID/state | CONDITIONAL | Required for `SHADOW`; `NOT_APPLICABLE` for other roles. |
| `experiment_revision` | role-scoped ID/state | CONDITIONAL | Required for `EXPERIMENT`; `NOT_APPLICABLE` for other roles. |
| `implementation_hash` | SHA-256 string | REQUIRED | Exact implementation/dependency identity. |
| `config_version` / `config_hash` | qualified identity/hash | REQUIRED | Effective non-secret configuration. |
| `schema_version` | qualified identity | REQUIRED | Engine output schema identity. |
| `input_hash` | SHA-256 string | REQUIRED | Exact engine input envelope, including role/component/frozen references. |
| `frozen_input_id` / `frozen_input_hash` | stable ref/hash | REQUIRED for formal pre-match runs | Frozen source boundary. Production/Shadow A/B must share the same `frozen_input_hash`. |
| `output_hash` | SHA-256 string | REQUIRED | Hash of raw logical output envelope/payload before presentation, result, review, or explanation. |
| `run_at` / `run_completed_at` | timezone-aware timestamps | REQUIRED | Execution start/end; separate from source availability and kickoff. |
| `prediction_cutoff_at` / `kickoff_at` | timezone-aware timestamps | REQUIRED for pre-match runs | No-future-leakage boundary. |
| `runtime_ms` | finite non-negative number | REQUIRED | Runtime telemetry; excluded from `output_hash` unless a future contract makes it logical. |
| `runtime_environment` | non-secret object | REQUIRED | Reproducibility descriptor; secrets never enter it. |
| `status` | `run_status` enum | REQUIRED | `SUCCEEDED`, `FAILED`, `BLOCKED`, `INVALID`, etc. |
| `warnings` | array | REQUIRED | Structured non-fatal warnings; empty array means no warnings, not unknown. |
| `errors` | array | REQUIRED | Structured errors; non-empty for `FAILED`, `BLOCKED`, or `INVALID`. |
| `payload` | engine-specific object | REQUIRED on success; CONDITIONAL on failure | Must conform to the engine payload contract below. A blocked run uses an explicit error/state, never a fabricated result. |
| common metadata | typed metadata | REQUIRED | Creation/source/provenance/hash/status metadata from the umbrella contract. |

`input_hash` is not the same as `frozen_input_hash`: the former includes role and component identity, while the latter identifies the substantive frozen pre-match data. This preserves both reproducibility and valid Production/Shadow A/B pairing.

## 3. Minimum payload contracts

All probabilities are finite numbers in `[0,1]`. A distribution must sum to `1.0` within the declared tolerance (default `1e-6`) or emit a validation error and fail closed. Payloads retain raw engine results; later consensus or risk layers cannot silently replace them.

| Engine | `engine_name` | Minimum payload |
|---|---|---|
| Outcome | `outcome_engine` | `outcome_probability: {H,D,A}`, `normalization_error`, and the exact feature/input refs used. |
| Handicap | `handicap_engine` | `official_handicap`, `handicap_outcome_probability: {H,D,A}`, `goal_difference_distribution`, and sign convention `home_minus_away`. |
| Goals | `goals_engine` | `goal_distribution` for `0..7+`, `goal_bands`, and normalization/tail policy. |
| HTFT | `htft_engine` | `half_full_probability` for exactly nine states: `H/H`, `H/D`, `H/A`, `D/H`, `D/D`, `D/A`, `A/H`, `A/D`, `A/A`. |
| Score | `score_engine` | `score_probability_matrix`, `lambda_home`, `lambda_away`, `btts_probability`, `clean_sheet_probability`, and `top_candidates`. |
| Upset | `upset_engine` | `upset_probability`, `upset_type`, `drivers`, and a separate payload `confidence` object. |
| Simulation | `simulation_engine` | `runs`, `seed`, `simulation_version`, `aggregate_probabilities`, and `scripts`. |
| Consensus | `consensus_engine` | `votes`, `support`, `conflicts`, `consensus_score`, and `individual_engine_output_refs`. |
| Uncertainty | `uncertainty_engine` | `uncertainty_components`, `confidence_interval`, and `grade`. |
| Risk | `risk_engine` | `risk_flags`, `abstention_state`, and gate/reason details. |

### 3.1 Distribution details

- Outcome probabilities use H/D/A keys and do not mechanically generate the other four market outputs.
- Handicap goal difference is signed as `home_goals - away_goals`; the supported range and any tail bucket are declared in the payload.
- Goals include explicit `0`, `1`, `2`, `3`, `4`, `5`, `6`, and `7+` buckets. `7+` is not silently dropped.
- HTFT always contains nine states. An unavailable official Half-Full market is an odds availability state, not a reason to fabricate a payload.
- Score matrix support is declared. Every cell in the declared support is numeric; a tail policy is explicit when finite support does not cover all scores. Top candidates are selected from the matrix and cannot rewrite it.
- `btts_probability`, clean-sheet probabilities, lambdas, confidence intervals, and risk scores use their own declared units and ranges; none is a substitute for a market probability or recommendation state.

### 3.2 Simulation, consensus, uncertainty, and risk

Simulation must preserve a positive integer `runs`, explicit `seed` (or `NOT_APPLICABLE` only for a deterministic simulation), exact `simulation_version`, input hash, aggregate distributions, and named match scripts. It is an evidence layer, not outcome truth.

Consensus must retain every contributing engine run reference, vote/support records, conflict details, and a numeric `consensus_score`. A simple averaged value without the underlying disagreement is invalid.

Uncertainty must separate components such as data quality, context, market conflict, disagreement, entropy, simulation variance, calibration reliability, missing evidence, and league sample quality. `grade` and `confidence_interval` do not alter raw probabilities.

Risk must retain each risk flag, severity, evidence/engine refs, and `abstention_state`. Risk may cause `BLOCKED` or `NO_STRONG_RECOMMENDATION`; it may not force a strong recommendation.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000601",
  "engine_run_id": "019a0000-0000-7000-8000-000000000601",
  "contract_version": "engine-output@1.0.0",
  "created_at": "2026-09-01T12:50:00+08:00",
  "source_timestamp": "2026-09-01T12:00:00+08:00",
  "observed_at": "2026-09-01T12:50:00+08:00",
  "ingested_at": "2026-09-01T12:50:01+08:00",
  "source": "JCFB V4 outcome engine",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/engines/outcome/4.0.0/r001/run-001",
  "confidence": {"state": "ASSESSED", "score": 0.90, "basis": "Versioned feature bundle and all input gates passed"},
  "provenance_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "payload_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
  "status": "SUCCEEDED",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at", "runtime_ms"]},
  "role": "PRODUCTION",
  "model_name": "outcome-model",
  "model_version": "outcome-model@4.0.0",
  "engine_name": "outcome_engine",
  "engine_version": "outcome-engine@4.0.0",
  "revision": "r001",
  "shadow_revision": "NOT_APPLICABLE",
  "experiment_revision": "NOT_APPLICABLE",
  "implementation_hash": "sha256:1212121212121212121212121212121212121212121212121212121212121212",
  "config_version": "outcome-engine-config@4.0.0",
  "config_hash": "sha256:3434343434343434343434343434343434343434343434343434343434343434",
  "schema_version": "engine-output-schema@1.0.0",
  "input_hash": "sha256:5656565656565656565656565656565656565656565656565656565656565656",
  "frozen_input_id": "019a0000-0000-7000-8000-000000000401",
  "frozen_input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "prediction_cutoff_at": "2026-09-01T12:00:00+08:00",
  "kickoff_at": "2026-09-01T19:35:00+08:00",
  "run_at": "2026-09-01T12:50:00+08:00",
  "run_completed_at": "2026-09-01T12:50:00.012+08:00",
  "runtime_ms": 12,
  "runtime_environment": {"runtime": "declared-runtime@1.0.0", "dependency_lock_hash": "sha256:7878787878787878787878787878787878787878787878787878787878787878"},
  "warnings": [],
  "errors": [],
  "payload": {
    "market": "spf",
    "outcome_probability": {"H": 0.52, "D": 0.26, "A": 0.22},
    "normalization_error": 0.0,
    "feature_bundle_ref": {"feature_bundle_id": "019a0000-0000-7000-8000-000000000501", "feature_hash": "sha256:9999999999999999999999999999999999999999999999999999999999999999"}
  },
  "output_hash": "sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
}
```

## 5. Validation rules

### Envelope and type checks

- Every field in section 2 marked required, every common required metadata field, and the engine-specific minimum payload are present.
- Hashes match `sha256:<64 lowercase hex>` and are recomputable. `implementation_hash`, `config_hash`, `input_hash`, and `output_hash` are distinct identities even when a test fixture happens to use the same format.
- `runtime_ms >= 0`, `run_completed_at >= run_at`, and `runtime_environment` contains no secret/token/cookie/password values.
- `status=SUCCEEDED` requires a valid payload and empty errors; `FAILED`/`BLOCKED`/`INVALID` requires a structured error and must not return a fabricated successful probability.
- The role is explicit and matches the role-scoped revision. A path or filename cannot supply the role.

### Payload and referential checks

- The engine name selects exactly one payload schema; an Outcome payload cannot be labeled as Score or Consensus.
- Every referenced Feature Bundle/Frozen Input/model/config identity resolves to the stated hash/version.
- Probabilities and intervals pass range/sum checks; score matrices and tail policy reconcile; nine HTFT states exist; simulation runs/seed/version are present when applicable.
- Consensus preserves individual engine output references and conflicts. Risk preserves flags and abstention state. Uncertainty preserves components and confidence interval.

### Time and no-future-leakage checks

- Pre-match `prediction_cutoff_at < kickoff_at`; all source availability times in the Frozen Input are at or before cutoff.
- A post-kickoff result, event, xG, red card, final score, post-match lineup, or future odds in an engine input sets `future_information_leakage=true`, `status=INVALID`, and `TIER_A_ELIGIBLE=false`.
- `run_at`/`run_completed_at` are execution times and cannot be substituted for source availability. A run completed after kickoff cannot be represented as a valid pre-match Shadow run.

### Role checks

- Production is the only role with formal public authority.
- Shadow is evidence-only and cannot write Production, Frozen Prediction, confidence, review, Tier A, or public projection.
- Experiment cannot enter public output, cannot count as Forward Tier A, and cannot be renamed Shadow after the fact.
- Production and Shadow A/B engine outputs must reference the same `frozen_input_hash`; mismatch is `PAIR_INVALID` and promotion evidence is false.

## 6. Hash and compatibility boundary

`output_hash` includes the logical envelope identity, role/version/revision references, input hash, engine payload, warnings/errors that affect interpretation, and declared references. It excludes `created_at`, `ingested_at`, `run_at`, `run_completed_at`, `runtime_ms`, transport headers, and non-authoritative trace metadata by default. `input_hash` includes the frozen input ref/hash, cutoff, role, component versions, and feature references.

Adding an optional payload annotation is `MINOR`; changing envelope field meaning/requiredness, role semantics, probability keys, distribution support, hash boundary, or no-future rules is `MAJOR`; documentation-only clarification is `PATCH`. A behavior/config/implementation change still requires a new revision and forward evidence even if the schema change is additive.

## 7. Pre-Frozen feature artifact boundary

`engine-output@1.0.0` remains the formal contract for an Engine Run. It is not
the creation contract for V4-044 Football Intelligence Feature Generation or
V4-045 Context Integration. Those tasks produce pre-Frozen artifacts under
`football-intelligence-feature@1.0.0` and
`football-context-integration@1.0.0`, which bind directly to accepted upstream
Feature Bundle, statistical feature, Team Context, and Evidence Graph
references. A pre-Frozen artifact does not require or contain
`frozen_input_id`/`frozen_input_hash` and must not be presented as a formal
Prediction, Score, Risk, Consensus, or other Engine Run. V4-076 is the sole
task that creates the pre-prediction Frozen Input boundary and is consumed by
formal Engine Runs after the freeze.
