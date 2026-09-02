"""Runtime validation case discovery and adapter wiring.

The existing smoke catalog defines 20 scenarios.  The existing negative-case
registry defines 15 database-required enforcement scenarios.  This module binds
both registries to a single adapter interface without claiming that any case
has run.  A real PostgreSQL adapter may implement the named hooks; an absent
hook is reported as pending rather than treated as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol

from .common import read_json


SMOKE_CATALOG_RELATIVE = "config/migration_harness/v4_smoke_test_catalog.json"
NEGATIVE_REGISTRY_RELATIVE = "config/migration_harness/v4_negative_case_registry.json"
RUNTIME_CASE_PENDING = "RUNTIME_CASE_HOOK_PENDING"


@dataclass(frozen=True)
class RuntimeCaseBinding:
    case_id: str
    number: int
    kind: str
    name: str
    expected_result: str
    caller_roles: List[str]
    hook_name: str
    source_ref: str
    runtime_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "number": self.number,
            "kind": self.kind,
            "name": self.name,
            "expected_result": self.expected_result,
            "caller_roles": list(self.caller_roles),
            "hook_name": self.hook_name,
            "source_ref": self.source_ref,
            "runtime_required": self.runtime_required,
        }


class RuntimeCaseAdapter(Protocol):
    def run_case(self, binding: RuntimeCaseBinding) -> Mapping[str, Any]:
        ...


def _hook_name(kind: str, case_id: str, name: str) -> str:
    normalized = "_".join(part for part in name.lower().replace("/", " ").split() if part)
    return f"{kind.lower()}_{case_id.lower().replace('-', '_')}_{normalized}"


def load_runtime_case_bindings(repo_root: Path) -> Dict[str, List[RuntimeCaseBinding]]:
    smoke = read_json(repo_root / SMOKE_CATALOG_RELATIVE)
    negative = read_json(repo_root / NEGATIVE_REGISTRY_RELATIVE)
    smoke_cases = smoke.get("cases", []) if isinstance(smoke, dict) else []
    negative_cases = negative.get("cases", []) if isinstance(negative, dict) else []
    smoke_bindings = [
        RuntimeCaseBinding(
            case_id=str(case.get("id")),
            number=int(case.get("source_case", index + 1)),
            kind="SMOKE",
            name=str(case.get("name")),
            expected_result=str(case.get("expected_result")),
            caller_roles=[str(item) for item in case.get("caller_roles", [])],
            hook_name=_hook_name("smoke", str(case.get("id")), str(case.get("name"))),
            source_ref=f"{SMOKE_CATALOG_RELATIVE}#{case.get('id')}",
        )
        for index, case in enumerate(smoke_cases)
        if isinstance(case, dict)
    ]
    enforcement_bindings = [
        RuntimeCaseBinding(
            case_id=str(case.get("id")),
            number=int(case.get("number", index + 1)),
            kind="ENFORCEMENT",
            name=str(case.get("name")),
            expected_result=str(case.get("expected_result")),
            caller_roles=[],
            hook_name=_hook_name("enforcement", str(case.get("id")), str(case.get("name"))),
            source_ref=f"{NEGATIVE_REGISTRY_RELATIVE}#{case.get('id')}",
        )
        for index, case in enumerate(negative_cases)
        if isinstance(case, dict) and case.get("runtime_required") is True
    ]
    return {"smoke": smoke_bindings, "enforcement": enforcement_bindings}


def validate_runtime_case_wiring(repo_root: Path) -> Dict[str, Any]:
    bindings = load_runtime_case_bindings(repo_root)
    smoke = bindings["smoke"]
    enforcement = bindings["enforcement"]
    issues: List[str] = []
    expected_smoke = [f"SMOKE-{index:02d}" for index in range(1, 21)]
    expected_enforcement = [f"NEG-{index:02d}" for index in range(8, 23)]
    if [item.case_id for item in smoke] != expected_smoke:
        issues.append("SMOKE_CASE_BINDING_ORDER_INVALID")
    if [item.case_id for item in enforcement] != expected_enforcement:
        issues.append("ENFORCEMENT_CASE_BINDING_ORDER_INVALID")
    for item in [*smoke, *enforcement]:
        if not item.hook_name or not item.source_ref or not item.expected_result:
            issues.append(f"CASE_BINDING_INCOMPLETE:{item.case_id}")
    return {
        "status": "PASS" if not issues and len(smoke) == 20 and len(enforcement) == 15 else "FAIL",
        "smoke_count": len(smoke),
        "enforcement_count": len(enforcement),
        "smoke_case_ids": [item.case_id for item in smoke],
        "enforcement_case_ids": [item.case_id for item in enforcement],
        "issues": issues,
        "adapter_contract": "RuntimeCaseAdapter.run_case(binding)",
    }


class PostgresRuntimeCaseAdapter:
    """Adapter seam for database cases; never converts an absent hook to PASS."""

    def __init__(self, connection: Any):
        self.connection = connection

    def run_case(self, binding: RuntimeCaseBinding) -> Mapping[str, Any]:
        hook = getattr(self.connection, "run_v4_runtime_case", None)
        if callable(hook):
            result = hook(binding.to_dict())
            if isinstance(result, Mapping):
                return dict(result)
        return {
            "status": RUNTIME_CASE_PENDING,
            "case_id": binding.case_id,
            "hook_name": binding.hook_name,
            "expected_result": binding.expected_result,
            "actually_executed": False,
            "reason": "The PostgreSQL validation adapter has no case hook implementation for this binding",
        }


def run_runtime_cases(repo_root: Path, adapter: RuntimeCaseAdapter) -> Dict[str, Any]:
    bindings = load_runtime_case_bindings(repo_root)
    results: List[Dict[str, Any]] = []
    for group in ("smoke", "enforcement"):
        for binding in bindings[group]:
            try:
                result = dict(adapter.run_case(binding))
            except Exception as exc:
                result = {
                    "status": "FAIL",
                    "case_id": binding.case_id,
                    "hook_name": binding.hook_name,
                    "expected_result": binding.expected_result,
                    "actually_executed": False,
                    "error_type": type(exc).__name__,
                }
            result.setdefault("case_id", binding.case_id)
            result.setdefault("kind", binding.kind)
            result.setdefault("hook_name", binding.hook_name)
            result.setdefault("expected_result", binding.expected_result)
            if result.get("case_id") != binding.case_id:
                result = {
                    "status": "FAIL",
                    "case_id": binding.case_id,
                    "kind": binding.kind,
                    "hook_name": binding.hook_name,
                    "expected_result": binding.expected_result,
                    "actually_executed": False,
                    "error_code": "RUNTIME_CASE_ID_MISMATCH",
                }
            elif result.get("status") == "PASS" and result.get("actually_executed") is not True:
                result = {
                    **result,
                    "status": "FAIL",
                    "actually_executed": False,
                    "error_code": "RUNTIME_CASE_PASS_WITHOUT_EXECUTION",
                }
            results.append(result)
    executed = sum(1 for result in results if result.get("actually_executed") is True)
    passed = sum(1 for result in results if result.get("status") == "PASS" and result.get("actually_executed") is True)
    failed = sum(1 for result in results if result.get("status") == "FAIL")
    pending = len(results) - passed - failed
    return {
        "status": "PASS" if len(results) == 35 and failed == 0 and pending == 0 else ("FAIL" if failed else "PENDING"),
        "defined_count": len(results),
        "actually_executed": executed,
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "smoke_count": len(bindings["smoke"]),
        "enforcement_count": len(bindings["enforcement"]),
        "results": results,
    }
