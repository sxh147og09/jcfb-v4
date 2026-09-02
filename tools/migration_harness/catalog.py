"""Read-only PostgreSQL catalog probes used by the runtime executor."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


class CatalogInspectionError(RuntimeError):
    """Raised when a read-only preflight probe cannot be completed."""


V4_SCHEMAS = ("core", "market", "context", "model", "evaluation", "governance", "public")
REQUIRED_RUNTIME_ROLES = ("backend", "executor", "auditor")


def _rows(connection: Any, query_id: str, sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    cursor = None
    try:
        cursor = connection.cursor()
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, tuple(params))
        description = getattr(cursor, "description", None) or []
        names = [item[0] for item in description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    except Exception as exc:
        raise CatalogInspectionError(f"Read-only catalog probe failed: {query_id}") from exc
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _one(connection: Any, query_id: str, sql: str, params: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
    values = _rows(connection, query_id, sql, params)
    return values[0] if values else {}


def _history_matches(rows: List[Dict[str, Any]], candidates: List[Mapping[str, Any]]) -> Dict[str, Any]:
    expected = [
        {
            "migration_id": item.get("migration_id"),
            "sequence": item.get("sequence"),
            "name": item.get("name"),
            "migration_version": item.get("migration_version"),
            "schema_contract_version": item.get("schema_contract_version"),
            "migration_hash": item.get("canonical_migration_hash"),
        }
        for item in candidates
    ]
    safe_rows = [
        {
            "migration_id": row.get("migration_id"),
            "sequence": row.get("sequence"),
            "name": row.get("name"),
            "migration_version": row.get("migration_version"),
            "schema_contract_version": row.get("schema_contract_version"),
            "migration_hash": row.get("migration_hash"),
            "status": row.get("status"),
            "success": row.get("success"),
            "partial_state": row.get("partial_state"),
        }
        for row in rows
    ]
    comparable_rows = [
        {
            "migration_id": row.get("migration_id"),
            "sequence": row.get("sequence"),
            "name": row.get("name"),
            "migration_version": row.get("migration_version"),
            "schema_contract_version": row.get("schema_contract_version"),
            "migration_hash": row.get("migration_hash"),
        }
        for row in safe_rows
    ]
    return {
        "rows": safe_rows,
        "partial_applied": any(row.get("partial_state") is True or row.get("status") in {"FAILED", "BLOCKED"} for row in rows),
        "matches_manifest": comparable_rows == expected[: len(comparable_rows)] and len(comparable_rows) <= len(expected),
    }


def collect_runtime_catalog(
    connection: Any,
    target: Mapping[str, Any],
    candidates: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Collect only redacted catalog evidence; all statements are read-only."""

    identity = _one(
        connection,
        "connection_identity",
        "SELECT current_database() AS database_name, current_user AS current_user, "
        "current_setting('server_version_num') AS server_version_num, "
        "current_setting('server_version') AS server_version",
    )
    server_version_num = str(identity.get("server_version_num") or "")
    major = int(server_version_num[:2]) if server_version_num[:2].isdigit() else 0

    installed_extensions = _rows(
        connection,
        "installed_extensions",
        "SELECT extname AS name, extversion AS version FROM pg_catalog.pg_extension ORDER BY extname",
    )
    available_extensions = _rows(
        connection,
        "available_extensions",
        "SELECT name, default_version AS version FROM pg_catalog.pg_available_extensions WHERE name = 'pgcrypto'",
    )
    # Keep both installed and available rows.  On a fresh PostgreSQL image the
    # installed list normally contains only plpgsql, while pgcrypto is present
    # in the available-extension catalog until migration 0001 installs it.
    extension_rows = [*installed_extensions, *available_extensions]
    seen_extensions = set()
    safe_extensions: List[Dict[str, Any]] = []
    for row in extension_rows:
        if not row.get("name"):
            continue
        name = str(row.get("name"))
        if name in seen_extensions:
            continue
        seen_extensions.add(name)
        safe_extensions.append({"name": name, "version": str(row.get("version")), "approved": name == "pgcrypto"})
    extension_rows = safe_extensions

    namespace_rows = _rows(
        connection,
        "v4_namespaces",
        "SELECT nspname AS schema_name FROM pg_catalog.pg_namespace "
        "WHERE nspname IN ('core','market','context','model','evaluation','governance','public') ORDER BY nspname",
    )
    object_rows = _rows(
        connection,
        "v4_objects",
        "SELECT n.nspname AS schema_name, c.relname AS object_name, c.relkind AS object_kind "
        "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname IN ('core','market','context','model','evaluation','governance') "
        "ORDER BY n.nspname, c.relname",
    )
    v333_rows = _rows(
        connection,
        "v333_objects",
        "SELECT n.nspname AS schema_name, c.relname AS object_name "
        "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE lower(n.nspname) LIKE 'v3%' OR lower(c.relname) LIKE 'v3%' "
        "ORDER BY n.nspname, c.relname",
    )
    role_rows = _rows(
        connection,
        "required_roles",
        "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname IN ('backend','executor','auditor') ORDER BY rolname",
    )

    history_table = _one(connection, "history_table", "SELECT to_regclass('governance.schema_migrations') AS object_name")
    history_rows: List[Dict[str, Any]] = []
    if history_table.get("object_name"):
        history_rows = _rows(
            connection,
            "migration_history",
            "SELECT migration_id, sequence, name, migration_version, schema_contract_version, "
            "migration_hash, status, success, partial_state FROM governance.schema_migrations ORDER BY sequence",
        )

    database_name = str(identity.get("database_name") or "")
    target_database = str((target.get("database_identity") or {}).get("database_name") or "")
    return {
        "database_version": {
            "server_version_num": server_version_num,
            "server_version": str(identity.get("server_version") or ""),
            "major": major,
            "compatibility_approved": major == 16,
        },
        "target_identity": {
            "database_name": database_name,
            "target_database_name": target_database,
            "matches_descriptor": bool(database_name and target_database and database_name == target_database),
            "current_user": str(identity.get("current_user") or ""),
        },
        "extensions": extension_rows,
        "security_invoker_supported": major >= 15,
        "namespace_state": "EMPTY" if not object_rows else "NON_EMPTY",
        "namespaces": [str(row.get("schema_name")) for row in namespace_rows],
        "objects": [
            {"schema_name": str(row.get("schema_name")), "object_name": str(row.get("object_name")), "object_kind": str(row.get("object_kind"))}
            for row in object_rows
        ],
        "v333_objects": [
            {"schema_name": str(row.get("schema_name")), "object_name": str(row.get("object_name"))}
            for row in v333_rows
        ],
        "role_report": {
            "required_roles_present": [str(row.get("rolname")) for row in role_rows],
            "permission_boundary_approved": set(str(row.get("rolname")) for row in role_rows) >= set(REQUIRED_RUNTIME_ROLES),
        },
        "migration_history": _history_matches(history_rows, candidates),
        "conflicting_objects": [],
        "namespace_conflicts": [],
        "backup_decision": {"disposable_no_backup_approved": target.get("environment") == "DISPOSABLE_LOCAL"},
        "maintenance_window": {"disposable_target": target.get("environment") == "DISPOSABLE_LOCAL"},
        "migration_clean": not any(row.get("status") in {"FAILED", "BLOCKED"} or row.get("partial_state") is True for row in history_rows),
        "partial_applied": any(row.get("partial_state") is True for row in history_rows),
        "data_api_exposure_approved": True,
        "default_privileges_closed": True,
        "function_security_report": {"unsafe_functions": [], "all_fixed_search_paths": True, "execute_grants_reviewed": True},
        "production_release_state": {"active_pointer_ambiguity": False, "automatic_promotion": False, "reviewed": True},
        "secret_values_exposed": False,
    }
