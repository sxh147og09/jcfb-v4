# JCFB V4 Prediction Input & Feature Profile Contract 1.0

Status: **BATCH-15 ARCHITECTURE GOVERNANCE / ACTIVE / IMPLEMENTATION NOT STARTED**
Contract version: `prediction-input@1.0.0`
Profile version: `engine-feature-profile@1.0.0`

## 1. Immutable input identity

The formal input envelope requires `frozen_input_id`, `frozen_input_hash`,
`feature_bundle_id`, `feature_bundle_hash`, `feature_snapshot_hash`,
`gate_record_id`, `gate_record_hash`, `prediction_cutoff_at`, `kickoff_at`,
dataset/schema versions, feature state, and exact source revisions. It also
retains exact references and hashes for BATCH-11 statistical, BATCH-12
football/context, BATCH-13 market, and BATCH-14 tactical artifacts.

The Feature Bundle and every domain artifact remain independent immutable
references. The engine input includes an exact `feature_subset` selected by
the registered engine profile, not a fresh read of raw upstream sources.

## 2. Per-engine profile matrix

| Engine | Required feature families | Optional feature families | Required market identity | Forbidden shortcut |
|---|---|---|---|---|
| Outcome | statistical, football, market, tactical, gate | profile-declared context fields only | SPF availability when used | copying another market |
| Handicap | statistical, football, market, tactical, gate, official RQSPF identity | profile-declared context fields only | official handicap value and availability | Outcome decision or external Asian handicap substitution |
| Goals | statistical, football, market, tactical, gate | profile-declared context fields only | official Total Goals availability when used | deriving from Outcome probability |
| HTFT | statistical, football, market, tactical, gate, half/full context | profile-declared context fields only | official Half-Full availability when used | half-time heuristic plus final SPF shortcut |

Required and optional fields, missing-state allowances, and exact feature names
must be registered in the model artifact manifest. `PARTIALLY_ELIGIBLE` is
consumable only when the specific profile says every missing item is optional
and in an allowed state. A missing required item is not silently imputed.

## 3. Run boundary

An Engine Run is admitted only after V4-076 has produced an immutable Frozen
Input and after the selected model artifact and engine profile resolve to
exact versions and hashes. BLOCKED, INELIGIBLE, unsupported PARTIAL, missing
hash, future-data, or cutoff-invalid inputs fail closed.
