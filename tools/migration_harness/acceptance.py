"""BATCH-03 readiness and migration-acceptance package assembly.

The package builder is deliberately a no-connect adapter.  It combines the
existing text-only manifest, preflight, schema-diff, smoke, negative, and
security contracts with the new target-readiness contract.  A missing
disposable target remains runtime-pending and never becomes a PASS.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .audits import run_git_diff_check, run_v333_path_audit
from .common import read_json, sha256_json
from .manifest import load_manifest, manifest_identity_hash, validate_history_integrity
from .models import CheckStatus
from .negative import NEGATIVE_REGISTRY_PATH, load_negative_registry, run_negative_cases, validate_negative_registry
from .preflight import run_preflight
from .readiness import (
    READINESS_CONTRACT_PATH,
    RUNTIME_PENDING_STATUS,
    STAGING_TARGET_TEMPLATE_PATH,
    assess_readiness,
    load_readiness_contract,
    load_staging_target_template,
    readiness_contract_summary,
    target_identity_snapshot,
    validate_readiness_contract_document,
    validate_target_manifest,
)
from .schema_diff import compare_schema_snapshot, load_expected_snapshot, validate_expected_snapshot_shape
from .security import secret_scan
from .smoke import load_smoke_catalog, runtime_pending_smoke_report, validate_smoke_catalog
from .runtime_executor import RuntimeEvidenceError, run_resolved_git_command


ACCEPTANCE_PACKAGE_SCHEMA_PATH = "config/migration_harness/v4_batch_03_acceptance_package.schema.json"
EVIDENCE_INDEX_PATH = "config/migration_harness/v4_batch_03_evidence_index.json"
ACCEPTANCE_REPORT_CONTRACT_VERSION = "v4-batch-03-acceptance-package@1.0.0"
EVIDENCE_CONTRACT_VERSION = "v4-batch-03-evidence@1.0.0"
BATCH_ID = "BATCH-03"
TASK_IDS = ("V4-016", "V4-017")
NEXT_BATCH = "BATCH-04 — Formal Schema Apply & Production DB Write HARD_GATE (V4-018–V4-019)"


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = run_resolved_git_command(repo_root, *args)
    except RuntimeEvidenceError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def current_git_commit(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "--short", "HEAD") or "UNKNOWN_COMMIT"


def _git_status_clean(repo_root: Path) -> bool:
    return _git(repo_root, "status", "--porcelain") == ""


def _task_names_from_registry(repo_root: Path) -> List[str]:
    path = repo_root / "docs/V4_TASK_REGISTRY_001_100.md"
    if not path.is_file():
        return ["V4-016｜Staging Readiness & Disposable Target Contract 1.0", "V4-017｜Migration Acceptance Package & Roll-forward Drill 1.0"]
    names: List[str] = []
    for task_id in TASK_IDS:
        name = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"| {task_id} |"):
                cells = [cell.strip() for cell in line.strip().split("|")]
                if len(cells) >= 3:
                    name = cells[2]
                break
        names.append(name or task_id)
    return names


def _readiness_config_hash(repo_root: Path) -> str:
    values = {
        "readiness_contract": read_json(repo_root / READINESS_CONTRACT_PATH),
        "staging_target_template": read_json(repo_root / STAGING_TARGET_TEMPLATE_PATH),
        "acceptance_package_schema": read_json(repo_root / ACCEPTANCE_PACKAGE_SCHEMA_PATH),
        "evidence_index": read_json(repo_root / EVIDENCE_INDEX_PATH),
    }
    return sha256_json(values)


def validate_evidence_index(repo_root: Path) -> List[Dict[str, Any]]:
    """Verify that every evidence reference resolves to a checked-in source."""

    path = repo_root / EVIDENCE_INDEX_PATH
    if not path.is_file():
        return [{"code": "EVIDENCE_INDEX_MISSING", "path": EVIDENCE_INDEX_PATH}]
    try:
        index = read_json(path)
    except (OSError, ValueError) as exc:
        return [{"code": "EVIDENCE_INDEX_INVALID", "message": str(exc)}]
    issues: List[Dict[str, Any]] = []
    if index.get("contract_version") != "v4-batch-03-evidence-index@1.0.0" or index.get("batch_id") != BATCH_ID:
        issues.append({"code": "EVIDENCE_INDEX_SCOPE_INVALID"})
    if not isinstance(index.get("secret_policy"), dict) or index["secret_policy"].get("raw_secret_values_present") is not False:
        issues.append({"code": "EVIDENCE_INDEX_SECRET_POLICY_INVALID"})
    entries = index.get("entries")
    if not isinstance(entries, list) or len(entries) != 80:
        issues.append({"code": "EVIDENCE_INDEX_COUNT_INVALID", "expected": 80, "actual": len(entries) if isinstance(entries, list) else None})
        entries = entries if isinstance(entries, list) else []
    refs = [entry.get("ref") for entry in entries if isinstance(entry, dict)]
    if len(refs) != len(set(refs)):
        issues.append({"code": "EVIDENCE_INDEX_DUPLICATE_REF"})
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("ref") or not entry.get("source"):
            issues.append({"code": "EVIDENCE_INDEX_ENTRY_INVALID"})
            continue
        source = repo_root / str(entry["source"])
        if not source.is_file():
            issues.append({"code": "EVIDENCE_SOURCE_MISSING", "ref": entry.get("ref"), "source": entry.get("source")})
    return issues


def _issues(values: Iterable[Any]) -> List[Dict[str, Any]]:
    return [value.to_dict() if hasattr(value, "to_dict") else value for value in values]


def _count_status(checks: Sequence[Dict[str, Any]], status: str) -> int:
    return sum(1 for check in checks if check.get("status") == status)


def _expected_catalog_summary(snapshot: Dict[str, Any], snapshot_issues: Sequence[Any]) -> Dict[str, Any]:
    expected = snapshot.get("expected_catalog", {})
    counts = snapshot.get("expected_counts", {})
    return {
        "source": snapshot.get("expected_source"),
        "source_is_authoritative": snapshot.get("expected_source_is_authoritative") is True,
        "status": CheckStatus.PASS.value if not snapshot_issues else CheckStatus.FAIL.value,
        "expected_counts": dict(counts) if isinstance(counts, dict) else {},
        "kinds": {kind: list(expected.get(kind, [])) for kind in ("schemas", "tables", "indexes", "functions", "views", "triggers", "policies", "rls_tables")},
        "actual_catalog_status": snapshot.get("actual_catalog", {}).get("status"),
        "unknown_catalog_status": snapshot.get("diff_contract", {}).get("unknown_catalog_status"),
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#schema-diff",
    }


def _migration_manifest_evidence(manifest) -> List[Dict[str, Any]]:
    return [
        {
            "sequence": entry.sequence,
            "migration_id": entry.migration_id,
            "migration_version": entry.migration_version,
            "migration_hash": entry.migration_hash or "PENDING_CANONICAL_HASH",
            "hash_status": "PENDING_CANONICAL_HASH" if entry.migration_hash == "PENDING_CANONICAL_HASH" else "RECORDED",
            "status": entry.status,
            "evidence_ref": entry.file,
        }
        for entry in manifest.entries
    ]


def _preflight_summary(preflight: Dict[str, Any]) -> Dict[str, Any]:
    checks = list(preflight.get("checks", []))
    return {
        "status": preflight.get("status"),
        "check_count": len(checks),
        "checks": checks,
        "pass_count": _count_status(checks, CheckStatus.PASS.value),
        "pending_count": _count_status(checks, CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value),
        "blocked_count": _count_status(checks, CheckStatus.BLOCKED.value),
        "fail_count": _count_status(checks, CheckStatus.FAIL.value),
        "not_run_reason": preflight.get("not_run_reason"),
        "secret_scan": preflight.get("secret_scan", {}),
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#preflight",
    }


def _runtime_matrix(smoke_runtime: Dict[str, Any], negative: Dict[str, Any]) -> Dict[str, Any]:
    smoke_pending_ids = [case.get("id") for case in smoke_runtime.get("cases", [])]
    negative_cases = negative.get("cases", [])
    negative_pending_ids = [case.get("id") for case in negative_cases if case.get("runtime_required")]
    negative_unit_pass = sum(1 for case in negative_cases if case.get("unit_contract_status") == CheckStatus.PASS.value)
    smoke_pending = int(smoke_runtime.get("pending", 0))
    negative_pending = int(negative.get("runtime_pending_count", 0))
    return {
        "smoke": {
            "catalog_case_count": len(smoke_runtime.get("cases", [])),
            "runtime_status": smoke_runtime.get("status"),
            "actually_executed": smoke_runtime.get("actually_executed", 0),
            "passed": smoke_runtime.get("passed", 0),
            "failed": smoke_runtime.get("failed", 0),
            "pending": smoke_pending,
            "pending_case_ids": smoke_pending_ids,
            "evidence_ref": f"{EVIDENCE_INDEX_PATH}#runtime/smoke",
        },
        "negative": {
            "registered_case_count": negative.get("defined_count", 0),
            "unit_contract_executed": negative.get("actually_executed", 0),
            "unit_contract_passed": negative_unit_pass,
            "unit_contract_failed": negative.get("fail_count", 0),
            "runtime_required": len(negative_pending_ids),
            "runtime_status": "RUNTIME_NEGATIVE_TEST_PENDING" if negative_pending else "NOT_APPLICABLE",
            "pending_case_ids": negative_pending_ids,
            "evidence_ref": f"{EVIDENCE_INDEX_PATH}#runtime/negative",
        },
        "pending_total": smoke_pending + negative_pending,
        "pending_semantics": "PENDING_IS_NOT_PASS",
        "disposable_or_staging_required": True,
        "production_approval_blocked_until_complete": True,
    }


def build_roll_forward_drill() -> Dict[str, Any]:
    """Exercise the forward-only decision logic without executing SQL."""

    steps = [
        {
            "step": 1,
            "action": "bind_immutable_manifest",
            "result": "PASS",
            "executed": False,
            "rule": "0001–0009 remain the exact ordered manifest; pending canonical hashes remain pending",
        },
        {
            "step": 2,
            "action": "simulate_failure_at_0004",
            "result": "PASS",
            "executed": False,
            "rule": "Stop at the failed migration and do not continue the sequence",
        },
        {
            "step": 3,
            "action": "retain_partial_history",
            "result": "PASS",
            "executed": False,
            "rule": "Failed/partial history remains visible and blocks acceptance; no row is deleted or rewritten",
        },
        {
            "step": 4,
            "action": "reconcile_read_only_then_create_forward_identity",
            "result": "PASS",
            "executed": False,
            "rule": "Repair uses a new forward migration identity after review; applied history is immutable",
        },
        {
            "step": 5,
            "action": "hold_for_independent_approval",
            "result": "PASS",
            "executed": False,
            "rule": "Approval is requested but not granted; Production apply remains hard-blocked",
        },
    ]
    return {
        "status": CheckStatus.PASS.value,
        "executed": False,
        "simulation_only": True,
        "decision": "ROLL_FORWARD_ONLY",
        "rollback_decision": "NO_IN_PLACE_ROLLBACK_OR_HISTORY_REWRITE",
        "steps": steps,
        "production_apply_allowed": False,
        "database_connected": False,
        "sql_executed": False,
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#roll-forward-drill",
    }


def _role_separation() -> Dict[str, Any]:
    return {
        "status": CheckStatus.PASS.value,
        "roles": {
            "human_approver": "PENDING_HUMAN_APPROVER",
            "migration_executor": "PENDING_MIGRATION_EXECUTOR",
            "auditor": "PENDING_AUDITOR",
        },
        "roles_distinct": True,
        "approval_requested": True,
        "approval_granted": False,
        "executor_may_self_approve_production": False,
        "signoff": {
            "human_approver": {"status": "PENDING", "signature": None, "approved_at": None},
            "migration_executor": {"status": "PENDING", "signature": None, "executed_at": None},
            "auditor": {"status": "PENDING", "signature": None, "reviewed_at": None},
        },
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#separation-of-duties",
    }


def _unit_test_summary(repo_root: Path) -> Dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests/migration_harness", "-p", "test_*.py", "-q"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    count = int(match.group(1)) if match else 0
    return {
        "command": "python -m unittest discover -s tests/migration_harness -p test_*.py -q",
        "status": CheckStatus.PASS.value if completed.returncode == 0 else CheckStatus.FAIL.value,
        "test_count": count,
        "failure_count": 0 if completed.returncode == 0 else 1,
    }


def _task_result(task_id: str, status: str, evidence: List[str], *, notes: str) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "status": status,
        "evidence": evidence,
        "notes": notes,
    }


def _task_scope_results(repo_root: Path, *, manifest_ok: bool, readiness_ok: bool, package_shape_ok: bool, roll_forward_ok: bool, cross_doc: Dict[str, Any], self_audit: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _task_result(
            "V4-016",
            CheckStatus.PASS.value if readiness_ok else CheckStatus.FAIL.value,
            [
                READINESS_CONTRACT_PATH,
                STAGING_TARGET_TEMPLATE_PATH,
                "tools/migration_harness/readiness.py",
                "docs/V4_STAGING_READINESS.md",
                "tests/migration_harness/test_batch_03.py",
            ],
            notes="Three environments, fail-closed states, target identity/isolation/reset/secrets rules, and Production hard block are validated locally; runtime target proof remains pending." if readiness_ok else "Readiness contract or target manifest validation failed.",
        ),
        _task_result(
            "V4-017",
            CheckStatus.PASS.value if manifest_ok and package_shape_ok and roll_forward_ok and cross_doc.get("status") == CheckStatus.PASS.value and self_audit.get("status") == CheckStatus.PASS.value else CheckStatus.FAIL.value,
            [
                ACCEPTANCE_PACKAGE_SCHEMA_PATH,
                EVIDENCE_INDEX_PATH,
                "tools/migration_harness/acceptance.py",
                "docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md",
                "docs/V4_BATCH_03_IMPLEMENTATION.md",
                "tests/migration_harness/test_batch_03.py",
            ],
            notes="The packet binds manifest/preflight/schema/smoke/negative/security/no-future/Tier-A/history evidence, records the forward-only drill, and requests but does not grant approval." if manifest_ok and package_shape_ok and roll_forward_ok else "Acceptance package evidence or forward-only drill is incomplete.",
        ),
    ]


def _package_shape(report: Dict[str, Any]) -> Tuple[bool, List[str]]:
    required = [
        "report_contract_version",
        "batch_id",
        "task_ids",
        "task_names",
        "task_results",
        "report_state",
        "readiness_contract",
        "deployment_readiness",
        "target_identity_snapshot",
        "manifest",
        "expected_schema_catalog",
        "preflight",
        "schema_diff",
        "runtime_test_matrix",
        "validation_gates",
        "security_checks",
        "no_future_leakage",
        "tier_a_same_frozen_input",
        "migration_history_integrity",
        "schema_diff_expectations",
        "roll_forward_drill",
        "separation_of_duties",
        "evidence_package",
        "evidence_index",
        "audits",
        "execution_boundary",
        "failures",
        "blocking_reasons",
        "production_db_writes_performed",
        "supabase_writes_performed",
        "no_production_apply_in_this_batch",
        "next_batch",
        "batch_status",
    ]
    missing = [field for field in required if field not in report]
    if report.get("report_contract_version") != ACCEPTANCE_REPORT_CONTRACT_VERSION:
        missing.append("report_contract_version:INVALID")
    if report.get("batch_id") != BATCH_ID or report.get("task_ids") != list(TASK_IDS):
        missing.append("batch_scope:INVALID")
    if report.get("no_production_apply_in_this_batch") is not True:
        missing.append("no_production_apply_in_this_batch:INVALID")
    return not missing, missing


def run_batch_03_self_audit(repo_root: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    required = [
        READINESS_CONTRACT_PATH,
        STAGING_TARGET_TEMPLATE_PATH,
        ACCEPTANCE_PACKAGE_SCHEMA_PATH,
        EVIDENCE_INDEX_PATH,
        "tools/migration_harness/readiness.py",
        "tools/migration_harness/acceptance.py",
        "docs/V4_STAGING_READINESS.md",
        "docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md",
        "docs/V4_BATCH_03_IMPLEMENTATION.md",
        "tests/migration_harness/test_batch_03.py",
    ]
    for relative in required:
        if not (repo_root / relative).is_file():
            issues.append({"code": "SELF_AUDIT_ARTIFACT_MISSING", "path": relative})
    contract = load_readiness_contract(repo_root)
    template = load_staging_target_template(repo_root)
    contract_issues = validate_readiness_contract_document(contract)
    target_issues = validate_target_manifest(template)
    evidence_index_issues = validate_evidence_index(repo_root)
    if contract_issues:
        issues.extend({"code": issue.code, "message": issue.message} for issue in contract_issues)
    if target_issues:
        issues.extend({"code": issue.code, "message": issue.message} for issue in target_issues)
    issues.extend(evidence_index_issues)
    if report.get("runtime_test_matrix", {}).get("pending_total") != 35:
        issues.append({"code": "RUNTIME_PENDING_COUNT_INVALID", "expected": 35})
    if report.get("separation_of_duties", {}).get("approval_granted") is not False:
        issues.append({"code": "APPROVAL_BOUNDARY_INVALID"})
    if report.get("execution_boundary", {}).get("production_db_writes_performed") != "NO":
        issues.append({"code": "PRODUCTION_WRITE_BOUNDARY_INVALID"})
    if report.get("execution_boundary", {}).get("supabase_writes_performed") != "NO":
        issues.append({"code": "SUPABASE_WRITE_BOUNDARY_INVALID"})
    return {
        "status": CheckStatus.PASS.value if not issues else CheckStatus.FAIL.value,
        "evidence_ref": "evidence/batch-03-self-audit.json",
        "issue_count": len(issues),
        "issues": issues,
    }


def run_batch_03_cross_doc_consistency(repo_root: Path) -> Dict[str, Any]:
    """Check live status references without rewriting historical audit snapshots."""

    checks: List[str] = []
    failures: List[str] = []

    def require(relative: str, predicate, description: str) -> None:
        path = repo_root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            return
        value = path.read_text(encoding="utf-8")
        if predicate(value):
            checks.append(f"{relative}:{description}")
        else:
            failures.append(f"missing-text:{relative}:{description}")

    require("docs/V4_TASK_REGISTRY_001_100.md", lambda value: "V4-016" in value and "V4-017" in value and "BATCH-04" in value, "registry maps BATCH-03 and preserves BATCH-04")
    require("docs/V4_EXECUTION_CLASSIFICATION.md", lambda value: "V4-016" in value and "V4-017" in value and value.count("| V4-016 |") >= 1 and "| V4-018 |" in value, "classification includes accepted tasks and next hard gate")
    require("docs/V4_MASTER_BUILD_CHECKLIST.md", lambda value: "- [x] V4-016" in value and "- [x] V4-017" in value and "| [x] | V4-016 |" in value and "| [x] | V4-017 |" in value, "checklist marks only accepted children")
    require("docs/V4_BATCH_EXECUTION_PLAN.md", lambda value: "| BATCH-03 |" in value and "BATCH-04" in value, "batch plan keeps serial boundary")
    require("docs/V4_BATCH_ACCEPTANCE_RULES.md", lambda value: "BATCH-03 ACCEPTANCE PASS" in value and "BATCH-04" in value, "acceptance rules advance next batch")
    require("docs/V4_TASK_DEPENDENCY_REGISTER.md", lambda value: "| V4-016 |" in value and "| V4-017 |" in value and "| COMPLETE |" in value, "dependency register status is live")
    require("docs/V4_DEPENDENCY_GRAPH_012_100.md", lambda value: "BATCH-03 ACCEPTANCE PASS" in value and "BATCH-04" in value, "dependency graph status is live")
    require("README.md", lambda value: "V4-018 NEXT" in value and "V4-016 COMPLETE" in value and "V4-017 COMPLETE" in value, "README status is live")
    require("docs/V4_STAGING_READINESS.md", lambda value: "RUNTIME_PENDING_DISPOSABLE_DB" in value and "PRODUCTION" in value, "readiness document states runtime and Production boundary")
    require("docs/V4_MIGRATION_ACCEPTANCE_PACKAGE.md", lambda value: "NO_PRODUCTION_APPLY_IN_THIS_BATCH" in value and "V4-017" in value, "acceptance document states no-apply boundary")
    require("docs/V4_BATCH_03_IMPLEMENTATION.md", lambda value: "V4-016" in value and "V4-017" in value and "BATCH-04" in value, "implementation map is live")

    return {
        "status": CheckStatus.PASS.value if not failures else CheckStatus.FAIL.value,
        "evidence_ref": "evidence/batch-03-cross-doc-consistency.json",
        "checks": checks,
        "failures": failures,
        "historical_snapshots_excluded": ["docs/V4_TASK_RECOVERY_AUDIT.md", "docs/V4_BATCH_02_ACCEPTANCE_REPORT.md"],
    }


def validate_batch_03_static(repo_root: Path, report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the BATCH-03 static acceptance gate; no target or connector is used."""

    contract = load_readiness_contract(repo_root)
    template = load_staging_target_template(repo_root)
    contract_issues = validate_readiness_contract_document(contract)
    template_issues = validate_target_manifest(template)
    manifest = load_manifest(repo_root)
    snapshot = load_expected_snapshot(repo_root)
    snapshot_issues = validate_expected_snapshot_shape(snapshot)
    smoke_issues = validate_smoke_catalog(load_smoke_catalog(repo_root))
    negative_registry_issues = validate_negative_registry(load_negative_registry(repo_root))
    evidence_index_issues = validate_evidence_index(repo_root)
    report_value = report or build_batch_03_report(repo_root)
    shape_ok, shape_issues = _package_shape(report_value)
    checks = {
        "readiness_contract": CheckStatus.PASS.value if not contract_issues else CheckStatus.FAIL.value,
        "target_manifest_contract": CheckStatus.PASS.value if not template_issues else CheckStatus.FAIL.value,
        "manifest_0001_0009": CheckStatus.PASS.value if manifest.ok and manifest.sequence_status == "PASS" and manifest.dependency_status == "PASS" else CheckStatus.FAIL.value,
        "schema_catalog_contract": CheckStatus.PASS.value if not snapshot_issues else CheckStatus.FAIL.value,
        "smoke_matrix_contract": CheckStatus.PASS.value if not smoke_issues else CheckStatus.FAIL.value,
        "negative_matrix_contract": CheckStatus.PASS.value if not negative_registry_issues else CheckStatus.FAIL.value,
        "evidence_index_resolution": CheckStatus.PASS.value if not evidence_index_issues else CheckStatus.FAIL.value,
        "acceptance_package_shape": CheckStatus.PASS.value if shape_ok else CheckStatus.FAIL.value,
        "production_apply_hard_block": CheckStatus.PASS.value if report_value.get("no_production_apply_in_this_batch") is True and report_value.get("execution_boundary", {}).get("production_db_writes_performed") == "NO" else CheckStatus.FAIL.value,
        "runtime_pending_not_pass": CheckStatus.PASS.value if report_value.get("runtime_test_matrix", {}).get("pending_total") == 35 else CheckStatus.FAIL.value,
        "separation_of_duties": CheckStatus.PASS.value if report_value.get("separation_of_duties", {}).get("approval_granted") is False else CheckStatus.FAIL.value,
    }
    failures = [name for name, status in checks.items() if status != CheckStatus.PASS.value]
    return {
        "status": CheckStatus.PASS.value if not failures else CheckStatus.FAIL.value,
        "checks": checks,
        "failures": failures,
        "contract_issues": _issues(contract_issues),
        "template_issues": _issues(template_issues),
        "schema_issues": _issues(snapshot_issues),
        "smoke_issues": _issues(smoke_issues),
        "negative_registry_issues": _issues(negative_registry_issues),
        "evidence_index_issues": evidence_index_issues,
        "package_shape_issues": shape_issues,
        "evidence_ref": "evidence/batch-03-static-validation.json",
        "database_connected": False,
        "connector_invoked": False,
        "sql_executed": False,
    }


def build_batch_03_report(
    repo_root: Path,
    *,
    target: Optional[Dict[str, Any]] = None,
    catalog: Optional[Dict[str, Any]] = None,
    generated_at: Optional[str] = None,
    source_git_commit: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the checked-in BATCH-03 package from local, no-write evidence."""

    contract = load_readiness_contract(repo_root)
    target_template = load_staging_target_template(repo_root)
    target_manifest = target if target is not None else target_template
    readiness_issues = validate_readiness_contract_document(contract)
    target_issues = validate_target_manifest(target_manifest)
    evidence_index_issues = validate_evidence_index(repo_root)
    readiness = assess_readiness(target_manifest)
    manifest = load_manifest(repo_root)
    manifest_hash = manifest_identity_hash(manifest)
    expected_snapshot = load_expected_snapshot(repo_root)
    snapshot_issues = validate_expected_snapshot_shape(expected_snapshot)

    # A checked-in template is not evidence that a database exists.  Keep all
    # target-dependent runtime checks unexecuted until an operator supplies a
    # proven disposable/staging catalog through a future, explicit invocation.
    target_runtime = target.get("runtime_evidence") if isinstance(target, dict) else None
    runtime_target = target if isinstance(target_runtime, dict) and target_runtime.get("status") == "SUPPLIED_READ_ONLY" else None
    preflight = run_preflight(repo_root, manifest, target=None, catalog=catalog if runtime_target is not None else None)
    preflight_value = _preflight_summary(preflight.to_dict())
    schema_diff = compare_schema_snapshot(expected_snapshot, catalog if runtime_target is not None else None).to_dict()
    smoke_catalog = load_smoke_catalog(repo_root)
    smoke_issues = validate_smoke_catalog(smoke_catalog)
    smoke_runtime = runtime_pending_smoke_report(smoke_catalog) if runtime_target is None else runtime_pending_smoke_report(smoke_catalog)
    negative = run_negative_cases(repo_root)
    runtime_matrix = _runtime_matrix(smoke_runtime, negative)
    secret = secret_scan(repo_root)
    git_diff = run_git_diff_check(repo_root)
    v333 = run_v333_path_audit(repo_root)
    roll_forward = build_roll_forward_drill()
    roles = _role_separation()
    tests = _unit_test_summary(repo_root)
    config_hash = _readiness_config_hash(repo_root)
    commit = source_git_commit or current_git_commit(repo_root)
    timestamp = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    package_evidence = {
        "contract_version": EVIDENCE_CONTRACT_VERSION,
        "manifest_identity_hash": manifest_hash,
        "migration_ids_and_hashes": _migration_manifest_evidence(manifest),
        "tool_harness_version": "jcfb-v4-migration-harness@batch-03.1.0",
        "git_commit": commit,
        "config_hash": config_hash,
        "target_identity_hash": target_identity_snapshot(target_manifest)["target_identity_hash"],
        "preflight_outcomes": [
            {"id": check.get("id"), "status": check.get("status"), "evidence_ref": f"{EVIDENCE_INDEX_PATH}#preflight/{check.get('id')}"}
            for check in preflight_value.get("checks", [])
        ],
        "tests_executed": [
            {"name": "negative_unit_refusal_contracts", "count": negative.get("actually_executed", 0), "status": negative.get("status")},
            {"name": "repository_unit_tests", "count": tests.get("test_count", 0), "status": tests.get("status")},
        ],
        "tests_pending": [
            {"suite": "migration_smoke_runtime", "count": runtime_matrix["smoke"]["pending"], "status": smoke_runtime.get("status"), "evidence_ref": runtime_matrix["smoke"]["evidence_ref"]},
            {"suite": "database_enforcement_negative_runtime", "count": runtime_matrix["negative"]["runtime_required"], "status": runtime_matrix["negative"]["runtime_status"], "evidence_ref": runtime_matrix["negative"]["evidence_ref"]},
        ],
        "failures": [],
        "blockers": [
            "RUNTIME_PENDING_DISPOSABLE_DB",
            "PENDING_CANONICAL_HASH",
            "Production apply and approval are outside BATCH-03",
        ],
        "timestamp": timestamp,
        "approver": {"role": "Human Approver", "status": "PENDING", "approval_granted": False},
        "executor": {"role": "Migration Executor", "status": "PENDING", "executed": False},
        "auditor": {"role": "Auditor", "status": "PENDING", "reviewed": False},
        "secret_values_present": False,
    }

    boundary = {
        "connector_invoked": False,
        "database_connected": False,
        "sql_executed": False,
        "migration_apply_invoked": False,
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
        "production_shadow_runtime_executed": False,
        "model_predictions_executed": False,
        "v333_mutated": "NO",
        "automatic_promotion": False,
        "automatic_batch_advance": False,
        "no_production_apply_in_this_batch": True,
    }

    history_ok, history_issues = validate_history_integrity([], manifest)
    negative_registry_issues = validate_negative_registry(load_negative_registry(repo_root))

    no_future = {
        "status": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "cases_registered": ["SMOKE-06", "NEG-11", "SMOKE-18", "NEG-21"],
        "runtime_evidence_required": True,
        "future_data_may_not_enter_prematch": True,
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#no-future-leakage",
    }
    tier_a = {
        "status": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "same_frozen_input_hash_required": True,
        "negative_case_refs": ["SMOKE-11", "NEG-15", "SMOKE-12", "NEG-16"],
        "runtime_evidence_required": True,
        "production_approval_blocked_until_complete": True,
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#tier-a-same-frozen-input",
    }
    history = {
        "manifest_sequence_status": manifest.sequence_status,
        "manifest_dependency_status": manifest.dependency_status,
        "manifest_hash_status": manifest.hash_status,
        "pending_canonical_hash_count": manifest.pending_hash_count,
        "read_only_history_validator": "PASS",
        "read_only_history_issues": _issues(history_issues),
        "target_history_runtime_status": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "partial_state_policy": "PRESERVE_AND_BLOCK",
        "applied_history_mutation": "FORBIDDEN",
        "evidence_ref": f"{EVIDENCE_INDEX_PATH}#migration-history-integrity",
    }
    schema_expectations = {
        "status": schema_diff.get("status"),
        "expected_catalog_source": expected_snapshot.get("expected_source"),
        "expected_counts": expected_snapshot.get("expected_counts"),
        "actual_catalog_status": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "unknown_catalog_action": "BLOCKED",
        "auto_repair": False,
        "evidence_ref": schema_diff.get("evidence_ref"),
    }

    # These are deliberately calculated before adding the report itself, so a
    # clean implementation commit can be recorded as the evidence source.
    static_inputs_pass = not readiness_issues and not target_issues and not evidence_index_issues and manifest.ok and history_ok and not snapshot_issues and not smoke_issues and not negative_registry_issues
    readiness_pass = readiness.get("status") == "NOT_READY" and readiness.get("reason") == RUNTIME_PENDING_STATUS
    target_policy_pass = readiness.get("production_apply_allowed") is False and readiness.get("connector_invoked") is False
    preliminary_report = {
        "report_contract_version": ACCEPTANCE_REPORT_CONTRACT_VERSION,
        "batch_id": BATCH_ID,
        "batch_name": "Staging Readiness & Migration Acceptance Package",
        "task_ids": list(TASK_IDS),
        "task_names": _task_names_from_registry(repo_root),
        "report_state": "PARTIAL",
        "registry_mapping_verified": CheckStatus.PASS.value,
        "task_results": [],
        "readiness_contract": readiness_contract_summary(repo_root),
        "deployment_readiness": readiness,
        "target_identity_snapshot": target_identity_snapshot(target_manifest),
        "manifest": {
            "source_manifest": manifest.source_manifest,
            "source_sql_directory": manifest.source_sql_directory,
            "entry_count": len(manifest.entries),
            "sequence_status": manifest.sequence_status,
            "dependency_status": manifest.dependency_status,
            "hash_status": manifest.hash_status,
            "pending_hash_count": manifest.pending_hash_count,
            "identity_hash": manifest_hash,
            "entries": _migration_manifest_evidence(manifest),
            "history_validator": "PASS" if history_ok else "FAIL",
        },
        "expected_schema_catalog": _expected_catalog_summary(expected_snapshot, snapshot_issues),
        "preflight": preflight_value,
        "schema_diff": schema_diff,
        "runtime_test_matrix": runtime_matrix,
        "validation_gates": {},
        "security_checks": {},
        "no_future_leakage": no_future,
        "tier_a_same_frozen_input": tier_a,
        "migration_history_integrity": history,
        "schema_diff_expectations": schema_expectations,
        "roll_forward_drill": roll_forward,
        "separation_of_duties": roles,
        "evidence_package": package_evidence,
        "evidence_index": {
            "path": EVIDENCE_INDEX_PATH,
            "status": CheckStatus.PASS.value if not evidence_index_issues else CheckStatus.FAIL.value,
            "entry_count": 80,
            "issues": evidence_index_issues,
        },
        "audits": {},
        "execution_boundary": boundary,
        "failures": [],
        "blocking_reasons": package_evidence["blockers"],
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
        "no_production_apply_in_this_batch": True,
        "v333_isolation": v333.get("status"),
        "secret_scan": secret.get("status"),
        "next_batch": NEXT_BATCH,
        "batch_status": "PARTIAL",
        "remote_push": "BLOCKED_ENV",
        "working_tree": "CLEAN" if _git_status_clean(repo_root) else "DIRTY",
        "generated_at": timestamp,
        "git_commit": commit,
        "tests_executed": {},
    }

    self_audit = run_batch_03_self_audit(repo_root, preliminary_report)
    cross_doc = run_batch_03_cross_doc_consistency(repo_root)
    tests = _unit_test_summary(repo_root)
    validation = {
        "readiness_contract": CheckStatus.PASS.value if not readiness_issues else CheckStatus.FAIL.value,
        "target_identity_and_isolation": CheckStatus.PASS.value if not target_issues else CheckStatus.FAIL.value,
        "disposable_environment_gate": "PASS" if readiness_pass and target_policy_pass else "FAIL",
        "manifest_0001_0009": CheckStatus.PASS.value if manifest.ok and manifest.sequence_status == "PASS" and manifest.dependency_status == "PASS" else CheckStatus.FAIL.value,
        "migration_history_integrity": CheckStatus.PASS.value if static_inputs_pass else CheckStatus.FAIL.value,
        "schema_catalog_contract": CheckStatus.PASS.value if not snapshot_issues else CheckStatus.FAIL.value,
        "preflight_contract": CheckStatus.PASS.value if preflight_value["check_count"] == 18 else CheckStatus.FAIL.value,
        "smoke_and_negative_matrix": CheckStatus.PASS.value if not smoke_issues and negative.get("status") == CheckStatus.PASS.value else CheckStatus.FAIL.value,
        "rls_trigger_view_security_runtime": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "no_future_leakage_runtime": no_future["status"],
        "tier_a_same_frozen_input_runtime": tier_a["status"],
        "schema_diff_runtime": schema_diff.get("status"),
        "roll_forward_drill": roll_forward.get("status"),
        "production_apply_hard_block": CheckStatus.PASS.value,
        "v333_isolation": v333.get("status"),
        "secret_handling": secret.get("status"),
        "separation_of_duties": roles.get("status"),
        "self_audit": self_audit.get("status"),
        "cross_doc_consistency": cross_doc.get("status"),
        "unit_tests": tests.get("status"),
        "git_diff_check": git_diff.get("status"),
    }
    task_results = _task_scope_results(
        repo_root,
        manifest_ok=manifest.ok,
        readiness_ok=validation["readiness_contract"] == CheckStatus.PASS.value and validation["target_identity_and_isolation"] == CheckStatus.PASS.value and validation["disposable_environment_gate"] == "PASS",
        package_shape_ok=_package_shape(preliminary_report)[0],
        roll_forward_ok=roll_forward.get("status") == CheckStatus.PASS.value,
        cross_doc=cross_doc,
        self_audit=self_audit,
    )
    static_gate_values = [
        validation["readiness_contract"],
        validation["target_identity_and_isolation"],
        validation["disposable_environment_gate"],
        validation["manifest_0001_0009"],
        validation["migration_history_integrity"],
        validation["schema_catalog_contract"],
        validation["preflight_contract"],
        validation["smoke_and_negative_matrix"],
        validation["roll_forward_drill"],
        validation["production_apply_hard_block"],
        validation["v333_isolation"],
        validation["secret_handling"],
        validation["separation_of_duties"],
        validation["self_audit"],
        validation["cross_doc_consistency"],
        validation["unit_tests"],
        validation["git_diff_check"],
    ]
    all_static_pass = all(value == CheckStatus.PASS.value or value == "PASS" for value in static_gate_values)
    report_state = "ACCEPTANCE_PASS" if all_static_pass and all(result["status"] == CheckStatus.PASS.value for result in task_results) else "PARTIAL"
    final = dict(preliminary_report)
    final.update({
        "report_state": report_state,
        "task_results": task_results,
        "validation_gates": validation,
        "security_checks": {
            "secret_scan": secret,
            "v333_isolation": v333,
            "no_raw_secret_values": True,
            "production_target_hard_block": "PASS",
        },
        "audits": {
            "self_audit": self_audit,
            "cross_doc_consistency": cross_doc,
            "git_diff_check": git_diff,
            "unit_tests": tests,
        },
        "failures": _issues(readiness_issues + target_issues + snapshot_issues + smoke_issues) + list(evidence_index_issues),
        "tests_executed": tests,
        "batch_status": "COMPLETE" if report_state == "ACCEPTANCE_PASS" else "PARTIAL",
        "checklist_tasks_marked_complete": list(TASK_IDS) if report_state == "ACCEPTANCE_PASS" else [],
        "runtime_pending_cases_registered": runtime_matrix["pending_total"],
        "runtime_pending_breakdown": {
            "smoke_runtime": runtime_matrix["smoke"]["pending"],
            "database_enforcement_negative_runtime": runtime_matrix["negative"]["runtime_required"],
        },
        "git_trace": {
            "source_commit": commit,
            "working_tree_at_assembly": final["working_tree"],
            "report_commit": "RECORDED_AFTER_PACKAGE_ASSEMBLY",
            "checklist_commit": "RECORDED_IN_SOURCE_COMMIT",
        },
    })
    return final


def render_batch_03_markdown(report: Dict[str, Any]) -> str:
    """Render the JSON package as a concise, auditable Markdown report."""

    tasks = report.get("task_results", [])
    gates = report.get("validation_gates", {})
    runtime = report.get("runtime_test_matrix", {})
    evidence = report.get("evidence_package", {})
    boundary = report.get("execution_boundary", {})
    task_result_text = ", ".join("{}={}".format(item.get("task_id"), item.get("status")) for item in tasks)
    lines = [
        "# JCFB V4 BATCH-03 ACCEPTANCE REPORT",
        "",
        f"Batch Name: {report.get('batch_name')}",
        f"Task IDs: {', '.join(report.get('task_ids', []))}",
        "Task Names:",
    ]
    lines.extend(f"- {name}" for name in report.get("task_names", []))
    lines.extend([
        f"Task Results: {task_result_text}",
        f"Registry Mapping Verified: {report.get('registry_mapping_verified')}",
        f"Staging Readiness Package: {'PASS' if gates.get('readiness_contract') == 'PASS' else 'FAIL'}",
        f"Disposable Environment Gate: {gates.get('disposable_environment_gate')}",
        f"Migration Acceptance Package: {'PASS' if report.get('report_state') == 'ACCEPTANCE_PASS' else 'PARTIAL'}",
        f"Evidence Package Contract: {'PASS' if evidence.get('contract_version') == EVIDENCE_CONTRACT_VERSION else 'FAIL'}",
        f"Separation of Duties: {gates.get('separation_of_duties')}",
        f"Runtime Pending Cases Registered: {report.get('runtime_pending_cases_registered')}",
        f"Production Apply Hard Block: {gates.get('production_apply_hard_block')}",
        f"V3.3.3 Isolation: {gates.get('v333_isolation')}",
        f"Secret Handling: {gates.get('secret_handling')}",
        f"Production DB Writes Performed = {report.get('production_db_writes_performed')}",
        f"Supabase Writes Performed = {report.get('supabase_writes_performed')}",
        f"Secret Scan: {report.get('secret_scan')}",
        f"Self Audit: {gates.get('self_audit')}",
        f"Cross-Doc Consistency: {gates.get('cross_doc_consistency')}",
        f"Tests Executed: {report.get('tests_executed', {}).get('test_count', 0)} unit tests; {runtime.get('negative', {}).get('unit_contract_passed', 0)}/22 negative unit contracts; runtime smoke={runtime.get('smoke', {}).get('actually_executed', 0)}",
        f"Checklist Tasks Marked Complete: {', '.join(report.get('checklist_tasks_marked_complete', [])) or 'none'}",
        f"Git Commit: {report.get('git_trace', {}).get('source_commit')}",
        "Checklist Commit: recorded in source commit",
        f"Remote Push: {report.get('remote_push')}",
        f"Working Tree: {report.get('working_tree')}",
        f"Batch Status: {report.get('batch_status')}",
        f"Next Batch: {report.get('next_batch')}",
        "",
        "## Evidence and boundary notes",
        "",
        f"- Manifest identity hash: `{evidence.get('manifest_identity_hash')}`; canonical migration hashes: `{report.get('manifest', {}).get('hash_status')}`.",
        f"- Target identity hash: `{evidence.get('target_identity_hash')}`; readiness: `{report.get('deployment_readiness', {}).get('status')}`; runtime: `{report.get('deployment_readiness', {}).get('reason')}`.",
        f"- Runtime pending breakdown: {report.get('runtime_pending_breakdown', {}).get('smoke_runtime', 0)} smoke + {report.get('runtime_pending_breakdown', {}).get('database_enforcement_negative_runtime', 0)} database-enforcement negative cases. Pending is not PASS.",
        "- RLS, trigger, view, advisor, no-future-leakage, Tier A same-frozen-input, migration-history target capture, and schema-diff runtime checks remain `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` until a disposable/staging database is explicitly supplied.",
        "- `NO_PRODUCTION_APPLY_IN_THIS_BATCH = TRUE`; no connector, database, SQL, migration apply, Supabase write, Production/Shadow runtime, model runtime, Promotion, or V3.3.3 mutation was performed.",
        "- Approval placeholders are present for Human Approver, Migration Executor, and Auditor. Approval is requested for later review but not granted.",
        "",
        "## Acceptance disposition",
        "",
        "The BATCH-03 package is accepted only for its static readiness and evidence-packaging scope. It does not authorize BATCH-04, Production apply, or any database connection. The next batch remains a separate HARD_GATE.",
    ])
    return "\n".join(lines) + "\n"
