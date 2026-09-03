# JCFB V4 Index Blueprint 1.0

Status: V4-010 INDEX DESIGN (DESIGN-ONLY)

These are candidate indexes, not executed statements. Unique constraints may create their own indexes; the migration must not add a duplicate non-unique index with the same leading key.

## 1. Index type policy

- **B-tree** is the default for UUID equality, business-key uniqueness, role/status filters, timestamp ordering, and joins.
- **Partial B-tree** is used when a predicate is stable and semantically required, such as the one active Production release, published projections, or eligible Tier A. The predicate must exactly match the gate rule.
- **Covering (`INCLUDE`)** is reserved for proven public/read paths where a small safe column set can avoid heap fetches. Do not include raw payloads or secrets.
- **BRIN** is a candidate for very large append-only time-ordered tables (`audit_logs`, snapshots, runs). It is much smaller than B-tree but depends on physical time correlation; it does not replace lookup/uniqueness indexes.
- **GIN** is optional for approved JSONB containment/search queries on payload columns. It is not a substitute for typed columns or FKs, and no blanket JSONB index is planned.
- **Hash** indexes are not needed: B-tree handles equality and also supports ordering/range predicates.

## 2. Required unique/access indexes

| Name | Table | Definition/predicate | Purpose |
|---|---|---|---|
| `matches_daily_business_key_uq` | `core.matches` | `UNIQUE (data_date, official_match_no)` | Required daily official lookup and duplicate rejection. |
| `matches_identity_key_idx` | `core.matches` | `(match_identity_key)` | Fast canonical lookup; uniqueness remains the typed daily key. |
| `official_odds_dedup_uq` | `market.official_odds_snapshots` | `UNIQUE (match_id, source, snapshot_kind, captured_at, snapshot_hash)` | Exact official snapshot dedup. |
| `external_market_dedup_uq` | `market.external_market_snapshots` | `UNIQUE (match_id, provider, market, normalized_line, captured_at, snapshot_hash)` | Exact provider/market/line snapshot dedup. |
| `team_context_evidence_membership_uq` | `context.team_context_evidence` | `UNIQUE (team_context_id, evidence_id)` | Prevents duplicate context evidence references. |
| `frozen_inputs_match_revision_uq` | `model.frozen_inputs` | `UNIQUE (match_id, revision)` | Required Frozen Input revision uniqueness. |
| `frozen_inputs_revision_id_idx` | `model.frozen_inputs` | `(match_id, revision DESC)` | Latest/chain traversal; may be covered by the unique index if ordering direction is acceptable. |
| `prediction_logical_uq` | `model.predictions` | `UNIQUE (match_id, model_version_id, role, stage, prediction_revision)` | Required logical Prediction identity. |
| `frozen_predictions_revision_uq` | `model.frozen_predictions` | `UNIQUE (match_id, role, model_version_id, freeze_revision)` | Required immutable freeze revision identity. |
| `result_match_revision_uq` | `evaluation.official_results` | `UNIQUE (match_id, result_revision)` | Result correction chain uniqueness. |
| `review_revision_uq` | `evaluation.postmatch_reviews` | `UNIQUE (frozen_prediction_id, review_type, review_revision)` | Evaluation/explanation revision uniqueness. |
| `tier_a_pair_uq` | `evaluation.tier_a_samples` | `UNIQUE (match_id, production_prediction_id, shadow_prediction_id, shadow_revision)` | Required immutable A/B pair dedup. |
| `tier_a_sample_no_uq` | `evaluation.tier_a_samples` | `UNIQUE (sample_no)` | V4 Tier A sequence never reused. |
| `active_production_model_uq` | `governance.model_versions` | `(model_family, canonical_output_channel) WHERE role='PRODUCTION' AND status='PRODUCTION' AND is_canonical_active` | At most one active Production release per family/channel. |
| `active_production_engine_uq` | `governance.engine_versions` | `(engine_name, canonical_output_channel) WHERE role='PRODUCTION' AND status='PRODUCTION' AND is_canonical_active` | Optional matching engine uniqueness. |
| `public_projection_revision_uq` | `public.public_read_projections` | `UNIQUE (match_id, production_frozen_prediction_id, projection_revision)` | Projection history uniqueness. |
| `audit_entry_hash_uq` | `governance.audit_logs` | `UNIQUE (entry_hash)` | Hash-chain duplicate rejection. |

## 3. Required time/lineage indexes

| Name | Table | Definition | Purpose |
|---|---|---|---|
| `official_odds_match_captured_idx` | official snapshots | `(match_id, captured_at DESC)` | Snapshot chronology and cutoff selection. |
| `external_market_match_captured_idx` | external snapshots | `(match_id, captured_at DESC)` | Provider chronology and cutoff selection. |
| `official_odds_snapshot_hash_idx` | official snapshots | `(snapshot_hash)` | Replay/hash lookup; dedup constraint remains composite. |
| `external_snapshot_hash_idx` | external snapshots | `(snapshot_hash)` | Replay/hash lookup; never joins to official source by hash. |
| `team_context_match_asof_idx` | context snapshots | `(match_id, team_id, as_of_at DESC)` | Context selection by match/team/time. |
| `evidence_match_published_idx` | evidence | `(match_id, published_at DESC)` where `match_id IS NOT NULL` | Evidence chronology and cutoff selection. |
| `evidence_bundle_match_cutoff_idx` | evidence bundles | `(match_id, prediction_cutoff_at DESC)` | Bundle selection by cutoff. |
| `team_context_evidence_context_idx` | context evidence membership | `(team_context_id, availability_at DESC)` | Context source lineage and cutoff audit. |
| `team_context_evidence_evidence_idx` | context evidence membership | `(evidence_id, team_context_id)` | Reverse evidence usage lookup. |
| `frozen_inputs_hash_idx` | Frozen Inputs | `(frozen_input_hash)` | Same-input A/B equality and replay. This is intentionally non-unique. |
| `frozen_inputs_status_idx` | Frozen Inputs | `(match_id, status, frozen_at DESC)` | Gate/current chain lookup. |
| `engine_runs_lineage_idx` | Engine Runs | `(frozen_input_id, role, engine_version_id)` | Required runtime lineage lookup. |
| `engine_runs_input_hash_idx` | Engine Runs | `(input_hash)` | Reproducibility/cache identity lookup. |
| `engine_runs_output_hash_idx` | Engine Runs | `(output_hash)` | Output replay/audit lookup. |
| `engine_runs_match_run_idx` | Engine Runs | `(match_id, role, run_at DESC)` | Pre-match role run chronology. |
| `predictions_match_role_idx` | Predictions | `(match_id, role, model_version_id, stage, prediction_revision DESC)` | Role/model prediction retrieval. The unique index may satisfy this path. |
| `frozen_predictions_match_freeze_idx` | Frozen Predictions | `(match_id, freeze_revision DESC)` | Required match/freeze revision lookup. |
| `reviews_frozen_prediction_idx` | Reviews | `(frozen_prediction_id, reviewed_at DESC)` | Required review history lookup. |
| `tier_a_shadow_qualified_idx` | Tier A | `(shadow_model_version_id, shadow_engine_version_id, shadow_revision, match_id)` where `qualification_status='ELIGIBLE'` | Qualified Shadow evidence lookup. |
| `tier_a_hash_idx` | Tier A | `(frozen_input_hash, match_id)` | Same-input qualification audits. |
| `promotion_samples_idx` | Promotion membership | `(promotion_review_id, tier_a_sample_id)` | Evidence aggregation. Unique constraint covers duplicates. |
| `audit_entity_time_idx` | Audit Logs | `(entity_type, entity_id, happened_at)` | Entity history traversal. |
| `audit_prev_hash_idx` | Audit Logs | `(prev_hash)` | Hash-chain adjacency/replay. |
| `incident_severity_status_time_idx` | Incidents | `(severity, status, created_at DESC)` | Operational triage. |
| `incident_entity_idx` | Incidents | `(affected_entity_type, affected_entity_id, created_at DESC)` | Affected-object history. |

## 4. Public latest-update support

`public.v4_canonical_latest_update` derives the business timestamp from the projection ledger, not from a page build/deploy field. The underlying candidate expression index is:

```sql
-- Candidate only; do not apply from this blueprint.
CREATE INDEX public_projection_business_latest_idx
ON public.public_read_projections
(
  GREATEST(
    prediction_business_at,
    frozen_business_at,
    odds_business_at,
    context_business_at,
    COALESCE(result_business_at, '-infinity'::timestamptz),
    COALESCE(review_business_at, '-infinity'::timestamptz)
  ) DESC,
  match_id
)
WHERE publication_status = 'PUBLISHED';
```

The publication gate must prove that each typed business time was copied from the exact Production Prediction, Frozen Prediction, official odds, Team Context, Official Result, or Review row used for the projection. `published_at`, `created_at`, API time, page build time, and deploy time are not inputs to this expression.

## 5. Foreign-key support index checklist

At minimum, index every FK not already covered by a leftmost unique key:

`team_aliases.team_id`, `matches.competition_id`, `matches.home_team_id`, `matches.away_team_id`, official/external `match_id`, context `match_id/team_id`, evidence scope IDs, bundle/item IDs, engine predecessor/model IDs, all Frozen Input selection parent/ref IDs, feature `frozen_input_id`, Engine Run `match_id/frozen_input_id/feature_bundle_id/model_version_id/engine_version_id`, Prediction `match_id/frozen_input_id/model_version_id/supersedes_prediction_id`, prediction/run join IDs, Frozen Prediction `match_id/prediction_id/frozen_input_id/model_version_id/supersedes_frozen_prediction_id`, result/review/tier/promotion/calibration/incident/projection FKs.

Some are intentionally combined into the composite indexes above. The future migration must run a missing-FK-index check and remove redundant single-column indexes whose leading key is already covered.

## 6. BRIN and payload index candidates

- Add a BRIN index on `governance.audit_logs.happened_at` when the table is large and append order remains correlated with event time. Retain `audit_entity_time_idx` for selective entity lookups.
- Add BRIN on `market.*.captured_at` only after volume/correlation measurements; retain `(match_id, captured_at DESC)` B-tree for normal match reads.
- Add optional GIN with `jsonb_path_ops` only for a proven `@>` query over a specific payload (for example, an approved provider-price search). Use an expression B-tree for a frequently filtered scalar JSONB key. Do not index all payloads by default.
- Do not use BRIN for the unique/dedup keys, FK equality lookups, role isolation checks, or Production uniqueness.

## 7. Covering index policy

`INCLUDE` is allowed only after query evidence. A safe example is a public projection lookup that filters by `match_id` and returns only `kickoff_at`, `publication_status`, and business timestamps. Raw prediction snapshots, internal release IDs, risk decomposition, source references, or feature payloads must not be added to a public covering index.

## 8. Advisor and maintenance checks

Before a migration is approved, inspect `pg_stat_user_indexes`/advisor output for duplicate, unused, or overlapping indexes; confirm every FK is indexed; confirm partial predicates match the gate functions; measure write amplification on append-only tables; and verify `ANALYZE`/vacuum behavior. Indexes never weaken RLS, append-only triggers, no-future gates, or V3.3.3 isolation.
