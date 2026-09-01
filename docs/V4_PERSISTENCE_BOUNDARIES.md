# JCFB V4 Persistence Boundaries 1.0

Status: V4-009 PERSISTENCE BOUNDARY DESIGN ARTIFACT

## 1. Purpose and non-goals

This document defines which logical namespace owns each V4 artifact, which service may append it, which data may cross a boundary, and which derived views are read-only. It is a storage blueprint, not a migration or a database implementation.

No V4-009 action creates tables, schemas, indexes, policies, triggers, or Supabase data. The physical design must be checked against this document and the V4 Constitution before implementation.

## 2. Boundary map

```text
SOURCE INTAKE
    -> core / canonical facts
    -> model / frozen lineage and runtime outputs
    -> evaluation / result, review, Tier A, promotion, calibration
    -> governance / registry, active pointers, incidents, audit
    -> public / Production-only read projection
```

The arrows describe controlled references, not unrestricted writes. A downstream namespace can reference an upstream immutable identity/hash but cannot rewrite the upstream record.

| Logical namespace | Source of truth | May be read by | May append | Must never contain |
|---|---|---|---|---|
| `core` / canonical facts | attributed objective source intake | governed V4 roles and review | Fact/odds/context/evidence intake authority | model probabilities, recommendation, confidence grade, V3.3.3 data |
| `model` / runtime | Frozen Input, Feature Bundle, Engine Run, Prediction and Frozen Prediction contracts | role-scoped runtime and controlled review | role-owned runtime path and Freeze Gate | postmatch facts in a pre-match input, cross-role overwrite, secrets |
| `evaluation` / postmatch | verified Result and immutable pre-match outputs | review/promotion/calibration services | controlled review/promotion service | mutable KPI history, Experiment-as-Tier-A, pre-match write-back |
| `governance` / registry/audit | version/release registry, active pointers, incidents, audit chain | authorized operators/services | registry, incident, and audit authorities | hidden state transitions, unaudited promotion, deleted history |
| `public` / read projection | canonical Production publication gate | Public Web and approved read clients | Production publication gate only | Shadow/Experiment IDs, internal payloads, secrets, debug traces |

## 3. Artifact ownership and persistence authority

| Artifact | Owning boundary | Authoritative write path | Downstream use |
|---|---|---|---|
| `competitions`, `teams`, `team_aliases`, `matches` | `core` | canonical fact intake/correction authority | stable identity only |
| `official_odds_snapshots` | `core` | official odds intake | official five-market source; exact snapshot refs |
| `external_market_snapshots` | `core` | external market intake | Market Intelligence only; never official substitution |
| `team_context_snapshots` | `core` | context intake | time-valid objective/context facts |
| `evidence_items`, `evidence_bundles` | `core` | evidence intake/bundle assembly | provenance and cutoff support |
| `model_versions`, `engine_versions` | `governance` | registry/release authority | exact runtime identities |
| `frozen_inputs` | `model` | Freeze Gate; Experiment may append its own isolated research input | sole formal source boundary |
| `feature_bundles` | `model` | versioned generator in the role namespace | typed engine input |
| `engine_runs`, `predictions` | `model` | explicit role runtime | raw and assembled outputs |
| `frozen_predictions` | `model` | Production Final Prediction Gate; role-owned Shadow/Experiment freeze only in their permitted scope | immutable public/audit candidate |
| `official_results` | `evaluation` | official result intake/verification | postmatch evaluation only |
| `postmatch_reviews` | `evaluation` | controlled review service | evaluation, explanation, diagnostic evidence |
| `tier_a_samples`, `promotion_reviews`, `calibration_records` | `evaluation` | Promotion/Review authority | forward evidence and calibration |
| `incidents`, `audit_logs`, active release pointers | `governance` | incident, registry, and audit services | traceability and controlled transitions |
| `public_read_projections` | `public` | Production publication gate | public read only |

## 4. Write boundary matrix

`APPEND_ONLY` means append a new immutable record or event in the actor's own namespace. It does not mean update, delete, replace, or cross-write another role.

| Actor/path | `core` facts | `model` Production | `model` Shadow | `model` Experiment | `evaluation` | `governance` | `public` |
|---|---|---|---|---|---|---|---|
| Canonical intake | APPEND_ONLY / correction revision | DENY | DENY | DENY | DENY | audit append | DENY |
| Production runtime | READ | APPEND_ONLY in Production namespace | DENY | DENY | READ approved evidence | audit append | publication gate only |
| Shadow runtime | READ | DENY | APPEND_ONLY in Shadow namespace | DENY | READ approved scope | audit append | DENY |
| Experiment runtime | READ | DENY | DENY | APPEND_ONLY in Experiment namespace | read only approved research scope | audit append | DENY |
| Freeze Gate | READ | append shared Production Frozen Input | READ shared input | own Experiment input only | DENY | audit append | DENY |
| Review/Promotion | READ | DENY to historical output | DENY to historical output | DENY to historical output | APPEND_ONLY review/Tier A/promotion/calibration | registry pointer only after approval; audit append | READ |
| Public Web | DENY to private core rows | DENY | DENY | DENY | DENY | DENY | READ only |

Every cell remains subject to source identity, cutoff, hash, status, and audit gates. A role cannot gain a write path by calling a lower-level repository or by writing directly to a projected table.

## 5. Frozen lineage boundary

Formal runtime may consume only:

```text
canonical match identity
  + exact official/external snapshot refs and hashes
  + exact team context ref/hash
  + exact evidence bundle ref/hash
  + feature schema/generator identity
  + model/engine/config/dataset identities
  + prediction_cutoff_at and kickoff_at
        -> Frozen Input
        -> Feature Bundle
        -> Engine Run
        -> Prediction
        -> Frozen Prediction
```

The Frozen Input is the handoff from shared facts to model-private interpretation. It is immutable after `FROZEN`, carries `frozen_input_hash`, and remains a read-only reference for both Production and comparable Shadow. A role-specific `input_hash` is permitted to differ because it includes role and component identity.

No runtime path may bypass Frozen Input to read a raw screenshot, unversioned JSON, post-cutoff source, or another role's output. If exact lineage cannot be resolved, the path is `BLOCKED`.

## 6. Persistence versus projection

The following are sources of truth:

- source snapshots and Evidence for what was observed;
- `matches` for canonical identity;
- Frozen Input for accepted pre-match input;
- Feature Bundle for the typed derived features;
- Engine Run and Prediction for role-scoped raw/assembled output;
- Frozen Prediction for the immutable prediction record;
- Official Result for the verified postmatch result;
- Review, Tier A, Promotion, Calibration, Incident, and Audit records for their own evidence.

The following are projections and cannot be used to update a source:

- `LATEST`/`CURRENT` odds read views;
- current active release pointer;
- current result/prediction revision lookup;
- `public_read_projections`;
- dashboard aggregates, latest-update values, or UI summaries.

The derived `canonical_latest_update_at` must be calculated from actual business-data update times covered by the projection. Page build time or row insertion time cannot substitute for source or business update time.

## 7. Limited mutable metadata

Only non-historical control metadata may be updated in place, for example:

- a registry pointer while appending the corresponding pointer event;
- an operational lock/lease or ingestion cursor that is not part of a formal artifact;
- a non-authoritative display cache that can be rebuilt from immutable source records;
- a current projection pointer whose predecessor, actor, reason, time, and audit event are retained.

These updates must not change a contract payload, identity, hash, role, source fact, result, Prediction, Frozen Input, Frozen Prediction, evaluation, Tier A sample, Promotion Review, Calibration Record, Incident, or Audit Log. A pointer is control metadata, not permission to mutate the pointed-to record.

## 8. Boundary failure behavior

| Boundary failure | Persistence action |
|---|---|
| source identity or source time cannot be proven | append source record as `UNKNOWN`/`NOT_VERIFIED`; block formal use |
| official market absent | append explicit unavailable snapshot/state; never create a synthetic odds payload |
| Frozen Input reference/hash mismatch | reject or append `BLOCKED` input/run evidence; preserve offending refs |
| future data enters pre-match path | append invalid run/incident/audit evidence; set `RUN_INVALID`, Tier A false |
| Shadow/Experiment attempts Production write | reject write, append role-violation audit/incident evidence |
| more than one active Production release | fail closed, block publication, open governance incident |
| public projection includes non-Production identity | block publication and append Publication/Model Incident |
| correction requested for immutable history | use new revision/correction event; never update old row |

## 9. Future physical implementation boundary

The future database may implement these boundaries with schemas, tables, grants, RLS, append-only triggers, foreign keys, check constraints, views, and controlled service functions. The physical implementation must preserve:

- namespace ownership and role-scoped writes;
- immutable hashes and supersedes chains;
- explicit business state rather than hidden NULL/empty values;
- database-reconstructable no-future-leakage checks;
- one active Production pointer per model family/channel;
- Public Web read-only access to a safe Production projection;
- no access to JCFB V3.3.3 artifacts from V4 paths.

Implementation details are deferred to `docs/V4_FUTURE_SUPABASE_BLUEPRINT.md` and a later schema task. V4-009 does not authorize SQL migration or real table creation.
