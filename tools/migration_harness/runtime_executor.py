"""Fail-closed PostgreSQL runtime executor for the V4 candidate package."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .catalog import collect_runtime_catalog
from .canonical_hash import CanonicalHashError, load_candidate_manifest, verify_candidate_hashes
from .common import sha256_json
from .connection import ConnectionAdapter, ConnectionConfigError, ConnectionSettings, PostgresConnectionAdapter, driver_status
from .models import ExecutionMode
from .runtime_tests import PostgresRuntimeCaseAdapter, run_runtime_cases, validate_runtime_case_wiring
from .runtime_schema import collect_runtime_schema_checks
from .target import validate_target_descriptor


RUNTIME_EXECUTOR_CONTRACT_VERSION = "v4-runtime-executor@1.0.0"
ALLOWED_TARGET_ENVIRONMENTS = {"DISPOSABLE_LOCAL", "STAGING"}
PRODUCTION_ENVIRONMENT = "PRODUCTION"
DEFAULT_ACTOR = "jcfb-v4-runtime-executor"
DEFAULT_REPORT_RELATIVE = ".runtime/reports/prebatch04"
RUNTIME_REPORT_FILENAME = "prebatch04_runtime_validation.json"
RUNTIME_REPORT_MARKDOWN_FILENAME = "prebatch04_runtime_validation.md"
RUNTIME_REPORT_POINTER_FILENAME = "latest.json"
RUNTIME_REPORT_POINTER_VERSION = "v4-runtime-report-latest@1.0.0"
_SQL_BEGIN_RE = re.compile(r"(?im)^\s*BEGIN;\s*$")
_SQL_COMMIT_RE = re.compile(r"(?im)^\s*COMMIT;\s*$")

CONNECTOR_NOT_INVOKED = "CONNECTOR_NOT_INVOKED"
CONNECTOR_INVOKED = "CONNECTOR_INVOKED"
CONNECTION_REFUSED = "CONNECTION_REFUSED"
AUTH_FAILED = "AUTH_FAILED"
DRIVER_MISSING = "DRIVER_MISSING"
TARGET_IDENTITY_MISMATCH = "TARGET_IDENTITY_MISMATCH"
SQL_APPLY_FAILED = "SQL_APPLY_FAILED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_report_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _compact_report_time(value: str) -> str:
    parsed = _parse_report_time(value)
    if parsed is None:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return parsed.strftime("%Y%m%dT%H%M%SZ")


def _git_head(repo_root: Path) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if re.fullmatch(r"[0-9a-fA-F]{7,64}", value) else None


def _safe_report_count(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _runtime_summary_lines(report: Mapping[str, Any]) -> List[str]:
    runtime = report.get("runtime_validation") if isinstance(report.get("runtime_validation"), Mapping) else {}
    wiring = report.get("runtime_case_wiring") if isinstance(report.get("runtime_case_wiring"), Mapping) else {}
    hashes = report.get("hash_verification") if isinstance(report.get("hash_verification"), Mapping) else {}
    readiness = report.get("staging_readiness") if isinstance(report.get("staging_readiness"), Mapping) else {}
    smoke_count = _safe_report_count(runtime.get("smoke_count", wiring.get("smoke_count", 20)), 20)
    enforcement_count = _safe_report_count(runtime.get("enforcement_count", wiring.get("enforcement_count", 15)), 15)
    smoke_passed = _safe_report_count(
        report.get("smoke_passed", runtime.get("passed_smoke", 0)), 0
    )
    enforcement_passed = _safe_report_count(
        report.get("enforcement_passed", runtime.get("passed_enforcement", 0)), 0
    )
    return [
        f"PRE_BATCH_04_RUNTIME_MODE={report.get('mode', 'UNKNOWN')}",
        f"PRE_BATCH_04_RUNTIME_STATUS={report.get('status', 'UNKNOWN')}",
        f"PRE_BATCH_04_HASHES={_safe_report_count(hashes.get('matched_count'), 0)}/{_safe_report_count(hashes.get('candidate_count'), 0)}",
        f"PRE_BATCH_04_SMOKE_EXECUTABLE_HANDLERS={_safe_report_count(wiring.get('smoke_executable_handler_count'), 0)}/{smoke_count}",
        f"PRE_BATCH_04_ENFORCEMENT_EXECUTABLE_HANDLERS={_safe_report_count(wiring.get('enforcement_executable_handler_count'), 0)}/{enforcement_count}",
        f"PRE_BATCH_04_SMOKE_PASSED={smoke_passed}/{smoke_count}",
        f"PRE_BATCH_04_ENFORCEMENT_PASSED={enforcement_passed}/{enforcement_count}",
        f"PRE_BATCH_04_STAGING_READINESS={readiness.get('status', 'UNKNOWN')}",
    ]


def _materialize_runtime_report(
    report: Mapping[str, Any],
    repo_root: Path,
    *,
    run_id: Optional[str] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    git_head: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach immutable identity to one report write.

    The writer intentionally does not reuse identity fields already present in
    ``report``.  Reusing a dict from a previous invocation would make a second
    runtime run appear to be the first one, which was the failure mode this
    persistence contract is designed to prevent.
    """

    started = started_at or _now_iso()
    finished = finished_at or _now_iso()
    actual_run_id = run_id or f"prebatch04-{_compact_report_time(started)}-{uuid.uuid4().hex}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}", actual_run_id):
        raise ValueError("Runtime report run_id is not a safe path component")
    value = dict(report)
    value.update(
        {
            "run_id": actual_run_id,
            "started_at": started,
            "finished_at": finished,
            "git_head": git_head if git_head is not None else _git_head(repo_root),
        }
    )
    runtime = value.get("runtime_validation") if isinstance(value.get("runtime_validation"), Mapping) else {}
    value["smoke_passed"] = _safe_report_count(runtime.get("passed_smoke"), 0)
    value["enforcement_passed"] = _safe_report_count(runtime.get("passed_enforcement"), 0)
    value["runtime_summary_lines"] = _runtime_summary_lines(value)
    return value


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _report_path_is_inside(root: Path, path: Path) -> bool:
    return root == path or root in path.parents


def default_disposable_target(database_name: str = "jcfb_v4_runtime") -> Dict[str, Any]:
    """Build a non-secret local target descriptor for the PowerShell wrapper."""

    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_-]{0,62}", database_name):
        raise ValueError("Database name is not a safe local target identity")
    return {
        "descriptor_version": "v4-migration-target-descriptor@1.0.0",
        "target_id": "jcfb-v4-disposable-runtime",
        "environment": "DISPOSABLE_LOCAL",
        "provider": "LOCAL_POSTGRES",
        "database_identity": {
            "server_name": "local-disposable",
            "database_name": database_name,
            "project_or_cluster_ref": "jcfb-v4-disposable-runtime",
        },
        "disposable": True,
        "contains_v333_objects": False,
        "contains_production_data": False,
        "credential_env_name": "JCFB_V4_RUNTIME_DB_PASSWORD",
        "allow_network": False,
        "connect_permission": "EXPLICITLY_GRANTED",
        "reset_and_teardown_contract": {
            "reset_before_run": True,
            "destroy_after_evidence": True,
            "operator_owned": True,
        },
    }


def _safe_target(target: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(target, Mapping):
        return {"target_id": None, "environment": None, "provider": None, "database_identity": None}
    identity = target.get("database_identity") if isinstance(target.get("database_identity"), Mapping) else {}
    return {
        "target_id": target.get("target_id"),
        "environment": target.get("environment"),
        "provider": target.get("provider"),
        "database_identity": {
            "server_name": identity.get("server_name"),
            "database_name": identity.get("database_name"),
            "project_or_cluster_ref": identity.get("project_or_cluster_ref"),
        },
    }


def _safe_error(
    exc: BaseException,
    *,
    error_code: str,
    phase: str,
    connector_status: str,
) -> Dict[str, str]:
    """Return error metadata without serialising driver text or credentials."""

    return {
        "error_code": error_code,
        "error_type": type(exc).__name__,
        "phase": phase,
        "connector_status": connector_status,
    }


def _set_failure_taxonomy(plan: Dict[str, Any], error_code: str, phase: str) -> None:
    invoked = bool(plan.get("execution_boundary", {}).get("connector_invoked"))
    plan["failure_taxonomy"] = {
        "error_code": error_code,
        "phase": phase,
        "connector_status": CONNECTOR_INVOKED if invoked else CONNECTOR_NOT_INVOKED,
    }


def _exception_text(exc: BaseException) -> str:
    """Build private classification text; it is never written to a report."""

    parts: List[str] = []
    current: Optional[BaseException] = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(type(current).__name__.lower())
        try:
            parts.append(str(current).lower())
        except Exception:
            pass
        current = current.__cause__ or current.__context__
    return " ".join(parts)


def _classify_connection_error(exc: BaseException) -> str:
    """Classify a failed connector call without exposing its message."""

    text = _exception_text(exc)
    auth_markers = (
        "authentication failed",
        "password authentication failed",
        "invalid password",
        "pg_hba.conf",
        "not authorized",
        "role .* does not exist",
    )
    if any(re.search(marker, text) for marker in auth_markers):
        return AUTH_FAILED
    # A timeout means the local published port is absent/unreachable just as a
    # refusal does for this disposable connector contract.
    network_markers = (
        "connection refused",
        "connection timed out",
        "timeout",
        "could not connect",
        "no route to host",
        "server closed the connection",
        "operationalerror",
        "interfaceerror",
    )
    if isinstance(exc, (ConnectionRefusedError, TimeoutError, OSError)) or any(
        marker in text for marker in network_markers
    ):
        return CONNECTION_REFUSED
    # The connector was invoked, so an unknown driver-side connect exception is
    # still more actionable as a connection failure than as a generic database
    # operation failure.
    return CONNECTION_REFUSED


def _preflight_failure_code(preflight: Mapping[str, Any]) -> str:
    if any(
        check.get("id") == "RPF-01" and check.get("status") != "PASS"
        for check in preflight.get("checks", [])
        if isinstance(check, Mapping)
    ):
        return TARGET_IDENTITY_MISMATCH
    return "RUNTIME_PREFLIGHT_BLOCKED"


def _postflight_failure_code(postflight: Mapping[str, Any]) -> str:
    if any(
        check.get("id") == "RPO-01" and check.get("status") != "PASS"
        for check in postflight.get("checks", [])
        if isinstance(check, Mapping)
    ):
        return TARGET_IDENTITY_MISMATCH
    return "RUNTIME_POSTFLIGHT_BLOCKED"


def _blocking_report(plan: Dict[str, Any], reason: str) -> Dict[str, Any]:
    reasons = list(plan.get("blocking_reasons", []))
    if reason not in reasons:
        reasons.append(reason)
    plan["blocking_reasons"] = sorted(set(reasons))
    plan["status"] = "BLOCKED"
    plan["execution_boundary"]["apply_reached"] = False
    if "failure_taxonomy" not in plan:
        _set_failure_taxonomy(plan, reason, "STATIC_PREFLIGHT")
    return plan


def _candidate_steps(manifest: Mapping[str, Any], *, apply_allowed: bool) -> List[Dict[str, Any]]:
    candidates = manifest.get("candidates") if isinstance(manifest.get("candidates"), list) else []
    steps: List[Dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, Mapping):
            continue
        steps.append(
            {
                "sequence": entry.get("sequence"),
                "candidate_file": entry.get("candidate_file"),
                "migration_id": entry.get("migration_id"),
                "depends_on": list(entry.get("depends_on", [])) if isinstance(entry.get("depends_on"), list) else [],
                "transaction_boundary": "ONE_TRANSACTION",
                "apply_allowed": apply_allowed,
                "status": "PLANNED",
            }
        )
    return steps


def _static_preflight(
    mode: ExecutionMode,
    target: Optional[Mapping[str, Any]],
    target_validation: Any,
    hash_report: Mapping[str, Any],
    blocking_reasons: Sequence[str],
) -> Dict[str, Any]:
    """Run checks that must pass before the connector can be invoked."""

    checks = [
        {
            "id": "RPS-01",
            "status": "PASS" if hash_report.get("status") == "PASS" else "BLOCKED",
            "reason": "Candidate manifest and canonical hashes verify locally",
        },
        {
            "id": "RPS-02",
            "status": "PASS"
            if (
                mode in {ExecutionMode.PLAN_ONLY, ExecutionMode.DRY_RUN}
                and target is None
            )
            or (target_validation is not None and target_validation.ok)
            else "BLOCKED",
            "reason": "Target descriptor is valid when required; no-write modes may omit it",
        },
        {
            "id": "RPS-03",
            "status": "PASS"
            if mode != ExecutionMode.APPLY
            or target is not None and target.get("environment") in ALLOWED_TARGET_ENVIRONMENTS
            else "BLOCKED",
            "reason": "Only an explicit non-production target can reach apply",
        },
        {
            "id": "RPS-04",
            "status": "PASS" if mode != ExecutionMode.PRODUCTION_APPLY else "BLOCKED",
            "reason": "Production apply mode is unconditionally hard-blocked",
        },
    ]
    return {
        "status": "PASS" if not blocking_reasons and all(check["status"] == "PASS" for check in checks) else "BLOCKED",
        "checks": checks,
        "connector_invoked": False,
        "blocking_reasons": list(sorted(set(blocking_reasons))),
    }


class RuntimeExecutor:
    """Plan by default; only explicit allow-listed apply can connect/write."""

    contract_version = RUNTIME_EXECUTOR_CONTRACT_VERSION

    def __init__(
        self,
        repo_root: Path,
        *,
        connection_adapter: Optional[ConnectionAdapter] = None,
        clock: Optional[Callable[[], str]] = None,
        actor: str = DEFAULT_ACTOR,
    ):
        self.repo_root = repo_root.resolve()
        self.connection_adapter = connection_adapter
        self.clock = clock or _now_iso
        self.actor = actor

    def plan(
        self,
        *,
        mode: ExecutionMode | str = ExecutionMode.PLAN_ONLY,
        target: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if isinstance(mode, str):
            mode = ExecutionMode(mode)
        try:
            manifest = load_candidate_manifest(self.repo_root)
        except CanonicalHashError:
            manifest = {"candidates": []}
        hash_report = verify_candidate_hashes(self.repo_root, manifest if manifest.get("candidates") else None)
        target_validation = validate_target_descriptor(dict(target)) if target is not None else None
        blocking: List[str] = []
        if hash_report.get("status") != "PASS":
            blocking.append("CANONICAL_HASH_VERIFICATION_FAILED")
        if mode == ExecutionMode.APPLY:
            if target_validation is None:
                blocking.append("EXPLICIT_TARGET_REQUIRED_FOR_APPLY")
            elif not target_validation.ok:
                blocking.extend(issue.code for issue in target_validation.issues)
            if target is not None and target.get("environment") not in ALLOWED_TARGET_ENVIRONMENTS:
                blocking.append("PRODUCTION_TARGET_HARD_BLOCK")
        if mode == ExecutionMode.PRODUCTION_APPLY:
            blocking.append("PRODUCTION_TARGET_HARD_BLOCK")
        if target_validation is not None and not target_validation.ok and mode in {ExecutionMode.PLAN_ONLY, ExecutionMode.DRY_RUN}:
            blocking.extend(issue.code for issue in target_validation.issues)

        status = "BLOCKED" if blocking else ("PLANNED" if mode == ExecutionMode.PLAN_ONLY else "DRY_RUN_READY")
        target_value = _safe_target(target)
        static_preflight = _static_preflight(mode, target, target_validation, hash_report, blocking)
        payload = {
            "contract_version": self.contract_version,
            "mode": mode.value,
            "status": status,
            "target": target_value,
            "target_validation": target_validation.to_dict() if target_validation else None,
            "hash_verification": hash_report,
            "driver": driver_status(),
            "runtime_case_wiring": validate_runtime_case_wiring(self.repo_root),
            "static_preflight": static_preflight,
            "steps": _candidate_steps(manifest, apply_allowed=status != "BLOCKED" and mode == ExecutionMode.APPLY),
            "execution_boundary": {
                "connector_invoked": False,
                "database_connected": False,
                "sql_executed": False,
                "ddl_applied": False,
                "apply_reached": False,
                "production_db_writes_performed": "NO",
                "supabase_writes_performed": "NO",
                "v333_mutated": "NO",
            },
            "blocking_reasons": sorted(set(blocking)),
        }
        payload["plan_hash"] = sha256_json(
            {
                "contract_version": payload["contract_version"],
                "mode": payload["mode"],
                "status": payload["status"],
                "target": payload["target"],
                "steps": payload["steps"],
                "hashes": [entry.get("computed_hash") for entry in hash_report.get("entries", [])],
                "blocking_reasons": payload["blocking_reasons"],
            }
        )
        return payload

    def execute(
        self,
        *,
        target: Optional[Mapping[str, Any]],
        mode: ExecutionMode | str = ExecutionMode.PLAN_ONLY,
        connection_settings: Optional[ConnectionSettings] = None,
        run_validations: bool = True,
    ) -> Dict[str, Any]:
        if isinstance(mode, str):
            mode = ExecutionMode(mode)
        plan = self.plan(mode=mode, target=target)
        if mode != ExecutionMode.APPLY or plan["blocking_reasons"]:
            return plan
        if target is None or target.get("environment") not in ALLOWED_TARGET_ENVIRONMENTS:
            return _blocking_report(plan, "PRODUCTION_TARGET_HARD_BLOCK")

        try:
            settings = connection_settings or ConnectionSettings.from_environment()
        except ConnectionConfigError as exc:
            error_code = "RUNTIME_CONNECTION_CONFIG_INVALID"
            plan["connection"] = {
                "status": "BLOCKED_CONFIGURATION",
                "safe_settings": {},
                "error_code": error_code,
                "missing_environment_variables": list(exc.missing),
            }
            plan["error"] = {
                "error_code": error_code,
                "error_type": type(exc).__name__,
                "phase": "CONFIGURATION",
                "connector_status": CONNECTOR_NOT_INVOKED,
                "missing_environment_variables": list(exc.missing),
            }
            _set_failure_taxonomy(plan, error_code, "CONFIGURATION")
            return _blocking_report(plan, error_code)

        adapter = self.connection_adapter or PostgresConnectionAdapter()
        adapter_status = adapter.status() if hasattr(adapter, "status") else {"status": "READY", "connection_opened": False}
        plan["driver"] = adapter_status
        if adapter_status.get("status") != "READY":
            error_code = DRIVER_MISSING
            plan["connection"] = {"status": "BLOCKED_DEPENDENCY", "safe_settings": settings.safe_dict()}
            plan["error"] = {
                "error_code": error_code,
                "error_type": "DriverUnavailable",
                "phase": "DRIVER_CHECK",
                "connector_status": CONNECTOR_NOT_INVOKED,
            }
            _set_failure_taxonomy(plan, error_code, "DRIVER_CHECK")
            return _blocking_report(plan, error_code)

        plan["connection"] = {"status": "READY_TO_CONNECT", "safe_settings": settings.safe_dict()}
        connection = None
        phase = "CONNECT"
        # Mark invocation before entering the adapter.  A refused or timed-out
        # socket raises before connect() returns, but the call was still made.
        plan["execution_boundary"]["connector_invoked"] = True
        try:
            connection = adapter.connect(settings)
            plan["execution_boundary"]["database_connected"] = True
            plan["connection"]["status"] = "CONNECTED"
            phase = "RUNTIME_PREFLIGHT"
            preflight = self._runtime_preflight(connection, target, plan["hash_verification"], settings)
            plan["preflight"] = preflight
            if preflight.get("status") != "PASS":
                error_code = _preflight_failure_code(preflight)
                plan["error"] = {
                    "error_code": error_code,
                    "error_type": "RuntimePreflightBlocked",
                    "phase": phase,
                    "connector_status": CONNECTOR_INVOKED,
                }
                _set_failure_taxonomy(plan, error_code, phase)
                return _blocking_report(plan, error_code)
            plan["execution_boundary"]["apply_reached"] = True
            phase = "SQL_APPLY"
            apply_report = self._apply_candidates(connection, plan["hash_verification"])
            plan["migrations"] = apply_report
            plan["migration_apply_path"] = {
                "status": "PASS" if apply_report.get("status") in {"PASS", "ALREADY_APPLIED"} else "FAIL",
                "candidate_count": 9,
                "applied_count": apply_report.get("applied_count", 0),
                "validated_history_count": apply_report.get("applied_count", 0) + apply_report.get("skipped_count", 0),
                "history_recording": "PASS" if apply_report.get("status") in {"PASS", "ALREADY_APPLIED"} else "FAIL",
                "transactional_ddl_and_history": True,
            }
            if apply_report.get("status") not in {"PASS", "ALREADY_APPLIED"}:
                error_code = str(apply_report.get("error_code") or SQL_APPLY_FAILED)
                failed_record = next(
                    (
                        record
                        for record in apply_report.get("records", [])
                        if isinstance(record, Mapping) and record.get("status") not in {"APPLIED"}
                    ),
                    None,
                )
                plan["error"] = (
                    dict(failed_record["error"])
                    if isinstance(failed_record, Mapping) and isinstance(failed_record.get("error"), Mapping)
                    else {
                        "error_code": error_code,
                        "error_type": "MigrationApplyBlocked",
                        "phase": phase,
                        "connector_status": CONNECTOR_INVOKED,
                    }
                )
                _set_failure_taxonomy(plan, error_code, phase)
                return _blocking_report(plan, error_code)
            phase = "RUNTIME_POSTFLIGHT"
            postflight = self._runtime_postflight(connection, target)
            plan["postflight"] = postflight
            if postflight.get("status") != "PASS":
                error_code = _postflight_failure_code(postflight)
                plan["error"] = {
                    "error_code": error_code,
                    "error_type": "RuntimePostflightBlocked",
                    "phase": phase,
                    "connector_status": CONNECTOR_INVOKED,
                }
                _set_failure_taxonomy(plan, error_code, phase)
                return _blocking_report(plan, error_code)
            if run_validations:
                phase = "RUNTIME_VALIDATION"
                plan["schema_checks"] = collect_runtime_schema_checks(connection)
                validation_adapter = PostgresRuntimeCaseAdapter(connection, repo_root=self.repo_root, actor=self.actor)
                plan["runtime_validation"] = run_runtime_cases(self.repo_root, validation_adapter)
            else:
                plan["schema_checks"] = {
                    "status": "BLOCKED_ENVIRONMENT",
                    "reason": "Runtime validations were explicitly disabled",
                    "advisor_status": "NOT_RUN_IN_DISPOSABLE",
                }
                plan["runtime_validation"] = {
                    "status": "BLOCKED",
                    "defined_count": 35,
                    "actually_executed": 0,
                    "blocked_environment": 35,
                    "reason": "Runtime validations were explicitly disabled",
                    "results": [],
                }
            runtime_status = plan.get("runtime_validation", {}).get("status")
            if runtime_status == "FAIL":
                plan["status"] = "RUNTIME_VALIDATION_FAILED"
            elif runtime_status == "PASS":
                plan["status"] = "RUNTIME_VALIDATION_PASS"
            else:
                plan["status"] = "RUNTIME_VALIDATION_BLOCKED"
            plan["execution_boundary"]["sql_executed"] = bool(
                apply_report.get("applied_count", 0) > 0
                or plan.get("runtime_validation", {}).get("actually_executed", 0) > 0
            )
            plan["execution_boundary"]["ddl_applied"] = apply_report.get("applied_count", 0) > 0
            plan["database_runtime_executed_in_codex"] = "NO"
            plan["database_runtime_executed_on_target"] = "YES"
            plan["production_db_writes_performed"] = "NO"
            plan["supabase_writes_performed"] = "NO"
            plan["v4_018_v4_019_changed"] = "NO"
            runtime = plan.get("runtime_validation", {})
            schema = plan.get("schema_checks", {})
            gates = runtime.get("runtime_gates", {}) if isinstance(runtime, Mapping) else {}
            history_ok = (
                apply_report.get("status") in {"PASS", "ALREADY_APPLIED"}
                and int(plan.get("postflight", {}).get("history_row_count", 0)) == 9
            )
            readiness_checks = {
                "migrations_9_of_9": history_ok,
                "smoke_20_of_20": runtime.get("passed_smoke", 0) == 20 and runtime.get("smoke_count") == 20,
                "enforcement_15_of_15": runtime.get("passed_enforcement", 0) == 15 and runtime.get("enforcement_count") == 15,
                "schema_constraints": schema.get("constraints", {}).get("status") == "PASS",
                "rls": schema.get("rls", {}).get("status") == "PASS",
                "triggers": schema.get("triggers", {}).get("status") == "PASS",
                "views": schema.get("views", {}).get("status") == "PASS",
                "no_future_leakage": gates.get("no_future_leakage") == "PASS" and schema.get("no_future_leakage", {}).get("status") == "PASS",
                "production_uniqueness": gates.get("production_uniqueness") == "PASS" and schema.get("production_uniqueness", {}).get("status") == "PASS",
                "tier_a_same_frozen_input": gates.get("tier_a_same_frozen_input") == "PASS",
                "canonical_latest_update": gates.get("canonical_latest_update") == "PASS" and schema.get("canonical_latest_update", {}).get("status") == "PASS",
            }
            readiness_ready = all(readiness_checks.values()) and runtime.get("status") == "PASS" and schema.get("status") == "PASS"
            plan["staging_readiness"] = {
                "status": "READY_FOR_PRODUCTION_REVIEW" if readiness_ready else "BLOCKED_RUNTIME_VALIDATION",
                "checks": readiness_checks,
                "advisor_status": "NOT_RUN_IN_DISPOSABLE",
                "production_apply_allowed": False,
            }
            return plan
        except Exception as exc:
            if phase == "CONNECT":
                error_code = _classify_connection_error(exc)
            elif phase == "SQL_APPLY":
                error_code = SQL_APPLY_FAILED
            elif phase == "RUNTIME_PREFLIGHT":
                error_code = "RUNTIME_PREFLIGHT_FAILED"
            elif phase == "RUNTIME_POSTFLIGHT":
                error_code = "RUNTIME_POSTFLIGHT_FAILED"
            elif phase == "RUNTIME_VALIDATION":
                error_code = "RUNTIME_VALIDATION_FAILED"
            else:
                error_code = "RUNTIME_EXECUTION_FAILED"
            plan["error"] = _safe_error(
                exc,
                error_code=error_code,
                phase=phase,
                connector_status=CONNECTOR_INVOKED,
            )
            if phase == "CONNECT":
                plan["connection"]["status"] = "CONNECT_FAILED"
            _set_failure_taxonomy(plan, error_code, phase)
            return _blocking_report(plan, error_code)
        finally:
            if connection is not None:
                try:
                    adapter.close(connection)
                except Exception:
                    # Close failures do not expose driver text or credentials.
                    plan.setdefault("cleanup", {})["close_status"] = "FAILED_REDACTED"

    def _runtime_preflight(
        self,
        connection: Any,
        target: Mapping[str, Any],
        hash_report: Mapping[str, Any],
        settings: ConnectionSettings,
    ) -> Dict[str, Any]:
        manifest = load_candidate_manifest(self.repo_root)
        candidates = [item for item in manifest.get("candidates", []) if isinstance(item, Mapping)]
        catalog = collect_runtime_catalog(connection, target, candidates)
        checks: List[Dict[str, Any]] = []

        def add(check_id: str, passed: bool, reason: str, **details: Any) -> None:
            checks.append({"id": check_id, "status": "PASS" if passed else "BLOCKED", "reason": reason, "details": details})

        target_identity = catalog.get("target_identity", {})
        add("RPF-01", target_identity.get("matches_descriptor") is True, "Connected database matches the explicit target identity")
        version = catalog.get("database_version", {})
        add("RPF-02", version.get("compatibility_approved") is True, "PostgreSQL 16 compatibility is proven", major=version.get("major"))
        extensions = catalog.get("extensions", [])
        add("RPF-03", any(item.get("name") == "pgcrypto" and item.get("approved") is True for item in extensions), "pgcrypto is installed or available for the candidate bootstrap")
        add("RPF-04", not catalog.get("v333_objects"), "No V3.3.3-like object is present in the local target")
        history = catalog.get("migration_history", {})
        history_rows = self._read_history_rows(connection)
        history_prefix, history_issue = self._validated_history_prefix(history_rows, candidates)
        history_prefix_ok = history_issue is None and history_prefix == len(history_rows)
        add("RPF-05", history.get("partial_applied") is not True and history.get("matches_manifest") is True and history_prefix_ok, "Migration history is empty or an exact applied prefix", history_issue=history_issue)
        objects = catalog.get("objects", [])
        has_history = bool(history.get("rows"))
        add("RPF-06", not objects or has_history, "Target is fresh or already attributable to the candidate history")
        add("RPF-07", hash_report.get("status") == "PASS", "All candidate canonical hashes and headers verify")
        add("RPF-08", settings.password_env_name == target.get("credential_env_name"), "Credential is referenced by the expected environment-variable name")
        add("RPF-09", target.get("environment") in ALLOWED_TARGET_ENVIRONMENTS, "Target environment is explicitly allow-listed")
        return {
            "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "BLOCKED",
            "checks": checks,
            "catalog_summary": {
                "database_version": catalog.get("database_version"),
                "target_identity": catalog.get("target_identity"),
                "namespace_count": len(catalog.get("namespaces", [])),
                "object_count": len(catalog.get("objects", [])),
                "v333_object_count": len(catalog.get("v333_objects", [])),
                "history_row_count": len(catalog.get("migration_history", {}).get("rows", [])),
            },
            "connector_invoked": True,
        }

    def _runtime_postflight(self, connection: Any, target: Mapping[str, Any]) -> Dict[str, Any]:
        """Prove the exact nine-row history prefix after explicit apply."""

        manifest = load_candidate_manifest(self.repo_root)
        candidates = [item for item in manifest.get("candidates", []) if isinstance(item, Mapping)]
        catalog = collect_runtime_catalog(connection, target, candidates)
        history = catalog.get("migration_history", {})
        history_rows = self._read_history_rows(connection)
        history_prefix, history_issue = self._validated_history_prefix(history_rows, candidates)
        checks = [
            {
                "id": "RPO-01",
                "status": "PASS" if catalog.get("target_identity", {}).get("matches_descriptor") is True else "BLOCKED",
                "reason": "Postflight database identity matches the explicit target",
            },
            {
                "id": "RPO-02",
                "status": "PASS" if not catalog.get("v333_objects") else "BLOCKED",
                "reason": "No V3.3.3-like object is present after apply",
            },
            {
                "id": "RPO-03",
                "status": "PASS"
                if history.get("matches_manifest") is True
                and history.get("partial_applied") is not True
                and len(history.get("rows", [])) == len(candidates)
                and history_issue is None
                and history_prefix == len(candidates)
                else "BLOCKED",
                "reason": "All nine immutable migration history rows match the candidate manifest",
                "details": {"history_issue": history_issue},
            },
        ]
        return {
            "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "BLOCKED",
            "checks": checks,
            "history_row_count": len(history.get("rows", [])),
            "v333_object_count": len(catalog.get("v333_objects", [])),
        }

    def _apply_candidates(self, connection: Any, hash_report: Mapping[str, Any]) -> Dict[str, Any]:
        manifest = load_candidate_manifest(self.repo_root)
        candidates = [item for item in manifest.get("candidates", []) if isinstance(item, Mapping)]
        if hash_report.get("status") != "PASS" or len(candidates) != 9:
            return {"status": "BLOCKED", "applied_count": 0, "records": [], "reason": "Canonical hash verification did not pass"}
        history_rows = self._read_history_rows(connection)
        prefix, history_issue = self._validated_history_prefix(history_rows, candidates)
        if history_issue:
            return {
                "status": "BLOCKED",
                "applied_count": 0,
                "records": [],
                "reason": history_issue,
                "error_code": "MIGRATION_HISTORY_INVALID",
            }
        if prefix == len(candidates):
            return {"status": "ALREADY_APPLIED", "applied_count": 0, "records": [], "skipped_count": prefix}

        records: List[Dict[str, Any]] = []
        previous_hash = candidates[prefix - 1].get("canonical_migration_hash") if prefix else None
        for entry in candidates[prefix:]:
            started_at = self.clock()
            record: Dict[str, Any] = {
                "sequence": entry.get("sequence"),
                "migration_id": entry.get("migration_id"),
                "migration_hash": entry.get("canonical_migration_hash"),
                "start": started_at,
                "end": None,
                "status": "APPLYING",
                "error": None,
            }
            sql_path = self.repo_root / Path(str(entry.get("candidate_file")))
            sql_applied = False
            try:
                sql_text = sql_path.read_text(encoding="utf-8")
                if len(_SQL_BEGIN_RE.findall(sql_text)) != 1 or len(_SQL_COMMIT_RE.findall(sql_text)) != 1:
                    raise RuntimeError("Candidate migration transaction shape is invalid")
                self._execute_sql(connection, sql_text)
                sql_applied = True
                chain_hash = sha256_json({"migration_id": entry.get("migration_id"), "migration_hash": entry.get("canonical_migration_hash"), "prev_migration_hash": previous_hash})
                self._record_history(
                    connection,
                    entry,
                    applied_at=started_at,
                    applied_by=self.actor,
                    previous_hash=previous_hash,
                    chain_hash=chain_hash,
                    status="APPLIED",
                    success=True,
                    partial_state=False,
                    notes="runtime candidate applied by explicit local/staging executor",
                )
                self._commit(connection)
                sql_applied = True
                record["status"] = "APPLIED"
                record["end"] = self.clock()
                records.append(record)
                previous_hash = entry.get("canonical_migration_hash")
            except Exception as exc:
                self._rollback(connection)
                record["status"] = "PARTIAL_FAIL" if sql_applied else "FAILED"
                record["end"] = self.clock()
                record["error"] = _safe_error(
                    exc,
                    error_code=SQL_APPLY_FAILED,
                    phase="SQL_APPLY",
                    connector_status=CONNECTOR_INVOKED,
                )
                self._try_record_failure(connection, entry, previous_hash, partial_state=sql_applied)
                records.append(record)
                return {
                    "status": record["status"],
                    "applied_count": sum(item["status"] == "APPLIED" for item in records),
                    "records": records,
                    "error_code": SQL_APPLY_FAILED,
                }
        return {"status": "PASS", "applied_count": len(records), "records": records, "skipped_count": prefix}

    @staticmethod
    def _execute_sql(connection: Any, sql_text: str) -> None:
        lines = sql_text.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
        begin_indices = [index for index, line in enumerate(lines) if line.strip().upper() == "BEGIN;"]
        commit_indices = [index for index, line in enumerate(lines) if line.strip().upper() == "COMMIT;"]
        if len(begin_indices) != 1 or len(commit_indices) != 1 or begin_indices[0] >= commit_indices[0]:
            raise RuntimeError("Candidate migration transaction shape is invalid")
        body = "".join(
            line
            for index, line in enumerate(lines)
            if index not in {begin_indices[0], commit_indices[0]}
        )
        cursor = connection.cursor()
        try:
            # Candidate files carry explicit BEGIN/COMMIT markers as static
            # evidence.  The executor removes only those wrapper lines so the
            # DDL and its immutable history row commit atomically together.
            cursor.execute(body)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _commit(connection: Any) -> None:
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    @staticmethod
    def _rollback(connection: Any) -> None:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()

    @staticmethod
    def _read_rows(connection: Any, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, tuple(params))
            names = [item[0] for item in (getattr(cursor, "description", None) or [])]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def _read_history_rows(self, connection: Any) -> List[Dict[str, Any]]:
        table = self._read_rows(connection, "SELECT to_regclass('governance.schema_migrations') AS object_name")
        if not table or not table[0].get("object_name"):
            return []
        return self._read_rows(
            connection,
            "SELECT migration_id, sequence, name, migration_version, schema_contract_version, migration_hash, applied_at, applied_by, app_version, status, success, partial_state, notes, prev_migration_hash, chain_hash, recorded_at "
            "FROM governance.schema_migrations ORDER BY sequence",
        )

    @staticmethod
    def _validated_history_prefix(rows: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> tuple[int, Optional[str]]:
        if len(rows) > len(candidates):
            return 0, "Migration history contains more rows than the immutable candidate manifest"
        seen = set()
        for index, row in enumerate(rows):
            entry = candidates[index]
            migration_id = row.get("migration_id")
            if migration_id in seen or migration_id != entry.get("migration_id"):
                return index, "Migration history identity/order does not match the candidate prefix"
            seen.add(migration_id)
            if row.get("sequence") != entry.get("sequence"):
                return index, "Migration history sequence differs from the immutable candidate prefix"
            if row.get("name") != entry.get("name"):
                return index, "Migration history name differs from the immutable candidate prefix"
            if row.get("migration_version") != entry.get("migration_version"):
                return index, "Migration history migration_version differs from the immutable candidate prefix"
            if row.get("schema_contract_version") != entry.get("schema_contract_version"):
                return index, "Migration history schema contract differs from the immutable candidate prefix"
            if row.get("migration_hash") != entry.get("canonical_migration_hash"):
                return index, "Migration history hash differs from the immutable candidate hash"
            if row.get("status") != "APPLIED" or row.get("success") is not True or row.get("partial_state") is True:
                return index, "Migration history contains a failed, blocked, or partial state"
            expected_previous_hash = candidates[index - 1].get("canonical_migration_hash") if index else None
            if row.get("prev_migration_hash") != expected_previous_hash:
                return index, "Migration history previous-hash chain differs from the immutable candidate prefix"
            expected_chain_hash = sha256_json(
                {
                    "migration_id": entry.get("migration_id"),
                    "migration_hash": entry.get("canonical_migration_hash"),
                    "prev_migration_hash": expected_previous_hash,
                }
            )
            if row.get("chain_hash") != expected_chain_hash:
                return index, "Migration history chain_hash differs from the immutable candidate prefix"
        return len(rows), None

    def _record_history(
        self,
        connection: Any,
        entry: Mapping[str, Any],
        *,
        applied_at: str,
        applied_by: str,
        previous_hash: Optional[str],
        chain_hash: str,
        status: str,
        success: bool,
        partial_state: bool,
        notes: str,
    ) -> None:
        sql = (
            "INSERT INTO governance.schema_migrations "
            "(migration_id, sequence, name, migration_version, schema_contract_version, migration_hash, "
            "applied_at, applied_by, app_version, success, status, partial_state, notes, prev_migration_hash, chain_hash, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        values = (
            entry.get("migration_id"),
            entry.get("sequence"),
            entry.get("name"),
            entry.get("migration_version"),
            entry.get("schema_contract_version"),
            entry.get("canonical_migration_hash"),
            applied_at,
            applied_by,
            "jcfb-v4-runtime-executor@1.0.0",
            success,
            status,
            partial_state,
            notes,
            previous_hash,
            chain_hash,
            json.dumps({"executor_contract": RUNTIME_EXECUTOR_CONTRACT_VERSION}, separators=(",", ":")),
        )
        cursor = connection.cursor()
        try:
            cursor.execute(sql, values)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        # The caller commits DDL and its immutable history row together.  A
        # commit here would make the migration only partially atomic.

    def _try_record_failure(self, connection: Any, entry: Mapping[str, Any], previous_hash: Optional[str], *, partial_state: bool) -> None:
        try:
            table = self._read_rows(connection, "SELECT to_regclass('governance.schema_migrations') AS object_name")
            if not table or not table[0].get("object_name"):
                return
            chain_hash = sha256_json({"migration_id": entry.get("migration_id"), "migration_hash": entry.get("canonical_migration_hash"), "prev_migration_hash": previous_hash, "status": "BLOCKED"})
            self._record_history(
                connection,
                entry,
                applied_at=self.clock(),
                applied_by=self.actor,
                previous_hash=previous_hash,
                chain_hash=chain_hash,
                status="BLOCKED",
                success=False,
                partial_state=partial_state,
                notes="runtime candidate execution failed; remediation requires a new forward migration",
            )
            self._commit(connection)
        except Exception:
            # Failure evidence remains in the local JSON report.  Never expose
            # a secondary driver error or attempt an UPDATE/DELETE repair.
            return


def render_runtime_report_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact report without credentials, URLs, or SQL text."""

    boundary = report.get("execution_boundary", {})
    hashes = report.get("hash_verification", {})
    runtime = report.get("runtime_validation", {})
    wiring = report.get("runtime_case_wiring", {})
    migrations = report.get("migrations", {})
    schema = report.get("schema_checks", {})
    readiness = report.get("staging_readiness", {})
    taxonomy = report.get("failure_taxonomy", {})
    error = report.get("error", {})
    runtime_summary_lines = report.get("runtime_summary_lines")
    if not isinstance(runtime_summary_lines, list) or not all(
        isinstance(item, str) for item in runtime_summary_lines
    ):
        runtime_summary_lines = _runtime_summary_lines(report)
    lines = [
        "# JCFB V4 PRE-BATCH-04 Runtime Validation Report",
        "",
        f"- run_id: `{report.get('run_id', 'NOT_PERSISTED')}`",
        f"- started_at: `{report.get('started_at', 'NOT_PERSISTED')}`",
        f"- finished_at: `{report.get('finished_at', 'NOT_PERSISTED')}`",
        f"- git_head: `{report.get('git_head', 'NOT_PERSISTED')}`",
        f"- smoke_passed: `{report.get('smoke_passed', runtime.get('passed_smoke', 0))}/{runtime.get('smoke_count', 20)}`",
        f"- enforcement_passed: `{report.get('enforcement_passed', runtime.get('passed_enforcement', 0))}/{runtime.get('enforcement_count', 15)}`",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Contract: `{report.get('contract_version')}`",
        f"- Mode: `{report.get('mode')}`",
        f"- Target identity: `{(report.get('target') or {}).get('target_id')}`",
        f"- Target environment: `{(report.get('target') or {}).get('environment')}`",
        f"- Canonical hashes: `{hashes.get('matched_count', 0)}/{hashes.get('candidate_count', 0)}`",
        f"- Hash verifier: `{hashes.get('status')}`",
        f"- Connector invoked: `{boundary.get('connector_invoked')}`",
        f"- Database connected: `{boundary.get('database_connected')}`",
        f"- SQL executed: `{boundary.get('sql_executed')}`",
        f"- Production DB writes: `{boundary.get('production_db_writes_performed', 'NO')}`",
        f"- Supabase writes: `{boundary.get('supabase_writes_performed', 'NO')}`",
        f"- V3.3.3 mutated: `{boundary.get('v333_mutated', 'NO')}`",
        f"- Database runtime tests executed in Codex: `{report.get('database_runtime_executed_in_codex', 'NO')}`",
        f"- Database runtime tests executed on target: `{report.get('database_runtime_executed_on_target', 'NO')}`",
        f"- Migration apply path: `{report.get('migration_apply_path', {}).get('status', 'NOT_RUN')}`",
        f"- Migration history recording: `{report.get('migration_apply_path', {}).get('history_recording', 'NOT_RUN')}`",
        f"- Production/Supabase writes performed: `{report.get('production_db_writes_performed', boundary.get('production_db_writes_performed', 'NO'))}/{report.get('supabase_writes_performed', boundary.get('supabase_writes_performed', 'NO'))}`",
        "- BATCH-04/V4-018/V4-019 changed: `NO`",
        "",
        "## Persisted runtime summary",
        "",
        "```text",
        *runtime_summary_lines,
        "```",
        "",
        "## Runtime case wiring",
        "",
        f"- Smoke bindings: `{wiring.get('smoke_count', 0)}/20`",
        f"- Smoke executable handlers: `{wiring.get('smoke_executable_handler_count', 0)}/20`",
        f"- Enforcement bindings: `{wiring.get('enforcement_count', 0)}/15`",
        f"- Enforcement executable handlers: `{wiring.get('enforcement_executable_handler_count', 0)}/15`",
        f"- Runtime case result: `{runtime.get('status', 'NOT_RUN')}`",
        f"- Cases executed: `{runtime.get('actually_executed', 0)}/35`",
        f"- Expected-reject matching: `{runtime.get('expected_reject_matching', 'NOT_RUN')}`",
        f"- Role simulation: `{(runtime.get('role_simulation') or {}).get('status', 'NOT_RUN')}`",
        f"- Case cleanup: `{(runtime.get('cleanup') or {}).get('status', 'NOT_RUN')}`",
        "",
        "## Migration history",
        "",
        f"- Apply status: `{migrations.get('status', 'NOT_RUN')}`",
        f"- Applied this invocation: `{migrations.get('applied_count', 0)}/9`",
        f"- Validated migration history rows: `{migrations.get('validated_history_count', migrations.get('applied_count', 0))}/9`",
        f"- Transactional DDL + history row: `{report.get('migration_apply_path', {}).get('transactional_ddl_and_history', False)}`",
        "",
        "## Schema and security checks",
        "",
        f"- Schema audit: `{schema.get('status', 'NOT_RUN')}`",
        f"- Tables/constraints: `{schema.get('tables', {}).get('status', 'NOT_RUN')}/{schema.get('constraints', {}).get('status', 'NOT_RUN')}`",
        f"- RLS/triggers/views: `{schema.get('rls', {}).get('status', 'NOT_RUN')}/{schema.get('triggers', {}).get('status', 'NOT_RUN')}/{schema.get('views', {}).get('status', 'NOT_RUN')}`",
        f"- No future leakage: `{schema.get('no_future_leakage', {}).get('status', 'NOT_RUN')}`",
        f"- Production uniqueness: `{schema.get('production_uniqueness', {}).get('status', 'NOT_RUN')}`",
        f"- Canonical latest update: `{schema.get('canonical_latest_update', {}).get('status', 'NOT_RUN')}`",
        f"- Supabase Advisor: `{schema.get('advisor_status', 'NOT_RUN_IN_DISPOSABLE')}`",
        "",
        "## Runtime gates",
        "",
    ]
    gates = runtime.get("runtime_gates", {}) if isinstance(runtime, Mapping) else {}
    lines.extend([f"- {name}: `{value}`" for name, value in gates.items()] or ["- None"])
    lines.extend(["", "## Staging readiness", "", f"- Status: `{readiness.get('status', 'NOT_RUN')}`"])
    readiness_checks = readiness.get("checks", {}) if isinstance(readiness, Mapping) else {}
    lines.extend([f"- {name}: `{'PASS' if value else 'FAIL'}`" for name, value in readiness_checks.items()] or ["- No readiness checks were run"])
    lines.extend(["", "## Blocking reasons", ""])
    lines.extend([f"- `{reason}`" for reason in (report.get("blocking_reasons") or [])] or ["- None"])
    lines.extend(["", "## Runtime cases", "", "| Case | Kind | Status | Expected | Actual | Phase | Transaction state | Error class | SQLSTATE | DB object/constraint/trigger/policy | Matcher | Previous-case contamination | Handler | Reason |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---"])
    case_results = runtime.get("results", []) if isinstance(runtime, Mapping) else []
    if case_results:
        for result in case_results:
            mechanism = result.get("observed_mechanism") or result.get("expected_mechanism") or {}
            mechanism_parts = []
            for key in ("object", "constraint", "trigger", "policy", "role_gate", "view", "catalog", "postcondition"):
                value = mechanism.get(key) if isinstance(mechanism, Mapping) else None
                if value:
                    mechanism_parts.append(f"{key}={value}")
            error_constraint = result.get("error_constraint")
            if error_constraint and not any("constraint=" in item for item in mechanism_parts):
                mechanism_parts.append(f"db_constraint={error_constraint}")
            mechanism_text = ", ".join(mechanism_parts) or (str(mechanism.get("type") if isinstance(mechanism, Mapping) else "-") or "-")
            mechanism_text = mechanism_text.replace("|", "/")
            reason_text = str(result.get("reason") or result.get("blocked_reason") or result.get("expected_rejection_match_reason") or "-").replace("|", "/").replace("\r", " ").replace("\n", " ")
            lines.append(
                f"| {result.get('case_id')} | {result.get('kind')} | {result.get('status')} | {result.get('expected_outcome', '-')} | {result.get('actual_outcome', '-')} | {result.get('execution_phase') or result.get('phase') or '-'} | {result.get('transaction_state') or '-'} | {result.get('error_class') or '-'} | {result.get('error_sqlstate') or '-'} | {mechanism_text} | {result.get('expected_rejection_match') if result.get('expected_rejection_match') is not None else '-'} | {result.get('contaminated_by_previous_case', '-')} | {result.get('hook_name')} | {reason_text} |"
            )
    else:
        lines.append("| - | - | NOT_RUN | - | - | - | - | - | - | - | - | - | - | - |")
    if taxonomy:
        lines.extend(
            [
                "",
                "## Failure taxonomy",
                "",
                f"- Error code: `{taxonomy.get('error_code')}`",
                f"- Phase: `{taxonomy.get('phase')}`",
                f"- Connector status: `{taxonomy.get('connector_status')}`",
            ]
        )
    if error:
        lines.extend(
            [
                "",
                "## Redacted error",
                "",
                f"- Error code: `{error.get('error_code')}`",
                f"- Error type: `{error.get('error_type')}`",
                f"- Phase: `{error.get('phase')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def list_runtime_report_paths(report_dir: Path) -> List[Path]:
    """List valid report filenames under the report root and all run folders."""

    root = Path(report_dir).resolve()
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob(RUNTIME_REPORT_FILENAME)
        if path.is_file() and _report_path_is_inside(root, path.resolve())
    )


def _read_runtime_report(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _runtime_report_sort_key(path: Path) -> tuple[Any, ...]:
    value = _read_runtime_report(path) or {}
    timestamp = _parse_report_time(value.get("finished_at")) or _parse_report_time(value.get("started_at"))
    return (
        1 if timestamp is not None else 0,
        timestamp or datetime.min.replace(tzinfo=timezone.utc),
        path.stat().st_mtime_ns,
        str(value.get("run_id") or ""),
        path.as_posix(),
    )


def select_latest_runtime_report(report_dir: Path) -> Optional[Path]:
    """Select the newest valid report, including reports in timestamped runs.

    A valid latest pointer is written for operator convenience, but selection
    still compares every valid report.  That prevents a stale pointer from
    hiding a newer report if a run was copied or recovered manually.
    """

    candidates = [path for path in list_runtime_report_paths(report_dir) if _read_runtime_report(path) is not None]
    return max(candidates, key=_runtime_report_sort_key) if candidates else None


def load_latest_runtime_report(report_dir: Path) -> Dict[str, Any]:
    path = select_latest_runtime_report(report_dir)
    if path is None:
        raise FileNotFoundError(f"No valid {RUNTIME_REPORT_FILENAME} found under {Path(report_dir).resolve()}")
    value = _read_runtime_report(path)
    if value is None:
        raise ValueError(f"Selected runtime report is not valid JSON: {path}")
    value["_selected_report_path"] = path.as_posix()
    return value


def write_runtime_report(
    report: Mapping[str, Any],
    repo_root: Path,
    report_dir: Optional[Path] = None,
    *,
    run_id: Optional[str] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    git_head: Optional[str] = None,
) -> Dict[str, str]:
    directory = (report_dir or (repo_root / DEFAULT_REPORT_RELATIVE)).resolve()
    root = repo_root.resolve()
    if root not in directory.parents and directory != root:
        raise ValueError("Runtime report directory must remain inside the repository")
    directory.mkdir(parents=True, exist_ok=True)
    runs_directory = directory / "runs"
    runs_directory.mkdir(parents=True, exist_ok=True)
    materialized = _materialize_runtime_report(
        report,
        root,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        git_head=git_head,
    )
    run_directory = (runs_directory / materialized["run_id"]).resolve()
    if not _report_path_is_inside(directory, run_directory):
        raise ValueError("Runtime report run directory must remain inside the report root")
    run_directory.mkdir(parents=False, exist_ok=False)
    json_path = run_directory / RUNTIME_REPORT_FILENAME
    markdown_path = run_directory / RUNTIME_REPORT_MARKDOWN_FILENAME
    _atomic_write_text(
        json_path,
        json.dumps(materialized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(markdown_path, render_runtime_report_markdown(materialized))

    pointer_path = directory / RUNTIME_REPORT_POINTER_FILENAME
    pointer = {
        "pointer_version": RUNTIME_REPORT_POINTER_VERSION,
        "run_id": materialized["run_id"],
        "started_at": materialized["started_at"],
        "finished_at": materialized["finished_at"],
        "git_head": materialized["git_head"],
        "smoke_passed": materialized["smoke_passed"],
        "enforcement_passed": materialized["enforcement_passed"],
        "json": json_path.relative_to(directory).as_posix(),
        "markdown": markdown_path.relative_to(directory).as_posix(),
    }
    _atomic_write_text(pointer_path, json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if isinstance(report, dict):
        report.clear()
        report.update(materialized)
    return {
        "json": json_path.as_posix(),
        "markdown": markdown_path.as_posix(),
        "latest": pointer_path.as_posix(),
        "run_id": str(materialized["run_id"]),
    }
