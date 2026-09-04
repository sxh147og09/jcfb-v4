# JCFB V4 Football Context Integration Contract 1.0

Status: **BATCH-12 GOVERNANCE RESOLUTION / PRE-FROZEN INTEGRATION CONTRACT**
Contract version: `football-context-integration@1.0.0`
Task boundary: `V4-045`

## 1. Purpose and boundary

V4-045 integrates the accepted V4-044 Football Intelligence Feature Artifact
with typed Team Context and BATCH-11 statistical references. It is a
pre-Frozen context feature artifact, not a Prediction Engine, Market
Intelligence Engine, Score Engine, or Frozen Input.

The output is limited to structured football/context features, source/basis
references, quality dimensions, conflict states, and deterministic lineage.

## 2. Required integration envelope

| Field | Requiredness | Rule |
|---|---|---|
| `integration_id` | REQUIRED | Stable immutable identity. |
| `contract_version` | REQUIRED | Exact `football-context-integration@1.0.0`. |
| `football_intelligence_artifact_ref` | REQUIRED | Exact V4-044 ID and hash. |
| `feature_bundle_ref` | REQUIRED | Exact Feature Bundle ID and snapshot hash. |
| `canonical_entity_refs` | REQUIRED | Match/team/side identity. |
| `team_context_refs` | REQUIRED | Exact Team Context revisions/hashes. |
| `statistical_feature_refs` | REQUIRED | Exact BATCH-11 refs/hashes used. |
| `evidence_refs` | REQUIRED | Basis evidence refs/hashes. |
| `prediction_cutoff_at` / `kickoff_at` | REQUIRED | No-future boundary. |
| `config_version` / `config_hash` | REQUIRED | Exact BATCH-12 config. |
| `mapping_registry_version` | REQUIRED | Exact mapping registry. |
| `features` | REQUIRED | Typed integrated feature records. |
| `feature_quality` | REQUIRED | Data quality only. |
| `input_hash` / `output_hash` / `provenance_hash` | REQUIRED | Recomputable identities. |
| `revision` | REQUIRED | Append-only revision. |
| `supersedes_integration_id` | CONDITIONAL | Required for correction. |

`frozen_input_id` and `frozen_input_hash` are forbidden. This contract is not
the `engine-output@1.0.0` formal run contract.

## 3. Integration semantics

- BATCH-11 statistical values are consumed by reference and cannot be
  overwritten or modified by BATCH-12.
- Team Context values remain separate dimensions unless an approved mapping in
  `football-intelligence-config@1.0.0` exists.
- The current approved interaction rule is
  `SEPARATE_DIMENSIONS_ONLY`; the interaction rule registry is empty.
- No injury, tactical, weather, travel, or context value receives a model-effect
  coefficient in this contract.
- Numeric features must retain raw unit, transformation, normalization, and
  missing-state behavior.
- Categorical/state features retain their source vocabulary and evidence.
- `PROJECTED` never becomes `CONFIRMED`.
- `UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`,
  `FUTURE_DATA`, and `BLOCKED` are never numericized.

## 4. Context families

The initial mapping registry permits native-unit observable values for schedule,
travel, confirmed availability counts, and weather observations. Coach,
tactical style, formation, motivation, projected lineup, tactical matchup, and
qualitative availability remain categorical/state values unless a later major
or minor contract/config explicitly authorizes a mapping.

Pitch values remain source-governed vocabulary values. No pitch severity
threshold is invented in this version.

## 5. Evidence and conflict handling

Every derived feature retains basis refs and source refs. Conflicting claims
retain all claims and their Evidence Graph state. V4-045 has no authority to
rank sources, resolve contradictions, or silently choose the majority claim.
Only an already documented `RESOLVED` evidence state may be consumed as
resolved; otherwise the state remains visible or the feature is blocked.

## 6. Time and replay

All accepted inputs must satisfy:

```text
availability_at <= prediction_cutoff_at < kickoff_at
```

Post-cutoff, post-kickoff, ambiguous, or unprovable data is not usable as a
normal pre-match feature. The full accepted reference/hash set, cutoff,
generator/config/mapping versions, typed values, states, and lineage determine
the deterministic hash. Corrections create a new revision with a supersedes
pointer.

## 7. Forbidden downstream leakage

V4-045 must not emit or consume as its own output:

```text
prediction, probability, recommendation, score selection, lambda,
expected score, model confidence, betting confidence, risk decision,
official-odds rewrite, Frozen Input, Shadow/Tier A, or Public projection
```

Risk flags, if carried from an attributed context interpretation, remain typed
context evidence and cannot become a recommendation or prediction.

## 8. Minimum legal JSON example

```json
{
  "integration_id": "football-context-integration-001",
  "contract_version": "football-context-integration@1.0.0",
  "football_intelligence_artifact_ref": {"id": "football-intelligence-artifact-001", "hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111"},
  "feature_bundle_ref": {"id": "feature-bundle-001", "feature_snapshot_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222"},
  "canonical_entity_refs": {"match_id": "match-001", "home_team_id": "team-home-001", "away_team_id": "team-away-001"},
  "team_context_refs": [{"id": "team-context-001", "hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333"}],
  "statistical_feature_refs": [{"id": "statistical-feature-001", "hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444"}],
  "evidence_refs": [{"id": "evidence-001", "hash": "sha256:5555555555555555555555555555555555555555555555555555555555555555"}],
  "prediction_cutoff_at": "2026-09-04T12:00:00+08:00",
  "kickoff_at": "2026-09-04T19:35:00+08:00",
  "config_version": "football-intelligence-config@1.0.0",
  "config_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "mapping_registry_version": "football-intelligence-mapping@1.0.0",
  "features": [{"feature_key": "lineup_state", "category": "lineup", "kind": "CATEGORICAL", "state": "AVAILABLE", "value": "PROJECTED_LINEUP", "unit": "category", "context_state": "PROJECTED", "basis_refs": ["evidence-001"], "source_refs": ["team-context-001"], "derivation_ref": "football-intelligence-mapping@1.0.0/lineup_state", "reason_code": null, "reason_detail": null}],
  "feature_quality": {"coverage": "PARTIAL", "verification": "PARTIAL", "freshness": "CURRENT", "completeness": "PARTIAL", "conflict": "NONE", "provenance": "RESOLVED"},
  "input_hash": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
  "output_hash": "sha256:8888888888888888888888888888888888888888888888888888888888888888",
  "provenance_hash": "sha256:9999999999999999999999999999999999999999999999999999999999999999",
  "revision": 1,
  "supersedes_integration_id": null
}
```
