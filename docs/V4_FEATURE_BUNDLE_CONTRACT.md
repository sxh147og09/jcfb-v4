# JCFB V4 Feature Bundle Contract 2.0

Status: V4-010 ARCHITECTURE GOVERNANCE AMENDMENT  
Contract version: `feature-bundle@2.0.0`  
Supersedes: `feature-bundle@1.0.0` in `docs/V4_FEATURE_BUNDLE_CONTRACT_1.0.md`

## 1. Decision and boundary

Feature Bundle is the typed, versioned, deterministic representation of accepted upstream inputs. It is created before Frozen Input and is never a consumer of Frozen Input. The governed flow is:

```text
canonical facts / official odds / external markets / team context / Evidence Graph
    -> Feature Bundle
    -> downstream feature and quality layers
    -> Frozen Input
    -> Prediction
```

The bundle may read only versioned, identity-bound, time-eligible upstream artifacts. It never reads an unversioned raw source directly in a formal Production, Shadow, or Experiment path. `frozen_input_id` and `frozen_input_hash` are not creation-stage inputs and are not required fields in this contract.

## 2. Required envelope

The following fields are required unless a field is explicitly marked as a governed empty collection. A missing required field is `BLOCKED`; no default or implicit coercion is permitted.

| Field | Rule |
|---|---|
| `object_id`, `feature_bundle_id` | Stable UUID identities; never reused. |
| `contract_version` | Exact `feature-bundle@2.0.0`; no `latest` or silent downgrade. |
| `feature_schema_version` | Exact registered feature shape. |
| `generator_version` | Exact generator implementation identity. |
| `role` | Explicit `PRODUCTION`, `SHADOW`, or `EXPERIMENT` namespace identity; never inferred. |
| `config_version`, `config_hash` | Exact feature-affecting configuration identity; no hidden defaults. |
| `canonical_entity_refs` | Required match reference and resolved canonical team/side references. |
| `canonical_fact_refs` | Exact accepted fact IDs and hashes used by the bundle. |
| `official_odds_snapshot_refs` | Exact official snapshot IDs and hashes, including explicit market availability states. |
| `external_market_refs` | Exact external snapshot IDs and hashes; every reference retains `source_is_official=false`. |
| `team_context_refs` | Exact team-context IDs and hashes used. |
| `evidence_graph_refs` | Exact Evidence Graph object IDs and hashes used as basis. |
| `input_hash` | Deterministically derived from the complete accepted upstream reference/hash set and declared temporal/config identities. |
| `generated_at` | Envelope generation timestamp; excluded from substantive replay hash when declared volatile. |
| `prediction_cutoff_at`, `kickoff_at` | Required time boundary; cutoff precedes kickoff. |
| `feature_values` | The seven governed categories with typed values and explicit state. |
| `missingness_summary` | Reconciles every feature state; no hidden omissions. |
| `feature_quality` | Typed data-quality object defined in section 5; not prediction confidence. |
| `quality_flags` | Explicit blockers, conflicts, stale/future states, and provenance conditions. |
| `feature_snapshot_hash` | Required for a finalized/replayable bundle and established by V4-039. |
| `feature_hash`, `payload_hash`, `provenance_hash` | Recomputable canonical hashes. |
| `status`, `metadata` | Governed lifecycle state and non-secret audit metadata. |

## 3. Upstream lineage and identity

Every bundle must resolve exactly one canonical match identity. All source references must resolve to accepted V4 records and preserve their original IDs, source role, source references, and hashes. A missing or invalid canonical match, team, side, source, source reference, or hash is `BLOCKED`; an orphan feature bundle is invalid.

`display_name` is descriptive only and is never a join key. Official and external market references remain separate; an external reference cannot fill an official reference or change its market semantics. The bundle does not invent a snapshot, odds value, line, context value, evidence claim, or source.

The bundle's direct input boundary is the ordered canonical set:

```text
canonical_entity_refs
canonical_fact_refs
official_odds_snapshot_refs
external_market_refs
team_context_refs
evidence_graph_refs
prediction_cutoff_at / kickoff_at
feature_schema_version / generator_version
```

`input_hash` covers this set after canonical serialization, including each referenced object's exact hash and governed status. It does not include `frozen_input_id`, `frozen_input_hash`, downstream engine output, Prediction, recommendation, or model interpretation.

## 4. Feature value and availability semantics

Every feature record carries `value`, `state`, `unit` where applicable, `source_refs`, and `derivation_ref` where derived. `AVAILABLE` requires a non-empty correctly typed value and traceable source/basis references. `UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`, `BLOCKED`, and `NOT_APPLICABLE` remain explicit states; an absent value is not evidence for any other state.

The following implicit conversions are forbidden:

```text
missing -> UNKNOWN
empty payload -> UNAVAILABLE
stale / future / conflict / blocked -> AVAILABLE
conflict -> selected winner without approved policy
missing -> 0 / mean / previous-match value / synthetic payload
```

Zeros are valid only when the accepted upstream evidence supports a real zero. Imputation is permitted only when a separately versioned feature contract, configuration identity, and quality flag explicitly authorize it; otherwise the state remains missing or blocked.

## 5. Feature-quality semantics

The bundle must not contain an unqualified bare `confidence` field. Its typed quality object is `feature_quality`, whose dimensions describe evidence and data quality only:

```json
{
  "coverage": "COMPLETE|PARTIAL|UNKNOWN",
  "verification": "VERIFIED|PARTIAL|UNKNOWN",
  "freshness": "CURRENT|STALE|UNKNOWN",
  "completeness": "COMPLETE|PARTIAL|UNKNOWN",
  "conflict": "NONE|PRESENT|UNKNOWN",
  "provenance": "RESOLVED|PARTIAL|UNKNOWN"
}
```

These dimensions must not be interpreted as win probability, model confidence, betting confidence, recommendation grade, or engine output. A numeric score is not part of this generic object. Source/evidence-specific confidence remains governed by the relevant source or Evidence contract and is not copied into a prediction-like field.

## 6. Time, cutoff, and replay rules

All accepted upstream objects must be eligible at `prediction_cutoff_at`; future, post-kickoff, stale, ambiguous, or unprovable time data remains explicitly represented and cannot be silently promoted. This contract carries time fields for the boundary but does not replace V4-022's complete cutoff gate.

Canonical serialization fixes field order, object representation, collection order, number handling, state handling, and hash algorithm/profile. Identical accepted upstream identities, hashes, schema, generator, cutoff, and feature values produce the same `input_hash` and, after V4-039, the same `feature_snapshot_hash`. A logical change produces a different hash. Volatile telemetry such as generation/ingestion time is excluded only when the hash profile explicitly declares it volatile.

## 7. Lifecycle and downstream Frozen Input relationship

Feature Bundle observations and corrections are append-only. A correction creates a new revision with a new identity/hash and an explicit `supersedes_feature_bundle_id`; an existing bundle is never overwritten.

V4-076 consumes the accepted Feature Bundle and must freeze at least `feature_bundle_id` and `feature_snapshot_hash`, together with its other approved upstream identities. Frozen Input therefore points downstream to the exact Feature Bundle; it never becomes a prerequisite for Feature Bundle creation.

Feature Bundle is a representation artifact, not a Feature Engine, Market Intelligence output, Prediction, Score Engine output, Shadow/Tier A artifact, Public projection, or Promotion decision.

## 8. Forbidden fields and validation

The envelope must reject fields named or semantically equivalent to `prediction`, `recommendation`, `confidence` (when unqualified), `model_confidence`, `win_probability`, `betting_confidence`, `selection`, `risk_decision`, `engine_output`, or `score_selection`. A feature may cite an upstream fact and derive a typed representation, but it cannot silently rewrite a fact or create a decision.

Validation fails closed when any required identity/hash cannot resolve, a status is inferred from payload shape, a future source enters the pre-match object, a feature schema or generator is unregistered, a hash cannot be recomputed, or the bundle would require a Frozen Input that does not yet exist.
