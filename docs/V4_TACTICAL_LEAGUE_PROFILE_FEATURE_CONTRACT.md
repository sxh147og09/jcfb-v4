# JCFB V4 Tactical & League Profile Feature Contract 1.0

Status: **BATCH-14 ARCHITECTURE GOVERNANCE / ACTIVE**  
Contract version: `tactical-league-profile-feature@1.0.0`  
Lifecycle: **PRE_PREDICTION_PRE_FREEZE**

## 1. Purpose and boundary

This contract governs V4-049. It creates typed tactical matchup relations,
league tactical/context profiles, and source/conflict annotations from accepted
Feature Bundle, Football Context Integration, and Evidence Graph references.
It does not create a Prediction, Score Engine output, recommendation, risk
decision, or Frozen Input.

The approved flow is:

```text
Feature Bundle + Football Context + Evidence Graph
    -> V4-049 Tactical / League Profile Features
    -> V4-050 Quality Assessment
    -> V4-051 Provenance / Quality Gate
    -> downstream preparation
```

V4-049 does not replace or modify BATCH-11 Statistical League Strength. A
league statistical strength feature and a league tactical/context profile are
different feature semantics and retain separate identities and hashes.

## 2. Required artifact envelope

Every artifact must contain:

- `artifact_id`, `artifact_kind=PRE_FREEZE_TACTICAL_LEAGUE_PROFILE`;
- exact `contract_version=tactical-league-profile-feature@1.0.0`;
- canonical match/team/side references;
- exact Feature Bundle, Football Context, and Evidence Graph IDs and hashes;
- `prediction_cutoff_at` and `kickoff_at` with the V4-022 relationship;
- `generator_version`, `config_version`, `config_hash`, and `mapping_registry_version`;
- typed `features` and explicit `feature_quality` dimensions;
- `input_hash`, `payload_hash`, `provenance_hash`, and `output_hash`;
- positive `revision` and conditional `supersedes_artifact_id`.

Missing identity, source/basis reference, required hash, or time boundary is
`BLOCKED`; no display name, empty value, or default may substitute for it.

## 3. Allowed feature representation

The first active version permits only typed categorical or relational values
from an approved vocabulary/mapping, including:

- style relation;
- formation relation;
- press/build-up relation;
- width/transition relation;
- tactical matchup relation;
- league tactical/context profile;
- competition/league context;
- source and conflict annotations.

Without a separately approved model-affecting contract, the artifact must not
emit a tactical advantage score, matchup impact coefficient, league adjustment
multiplier, feature importance weight, or prediction-oriented tactical score.

## 4. State, evidence, and quality

Each feature carries `value`, `state`, `basis_refs`, `source_refs`, and a
`reason_code`/`reason_detail` when it is not consumable. `UNKNOWN`,
`UNAVAILABLE`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`, `FUTURE_DATA`, and
`BLOCKED` remain explicit. They cannot be converted to zero, mean, prior-match
value, `AVAILABLE`, or a guessed relation.

Conflicting claims retain all source and basis references. V4-049 has no
authority-ranking or silent winner-selection rule. Only an upstream approved
`RESOLVED` evidence state may be represented as resolved.

`feature_quality` is limited to coverage, verification, freshness,
completeness, conflict, and provenance. It is not win probability, model
confidence, betting confidence, recommendation grade, or abstention.

## 5. Interaction, time, and lifecycle

The default interaction policy is `SEPARATE_DIMENSIONS_ONLY`; no cross-domain
rules are approved in this version. V4-049 cannot numerically combine
Statistical Strength, Football Intelligence, or Market Intelligence values.

All source/effective/availability times must prove:

```text
input_availability_at <= prediction_cutoff_at < kickoff_at
```

Post-cutoff, post-kickoff, stale, ambiguous, or unreproducible inputs remain
non-consumable or blocked according to the Quality Gate Matrix.

Corrections append a new artifact identity, hash, revision, and explicit
`supersedes_artifact_id`; the prior artifact remains immutable and readable.

The substantive hash covers exact upstream references/hashes, typed feature
states and values, cutoff/kickoff, contract/config/mapping identities, and
lineage. Frozen Input IDs/hashes and Prediction fields are excluded because
Frozen Input is downstream.

## 6. Forbidden output

The artifact must reject or never emit:

```text
prediction, recommendation, model_confidence, win_probability,
betting_confidence, selection, risk_decision, engine_output,
frozen_input_id, frozen_input_hash, tactical_advantage_score,
matchup_impact, league_adjustment_multiplier
```
