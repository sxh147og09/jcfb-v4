"""Read-only expected-vs-actual catalog comparison."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .common import count_by_kind, object_name, read_json
from .models import CheckStatus, Issue, SchemaDiffReport


CATALOG_KINDS = (
    "schemas",
    "tables",
    "indexes",
    "functions",
    "views",
    "triggers",
    "policies",
    "rls_tables",
)
DIFF_CLASSIFICATIONS = {
    "MISSING",
    "EXTRA",
    "TYPE_MISMATCH",
    "CONSTRAINT_MISMATCH",
    "SECURITY_MISMATCH",
}


def load_expected_snapshot(repo_root: Path) -> Dict[str, Any]:
    return read_json(repo_root / "config/migration_harness/v4_schema_snapshot_contract.json")


def validate_expected_snapshot_shape(snapshot: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    expected = snapshot.get("expected_catalog")
    counts = snapshot.get("expected_counts")
    if not isinstance(expected, dict) or not isinstance(counts, dict):
        return [Issue("EXPECTED_SNAPSHOT_INVALID", "Expected schema snapshot must contain expected_catalog and expected_counts")]
    for kind in CATALOG_KINDS:
        values = expected.get(kind)
        if not isinstance(values, list):
            issues.append(Issue("EXPECTED_SNAPSHOT_KIND_MISSING", f"Expected snapshot kind is missing: {kind}"))
            continue
        if counts.get(kind) != len(values):
            issues.append(Issue("EXPECTED_SNAPSHOT_COUNT_MISMATCH", f"Expected count does not match catalog list for {kind}"))
        if len({object_name(value) for value in values}) != len(values):
            issues.append(Issue("EXPECTED_SNAPSHOT_DUPLICATE", f"Expected snapshot has duplicate objects in {kind}"))
    actual = snapshot.get("actual_catalog")
    if not isinstance(actual, dict) or actual.get("status") != "NOT_EXECUTED_REQUIRES_DISPOSABLE_DB":
        issues.append(Issue("EXPECTED_SNAPSHOT_BOUNDARY_INVALID", "The checked-in actual catalog must remain runtime-pending"))
    diff_contract = snapshot.get("diff_contract", {})
    if diff_contract.get("unknown_catalog_status") != "BLOCKED" or diff_contract.get("never_auto_repair") is not True:
        issues.append(Issue("EXPECTED_SNAPSHOT_DIFF_POLICY_INVALID", "Unknown catalogs must block and may not be auto-repaired"))
    return issues


def _items_by_name(items: Iterable[Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for item in items:
        result[object_name(item)] = item
    return result


def _compare_structured(expected: Any, actual: Any) -> Optional[str]:
    """Return the most specific contract classification for a structured item."""

    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return None
    for field in ("types", "type", "data_type"):
        if field in expected and actual.get(field) != expected.get(field):
            return "TYPE_MISMATCH"
    for field in ("constraints", "indexes", "columns"):
        if field in expected and actual.get(field) != expected.get(field):
            return "CONSTRAINT_MISMATCH"
    for field in ("rls", "policies", "grants", "view_security", "definition_hash"):
        if field in expected and actual.get(field) != expected.get(field):
            return "SECURITY_MISMATCH"
    return None


def compare_schema_snapshot(
    expected_snapshot: Dict[str, Any],
    actual_catalog: Optional[Dict[str, Any]],
    *,
    evidence_ref: str = "evidence/schema-diff.json",
) -> SchemaDiffReport:
    expected = expected_snapshot.get("expected_catalog", {})
    expected_counts = {kind: len(expected.get(kind, [])) for kind in CATALOG_KINDS}
    if actual_catalog is None:
        return SchemaDiffReport(
            status=CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB,
            classifications=[
                {
                    "classification": "UNKNOWN_CATALOG",
                    "message": "No read-only pg_catalog snapshot was supplied",
                }
            ],
            evidence_ref=evidence_ref,
            expected_counts=expected_counts,
            actual_counts={kind: 0 for kind in CATALOG_KINDS},
        )

    source = actual_catalog.get("objects", actual_catalog)
    if not isinstance(source, dict):
        return SchemaDiffReport(
            status=CheckStatus.BLOCKED,
            classifications=[
                {
                    "classification": "UNKNOWN_CATALOG",
                    "message": "Actual catalog payload is not an object",
                }
            ],
            evidence_ref=evidence_ref,
            expected_counts=expected_counts,
            actual_counts={kind: 0 for kind in CATALOG_KINDS},
        )

    actual_counts = count_by_kind(source, CATALOG_KINDS)
    diffs: List[Dict[str, Any]] = []
    for kind in CATALOG_KINDS:
        expected_items = _items_by_name(expected.get(kind, []))
        actual_items = _items_by_name(source.get(kind, []))
        for name in sorted(set(expected_items) - set(actual_items)):
            diffs.append({"classification": "MISSING", "object_kind": kind, "name": name})
        for name in sorted(set(actual_items) - set(expected_items)):
            diffs.append({"classification": "EXTRA", "object_kind": kind, "name": name})
        for name in sorted(set(expected_items) & set(actual_items)):
            classification = _compare_structured(expected_items[name], actual_items[name])
            if classification:
                diffs.append({"classification": classification, "object_kind": kind, "name": name})

    return SchemaDiffReport(
        status=CheckStatus.PASS if not diffs else CheckStatus.BLOCKED,
        classifications=diffs,
        evidence_ref=evidence_ref,
        expected_counts=expected_counts,
        actual_counts=actual_counts,
    )
