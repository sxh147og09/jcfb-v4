# JCFB V4 Football Intelligence Feature Contract 1.0

Status: **BATCH-12 GOVERNANCE RESOLUTION / PRE-FROZEN ARTIFACT CONTRACT**
Contract version: `football-intelligence-feature@1.0.0`
Task boundary: `V4-044`
Supersedes: none

## 1. Purpose and lifecycle boundary

V4-044 is a pre-Frozen feature-generation component. It creates an auditable
Football Intelligence Feature Artifact from accepted Feature Bundle,
statistical, Team Context, and Evidence Graph references. It is not a formal
Prediction Engine run and does not use the `engine-output@1.0.0` run envelope.

The governed flow is:

```text
Feature Bundle
  -> Statistical Strength Features
  -> Football Intelligence Feature Artifact
  -> Football Context Integration
  -> Quality / Provenance Gates
  -> Frozen Input
  -> Prediction Engines
```

`frozen_input_id` and `frozen_input_hash` are forbidden at this stage. V4-076
remains a downstream consumer and is not implemented by BATCH-12.

## 2. Required artifact envelope

| Field | Requiredness | Rule |
|---|---|---|
| `artifact_id` | REQUIRED | Stable immutable artifact identity. |
| `artifact_kind` | REQUIRED | Exact value `PRE_FREEZE_FEATURE_ARTIFACT`. |
| `contract_version` | REQUIRED | Exact `football-intelligence-feature@1.0.0`. |
| `feature_bundle_id` | REQUIRED | Accepted Feature Bundle identity. |
| `feature_bundle_ref` | REQUIRED | Contains `id` and exact `feature_snapshot_hash`. |
| `statistical_feature_refs` | REQUIRED | Exact BATCH-11 feature IDs and hashes; may be empty only when the declared feature set does not consume them. |
| `team_context_refs` | REQUIRED | Exact Team Context revision IDs and hashes. |
| `evidence_refs` | REQUIRED | Exact Evidence Graph IDs and hashes used as basis. |
| `canonical_entity_refs` | REQUIRED | Canonical match/team/side identity; display names are descriptive only. |
| `role` | REQUIRED | Explicit V4 namespace role; never inferred from path. |
| `generator_version` | REQUIRED | Exact implementation identity. |
| `config_version` / `config_hash` | REQUIRED | Exact BATCH-12 configuration identity. |
| `mapping_registry_version` | REQUIRED | Exact context-to-feature mapping registry. |
| `prediction_cutoff_at` / `kickoff_at` | REQUIRED | `availability_at <= prediction_cutoff_at < kickoff_at`. |
| `features` | REQUIRED | Typed numeric, categorical, or state features. |
| `feature_quality` | REQUIRED | Typed data-quality dimensions only; no numeric prediction confidence. |
| `input_hash` / `payload_hash` / `provenance_hash` | REQUIRED | Recomputable SHA-256 identities. |
| `revision` | REQUIRED | Positive append-only revision. |
| `supersedes_artifact_id` | CONDITIONAL | Required for a correction after the first revision. |

## 3. Typed feature record

Each feature record contains:

```json
{
  "feature_key": "rest_days",
  "category": "schedule",
  "kind": "NUMERIC",
  "state": "AVAILABLE",
  "value": 5,
  "unit": "days",
  "context_state": "CONFIRMED",
  "basis_refs": ["evidence-001"],
  "source_refs": ["context-001"],
  "derivation_ref": "football-intelligence-mapping@1.0.0/rest_days",
  "reason_code": null,
  "reason_detail": null
}
```

`AVAILABLE` requires a non-empty correctly typed value, a unit when
applicable, and resolvable source/basis references. Every other feature state
requires an explicit `reason_code` and `reason_detail`.

The non-consumable states are:

```text
UNKNOWN, UNAVAILABLE, NOT_VERIFIED, CONFLICTED, STALE, FUTURE_DATA, BLOCKED
```

They are never silently converted to zero, mean, previous-match value,
`AVAILABLE`, or a synthetic feature.

## 4. Context-to-feature classification

### Type A — deterministic observable features

Only values with explicit units, source observation semantics, and an approved
mapping in `football-intelligence-config@1.0.0` may be numeric. The first
approved registry contains native-unit schedule, travel, availability-count,
and weather observations. It defines transformation, missingness, and hash
identity without model-effect coefficients.

### Type B — structured categorical/state features

Coach context, tactical style, formation, motivation evidence, tactical
matchup, projected lineup, and qualitative availability remain typed
categorical/state values unless a later versioned model/config approves a
numeric mapping. BATCH-12 does not emit arbitrary `+0.1`, `-0.2`, or `*0.8`
impact values for these categories.

### Type C — non-consumable states

`UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`,
`FUTURE_DATA`, and `BLOCKED` remain visible and block or downgrade downstream
quality gates. They are not numeric substitutes.

## 5. Identity, evidence, and conflict rules

- Exactly one canonical match identity is required.
- Team and side references must resolve to the canonical match.
- Feature Bundle, statistical, Team Context, and Evidence refs retain exact IDs
  and hashes.
- Conflicting claims remain represented with all source and basis references.
- BATCH-12 has no source-authority ranking and cannot silently select a winner.
- Only a documented `RESOLVED` state from the approved Evidence Graph may be
  consumed as resolved context.
- Corrections append a new artifact with a new identity/hash and an explicit
  `supersedes_artifact_id`.

## 6. Confidence and quality

This contract has no bare `confidence` field. `feature_quality` describes only:

```text
coverage, verification, freshness, completeness, conflict, provenance
```

It cannot express win probability, model confidence, betting confidence,
recommendation grade, or engine output confidence. Team Context uses the
canonical `context_confidence` field; its score is not copied into
`feature_quality`.

## 7. Hash and replay boundary

The substantive artifact hash includes the exact Feature Bundle snapshot hash,
BATCH-11 refs/hashes, Team Context refs/hashes, Evidence refs/hashes,
cutoff/kickoff, generator/config/mapping versions, and typed feature values and
states. It excludes Frozen Input IDs/hashes, prediction, recommendation, and
transport-only runtime metadata.

The V4 canonical JSON/SHA-256 profile is used. Equal logical inputs and
identities must replay to equal hashes. A logical change creates a new
append-only revision.

## 8. Forbidden output boundary

The artifact must reject or never emit:

```text
prediction, recommendation, model_confidence, win_probability,
betting_confidence, score_selection, engine_output, lambda,
frozen_input_id, frozen_input_hash
```

V4-044 does not modify official odds, canonical facts, Team Context, Evidence
Graph claims, or BATCH-11 feature values.

## 9. Minimum legal JSON example

```json
{
  "artifact_id": "football-intelligence-artifact-001",
  "artifact_kind": "PRE_FREEZE_FEATURE_ARTIFACT",
  "contract_version": "football-intelligence-feature@1.0.0",
  "feature_bundle_id": "feature-bundle-001",
  "feature_bundle_ref": {"id": "feature-bundle-001", "feature_snapshot_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111"},
  "statistical_feature_refs": [{"id": "statistical-feature-001", "hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222"}],
  "team_context_refs": [{"id": "team-context-001", "hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333"}],
  "evidence_refs": [{"id": "evidence-001", "hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444"}],
  "canonical_entity_refs": {"match_id": "match-001", "home_team_id": "team-home-001", "away_team_id": "team-away-001"},
  "role": "EXPERIMENT",
  "generator_version": "football-intelligence-generator@1.0.0",
  "config_version": "football-intelligence-config@1.0.0",
  "config_hash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "mapping_registry_version": "football-intelligence-mapping@1.0.0",
  "prediction_cutoff_at": "2026-09-04T12:00:00+08:00",
  "kickoff_at": "2026-09-04T19:35:00+08:00",
  "features": [{"feature_key": "rest_days", "category": "schedule", "kind": "NUMERIC", "state": "AVAILABLE", "value": 5, "unit": "days", "context_state": "CONFIRMED", "basis_refs": ["evidence-001"], "source_refs": ["team-context-001"], "derivation_ref": "football-intelligence-mapping@1.0.0/rest_days", "reason_code": null, "reason_detail": null}],
  "feature_quality": {"coverage": "COMPLETE", "verification": "VERIFIED", "freshness": "CURRENT", "completeness": "COMPLETE", "conflict": "NONE", "provenance": "RESOLVED"},
  "input_hash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "payload_hash": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
  "provenance_hash": "sha256:8888888888888888888888888888888888888888888888888888888888888888",
  "revision": 1,
  "supersedes_artifact_id": null
}
```
