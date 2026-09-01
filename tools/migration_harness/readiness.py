"""BATCH-03 target-readiness contracts with a fail-closed boundary.

This module validates a non-secret target manifest and classifies readiness. It
does not discover, install, start, connect to, or mutate a database. A target
can become ready for a disposable/staging dry run only when an operator has
supplied explicit read-only runtime evidence; a missing runtime proof remains
``RUNTIME_PENDING_DISPOSABLE_DB``.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .common import CREDENTIAL_ENV_RE, TARGET_ID_RE, is_non_empty_string, read_json, sha256_json
from .models import CheckStatus, Issue


READINESS_CONTRACT_PATH = "config/migration_harness/v4_batch_03_readiness_contract.json"
STAGING_TARGET_TEMPLATE_PATH = "config/migration_harness/v4_batch_03_staging_target.template.json"
READINESS_CONTRACT_VERSION = "v4-batch-03-readiness-contract@1.0.0"
TARGET_MANIFEST_VERSION = "v4-staging-target-manifest@1.0.0"
RUNTIME_PENDING_STATUS = "RUNTIME_PENDING_DISPOSABLE_DB"
RUNTIME_EVIDENCE_SUPPLIED = "SUPPLIED_READ_ONLY"

READINESS_STATES = (
    "NOT_READY",
    "READY_FOR_DISPOSABLE_DRY_RUN",
    "READY_FOR_STAGING_DRY_RUN",
    "READY_FOR_PRODUCTION_REVIEW",
    "BLOCKED",
)

V4_NAMESPACES = ("core", "market", "context", "model", "evaluation", "governance", "public")
ALLOWED_ENVIRONMENTS = {"DISPOSABLE_LOCAL", "STAGING", "PRODUCTION"}
ALLOWED_PROVIDERS = {
    "LOCAL_POSTGRES",
    "DOCKER_POSTGRES",
    "STAGING_POSTGRES",
    "STAGING_SUPABASE",
    "PRODUCTION_SUPABASE",
}
PROVIDER_BY_ENVIRONMENT = {
    "DISPOSABLE_LOCAL": {"LOCAL_POSTGRES", "DOCKER_POSTGRES"},
    "STAGING": {"STAGING_POSTGRES", "STAGING_SUPABASE"},
    "PRODUCTION": {"PRODUCTION_SUPABASE"},
}

REQUIRED_TARGET_FIELDS = (
    "manifest_version",
    "target_id",
    "environment",
    "provider",
    "target_state",
    "non_production",
    "disposable",
    "non_secret_database_identity",
    "ownership",
    "database",
    "network_security",
    "permissions",
    "namespace_isolation",
    "migration_history",
    "backup_snapshot",
    "partial_state",
    "reset_and_teardown",
    "secret_source",
    "retention",
    "runtime_evidence",
    "connect_permission",
)

SENSITIVE_KEYS = {
    "url",
    "database_url",
    "password",
    "token",
    "api_key",
    "service_role_key",
    "cookie",
    "private_key",
    "secret_value",
}


def _issue(code: str, message: str, location: Optional[str] = None) -> Issue:
    return Issue(code, message, location)


def load_readiness_contract(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / READINESS_CONTRACT_PATH)


def load_staging_target_template(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / STAGING_TARGET_TEMPLATE_PATH)


def _walk_sensitive_keys(value: Any, path: str = "") -> Iterable[Issue]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            location = f"{path}.{key_text}" if path else key_text
            if key_lower in SENSITIVE_KEYS:
                yield _issue("RAW_SECRET_FIELD_PRESENT", "Raw credential material is not allowed in a target manifest", location)
            yield from _walk_sensitive_keys(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_sensitive_keys(child, f"{path}[{index}]")


def normalize_target_manifest(descriptor: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Accept the BATCH-02 descriptor shape without weakening BATCH-03 rules."""

    if descriptor is None or not isinstance(descriptor, dict):
        return descriptor
    if descriptor.get("manifest_version") == TARGET_MANIFEST_VERSION:
        return deepcopy(descriptor)
    if descriptor.get("descriptor_version") != "v4-migration-target-descriptor@1.0.0":
        return deepcopy(descriptor)

    environment = descriptor.get("environment")
    identity = descriptor.get("database_identity")
    identity = identity if isinstance(identity, dict) else {}
    return {
        "manifest_version": TARGET_MANIFEST_VERSION,
        "target_id": descriptor.get("target_id"),
        "environment": environment,
        "provider": descriptor.get("provider"),
        "target_state": "RUNTIME_PENDING",
        "non_production": environment in {"DISPOSABLE_LOCAL", "STAGING"},
        "disposable": descriptor.get("disposable"),
        "non_secret_database_identity": {
            "server_name": identity.get("server_name"),
            "database_name": identity.get("database_name"),
            "project_or_cluster_ref": identity.get("project_or_cluster_ref"),
        },
        "ownership": {
            "human_approver": "PENDING_HUMAN_APPROVER",
            "migration_executor": "PENDING_MIGRATION_EXECUTOR",
            "auditor": "PENDING_AUDITOR",
            "ownership_confirmed": False,
        },
        "database": {
            "postgres_major_version": "PENDING_RUNTIME_EVIDENCE",
            "compatibility_status": "PENDING_RUNTIME_EVIDENCE",
            "extensions": [{"name": "pgcrypto", "approved": False, "version": "PENDING_RUNTIME_EVIDENCE", "owner": "PENDING"}],
        },
        "network_security": {
            "allow_network": descriptor.get("allow_network"),
            "ssl_mode": "RUNTIME_PENDING",
            "ssl_verified": False,
            "certificate_source": "PENDING_RUNTIME_EVIDENCE",
        },
        "permissions": {
            "required_roles": ["backend", "executor", "auditor"],
            "permission_boundary_status": "PENDING_RUNTIME_EVIDENCE",
            "default_privileges_closed": False,
        },
        "namespace_isolation": {
            "v4_namespaces": list(V4_NAMESPACES),
            "namespace_conflicts": [],
            "v333_objects_present": descriptor.get("contains_v333_objects"),
            "production_data_present": descriptor.get("contains_production_data"),
            "production_pointer_state": "PENDING_RUNTIME_EVIDENCE",
        },
        "migration_history": {
            "history_state": "RUNTIME_PENDING",
            "partial_state_detected": False,
            "dirty_state_detected": False,
            "matches_manifest": False,
            "rows": [],
        },
        "backup_snapshot": {
            "decision": "RUNTIME_PENDING",
            "backup_id": None,
            "no_backup_approved": False,
        },
        "partial_state": {"detected": False, "unresolved_objects": []},
        "reset_and_teardown": descriptor.get("reset_and_teardown_contract"),
        "secret_source": {
            "mode": "PROCESS_ENVIRONMENT_ONLY",
            "credential_env_name": descriptor.get("credential_env_name"),
            "values_persisted": False,
            "values_logged": False,
            "values_reported": False,
        },
        "retention": {
            "evidence_retention_days": "PENDING_RUNTIME_EVIDENCE",
            "target_destroy_after_evidence": bool(
                isinstance(descriptor.get("reset_and_teardown_contract"), dict)
                and descriptor["reset_and_teardown_contract"].get("destroy_after_evidence") is True
            ),
            "logs_exclude_secrets": True,
        },
        "runtime_evidence": {
            "status": RUNTIME_PENDING_STATUS,
            "read_only_catalog_verified": False,
            "target_identity_verified": False,
            "connector_invoked": False,
        },
        "connect_permission": descriptor.get("connect_permission"),
    }


def _require_dict(value: Any, field: str, issues: List[Issue]) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        issues.append(_issue("READINESS_FIELD_INVALID", "Readiness field must be an object", field))
        return None
    return value


def _require_bool(mapping: Dict[str, Any], field: str, issues: List[Issue], location: str) -> None:
    if not isinstance(mapping.get(field), bool):
        issues.append(_issue("READINESS_BOOLEAN_INVALID", "Readiness field must be boolean", f"{location}.{field}"))


def validate_readiness_contract_document(contract: Dict[str, Any]) -> List[Issue]:
    """Validate the checked-in environment/state contract itself."""

    issues: List[Issue] = []
    if not isinstance(contract, dict):
        return [_issue("READINESS_CONTRACT_INVALID", "Readiness contract must be an object")]
    if contract.get("contract_version") != READINESS_CONTRACT_VERSION:
        issues.append(_issue("READINESS_CONTRACT_VERSION_INVALID", "Readiness contract version is not approved"))
    if contract.get("batch_id") != "BATCH-03" or contract.get("task_id") != "V4-016":
        issues.append(_issue("READINESS_CONTRACT_SCOPE_INVALID", "Readiness contract must bind BATCH-03 and V4-016"))
    if contract.get("status") != "DESIGN_ONLY":
        issues.append(_issue("READINESS_CONTRACT_STATUS_INVALID", "Readiness contract must remain design-only"))

    environments = contract.get("environments")
    if not isinstance(environments, list) or {item.get("environment") for item in environments if isinstance(item, dict)} != ALLOWED_ENVIRONMENTS:
        issues.append(_issue("READINESS_ENVIRONMENT_SET_INVALID", "Contract must define DISPOSABLE_LOCAL, STAGING, and PRODUCTION"))
    states = contract.get("deployment_readiness_states")
    if not isinstance(states, dict) or set(states) != set(READINESS_STATES):
        issues.append(_issue("READINESS_STATE_SET_INVALID", "Contract must define the complete BATCH-03 readiness state set"))
    if contract.get("prohibited_states") != ["READY_FOR_PRODUCTION_APPLY"]:
        issues.append(_issue("PRODUCTION_APPLY_STATE_UNSAFE", "Production apply readiness is prohibited in BATCH-03"))
    runtime_policy = contract.get("runtime_policy", {})
    if not isinstance(runtime_policy, dict) or runtime_policy.get("missing_runtime_evidence") != RUNTIME_PENDING_STATUS:
        issues.append(_issue("RUNTIME_PENDING_POLICY_INVALID", "Missing disposable evidence must remain runtime-pending"))
    secrets = contract.get("secret_policy", {})
    if not isinstance(secrets, dict) or secrets.get("source") != "PROCESS_ENVIRONMENT_ONLY" or secrets.get("persist_values") is not False or secrets.get("log_values") is not False or secrets.get("report_values") is not False:
        issues.append(_issue("READINESS_SECRET_POLICY_INVALID", "Readiness contract must keep secrets env-only and out of evidence"))
    boundary = contract.get("execution_boundary", {})
    if not isinstance(boundary, dict) or boundary.get("connector_invoked") is not False or boundary.get("database_connected") is not False or boundary.get("sql_executed") is not False or boundary.get("production_db_writes_performed") != "NO" or boundary.get("supabase_writes_performed") != "NO":
        issues.append(_issue("READINESS_EXECUTION_BOUNDARY_INVALID", "BATCH-03 contract must declare the no-write/no-connect boundary"))
    return issues


def validate_target_manifest(descriptor: Optional[Dict[str, Any]]) -> List[Issue]:
    """Validate target identity/isolation policy without contacting a target."""

    manifest = normalize_target_manifest(descriptor)
    if manifest is None:
        return [_issue("TARGET_MANIFEST_REQUIRED", "An explicit non-production target manifest is required")]
    if not isinstance(manifest, dict):
        return [_issue("TARGET_MANIFEST_INVALID", "Target manifest must be an object")]

    issues: List[Issue] = list(_walk_sensitive_keys(manifest))
    for field in REQUIRED_TARGET_FIELDS:
        if field not in manifest:
            issues.append(_issue("TARGET_MANIFEST_FIELD_MISSING", "Required target manifest field is missing", field))

    if manifest.get("manifest_version") != TARGET_MANIFEST_VERSION:
        issues.append(_issue("TARGET_MANIFEST_VERSION_INVALID", "Target manifest version is not approved"))
    target_id = manifest.get("target_id")
    if not isinstance(target_id, str) or not TARGET_ID_RE.fullmatch(target_id):
        issues.append(_issue("TARGET_ID_INVALID", "Target identity must be a lowercase opaque identifier"))
    environment = manifest.get("environment")
    provider = manifest.get("provider")
    if environment not in ALLOWED_ENVIRONMENTS:
        issues.append(_issue("TARGET_ENVIRONMENT_INVALID", "Target environment is not recognized"))
    if provider not in ALLOWED_PROVIDERS:
        issues.append(_issue("TARGET_PROVIDER_INVALID", "Target provider is not recognized"))
    if environment in PROVIDER_BY_ENVIRONMENT and provider not in PROVIDER_BY_ENVIRONMENT[environment]:
        issues.append(_issue("TARGET_PROVIDER_ENVIRONMENT_MISMATCH", "Provider does not match target environment"))

    identity = _require_dict(manifest.get("non_secret_database_identity"), "non_secret_database_identity", issues)
    if identity is not None:
        for field in ("server_name", "database_name", "project_or_cluster_ref"):
            if not is_non_empty_string(identity.get(field)):
                issues.append(_issue("DATABASE_IDENTITY_FIELD_INVALID", "Non-secret database identity field is missing", f"non_secret_database_identity.{field}"))

    _require_bool(manifest, "non_production", issues, "target")
    _require_bool(manifest, "disposable", issues, "target")
    if environment in {"DISPOSABLE_LOCAL", "STAGING"} and manifest.get("non_production") is not True:
        issues.append(_issue("NON_PRODUCTION_ASSERTION_REQUIRED", "Non-production environments must assert non_production=true"))
    if environment == "DISPOSABLE_LOCAL" and manifest.get("disposable") is not True:
        issues.append(_issue("DISPOSABLE_ASSERTION_REQUIRED", "DISPOSABLE_LOCAL must assert disposable=true"))

    ownership = _require_dict(manifest.get("ownership"), "ownership", issues)
    if ownership is not None:
        roles = [ownership.get(field) for field in ("human_approver", "migration_executor", "auditor")]
        if any(not is_non_empty_string(role) for role in roles):
            issues.append(_issue("OWNERSHIP_ROLE_MISSING", "Human Approver, Migration Executor, and Auditor roles must be named or pending"))
        if len(set(roles)) != len(roles):
            issues.append(_issue("SEPARATION_OF_DUTIES_INVALID", "Approver, executor, and auditor roles must remain distinct"))
        _require_bool(ownership, "ownership_confirmed", issues, "ownership")

    database = _require_dict(manifest.get("database"), "database", issues)
    if database is not None:
        if not is_non_empty_string(database.get("postgres_major_version")):
            issues.append(_issue("DATABASE_VERSION_MISSING", "PostgreSQL major version must be explicit or runtime-pending"))
        if database.get("compatibility_status") not in {"PASS", "FAIL", RUNTIME_PENDING_STATUS, "PENDING_RUNTIME_EVIDENCE"}:
            issues.append(_issue("DATABASE_COMPATIBILITY_STATUS_INVALID", "PostgreSQL compatibility status is not governed"))
        extensions = database.get("extensions")
        if not isinstance(extensions, list) or not any(isinstance(item, dict) and item.get("name") == "pgcrypto" for item in extensions):
            issues.append(_issue("REQUIRED_EXTENSION_DECLARATION_MISSING", "The required pgcrypto/UUID provider must be declared"))

    network = _require_dict(manifest.get("network_security"), "network_security", issues)
    if network is not None:
        _require_bool(network, "allow_network", issues, "network_security")
        _require_bool(network, "ssl_verified", issues, "network_security")
        if environment == "STAGING" and network.get("allow_network") is True and network.get("ssl_mode") != "REQUIRE_VERIFY_FULL":
            issues.append(_issue("STAGING_SSL_POLICY_INVALID", "Networked staging requires full certificate verification"))
        if environment == "PRODUCTION" and network.get("allow_network") is not False:
            issues.append(_issue("PRODUCTION_NETWORK_INVALID", "Production network access is always blocked"))

    permissions = _require_dict(manifest.get("permissions"), "permissions", issues)
    if permissions is not None:
        roles = permissions.get("required_roles")
        if not isinstance(roles, list) or not {"backend", "executor", "auditor"}.issubset(set(roles)):
            issues.append(_issue("REQUIRED_ROLES_MISSING", "Backend, executor, and auditor roles must be declared"))
        if not isinstance(permissions.get("default_privileges_closed"), bool):
            issues.append(_issue("DEFAULT_PRIVILEGE_STATE_INVALID", "Default privilege closure must be boolean"))

    isolation = _require_dict(manifest.get("namespace_isolation"), "namespace_isolation", issues)
    if isolation is not None:
        if set(isolation.get("v4_namespaces", [])) != set(V4_NAMESPACES):
            issues.append(_issue("V4_NAMESPACE_SET_INVALID", "All seven V4 namespaces must be listed"))
        if not isinstance(isolation.get("namespace_conflicts"), list):
            issues.append(_issue("NAMESPACE_CONFLICTS_INVALID", "Namespace conflicts must be a list"))
        if isolation.get("v333_objects_present") is not False:
            issues.append(_issue("V333_OBJECT_COLLISION", "Target must contain no V3.3.3 objects"))
        if isolation.get("production_data_present") is not False:
            issues.append(_issue("PRODUCTION_DATA_COLLISION", "Target must contain no retained Production data"))

    history = _require_dict(manifest.get("migration_history"), "migration_history", issues)
    if history is not None:
        if history.get("history_state") not in {"EMPTY", "EXACT_MANIFEST_MATCH", "RUNTIME_PENDING"}:
            issues.append(_issue("MIGRATION_HISTORY_STATE_INVALID", "Migration history state is not governed"))
        _require_bool(history, "partial_state_detected", issues, "migration_history")
        _require_bool(history, "dirty_state_detected", issues, "migration_history")
        if not isinstance(history.get("rows"), list):
            issues.append(_issue("MIGRATION_HISTORY_ROWS_INVALID", "Migration history evidence must be a list"))

    backup = _require_dict(manifest.get("backup_snapshot"), "backup_snapshot", issues)
    if backup is not None and backup.get("decision") not in {"BACKUP_REQUIRED", "DISPOSABLE_NO_BACKUP", "RUNTIME_PENDING"}:
        issues.append(_issue("BACKUP_DECISION_INVALID", "Backup/snapshot decision is not governed"))

    partial = _require_dict(manifest.get("partial_state"), "partial_state", issues)
    if partial is not None:
        _require_bool(partial, "detected", issues, "partial_state")
        if not isinstance(partial.get("unresolved_objects"), list):
            issues.append(_issue("PARTIAL_STATE_EVIDENCE_INVALID", "Unresolved partial-state objects must be a list"))

    reset = _require_dict(manifest.get("reset_and_teardown"), "reset_and_teardown", issues)
    if reset is not None:
        for field in ("reset_before_run", "destroy_after_evidence", "operator_owned"):
            _require_bool(reset, field, issues, "reset_and_teardown")
        if environment == "DISPOSABLE_LOCAL" and any(reset.get(field) is not True for field in ("reset_before_run", "destroy_after_evidence", "operator_owned")):
            issues.append(_issue("RESET_TEARDOWN_CONTRACT_INVALID", "Disposable targets require operator-owned reset and teardown"))

    secret_source = _require_dict(manifest.get("secret_source"), "secret_source", issues)
    if secret_source is not None:
        if secret_source.get("mode") != "PROCESS_ENVIRONMENT_ONLY":
            issues.append(_issue("SECRET_SOURCE_INVALID", "Credentials must come from process environment only"))
        if not isinstance(secret_source.get("credential_env_name"), str) or not CREDENTIAL_ENV_RE.fullmatch(secret_source.get("credential_env_name", "")):
            issues.append(_issue("CREDENTIAL_ENV_REFERENCE_INVALID", "Only an uppercase environment-variable name may identify credentials"))
        for field in ("values_persisted", "values_logged", "values_reported"):
            if secret_source.get(field) is not False:
                issues.append(_issue("SECRET_PERSISTENCE_INVALID", "Secret values must be excluded from evidence", f"secret_source.{field}"))

    retention = _require_dict(manifest.get("retention"), "retention", issues)
    if retention is not None:
        if not (isinstance(retention.get("evidence_retention_days"), int) or is_non_empty_string(retention.get("evidence_retention_days"))):
            issues.append(_issue("RETENTION_POLICY_INVALID", "Evidence retention must be explicit or runtime-pending"))
        if retention.get("logs_exclude_secrets") is not True:
            issues.append(_issue("RETENTION_SECRET_POLICY_INVALID", "Retained logs must exclude secret values"))

    runtime = _require_dict(manifest.get("runtime_evidence"), "runtime_evidence", issues)
    if runtime is not None:
        if runtime.get("status") not in {RUNTIME_PENDING_STATUS, RUNTIME_EVIDENCE_SUPPLIED}:
            issues.append(_issue("RUNTIME_EVIDENCE_STATUS_INVALID", "Runtime evidence status is not governed"))
        for field in ("read_only_catalog_verified", "target_identity_verified", "connector_invoked"):
            _require_bool(runtime, field, issues, "runtime_evidence")
        if runtime.get("status") == RUNTIME_PENDING_STATUS and runtime.get("connector_invoked") is not False:
            issues.append(_issue("RUNTIME_PENDING_CONNECTOR_INVALID", "Runtime-pending evidence cannot claim a connector invocation"))

    permission = manifest.get("connect_permission")
    if permission not in {"EXPLICITLY_GRANTED", "NOT_GRANTED", "BLOCKED"}:
        issues.append(_issue("CONNECT_PERMISSION_INVALID", "Connection permission is not recognized"))
    if environment == "PRODUCTION":
        if manifest.get("target_state") != "BLOCKED":
            issues.append(_issue("PRODUCTION_TARGET_STATE_INVALID", "Production target state must be BLOCKED"))
        if permission != "BLOCKED":
            issues.append(_issue("PRODUCTION_CONNECT_BLOCKED", "Production connection is always blocked"))
        issues.append(_issue("PRODUCTION_TARGET_HARD_BLOCK", "Production targets are hard-blocked in BATCH-03"))

    isolation_for_gate = manifest.get("namespace_isolation")
    if isinstance(isolation_for_gate, dict) and isolation_for_gate.get("namespace_conflicts") not in (None, []):
        issues.append(_issue("NAMESPACE_CONFLICT_PRESENT", "Unapproved namespace conflicts block readiness"))
    history_for_gate = manifest.get("migration_history")
    partial_for_gate = manifest.get("partial_state")
    if (isinstance(history_for_gate, dict) and history_for_gate.get("partial_state_detected") is True) or (isinstance(partial_for_gate, dict) and partial_for_gate.get("detected") is True):
        issues.append(_issue("PARTIAL_STATE_DETECTED", "Partial migration state blocks readiness"))
    return issues


def _safe_identity(manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = normalize_target_manifest(manifest)
    if not isinstance(normalized, dict):
        return {"target_id": None, "environment": None, "provider": None, "database_identity": {}}
    identity = normalized.get("non_secret_database_identity")
    identity = identity if isinstance(identity, dict) else {}
    return {
        "target_id": normalized.get("target_id"),
        "environment": normalized.get("environment"),
        "provider": normalized.get("provider"),
        "database_identity": {
            field: identity.get(field)
            for field in ("server_name", "database_name", "project_or_cluster_ref")
        },
    }


def target_identity_snapshot(manifest: Optional[Dict[str, Any]], *, runtime_status: str = RUNTIME_PENDING_STATUS) -> Dict[str, Any]:
    identity = _safe_identity(manifest)
    payload = {
        "status": runtime_status,
        "target_id": identity["target_id"],
        "environment": identity["environment"],
        "provider": identity["provider"],
        "database_identity": identity["database_identity"],
        "secret_values_present": False,
        "identity_verified": runtime_status == RUNTIME_EVIDENCE_SUPPLIED,
    }
    payload["target_identity_hash"] = sha256_json(
        {key: payload[key] for key in ("target_id", "environment", "provider", "database_identity")}
    )
    return payload


def _runtime_proof_complete(runtime: Dict[str, Any], environment: str) -> bool:
    required = (
        "read_only_catalog_verified",
        "target_identity_verified",
        "version_compatible",
        "extensions_available",
        "namespace_isolation_pass",
        "history_integrity_pass",
        "partial_state_absent",
        "permission_boundary_pass",
        "backup_decision_recorded",
        "secret_presence_verified",
        "production_release_reviewed",
    )
    if environment == "STAGING":
        required = required + ("ssl_verified",)
    return all(runtime.get(field) is True for field in required) and runtime.get("connector_invoked") is False


def assess_readiness(
    descriptor: Optional[Dict[str, Any]],
    *,
    runtime_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a readiness state; never returns a Production apply state."""

    manifest = normalize_target_manifest(descriptor)
    issues = validate_target_manifest(manifest)
    environment = manifest.get("environment") if isinstance(manifest, dict) else None
    if environment == "PRODUCTION":
        status = "BLOCKED"
        reason = "PRODUCTION_TARGET_HARD_BLOCK"
    elif issues:
        status = "BLOCKED"
        reason = "TARGET_MANIFEST_INVALID"
    else:
        runtime = runtime_evidence if runtime_evidence is not None else manifest.get("runtime_evidence", {})
        runtime = runtime if isinstance(runtime, dict) else {}
        if runtime.get("status") != RUNTIME_EVIDENCE_SUPPLIED:
            status = "NOT_READY"
            reason = RUNTIME_PENDING_STATUS
        elif manifest.get("connect_permission") != "EXPLICITLY_GRANTED":
            status = "NOT_READY"
            reason = "EXPLICIT_CONNECT_PERMISSION_REQUIRED"
        elif not _runtime_proof_complete(runtime, environment):
            status = "BLOCKED"
            reason = "RUNTIME_READINESS_EVIDENCE_INCOMPLETE"
        else:
            status = "READY_FOR_DISPOSABLE_DRY_RUN" if environment == "DISPOSABLE_LOCAL" else "READY_FOR_STAGING_DRY_RUN"
            reason = "Explicit isolated target and read-only runtime evidence are complete"

    return {
        "status": status,
        "target": _safe_identity(manifest),
        "target_identity_hash": target_identity_snapshot(manifest)["target_identity_hash"],
        "connect_allowed": status in {"READY_FOR_DISPOSABLE_DRY_RUN", "READY_FOR_STAGING_DRY_RUN"},
        "runtime_status": (manifest.get("runtime_evidence", {}).get("status") if isinstance(manifest, dict) and isinstance(manifest.get("runtime_evidence"), dict) else None),
        "reason": reason,
        "issues": [issue.to_dict() for issue in issues],
        "production_apply_allowed": False,
        "database_connected": False,
        "connector_invoked": False,
    }


def readiness_contract_summary(repo_root: Path) -> Dict[str, Any]:
    contract = load_readiness_contract(repo_root)
    issues = validate_readiness_contract_document(contract)
    return {
        "status": CheckStatus.PASS.value if not issues else CheckStatus.FAIL.value,
        "contract_version": contract.get("contract_version"),
        "environment_count": len(contract.get("environments", [])) if isinstance(contract.get("environments"), list) else 0,
        "readiness_states": list(contract.get("deployment_readiness_states", {}).keys()) if isinstance(contract.get("deployment_readiness_states"), dict) else [],
        "issues": [issue.to_dict() for issue in issues],
    }
