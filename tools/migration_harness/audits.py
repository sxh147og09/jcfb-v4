"""Batch-level static audits used by the BATCH-02 report."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import CheckStatus, Issue
from .runtime_executor import RuntimeEvidenceError, run_resolved_git_command


def _result(status: str, evidence_ref: str, reason: str, **extra: Any) -> Dict[str, Any]:
    value: Dict[str, Any] = {"status": status, "evidence_ref": evidence_ref, "reason": reason}
    value.update(extra)
    return value


def run_self_audit(repo_root: Path, manifest, smoke_issues: Iterable[Issue], negative_registry_issues: Iterable[Issue]) -> Dict[str, Any]:
    issues: List[Issue] = []
    required = [
        "tools/migration_harness/manifest.py",
        "tools/migration_harness/runner.py",
        "tools/migration_harness/preflight.py",
        "tools/migration_harness/schema_diff.py",
        "tools/migration_harness/negative.py",
        "config/migration_harness/v4_negative_case_registry.json",
        "docs/V4_BATCH_02_IMPLEMENTATION.md",
    ]
    for relative in required:
        if not (repo_root / relative).is_file():
            issues.append(Issue("SELF_AUDIT_ARTIFACT_MISSING", f"Required BATCH-02 artifact is missing: {relative}"))
    if not manifest.ok:
        issues.append(Issue("SELF_AUDIT_MANIFEST_INVALID", "Manifest must parse and cross-check before acceptance"))
    issues.extend(smoke_issues)
    issues.extend(negative_registry_issues)
    if len(manifest.entries) != 9 or manifest.sequence_status != "PASS" or manifest.dependency_status != "PASS":
        issues.append(Issue("SELF_AUDIT_MANIFEST_ORDER", "Manifest must contain ordered 0001 through 0009 dependencies"))
    return _result(
        CheckStatus.PASS.value if not issues else CheckStatus.FAIL.value,
        "evidence/batch-02-self-audit.json",
        "Child scope, artifacts, IDs, boundaries, and registries are consistent" if not issues else "Self-audit found one or more issues",
        issue_count=len(issues),
        issues=[issue.to_dict() for issue in issues],
    )


def run_cross_doc_consistency(repo_root: Path) -> Dict[str, Any]:
    checks: List[str] = []
    failures: List[str] = []

    def require(relative: str, needle: str) -> None:
        path = repo_root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            return
        text = path.read_text(encoding="utf-8")
        if needle not in text:
            failures.append(f"missing-text:{relative}:{needle}")
        else:
            checks.append(f"{relative}:{needle}")

    require("docs/V4_TASK_REGISTRY_001_100.md", "| V4-013 | V4-013｜Migration Dry-Run Harness Implementation 1.0 |")
    require("docs/V4_TASK_REGISTRY_001_100.md", "| V4-015 | V4-015｜Migration Smoke, RLS & Trigger Test Suite 1.0 |")
    require("docs/V4_EXECUTION_CLASSIFICATION.md", "| V4-013 | V4-013｜Migration Dry-Run Harness Implementation 1.0 | BATCHABLE + SERIAL | BATCH-02")
    require("docs/V4_EXECUTION_CLASSIFICATION.md", "| V4-015 | V4-015｜Migration Smoke, RLS & Trigger Test Suite 1.0 | BATCHABLE + PARALLEL | BATCH-02")
    require("docs/V4_BATCH_EXECUTION_PLAN.md", "| BATCH-02 | V4-013–V4-015 |")
    require("docs/V4_BATCH_ACCEPTANCE_RULES.md", "BATCH-02 ACCEPTANCE PASS")
    require("docs/V4_MASTER_BUILD_CHECKLIST.md", "- [x] V4-013")
    require("docs/V4_MASTER_BUILD_CHECKLIST.md", "- [x] V4-015")
    require("docs/V4_BATCH_02_IMPLEMENTATION.md", "V4-013")
    require("docs/V4_BATCH_02_IMPLEMENTATION.md", "V4-014")
    require("docs/V4_BATCH_02_IMPLEMENTATION.md", "V4-015")
    require("README.md", "V4-016 NEXT")

    return _result(
        CheckStatus.PASS.value if not failures else CheckStatus.FAIL.value,
        "evidence/batch-02-cross-doc-consistency.json",
        "Registry, classification, plan, acceptance rules, checklist, implementation note, and README agree" if not failures else "Cross-document consistency check failed",
        checks=checks,
        failures=failures,
    )


def run_git_diff_check(repo_root: Path) -> Dict[str, Any]:
    try:
        result = run_resolved_git_command(repo_root, "diff", "--check")
    except RuntimeEvidenceError as exc:
        return _result(
            CheckStatus.FAIL.value,
            "evidence/git-diff-check.txt",
            "Git executable could not be resolved for git diff --check",
            output=exc.code,
        )
    return _result(
        CheckStatus.PASS.value if result.returncode == 0 else CheckStatus.FAIL.value,
        "evidence/git-diff-check.txt",
        "git diff --check passed" if result.returncode == 0 else "git diff --check reported whitespace errors",
        output=result.stdout.strip() or result.stderr.strip(),
    )


def run_v333_path_audit(repo_root: Path) -> Dict[str, Any]:
    try:
        result = run_resolved_git_command(repo_root, "diff", "--name-only")
    except RuntimeEvidenceError as exc:
        return _result(
            CheckStatus.FAIL.value,
            "evidence/v333-isolation-audit.json",
            "Git executable could not be resolved for the V3.3.3 isolation audit",
            changed_paths=[],
            collisions=[],
            error_code=exc.code,
        )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    collisions = [path for path in changed if re.search(r"(^|/)(?:V333|v333|V3\.3\.3)(?:/|$)", path)]
    return _result(
        CheckStatus.PASS.value if not collisions else CheckStatus.FAIL.value,
        "evidence/v333-isolation-audit.json",
        "No V3.3.3 path is changed by BATCH-02" if not collisions else "A V3.3.3 path appears in the working diff",
        changed_paths=changed,
        collisions=collisions,
    )
