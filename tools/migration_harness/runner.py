"""No-write migration plan/runner boundary for BATCH-02."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import sha256_json
from .manifest import load_manifest, manifest_identity_hash
from .models import CheckStatus, ExecutionMode, RunnerStatus
from .preflight import run_preflight
from .target import validate_target_descriptor


ALLOWED_TRANSITIONS = {
    RunnerStatus.PLANNED: {RunnerStatus.READY_FOR_DISPOSABLE, RunnerStatus.PRECHECK_BLOCKED},
    RunnerStatus.READY_FOR_DISPOSABLE: {RunnerStatus.APPLYING, RunnerStatus.PRECHECK_BLOCKED},
    RunnerStatus.APPLYING: {RunnerStatus.VALIDATING, RunnerStatus.FAILED, RunnerStatus.PARTIAL_FAIL},
    RunnerStatus.VALIDATING: {RunnerStatus.ACCEPTED, RunnerStatus.FAILED},
    RunnerStatus.PRECHECK_BLOCKED: set(),
    RunnerStatus.ACCEPTED: set(),
    RunnerStatus.FAILED: set(),
    RunnerStatus.PARTIAL_FAIL: set(),
}


def can_transition(current: RunnerStatus, next_status: RunnerStatus) -> bool:
    return next_status in ALLOWED_TRANSITIONS.get(current, set())


def _safe_target(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if target is None:
        return {"target_id": None, "environment": None, "provider": None}
    return {
        "target_id": target.get("target_id"),
        "environment": target.get("environment"),
        "provider": target.get("provider"),
    }


class DryRunRunner:
    """Build plans and refuse every path that could apply or reach Production."""

    contract_version = "v4-batch-02-dry-run-runner@1.0.0"

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def _steps(self, manifest) -> List[Dict[str, Any]]:
        return [
            {
                "sequence": entry.sequence,
                "file": entry.file,
                "migration_id": entry.migration_id,
                "depends_on": list(entry.depends_on),
                "transaction_boundary": "ONE_TRANSACTION",
                "apply_allowed": False,
                "status": "PLANNED",
            }
            for entry in manifest.entries
        ]

    def plan(
        self,
        *,
        mode: ExecutionMode = ExecutionMode.PLAN_ONLY,
        target: Optional[Dict[str, Any]] = None,
        catalog: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if isinstance(mode, str):
            mode = ExecutionMode(mode)
        manifest = load_manifest(self.repo_root)
        status = RunnerStatus.PLANNED
        blocking_reasons: List[str] = []
        preflight = None
        target_validation = None

        if not manifest.ok:
            status = RunnerStatus.PRECHECK_BLOCKED
            blocking_reasons.append("MANIFEST_VALIDATION_FAILED")

        if mode in {ExecutionMode.APPLY, ExecutionMode.PRODUCTION_APPLY}:
            status = RunnerStatus.PRECHECK_BLOCKED
            blocking_reasons.append("APPLY_FORBIDDEN_IN_BATCH_02")

        if mode == ExecutionMode.DRY_RUN:
            if target is None:
                status = RunnerStatus.PRECHECK_BLOCKED
                blocking_reasons.append("TARGET_REQUIRED_FOR_DRY_RUN")
            else:
                target_validation = validate_target_descriptor(target)
                if not target_validation.ok:
                    status = RunnerStatus.PRECHECK_BLOCKED
                    blocking_reasons.extend(issue.code for issue in target_validation.issues)
                else:
                    preflight = run_preflight(self.repo_root, manifest, target=target, catalog=catalog)
                    if preflight.status != CheckStatus.PASS:
                        status = RunnerStatus.PRECHECK_BLOCKED
                        blocking_reasons.append("PREFLIGHT_NOT_PASS")
                    else:
                        # This branch is intentionally not an apply.  A future
                        # adapter may move from READY_FOR_DISPOSABLE to a
                        # read-only VALIDATING stage only after its own gate.
                        status = RunnerStatus.READY_FOR_DISPOSABLE
        elif mode == ExecutionMode.PLAN_ONLY and target is not None:
            target_validation = validate_target_descriptor(target)
            if not target_validation.ok:
                status = RunnerStatus.PRECHECK_BLOCKED
                blocking_reasons.extend(issue.code for issue in target_validation.issues)
            else:
                status = RunnerStatus.READY_FOR_DISPOSABLE

        if mode == ExecutionMode.PRODUCTION_APPLY:
            blocking_reasons.append("PRODUCTION_TARGET_HARD_BLOCK")

        report_payload = {
            "contract_version": self.contract_version,
            "mode": mode.value,
            "status": status.value,
            "manifest_identity_hash": manifest_identity_hash(manifest),
            "manifest": manifest.to_dict(),
            "target": _safe_target(target),
            "target_validation": target_validation.to_dict() if target_validation else None,
            "preflight": preflight.to_dict() if preflight else None,
            "steps": self._steps(manifest),
            "state_machine": {
                "allowed_statuses": [item.value for item in RunnerStatus],
                "apply_stage_reachable": False,
                "production_target_hard_block": True,
            },
            "execution_boundary": {
                "connector_invoked": False,
                "database_connected": False,
                "sql_executed": False,
                "ddl_applied": False,
                "production_db_writes_performed": "NO",
                "supabase_writes_performed": "NO",
                "v333_mutated": "NO",
            },
            "blocking_reasons": sorted(set(blocking_reasons)),
        }
        report_payload["plan_hash"] = sha256_json(
            {
                "contract_version": report_payload["contract_version"],
                "mode": report_payload["mode"],
                "status": report_payload["status"],
                "manifest_identity_hash": report_payload["manifest_identity_hash"],
                "target": report_payload["target"],
                "steps": report_payload["steps"],
                "blocking_reasons": report_payload["blocking_reasons"],
            }
        )
        return report_payload

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Alias for plan; no apply method exists by design."""

        return self.plan(**kwargs)
