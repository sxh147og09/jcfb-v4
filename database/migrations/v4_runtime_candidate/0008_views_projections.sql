-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.008
-- source_design_file: database/migrations/v4/0008_views_projections.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: PENDING_CANONICAL_HASH
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.008
-- sequence: 0008
-- name: v4-views-projections
-- migration_version: migration@20260901.008
-- depends_on: [migration@20260901.007]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- This candidate creates the public projection boundary; it publishes no Production output.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

CREATE TABLE public.public_read_projections (
  projection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id uuid NOT NULL REFERENCES core.matches(match_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_model_version_id uuid NOT NULL REFERENCES governance.model_versions(model_version_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_prediction_id uuid NOT NULL REFERENCES model.predictions(prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  production_frozen_prediction_id uuid NOT NULL REFERENCES model.frozen_predictions(frozen_prediction_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  public_odds_snapshot_id uuid REFERENCES market.official_odds_snapshots(snapshot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  competition_name text NOT NULL,
  home_team_name text NOT NULL,
  away_team_name text NOT NULL,
  kickoff_at timestamptz NOT NULL,
  match_status text NOT NULL,
  public_model_name text NOT NULL,
  public_model_version text NOT NULL,
  public_model_revision text NOT NULL,
  safe_odds_summary jsonb NOT NULL CHECK (jsonb_typeof(safe_odds_summary) = 'object'),
  safe_selection_summary jsonb NOT NULL CHECK (jsonb_typeof(safe_selection_summary) = 'object'),
  safe_result_summary jsonb,
  prediction_business_at timestamptz NOT NULL,
  frozen_business_at timestamptz NOT NULL,
  odds_business_at timestamptz NOT NULL,
  context_business_at timestamptz NOT NULL,
  result_business_at timestamptz,
  review_business_at timestamptz,
  projection_revision integer NOT NULL CHECK (projection_revision > 0),
  projection_hash text NOT NULL CHECK (governance.is_v4_hash(projection_hash)),
  payload_hash text NOT NULL CHECK (governance.is_v4_hash(payload_hash)),
  provenance_hash text NOT NULL CHECK (governance.is_v4_hash(provenance_hash)),
  hash_algorithm text NOT NULL DEFAULT 'SHA-256' CHECK (hash_algorithm = 'SHA-256'),
  hash_profile text NOT NULL DEFAULT 'v4-canonical-json@1.0',
  publication_status text NOT NULL CHECK (publication_status IN ('PUBLISHED', 'WITHDRAWN', 'BLOCKED')),
  published_at timestamptz,
  contract_version text NOT NULL,
  schema_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  UNIQUE (match_id, production_frozen_prediction_id, projection_revision),
  CHECK ((publication_status = 'PUBLISHED') = (published_at IS NOT NULL))
);

ALTER TABLE public.public_read_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_read_projections FORCE ROW LEVEL SECURITY;

-- Trigger attachments are possible only after the ledger exists. The
-- validator rejects Shadow/Experiment refs, unsafe fields, and unproven
-- business timestamps; the append-only trigger rejects all UPDATE/DELETE.
CREATE TRIGGER v4_public_projection_scope_gate
BEFORE INSERT ON public.public_read_projections
FOR EACH ROW EXECUTE FUNCTION governance.validate_public_projection();
CREATE TRIGGER v4_public_projection_audit_event
AFTER INSERT ON public.public_read_projections
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_public_projection_append_only
BEFORE UPDATE OR DELETE ON public.public_read_projections
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();

REVOKE ALL ON SCHEMA public FROM PUBLIC, anon, authenticated;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON TABLE public.public_read_projections FROM PUBLIC, anon, authenticated;

-- The policy is limited to safe published rows. Column-level grants below are
-- only the minimum underlying access required by security_invoker views.
CREATE POLICY v4_public_projection_published_read
ON public.public_read_projections
FOR SELECT TO anon, authenticated
USING (publication_status = 'PUBLISHED');

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT ON TABLE public.public_read_projections TO service_role;
GRANT SELECT (
  match_id, competition_name, home_team_name, away_team_name, kickoff_at,
  match_status, public_model_name, public_model_version, public_model_revision,
  safe_odds_summary, safe_selection_summary, safe_result_summary,
  prediction_business_at, frozen_business_at, odds_business_at,
  context_business_at, result_business_at, review_business_at,
  projection_revision, publication_status, created_at
)
ON public.public_read_projections TO anon, authenticated;

CREATE VIEW public.v_public_predictions
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id, p.competition_name, p.home_team_name, p.away_team_name,
    p.kickoff_at, p.match_status, p.safe_selection_summary,
    p.safe_odds_summary, p.prediction_business_at, p.frozen_business_at,
    p.odds_business_at, p.context_business_at, p.result_business_at,
    p.review_business_at, p.projection_revision, p.publication_status,
    p.created_at,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.projection_revision DESC, p.created_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT
  r.match_id, r.competition_name, r.home_team_name, r.away_team_name,
  r.kickoff_at, r.match_status, r.safe_selection_summary,
  r.safe_odds_summary, r.frozen_business_at AS frozen_at,
  GREATEST(
    r.prediction_business_at, r.frozen_business_at, r.odds_business_at,
    r.context_business_at,
    COALESCE(r.result_business_at, '-infinity'::timestamptz),
    COALESCE(r.review_business_at, '-infinity'::timestamptz)
  ) AS canonical_latest_update_at
FROM ranked AS r
WHERE r.rn = 1;

CREATE VIEW public.v_public_latest_odds
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id, p.kickoff_at, p.safe_odds_summary, p.odds_business_at,
    p.publication_status, p.projection_revision,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.odds_business_at DESC, p.projection_revision DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT match_id, kickoff_at, safe_odds_summary, odds_business_at, publication_status
FROM ranked WHERE rn = 1;

CREATE VIEW public.v_current_frozen_predictions
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.match_id, p.kickoff_at, p.safe_selection_summary,
    p.prediction_business_at, p.frozen_business_at, p.projection_revision,
    p.publication_status,
    row_number() OVER (
      PARTITION BY p.match_id
      ORDER BY p.projection_revision DESC, p.frozen_business_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT match_id, kickoff_at, safe_selection_summary,
       frozen_business_at AS frozen_at, prediction_business_at,
       frozen_business_at, projection_revision
FROM ranked WHERE rn = 1;

CREATE VIEW public.v_canonical_latest_update
WITH (security_invoker = true)
AS
WITH business_updates AS (
  SELECT
    p.match_id,
    GREATEST(
      p.prediction_business_at, p.frozen_business_at, p.odds_business_at,
      p.context_business_at,
      COALESCE(p.result_business_at, '-infinity'::timestamptz),
      COALESCE(p.review_business_at, '-infinity'::timestamptz)
    ) AS business_update_at
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT match_id, MAX(business_update_at) AS canonical_latest_update_at
FROM business_updates GROUP BY match_id;

CREATE VIEW public.v_tier_a_progress
WITH (security_invoker = true)
AS
SELECT
  count(*) FILTER (WHERE qualification_status = 'ELIGIBLE') AS eligible_sample_count,
  count(*) FILTER (WHERE qualification_status = 'REJECTED') AS rejected_sample_count,
  count(*) FILTER (WHERE qualification_status = 'BLOCKED') AS blocked_sample_count,
  MAX(sample_no) FILTER (WHERE qualification_status = 'ELIGIBLE') AS last_eligible_sample_no,
  MAX(created_at) AS as_of_business_at
FROM evaluation.tier_a_samples;

CREATE VIEW public.v_model_registry_public
WITH (security_invoker = true)
AS
WITH ranked AS (
  SELECT
    p.public_model_name, p.public_model_version, p.public_model_revision,
    p.projection_revision, p.frozen_business_at, p.publication_status,
    p.created_at,
    row_number() OVER (
      PARTITION BY p.public_model_name, p.public_model_version
      ORDER BY p.projection_revision DESC, p.created_at DESC
    ) AS rn
  FROM public.public_read_projections AS p
  WHERE p.publication_status = 'PUBLISHED'
)
SELECT public_model_name, public_model_version, public_model_revision,
       publication_status, frozen_business_at AS effective_at
FROM ranked WHERE rn = 1;

GRANT SELECT ON public.v_public_predictions,
               public.v_public_latest_odds,
               public.v_current_frozen_predictions,
               public.v_canonical_latest_update
TO anon, authenticated;
GRANT SELECT ON public.v_public_predictions,
               public.v_public_latest_odds,
               public.v_current_frozen_predictions,
               public.v_canonical_latest_update,
               public.v_tier_a_progress,
               public.v_model_registry_public
TO service_role;
-- v_tier_a_progress and v_model_registry_public remain approved/internal
-- views until a separate public-safe column review grants them.

CREATE INDEX public_projection_business_latest_idx
ON public.public_read_projections (
  GREATEST(
    prediction_business_at, frozen_business_at, odds_business_at,
    context_business_at,
    COALESCE(result_business_at, '-infinity'::timestamptz),
    COALESCE(review_business_at, '-infinity'::timestamptz)
  ) DESC,
  match_id
)
WHERE publication_status = 'PUBLISHED';

COMMIT;
