# JCFB V4 Canonical Data Model 1.0

Status: V4-009 LOGICAL DATA MODEL DESIGN ARTIFACT

## 1. Authority, scope, and non-goals

This document defines the logical persistence model for JCFB V4. It turns the accepted V4-008 contracts into stable entities, references, revision chains, role boundaries, integrity checks, and future storage namespaces.

The authority order is:

1. `docs/V4_CONSTITUTION.md`
2. the affected V4-008 contract and this logical model
3. `docs/V4_VERSIONING_STANDARD.md`, `docs/V4_VERSION_IDENTITY_CONTRACT.md`, and `docs/V4_COMPATIBILITY_POLICY.md`
4. `docs/V4_RUNTIME_ROLE_BOUNDARY.md`, `docs/V4_RUNTIME_ACCESS_MATRIX.md`, and the V4 governance policies
5. a future physical schema that remains compatible with the above

This is a design artifact only. It does not create a database schema, run a migration, write to Supabase, execute a model, run Production or Shadow, publish a prediction, tune parameters, or modify JCFB V3.3.3.

The model has five logical namespaces:

| Namespace | Authority | Logical contents |
|---|---|---|
| `core` | canonical objective-data intake | competitions, teams, aliases, matches, official and external snapshots, team context, evidence and bundles |
| `model` | versioned runtime and immutable model outputs | Frozen Inputs, Feature Bundles, Engine Runs, Predictions, Frozen Predictions |
| `evaluation` | controlled postmatch and promotion services | Official Results, Postmatch Reviews, Tier A Samples, Promotion Reviews, Calibration Records |
| `governance` | registry, incident and audit authority | Model/Engine registries, active release pointers, Incidents, Audit Logs |
| `public` | read-only Production projection | Public Read Projections only; no source or experiment payloads |

The namespace names are logical recommendations. They are not physical PostgreSQL schemas in V4-009.

## 2. Modeling principles

1. Every business entity has a UUID/UUIDv7 internal primary key. A human-readable key is a unique lookup key only.
2. `match_id` is the permanent cross-contract identity. `data_date + official_match_no` is a daily business key and never replaces `match_id`.
3. Team and competition display names are labels. `team_id`, `competition_id`, and their revision/history are the stable references.
4. Every formal derived object points to exact upstream IDs and hashes. `latest`, `current`, `default`, a filename, or insertion order is never a foreign key.
5. Feature Bundle is the typed representation node upstream of Frozen Input. Production and comparable Shadow use the same `frozen_input_hash`; role-specific Engine Run and Prediction identities remain separate.
6. Objective Facts and Model Interpretation are separate classes. Model interpretation cannot update the canonical fact row.
7. Audit-critical history is append-only. A correction is a new revision or correction event with a `supersedes_*_id` pointer.
8. Production, Shadow, and Experiment are explicit role namespaces. A row cannot change role after creation.
9. A pre-match record persists enough source, observation, cutoff, kickoff, run, freeze, and hash facts to reconstruct no-future-leakage eligibility.
10. A public projection is a read model of canonical Production records, never an alternate source of truth.

## 3. Common identity and lineage vocabulary

The following fields are logical common columns. Requiredness remains governed by the applicable V4-008 contract.

| Field | Logical meaning | Class |
|---|---|---|
| `object_id` | UUID/UUIDv7 row identity | internal stable primary key |
| `contract_version` | exact contract identity such as `prediction@1.0.0` | contract identity |
| `schema_version` | exact persisted shape identity | schema identity |
| `revision` / `*_revision` | immutable revision within a component or entity chain | version/revision identity |
| `status` | governed data or lifecycle state | state, not identity |
| `match_id` | permanent canonical Match reference | business entity foreign key |
| `role` | `PRODUCTION`, `SHADOW`, or `EXPERIMENT` where the artifact is role-owned | isolation discriminator |
| `source_timestamp` | time asserted by a source | source availability evidence |
| `observed_at` | time V4 observed the source | observation evidence |
| `ingested_at` | time V4 accepted the record | intake telemetry, never source availability |
| `model_run_at` / `run_at` | execution start time | runtime evidence |
| `frozen_at` | time a frozen artifact was sealed | freeze evidence |
| `kickoff_at` | canonical match kickoff | no-future boundary |
| `prediction_cutoff_at` | last eligible pre-match source boundary | no-future boundary |
| `implementation_hash` | implementation/dependency identity | reproducibility identity |
| `config_hash` | resolved non-secret model-affecting configuration identity | reproducibility identity |
| `input_hash` | exact role/component input-envelope identity | input integrity and replay identity |
| `output_hash` | exact raw runtime output identity | output integrity and replay evidence |
| `payload_hash` | canonical contract payload checksum | integrity checksum |
| `provenance_hash` | canonical source/reference manifest checksum | provenance integrity checksum |
| `frozen_input_hash` | exact immutable pre-match input boundary | lineage identity and replay evidence |
| `prediction_hash` | exact Prediction payload identity | prediction integrity and replay evidence |
| `review_hash` | exact Review payload identity | review integrity and replay evidence |
| `result_hash` | exact Official Result payload identity | result integrity and replay evidence |
| `supersedes_*_id` | direct pointer to the immediately prior revision | revision chain, not replacement |

Hashes are never primary keys, timestamps, confidence scores, or release nicknames. Hashes use the V4-008 canonical JSON profile.

## 4. Logical entity catalog

The table below is the minimum logical model. A future physical schema may split payloads into typed columns and JSONB only when the contract-required fields, hashes, references, and states remain queryable and auditable.

| Entity | Namespace | Stable primary key | Required logical identity and references | Lifecycle / history rule |
|---|---|---|---|---|
| `model_versions` | `governance` | `model_version_id` | `model_family`, `model_name`, `model_version`, `jcfb_version`, semantic components, `role`, role-scoped `revision`, implementation/config/schema identities, release channel, status | New release or behavior creates a new row; `supersedes_model_version_id` records the predecessor; one active Production pointer per family/channel |
| `engine_versions` | `governance` | `engine_version_id` | `engine_name`, `engine_version`, model family/reference, `role`, immutable revision, implementation/config/schema identities, status | New engine behavior creates a new role-scoped row; Shadow/Experiment identity is never relabeled as Production |
| `competitions` | `core` | `competition_id` | stable competition key, governing source, display names, timezone policy, provenance and revision metadata | Display corrections append a governed revision or alias; display name is not a key |
| `teams` | `core` | `team_id` | stable canonical team identity, canonical display name, source/provenance and identity-resolution state | Team identity is not derived from display text; factual corrections preserve prior identity/history |
| `team_aliases` | `core` | `team_alias_id` | `team_id`, alias text, normalized alias, locale/source scope, validity interval, verification state | Alias additions/corrections are auditable; alias text is never a primary key |
| `matches` | `core` | `match_id` | `data_date`, `official_match_no`, `match_identity_key`, `competition_id`, home/away `team_id`, kickoff/timezone, canonical match status, identity resolution, canonical facts hash | `UNIQUE(data_date, official_match_no)`; identity correction appends a new canonical revision and never detaches a Frozen Input |
| `official_odds_snapshots` | `core` | `snapshot_id` | `match_id`, official source, `snapshot_kind`, `captured_at`, `source_timestamp`, five-market availability, payload, `snapshot_hash` | APPEND_ONLY; exact dedup key; correction uses new snapshot and `supersedes_snapshot_id` |
| `external_market_snapshots` | `core` | `snapshot_id` | `match_id`, provider, external market/line, capture/source times, prices, `source_is_official=false`, snapshot/payload hashes | APPEND_ONLY; external data never populates an official market field |
| `team_context_snapshots` | `core` | `team_context_id` | `match_id`, `team_id`, side, `as_of_at`, structured context states, source/evidence refs, context hash | APPEND_ONLY formal snapshots; a correction is a new context revision |
| `evidence_items` | `core` | `evidence_id` | atomic claim, entity refs, source/source type/reference, publication/retrieval/validity times, verification/contradiction states, `evidence_hash` | APPEND_ONLY; corrections use `supersedes_evidence_id`; rejected/conflicted evidence remains visible |
| `evidence_bundles` | `core` | `evidence_bundle_id` | `match_id`, `prediction_cutoff_at`, bundle revision, ordered item membership, inclusion/gate state, bundle/provenance hashes | APPEND_ONLY; membership is a new bundle revision, not an edit to a used bundle |
| `feature_bundles` | `model` | `feature_bundle_id` | canonical entity/fact, official/external market, team-context, Evidence Graph refs/hashes, feature schema/generator version, typed categories, missingness, cutoff/kickoff, `input_hash`, `feature_snapshot_hash` | APPEND_ONLY; a changed generator, lineage, or value creates a new bundle; no Frozen Input prerequisite |
| `frozen_inputs` | `model` | `frozen_input_id` | `match_id`, `frozen_input_revision`, exact canonical/odds/context/evidence refs, `feature_bundle_id`, `feature_snapshot_hash`, version refs, cutoff/kickoff, A/B group/mode, `frozen_input_hash` | APPEND_ONLY and immutable after `FROZEN`; `UNIQUE(match_id, frozen_input_revision)`; new input supersedes old input |
| `engine_runs` | `model` | `engine_run_id` | `match_id`, role, model/engine version IDs, role revision, Frozen Input and Feature Bundle refs, implementation/config/input/output hashes, run times, payload, leakage/gate state | APPEND_ONLY; failed/invalid runs remain; role is immutable |
| `predictions` | `model` | `prediction_id` | `match_id`, role, exact model release, prediction revision, stage, one Frozen Input, many Engine Run refs, five-market payload, confidence/risk/recommendation, `prediction_hash` | APPEND_ONLY formal records; `UNIQUE(match_id, model_version, role, revision, stage)`; pre-kickoff replacement supersedes prior Prediction |
| `frozen_predictions` | `model` | `frozen_prediction_id` | `match_id`, role, `prediction_id`, freeze revision, immutable embedded snapshot, prediction/frozen snapshot hashes, Frozen Input hash, supersession ref | APPEND_ONLY and immutable; freeze correction is a new revision and never an in-place update |
| `official_results` | `evaluation` | `result_id` | `match_id`, canonical result-lineage ID, result revision, regulation result scope, scores, verification/source times, `result_hash`, supersession ref | Physical 1:N append-only revisions; exactly one current canonical result pointer per match |
| `postmatch_reviews` | `evaluation` | `review_id` | `match_id`, review type, Frozen Prediction, Official Result, review revision, allowed input set, metrics/diagnostics, `review_hash` | APPEND_ONLY; factual correction creates a new review revision; no KPI editing |
| `tier_a_samples` | `evaluation` | `tier_a_sample_id` | V4 sequence, match, Frozen Input, Production and required Shadow outputs, official result/review refs, same Frozen Input hash, all timestamps/hashes, eligibility gate | APPEND_ONLY; Experiment is denied; one pair cannot register twice |
| `promotion_reviews` | `evaluation` | `promotion_review_id` | candidate model/engine release, source role, evaluation set, Tier A refs, calibration/regression/integrity/leakage evidence, manual approver, status, production release ref | APPEND_ONLY; status transition is a new event/revision; no auto-promotion |
| `calibration_records` | `evaluation` | `calibration_record_id` | role/model/market/scope/confidence band, evaluation sample period, metric payload, input/evaluation refs, hashes | APPEND_ONLY and role/model namespaced; Shadow/Experiment cannot overwrite Production calibration |
| `incidents` | `governance` | `incident_id` | incident class/severity, affected entity/role/match/run, detected/known times, containment, before/after evidence, owner, resolution | APPEND_ONLY state history; recovery receives new identities; incident evidence is never deleted |
| `audit_logs` | `governance` | `audit_log_id` | actor, action, entity type/id, before/after state, metadata, happened time, `prev_hash`, `entry_hash` | APPEND_ONLY hash chain; every intake, freeze, run, correction, result, review, Tier A, promotion, publication and incident event is auditable |
| `public_read_projections` | `public` | `projection_id` | `match_id`, Production release/prediction/Frozen Prediction refs, public-safe odds ref, frozen time, canonical latest business update, safe postmatch summary, projection revision/hash | APPEND_ONLY publication revisions; only the Production publication gate writes; Public Web is read-only |

## 5. Version and release identity

`model_versions` and `engine_versions` are registries, not output tables. Each row preserves:

- exact `model_name`/`engine_name`, semantic version and immutable registry `revision`;
- role namespace (`PRODUCTION`, `SHADOW`, or `EXPERIMENT`);
- `implementation_hash`, `config_version`, `config_hash`, `schema_version`, and compatibility level;
- lifecycle status and effective/retirement time;
- `supersedes_model_version_id` or `supersedes_engine_version_id` when a new release replaces an earlier identity;
- explicit `canonical_output_channel` for Production uniqueness;
- approval, evidence, and audit references.

The tuple remains compatible with V4-006:

```text
model/engine identity + semantic version + role revision + implementation_hash
+ config_hash + schema/dataset identity + frozen_input_hash + role + status
```

Changing algorithm, features, weights, selector, calibration, simulation behavior, league profile, threshold, effective configuration, or hash interpretation creates a new identity and new forward evidence. A Shadow or Experiment row is not promoted by editing `role`; promotion creates a new Production release identity and a new revision.

## 6. Time and no-future-leakage persistence

The minimum reconstructable timeline for every formal pre-match chain is:

```text
source_timestamp / published_at / availability_at
        <= observed_at / ingested_at
        <= prediction_cutoff_at
        < kickoff_at
        and model_run_at < kickoff_at
        and frozen_at proves the accepted input was sealed
```

The storage model must retain, where applicable:

- source-side time (`source_timestamp`, Evidence `published_at`, or provider time);
- system observation (`observed_at`, `retrieved_at`, `captured_at`) and ingestion (`ingested_at`);
- `prediction_cutoff_at` and canonical `kickoff_at` on Frozen Input and pre-match outputs;
- `model_run_at`/`run_at`, `run_completed_at`, and `frozen_at`;
- an explicit `availability_at` derivation and source-time basis;
- `future_information_leakage`, gate result, offending reference, and `TIER_A_ELIGIBLE`/promotion evidence flags;
- immutable hashes and audit entries proving which records were read.

No-future-leakage eligibility is a database-reconstructable predicate, not a free-text assertion:

```text
all critical availability_at <= prediction_cutoff_at
AND prediction_cutoff_at < kickoff_at
AND model_run_at < kickoff_at
AND no forbidden result/event/postmatch reference exists
AND future_information_leakage = FALSE
AND all referenced hashes resolve
```

If any term cannot be proven, the consuming artifact is `BLOCKED`/`INVALID`, Tier A eligibility is false, and the offending history remains append-only.

## 7. Logical uniqueness and key rules

The following are logical constraints to be implemented only in a future physical schema:

| Scope | Logical constraint |
|---|---|
| Match business key | `UNIQUE(matches.data_date, matches.official_match_no)`; `match_identity_key` must equal `data_date + ':' + official_match_no` |
| Team/competition | Stable UUID PK; normalized display/alias keys are scoped unique business keys only |
| Official odds dedup | `UNIQUE(match_id, source, snapshot_kind, captured_at, snapshot_hash)` or a stricter source-specific equivalent |
| External odds dedup | `UNIQUE(match_id, provider, market, normalized_line, captured_at, snapshot_hash)` |
| Frozen Input | `UNIQUE(match_id, frozen_input_revision)`; optional exact-hash dedup cannot remove revisions |
| Prediction | `UNIQUE(match_id, model_version_id, role, prediction_revision, stage)` |
| Frozen Prediction | `UNIQUE(match_id, freeze_revision, role, production_or_model_identity)` |
| Production release | at most one active Production pointer per `(model_family, canonical_output_channel)` |
| Official result | one current canonical pointer per `match_id`; historical result revisions remain many rows |
| Evidence bundle membership | `UNIQUE(evidence_bundle_id, evidence_id)` with stable order and inclusion role |
| Prediction engine membership | `UNIQUE(prediction_id, engine_run_id, market, lineage_purpose)` |
| Tier A sample | unique pair key over `match_id + production_prediction_id + shadow_prediction_id + shadow_revision`; sample sequence is also unique |
| Promotion sample membership | `UNIQUE(promotion_review_id, tier_a_sample_id)` |

An index or unique constraint never replaces a business entity PK. A partial/filtered active-row constraint is a future implementation detail; the logical rule is the single active pointer rule.

## 8. Referential integrity rules

The future store must reject or mark `BLOCKED` any record that violates these rules:

1. Every snapshot, context, evidence bundle, Frozen Input, output, prediction, result, review, Tier A record, and public projection resolves to one canonical `match_id`.
2. A Frozen Input's selected snapshot/context/evidence references resolve to exact IDs and hashes, and each source availability time is within the cutoff.
3. A Feature Bundle references exact accepted upstream lineage; a Frozen Input references one exact Feature Bundle and snapshot hash; an Engine Run references the exact Frozen Input and Feature Bundle identities it used.
4. A Prediction's `match_id` equals the Frozen Input's `match_id`; each Engine Run reference has the same match and declared role scope.
5. A Frozen Prediction's `match_id` equals its Prediction's `match_id`; its embedded snapshot hash matches the Prediction hash it freezes.
6. A Review's Frozen Prediction and Official Result both resolve to the same `match_id`.
7. A Tier A Production/Shadow pair has the same `match_id`, same `frozen_input_hash`, valid pre-kickoff completion, and distinct explicit roles.
8. A public projection references only a canonical Production Prediction/Frozen Prediction and a Production release; Shadow and Experiment IDs are rejected.
9. A correction's `supersedes_*_id` points to the same entity family and chain, and no chain points forward to a record that was not yet created.
10. V3.3.3 IDs, payloads, parameters, results, reviews, samples, and audit history are not valid V4 foreign keys.

These are typed relationship checks. A free-text note cannot satisfy a required foreign key or same-match condition.

## 9. Status model compatibility

The logical model keeps contract status and storage lifecycle state distinct where the existing V4-008 enum is narrower or differently named.

| Entity | Logical lifecycle states required by V4-009 | Contract/storage compatibility |
|---|---|---|
| `model_versions` | `DRAFT`, `EXPERIMENT`, `SHADOW`, `PROMOTION_REVIEW`, `PRODUCTION`, `RETIRED` | Exact V4-006/Runtime Boundary lifecycle; `BLOCKED` is a gate outcome, not a promotion state |
| `matches` | `SCHEDULED`, `OPEN`, `CLOSED`, `STARTED`, `FINISHED`, `CANCELLED`, `POSTPONED` | `match_status` retains the V4-008 enum (`IN_PROGRESS` represents `STARTED`); `OPEN`/`CLOSED` are a separate intake lifecycle field and do not alter canonical match status |
| `frozen_inputs` | `DRAFT`, `VALIDATED`, `FROZEN`, `REJECTED` | V4-008 `FROZEN`, `SUPERSEDED`, `BLOCKED` remain gate/storage outcomes; supersession is represented by chain metadata |
| `engine_runs` | `CREATED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INVALID` | V4-008 `run_status` may additionally carry `BLOCKED`/`CANCELLED`; no successful payload is fabricated for either |
| `predictions` | `DRAFT`, `FORMAL`, `FROZEN`, `SUPERSEDED`, `INVALID` | Contract recommendation/status fields remain separate; `FROZEN` refers to the downstream freeze boundary |
| `promotion_reviews` | `OPEN`, `APPROVED`, `REJECTED`, `WITHDRAWN` | Manual approval and the explicit Production release identity are required for `APPROVED` |
| `incidents` | `OPEN`, `MITIGATED`, `RESOLVED`, `CLOSED` | Incident class/severity remain separate; closure requires the existing Incident Policy criteria |

No existing V4-008 enum is silently renamed or reused. A future schema may store both fields when necessary.

## 10. Deletion and correction rule

The default is `NO HARD DELETE` for all audit-critical rows, including source snapshots, evidence, Frozen Inputs, Engine Runs, Predictions, Frozen Predictions, Results, Reviews, Tier A, Promotion, Calibration, Incidents, Audit Logs, and Public Read revisions. A legal/GDPR/security deletion, if ever mandatory, is a separately approved compliance workflow with a tombstone, scope, actor, reason, and audit evidence; it is not routine model maintenance.

Factual correction appends a new source/revision/correction event. A model output error never edits historical output; it receives review/error attribution. A Frozen Prediction is immutable. An Official Result correction appends a new result revision and downstream review correction chain while retaining the original result and evaluation.

## 11. V3.3.3 boundary

This model is V4-only. It does not copy, migrate, rename, or mutate JCFB V3.3.3 code, parameters, predictions, Frozen Predictions, reviews, Tier A samples, results, or audit history. A benchmark may use a separately authorized read boundary, but V3.3.3 artifacts are not V4 model entities or foreign keys.

## 12. Design acceptance conditions

V4-009 may be accepted only when:

- the seven V4-009 documents exist and agree on entity names, IDs, roles, hashes, revisions, and boundaries;
- the ER model shows the Match → Snapshot/Context/Evidence → Frozen Input → Engine Run/Prediction → Frozen Prediction → Result/Review → Tier A/Promotion chain;
- Production/Shadow/Experiment isolation and same-Frozen-Input A/B are mechanically expressible;
- no-future-leakage eligibility is reconstructable from persisted timestamps and references;
- append-only and correction rules prohibit history deletion or in-place mutation;
- public projections can reference only Production canonical records;
- Cross-Contract and Constitution checks pass and no V3.3.3 path is changed.

## 13. V4-009 cross-contract consistency matrix

| Existing authority | Model compatibility check |
|---|---|
| `V4_DATA_CONTRACT.md` | stable UUID identities, explicit availability states, source/provenance/time fields, canonical hashes, objective-fact/model-interpretation separation, and fail-closed behavior are preserved |
| `V4_FROZEN_INPUT_CONTRACT.md` | Frozen Input stores exact match/snapshot/context/evidence/feature/version refs, cutoff/kickoff, A/B group/mode, immutable flag, and `frozen_input_hash`; role is not added to the substantive A/B hash |
| `V4_ENGINE_OUTPUT_CONTRACT.md` | every Engine Run stores role, model/engine/revision, implementation/config/input/output hashes, Frozen Input hash, run times, payload/error state, and no fabricated success output |
| `V4_PREDICTION_CONTRACT.md` | Prediction is one match/one Frozen Input with many exact Engine Run refs, all five independent markets, separate consensus/disagreement/uncertainty/risk, and immutable Frozen Prediction lineage |
| `V4_RESULT_REVIEW_CONTRACT.md` | Results are postmatch and regulation-scoped by default; Review binds same-match Frozen Prediction + Result and keeps Model Evaluation separate from Match Explanation |
| `V4_RUNTIME_ROLE_BOUNDARY.md` | role is explicit and immutable; Production is canonical, Shadow is evidence-only, Experiment is research-only, and promotion creates a new identity |
| `V4_VERSIONING_STANDARD.md` | semantic version, registry revision, status, role revision, migration/dataset/schema identity, and hashes remain distinct; no nickname becomes an identity |
| `V4_CONSTITUTION.md` | no future leakage, immutable freezes, manual promotion, append-only correction, public read-only path, and V3.3.3 protection remain higher-order constraints |

No relationship or persistence rule in this V4-009 model weakens an existing V4-008 contract. Any future physical schema conflict is `BLOCKED` until the relevant contract/governance version is formally changed.

## 14. V4-009 Self Audit

| Audit item | Pass condition | Result |
|---|---|---|
| Stable primary keys | UUID/UUIDv7 PKs are defined for business entities | PASS |
| Business key separation | daily match key, aliases, labels, and release aliases never replace PKs | PASS |
| Role isolation | Production/Shadow/Experiment have explicit namespaces, permissions, and immutable role identity | PASS |
| Frozen Input core | all formal downstream lineage is anchored to exact Frozen Input ID/hash | PASS |
| Same-input A/B | Production/Shadow equality is checkable by match, cutoff, A/B group, and `frozen_input_hash` | PASS |
| Append-only boundary | every audit-critical entity is listed with immutable/revisioned behavior | PASS |
| Revision chains | current-to-predecessor `supersedes` links exist for input, prediction, freeze, result, review, and release identity | PASS |
| No future leakage | source/observation/ingestion/run/freeze/kickoff/cutoff facts and gate flags can reconstruct eligibility | PASS |
| Public read isolation | projection contains only safe canonical Production fields and has no write-back path | PASS |
| Tier A integrity | sample binds same-match Production/Shadow outputs, same Frozen Input hash, result/review, hashes, and pre-kickoff gates | PASS |
| Typed relationships | same-match, same-role, same-hash, and source-official checks are explicit rather than free-text | PASS |
| V3.3.3 isolation | no V4 entity or relationship references V3.3.3 artifacts | PASS |
| Contract compatibility | matrix above covers all required V4-008 and governance contracts | PASS |
| Constitution compatibility | authority, correction, security, public, promotion, and fail-closed rules are retained | PASS |

Self Audit result: `PASS` for the logical model. This result is documentation evidence only; it does not authorize database migration, model execution, or V4-010 work.
