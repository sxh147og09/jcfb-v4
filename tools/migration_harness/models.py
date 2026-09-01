"""Small immutable-ish data structures shared by the harness modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_EXECUTED_REQUIRES_DISPOSABLE_DB = "NOT_EXECUTED_REQUIRES_DISPOSABLE_DB"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RUNTIME_NEGATIVE_TEST_PENDING = "RUNTIME_NEGATIVE_TEST_PENDING"
    RUNTIME_PENDING_DISPOSABLE_DB = "RUNTIME_PENDING_DISPOSABLE_DB"


class ExecutionMode(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    DRY_RUN = "DRY_RUN"
    APPLY = "APPLY"
    PRODUCTION_APPLY = "PRODUCTION_APPLY"


class RunnerStatus(str, Enum):
    PLANNED = "PLANNED"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    READY_FOR_DISPOSABLE = "READY_FOR_DISPOSABLE"
    APPLYING = "APPLYING"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"
    PARTIAL_FAIL = "PARTIAL_FAIL"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.location:
            value["location"] = self.location
        return value


@dataclass
class ManifestEntry:
    sequence: str
    file: str
    migration_id: str
    migration_version: str
    name: str
    depends_on: List[str]
    schema_contract_version: str
    authored_at: str
    migration_hash: str
    status: str
    expected_objects: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "file": self.file,
            "migration_id": self.migration_id,
            "migration_version": self.migration_version,
            "name": self.name,
            "depends_on": list(self.depends_on),
            "schema_contract_version": self.schema_contract_version,
            "authored_at": self.authored_at,
            "migration_hash": self.migration_hash,
            "status": self.status,
            "expected_objects": list(self.expected_objects),
        }


@dataclass
class ManifestLoadResult:
    entries: List[ManifestEntry]
    issues: List[Issue]
    source_manifest: str
    source_sql_directory: str
    parse_mode: str = "TEXT_METADATA_ONLY"

    @property
    def ok(self) -> bool:
        return not self.issues and len(self.entries) == 9

    @property
    def pending_hash_count(self) -> int:
        return sum(1 for entry in self.entries if entry.migration_hash == "PENDING_CANONICAL_HASH")

    @property
    def sequence_status(self) -> str:
        expected = [f"000{i}" for i in range(1, 10)]
        return "PASS" if [entry.sequence for entry in self.entries] == expected else "FAIL"

    @property
    def dependency_status(self) -> str:
        return "PASS" if not any(issue.code.startswith("DEPENDENCY_") for issue in self.issues) else "FAIL"

    @property
    def hash_status(self) -> str:
        if any(issue.code.startswith("HASH_") for issue in self.issues):
            return "FAIL"
        return "PENDING_CANONICAL_HASH" if self.pending_hash_count else "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_manifest": self.source_manifest,
            "source_sql_directory": self.source_sql_directory,
            "parse_mode": self.parse_mode,
            "entries": [entry.to_dict() for entry in self.entries],
            "sequence_status": self.sequence_status,
            "dependency_status": self.dependency_status,
            "hash_status": self.hash_status,
            "pending_hash_count": self.pending_hash_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class TargetValidation:
    status: CheckStatus
    issues: List[Issue]
    target_id: Optional[str] = None
    environment: Optional[str] = None
    provider: Optional[str] = None
    connect_allowed: bool = False

    @property
    def ok(self) -> bool:
        return self.status == CheckStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "target_id": self.target_id,
            "environment": self.environment,
            "provider": self.provider,
            "connect_allowed": self.connect_allowed,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class PreflightCheck:
    check_id: str
    status: CheckStatus
    target_dependent: bool
    evidence_ref: str
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        value: Dict[str, Any] = {
            "id": self.check_id,
            "status": self.status.value,
            "target_dependent": self.target_dependent,
            "evidence_ref": self.evidence_ref,
            "reason": self.reason,
        }
        if self.details:
            value["details"] = self.details
        return value


@dataclass
class PreflightReport:
    status: CheckStatus
    checks: List[PreflightCheck]
    target: Optional[Dict[str, Any]]
    not_run_reason: str
    secret_scan: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "target": {
                "target_id": self.target.get("target_id") if self.target else None,
                "environment": self.target.get("environment") if self.target else None,
                "provider": self.target.get("provider") if self.target else None,
            },
            "not_run_reason": self.not_run_reason,
            "secret_scan": self.secret_scan,
        }


@dataclass
class SchemaDiffReport:
    status: CheckStatus
    classifications: List[Dict[str, Any]]
    evidence_ref: str
    expected_counts: Dict[str, int]
    actual_counts: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "classifications": list(self.classifications),
            "evidence_ref": self.evidence_ref,
            "expected_counts": dict(self.expected_counts),
            "actual_counts": dict(self.actual_counts),
        }
