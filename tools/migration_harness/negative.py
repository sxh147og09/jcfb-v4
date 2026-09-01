"""Negative/refusal case registry and unit-level execution harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from .common import read_json
from .contracts import (
    validate_canonical_latest,
    validate_function_security,
    validate_immutable_mutation,
    validate_market_payload,
    validate_prematch_run,
    validate_production_uniqueness,
    validate_public_projection,
    validate_review_scope,
    validate_role_write,
    validate_tier_a_pair,
    validate_unknown_not_coerced,
)
from .manifest import load_manifest, validate_history_integrity, validate_manifest
from .models import CheckStatus, Issue
from .target import validate_target_descriptor


NEGATIVE_REGISTRY_PATH = "config/migration_harness/v4_negative_case_registry.json"


def load_negative_registry(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / NEGATIVE_REGISTRY_PATH)


def validate_negative_registry(registry: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    cases = registry.get("cases")
    if not isinstance(cases, list) or len(cases) != 22:
        return [Issue("NEGATIVE_CASE_COUNT_INVALID", "BATCH-02 requires exactly 22 negative cases")]
    expected_ids = [f"NEG-{index:02d}" for index in range(1, 23)]
    if [case.get("id") for case in cases] != expected_ids:
        issues.append(Issue("NEGATIVE_CASE_IDS_INVALID", "Negative IDs must be NEG-01 through NEG-22 in order"))
    if [case.get("number") for case in cases] != list(range(1, 23)):
        issues.append(Issue("NEGATIVE_CASE_NUMBERS_INVALID", "Negative case numbers must be 1 through 22 in order"))
    for case in cases:
        if case.get("expected_result") != "REJECTED":
            issues.append(Issue("NEGATIVE_EXPECTATION_INVALID", "Every registered case must expect rejection", str(case.get("id"))))
        if not case.get("evidence_ref"):
            issues.append(Issue("NEGATIVE_EVIDENCE_REF_MISSING", "Every negative case needs an evidence reference", str(case.get("id"))))
    return issues


def _base_target() -> Dict[str, Any]:
    return {
        "descriptor_version": "v4-migration-target-descriptor@1.0.0",
        "target_id": "local-v4-validation",
        "environment": "DISPOSABLE_LOCAL",
        "provider": "LOCAL_POSTGRES",
        "database_identity": {
            "server_name": "local-disposable",
            "database_name": "jcfb_v4_validation",
            "project_or_cluster_ref": "local-cluster-v4",
        },
        "disposable": True,
        "contains_v333_objects": False,
        "contains_production_data": False,
        "credential_env_name": "JCFB_V4_TEST_DATABASE_URL",
        "allow_network": False,
        "connect_permission": "EXPLICITLY_GRANTED",
        "reset_and_teardown_contract": {
            "reset_before_run": True,
            "destroy_after_evidence": True,
            "operator_owned": True,
        },
    }


def _sql_texts(repo_root: Path, manifest) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for entry in manifest.entries:
        path = repo_root / Path(entry.file)
        if path.is_file():
            values[entry.file] = path.read_text(encoding="utf-8")
    return values


def _manifest_missing(repo_root: Path):
    path = repo_root / "database/migrations/v4/0000_manifest.md"
    source = path.read_text(encoding="utf-8")
    current = load_manifest(repo_root)
    return source, _sql_texts(repo_root, current)


def _decision_for_case(number: int, repo_root: Path):
    manifest = load_manifest(repo_root)
    if number == 1:
        text, sql = _manifest_missing(repo_root)
        mutated = "\n".join(line for line in text.splitlines() if not line.startswith("| 0005 |"))
        result = validate_manifest(mutated, sql)
        return (not result.ok, result.issues)
    if number == 2:
        text, sql = _manifest_missing(repo_root)
        row = next(line for line in text.splitlines() if line.startswith("| 0005 |"))
        result = validate_manifest(text + "\n" + row + "\n", sql)
        return (not result.ok, result.issues)
    if number == 3:
        row = {
            "migration_id": "migration@20260901.001",
            "migration_hash": "sha256:" + "0" * 64,
            "status": "APPLIED",
        }
        ok, issues = validate_history_integrity([row], manifest)
        return (not ok, issues)
    if number == 4:
        target = _base_target()
        target.update({"environment": "PRODUCTION", "provider": "PRODUCTION_SUPABASE", "connect_permission": "EXPLICITLY_GRANTED", "allow_network": True})
        result = validate_target_descriptor(target)
        return (not result.ok, result.issues)
    if number == 5:
        target = _base_target()
        target.pop("credential_env_name")
        result = validate_target_descriptor(target)
        return (not result.ok, result.issues)
    if number == 6:
        target = _base_target()
        target["target_id"] = "Invalid Target!"
        result = validate_target_descriptor(target)
        return (not result.ok, result.issues)
    if number == 7:
        target = _base_target()
        target["contains_v333_objects"] = True
        result = validate_target_descriptor(target)
        return (not result.ok, result.issues)
    if number == 8:
        result = validate_market_payload({"market": "spf", "status": "AVAILABLE", "payload": None})
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 9:
        result = validate_market_payload({"market": "total_goals", "status": "UNAVAILABLE", "payload": None, "unavailable_reason": ""})
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 10:
        result = validate_market_payload({"market": "rqspf", "status": "AVAILABLE", "payload": {"home": 1.0}, "handicap_line": None})
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 11:
        result = validate_prematch_run({
            "role": "PRODUCTION",
            "prediction_cutoff_at": "2026-09-01T18:00:00+08:00",
            "kickoff_at": "2026-09-01T19:00:00+08:00",
            "run_at": "2026-09-01T19:01:00+08:00",
        })
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 12:
        result = validate_immutable_mutation({"entity_type": "Frozen Input", "status": "FROZEN", "immutable": True}, "UPDATE")
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 13:
        result = validate_immutable_mutation({"entity_type": "Frozen Prediction", "status": "FROZEN", "immutable": True}, "DELETE")
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 14:
        result = validate_review_scope({"result_match_id": "match-a", "frozen_prediction_match_id": "match-b"})
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 15:
        result = validate_tier_a_pair({
            "production_role": "PRODUCTION",
            "shadow_role": "SHADOW",
            "production_frozen_input_hash": "sha256:" + "1" * 64,
            "shadow_frozen_input_hash": "sha256:" + "2" * 64,
        })
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 16:
        result = validate_tier_a_pair({
            "production_role": "PRODUCTION",
            "shadow_role": "SHADOW",
            "production_frozen_input_hash": "sha256:" + "1" * 64,
            "shadow_frozen_input_hash": "sha256:" + "1" * 64,
            "experiment_member": True,
        })
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 17:
        result = validate_public_projection({"role": "SHADOW", "status": "PUBLISHED"})
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 18:
        rows = [
            {"role": "PRODUCTION", "status": "PRODUCTION", "is_canonical_active": True},
            {"role": "PRODUCTION", "status": "PRODUCTION", "is_canonical_active": True},
        ]
        result = validate_production_uniqueness(rows)
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 19:
        result = validate_function_security({
            "security": "DEFINER",
            "search_path": ["public"],
            "actor_check": False,
            "execute_grants_reviewed": False,
        })
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 20:
        result = validate_role_write("anon", "internal", "INSERT")
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 21:
        result = validate_canonical_latest({
            "business_times": ["2026-09-01T10:00:00+08:00", "2026-09-01T11:00:00+08:00"],
            "canonical_latest_update_at": "2026-09-01T12:00:00+08:00",
            "page_build_at": "2026-09-01T12:00:00+08:00",
            "deploy_at": "2026-09-01T12:00:00+08:00",
        })
        return (result.rejected, [Issue(result.code, result.reason)])
    if number == 22:
        result = validate_unknown_not_coerced({"state": "UNKNOWN", "coerced_value": 0})
        return (result.rejected, [Issue(result.code, result.reason)])
    return (False, [Issue("NEGATIVE_CASE_UNIMPLEMENTED", "Negative case has no evaluator")])


def run_negative_cases(repo_root: Path) -> Dict[str, Any]:
    registry = load_negative_registry(repo_root)
    registry_issues = validate_negative_registry(registry)
    if registry_issues:
        return {
            "status": CheckStatus.FAIL.value,
            "defined_count": len(registry.get("cases", [])),
            "actually_executed": 0,
            "pass_count": 0,
            "fail_count": 1,
            "runtime_pending_count": 0,
            "registry_issues": [issue.to_dict() for issue in registry_issues],
            "cases": [],
        }

    results: List[Dict[str, Any]] = []
    for case in registry["cases"]:
        rejected, issues = _decision_for_case(int(case["number"]), repo_root)
        unit_status = CheckStatus.PASS.value if rejected else CheckStatus.FAIL.value
        results.append({
            "id": case["id"],
            "number": case["number"],
            "name": case["name"],
            "expected_result": case["expected_result"],
            "actual_result": "REJECTED" if rejected else "ACCEPTED",
            "unit_contract_status": unit_status,
            "runtime_status": CheckStatus.RUNTIME_NEGATIVE_TEST_PENDING.value if case["runtime_required"] else CheckStatus.NOT_APPLICABLE.value,
            "runtime_required": bool(case["runtime_required"]),
            "decision_code": issues[0].code if issues else "NO_REJECTION",
            "evidence_ref": case["evidence_ref"],
        })
    pass_count = sum(1 for result in results if result["unit_contract_status"] == CheckStatus.PASS.value)
    fail_count = len(results) - pass_count
    pending_count = sum(1 for result in results if result["runtime_required"])
    return {
        "status": CheckStatus.PASS.value if fail_count == 0 else CheckStatus.FAIL.value,
        "defined_count": len(results),
        "actually_executed": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "runtime_pending_count": pending_count,
        "unit_contract_only": True,
        "runtime_pending_reason": "Database constraint/RLS/trigger/view behavior needs a proven disposable PostgreSQL target",
        "registry_issues": [],
        "cases": results,
    }
