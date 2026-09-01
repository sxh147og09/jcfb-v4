# JCFB V4 Future Supabase Blueprint 1.0

Status: V4-009 FUTURE STORAGE BLUEPRINT ONLY

## 1. Scope and hard boundary

This document describes a candidate Supabase/Postgres implementation of the V4-009 logical model. It is intentionally non-executable: it creates no schema, table, index, trigger, view, policy, function, migration, or data. A future V4-010 task must turn this blueprint into reviewed migrations without weakening the contracts or Constitution.

The implementation must be checked against the official [Supabase Row Level Security guidance](https://supabase.com/docs/guides/database/postgres/row-level-security), [Supabase table/view security guidance](https://supabase.com/docs/guides/database/tables), and [PostgreSQL `CREATE VIEW` reference](https://www.postgresql.org/docs/current/sql-createview.html) at implementation time.

## 2. Candidate logical schemas and tables

The following names are candidates, not created objects.

### `core` — canonical objective facts

| Candidate table | Purpose | Key references |
|---|---|---|
| `core.competitions` | stable competition identity and source metadata | `competition_id` UUID PK; unique scoped business key |
| `core.teams` | stable team identity and canonical display labels | `team_id` UUID PK |
| `core.team_aliases` | source/locale/validity-scoped aliases | `team_alias_id` UUID PK; FK `team_id` |
| `core.matches` | canonical fixture identity and objective schedule | `match_id` UUID PK; FK competition/home/away teams |
| `core.official_odds_snapshots` | official five-market snapshots | `snapshot_id` UUID PK; FK `match_id`; exact snapshot hash |
| `core.external_market_snapshots` | non-official provider snapshots | `snapshot_id` UUID PK; FK `match_id`; `source_is_official=false` |
| `core.team_context_snapshots` | time-valid context per match/team/side | `team_context_id` UUID PK; FKs match/team |
| `core.evidence_items` | atomic source-bound claims | `evidence_id` UUID PK; typed entity refs |
| `core.evidence_bundles` | cutoff-scoped evidence selection | `evidence_bundle_id` UUID PK; FK match |
| `core.evidence_bundle_items` | normalized N:M bundle membership | composite unique `(evidence_bundle_id, evidence_id)` |

### `governance` — identity, pointers, incidents, audit

| Candidate table | Purpose | Key references |
|---|---|---|
| `governance.model_versions` | model/release registry and role-scoped revisions | `model_version_id` UUID PK; predecessor FK |
| `governance.engine_versions` | engine registry and role-scoped revisions | `engine_version_id` UUID PK; model/release FK |
| `governance.release_pointer_events` | append-only active Production pointer history | model family/channel, predecessor/successor release IDs |
| `governance.incidents` | integrity, leakage, security, publication and model incidents | `incident_id` UUID PK; typed affected entity refs |
| `governance.audit_logs` | hash-chained audit events | `audit_log_id` UUID PK; `prev_hash`, `entry_hash` |

### `model` — frozen lineage and role-owned outputs

| Candidate table | Purpose | Key references |
|---|---|---|
| `model.frozen_inputs` | immutable accepted pre-match input | `frozen_input_id` UUID PK; FK match; exact source/hash refs |
| `model.feature_bundles` | typed features generated from one Frozen Input | `feature_bundle_id` UUID PK; FK Frozen Input |
| `model.engine_runs` | role-scoped independent engine output envelope | `engine_run_id` UUID PK; FKs match/Frozen Input/Feature/versions |
| `model.predictions` | role-scoped five-market assembled Prediction | `prediction_id` UUID PK; FK match/Frozen Input |
| `model.prediction_engine_runs` | Prediction to many Engine Run references | composite unique `(prediction_id, engine_run_id, market, lineage_purpose)` |
| `model.frozen_predictions` | immutable Prediction freeze snapshot | `frozen_prediction_id` UUID PK; FK prediction/match |

### `evaluation` — postmatch evidence and controlled review

| Candidate table | Purpose | Key references |
|---|---|---|
| `evaluation.official_results` | verified result revisions | `result_id` UUID PK; FK match; supersedes FK |
| `evaluation.postmatch_reviews` | Model Evaluation or Match Explanation revisions | `review_id` UUID PK; FKs Frozen Prediction/result |
| `evaluation.tier_a_samples` | V4 Forward Tier A qualification records | `tier_a_sample_id` UUID PK; FK match/Frozen Input |
| `evaluation.tier_a_run_members` | typed Production/Shadow sample members | sample FK; role/output/prediction refs |
| `evaluation.promotion_reviews` | manual promotion evidence and decision | `promotion_review_id` UUID PK; candidate release FK |
| `evaluation.promotion_review_samples` | promotion review to Tier A N:M membership | composite unique `(promotion_review_id, tier_a_sample_id)` |
| `evaluation.calibration_records` | append-only stratified calibration evidence | `calibration_record_id` UUID PK; model/role/scope refs |

### `public` — safe read projection

| Candidate object | Purpose | Boundary |
|---|---|---|
| `public.public_read_projections` | append-only safe Production projection rows | only Production publication gate may append |
| `public.v_public_match_predictions` | explicit-column read view over safe projection | `SELECT` only; no direct private-table exposure |

The physical schema may choose different names, but it must preserve this ownership split and the logical table relationships.

## 3. Candidate column and constraint baseline

Every formal table should include, as applicable:

- UUID/UUIDv7 `object_id`/entity ID as primary key;
- exact `contract_version`, `schema_version`, and qualified model/engine/dataset identities;
- role and role-scoped revision for role-owned records;
- source, source type/reference, source/observation/ingestion times;
- relevant cutoff, kickoff, run, freeze, verification, and review times;
- typed status and explicit `UNKNOWN`/`UNAVAILABLE`/`NOT_VERIFIED`/`BLOCKED`/`NOT_APPLICABLE` states;
- required hash fields and declared hash exclusions;
- `supersedes_*_id` and correction metadata when the contract supports revisions;
- created-by/audit references without secrets.

Candidate relational constraints:

1. `core.matches` has unique `(data_date, official_match_no)` and a derived/validated `match_identity_key`.
2. Every downstream table carries a `match_id` FK where the object is match-scoped. Nested references also pass same-match checks.
3. `core.official_odds_snapshots.source_is_official` is true; `core.external_market_snapshots.source_is_official` is false.
4. Frozen Input refs resolve to exact snapshot/context/evidence IDs and hashes; Feature Bundle has exactly one Frozen Input.
5. Prediction and Frozen Prediction match IDs agree with the referenced Frozen Input/Prediction.
6. Review Frozen Prediction and Official Result match IDs agree.
7. Tier A Production/Shadow members have the same match and `frozen_input_hash`, distinct explicit roles, and pre-kickoff completion.
8. Public projection foreign keys resolve only to Production release/prediction/Frozen Prediction records.
9. Every `supersedes_*_id` points to the same entity family and an earlier revision; root records use `NOT_APPLICABLE` as a governed state where the contract allows it.
10. No V4 table has a foreign key to a JCFB V3.3.3 object.

## 4. Candidate indexes and uniqueness planning

These are logical index requirements, not index commands:

| Access pattern | Candidate index/constraint |
|---|---|
| match business key | unique `(data_date, official_match_no)` |
| match + captured time | `(match_id, captured_at DESC)` on official/external snapshots |
| Frozen Input hash | `(frozen_input_hash)` plus `(match_id, frozen_input_revision)` unique |
| Engine Run input hash | `(input_hash)` and `(frozen_input_hash, match_id)` |
| Prediction match/model/role/revision | `(match_id, model_version_id, role, prediction_revision, stage)` unique |
| Frozen Prediction match/revision | `(match_id, freeze_revision, role, model_identity)` unique |
| Review by Frozen Prediction | `(frozen_prediction_id, reviewed_at DESC)` |
| Tier A by Shadow version/revision | `(shadow_model_version_id, shadow_revision, match_id)` |
| Tier A pair uniqueness | unique `(match_id, production_prediction_id, shadow_prediction_id, shadow_revision)` |
| Promotion sample membership | unique `(promotion_review_id, tier_a_sample_id)` |
| latest business update | `(canonical_latest_update_at DESC, match_id)` on safe projection |
| active Production release | a future partial/conditional uniqueness rule for `(model_family, canonical_output_channel)` where state is active |
| audit chain traversal | `(entity_type, entity_id, happened_at)` and `(prev_hash)` |

No index can replace a stable UUID primary key or a typed relationship check.

## 5. RLS and permission baseline

The future implementation must enable Row Level Security on every table exposed through an API schema and grant only the operations required by the role. Private schemas/tables should not be directly exposed to browser clients.

Candidate application/database identities:

| Identity | Intended access |
|---|---|
| `anon` / `authenticated` public reader | `SELECT` only on the safe public view/projection; no private model tables |
| `v4_fact_intake` | append canonical facts/snapshots/evidence and correction events; no model output writes |
| `v4_production_runtime` | read approved core facts; append Production Feature/Engine/Prediction/Frozen records in its namespace |
| `v4_shadow_runtime` | read approved core facts/shared Frozen Input; append Shadow-owned runtime records only |
| `v4_experiment_runtime` | read approved scope; append Experiment-owned research records only |
| `v4_review_promotion` | read immutable evidence; append Reviews, Tier A, Promotion, Calibration, and audit records after gates |
| `v4_registry_admin` | append model/engine releases and pointer events; no historical output mutation |
| `v4_incident_admin` | append incident/containment/recovery/closure events; no output rewriting |
| server-side privileged service | narrowly allow listed functions/transactions; never exposed to a browser |

RLS policy rules:

1. Default deny. Add explicit `SELECT`/`INSERT` policies per namespace and role.
2. Runtime `INSERT` policies require the row's explicit `role` and namespace to match the caller's permitted role.
3. Runtime roles have no `UPDATE` or `DELETE` on audit-critical tables.
4. Shadow and Experiment policies cannot address Production rows, active pointers, Production Frozen Prediction, Tier A, or the canonical public projection.
5. Review/Promotion may append evidence but cannot update a Frozen Input, Prediction, Frozen Prediction, Result, or prior Review.
6. Public readers can see only allow-listed projection columns and rows; they cannot call model execution or write functions.
7. Administrative bypass is limited to approved server-side functions and must emit an audit event. A privileged service key is treated as full authority and is never shipped to a client.

RLS is an authorization layer, not a substitute for foreign keys, append-only triggers, hash checks, no-future-leakage validation, or Promotion gates.

## 6. Append-only trigger and function requirements

Future migrations should provide reviewed database enforcement for:

- rejecting `UPDATE`/`DELETE` on audit-critical rows;
- rejecting changes to IDs, role, hashes, source/cutoff/kickoff times, and frozen payloads;
- allowing only explicitly classified non-historical pointer/cache metadata updates;
- validating `supersedes_*_id`, same entity family, predecessor hash, and monotonic revision;
- checking `prediction_cutoff_at < kickoff_at`, source availability, `model_run_at < kickoff_at`, and leakage flags before formal eligibility;
- checking same-match relationships across nested Frozen Input, Prediction, Frozen Prediction, Result, Review, and Tier A references;
- enforcing official/external source separation;
- enforcing one active Production release per model family/channel;
- denying Experiment-as-Tier-A and non-Production public projection;
- appending `audit_logs` for intake, freeze, run, prediction, result, review, correction, Tier A, promotion, release, publication, incident, and permitted pointer events.

Triggers should reject unsafe writes rather than repair them silently. A failed trigger must leave the attempted operation auditable without mutating the protected predecessor.

## 7. Security-invoker public view requirement

The public read path should be an explicit-column view over `public.public_read_projections`, created with the Postgres `security_invoker` option when the deployed Postgres version supports it. The view must:

- expose only match identity, public-safe official odds reference, canonical Production selection, Frozen timestamp, latest business update, and safe postmatch summary;
- avoid `SELECT *` and exclude raw payloads, features, source secrets, debug traces, internal disagreement details, and Shadow/Experiment identities;
- rely on RLS/grants for the invoking caller and deny direct private-table access;
- be treated as read-only by grants and deployment policy;
- carry an explicit schema/view version and be rebuilt through an append-only migration identity.

Supabase documents that views are otherwise accessed with the creator's permissions and that `security_invoker` makes underlying RLS apply for supported PostgreSQL versions. The implementation must verify the deployed version and permissions before exposure; on an older version, keep the view in an unexposed/private schema or revoke public roles as required by the official guidance.

## 8. Service-role and admin write boundary

Service-side privileged access is a controlled backend boundary, not a general-purpose client capability.

It may:

- call the fact intake, Freeze Gate, role runtime, review/promotion, registry, publication, and incident functions allowed for the current actor;
- append immutable records and typed transition events;
- update a permitted active pointer only together with its predecessor, effective time, reason, and audit event;
- execute a reviewed migration with an explicit `migration_version`.

It may not:

- rewrite or delete audit-critical history;
- convert role or copy a Shadow/Experiment identity into Production;
- make an invalid/leaked run Tier A-eligible by deleting evidence;
- bypass Frozen Input, Freeze, no-future, Secret, or Promotion gates;
- expose a service credential, database password, or private key to browser code, repository content, or public projection.

Any emergency administrative action follows the Incident Policy and retains before/after evidence. Routine model maintenance does not use an emergency bypass.

## 9. Migration discipline deferred to V4-010

When a future schema task begins:

1. register a new immutable `migration_version`;
2. review field and hash compatibility against every V4-008 contract;
3. create namespaces/tables in dependency order without rewriting historical data;
4. add constraints, RLS, grants, triggers, and security-invoker views;
5. test same-match, same-Frozen-Input, role, no-leakage, append-only, public, and V3.3.3 isolation rules;
6. record migration, test, and audit identities.

V4-009 does not start that work. The next task is `V4-010 Database Schema Blueprint 1.0`.

## 10. V3.3.3 boundary

No candidate Supabase schema, role, policy, view, function, or migration may import, copy, expose, or mutate JCFB V3.3.3 code, parameters, predictions, Frozen Predictions, reviews, samples, results, or audit history. V3.3.3 remains outside the V4 database boundary.
