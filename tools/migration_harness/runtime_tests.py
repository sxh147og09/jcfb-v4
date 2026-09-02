"""Executable PRE-BATCH-04 runtime case contract and result semantics.

The smoke catalog and negative registry remain the only authorities for the
case list.  This module adds the executable contract that describes how each
registered case is set up, exercised, checked, and rolled back.  The actual
PostgreSQL statements live behind :class:`PostgresRuntimeCaseAdapter` in
``runtime_case_handlers.py`` so the adapter can be unit-tested without opening
a socket or importing Docker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

from .common import read_json
from .runtime_case_handlers import RuntimeCaseHandlerRunner, match_expected_rejection


SMOKE_CATALOG_RELATIVE = "config/migration_harness/v4_smoke_test_catalog.json"
NEGATIVE_REGISTRY_RELATIVE = "config/migration_harness/v4_negative_case_registry.json"
EXECUTION_CONTRACT_RELATIVE = "config/migration_harness/v4_runtime_case_execution.json"
RUNTIME_CASE_PENDING = "RUNTIME_CASE_HOOK_PENDING"  # legacy report token; never emitted by the executable adapter

CASE_RESULT_STATUSES = (
    "PASS_EXPECTED_ACCEPT",
    "PASS_EXPECTED_REJECT",
    "FAIL_UNEXPECTED_ACCEPT",
    "FAIL_UNEXPECTED_REJECT",
    "BLOCKED_ENVIRONMENT",
)


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
    expected_outcome: str = ""
    execution: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        execution = dict(self.execution)
        return {
            "case_id": self.case_id,
            "number": self.number,
            "kind": self.kind,
            "name": self.name,
            "expected_result": self.expected_result,
            "expected_outcome": self.expected_outcome or execution.get("expected_outcome"),
            "caller_roles": list(self.caller_roles),
            "hook_name": self.hook_name,
            "source_ref": self.source_ref,
            "runtime_required": self.runtime_required,
            "execution": execution,
        }


class RuntimeCaseAdapter(Protocol):
    def run_case(self, binding: RuntimeCaseBinding) -> Mapping[str, Any]:
        ...


def _hook_name(kind: str, case_id: str, name: str) -> str:
    normalized = "_".join(part for part in name.lower().replace("/", " ").split() if part)
    return f"{kind.lower()}_{case_id.lower().replace('-', '_')}_{normalized}"


def load_runtime_case_execution_contract(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / EXECUTION_CONTRACT_RELATIVE)


def _execution_specs(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    contract = load_runtime_case_execution_contract(repo_root)
    cases = contract.get("cases", []) if isinstance(contract, dict) else []
    return {
        str(case.get("case_id")): dict(case)
        for case in cases
        if isinstance(case, dict) and case.get("case_id")
    }


def load_runtime_case_bindings(repo_root: Path) -> Dict[str, List[RuntimeCaseBinding]]:
    smoke = read_json(repo_root / SMOKE_CATALOG_RELATIVE)
    negative = read_json(repo_root / NEGATIVE_REGISTRY_RELATIVE)
    specs = _execution_specs(repo_root)
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
            hook_name=str(specs.get(str(case.get("id")), {}).get("handler") or _hook_name("smoke", str(case.get("id")), str(case.get("name")))),
            source_ref=f"{SMOKE_CATALOG_RELATIVE}#{case.get('id')}",
            expected_outcome=str(specs.get(str(case.get("id")), {}).get("expected_outcome", "")),
            execution=specs.get(str(case.get("id")), {}),
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
            caller_roles=[
                str(item)
                for item in specs.get(str(case.get("id")), {}).get("caller_roles", [])
            ],
            hook_name=str(specs.get(str(case.get("id")), {}).get("handler") or _hook_name("enforcement", str(case.get("id")), str(case.get("name")))),
            source_ref=f"{NEGATIVE_REGISTRY_RELATIVE}#{case.get('id')}",
            expected_outcome=str(specs.get(str(case.get("id")), {}).get("expected_outcome", "")),
            execution=specs.get(str(case.get("id")), {}),
        )
        for index, case in enumerate(negative_cases)
        if isinstance(case, dict) and case.get("runtime_required") is True
    ]
    return {"smoke": smoke_bindings, "enforcement": enforcement_bindings}


def validate_runtime_case_wiring(repo_root: Path) -> Dict[str, Any]:
    bindings = load_runtime_case_bindings(repo_root)
    smoke = bindings["smoke"]
    enforcement = bindings["enforcement"]
    all_bindings = [*smoke, *enforcement]
    issues: List[str] = []
    expected_smoke = [f"SMOKE-{index:02d}" for index in range(1, 21)]
    expected_enforcement = [f"NEG-{index:02d}" for index in range(8, 23)]
    if [item.case_id for item in smoke] != expected_smoke:
        issues.append("SMOKE_CASE_BINDING_ORDER_INVALID")
    if [item.case_id for item in enforcement] != expected_enforcement:
        issues.append("ENFORCEMENT_CASE_BINDING_ORDER_INVALID")
    contract_handlers = [item.hook_name for item in all_bindings]
    if len(set(contract_handlers)) != len(contract_handlers):
        issues.append("RUNTIME_HANDLER_NAMES_NOT_UNIQUE")
    missing_handlers = [
        item.hook_name
        for item in all_bindings
        if not callable(getattr(RuntimeCaseHandlerRunner, item.hook_name, None))
    ]
    missing_handler_set = set(missing_handlers)
    issues.extend(f"RUNTIME_HANDLER_NOT_IMPLEMENTED:{name}" for name in missing_handlers)
    for item in all_bindings:
        execution = dict(item.execution)
        mechanism = execution.get("expected_mechanism")
        if not item.hook_name or not item.source_ref or not item.expected_result:
            issues.append(f"CASE_BINDING_INCOMPLETE:{item.case_id}")
        if execution.get("case_id") != item.case_id:
            issues.append(f"EXECUTION_CONTRACT_MISSING:{item.case_id}")
        if execution.get("kind") != item.kind:
            issues.append(f"EXECUTION_CONTRACT_KIND_MISMATCH:{item.case_id}")
        if list(execution.get("caller_roles", [])) != list(item.caller_roles):
            issues.append(f"EXECUTION_CALLER_ROLES_MISMATCH:{item.case_id}")
        if execution.get("expected_outcome") not in {"ACCEPT", "REJECT"}:
            issues.append(f"EXECUTION_OUTCOME_INVALID:{item.case_id}")
        if not isinstance(execution.get("setup"), str) or not str(execution.get("setup")).strip():
            issues.append(f"EXECUTION_SETUP_MISSING:{item.case_id}")
        if not isinstance(execution.get("action"), str) or not str(execution.get("action")).strip():
            issues.append(f"EXECUTION_ACTION_MISSING:{item.case_id}")
        if not isinstance(execution.get("cleanup"), str) or not str(execution.get("cleanup")).strip():
            issues.append(f"EXECUTION_CLEANUP_MISSING:{item.case_id}")
        if not isinstance(mechanism, dict) or not str(mechanism.get("type", "")).strip():
            issues.append(f"EXPECTED_MECHANISM_MISSING:{item.case_id}")
        if execution.get("expected_outcome") == "REJECT" and not any(
            mechanism.get(key) for key in ("sqlstates", "constraints", "constraint_prefixes", "trigger_names", "message_tokens")
        ):
            issues.append(f"EXPECTED_REJECT_MATCH_RULE_MISSING:{item.case_id}")
    contract = load_runtime_case_execution_contract(repo_root)
    if contract.get("contract_version") != "v4-runtime-case-execution@1.0.0":
        issues.append("RUNTIME_EXECUTION_CONTRACT_VERSION_INVALID")
    contract_ids = [str(case.get("case_id")) for case in contract.get("cases", []) if isinstance(case, dict)]
    if contract_ids != expected_smoke + expected_enforcement:
        issues.append("RUNTIME_EXECUTION_CONTRACT_CASE_SET_INVALID")
    return {
        "status": "PASS" if not issues and len(smoke) == 20 and len(enforcement) == 15 else "FAIL",
        "smoke_count": len(smoke),
        "enforcement_count": len(enforcement),
        "executable_handler_count": len(all_bindings) - len(missing_handlers),
        "smoke_executable_handler_count": sum(item.hook_name not in missing_handler_set for item in smoke),
        "enforcement_executable_handler_count": sum(item.hook_name not in missing_handler_set for item in enforcement),
        "missing_handlers": missing_handlers,
        "smoke_case_ids": [item.case_id for item in smoke],
        "enforcement_case_ids": [item.case_id for item in enforcement],
        "handler_names": contract_handlers,
        "issues": issues,
        "execution_contract": EXECUTION_CONTRACT_RELATIVE,
        "adapter_contract": "RuntimeCaseAdapter.run_case(binding)",
        "result_statuses": list(CASE_RESULT_STATUSES),
    }


class PostgresRuntimeCaseAdapter:
    """Dispatch each binding to a real, isolated PostgreSQL case handler."""

    def __init__(self, connection: Any, *, repo_root: Optional[Path] = None, actor: str = "jcfb-v4-runtime-executor"):
        self.connection = connection
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.actor = actor
        self._runner: Any = None
        self.role_simulation: Optional[Mapping[str, Any]] = None

    def prepare(self) -> Mapping[str, Any]:
        from .runtime_case_handlers import RuntimeCaseHandlerRunner

        if self._runner is None:
            self._runner = RuntimeCaseHandlerRunner(self.connection, actor=self.actor)
        result = self._runner.prepare()
        self.role_simulation = self._runner.role_simulation
        return result

    def run_case(self, binding: RuntimeCaseBinding) -> Mapping[str, Any]:
        if self._runner is None:
            prepared = self.prepare()
            if prepared.get("status") != "PASS":
                return {
                    "status": "BLOCKED_ENVIRONMENT",
                    "case_id": binding.case_id,
                    "actually_executed": False,
                    "phase": "ROLE_SIMULATION",
                    "blocked_reason": prepared.get("reason", "Role simulation could not be prepared"),
                }
        result = self._runner.run_case(binding)
        self.role_simulation = self._runner.role_simulation
        return result


def _normalize_adapter_result(binding: RuntimeCaseBinding, result: Mapping[str, Any]) -> Dict[str, Any]:
    value = dict(result)
    expected = binding.expected_outcome or dict(binding.execution).get("expected_outcome")
    status = value.get("status")
    verification = value.get("verification")
    verification_pass = verification is True or (
        isinstance(verification, Mapping) and bool(verification) and all(item is True for item in verification.values())
    )
    actual = str(value.get("actual_outcome") or "").upper()
    raw_error = value.get("error")
    # Keep the old adapter seam source-compatible for injected unit-test
    # adapters, but translate its generic PASS/FAIL into the explicit runtime
    # result vocabulary before it reaches a report.
    if status == "PASS":
        if expected == "ACCEPT" and actual == "ACCEPT" and verification_pass:
            status = "PASS_EXPECTED_ACCEPT"
        elif expected == "REJECT" and actual == "REJECT" and verification_pass and match_expected_rejection(raw_error, dict(binding.execution).get("expected_mechanism", {})):
            status = "PASS_EXPECTED_REJECT"
        else:
            status = "BLOCKED_ENVIRONMENT"
            value.setdefault("blocked_reason", "Adapter PASS did not provide a fully verified governed outcome")
    elif status == "FAIL":
        status = "FAIL_UNEXPECTED_REJECT" if value.get("actual_outcome") == "REJECT" else "FAIL_UNEXPECTED_ACCEPT"
    elif status == RUNTIME_CASE_PENDING:
        status = "BLOCKED_ENVIRONMENT"
        value.setdefault("blocked_reason", "Legacy adapter did not provide an executable handler")
    elif status == "PASS_EXPECTED_ACCEPT":
        if expected != "ACCEPT" or actual != "ACCEPT" or not verification_pass:
            status = "FAIL_UNEXPECTED_ACCEPT"
            value.setdefault("reason", "Accepted case result did not satisfy its explicit postcondition")
    elif status == "PASS_EXPECTED_REJECT":
        if expected != "REJECT" or actual != "REJECT" or not verification_pass or not match_expected_rejection(raw_error, dict(binding.execution).get("expected_mechanism", {})):
            status = "FAIL_UNEXPECTED_REJECT"
            value.setdefault("reason", "Rejected case result did not match its explicit SQLSTATE/mechanism contract")
    if status not in CASE_RESULT_STATUSES:
        status = "BLOCKED_ENVIRONMENT"
        value.setdefault("blocked_reason", "Adapter returned no governed runtime result status")
    value["status"] = status
    value.setdefault("case_id", binding.case_id)
    value.setdefault("kind", binding.kind)
    value.setdefault("hook_name", binding.hook_name)
    value.setdefault("expected_result", binding.expected_result)
    value.setdefault("expected_outcome", expected)
    value.setdefault("actually_executed", status != "BLOCKED_ENVIRONMENT")
    if raw_error is not None:
        # Never carry a driver exception (and therefore never carry its
        # message, password, URL, or server detail) into the JSON report.
        value["error_sqlstate"] = getattr(raw_error, "sqlstate", None) or getattr(raw_error, "pgcode", None)
        value["error_constraint"] = getattr(getattr(raw_error, "diag", None), "constraint_name", None)
        value.pop("error", None)
    if value.get("case_id") != binding.case_id:
        value = {
            "status": "FAIL_UNEXPECTED_REJECT",
            "case_id": binding.case_id,
            "kind": binding.kind,
            "hook_name": binding.hook_name,
            "expected_result": binding.expected_result,
            "expected_outcome": expected,
            "actually_executed": False,
            "phase": "ADAPTER_CONTRACT",
            "error_code": "RUNTIME_CASE_ID_MISMATCH",
        }
    return value


def run_runtime_cases(repo_root: Path, adapter: RuntimeCaseAdapter) -> Dict[str, Any]:
    bindings = load_runtime_case_bindings(repo_root)
    preparation: Optional[Mapping[str, Any]] = None
    prepare = getattr(adapter, "prepare", None)
    if callable(prepare):
        try:
            preparation = prepare()
        except Exception:
            preparation = {
                "status": "BLOCKED",
                "reason": "Disposable role simulation or runtime preparation failed",
            }

    results: List[Dict[str, Any]] = []
    for group in ("smoke", "enforcement"):
        for binding in bindings[group]:
            if preparation is not None and preparation.get("status") != "PASS":
                result = {
                    "status": "BLOCKED_ENVIRONMENT",
                    "case_id": binding.case_id,
                    "kind": binding.kind,
                    "hook_name": binding.hook_name,
                    "expected_result": binding.expected_result,
                    "expected_outcome": binding.expected_outcome,
                    "actually_executed": False,
                    "phase": "ROLE_SIMULATION",
                    "blocked_reason": preparation.get("reason", "Runtime preparation was blocked"),
                }
            else:
                try:
                    result = _normalize_adapter_result(binding, adapter.run_case(binding))
                except Exception:
                    result = {
                        "status": "BLOCKED_ENVIRONMENT",
                        "case_id": binding.case_id,
                        "kind": binding.kind,
                        "hook_name": binding.hook_name,
                        "expected_result": binding.expected_result,
                        "expected_outcome": binding.expected_outcome,
                        "actually_executed": False,
                        "phase": "ADAPTER_DISPATCH",
                        "blocked_reason": "Runtime adapter dispatch failed before a governed result was produced",
                    }
            results.append(result)

    passed_accept = sum(1 for result in results if result.get("status") == "PASS_EXPECTED_ACCEPT")
    passed_reject = sum(1 for result in results if result.get("status") == "PASS_EXPECTED_REJECT")
    failed_accept = sum(1 for result in results if result.get("status") == "FAIL_UNEXPECTED_ACCEPT")
    failed_reject = sum(1 for result in results if result.get("status") == "FAIL_UNEXPECTED_REJECT")
    blocked = sum(1 for result in results if result.get("status") == "BLOCKED_ENVIRONMENT")
    passed = passed_accept + passed_reject
    failed = failed_accept + failed_reject
    passed_smoke = sum(
        1
        for result in results
        if result.get("kind") == "SMOKE" and result.get("status") in {"PASS_EXPECTED_ACCEPT", "PASS_EXPECTED_REJECT"}
    )
    passed_enforcement = sum(
        1
        for result in results
        if result.get("kind") == "ENFORCEMENT" and result.get("status") in {"PASS_EXPECTED_ACCEPT", "PASS_EXPECTED_REJECT"}
    )
    expected_reject_results = [result for result in results if result.get("expected_outcome") == "REJECT"]
    expected_reject_matching = "PASS" if expected_reject_results and all(
        result.get("status") == "PASS_EXPECTED_REJECT" for result in expected_reject_results
    ) else "FAIL"
    by_id = {str(result.get("case_id")): result for result in results}

    def gate(case_ids: Sequence[str]) -> str:
        selected = [by_id.get(case_id) for case_id in case_ids]
        if not selected or any(item is None or item.get("status") == "BLOCKED_ENVIRONMENT" for item in selected):
            return "BLOCKED"
        if any(item.get("status") in {"FAIL_UNEXPECTED_ACCEPT", "FAIL_UNEXPECTED_REJECT"} for item in selected):
            return "FAIL"
        return "PASS" if all(item.get("status") in {"PASS_EXPECTED_ACCEPT", "PASS_EXPECTED_REJECT"} for item in selected) else "FAIL"

    runtime_gates = {
        "no_future_leakage": gate(("SMOKE-06", "NEG-11")),
        "frozen_immutability": gate(("SMOKE-07", "SMOKE-08", "NEG-12", "NEG-13")),
        "tier_a_same_frozen_input": gate(("SMOKE-11", "SMOKE-12", "NEG-15", "NEG-16")),
        "production_uniqueness": gate(("SMOKE-14", "NEG-18")),
        "rls_role_boundary": gate(("SMOKE-15", "SMOKE-16", "NEG-20")),
        "canonical_latest_update": gate(("SMOKE-18", "NEG-21")),
        "market_semantics": gate(("SMOKE-03", "SMOKE-04", "SMOKE-05", "NEG-08", "NEG-09", "NEG-10", "NEG-22")),
    }
    runtime_gates["hard_gates"] = "PASS" if all(
        runtime_gates[name] == "PASS"
        for name in ("no_future_leakage", "frozen_immutability", "tier_a_same_frozen_input", "production_uniqueness", "rls_role_boundary", "canonical_latest_update")
    ) else ("BLOCKED" if any(runtime_gates[name] == "BLOCKED" for name in runtime_gates) else "FAIL")
    if len(results) == 35 and passed == 35:
        status = "PASS"
    elif failed:
        status = "FAIL"
    else:
        status = "BLOCKED"
    role_simulation = getattr(adapter, "role_simulation", None)
    return {
        "status": status,
        "defined_count": len(results),
        "actually_executed": sum(1 for result in results if result.get("actually_executed") is True),
        "passed": passed,
        "passed_smoke": passed_smoke,
        "passed_enforcement": passed_enforcement,
        "pass_expected_accept": passed_accept,
        "pass_expected_reject": passed_reject,
        "failed": failed,
        "fail_unexpected_accept": failed_accept,
        "fail_unexpected_reject": failed_reject,
        "blocked_environment": blocked,
        "pending": 0,
        "smoke_count": len(bindings["smoke"]),
        "enforcement_count": len(bindings["enforcement"]),
        "expected_reject_matching": expected_reject_matching,
        "runtime_gates": runtime_gates,
        "case_status_counts": {
            status: sum(1 for result in results if result.get("status") == status)
            for status in CASE_RESULT_STATUSES
        },
        "role_simulation": dict(role_simulation) if isinstance(role_simulation, Mapping) else None,
        "results": results,
    }
