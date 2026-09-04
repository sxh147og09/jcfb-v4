# JCFB V4 BATCH-12 Football Intelligence Architecture & Feature Semantics Governance Decision

Decision ID: `V4-BATCH-12-ADR-001`
Status: **APPROVED GOVERNANCE RESOLUTION**
Decision date: `2026-09-04` (`Asia/Shanghai`)
Workspace: `F:\Projects\jcfb-v4`
Baseline HEAD: `17cdde4843ec6b6bd59cbe392952c37d87cc3d3e`

## 1. Decision

The BATCH-12 Entry Review blockers are resolved as one coordinated
architecture amendment. The decision does not implement V4-044 or V4-045 and
does not authorize BATCH-13, Prediction, Score Engine, Frozen Input, Shadow,
Production, Supabase, migration, or V3.3.3 work.

The approved BATCH-12 path is:

```text
BATCH-10 Feature Bundle
  + BATCH-11 Statistical Strength Features
    -> V4-044 Football Intelligence pre-Frozen generator
    -> V4-045 Football Context integration pre-Frozen generator
    -> BATCH-14 quality/tactical gates
    -> V4-076 downstream Frozen Input
    -> Prediction layers
```

## 2. Batch dependency resolution

The canonical batch-level upstream set is:

```text
BATCH-12 upstream = BATCH-10 + BATCH-11
```

The task-level graph remains:

```text
V4-040 + V4-043 -> V4-044 -> V4-045
```

The Batch Plan, Task Dependency Register, Dependency Graph, and Master Build
Checklist now carry the same authoritative override. No task IDs are added,
removed, or reassigned. The graph remains acyclic.

## 3. V4-044 and V4-045 lifecycle classification

V4-044 and V4-045 are formally classified as:

```text
PRE-FROZEN FEATURE GENERATORS
```

They create pre-Frozen feature artifacts and do not create formal Engine Runs.
They therefore do not use the `engine-output@1.0.0` formal run envelope and do
not require `frozen_input_id` or `frozen_input_hash` at creation time.

This is not a relaxation of the formal Engine Output Contract. The formal
contract remains applicable to later Prediction, Score, Risk, Consensus, and
other formal pre-match Engine Runs, where Frozen Input is required.

V4-076 remains downstream and must consume the exact Feature Bundle and
pre-Frozen feature lineage that is approved for freezing. No mock Frozen Input,
reverse dependency, or silent omission is allowed.

## 4. Active BATCH-12 governance artifacts

| Artifact | Version | Scope |
|---|---|---|
| Football Intelligence Feature Contract | `football-intelligence-feature@1.0.0` | V4-044 pre-Frozen feature artifact |
| Football Context Integration Contract | `football-context-integration@1.0.0` | V4-045 pre-Frozen integration artifact |
| Football Intelligence Config | `football-intelligence-config@1.0.0` | Typed mappings and no-coefficient policy |
| Mapping Registry | `football-intelligence-mapping@1.0.0` | Numeric/categorical mapping identity |
| Team Context Contract | `team-context@2.0.0` | Canonical `context_confidence` field |

The active contract documents are:

- `docs/V4_FOOTBALL_INTELLIGENCE_FEATURE_CONTRACT.md`
- `docs/V4_FOOTBALL_CONTEXT_INTEGRATION_CONTRACT.md`
- `docs/V4_FOOTBALL_INTELLIGENCE_CONFIG.json`
- `docs/V4_TEAM_CONTEXT_CONTRACT.md`

The previous Team Context contract remains at
`docs/V4_TEAM_CONTEXT_CONTRACT_1.0.md` and is not overwritten.

## 5. Context-to-feature classification

### Type A: deterministic observable values

The initial config permits only explicit, source-backed, native-unit values:

- rest days
- matches in 7/14/30-day windows
- consecutive short-rest count
- travel distance
- timezone delta
- consecutive away count
- confirmed absence count
- confirmed availability count
- weather observations such as temperature, wind, precipitation, and humidity

Each mapping declares raw source, transformation, unit, normalization,
clipping, missing behavior, config identity, and mapping identity.

### Type B: categorical/state values

The initial config keeps the following structured and non-numeric:

- confirmed/projected/unknown lineup state
- coach change state
- tactical style
- formation
- motivation evidence state
- tactical matchup relation
- pitch state vocabulary

No arbitrary impact coefficient is authorized. Examples such as
`coach_quality=0.82`, `motivation_score=0.75`, `tactical_advantage=+0.20`, or
`projected_lineup*0.7` are forbidden in this version.

### Type C: non-consumable states

The following remain stateful and cannot be numericized:

```text
UNKNOWN, UNAVAILABLE, NOT_VERIFIED, CONFLICTED, STALE, FUTURE_DATA, BLOCKED
```

They are retained as states or block the derived feature. They are never
replaced by zero, mean, previous-match values, default values, or synthetic
payloads.

## 6. Availability and lineup governance

The following distinctions are mandatory:

```text
UNKNOWN != NONE_CONFIRMED
PROJECTED != CONFIRMED
NOT_VERIFIED != AVAILABLE
CONFLICTED != selected winner
STALE != current
BLOCKED != fallback value
```

Confirmed absence/availability counts can be emitted only from the explicitly
confirmed upstream collections. No player-importance score is invented unless
a future approved mapping provides one.

Projected lineup is a typed categorical feature. It cannot be assigned a
numeric discount in this version.

## 7. Coach, tactical, and motivation governance

Coach, tactical, formation, motivation, and tactical matchup data must retain:

- source references
- basis references
- attributed vocabulary or relation
- source/evidence state
- effective time
- feature quality

Rumor, narrative, or unverified interpretation cannot silently become an
objective fact or a numeric impact score.

## 8. Schedule, fatigue, travel, weather, and pitch governance

Observable schedule and travel measures use the versioned config. Composite
fatigue or impact indexes are not authorized unless a future config defines
their formula, weights, scale, clipping, and minimum observations.

Weather remains raw/native-unit where source support exists. Pitch remains
source-governed categorical vocabulary in this version; no severity threshold
is invented.

## 9. BATCH-11 interaction boundary

BATCH-12 may consume the exact BATCH-11 statistical feature references and
hashes. It may not overwrite or modify their values.

The approved interaction default is:

```text
SEPARATE_DIMENSIONS_ONLY
```

The approved interaction rule registry is empty. Injury × attack, tactics ×
home advantage, weather × defence, or any other interaction requires a new
versioned contract/config and independent evidence.

## 10. Evidence, conflict, and authority

BATCH-12 consumes Evidence Graph references but does not create a new source
authority ranking. Conflicting claims remain visible with all claims, sources,
timestamps, and hashes. Majority count or evidence count cannot silently
resolve a conflict.

Only a documented `RESOLVED` state from the approved Evidence Graph may be
treated as resolved input. Otherwise the feature remains conflicted,
not-verified, or blocked.

## 11. Confidence semantics

The Team Context active field is now exclusively:

```text
context_confidence
```

It describes coverage, verification, freshness, completeness, conflict, and
provenance quality. It is not a prediction probability, model confidence,
betting confidence, or recommendation grade.

Feature artifacts use `feature_quality`, not a bare `confidence` field. A
numeric `context_confidence.score` is not copied into `feature_quality`.

## 12. Time, hash, and append-only boundary

Every pre-Frozen artifact must prove:

```text
availability_at <= prediction_cutoff_at < kickoff_at
```

The substantive hash includes exact Feature Bundle snapshot hash, statistical
refs/hashes, Team Context refs/hashes, Evidence refs/hashes, cutoff/kickoff,
generator/config/mapping identities, and typed values/states. It excludes
Frozen Input IDs/hashes, prediction, recommendation, and transport metadata.

Corrections append a new artifact with a new identity/hash and an explicit
`supersedes_*` pointer. Existing artifacts are never overwritten.

## 13. Versioning and compatibility impact

The Team Context change is a breaking semantic change because the canonical
confidence field and accepted schema example are corrected. The active version
is therefore raised from `team-context@1.0.0` to `team-context@2.0.0`. The v1
document and historical objects remain preserved and immutable.

The three new BATCH-12 contracts/config identities are new versioned artifacts;
they do not overwrite another contract. Any future algorithm, coefficient,
threshold, unit, state meaning, required field, or hash-boundary change must
create a new identity under the V4 Versioning Standard.

## 14. Safety and persistence impact

- Migration added: **NO**
- Migration applied: **NO**
- Production/Supabase read: **NO**
- Production/Supabase write: **NO**
- Production runtime: **NO**
- Shadow/Tier A runtime: **NO**
- Prediction/Score Engine: **NO**
- Frozen Input/V4-076 implementation: **NO**
- BATCH-13: **NO**
- V3.3.3 modification: **NO**

All artifacts are repository-local governance/config/test artifacts under the
V4 workspace. No C-drive runtime/cache/output path is introduced.

## 15. Decision result

```text
BATCH-12 ARCHITECTURE BLOCKER RESOLVED
```

This decision authorizes a new BATCH-12 Scope & Entry Review. It does not by
itself authorize V4-044/V4-045 implementation. Implementation requires the
re-run Entry Review to pass.
