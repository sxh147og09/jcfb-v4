# JCFB V4 Market Intelligence Feature Contract 1.0

Status: **BATCH-13 GOVERNANCE RESOLUTION — APPROVED FOR ENTRY REVIEW**
Contract version: `market-intelligence-feature@1.0.0`

## 1. Scope and lifecycle

This contract defines the canonical pre-Frozen Market Intelligence feature artifact. V4-046, V4-047, and V4-048 produce market-derived features and evidence profiles only. They do not create a formal `engine-output@1.0.0` run, Prediction, Score Engine result, Frozen Input, recommendation, or final risk decision.

The approved data flow is:

```text
Official Odds + External Market Snapshots
    -> V4-046 market artifact foundation
    -> V4-047 movement / velocity / divergence features
    -> V4-048 heat / pressure / anomaly evidence profile
    -> future quality / feature integration
    -> Frozen Input
    -> Prediction
```

`frozen_input_id` and `frozen_input_hash` are forbidden in these artifacts. Frozen Input remains a downstream task.

## 2. Required envelope

Every Market Intelligence artifact must carry:

- deterministic `artifact_id`;
- `contract_version`;
- canonical `match_id` and match identity hash;
- market type and semantic market mapping;
- provider/source identity;
- `source_is_official` with the original official/external role;
- exact snapshot IDs and hashes;
- source, captured, observed/retrieved, and ingested timestamps;
- `prediction_cutoff_at` and `kickoff_at`;
- generator version and implementation hash;
- config version and config hash;
- mapping registry version;
- typed feature state, value, unit, and reason when non-consumable;
- source refs and basis/evidence refs;
- `feature_quality`;
- `input_hash`, `payload_hash`, `output_hash`, and `provenance_hash`;
- positive `revision` and optional `supersedes_*` reference.

## 3. Source and market isolation

Official China Sports Lottery odds and external markets are separate contract families. External records remain `source_is_official=false`. No external European 1X2, Asian Handicap, or O/U snapshot may populate an official SPF, RQSPF, Total Goals, Exact Score, or Half-Full payload. Market Intelligence cannot modify BATCH-06 or BATCH-07 source records.

Cross-source comparison is allowed only where an approved semantic mapping exists. The approved v1 mapping is official SPF to external European 1X2 through normalized market-implied probabilities. Official RQSPF versus external Asian Handicap and official Total Goals distribution versus external O/U line are `NOT_COMPARABLE`; the relation is retained without forced numeric divergence.

## 4. Snapshot semantics

The contract distinguishes `OPENING`, `INTERMEDIATE`, `CURRENT`, `LATEST`, `FINAL`, and `CORRECTION`.

- `OPENING` requires an explicit accepted opening identity; the earliest observed value must not be silently relabeled as opening.
- `LATEST` means the greatest eligible source-time snapshot for the same canonical match, market, provider/source, and semantic line at the target cutoff.
- `LATEST` is not the newest database row or a wall-clock alias.
- Post-cutoff snapshots remain `FUTURE_DATA` or `BLOCKED` and cannot enter the target-cutoff feature object.
- Source time, captured time, observed/retrieved time, and ingested time remain separate.
- Equal source times use the approved stable snapshot hash tie-break.

## 5. Feature quality and state

Market-derived values use explicit typed states. `UNKNOWN`, `UNAVAILABLE`, `SUSPENDED`, `NOT_VERIFIED`, `STALE`, `CONFLICTED`, `FUTURE_DATA`, and `BLOCKED` are never silently converted to `AVAILABLE` or `CURRENT`. A missing or suspended market cannot be filled by a prior snapshot, another provider, a default line, a default price, zero, an average, or a synthetic payload.

`feature_quality` contains only data/evidence quality dimensions: `coverage`, `verification`, `freshness`, `completeness`, `conflict`, and `provenance`, with optional market counts. It is not win probability, prediction confidence, betting confidence, trap certainty, or recommendation grade.

## 6. Determinism and append-only history

The input, payload, output, and provenance hashes include exact snapshot refs/hashes, provider/source identity, timestamps, cutoff/kickoff, semantic mapping, generator/config/mapping identity, typed values/states, and basis/source refs. Runtime transport metadata is excluded only under the declared hash profile.

Corrections and recomputation append a new artifact identity, revision, hash set, and explicit `supersedes_*` pointer. Previous artifacts remain readable and immutable. No update or delete operation is a valid correction.

## 7. Forbidden output

The artifact must reject or never emit `prediction`, `recommendation`, `model_confidence`, `win_probability`, `betting_confidence`, `score_selection`, `risk_decision`, `engine_output`, `lambda`, `score_matrix`, `trap_risk_score`, `heat_score`, `pressure_score`, `BOOKMAKER_INTENT_CONFIRMED`, or `CERTAIN_TRAP`.

## 8. Compatibility

Adding an optional observable annotation is `MINOR`. Changing official/external isolation, market keys, state meanings, lifecycle, required identity/time fields, or hash boundaries is `MAJOR`. Documentation-only clarification is `PATCH`. Historical IDs and hashes are immutable.
