"""Smoke catalog loading and explicit runtime-pending semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .common import read_json
from .models import CheckStatus, Issue


def load_smoke_catalog(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / "config/migration_harness/v4_smoke_test_catalog.json")


def validate_smoke_catalog(catalog: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    cases = catalog.get("cases")
    if not isinstance(cases, list) or len(cases) != 20:
        issues.append(Issue("SMOKE_CASE_COUNT_INVALID", "The V4 smoke catalog must contain exactly 20 cases"))
        return issues
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    expected_ids = [f"SMOKE-{index:02d}" for index in range(1, 21)]
    if ids != expected_ids:
        issues.append(Issue("SMOKE_CASE_IDS_INVALID", "Smoke IDs must be SMOKE-01 through SMOKE-20 in order"))
    for case in cases:
        if not isinstance(case, dict):
            issues.append(Issue("SMOKE_CASE_INVALID", "Smoke case must be an object"))
            continue
        for field in ("id", "source_case", "name", "expected_result", "gates"):
            if field not in case:
                issues.append(Issue("SMOKE_CASE_FIELD_MISSING", f"Smoke case is missing {field}", str(case.get("id"))))
        if not case.get("expected_result"):
            issues.append(Issue("SMOKE_EXPECTATION_MISSING", "Every smoke case needs an expected result", str(case.get("id"))))
    if catalog.get("runtime_required") is not True:
        issues.append(Issue("SMOKE_RUNTIME_BOUNDARY_INVALID", "Smoke catalog must declare runtime_required=true"))
    if catalog.get("runtime_status") != "NOT_EXECUTED_REQUIRES_DISPOSABLE_DB":
        issues.append(Issue("SMOKE_RUNTIME_STATUS_INVALID", "Smoke catalog must remain explicitly runtime-pending"))
    if catalog.get("execution_boundary", {}).get("production_target") != "BLOCKED":
        issues.append(Issue("SMOKE_PRODUCTION_BOUNDARY_INVALID", "Production smoke execution must be hard-blocked"))
    return issues


def runtime_pending_smoke_report(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Return a truthful report when no disposable PostgreSQL target exists."""

    cases = catalog.get("cases", [])
    return {
        "status": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
        "runtime_required": True,
        "actually_executed": 0,
        "passed": 0,
        "failed": 0,
        "pending": len(cases),
        "reason": "No disposable PostgreSQL target or approved catalog capture was supplied",
        "cases": [
            {
                "id": case.get("id"),
                "expected_result": case.get("expected_result"),
                "actual_result": CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value,
                "evidence_ref": f"runtime-pending/{case.get('id')}.json",
            }
            for case in cases
        ],
    }
