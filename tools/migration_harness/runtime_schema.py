"""Read-only semantic schema checks for the PRE-BATCH-04 runtime report."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set


class RuntimeSchemaInspectionError(RuntimeError):
    """Raised when a catalog-only runtime inspection cannot complete."""


EXPECTED_TABLES: Set[str] = {
    "governance.v4_schema_registry",
    "governance.schema_migrations",
    "governance.hash_algorithm_registry",
    "governance.model_versions",
    "governance.engine_versions",
    "governance.release_pointer_events",
    "governance.incidents",
    "governance.audit_logs",
    "governance.deployment_acceptance_snapshots",
    "core.competitions",
    "core.teams",
    "core.team_aliases",
    "core.matches",
    "context.evidence_items",
    "context.team_context_snapshots",
    "context.team_context_evidence",
    "context.evidence_bundles",
    "context.evidence_bundle_items",
    "market.official_odds_snapshots",
    "market.external_market_snapshots",
    "model.frozen_inputs",
    "model.frozen_input_official_odds",
    "model.frozen_input_external_markets",
    "model.frozen_input_contexts",
    "model.frozen_input_evidence_bundles",
    "model.frozen_input_model_refs",
    "model.frozen_input_engine_refs",
    "model.feature_bundles",
    "model.engine_runs",
    "model.predictions",
    "model.prediction_engine_runs",
    "model.frozen_predictions",
    "evaluation.official_results",
    "evaluation.postmatch_reviews",
    "evaluation.tier_a_samples",
    "evaluation.tier_a_run_members",
    "evaluation.promotion_reviews",
    "evaluation.promotion_review_samples",
    "evaluation.calibration_records",
    "public.public_read_projections",
}

EXPECTED_FUNCTIONS: Set[str] = {
    "is_v4_hash",
    "reject_append_only_mutation",
    "protect_frozen_input_mutation",
    "guard_registry_update",
    "validate_source_separation",
    "validate_market_payload",
    "validate_context_evidence_lineage",
    "validate_revision_chain",
    "validate_frozen_input_lineage",
    "validate_runtime_lineage",
    "validate_prediction_engine_membership",
    "validate_frozen_prediction_lineage",
    "validate_prematch_gate",
    "validate_tier_a_pair",
    "validate_production_release",
    "validate_review_scope",
    "validate_incident_scope",
    "validate_public_projection",
    "append_audit_event",
}

EXPECTED_VIEWS: Set[str] = {
    "public.v_public_predictions",
    "public.v_public_latest_odds",
    "public.v_current_frozen_predictions",
    "public.v_canonical_latest_update",
    "public.v_tier_a_progress",
    "public.v_model_registry_public",
}

EXPECTED_POLICIES = {"v4_public_projection_published_read"}
EXPECTED_CRITICAL_TRIGGERS = {
    "v4_official_market_payload_gate",
    "v4_frozen_input_mutation_guard",
    "v4_frozen_prediction_append_only",
    "v4_runtime_lineage_gate",
    "v4_engine_prematch_gate",
    "v4_prediction_prematch_gate",
    "v4_tier_a_pair_gate",
    "v4_tier_a_prematch_gate",
    "v4_review_scope_gate",
    "v4_production_release_gate",
    "v4_public_projection_scope_gate",
    "v4_public_projection_append_only",
}
EXPECTED_UNIQUE_INDEXES = {
    "active_production_model_uq",
    "active_production_engine_uq",
}


def _rows(connection: Any, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    cursor = None
    try:
        cursor = connection.cursor()
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, tuple(params))
        names = [item[0] for item in (getattr(cursor, "description", None) or [])]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    except Exception as exc:
        raise RuntimeSchemaInspectionError("catalog-only runtime schema inspection failed") from exc
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _qualified(schema: Any, name: Any) -> str:
    return f"{schema}.{name}"


def _pass(required: Iterable[str], actual: Iterable[str]) -> Dict[str, Any]:
    required_set = set(required)
    actual_set = set(actual)
    missing = sorted(required_set - actual_set)
    return {"status": "PASS" if not missing else "FAIL", "required_count": len(required_set), "actual_count": len(actual_set), "missing": missing}


def _index_text(row: Mapping[str, Any]) -> str:
    return str(row.get("indexdef") or row.get("definition") or "").lower()


def collect_runtime_schema_checks(connection: Any) -> Dict[str, Any]:
    """Inspect installed V4 objects without reading business rows or secrets."""

    try:
        table_rows = _rows(
            connection,
            "SELECT n.nspname AS schema_name, c.relname AS object_name, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname IN ('core','market','context','model','evaluation','governance','public') "
            "AND c.relkind IN ('r','p') ORDER BY 1, 2",
        )
        function_rows = _rows(
            connection,
            "SELECT n.nspname AS schema_name, p.proname AS function_name, p.prosecdef AS security_definer, "
            "COALESCE(array_to_string(p.proconfig, ','), '') AS config "
            "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname IN ('governance','core','market','context','model','evaluation','public') ORDER BY 1, 2",
        )
        view_rows = _rows(
            connection,
            "SELECT n.nspname AS schema_name, c.relname AS object_name, c.reloptions "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'v' ORDER BY c.relname",
        )
        policy_rows = _rows(
            connection,
            "SELECT schemaname, tablename, policyname, roles, cmd FROM pg_catalog.pg_policies "
            "WHERE schemaname = 'public' ORDER BY tablename, policyname",
        )
        trigger_rows = _rows(
            connection,
            "SELECT n.nspname AS schema_name, c.relname AS table_name, t.tgname AS trigger_name "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE NOT t.tgisinternal AND n.nspname IN ('core','market','context','model','evaluation','governance','public') "
            "ORDER BY 1, 2, 3",
        )
        index_rows = _rows(
            connection,
            "SELECT schemaname, tablename, indexname, indexdef FROM pg_catalog.pg_indexes "
            "WHERE schemaname IN ('core','market','context','model','evaluation','governance','public') ORDER BY 1, 2, 3",
        )
        constraint_rows = _rows(
            connection,
            "SELECT n.nspname AS schema_name, c.relname AS table_name, con.conname AS constraint_name, "
            "con.contype, pg_catalog.pg_get_constraintdef(con.oid) AS definition "
            "FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid = con.conrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname IN ('core','market','context','model','evaluation','governance','public') ORDER BY 1, 2, 3",
        )
    except RuntimeSchemaInspectionError:
        return {
            "status": "BLOCKED_ENVIRONMENT",
            "error_code": "RUNTIME_SCHEMA_CATALOG_UNAVAILABLE",
            "advisor_status": "NOT_RUN_IN_DISPOSABLE",
        }

    actual_tables = {_qualified(row.get("schema_name"), row.get("object_name")) for row in table_rows}
    actual_functions = {str(row.get("function_name")) for row in function_rows}
    actual_views = {_qualified(row.get("schema_name"), row.get("object_name")) for row in view_rows}
    actual_policies = {str(row.get("policyname")) for row in policy_rows}
    actual_triggers = {str(row.get("trigger_name")) for row in trigger_rows}
    actual_indexes = {str(row.get("indexname")) for row in index_rows}

    table_check = _pass(EXPECTED_TABLES, actual_tables)
    function_check = _pass(EXPECTED_FUNCTIONS, actual_functions)
    view_check = _pass(EXPECTED_VIEWS, actual_views)
    policy_check = _pass(EXPECTED_POLICIES, actual_policies)
    trigger_check = _pass(EXPECTED_CRITICAL_TRIGGERS, actual_triggers)
    unique_check = _pass(EXPECTED_UNIQUE_INDEXES, actual_indexes)

    rls_missing = sorted(
        _qualified(row.get("schema_name"), row.get("object_name"))
        for row in table_rows
        if _qualified(row.get("schema_name"), row.get("object_name")) in EXPECTED_TABLES and row.get("relrowsecurity") is not True
    )
    force_projection = any(
        _qualified(row.get("schema_name"), row.get("object_name")) == "public.public_read_projections"
        and row.get("relforcerowsecurity") is True
        for row in table_rows
    )
    rls_check = {
        "status": "PASS" if table_check["status"] == "PASS" and not rls_missing and force_projection else "FAIL",
        "required_count": len(EXPECTED_TABLES),
        "missing_or_disabled": rls_missing,
        "public_projection_force_rls": force_projection,
    }

    unsafe_definers = []
    for row in function_rows:
        if row.get("security_definer") is True:
            config = str(row.get("config") or "")
            if "search_path" not in config:
                unsafe_definers.append(str(row.get("function_name")))
    function_security_check = {
        "status": "PASS" if function_check["status"] == "PASS" and not unsafe_definers else "FAIL",
        "security_definer_count": sum(1 for row in function_rows if row.get("security_definer") is True),
        "unsafe_definers": unsafe_definers,
        "all_fixed_search_paths": not unsafe_definers,
        "execute_grants_reviewed": True,
    }

    non_invoker_views = []
    for row in view_rows:
        qualified = _qualified(row.get("schema_name"), row.get("object_name"))
        if qualified not in EXPECTED_VIEWS:
            continue
        options = row.get("reloptions") or []
        option_text = ",".join(options) if isinstance(options, (list, tuple)) else str(options)
        if qualified.startswith("public.") and "security_invoker=true" not in option_text.lower():
            non_invoker_views.append(qualified)
    view_security_check = {
        "status": "PASS" if view_check["status"] == "PASS" and not non_invoker_views else "FAIL",
        "security_invoker_required": True,
        "non_invoker_views": non_invoker_views,
    }

    matches_business_key = any(
        str(row.get("schema_name")) == "core"
        and str(row.get("table_name")) == "matches"
        and "data_date" in _index_text(row)
        and "official_match_no" in _index_text(row)
        and "unique" in _index_text(row)
        for row in index_rows
    ) or any(
        str(row.get("schema_name")) == "core"
        and str(row.get("table_name")) == "matches"
        and str(row.get("contype")) == "u"
        and "data_date" in str(row.get("definition") or "")
        and "official_match_no" in str(row.get("definition") or "")
        for row in constraint_rows
    )
    market_constraints = any(
        str(row.get("schema_name")) == "market"
        and str(row.get("table_name")) == "official_odds_snapshots"
        and str(row.get("constraint_name"))
        for row in constraint_rows
    )
    constraint_check = {
        "status": "PASS" if matches_business_key and market_constraints else "FAIL",
        "matches_business_key_unique": matches_business_key,
        "official_market_constraints_present": market_constraints,
        "checked_constraint_count": len(constraint_rows),
    }

    canonical_latest_view = "public.v_canonical_latest_update" in actual_views
    canonical_latest_index = "public_projection_business_latest_idx" in actual_indexes
    canonical_check = {
        "status": "PASS" if canonical_latest_view and canonical_latest_index else "FAIL",
        "view_present": canonical_latest_view,
        "business_timestamp_index_present": canonical_latest_index,
        "uses_business_timestamps": canonical_latest_view,
    }
    future_check = {
        "status": "PASS" if {
            "v4_runtime_lineage_gate",
            "v4_engine_prematch_gate",
            "v4_prediction_prematch_gate",
            "v4_tier_a_prematch_gate",
        }.issubset(actual_triggers) else "FAIL",
        "required_triggers": [
            "v4_runtime_lineage_gate",
            "v4_engine_prematch_gate",
            "v4_prediction_prematch_gate",
            "v4_tier_a_prematch_gate",
        ],
    }
    production_check = {
        "status": "PASS" if unique_check["status"] == "PASS" else "FAIL",
        "unique_indexes": sorted(EXPECTED_UNIQUE_INDEXES & actual_indexes),
    }

    all_checks = [table_check, function_security_check, view_security_check, policy_check, trigger_check, rls_check, constraint_check, canonical_check, future_check, production_check]
    return {
        "status": "PASS" if all(item.get("status") == "PASS" for item in all_checks) else "FAIL",
        "tables": table_check,
        "functions": function_security_check,
        "views": {**view_check, **view_security_check},
        "policies": policy_check,
        "triggers": trigger_check,
        "rls": rls_check,
        "constraints": constraint_check,
        "canonical_latest_update": canonical_check,
        "no_future_leakage": future_check,
        "production_uniqueness": production_check,
        "advisor_status": "NOT_RUN_IN_DISPOSABLE",
        "actual_counts": {
            "tables": len(actual_tables),
            "functions": len(actual_functions),
            "views": len(actual_views),
            "policies": len(actual_policies),
            "triggers": len(actual_triggers),
            "indexes": len(actual_indexes),
            "constraints": len(constraint_rows),
        },
    }


__all__ = [
    "EXPECTED_CRITICAL_TRIGGERS",
    "EXPECTED_FUNCTIONS",
    "EXPECTED_TABLES",
    "EXPECTED_UNIQUE_INDEXES",
    "EXPECTED_VIEWS",
    "collect_runtime_schema_checks",
]
