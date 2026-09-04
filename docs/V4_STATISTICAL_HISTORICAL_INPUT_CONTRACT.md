# JCFB V4 Statistical Historical Input Contract 1.0

Status: V4-011 GOVERNANCE AMENDMENT
Contract version: `historical-statistical-input@1.0.0`
Owner: JCFB V4 Statistical Strength Governance

## 1. Purpose and boundary

This contract defines how a completed source match may contribute an objective historical observation to a later target match's pre-match Statistical Strength Feature generation.

The source match lifecycle and the target run eligibility are separate dimensions:

```text
source match S
  -> Official Result / historical statistic
  -> source-match POSTMATCH_ONLY lifecycle
  -> known, attributable, immutable observation revision
  -> target-scoped historical input manifest for match T
  -> target cutoff eligibility
  -> V4-041 / V4-042 / V4-043 statistical feature generation
```

`POSTMATCH_ONLY` remains true for the observation relative to its own `source_match_id`. It does not mean that the observation can never be used for a later target match. It may be reused only through this target-scoped contract. The observation is not copied into the target match's ordinary pre-match fact record.

This contract creates no prediction, recommendation, model interpretation, Score Engine output, Frozen Input, Shadow evidence, or Production artifact.

## 2. Historical eligibility predicate

For every observation selected for `target_match_id`, all conditions below are required:

```text
source_match_id != target_match_id
source_match_identity is canonical and resolvable
target_match_identity is canonical and resolvable
observation source and evidence are attributable
availability_at <= target_prediction_cutoff_at < target_kickoff_at
observation revision/hash was visible and reproducible at target cutoff
observation is not FUTURE_DATA relative to target cutoff
no post-cutoff correction replaces the revision visible at target cutoff
```

If any condition cannot be proven, the historical input is `BLOCKED` or `NOT_VERIFIED` and the observation cannot produce an ordinary numeric feature.

`retrieved_at` and `ingested_at` are audit fields only. They cannot be used to infer that an observation was historically available.

## 3. Target-match leakage prohibition

The target match's own following records are never eligible historical inputs for that target:

- Official Result
- final score
- post-match xG
- post-match shots or shots on target
- post-match possession
- post-match event statistics
- review, reconciliation, calibration, or error-attribution output

This remains true even if the generator is run after kickoff. Eligibility is replayed against the recorded `target_prediction_cutoff_at`, not wall-clock execution time.

## 4. Historical observation object

Each observation in a target-scoped manifest must retain:

| Field | Rule |
|---|---|
| `historical_input_id` | Stable UUID identity for the target-scoped manifest |
| `contract_version` | Exact `historical-statistical-input@1.0.0` |
| `source_match_id` | Canonical completed source match; never the target match |
| `target_match_id` | Canonical target match used for eligibility |
| `source_match_identity_hash` | Exact source match revision/hash |
| `target_match_identity_hash` | Exact target match revision/hash |
| `team_id` | Canonical team identity receiving the observation |
| `competition_id` | Canonical competition identity |
| `season_id` | Explicit season identity; unknown season blocks formal use |
| `side` | `HOME`, `AWAY`, or `NEUTRAL` as observed for the source match |
| `observation_type` | Governed type such as `OFFICIAL_RESULT`, `GOALS_FOR`, `GOALS_AGAINST`, `POINTS`, `XG`, `SHOTS`, or `SHOTS_ON_TARGET` |
| `value` / `unit` | Typed finite value and declared unit; no hidden conversion |
| `source` / `source_reference` | Attributable and replayable source identity |
| `evidence_refs` | Exact Evidence IDs and hashes when the value is evidence-backed |
| `source_published_at` | Source publication time when supplied |
| `source_event_at` | Time of the source match event/statistic |
| `result_known_at` | Time the result became known to the result path, when applicable |
| `stat_available_at` | Time the statistic became defensibly available |
| `published_at` / `observed_at` / `ingested_at` | Retained distinct; never collapsed |
| `availability_at` | Source-semantic eligibility time used by the target cutoff gate |
| `revision` / `supersedes_id` | Append-only correction lineage |
| `verification_state` | Explicit verification state; unresolved values are not ordinary inputs |
| `quality_state` | Explicit quality/missingness state |
| `payload_hash` / `provenance_hash` / `content_hash` | Recomputable exact hashes |

The manifest also retains `target_prediction_cutoff_at`, `target_kickoff_at`, exact observation IDs/revisions/hashes, sample counts, historical horizon, scope policies, and its own `input_hash`.

## 5. Approved historical data classes

The following may be consumed when the eligibility predicate and source contracts pass:

- Official Result and regulation-scoped outcome
- goals for and goals against
- historical league points/results where the competition contract supports them
- xG
- shots and shots on target
- other explicitly approved objective match statistics

The observation remains postmatch for its source match. A source statistic may not be treated as a fact about the target match.

The source object must be canonical or Evidence-backed, identity-bound, hashable, and attributable. A display name, copied spreadsheet row, unversioned API response, or post-cutoff reconstruction is not a legal input.

## 6. Minimum sample and sparse-data policy

The approved baseline configuration is `statistical-strength-config@1.0.0` with the following minimums:

| Feature family | Minimum eligible sample |
|---|---:|
| Dynamic team rating | 5 source matches per team |
| Attack / defence | 5 source matches per team |
| Home advantage scope | 20 eligible scope matches |
| Opponent adjustment | 5 eligible team/opponent observations |
| Form decay | 5 eligible team observations |
| League strength | 20 eligible competition-season matches |
| Promotion/relegation prior | 5 eligible prior observations plus an explicit transition mapping |

Below the applicable minimum, the feature has no numeric value and remains `UNKNOWN` with `reason_code=INSUFFICIENT_SAMPLE`; `feature_quality` is at most partial. A feature family that requires a proven transition mapping is `BLOCKED` when that mapping is absent.

The generator must retain usable, rejected, unknown, cutoff-excluded, conflict-excluded, and stale sample counts. It must not replace sparse data with zero, mean, previous value, league average, synthetic payload, or an undocumented prior.

## 7. Rolling window and recency policy

The approved baseline uses:

- at most the latest 20 eligible source matches by source kickoff order;
- a maximum historical horizon of 730 calendar days;
- deterministic tie-breaking by canonical `source_match_id`;
- exponential rank decay with `half_life_matches=10`;
- weights normalized only over retained eligible observations;
- no use of an observation outside the target cutoff, even if it is inside the calendar horizon.

The window, ordering, decay function, half-life, horizon, and normalization are configuration inputs and are included in `config_hash` and the generator input identity.

## 8. Competition, season, and league policy

- Same `competition_id` and same `season_id`: eligible when all source/time/quality gates pass.
- Same competition across seasons: requires the explicit cross-season transition policy and retains the season boundary.
- Different competitions: `BLOCKED` unless an approved `competition_mapping_ref` and translation policy are present.
- League and cup competitions are separate by explicit `competition_type`; no silent mixing.
- Unknown competition or season identity: `BLOCKED`.
- Promotion/relegation: raw prior ratings cannot be copied into a new competition. A promoted/relegated team requires an explicit transition state, `EXPLICIT_TRANSLATION_REQUIRED` league-strength translation policy, prior-history rule, and version/hash identity.

No league is assumed equal in strength to another league. No display-name mapping is a competition identity.

## 9. Units, normalization, and home/away semantics

- Source units are preserved exactly in the observation.
- Derived rate features use `per_eligible_match` and retain numerator, denominator, unit, and scope.
- Baselines are scoped to explicit `competition_id + season_id`; cross-competition scaling is blocked without an approved mapping.
- Standardization or other scaling is legal only with a versioned baseline, finite denominator, sufficient sample, and config/hash identity. Otherwise the feature is `UNKNOWN`.
- `HOME` and `AWAY` are source-match sides, not inferred from display order.
- Home advantage is calculated only within its declared sample scope and unit. A neutral venue is `NOT_APPLICABLE`; an unknown venue is `BLOCKED` for a home-advantage value.
- A global or league-specific parameter must be declared explicitly; no hidden fixed home advantage is allowed.

## 10. Conflict, stale, and correction handling

Conflicting claims are all retained. An unresolved conflict is excluded from ordinary numeric aggregation and remains `CONFLICT`/`BLOCKED` with all source/evidence references. There is no silent source selection.

`STALE`, `FUTURE_DATA`, `NOT_VERIFIED`, and `BLOCKED` observations do not become ordinary available observations. A correction after the target cutoff cannot replace the revision that was visible at the cutoff. Corrections append a new observation/manifest revision with `supersedes_id`; old records remain immutable.

## 11. Statistical feature output boundary

V4-041, V4-042, and V4-043 may emit only typed statistical strength features and quality/lineage metadata, including:

- rating values or explicit insufficient-data state;
- attack, defence, and home-advantage values or explicit state;
- opponent-adjusted and recency-decayed statistical values or explicit state;
- league-strength and transition state or explicit state;
- sample counts, scope, policy versions, and hashes.

They may not emit or contain:

- win/draw/loss probability;
- handicap or goals probability;
- exact score;
- prediction or recommendation;
- betting selection or confidence;
- risk decision;
- Score Engine or engine output.

`feature_quality` describes coverage, verification, freshness, completeness, conflict, and provenance only. It is not prediction confidence.

## 12. Determinism and replay

Replaying the same exact source observation IDs, revisions, evidence hashes, target cutoff/kickoff, competition/season scope, sample policy, rolling policy, decay policy, normalization policy, priors, generator version, implementation hash, and config hash must produce the same statistical feature values, states, and output hash.

Changing any accepted observation, revision, scope, policy, prior, generator, configuration, or cutoff creates a new input/output identity. `retrieved_at`, `ingested_at`, and other declared volatile telemetry cannot change substantive replay hashes unless the applicable hash profile says otherwise.

## 13. Versioning and persistence

This is a new additive contract family and does not change the meaning of existing `POSTMATCH_ONLY`, `fact_state`, or hash enums. Existing source facts and evidence remain under their original contracts. This contract is the only legal cross-match historical selection boundary for BATCH-11.

Historical manifests and statistical feature observations are append-only. A correction or new policy creates a new identity and explicit supersession lineage. No migration or database write is authorized by this contract.

## 14. V3.3.3 and production boundary

This contract is V4-only. It cannot read, copy, mutate, or publish V3.3.3 model outputs, parameters, predictions, Frozen Predictions, reviews, samples, or audit history. It does not authorize Production/Supabase access, migration application, Prediction, Score Engine, Shadow/Tier A, Public Page, Promotion, or Deployment.

```json
{
  "contract_version": "historical-statistical-input@1.0.0",
  "historical_input_id": "019a0000-0000-7000-8000-000000000011",
  "source_match_id": "019a0000-0000-7000-8000-000000000012",
  "target_match_id": "019a0000-0000-7000-8000-000000000013",
  "availability_at": "2026-09-03T20:00:00+00:00",
  "target_prediction_cutoff_at": "2026-09-04T11:00:00+00:00",
  "target_kickoff_at": "2026-09-04T19:00:00+00:00",
  "verification_state": "VERIFIED",
  "quality_state": "AVAILABLE",
  "input_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
}
```
