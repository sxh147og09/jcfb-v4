-- JCFB V4 RUNTIME VALIDATION CANDIDATE
-- RUNTIME VALIDATION CANDIDATE
-- DISPOSABLE/STAGING ONLY
-- NOT APPROVED FOR PRODUCTION
-- candidate_identity: v4-runtime-candidate@20260901.007
-- source_design_file: database/migrations/v4/0007_security_rls.sql
-- source_design_commit: cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
-- candidate_manifest: database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md
-- canonical_migration_hash: PENDING_CANONICAL_HASH
-- production_status: PRODUCTION_REVIEW_REQUIRED
--
-- migration_id: migration@20260901.007
-- sequence: 0007
-- name: v4-security-rls
-- migration_version: migration@20260901.007
-- depends_on: [migration@20260901.006]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- This candidate installs the disposable security, trigger, RLS, and role boundary.

BEGIN;

SET LOCAL TIME ZONE 'UTC';

-- All runtime validators below are reviewed fail-closed gates. None repairs a
-- mismatch or manufactures a missing hash/time/source.
-- Runtime validation gates. Every gate is fail-closed: it rejects an
-- unverifiable identity, time, source, role, hash, or approval instead of
-- repairing or inferring one.
CREATE OR REPLACE FUNCTION governance.reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'V4 append-only violation on %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = '55000';
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION governance.protect_frozen_input_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
  boundary text := COALESCE(NULLIF(current_setting('v4.write_boundary', true), ''), '');
  old_data jsonb := to_jsonb(OLD);
  new_data jsonb := to_jsonb(NEW);
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'FROZEN_INPUT_DELETE is not allowed' USING ERRCODE = '55000';
  END IF;
  IF OLD.immutable OR OLD.status IN ('FROZEN', 'SUPERSEDED') THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MUTATION is not allowed' USING ERRCODE = '55000';
  END IF;
  IF boundary <> 'FREEZE_GATE' THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MUTATION requires FREEZE_GATE context' USING ERRCODE = '55000';
  END IF;
  IF (new_data - ARRAY[
        'status', 'frozen_at', 'immutable', 'future_information_leakage',
        'run_invalid', 'tier_a_eligible', 'gate_reason', 'source_summary',
        'metadata'
      ]::text[]) IS DISTINCT FROM
     (old_data - ARRAY[
        'status', 'frozen_at', 'immutable', 'future_information_leakage',
        'run_invalid', 'tier_a_eligible', 'gate_reason', 'source_summary',
        'metadata'
      ]::text[]) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_IDENTITY_FIELDS_ARE_IMMUTABLE' USING ERRCODE = '55000';
  END IF;
  IF NEW.status IN ('FROZEN', 'SUPERSEDED') AND NOT NEW.immutable THEN
    RAISE EXCEPTION 'FROZEN_INPUT_STATUS_REQUIRES_IMMUTABLE' USING ERRCODE = '23514';
  END IF;
  IF NEW.immutable AND NEW.frozen_at IS NULL THEN
    RAISE EXCEPTION 'FROZEN_INPUT_IMMUTABLE_REQUIRES_FROZEN_AT' USING ERRCODE = '23514';
  END IF;
  IF NEW.frozen_at IS NOT NULL AND NEW.frozen_at >= NEW.kickoff_at THEN
    RAISE EXCEPTION 'FROZEN_INPUT_FREEZE_MUST_PRECEDE_KICKOFF' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.guard_registry_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
  boundary text := COALESCE(NULLIF(current_setting('v4.write_boundary', true), ''), '');
  actor text := COALESCE(NULLIF(current_setting('v4.actor', true), ''), current_user);
  old_data jsonb := to_jsonb(OLD);
  new_data jsonb := to_jsonb(NEW);
BEGIN
  IF boundary NOT IN ('REGISTRY_ADMIN', 'RELEASE_APPROVAL') THEN
    RAISE EXCEPTION 'REGISTRY_UPDATE_REQUIRES_CONTROLLED_BOUNDARY' USING ERRCODE = '55000';
  END IF;
  IF btrim(actor) = '' THEN
    RAISE EXCEPTION 'REGISTRY_UPDATE_REQUIRES_ACTOR' USING ERRCODE = '55000';
  END IF;
  IF (new_data - ARRAY[
        'status', 'is_canonical_active', 'effective_at', 'retired_at',
        'retirement_reason', 'approval_reference', 'approved_at', 'updated_at',
        'metadata'
      ]::text[]) IS DISTINCT FROM
     (old_data - ARRAY[
        'status', 'is_canonical_active', 'effective_at', 'retired_at',
        'retirement_reason', 'approval_reference', 'approved_at', 'updated_at',
        'metadata'
      ]::text[]) THEN
    RAISE EXCEPTION 'REGISTRY_IDENTITY_FIELDS_ARE_IMMUTABLE' USING ERRCODE = '55000';
  END IF;
  IF NEW.updated_at < OLD.updated_at THEN
    RAISE EXCEPTION 'REGISTRY_UPDATED_AT_MUST_BE_MONOTONIC' USING ERRCODE = '23514';
  END IF;
  IF NEW.status = 'PRODUCTION' AND OLD.status <> 'PROMOTION_REVIEW' THEN
    RAISE EXCEPTION 'PRODUCTION_REQUIRES_PROMOTION_REVIEW' USING ERRCODE = '55000';
  END IF;
  IF NEW.status = 'PRODUCTION' AND boundary <> 'RELEASE_APPROVAL' THEN
    RAISE EXCEPTION 'PRODUCTION_STATUS_REQUIRES_RELEASE_APPROVAL' USING ERRCODE = '55000';
  END IF;
  IF NEW.is_canonical_active AND boundary <> 'RELEASE_APPROVAL' THEN
    RAISE EXCEPTION 'CANONICAL_ACTIVE_REQUIRES_RELEASE_APPROVAL' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_source_separation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance
AS $$
DECLARE
  row_data jsonb := to_jsonb(NEW);
  source_type text := upper(COALESCE(row_data->>'source_type', ''));
  source_reference text := lower(COALESCE(row_data->>'source_reference', ''));
  is_official text := COALESCE(row_data->>'source_is_official', '');
BEGIN
  IF source_type = '' OR btrim(COALESCE(row_data->>'source_reference', '')) = '' THEN
    RAISE EXCEPTION 'SOURCE_IDENTITY_REQUIRED' USING ERRCODE = '23514';
  END IF;
  IF source_reference ~ '(password|secret|service[_-]?role|api[_-]?key|token=)' THEN
    RAISE EXCEPTION 'SOURCE_REFERENCE_SECRET_BOUNDARY_VIOLATION' USING ERRCODE = '22023';
  END IF;
  IF TG_TABLE_NAME = 'official_odds_snapshots' THEN
    IF is_official <> 'true' THEN
      RAISE EXCEPTION 'OFFICIAL_SOURCE_FLAG_REQUIRED' USING ERRCODE = '23514';
    END IF;
    IF source_type NOT IN ('OFFICIAL_FEED', 'OFFICIAL_SCREENSHOT', 'OFFICIAL_DOCUMENT') THEN
      RAISE EXCEPTION 'OFFICIAL_SOURCE_TYPE_REQUIRED' USING ERRCODE = '23514';
    END IF;
    IF source_type = 'OFFICIAL_SCREENSHOT'
       AND NULLIF(btrim(COALESCE(row_data->>'evidence_ref', '')), '') IS NULL THEN
      RAISE EXCEPTION 'OFFICIAL_SCREENSHOT_REQUIRES_EVIDENCE_REF' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'external_market_snapshots' THEN
    IF is_official <> 'false' THEN
      RAISE EXCEPTION 'EXTERNAL_SOURCE_MUST_NOT_BE_OFFICIAL' USING ERRCODE = '23514';
    END IF;
    IF source_type NOT IN ('EXTERNAL_FEED', 'EXTERNAL_SCREENSHOT', 'EXTERNAL_DOCUMENT') THEN
      RAISE EXCEPTION 'EXTERNAL_SOURCE_TYPE_REQUIRED' USING ERRCODE = '23514';
    END IF;
    IF NULLIF(btrim(COALESCE(row_data->>'provider', '')), '') IS NULL THEN
      RAISE EXCEPTION 'EXTERNAL_PROVIDER_REQUIRED' USING ERRCODE = '23514';
    END IF;
  ELSE
    RAISE EXCEPTION 'SOURCE_SEPARATION_TRIGGER_SCOPE_UNKNOWN' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_market_payload()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance
AS $$
DECLARE
  row_data jsonb := to_jsonb(NEW);
  required_markets text[] := ARRAY['spf', 'rqspf', 'total_goals', 'exact_score', 'half_full']::text[];
  market_name text;
  market_state jsonb;
  market_payload jsonb;
  unavailable_reasons jsonb;
  market_reason text;
  status_value text;
  price_key text;
  price_value jsonb;
  available boolean;
  key_count integer;
  reason_count integer;
BEGIN
  IF TG_TABLE_NAME = 'external_market_snapshots' THEN
    IF jsonb_typeof(row_data->'prices') IS DISTINCT FROM 'object'
       OR row_data->'prices' = '{}'::jsonb THEN
      RAISE EXCEPTION 'EXTERNAL_PRICES_MUST_BE_NONEMPTY_OBJECT' USING ERRCODE = '23514';
    END IF;
    FOR price_key, price_value IN SELECT key, value FROM jsonb_each(row_data->'prices') LOOP
      IF jsonb_typeof(price_value) IS DISTINCT FROM 'number'
         OR (price_value::text)::numeric <= 0 THEN
        RAISE EXCEPTION 'EXTERNAL_PRICE_MUST_BE_POSITIVE_NUMBER' USING ERRCODE = '23514';
      END IF;
    END LOOP;
    IF row_data->>'availability_time_state' = 'KNOWN'
       AND (row_data->>'availability_at')::timestamptz > (row_data->>'captured_at')::timestamptz THEN
      RAISE EXCEPTION 'EXTERNAL_AVAILABILITY_AFTER_CAPTURE' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
  END IF;

  IF TG_TABLE_NAME <> 'official_odds_snapshots' THEN
    RAISE EXCEPTION 'MARKET_PAYLOAD_TRIGGER_SCOPE_UNKNOWN' USING ERRCODE = '55000';
  END IF;
  IF jsonb_typeof(row_data->'market_availability') IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'OFFICIAL_MARKET_AVAILABILITY_MUST_BE_OBJECT' USING ERRCODE = '23514';
  END IF;
  SELECT count(*) INTO key_count
    FROM jsonb_object_keys(row_data->'market_availability') AS keys(market_key)
   WHERE keys.market_key = ANY(required_markets);
  SELECT count(*) INTO reason_count
    FROM jsonb_object_keys(row_data->'market_availability');
  IF key_count <> cardinality(required_markets) OR reason_count <> cardinality(required_markets) THEN
    RAISE EXCEPTION 'OFFICIAL_MARKET_KEYS_MUST_BE_EXACTLY_FIVE' USING ERRCODE = '23514';
  END IF;
  unavailable_reasons := row_data->'market_unavailable_reason';
  IF jsonb_typeof(unavailable_reasons) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'OFFICIAL_UNAVAILABLE_REASON_MUST_BE_OBJECT' USING ERRCODE = '23514';
  END IF;
  SELECT count(*) INTO reason_count FROM jsonb_object_keys(unavailable_reasons);
  IF reason_count <> cardinality(required_markets) THEN
    RAISE EXCEPTION 'OFFICIAL_UNAVAILABLE_REASON_KEYS_MUST_BE_EXACTLY_FIVE' USING ERRCODE = '23514';
  END IF;

  FOREACH market_name IN ARRAY required_markets LOOP
    market_state := row_data->'market_availability'->market_name;
    IF jsonb_typeof(market_state) IS DISTINCT FROM 'object'
       OR NOT (market_state ? 'available')
       OR NOT (market_state ? 'status')
       OR NOT (market_state ? 'reason') THEN
      RAISE EXCEPTION 'OFFICIAL_MARKET_STATE_FIELDS_REQUIRED for %', market_name USING ERRCODE = '23514';
    END IF;
    available := (market_state->>'available')::boolean;
    status_value := upper(COALESCE(market_state->>'status', ''));
    market_reason := btrim(COALESCE(market_state->>'reason', ''));
    market_payload := row_data->market_name;
    IF available THEN
      IF status_value <> 'AVAILABLE'
         OR market_payload IS NULL
         OR jsonb_typeof(market_payload) IS DISTINCT FROM 'object'
         OR market_payload = '{}'::jsonb THEN
        RAISE EXCEPTION 'OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD for %', market_name USING ERRCODE = '23514';
      END IF;
      IF market_name = 'rqspf' AND NOT (market_payload ? 'official_handicap') THEN
        RAISE EXCEPTION 'OFFICIAL_RQSPF_HANDICAP_REQUIRED' USING ERRCODE = '23514';
      END IF;
      FOR price_key, price_value IN SELECT key, value FROM jsonb_each(market_payload) LOOP
        IF price_key <> 'official_handicap'
           AND (jsonb_typeof(price_value) IS DISTINCT FROM 'number'
                OR (price_value::text)::numeric <= 0) THEN
          RAISE EXCEPTION 'OFFICIAL_PRICE_MUST_BE_POSITIVE_NUMBER for %', market_name USING ERRCODE = '23514';
        END IF;
      END LOOP;
    ELSE
      IF status_value <> 'UNAVAILABLE' OR market_reason = '' OR market_payload IS NOT NULL THEN
        RAISE EXCEPTION 'OFFICIAL_UNAVAILABLE_MARKET_REQUIRES_REASON_AND_NO_PAYLOAD for %', market_name USING ERRCODE = '23514';
      END IF;
      IF btrim(COALESCE(unavailable_reasons->>market_name, '')) = '' THEN
        RAISE EXCEPTION 'OFFICIAL_UNAVAILABLE_REASON_MAP_REQUIRED for %', market_name USING ERRCODE = '23514';
      END IF;
    END IF;
  END LOOP;
  IF row_data->>'availability_time_state' = 'KNOWN'
     AND (row_data->>'availability_at')::timestamptz > (row_data->>'captured_at')::timestamptz THEN
    RAISE EXCEPTION 'OFFICIAL_AVAILABILITY_AFTER_CAPTURE' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_context_evidence_lineage()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, context
AS $$
DECLARE
  context_match_id uuid;
  context_team_id uuid;
  context_as_of_at timestamptz;
  context_hash text;
  context_status text;
  evidence_match_id uuid;
  evidence_team_id uuid;
  evidence_hash text;
  evidence_status text;
BEGIN
  SELECT c.match_id, c.team_id, c.as_of_at, c.context_hash, c.status,
         e.match_id, e.team_id, e.evidence_hash, e.status
    INTO context_match_id, context_team_id, context_as_of_at, context_hash, context_status,
         evidence_match_id, evidence_team_id, evidence_hash, evidence_status
    FROM context.team_context_snapshots AS c
    JOIN context.evidence_items AS e ON e.evidence_id = NEW.evidence_id
   WHERE c.team_context_id = NEW.team_context_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF evidence_match_id IS NOT NULL AND context_match_id IS NOT NULL
     AND evidence_match_id IS DISTINCT FROM context_match_id THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_MATCH_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF evidence_team_id IS NOT NULL AND evidence_team_id IS DISTINCT FROM context_team_id THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_TEAM_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF NEW.used_evidence_hash IS DISTINCT FROM evidence_hash THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_HASH_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF NEW.availability_at > context_as_of_at THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_AVAILABILITY_AFTER_CONTEXT_ASOF' USING ERRCODE = '23514';
  END IF;
  IF context_status <> 'AVAILABLE' OR evidence_status <> 'AVAILABLE' THEN
    RAISE EXCEPTION 'CONTEXT_EVIDENCE_PARENT_NOT_AVAILABLE' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_revision_chain()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, context, evaluation
AS $$
DECLARE
  row_data jsonb := to_jsonb(NEW);
  parent_revision integer;
  parent_match_id uuid;
  parent_team_id uuid;
  parent_side text;
  parent_lineage_id uuid;
  parent_frozen_prediction_id uuid;
  parent_review_type text;
  parent_role text;
  parent_market text;
  parent_scope_key text;
  parent_confidence_band text;
  parent_window_start date;
  parent_window_end date;
  previous_max integer;
  new_revision integer;
  correction_reason text := btrim(COALESCE(row_data->'metadata'->>'correction_reason', ''));
  correction_actor text := btrim(COALESCE(row_data->'metadata'->>'correction_actor', ''));
BEGIN
  IF TG_TABLE_NAME = 'evidence_items' THEN
    new_revision := NEW.revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_evidence_id IS NOT NULL THEN
        RAISE EXCEPTION 'EVIDENCE_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_evidence_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'EVIDENCE_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT revision, match_id, team_id INTO parent_revision, parent_match_id, parent_team_id
      FROM context.evidence_items WHERE evidence_id = NEW.supersedes_evidence_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_match_id IS DISTINCT FROM NEW.match_id
       OR parent_team_id IS DISTINCT FROM NEW.team_id THEN
      RAISE EXCEPTION 'EVIDENCE_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'team_context_snapshots' THEN
    new_revision := NEW.revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_team_context_id IS NOT NULL THEN
        RAISE EXCEPTION 'CONTEXT_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_team_context_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'CONTEXT_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT revision, match_id, team_id, side INTO parent_revision, parent_match_id, parent_team_id, parent_side
      FROM context.team_context_snapshots WHERE team_context_id = NEW.supersedes_team_context_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_match_id IS DISTINCT FROM NEW.match_id
       OR parent_team_id IS DISTINCT FROM NEW.team_id
       OR parent_side IS DISTINCT FROM NEW.side THEN
      RAISE EXCEPTION 'CONTEXT_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'evidence_bundles' THEN
    new_revision := NEW.bundle_revision;
    IF new_revision > 1 THEN
      SELECT max(bundle_revision) INTO previous_max
        FROM context.evidence_bundles
       WHERE match_id = NEW.match_id AND evidence_bundle_id <> NEW.evidence_bundle_id;
      IF previous_max IS DISTINCT FROM new_revision - 1 OR correction_reason = '' OR correction_actor = '' THEN
        RAISE EXCEPTION 'EVIDENCE_BUNDLE_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
      END IF;
    END IF;
  ELSIF TG_TABLE_NAME = 'official_results' THEN
    new_revision := NEW.result_revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_result_id IS NOT NULL THEN
        RAISE EXCEPTION 'RESULT_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_result_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'RESULT_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT result_revision, match_id, result_lineage_id
      INTO parent_revision, parent_match_id, parent_lineage_id
      FROM evaluation.official_results WHERE result_id = NEW.supersedes_result_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_match_id IS DISTINCT FROM NEW.match_id
       OR parent_lineage_id IS DISTINCT FROM NEW.result_lineage_id THEN
      RAISE EXCEPTION 'RESULT_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'postmatch_reviews' THEN
    new_revision := NEW.review_revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_review_id IS NOT NULL THEN
        RAISE EXCEPTION 'REVIEW_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_review_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'REVIEW_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT review_revision, match_id, frozen_prediction_id, review_type
      INTO parent_revision, parent_match_id, parent_frozen_prediction_id, parent_review_type
      FROM evaluation.postmatch_reviews WHERE review_id = NEW.supersedes_review_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_match_id IS DISTINCT FROM NEW.match_id
       OR parent_frozen_prediction_id IS DISTINCT FROM NEW.frozen_prediction_id
       OR parent_review_type IS DISTINCT FROM NEW.review_type THEN
      RAISE EXCEPTION 'REVIEW_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'promotion_reviews' THEN
    new_revision := NEW.review_revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_promotion_review_id IS NOT NULL THEN
        RAISE EXCEPTION 'PROMOTION_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_promotion_review_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'PROMOTION_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT review_revision, candidate_model_version_id INTO parent_revision, parent_lineage_id
      FROM evaluation.promotion_reviews WHERE promotion_review_id = NEW.supersedes_promotion_review_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_lineage_id IS DISTINCT FROM NEW.candidate_model_version_id THEN
      RAISE EXCEPTION 'PROMOTION_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'calibration_records' THEN
    new_revision := NEW.record_revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_calibration_record_id IS NOT NULL THEN
        RAISE EXCEPTION 'CALIBRATION_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_calibration_record_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'CALIBRATION_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT record_revision, model_version_id, role, market, scope_key, confidence_band,
           sample_window_start, sample_window_end
      INTO parent_revision, parent_lineage_id, parent_role, parent_market, parent_scope_key,
           parent_confidence_band, parent_window_start, parent_window_end
      FROM evaluation.calibration_records
     WHERE calibration_record_id = NEW.supersedes_calibration_record_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_lineage_id IS DISTINCT FROM NEW.model_version_id
       OR parent_role IS DISTINCT FROM NEW.role
       OR parent_market IS DISTINCT FROM NEW.market
       OR parent_scope_key IS DISTINCT FROM NEW.scope_key
       OR parent_confidence_band IS DISTINCT FROM NEW.confidence_band
       OR parent_window_start IS DISTINCT FROM NEW.sample_window_start
       OR parent_window_end IS DISTINCT FROM NEW.sample_window_end THEN
      RAISE EXCEPTION 'CALIBRATION_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'incidents' THEN
    new_revision := NEW.incident_revision;
    IF new_revision = 1 THEN
      IF NEW.supersedes_incident_id IS NOT NULL THEN
        RAISE EXCEPTION 'INCIDENT_FIRST_REVISION_CANNOT_SUPERSEDE' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END IF;
    IF NEW.supersedes_incident_id IS NULL OR correction_reason = '' OR correction_actor = '' THEN
      RAISE EXCEPTION 'INCIDENT_CORRECTION_METADATA_REQUIRED' USING ERRCODE = '23514';
    END IF;
    SELECT incident_revision, incident_lineage_id INTO parent_revision, parent_lineage_id
      FROM governance.incidents WHERE incident_id = NEW.supersedes_incident_id;
    IF NOT FOUND OR parent_revision <> new_revision - 1
       OR parent_lineage_id IS DISTINCT FROM NEW.incident_lineage_id THEN
      RAISE EXCEPTION 'INCIDENT_REVISION_CHAIN_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSE
    RAISE EXCEPTION 'REVISION_TRIGGER_SCOPE_UNKNOWN' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_frozen_input_lineage()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, core, market, context, model
AS $$
DECLARE
  match_kickoff timestamptz;
BEGIN
  SELECT kickoff_at INTO match_kickoff FROM core.matches WHERE match_id = NEW.match_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MATCH_MISSING' USING ERRCODE = '23503';
  END IF;
  IF NEW.prediction_cutoff_at >= NEW.kickoff_at OR NEW.kickoff_at <> match_kickoff THEN
    RAISE EXCEPTION 'FROZEN_INPUT_TIME_BOUNDARY_INVALID' USING ERRCODE = '23514';
  END IF;
  IF NEW.frozen_at IS NOT NULL AND NEW.frozen_at >= NEW.kickoff_at THEN
    RAISE EXCEPTION 'FROZEN_INPUT_FREEZE_AFTER_KICKOFF' USING ERRCODE = '23514';
  END IF;
  IF NEW.status IN ('FROZEN', 'SUPERSEDED') AND NOT NEW.immutable THEN
    RAISE EXCEPTION 'FROZEN_INPUT_STATUS_IMMUTABILITY_INVALID' USING ERRCODE = '23514';
  END IF;
  IF NEW.owner_role = 'PRODUCTION' AND NEW.comparison_mode <> 'FORWARD_AB' THEN
    RAISE EXCEPTION 'PRODUCTION_FROZEN_INPUT_REQUIRES_FORWARD_AB' USING ERRCODE = '23514';
  END IF;
  IF NEW.owner_role = 'EXPERIMENT' AND NEW.comparison_mode <> 'EXPERIMENT_ONLY' THEN
    RAISE EXCEPTION 'EXPERIMENT_FROZEN_INPUT_REQUIRES_EXPERIMENT_ONLY' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_official_odds r
      JOIN market.official_odds_snapshots s ON s.snapshot_id = r.snapshot_id
     WHERE r.frozen_input_id = NEW.frozen_input_id
       AND (s.match_id IS DISTINCT FROM NEW.match_id
         OR r.used_snapshot_hash IS DISTINCT FROM s.snapshot_hash
         OR r.availability_at > NEW.prediction_cutoff_at
         OR s.availability_time_state <> 'KNOWN'
         OR s.source_is_official IS NOT TRUE)
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_OFFICIAL_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_external_markets r
      JOIN market.external_market_snapshots s ON s.snapshot_id = r.snapshot_id
     WHERE r.frozen_input_id = NEW.frozen_input_id
       AND (s.match_id IS DISTINCT FROM NEW.match_id
         OR r.used_snapshot_hash IS DISTINCT FROM s.snapshot_hash
         OR r.availability_at > NEW.prediction_cutoff_at
         OR s.availability_time_state <> 'KNOWN'
         OR s.source_is_official IS NOT FALSE)
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_EXTERNAL_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_contexts r
      JOIN context.team_context_snapshots c ON c.team_context_id = r.team_context_id
     WHERE r.frozen_input_id = NEW.frozen_input_id
       AND (c.match_id IS DISTINCT FROM NEW.match_id
         OR r.used_context_hash IS DISTINCT FROM c.context_hash
         OR r.availability_at > NEW.prediction_cutoff_at
         OR c.availability_time_state <> 'KNOWN')
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_CONTEXT_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_evidence_bundles r
      JOIN context.evidence_bundles b ON b.evidence_bundle_id = r.evidence_bundle_id
     WHERE r.frozen_input_id = NEW.frozen_input_id
       AND (b.match_id IS DISTINCT FROM NEW.match_id
         OR r.used_bundle_hash IS DISTINCT FROM b.bundle_hash
         OR b.prediction_cutoff_at > NEW.prediction_cutoff_at)
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_BUNDLE_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_model_refs r
      JOIN governance.model_versions v ON v.model_version_id = r.model_version_id
     WHERE r.frozen_input_id = NEW.frozen_input_id AND v.role <> NEW.owner_role
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MODEL_ROLE_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM model.frozen_input_engine_refs r
      JOIN governance.engine_versions v ON v.engine_version_id = r.engine_version_id
     WHERE r.frozen_input_id = NEW.frozen_input_id AND v.role <> NEW.owner_role
  ) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_ENGINE_ROLE_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF NEW.status IN ('FROZEN', 'SUPERSEDED')
     AND (NOT EXISTS (SELECT 1 FROM model.frozen_input_model_refs WHERE frozen_input_id = NEW.frozen_input_id)
       OR NOT EXISTS (SELECT 1 FROM model.frozen_input_engine_refs WHERE frozen_input_id = NEW.frozen_input_id)) THEN
    RAISE EXCEPTION 'FROZEN_INPUT_REQUIRES_MODEL_AND_ENGINE_REFS' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_runtime_lineage()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, core, model
AS $$
DECLARE
  fi_match_id uuid;
  fi_hash text;
  fi_cutoff timestamptz;
  fi_kickoff timestamptz;
  fi_owner_role text;
  fi_status text;
  bundle_input_id uuid;
  bundle_hash text;
  bundle_role text;
  bundle_status text;
  model_role text;
  model_status text;
  engine_role text;
  engine_model_id uuid;
BEGIN
  SELECT fi.match_id, fi.frozen_input_hash, fi.prediction_cutoff_at, fi.kickoff_at,
         fi.owner_role, fi.status,
         fb.frozen_input_id, fb.frozen_input_hash, fb.role, fb.status,
         mv.role, mv.status, ev.role, ev.model_version_id
    INTO fi_match_id, fi_hash, fi_cutoff, fi_kickoff, fi_owner_role, fi_status,
         bundle_input_id, bundle_hash, bundle_role, bundle_status,
         model_role, model_status, engine_role, engine_model_id
    FROM model.frozen_inputs fi
    JOIN model.feature_bundles fb ON fb.feature_bundle_id = NEW.feature_bundle_id
    JOIN governance.model_versions mv ON mv.model_version_id = NEW.model_version_id
    JOIN governance.engine_versions ev ON ev.engine_version_id = NEW.engine_version_id
   WHERE fi.frozen_input_id = NEW.frozen_input_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'RUNTIME_LINEAGE_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF fi_match_id IS DISTINCT FROM NEW.match_id
     OR bundle_input_id IS DISTINCT FROM NEW.frozen_input_id
     OR fi_hash IS DISTINCT FROM NEW.frozen_input_hash
     OR bundle_hash IS DISTINCT FROM NEW.frozen_input_hash
     OR bundle_role IS DISTINCT FROM NEW.role
     OR model_role IS DISTINCT FROM NEW.role
     OR engine_role IS DISTINCT FROM NEW.role
     OR engine_model_id IS DISTINCT FROM NEW.model_version_id THEN
    RAISE EXCEPTION 'RUNTIME_LINEAGE_ID_ROLE_HASH_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF NOT (NEW.role = fi_owner_role OR (NEW.role = 'SHADOW' AND fi_owner_role = 'PRODUCTION')) THEN
    RAISE EXCEPTION 'RUNTIME_FROZEN_INPUT_OWNER_ROLE_MISMATCH' USING ERRCODE = '23514';
  END IF;
  IF NEW.prediction_cutoff_at >= NEW.kickoff_at
     OR NEW.prediction_cutoff_at > fi_cutoff
     OR NEW.kickoff_at IS DISTINCT FROM fi_kickoff
     OR NEW.run_at > NEW.prediction_cutoff_at
     OR (NEW.run_completed_at IS NOT NULL AND NEW.run_completed_at > NEW.prediction_cutoff_at) THEN
    RAISE EXCEPTION 'RUNTIME_PREMATCH_TIME_BOUNDARY_INVALID' USING ERRCODE = '23514';
  END IF;
  IF NEW.tier_a_eligible AND (NEW.status <> 'SUCCEEDED' OR NEW.run_completed_at IS NULL
      OR NEW.future_information_leakage OR NEW.run_invalid) THEN
    RAISE EXCEPTION 'RUNTIME_TIER_A_ELIGIBILITY_INVALID' USING ERRCODE = '23514';
  END IF;
  IF fi_status IN ('BLOCKED', 'REJECTED') OR bundle_status IN ('BLOCKED', 'INVALID')
     OR model_status IN ('BLOCKED', 'RETIRED') THEN
    RAISE EXCEPTION 'RUNTIME_LINEAGE_PARENT_NOT_USABLE' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_prediction_engine_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, model
AS $$
DECLARE
  prediction_match_id uuid;
  prediction_role text;
  prediction_frozen_input_id uuid;
  prediction_frozen_hash text;
  prediction_output_hash text;
  run_match_id uuid;
  run_role text;
  run_frozen_input_id uuid;
  run_frozen_hash text;
  run_output_hash text;
BEGIN
  SELECT p.match_id, p.role, p.frozen_input_id, p.frozen_input_hash, p.output_hash,
         r.match_id, r.role, r.frozen_input_id, r.frozen_input_hash, r.output_hash
    INTO prediction_match_id, prediction_role, prediction_frozen_input_id, prediction_frozen_hash, prediction_output_hash,
         run_match_id, run_role, run_frozen_input_id, run_frozen_hash, run_output_hash
    FROM model.predictions p
    JOIN model.engine_runs r ON r.engine_run_id = NEW.engine_run_id
   WHERE p.prediction_id = NEW.prediction_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'PREDICTION_ENGINE_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF prediction_match_id IS DISTINCT FROM run_match_id
     OR prediction_role IS DISTINCT FROM run_role
     OR prediction_frozen_input_id IS DISTINCT FROM run_frozen_input_id
     OR prediction_frozen_hash IS DISTINCT FROM run_frozen_hash
     OR NEW.output_hash IS DISTINCT FROM run_output_hash
     OR NEW.output_hash IS DISTINCT FROM prediction_output_hash THEN
    RAISE EXCEPTION 'PREDICTION_ENGINE_MEMBERSHIP_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_frozen_prediction_lineage()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, model
AS $$
DECLARE
  prediction_match_id uuid;
  prediction_role text;
  prediction_frozen_input_id uuid;
  prediction_model_id uuid;
  prediction_hash text;
  prediction_frozen_hash text;
  input_match_id uuid;
  input_hash text;
  input_owner_role text;
BEGIN
  SELECT p.match_id, p.role, p.frozen_input_id, p.model_version_id,
         p.prediction_hash, p.frozen_input_hash,
         fi.match_id, fi.frozen_input_hash, fi.owner_role
    INTO prediction_match_id, prediction_role, prediction_frozen_input_id, prediction_model_id,
         prediction_hash, prediction_frozen_hash,
         input_match_id, input_hash, input_owner_role
    FROM model.predictions p
    JOIN model.frozen_inputs fi ON fi.frozen_input_id = p.frozen_input_id
   WHERE p.prediction_id = NEW.prediction_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'FROZEN_PREDICTION_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF NEW.match_id IS DISTINCT FROM prediction_match_id
     OR NEW.match_id IS DISTINCT FROM input_match_id
     OR NEW.role IS DISTINCT FROM prediction_role
     OR NEW.frozen_input_id IS DISTINCT FROM prediction_frozen_input_id
     OR NEW.model_version_id IS DISTINCT FROM prediction_model_id
     OR NEW.prediction_hash IS DISTINCT FROM prediction_hash
     OR NEW.frozen_input_hash IS DISTINCT FROM input_hash
     OR prediction_frozen_hash IS DISTINCT FROM input_hash
     OR NOT (NEW.role = input_owner_role OR (NEW.role = 'SHADOW' AND input_owner_role = 'PRODUCTION'))
     OR NEW.frozen_at > NEW.prediction_cutoff_at
     OR NEW.prediction_cutoff_at >= NEW.kickoff_at THEN
    RAISE EXCEPTION 'FROZEN_PREDICTION_LINEAGE_INVALID' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_prematch_gate()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, core, market, context, model
AS $$
DECLARE
  row_data jsonb := to_jsonb(NEW);
  cutoff_at timestamptz;
  kickoff_at timestamptz;
BEGIN
  IF row_data ? 'prediction_cutoff_at' THEN
    cutoff_at := (row_data->>'prediction_cutoff_at')::timestamptz;
  END IF;
  IF row_data ? 'kickoff_at' THEN
    kickoff_at := (row_data->>'kickoff_at')::timestamptz;
  END IF;
  IF cutoff_at IS NOT NULL AND kickoff_at IS NOT NULL AND cutoff_at >= kickoff_at THEN
    RAISE EXCEPTION 'PREMATCH_CUTOFF_MUST_PRECEDE_KICKOFF' USING ERRCODE = '23514';
  END IF;
  IF TG_TABLE_NAME IN ('frozen_inputs', 'feature_bundles', 'engine_runs', 'predictions', 'frozen_predictions', 'tier_a_samples') THEN
    IF row_data ? 'generated_at' AND row_data->>'generated_at' IS NOT NULL
       AND cutoff_at IS NOT NULL AND (row_data->>'generated_at')::timestamptz > cutoff_at THEN
      RAISE EXCEPTION 'PREMATCH_GENERATION_AFTER_CUTOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'run_at' AND row_data->>'run_at' IS NOT NULL
       AND cutoff_at IS NOT NULL AND (row_data->>'run_at')::timestamptz > cutoff_at THEN
      RAISE EXCEPTION 'PREMATCH_RUN_AFTER_CUTOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'run_completed_at' AND row_data->>'run_completed_at' IS NOT NULL
       AND cutoff_at IS NOT NULL AND (row_data->>'run_completed_at')::timestamptz > cutoff_at THEN
      RAISE EXCEPTION 'PREMATCH_COMPLETION_AFTER_CUTOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'model_run_at' AND row_data->>'model_run_at' IS NOT NULL
       AND cutoff_at IS NOT NULL AND (row_data->>'model_run_at')::timestamptz > cutoff_at THEN
      RAISE EXCEPTION 'PREMATCH_MODEL_RUN_AFTER_CUTOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'frozen_at' AND row_data->>'frozen_at' IS NOT NULL
       AND kickoff_at IS NOT NULL AND (row_data->>'frozen_at')::timestamptz >= kickoff_at THEN
      RAISE EXCEPTION 'PREMATCH_FREEZE_AFTER_KICKOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'production_run_completed_at' AND row_data->>'production_run_completed_at' IS NOT NULL
       AND kickoff_at IS NOT NULL AND (row_data->>'production_run_completed_at')::timestamptz >= kickoff_at THEN
      RAISE EXCEPTION 'TIER_A_PRODUCTION_COMPLETION_AFTER_KICKOFF' USING ERRCODE = '23514';
    END IF;
    IF row_data ? 'shadow_run_completed_at' AND row_data->>'shadow_run_completed_at' IS NOT NULL
       AND kickoff_at IS NOT NULL AND (row_data->>'shadow_run_completed_at')::timestamptz >= kickoff_at THEN
      RAISE EXCEPTION 'TIER_A_SHADOW_COMPLETION_AFTER_KICKOFF' USING ERRCODE = '23514';
    END IF;
    IF COALESCE((row_data->>'future_information_leakage')::boolean, false)
       AND (COALESCE((row_data->>'tier_a_eligible')::boolean, false)
         OR COALESCE((row_data->>'promotion_evidence')::boolean, false)) THEN
      RAISE EXCEPTION 'FUTURE_INFORMATION_LEAKAGE_INVALIDATES_ELIGIBILITY' USING ERRCODE = '23514';
    END IF;
    IF COALESCE((row_data->>'run_invalid')::boolean, false)
       AND COALESCE((row_data->>'tier_a_eligible')::boolean, false) THEN
      RAISE EXCEPTION 'INVALID_RUN_CANNOT_BE_TIER_A_ELIGIBLE' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_tier_a_pair()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, model, evaluation
AS $$
DECLARE
  prod_match_id uuid;
  shadow_match_id uuid;
  prod_input_id uuid;
  shadow_input_id uuid;
  prod_input_hash text;
  shadow_input_hash text;
  prod_cutoff timestamptz;
  shadow_cutoff timestamptz;
  prod_kickoff timestamptz;
  shadow_kickoff timestamptz;
  prod_role text;
  shadow_role text;
  prod_model_id uuid;
  shadow_model_id uuid;
  shadow_engine_id uuid;
  shadow_engine_role text;
  shadow_engine_model_id uuid;
BEGIN
  SELECT pp.match_id, sp.match_id, pp.frozen_input_id, sp.frozen_input_id,
         pp.frozen_input_hash, sp.frozen_input_hash,
         pp.prediction_cutoff_at, sp.prediction_cutoff_at,
         pp.kickoff_at, sp.kickoff_at, pp.role, sp.role,
         pp.model_version_id, sp.model_version_id,
         se.engine_version_id, se.role, se.model_version_id
    INTO prod_match_id, shadow_match_id, prod_input_id, shadow_input_id,
         prod_input_hash, shadow_input_hash,
         prod_cutoff, shadow_cutoff, prod_kickoff, shadow_kickoff,
         prod_role, shadow_role, prod_model_id, shadow_model_id,
         shadow_engine_id, shadow_engine_role, shadow_engine_model_id
    FROM model.predictions pp
    JOIN model.predictions sp ON sp.prediction_id = NEW.shadow_prediction_id
    JOIN governance.engine_versions se ON se.engine_version_id = NEW.shadow_engine_version_id
   WHERE pp.prediction_id = NEW.production_prediction_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'TIER_A_PAIR_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF prod_match_id IS DISTINCT FROM shadow_match_id
     OR prod_match_id IS DISTINCT FROM NEW.match_id
     OR prod_input_id IS DISTINCT FROM shadow_input_id
     OR prod_input_id IS DISTINCT FROM NEW.frozen_input_id
     OR prod_input_hash IS DISTINCT FROM shadow_input_hash
     OR prod_input_hash IS DISTINCT FROM NEW.frozen_input_hash
     OR prod_cutoff IS DISTINCT FROM shadow_cutoff
     OR prod_kickoff IS DISTINCT FROM shadow_kickoff
     OR prod_role <> 'PRODUCTION'
     OR shadow_role <> 'SHADOW'
     OR shadow_model_id IS DISTINCT FROM NEW.shadow_model_version_id
     OR shadow_engine_id IS DISTINCT FROM NEW.shadow_engine_version_id
     OR shadow_engine_role <> 'SHADOW'
     OR shadow_engine_model_id IS DISTINCT FROM shadow_model_id THEN
    RAISE EXCEPTION 'TIER_A_SAME_MATCH_SAME_FROZEN_INPUT_PAIR_REQUIRED' USING ERRCODE = '23514';
  END IF;
  IF NEW.production_run_completed_at >= NEW.kickoff_at
     OR NEW.shadow_run_completed_at >= NEW.kickoff_at
     OR NEW.prediction_cutoff_at >= NEW.kickoff_at THEN
    RAISE EXCEPTION 'TIER_A_PREMATCH_COMPLETION_REQUIRED' USING ERRCODE = '23514';
  END IF;
  IF NEW.tier_a_eligible AND NOT (
       NEW.pair_integrity_passed AND NEW.completeness_gate_passed
       AND NEW.pre_kickoff_gate_passed AND NOT NEW.future_information_leakage
       AND NEW.qualification_status = 'ELIGIBLE' AND NEW.promotion_evidence
     ) THEN
    RAISE EXCEPTION 'TIER_A_ELIGIBILITY_GATE_FAILED' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_production_release()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, evaluation
AS $$
DECLARE
  boundary text := COALESCE(NULLIF(current_setting('v4.write_boundary', true), ''), '');
  actor text := COALESCE(NULLIF(current_setting('v4.actor', true), ''), current_user);
  successor_family text;
  successor_channel text;
  successor_role text;
  successor_status text;
  successor_active boolean;
BEGIN
  IF boundary <> 'RELEASE_APPROVAL' OR btrim(actor) = '' THEN
    RAISE EXCEPTION 'PRODUCTION_RELEASE_REQUIRES_MANUAL_APPROVAL_CONTEXT' USING ERRCODE = '55000';
  END IF;
  IF NULLIF(current_setting('v4.actor', true), '') IS NOT NULL
     AND NEW.actor IS DISTINCT FROM current_setting('v4.actor', true) THEN
    RAISE EXCEPTION 'PRODUCTION_RELEASE_ACTOR_MISMATCH' USING ERRCODE = '55000';
  END IF;
  SELECT model_family, canonical_output_channel, role, status, is_canonical_active
    INTO successor_family, successor_channel, successor_role, successor_status, successor_active
    FROM governance.model_versions WHERE model_version_id = NEW.successor_model_version_id;
  IF NOT FOUND OR successor_family IS DISTINCT FROM NEW.model_family
     OR successor_channel IS DISTINCT FROM NEW.canonical_output_channel
     OR successor_role <> 'PRODUCTION'
     OR successor_status NOT IN ('PROMOTION_REVIEW', 'PRODUCTION') THEN
    RAISE EXCEPTION 'PRODUCTION_RELEASE_SUCCESSOR_INVALID' USING ERRCODE = '23514';
  END IF;
  IF NEW.action = 'ACTIVATE' THEN
    IF NOT (NEW.evidence ? 'promotion_review_id') THEN
      RAISE EXCEPTION 'PRODUCTION_ACTIVATION_REQUIRES_PROMOTION_EVIDENCE' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM evaluation.promotion_reviews pr
       WHERE pr.status = 'APPROVED'
         AND pr.production_model_version_id = NEW.successor_model_version_id
         AND pr.manual_approver IS NOT NULL
         AND pr.approved_at IS NOT NULL
    ) THEN
      RAISE EXCEPTION 'PRODUCTION_ACTIVATION_REQUIRES_APPROVED_PROMOTION_REVIEW' USING ERRCODE = '55000';
    END IF;
    IF EXISTS (
      SELECT 1 FROM governance.model_versions v
       WHERE v.model_family = NEW.model_family
         AND v.canonical_output_channel = NEW.canonical_output_channel
         AND v.role = 'PRODUCTION'
         AND v.status = 'PRODUCTION'
         AND v.is_canonical_active
         AND v.model_version_id IS DISTINCT FROM NEW.previous_model_version_id
         AND v.model_version_id IS DISTINCT FROM NEW.successor_model_version_id
    ) THEN
      RAISE EXCEPTION 'PRODUCTION_RELEASE_UNIQUENESS_CONFLICT' USING ERRCODE = '23505';
    END IF;
  ELSIF NEW.action = 'ROLLBACK' AND NEW.previous_model_version_id IS NULL THEN
    RAISE EXCEPTION 'PRODUCTION_ROLLBACK_REQUIRES_PREVIOUS_VERSION' USING ERRCODE = '23514';
  END IF;
  IF successor_active AND NEW.action <> 'ACTIVATE' THEN
    RAISE EXCEPTION 'ACTIVE_PRODUCTION_SUCCESSOR_REQUIRES_ACTIVATE_ACTION' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_review_scope()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, model, evaluation
AS $$
DECLARE
  frozen_match_id uuid;
  result_match_id uuid;
  frozen_role text;
  verified_at timestamptz;
BEGIN
  SELECT fp.match_id, r.match_id, fp.role, r.verified_at
    INTO frozen_match_id, result_match_id, frozen_role, verified_at
    FROM model.frozen_predictions fp
    JOIN evaluation.official_results r ON r.result_id = NEW.result_id
   WHERE fp.frozen_prediction_id = NEW.frozen_prediction_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'REVIEW_SCOPE_PARENT_MISSING' USING ERRCODE = '23503';
  END IF;
  IF frozen_match_id IS DISTINCT FROM result_match_id OR frozen_match_id IS DISTINCT FROM NEW.match_id
     OR NEW.reviewed_at < verified_at OR frozen_role = 'EXPERIMENT' THEN
    RAISE EXCEPTION 'REVIEW_SCOPE_MATCH_ROLE_OR_TIME_INVALID' USING ERRCODE = '23514';
  END IF;
  IF NEW.review_type = 'MODEL_EVALUATION' THEN
    IF NEW.allowed_input_set <> 'FROZEN_PREDICTION_RESULT_ONLY' OR NEW.postmatch_evidence_refs IS NOT NULL THEN
      RAISE EXCEPTION 'MODEL_EVALUATION_INPUT_SET_VIOLATION' USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.review_type = 'MATCH_EXPLANATION' THEN
    IF NEW.allowed_input_set <> 'POSTMATCH_EXPLANATION_EVIDENCE'
       OR NEW.postmatch_evidence_refs IS NULL
       OR jsonb_typeof(NEW.postmatch_evidence_refs) NOT IN ('array', 'object')
       OR NEW.postmatch_evidence_refs = '{}'::jsonb
       OR NEW.postmatch_evidence_refs = '[]'::jsonb THEN
      RAISE EXCEPTION 'MATCH_EXPLANATION_EVIDENCE_SCOPE_INVALID' USING ERRCODE = '23514';
    END IF;
  ELSE
    RAISE EXCEPTION 'REVIEW_TYPE_UNKNOWN' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_incident_scope()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, core
AS $$
DECLARE
  incident_text text := to_jsonb(NEW)::text;
BEGIN
  IF btrim(NEW.affected_entity_type) = '' OR btrim(NEW.affected_entity_id) = '' THEN
    RAISE EXCEPTION 'INCIDENT_ENTITY_IDENTITY_REQUIRED' USING ERRCODE = '23514';
  END IF;
  IF NEW.match_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.matches WHERE match_id = NEW.match_id) THEN
    RAISE EXCEPTION 'INCIDENT_MATCH_SCOPE_MISSING' USING ERRCODE = '23503';
  END IF;
  IF incident_text ~* '(password|secret|service[_-]?role|api[_-]?key|token=)' THEN
    RAISE EXCEPTION 'INCIDENT_SECRET_BOUNDARY_VIOLATION' USING ERRCODE = '22023';
  END IF;
  IF NEW.known_at < NEW.detected_at THEN
    RAISE EXCEPTION 'INCIDENT_KNOWN_AT_PRECEDES_DETECTED_AT' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.validate_public_projection()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance, core, market, model, public
AS $$
DECLARE
  model_role text;
  model_status text;
  model_active boolean;
  prediction_role text;
  frozen_role text;
  frozen_hash text;
  prediction_hash text;
BEGIN
  SELECT mv.role, mv.status, mv.is_canonical_active,
         p.role, fp.role, fp.frozen_input_hash, p.prediction_hash
    INTO model_role, model_status, model_active,
         prediction_role, frozen_role, frozen_hash, prediction_hash
    FROM governance.model_versions mv
    JOIN model.predictions p ON p.prediction_id = NEW.production_prediction_id
    JOIN model.frozen_predictions fp ON fp.frozen_prediction_id = NEW.production_frozen_prediction_id
   WHERE mv.model_version_id = NEW.production_model_version_id
     AND p.match_id = NEW.match_id
     AND fp.match_id = NEW.match_id
     AND fp.model_version_id = mv.model_version_id
     AND p.model_version_id = mv.model_version_id
     AND fp.prediction_id = p.prediction_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'PUBLIC_PROJECTION_PARENT_LINEAGE_MISSING' USING ERRCODE = '23503';
  END IF;
  IF model_role <> 'PRODUCTION' OR model_status <> 'PRODUCTION' OR NOT model_active
     OR prediction_role <> 'PRODUCTION' OR frozen_role <> 'PRODUCTION'
     OR frozen_hash IS NULL OR prediction_hash IS NULL THEN
    RAISE EXCEPTION 'PUBLIC_PROJECTION_PRODUCTION_ONLY_VIOLATION' USING ERRCODE = '23514';
  END IF;
  IF NEW.public_model_name IS NULL OR NEW.public_model_version IS NULL OR NEW.public_model_revision IS NULL THEN
    RAISE EXCEPTION 'PUBLIC_PROJECTION_MODEL_IDENTITY_REQUIRED' USING ERRCODE = '23514';
  END IF;
  IF NEW.publication_status = 'PUBLISHED' THEN
    IF NEW.prediction_business_at > NEW.kickoff_at
       OR NEW.frozen_business_at > NEW.kickoff_at
       OR NEW.odds_business_at > NEW.kickoff_at
       OR NEW.context_business_at > NEW.kickoff_at THEN
      RAISE EXCEPTION 'PUBLIC_PROJECTION_BUSINESS_TIME_AFTER_KICKOFF' USING ERRCODE = '23514';
    END IF;
    IF NEW.safe_odds_summary::text ~* '(raw_payload|password|secret|token|api[_-]?key|shadow|experiment)'
       OR NEW.safe_selection_summary::text ~* '(raw_payload|password|secret|token|api[_-]?key|shadow|experiment)'
       OR NEW.metadata::text ~* '(password|secret|service[_-]?role|api[_-]?key|token=)' THEN
      RAISE EXCEPTION 'PUBLIC_PROJECTION_SAFE_FIELD_BOUNDARY_VIOLATION' USING ERRCODE = '22023';
    END IF;
    IF NEW.public_odds_snapshot_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM market.official_odds_snapshots o
       WHERE o.snapshot_id = NEW.public_odds_snapshot_id
         AND o.match_id = NEW.match_id
         AND o.source_is_official
         AND o.captured_at <= NEW.kickoff_at
    ) THEN
      RAISE EXCEPTION 'PUBLIC_PROJECTION_OFFICIAL_ODDS_LINEAGE_INVALID' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION governance.append_audit_event()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance
AS $$
DECLARE
  new_data jsonb := to_jsonb(NEW);
  old_data jsonb := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
  actor_value text := COALESCE(NULLIF(current_setting('v4.actor', true), ''), current_user);
  actor_role_value text := COALESCE(NULLIF(current_setting('v4.actor_role', true), ''), current_role);
  entity_type_value text := TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
  entity_id_value text;
  match_id_value uuid;
  previous_hash text;
  happened_at_value timestamptz := clock_timestamp();
  audit_metadata jsonb := jsonb_build_object(
    'trigger_name', TG_NAME,
    'candidate_manifest', 'v4-runtime-candidate-manifest@1.0.0',
    'hash_profile', 'disposable-runtime-audit-envelope@1.0'
  );
  audit_envelope jsonb;
  entry_hash_value text;
BEGIN
  entity_id_value := COALESCE(
    new_data->>'model_version_id', new_data->>'engine_version_id',
    new_data->>'match_id', new_data->>'evidence_id',
    new_data->>'team_context_id', new_data->>'evidence_bundle_id',
    new_data->>'frozen_input_id', new_data->>'feature_bundle_id',
    new_data->>'engine_run_id', new_data->>'prediction_id',
    new_data->>'frozen_prediction_id', new_data->>'result_id',
    new_data->>'review_id', new_data->>'tier_a_sample_id',
    new_data->>'promotion_review_id', new_data->>'calibration_record_id',
    new_data->>'release_pointer_event_id', new_data->>'incident_id',
    new_data->>'registry_record_id', new_data->>'migration_id',
    new_data->>'hash_algorithm', new_data->>'acceptance_snapshot_id',
    new_data->>'projection_id', 'unidentified'
  );
  IF (new_data->>'match_id') ~ '^[0-9a-fA-F-]{36}$' THEN
    match_id_value := (new_data->>'match_id')::uuid;
  END IF;
  PERFORM pg_advisory_xact_lock(pg_catalog.hashtext(entity_type_value || ':' || entity_id_value));
  SELECT entry_hash INTO previous_hash
    FROM governance.audit_logs
   WHERE entity_type = entity_type_value AND entity_id = entity_id_value
   ORDER BY happened_at DESC, audit_log_id DESC
   LIMIT 1
   FOR UPDATE;
  audit_envelope := jsonb_build_object(
    'actor', actor_value,
    'actor_role', actor_role_value,
    'action', TG_OP,
    'entity_type', entity_type_value,
    'entity_id', entity_id_value,
    'match_id', match_id_value,
    'before_state', old_data,
    'after_state', new_data,
    'metadata', audit_metadata,
    'happened_at', happened_at_value
  );
  entry_hash_value := 'sha256:' || encode(
    public.digest(convert_to(audit_envelope::text, 'UTF8'), 'sha256'), 'hex'
  );
  INSERT INTO governance.audit_logs (
    actor, actor_role, action, entity_type, entity_id, match_id,
    before_state, after_state, metadata, happened_at, prev_hash, entry_hash,
    hash_algorithm, hash_profile
  ) VALUES (
    actor_value, actor_role_value, TG_OP, entity_type_value, entity_id_value, match_id_value,
    old_data, new_data, audit_metadata, happened_at_value, previous_hash, entry_hash_value,
    'SHA-256', 'disposable-runtime-audit-envelope@1.0'
  );
  RETURN NEW;
END;
$$;

-- Registry metadata is the only controlled UPDATE path. Identity, role,
-- version, predecessor, payload, and hashes remain immutable.
CREATE TRIGGER v4_model_registry_update_guard
BEFORE UPDATE ON governance.model_versions
FOR EACH ROW EXECUTE FUNCTION governance.guard_registry_update();
CREATE TRIGGER v4_engine_registry_update_guard
BEFORE UPDATE ON governance.engine_versions
FOR EACH ROW EXECUTE FUNCTION governance.guard_registry_update();

CREATE TRIGGER v4_official_source_separation_gate
BEFORE INSERT ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_source_separation();
CREATE TRIGGER v4_official_market_payload_gate
BEFORE INSERT ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_market_payload();
CREATE TRIGGER v4_external_source_separation_gate
BEFORE INSERT ON market.external_market_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.validate_source_separation();
CREATE TRIGGER v4_context_evidence_lineage_gate
BEFORE INSERT ON context.team_context_evidence
FOR EACH ROW EXECUTE FUNCTION governance.validate_context_evidence_lineage();
CREATE TRIGGER v4_prediction_engine_membership_gate
BEFORE INSERT ON model.prediction_engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.validate_prediction_engine_membership();
CREATE TRIGGER v4_frozen_prediction_lineage_gate
BEFORE INSERT ON model.frozen_predictions
FOR EACH ROW EXECUTE FUNCTION governance.validate_frozen_prediction_lineage();
CREATE TRIGGER v4_review_scope_gate
BEFORE INSERT ON evaluation.postmatch_reviews
FOR EACH ROW EXECUTE FUNCTION governance.validate_review_scope();
CREATE TRIGGER v4_incident_scope_gate
BEFORE INSERT ON governance.incidents
FOR EACH ROW EXECUTE FUNCTION governance.validate_incident_scope();
CREATE TRIGGER v4_production_release_gate
BEFORE INSERT ON governance.release_pointer_events
FOR EACH ROW EXECUTE FUNCTION governance.validate_production_release();

CREATE TRIGGER v4_frozen_input_mutation_guard
BEFORE UPDATE OR DELETE ON model.frozen_inputs
FOR EACH ROW EXECUTE FUNCTION governance.protect_frozen_input_mutation();
CREATE TRIGGER v4_frozen_prediction_append_only
BEFORE UPDATE OR DELETE ON model.frozen_predictions
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();

-- Strict append-only history. Corrections are new rows with supersedes IDs.
CREATE TRIGGER v4_official_odds_append_only
BEFORE UPDATE OR DELETE ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_external_market_append_only
BEFORE UPDATE OR DELETE ON market.external_market_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_context_append_only
BEFORE UPDATE OR DELETE ON context.team_context_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_context_evidence_append_only
BEFORE UPDATE OR DELETE ON context.team_context_evidence
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_evidence_append_only
BEFORE UPDATE OR DELETE ON context.evidence_items
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_evidence_bundle_append_only
BEFORE UPDATE OR DELETE ON context.evidence_bundles
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_evidence_bundle_item_append_only
BEFORE UPDATE OR DELETE ON context.evidence_bundle_items
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_feature_bundle_append_only
BEFORE UPDATE OR DELETE ON model.feature_bundles
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_engine_run_append_only
BEFORE UPDATE OR DELETE ON model.engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_prediction_append_only
BEFORE UPDATE OR DELETE ON model.predictions
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_prediction_engine_run_append_only
BEFORE UPDATE OR DELETE ON model.prediction_engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_official_result_append_only
BEFORE UPDATE OR DELETE ON evaluation.official_results
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_review_append_only
BEFORE UPDATE OR DELETE ON evaluation.postmatch_reviews
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_tier_a_append_only
BEFORE UPDATE OR DELETE ON evaluation.tier_a_samples
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_tier_a_member_append_only
BEFORE UPDATE OR DELETE ON evaluation.tier_a_run_members
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_promotion_review_append_only
BEFORE UPDATE OR DELETE ON evaluation.promotion_reviews
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_promotion_sample_append_only
BEFORE UPDATE OR DELETE ON evaluation.promotion_review_samples
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_calibration_append_only
BEFORE UPDATE OR DELETE ON evaluation.calibration_records
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_release_event_append_only
BEFORE UPDATE OR DELETE ON governance.release_pointer_events
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_incident_append_only
BEFORE UPDATE OR DELETE ON governance.incidents
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_audit_append_only
BEFORE UPDATE OR DELETE ON governance.audit_logs
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_schema_registry_append_only
BEFORE UPDATE OR DELETE ON governance.v4_schema_registry
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_schema_history_append_only
BEFORE UPDATE OR DELETE ON governance.schema_migrations
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();
CREATE TRIGGER v4_hash_registry_append_only
BEFORE UPDATE OR DELETE ON governance.hash_algorithm_registry
FOR EACH ROW EXECUTE FUNCTION governance.reject_append_only_mutation();

-- Critical lifecycle audit bindings. There is intentionally no audit trigger
-- on governance.audit_logs; the audit append function owns that insert.
CREATE TRIGGER v4_model_registry_audit_event
AFTER INSERT OR UPDATE ON governance.model_versions
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_engine_registry_audit_event
AFTER INSERT OR UPDATE ON governance.engine_versions
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_competition_audit_event
AFTER INSERT ON core.competitions
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_team_audit_event
AFTER INSERT ON core.teams
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_team_alias_audit_event
AFTER INSERT ON core.team_aliases
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_match_audit_event
AFTER INSERT ON core.matches
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_official_odds_audit_event
AFTER INSERT ON market.official_odds_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_external_market_audit_event
AFTER INSERT ON market.external_market_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_context_audit_event
AFTER INSERT ON context.team_context_snapshots
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_context_evidence_link_audit_event
AFTER INSERT ON context.team_context_evidence
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_evidence_audit_event
AFTER INSERT ON context.evidence_items
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_evidence_bundle_audit_event
AFTER INSERT ON context.evidence_bundles
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_evidence_bundle_item_audit_event
AFTER INSERT ON context.evidence_bundle_items
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_audit_event
AFTER INSERT ON model.frozen_inputs
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_official_odds_audit_event
AFTER INSERT ON model.frozen_input_official_odds
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_external_market_audit_event
AFTER INSERT ON model.frozen_input_external_markets
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_context_audit_event
AFTER INSERT ON model.frozen_input_contexts
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_bundle_audit_event
AFTER INSERT ON model.frozen_input_evidence_bundles
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_model_ref_audit_event
AFTER INSERT ON model.frozen_input_model_refs
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_input_engine_ref_audit_event
AFTER INSERT ON model.frozen_input_engine_refs
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_feature_bundle_audit_event
AFTER INSERT ON model.feature_bundles
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_engine_run_audit_event
AFTER INSERT ON model.engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_prediction_audit_event
AFTER INSERT ON model.predictions
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_prediction_engine_run_audit_event
AFTER INSERT ON model.prediction_engine_runs
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_frozen_prediction_audit_event
AFTER INSERT ON model.frozen_predictions
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_result_audit_event
AFTER INSERT ON evaluation.official_results
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_review_audit_event
AFTER INSERT ON evaluation.postmatch_reviews
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_tier_audit_event
AFTER INSERT ON evaluation.tier_a_samples
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_tier_a_member_audit_event
AFTER INSERT ON evaluation.tier_a_run_members
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_promotion_audit_event
AFTER INSERT ON evaluation.promotion_reviews
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_promotion_sample_audit_event
AFTER INSERT ON evaluation.promotion_review_samples
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_calibration_audit_event
AFTER INSERT ON evaluation.calibration_records
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_release_pointer_audit_event
AFTER INSERT ON governance.release_pointer_events
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_incident_audit_event
AFTER INSERT ON governance.incidents
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_schema_registry_audit_event
AFTER INSERT ON governance.v4_schema_registry
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_schema_history_audit_event
AFTER INSERT ON governance.schema_migrations
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();
CREATE TRIGGER v4_hash_registry_audit_event
AFTER INSERT ON governance.hash_algorithm_registry
FOR EACH ROW EXECUTE FUNCTION governance.append_audit_event();

-- Deferred gates run after normalized parent/member rows are present.
CREATE CONSTRAINT TRIGGER v4_evidence_revision_gate
AFTER INSERT ON context.evidence_items DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_context_revision_gate
AFTER INSERT ON context.team_context_snapshots DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_bundle_revision_gate
AFTER INSERT ON context.evidence_bundles DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_frozen_input_lineage_gate
AFTER INSERT ON model.frozen_inputs DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_frozen_input_lineage();
CREATE CONSTRAINT TRIGGER v4_frozen_input_prematch_gate
AFTER INSERT ON model.frozen_inputs DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER v4_feature_bundle_prematch_gate
AFTER INSERT ON model.feature_bundles DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER v4_runtime_lineage_gate
AFTER INSERT ON model.engine_runs DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_runtime_lineage();
CREATE CONSTRAINT TRIGGER v4_engine_prematch_gate
AFTER INSERT ON model.engine_runs DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER v4_prediction_prematch_gate
AFTER INSERT ON model.predictions DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER v4_frozen_prediction_prematch_gate
AFTER INSERT ON model.frozen_predictions DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();
CREATE CONSTRAINT TRIGGER v4_result_revision_gate
AFTER INSERT ON evaluation.official_results DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_review_revision_gate
AFTER INSERT ON evaluation.postmatch_reviews DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_promotion_revision_gate
AFTER INSERT ON evaluation.promotion_reviews DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_calibration_revision_gate
AFTER INSERT ON evaluation.calibration_records DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_incident_revision_gate
AFTER INSERT ON governance.incidents DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_revision_chain();
CREATE CONSTRAINT TRIGGER v4_tier_a_pair_gate
AFTER INSERT ON evaluation.tier_a_samples DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_tier_a_pair();
CREATE CONSTRAINT TRIGGER v4_tier_a_prematch_gate
AFTER INSERT ON evaluation.tier_a_samples DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION governance.validate_prematch_gate();

-- RLS enable order: all internal tables first, then 0008 enables the public
-- projection ledger before any public view grant. No internal policy is
-- created here by default; with client grants revoked, RLS keeps them private.
ALTER TABLE governance.v4_schema_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.hash_algorithm_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.engine_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.competitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.team_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.team_context_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.team_context_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE context.evidence_bundle_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE market.official_odds_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE market.external_market_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_inputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_official_odds ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_external_markets ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_model_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_input_engine_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.feature_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.engine_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.prediction_engine_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model.frozen_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.official_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.postmatch_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.tier_a_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.tier_a_run_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.promotion_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.promotion_review_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation.calibration_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.release_pointer_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance.audit_logs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;

-- Disposable-safe decision: service_role is a no-login local server-side test role.
-- Production ownership, mapping, and least-privilege grant review remain PRODUCTION_REVIEW_REQUIRED.
GRANT USAGE ON SCHEMA core, market, context, model, evaluation, governance TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, market, context, model, evaluation, governance TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA model, evaluation, governance TO service_role;
GRANT EXECUTE ON FUNCTION governance.is_v4_hash(text) TO service_role;

-- No SECURITY DEFINER function is required by this design. If a later
-- migration introduces one, it must use a fixed search_path, explicit actor
-- checks, and a restricted EXECUTE grant before the security gate can pass.

COMMIT;
