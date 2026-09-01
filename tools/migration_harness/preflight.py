"""Machine-runnable PF-01..PF-18 preflight contract.

The validator accepts an optional read-only catalog/evidence object.  It never
discovers or connects to a target.  Missing runtime evidence is explicitly
reported as NOT_EXECUTED_REQUIRES_DISPOSABLE_DB and therefore blocks apply.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from .common import is_non_empty_string, is_v4_hash
from .manifest import ManifestLoadResult, validate_history_integrity
from .models import CheckStatus, Issue, PreflightCheck, PreflightReport
from .schema_diff import load_expected_snapshot
from .security import secret_scan
from .target import validate_target_descriptor


PREFLIGHT_IDS = [f"PF-{index:02d}" for index in range(1, 19)]


def _check(
    check_id: str,
    status: CheckStatus,
    target_dependent: bool,
    reason: str,
    *,
    evidence_ref: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> PreflightCheck:
    return PreflightCheck(
        check_id=check_id,
        status=status,
        target_dependent=target_dependent,
        evidence_ref=evidence_ref or f"preflight/{check_id.lower()}.json",
        reason=reason,
        details=details or {},
    )


def _runtime_missing(check_id: str, reason: str) -> PreflightCheck:
    return _check(
        check_id,
        CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB,
        True,
        reason,
    )


def _bool_evidence(catalog: Dict[str, Any], key: str, check_id: str, reason: str) -> PreflightCheck:
    if key not in catalog:
        return _runtime_missing(check_id, f"Runtime evidence is required: {key}")
    if catalog.get(key) is True:
        return _check(check_id, CheckStatus.PASS, True, reason)
    return _check(check_id, CheckStatus.FAIL, True, f"Runtime evidence failed: {key}")


def _list_evidence(
    catalog: Dict[str, Any],
    key: str,
    check_id: str,
    pass_reason: str,
    *,
    target_dependent: bool = True,
) -> PreflightCheck:
    if key not in catalog:
        return _runtime_missing(check_id, f"Runtime evidence is required: {key}")
    values = catalog.get(key)
    if not isinstance(values, list):
        return _check(check_id, CheckStatus.FAIL, target_dependent, f"Runtime evidence is not a list: {key}")
    if values:
        return _check(check_id, CheckStatus.FAIL, target_dependent, f"Unapproved evidence entries found in {key}", details={"count": len(values)})
    return _check(check_id, CheckStatus.PASS, target_dependent, pass_reason)


def _check_pf_01(target: Optional[Dict[str, Any]]) -> PreflightCheck:
    result = validate_target_descriptor(target)
    if result.ok:
        return _check("PF-01", CheckStatus.PASS, True, "Explicit isolated target identity is valid", details={"target_id": result.target_id, "environment": result.environment})
    return _check("PF-01", CheckStatus.BLOCKED, True, "; ".join(issue.message for issue in result.issues))


def _check_pf_02(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "database_version" not in catalog:
        return _runtime_missing("PF-02", "Database version requires a disposable catalog snapshot")
    version = catalog.get("database_version")
    if not isinstance(version, dict) or not is_non_empty_string(version.get("server_version_num")):
        return _check("PF-02", CheckStatus.FAIL, True, "Database version evidence is incomplete")
    if version.get("compatibility_approved") is not True:
        return _check("PF-02", CheckStatus.BLOCKED, True, "PostgreSQL compatibility has not been explicitly approved")
    return _check("PF-02", CheckStatus.PASS, True, "Database version and compatibility evidence are present")


def _check_pf_03(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "extensions" not in catalog:
        return _runtime_missing("PF-03", "Extension availability requires a disposable catalog snapshot")
    extensions = catalog.get("extensions")
    if not isinstance(extensions, list):
        return _check("PF-03", CheckStatus.FAIL, True, "Extension evidence is not a list")
    pgcrypto = [item for item in extensions if isinstance(item, dict) and item.get("name") == "pgcrypto"]
    if not pgcrypto or pgcrypto[0].get("approved") is not True or not is_non_empty_string(pgcrypto[0].get("version")):
        return _check("PF-03", CheckStatus.BLOCKED, True, "Approved pgcrypto/UUID provider evidence is missing")
    return _check("PF-03", CheckStatus.PASS, True, "Approved extension evidence is present")


def _check_pf_04(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None:
        return _runtime_missing("PF-04", "Security-invoker capability requires a disposable target")
    if catalog.get("security_invoker_supported") is True or catalog.get("approved_security_invoker_fallback") is True:
        return _check("PF-04", CheckStatus.PASS, True, "Security-invoker support or approved fallback is evidenced")
    if "security_invoker_supported" not in catalog and "approved_security_invoker_fallback" not in catalog:
        return _runtime_missing("PF-04", "Security-invoker capability evidence is absent")
    return _check("PF-04", CheckStatus.BLOCKED, True, "Neither security-invoker support nor an approved fallback is proven")


def _check_pf_06(target: Optional[Dict[str, Any]], catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if target is not None and target.get("contains_v333_objects") is True:
        return _check("PF-06", CheckStatus.FAIL, True, "Target descriptor reports a V3.3.3 object collision")
    if catalog is None or "v333_objects" not in catalog:
        return _runtime_missing("PF-06", "V3.3.3 isolation requires a read-only disposable catalog comparison")
    return _list_evidence(catalog, "v333_objects", "PF-06", "No V3.3.3 objects are present in the supplied catalog")


def _check_pf_07(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "namespace_state" not in catalog:
        return _runtime_missing("PF-07", "V4 namespace state requires a disposable catalog snapshot")
    if catalog.get("namespace_state") not in {"EMPTY", "APPROVED_COEXISTENCE"}:
        return _check("PF-07", CheckStatus.FAIL, True, "V4 namespace state is not empty or approved coexistence")
    if catalog.get("namespace_conflicts", []) != []:
        return _check("PF-07", CheckStatus.FAIL, True, "V4 namespace conflicts are present")
    return _check("PF-07", CheckStatus.PASS, True, "V4 namespace state is explicitly isolated")


def _check_pf_08(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "role_report" not in catalog:
        return _runtime_missing("PF-08", "Role and permission evidence requires a disposable target")
    report = catalog.get("role_report")
    if not isinstance(report, dict) or report.get("permission_boundary_approved") is not True:
        return _check("PF-08", CheckStatus.FAIL, True, "Role/permission boundary is not approved")
    required_roles = {"backend", "executor", "auditor"}
    present = set(report.get("required_roles_present", [])) if isinstance(report.get("required_roles_present"), list) else set()
    if not required_roles.issubset(present):
        return _check("PF-08", CheckStatus.FAIL, True, "Attributable backend, executor, and auditor roles are incomplete")
    return _check("PF-08", CheckStatus.PASS, True, "Required actors and permissions are attributable")


def _check_pf_09(manifest: ManifestLoadResult, catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "migration_history" not in catalog:
        return _runtime_missing("PF-09", "Migration history requires a disposable catalog snapshot")
    history = catalog.get("migration_history")
    if not isinstance(history, dict):
        return _check("PF-09", CheckStatus.FAIL, True, "Migration history evidence is malformed")
    if history.get("partial_applied") is True:
        return _check("PF-09", CheckStatus.BLOCKED, True, "Partial-applied migration state is detected")
    if history.get("matches_manifest") is not True:
        return _check("PF-09", CheckStatus.BLOCKED, True, "Migration history does not match the immutable manifest")
    rows = history.get("rows", [])
    if rows:
        ok, issues = validate_history_integrity(rows, manifest)
        if not ok:
            return _check("PF-09", CheckStatus.FAIL, True, "; ".join(issue.message for issue in issues))
    return _check("PF-09", CheckStatus.PASS, True, "Migration history is empty or matches the supplied manifest")


def _check_pf_10(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "backup_decision" not in catalog:
        return _runtime_missing("PF-10", "Backup/snapshot decision requires target evidence")
    value = catalog.get("backup_decision")
    if isinstance(value, dict) and (is_non_empty_string(value.get("backup_id")) or value.get("disposable_no_backup_approved") is True):
        return _check("PF-10", CheckStatus.PASS, True, "Backup or disposable-target no-backup decision is recorded")
    return _check("PF-10", CheckStatus.BLOCKED, True, "Backup/snapshot decision is incomplete")


def _check_pf_11(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "maintenance_window" not in catalog:
        return _runtime_missing("PF-11", "Maintenance window evidence requires target evidence")
    value = catalog.get("maintenance_window")
    if isinstance(value, dict) and (value.get("approved") is True or value.get("disposable_target") is True):
        return _check("PF-11", CheckStatus.PASS, True, "Maintenance/lock/rollback ownership decision is recorded")
    return _check("PF-11", CheckStatus.BLOCKED, True, "Maintenance window or disposable lock decision is incomplete")


def _check_pf_12(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "migration_clean" not in catalog:
        return _runtime_missing("PF-12", "Current migration cleanliness requires target history evidence")
    if catalog.get("migration_clean") is True and catalog.get("dirty_state") is not True and catalog.get("partial_applied") is not True:
        return _check("PF-12", CheckStatus.PASS, True, "No failed, partial, dirty, or manual migration state is evidenced")
    return _check("PF-12", CheckStatus.BLOCKED, True, "Dirty or partial migration state is present")


def _check_pf_13(manifest: ManifestLoadResult) -> PreflightCheck:
    if not manifest.ok:
        return _check("PF-13", CheckStatus.BLOCKED, False, "Manifest metadata/dependency validation failed")
    if manifest.pending_hash_count:
        return _check(
            "PF-13",
            CheckStatus.BLOCKED,
            False,
            "Canonical migration hashes are pending; apply readiness is not proven",
            details={"pending_hash_count": manifest.pending_hash_count},
        )
    if any(not is_v4_hash(entry.migration_hash) for entry in manifest.entries):
        return _check("PF-13", CheckStatus.BLOCKED, False, "Every migration must have a canonical SHA-256 before approval")
    return _check("PF-13", CheckStatus.PASS, False, "Manifest files, dependencies, hashes, and statuses are ready")


def _check_pf_14(
    target: Optional[Dict[str, Any]],
    catalog: Optional[Dict[str, Any]],
    secret_scan_result: Dict[str, Any],
    secret_env_names: Optional[Set[str]],
) -> PreflightCheck:
    if secret_scan_result.get("status") != CheckStatus.PASS.value:
        return _check("PF-14", CheckStatus.FAIL, False, "Repository secret scan failed; credential values are withheld")
    if target is None:
        return _runtime_missing("PF-14", "Runtime secret presence is not verifiable without an explicit disposable target")
    credential_name = target.get("credential_env_name")
    if secret_env_names is None:
        return _runtime_missing("PF-14", "Only environment-variable names may be checked; runtime presence was not supplied")
    if credential_name not in secret_env_names:
        return _check("PF-14", CheckStatus.BLOCKED, True, "Required credential environment-variable reference is unavailable")
    if catalog is not None and catalog.get("secret_values_exposed") is True:
        return _check("PF-14", CheckStatus.FAIL, True, "Target evidence reports exposed credential material")
    return _check("PF-14", CheckStatus.PASS, True, "Repository is clean and the credential reference is env-only")


def _check_pf_15(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    return _bool_evidence(catalog or {}, "data_api_exposure_approved", "PF-15", "Data API exposure and safe public surface are explicitly approved")


def _check_pf_16(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    return _bool_evidence(catalog or {}, "default_privileges_closed", "PF-16", "PUBLIC/anon/authenticated default privileges are closed and reviewed")


def _check_pf_17(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "function_security_report" not in catalog:
        return _runtime_missing("PF-17", "Function security/search_path evidence requires a disposable catalog snapshot")
    report = catalog.get("function_security_report")
    if not isinstance(report, dict):
        return _check("PF-17", CheckStatus.FAIL, True, "Function security evidence is malformed")
    if report.get("unsafe_functions"):
        return _check("PF-17", CheckStatus.FAIL, True, "Unsafe SECURITY DEFINER function evidence is present")
    if report.get("all_fixed_search_paths") is not True or report.get("execute_grants_reviewed") is not True:
        return _check("PF-17", CheckStatus.BLOCKED, True, "Function search_path or execute-grant review is incomplete")
    return _check("PF-17", CheckStatus.PASS, True, "Function owner, search_path, actor checks, and execute grants are reviewed")


def _check_pf_18(catalog: Optional[Dict[str, Any]]) -> PreflightCheck:
    if catalog is None or "production_release_state" not in catalog:
        return _runtime_missing("PF-18", "Production release state requires a read-only target evidence snapshot")
    value = catalog.get("production_release_state")
    if not isinstance(value, dict):
        return _check("PF-18", CheckStatus.FAIL, True, "Production release state evidence is malformed")
    if value.get("active_pointer_ambiguity") is True or value.get("automatic_promotion") is True:
        return _check("PF-18", CheckStatus.BLOCKED, True, "Production pointer or auto-promotion boundary is unsafe")
    if value.get("reviewed") is not True:
        return _check("PF-18", CheckStatus.BLOCKED, True, "Production release state is not explicitly reviewed")
    return _check("PF-18", CheckStatus.PASS, True, "No unintended Production pointer replacement or auto-promotion is evidenced")


def run_preflight(
    repo_root: Path,
    manifest: ManifestLoadResult,
    target: Optional[Dict[str, Any]] = None,
    catalog: Optional[Dict[str, Any]] = None,
    *,
    secret_env_names: Optional[Set[str]] = None,
) -> PreflightReport:
    scan = secret_scan(repo_root)
    checks = [
        _check_pf_01(target),
        _check_pf_02(catalog),
        _check_pf_03(catalog),
        _check_pf_04(catalog),
        _list_evidence(catalog or {}, "conflicting_objects", "PF-05", "No unapproved schema/table conflicts are evidenced"),
        _check_pf_06(target, catalog),
        _check_pf_07(catalog),
        _check_pf_08(catalog),
        _check_pf_09(manifest, catalog),
        _check_pf_10(catalog),
        _check_pf_11(catalog),
        _check_pf_12(catalog),
        _check_pf_13(manifest),
        _check_pf_14(target, catalog, scan, secret_env_names),
        _check_pf_15(catalog),
        _check_pf_16(catalog),
        _check_pf_17(catalog),
        _check_pf_18(catalog),
    ]
    if len(checks) != len(PREFLIGHT_IDS) or [check.check_id for check in checks] != PREFLIGHT_IDS:
        raise RuntimeError("PF-01..PF-18 implementation ordering is invalid")
    overall = CheckStatus.PASS if all(check.status in {CheckStatus.PASS, CheckStatus.NOT_APPLICABLE} for check in checks) else CheckStatus.BLOCKED
    return PreflightReport(
        status=overall,
        checks=checks,
        target=target,
        not_run_reason=(
            "No disposable PostgreSQL target/catalog was supplied; target-dependent checks are not a pass"
            if catalog is None
            else "Runtime evidence was supplied as read-only input; no connector was invoked"
        ),
        secret_scan=scan,
    )
