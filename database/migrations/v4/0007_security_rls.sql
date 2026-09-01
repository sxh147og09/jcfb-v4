-- DESIGN ONLY - DO NOT APPLY
-- migration_id: migration@20260901.007
-- sequence: 0007
-- name: v4-security-rls
-- migration_version: migration@20260901.007
-- depends_on: [migration@20260901.006]
-- schema_contract_version: v4-database-schema@1.0.0
-- authored_at: 2026-09-01T00:00:00+08:00
-- migration_hash: PENDING_CANONICAL_HASH
-- status: DRAFT
-- Candidate security/trigger DDL only; no role grants or policies are applied.

BEGIN;

-- All complex validators are fail-closed design stubs until their reviewed
-- implementation and test evidence are approved. None may silently repair a
-- mismatch or manufacture a missing hash/time/source.
CREATE FUNCTION governance.reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'V4 append-only violation on %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.protect_frozen_input_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  IF OLD.immutable OR OLD.status IN ('FROZEN', 'SUPERSEDED') THEN
    RAISE EXCEPTION 'FROZEN_INPUT_MUTATION is not allowed' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'FROZEN_INPUT_DELETE is not allowed' USING ERRCODE = '55000';
  END IF;
  RAISE EXCEPTION 'TODO_DECISION: Draft mutation requires approved Freeze Gate field allow-list' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.guard_registry_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: registry update requires approved actor, field allow-list, and audit event' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_source_separation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate official/external source separation before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_market_payload()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate five-market availability, payload, price, and line state before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_context_evidence_lineage()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate context/evidence match, hash, and cutoff lineage before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_revision_chain()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-family monotonic revision chain before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_frozen_input_lineage()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core, market, context, model AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate exact Frozen Input IDs, hashes, cutoff, and source times before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_runtime_lineage()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core, model AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-match role/version/hash runtime lineage before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_prediction_engine_membership()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, model AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate prediction/engine match, role, output hash, and purpose before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_frozen_prediction_lineage()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, model AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate Prediction/Frozen Input/Frozen Prediction lineage before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_prematch_gate()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core, market, context, model AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: fail closed on source availability, cutoff, kickoff, leakage, and forbidden postmatch refs' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_tier_a_pair()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core, model, evaluation AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate same-match same-frozen-input Production/Shadow pair before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_production_release()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, evaluation AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate manual promotion evidence and unique active Production release before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_review_scope()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, model, evaluation AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate review result/frozen-prediction match and input-set separation before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_incident_scope()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate incident entity family, scope, revision, and secret boundary before apply' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION governance.validate_public_projection()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, governance, core, market, model, public AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: validate Production-only safe projection and real business timestamps before apply' USING ERRCODE = '55000';
END;
$$;

-- Audit append is a controlled AFTER trigger contract. The approved
-- implementation must obtain a per-stream lock, require the caller-supplied
-- canonical entry_hash/prev_hash, and exclude audit_logs itself to avoid
-- recursion. This fail-closed stub prevents accidental partial adoption.
CREATE FUNCTION governance.append_audit_event()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, governance
AS $$
BEGIN
  RAISE EXCEPTION 'TODO_DECISION: audit append requires actor context, chain lock, and canonical entry_hash' USING ERRCODE = '55000';
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

-- TODO_DECISION: confirm service_role exists and remains server-side. The
-- following is a candidate least-privilege backend grant shape; it is not a
-- browser grant and must be replaced by a custom backend role if approved.
GRANT USAGE ON SCHEMA core, market, context, model, evaluation, governance TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, market, context, model, evaluation, governance TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA model, evaluation, governance TO service_role;
GRANT EXECUTE ON FUNCTION governance.is_v4_hash(text) TO service_role;

-- No SECURITY DEFINER function is required by this design. If a later
-- migration introduces one, it must use a fixed search_path, explicit actor
-- checks, and a restricted EXECUTE grant before the security gate can pass.

COMMIT;
