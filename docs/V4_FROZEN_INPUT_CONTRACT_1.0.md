# JCFB V4 Frozen Input Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and immutability

Frozen Input is the immutable boundary for a formal V4 pre-match run. It records exactly which canonical identity, official odds, external market observations, team context, evidence, feature schema, cutoff, and model/engine registry identities were accepted. It is formed before formal engine execution and is the only input identity that can establish a valid Production/Shadow A/B pair.

This contract is design-only. It does not freeze a live match, write a database, execute an engine, or authorize Production or Shadow execution.

After formation, a Frozen Input is immutable. A correction or a changed source creates a new append-only `frozen_input_revision`, new `frozen_input_id` when the logical object changes, and new hashes. The old record remains available for replay and audit.

## 2. Required fields

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `frozen_input_id` | UUID/UUIDv7 | REQUIRED | Stable immutable identity. |
| `contract_version` | string | REQUIRED | `frozen-input@MAJOR.MINOR.PATCH`. |
| `frozen_input_revision` | `fi-YYYYMMDD-NNNNNN` | REQUIRED | Immutable append-only revision under V4-006. |
| `canonical_match_identity_ref` | stable ref | REQUIRED | Exact `match_id` plus canonical facts hash. |
| `official_odds_snapshot_refs` | non-empty array of stable refs | REQUIRED | Exact official snapshot IDs/hashes used by the run, including an explicit all-unavailable snapshot when no market is open. |
| `external_market_snapshot_refs` | array of stable refs | REQUIRED | May be empty only with an explicit `UNAVAILABLE` state/reason; never silently omitted. |
| `team_context_ref` | stable ref | REQUIRED | Exact Team Context object/hash; an unknown context still requires an explicit context object. |
| `evidence_bundle_ref` | stable ref | REQUIRED | Versioned Evidence Bundle identity/hash and cutoff scope. |
| `feature_schema_version` | qualified version | REQUIRED | Schema identity expected by the feature generator. |
| `prediction_cutoff_at` | timezone-aware timestamp | REQUIRED | Declared last eligible pre-match source boundary. |
| `kickoff_at` | timezone-aware timestamp | REQUIRED | Must match Canonical Match Identity. |
| `model_version_registry_refs` | non-empty array | REQUIRED | Exact model identities allowed for the consuming run. |
| `engine_version_registry_refs` | non-empty array | REQUIRED | Exact independent engine identities allowed for the consuming run. |
| `config_version_registry_refs` | non-empty array | REQUIRED | Exact effective configuration identities; secret values are never stored. |
| `dataset_version` / `schema_version` | qualified versions | REQUIRED | Dataset and Frozen Input shape identities. |
| `ab_comparison_group_id` | stable ID/state | CONDITIONAL | Required for a Production/Shadow comparison; the same group must point to the same hash. |
| `frozen_at` | timezone-aware timestamp | REQUIRED | Time the input was sealed. |
| `frozen_input_hash` | SHA-256 string | REQUIRED | Hash of the exact immutable Frozen Input logical payload. |
| `status` | `FROZEN`, `SUPERSEDED`, or `BLOCKED` | REQUIRED | `FROZEN` is usable only after all gates pass. |
| `immutable` | boolean | REQUIRED | Must be `true` after formation. |
| common metadata | typed metadata | REQUIRED | Source/provenance/status/hash lineage. |

The Frozen Input does not include a runtime `role` in its logical hash. This is intentional: a valid Production/Shadow A/B pair uses one substantive frozen pre-match input. Role, engine, and run identity belong to Engine Output and Prediction envelopes, whose `input_hash` values may differ by role and component.

## 3. Reference and time rules

1. `canonical_match_identity_ref` resolves to exactly one `match_id`; display names and official match numbers are insufficient.
2. Every official odds reference resolves to an exact `snapshot_id`, `snapshot_hash`, and availability map. An unavailable official market remains explicit and is never replaced by external odds.
3. `external_market_snapshot_refs` are optional in substance but required as an explicit array/state. External data is always marked non-official.
4. `team_context_ref` and `evidence_bundle_ref` must be cut off at or before `prediction_cutoff_at` for a pre-match run.
5. `feature_schema_version`, model/engine/config registry refs, and dataset/schema versions are exact identities, not `latest`, `current`, or `default` aliases.
6. `prediction_cutoff_at < kickoff_at`, and every defensible source availability time in the referenced bundle must be `<= prediction_cutoff_at`.
7. `frozen_at` may be later than `prediction_cutoff_at` because computation can seal an already accepted input later; this does not allow new source information after the cutoff.
8. A Production/Shadow A/B pair is valid only when `canonical_match_identity_ref`, `prediction_cutoff_at`, and `frozen_input_hash` are identical. Different `input_hash` values are allowed because role and component identity are included in the engine envelope.
9. An Experiment may use a different Frozen Input, but it must declare `comparison_mode=EXPERIMENT_ONLY` and cannot be counted as a Forward Shadow pair.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000401",
  "frozen_input_id": "019a0000-0000-7000-8000-000000000401",
  "contract_version": "frozen-input@1.0.0",
  "created_at": "2026-09-01T12:30:00+08:00",
  "source_timestamp": "2026-09-01T12:20:00+08:00",
  "observed_at": "2026-09-01T12:25:00+08:00",
  "ingested_at": "2026-09-01T12:30:01+08:00",
  "effective_at": "2026-09-01T12:30:00+08:00",
  "source": "JCFB V4 governed freeze assembly",
  "source_type": "DERIVED_SYSTEM",
  "source_reference": "ref://v4/freeze-assembly/20260901/001/123000",
  "confidence": {"state": "ASSESSED", "score": 0.93, "basis": "All references resolved and cutoff gate passed"},
  "provenance_hash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "payload_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "status": "FROZEN",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "frozen_input_revision": "fi-20260901-000001",
  "canonical_match_identity_ref": {
    "match_id": "019a0000-0000-7000-8000-000000000002",
    "payload_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "official_odds_snapshot_refs": [
    {
      "snapshot_id": "019a0000-0000-7000-8000-000000000101",
      "snapshot_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
    }
  ],
  "external_market_snapshot_refs": [
    {
      "snapshot_id": "019a0000-0000-7000-8000-000000000102",
      "snapshot_hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    }
  ],
  "team_context_ref": {
    "team_context_id": "019a0000-0000-7000-8000-000000000201",
    "payload_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222"
  },
  "evidence_bundle_ref": {
    "evidence_bundle_id": "019a0000-0000-7000-8000-000000000302",
    "bundle_hash": "sha256:7777777777777777777777777777777777777777777777777777777777777777"
  },
  "feature_schema_version": "feature-bundle@1.0.0",
  "prediction_cutoff_at": "2026-09-01T12:00:00+08:00",
  "kickoff_at": "2026-09-01T19:35:00+08:00",
  "model_version_registry_refs": ["outcome-model@4.0.0#r001"],
  "engine_version_registry_refs": ["outcome-engine@4.0.0#r001", "score-engine@4.0.0#r001"],
  "config_version_registry_refs": ["v4-pre-match-config@1.0.0#r001"],
  "dataset_version": "pre-match-facts@1.0.0#r001",
  "schema_version": "frozen-input-schema@1.0.0",
  "ab_comparison_group_id": "ab-20260901-000001",
  "comparison_mode": "FORWARD_AB_ELIGIBLE",
  "frozen_at": "2026-09-01T12:30:00+08:00",
  "frozen_input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "immutable": true,
  "supersedes_frozen_input_id": "NOT_APPLICABLE"
}
```

## 5. Validation rules

### Required, referential, and hash checks

- All fields marked required and all common required metadata exist; arrays are present even when an explicit state says no external source is available.
- Every reference resolves to the exact object and hash named. A match display name, official number, or “latest snapshot” label is not a valid reference.
- The referenced official snapshot is `source_is_official=true`; external references are `source_is_official=false`.
- `frozen_input_hash`, `payload_hash`, and `provenance_hash` are format-valid and recomputable. `payload_hash` equals the declared Frozen Input hash boundary.
- `immutable=true` and `status=FROZEN` are required for a usable formal input. `BLOCKED` or `SUPERSEDED` objects remain auditable but cannot feed a new formal run.

### Timestamp and no-future-leakage checks

- `prediction_cutoff_at` and `kickoff_at` are timezone-aware and satisfy cutoff < kickoff.
- Every referenced source/evidence availability time is `<= prediction_cutoff_at`; `ingested_at` alone never proves eligibility.
- Official odds after cutoff, post-kickoff lineup/events/results, or post-match evidence cause `future_information_leakage=true`, `status=BLOCKED`, and an invalid downstream run. The offending references remain append-only.
- A later correction never mutates this object. It creates a new revision and new hash; old engine/prediction lineage still points to the old Frozen Input.

### Role and A/B checks

- Production and Shadow paired runs use the same `frozen_input_hash` and `ab_comparison_group_id`; otherwise `PAIR_INVALID=true` and promotion evidence is false.
- An Experiment must declare `EXPERIMENT_ONLY` when it uses a different input. It cannot be relabeled Shadow after kickoff or after the result.
- Frozen Input contains no V3.3.3 prediction/model output, confidence, review, or Tier A label.

## 6. Hash and compatibility boundary

The Frozen Input hash includes canonical match identity reference/hash, official and external snapshot refs/hashes, team context and evidence bundle refs/hashes, feature schema, cutoff/kickoff, version registry refs, dataset/schema versions, comparison group/mode, and supersession identity. It excludes transport-only creation/ingestion timestamps and non-authoritative trace metadata.

Adding an optional provenance annotation is `MINOR`; changing what is frozen, changing cutoff semantics, changing A/B equality, allowing mutable updates, or changing a reference/hash meaning is `MAJOR`; documentation clarification is `PATCH`. `frozen_input_hash` is never reused for a different logical input.
