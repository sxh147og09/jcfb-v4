"""Static self-audit for PRE-BATCH-04 remediation 2.

This audit deliberately stops at repository and process boundaries.  It does
not import Docker clients, open a socket, invoke a database driver, or execute
SQL.  A local operator can run it before the explicit PowerShell apply gate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .canonical_hash import verify_candidate_hashes
from .connection import driver_status
from .runtime_executor import RuntimeExecutor, default_disposable_target
from .runtime_tests import validate_runtime_case_wiring
from .security import secret_scan
from .models import ExecutionMode


REQUIRED_FILES = (
    "tools/migration_harness/canonical_hash.py",
    "tools/migration_harness/connection.py",
    "tools/migration_harness/catalog.py",
    "tools/migration_harness/runtime_executor.py",
    "tools/migration_harness/runtime_tests.py",
    "tools/migration_harness/runtime_audit.py",
    "scripts/v4_run_prebatch04_runtime_validation.ps1",
    "docs/V4_CANONICAL_MIGRATION_HASH.md",
    "docs/V4_RUNTIME_EXECUTOR.md",
    "docs/V4_PRE_BATCH_04_LOCAL_EXECUTION.md",
    "requirements-v4-runtime.txt",
)

ACTIVE_STORAGE_FILES = (
    ".gitignore",
    "docker-compose.runtime-validation.yml",
    "scripts/v4_disposable_runtime.ps1",
    "scripts/activate_jcfb_v4_runtime.ps1",
    "docs/JCFB_V4_LOCAL_STORAGE.md",
)


def _git_status(repo_root: Path) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return {"status": "BLOCKED_GIT", "changed_files": [], "reason": "Git executable is unavailable"}
    if result.returncode != 0:
        return {"status": "BLOCKED_GIT", "changed_files": [], "reason": "Repository Git metadata is unavailable"}
    changed = [line[3:].strip() for line in result.stdout.splitlines() if len(line) >= 3]
    return {"status": "CLEAN" if not changed else "DIRTY", "changed_files": changed}


def _design_files_untouched(repo_root: Path) -> Dict[str, Any]:
    try:
        unstaged = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", "--", "database/migrations/v4"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        staged = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "--", "database/migrations/v4"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return {"status": "BLOCKED_GIT", "changed_files": []}
    if unstaged.returncode != 0 or staged.returncode != 0:
        return {"status": "BLOCKED_GIT", "changed_files": []}
    changed = [*unstaged.stdout.splitlines(), *staged.stdout.splitlines()]
    return {"status": "PASS" if not changed else "FAIL", "changed_files": changed}


def _storage_policy(repo_root: Path) -> Dict[str, Any]:
    issues: List[str] = []
    inspected: List[str] = []
    for relative in ACTIVE_STORAGE_FILES:
        path = repo_root / relative
        if not path.is_file():
            issues.append(f"MISSING:{relative}")
            continue
        inspected.append(relative)
        text = path.read_text(encoding="utf-8")
        if "C:\\Users\\Administrator" in text or "C:/Users/Administrator" in text:
            issues.append(f"ABSOLUTE_MACHINE_PATH:{relative}")
    compose = (repo_root / "docker-compose.runtime-validation.yml").read_text(encoding="utf-8") if (repo_root / "docker-compose.runtime-validation.yml").is_file() else ""
    activate = (repo_root / "scripts/activate_jcfb_v4_runtime.ps1").read_text(encoding="utf-8") if (repo_root / "scripts/activate_jcfb_v4_runtime.ps1").is_file() else ""
    if "./.runtime/postgres" not in compose:
        issues.append("POSTGRES_PATH_NOT_REPO_RELATIVE")
    if ".runtime" not in activate:
        issues.append("RUNTIME_ENV_NOT_PROJECT_SCOPED")
    return {"status": "PASS" if not issues else "FAIL", "files": inspected, "issues": issues}


def _required_files(repo_root: Path) -> Dict[str, Any]:
    missing = [relative for relative in REQUIRED_FILES if not (repo_root / relative).is_file()]
    return {"status": "PASS" if not missing else "FAIL", "missing": missing}


def run_remediation_self_audit(repo_root: Path) -> Dict[str, Any]:
    """Return redacted static evidence for the remediation package."""

    root = repo_root.resolve()
    hash_report = verify_candidate_hashes(root)
    wiring = validate_runtime_case_wiring(root)
    executor = RuntimeExecutor(root)
    plan = executor.execute(target=default_disposable_target(), mode=ExecutionMode.PLAN_ONLY)
    production_target = default_disposable_target()
    production_target.update(
        {
            "target_id": "jcfb-v4-production-review",
            "environment": "PRODUCTION",
            "provider": "PRODUCTION_SUPABASE",
            "disposable": False,
            "connect_permission": "BLOCKED",
        }
    )
    production = executor.execute(target=production_target, mode=ExecutionMode.PRODUCTION_APPLY)
    secrets = secret_scan(root)
    git = _git_status(root)
    design = _design_files_untouched(root)
    checks = {
        "required_files": _required_files(root),
        "canonical_hashes": {
            "status": "PASS" if hash_report.get("status") == "PASS" else "FAIL",
            "matched_count": hash_report.get("matched_count", 0),
            "candidate_count": hash_report.get("candidate_count", 0),
            "pending_count": hash_report.get("pending_count", 0),
            "dependency_status": hash_report.get("dependency_status"),
        },
        "runtime_case_wiring": wiring,
        "plan_only": {
            "status": "PASS"
            if plan.get("status") == "PLANNED"
            and plan.get("execution_boundary", {}).get("connector_invoked") is False
            and plan.get("execution_boundary", {}).get("database_connected") is False
            and plan.get("execution_boundary", {}).get("sql_executed") is False
            else "FAIL",
            "mode": plan.get("mode"),
        },
        "production_hard_block": {
            "status": "PASS"
            if production.get("status") == "BLOCKED"
            and "PRODUCTION_TARGET_HARD_BLOCK" in production.get("blocking_reasons", [])
            and production.get("execution_boundary", {}).get("connector_invoked") is False
            else "FAIL",
            "blocking_reasons": production.get("blocking_reasons", []),
        },
        "driver_strategy": driver_status(),
        "storage_policy": _storage_policy(root),
        "design_migrations_untouched": design,
        "secret_scan": secrets,
        "git": git,
    }
    hard_checks = (
        checks["required_files"]["status"] == "PASS",
        checks["canonical_hashes"]["status"] == "PASS",
        wiring.get("status") == "PASS",
        checks["plan_only"]["status"] == "PASS",
        checks["production_hard_block"]["status"] == "PASS",
        checks["storage_policy"]["status"] == "PASS",
        checks["design_migrations_untouched"]["status"] == "PASS",
        secrets.get("status") == "PASS",
    )
    return {
        "status": "PASS" if all(hard_checks) else "BLOCKED",
        "repository_root": root.as_posix(),
        "checks": checks,
        "database_runtime_executed": "NO",
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
        "v333_mutated": "NO",
    }
