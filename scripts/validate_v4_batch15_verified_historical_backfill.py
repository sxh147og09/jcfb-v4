"""No-write validator for the B15-EWP-001 historical backfill addendum."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
sys.path.insert(0, str(ROOT))

from src.historical_backfill_intake import ARCHIVE_ROOT, STAGING_ROOT, sha256_json, validate_staging_path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "canonical_hash"}
    return sha256_json(body)


def validate() -> list[str]:
    failures: list[str] = []
    schema_paths = (
        CONFIG / "v4_batch15_verified_historical_backfill_import_manifest_schema.json",
        CONFIG / "v4_batch15_verified_historical_backfill_export_package_schema.json",
        CONFIG / "v4_batch15_verified_historical_backfill_contract.json",
    )
    for path in schema_paths:
        if not path.is_file():
            failures.append(f"MISSING_CONTRACT: {path.name}")
            continue
        document = load(path)
        if document.get("canonical_hash", "").startswith("sha256:PLACEHOLDER"):
            failures.append(f"PLACEHOLDER_HASH: {path.name}")
        elif document.get("canonical_hash") != canonical_hash(document):
            failures.append(f"CANONICAL_HASH_MISMATCH: {path.name}")

    import_schema = load(CONFIG / "v4_batch15_verified_historical_backfill_import_manifest_schema.json")
    export_schema = load(CONFIG / "v4_batch15_verified_historical_backfill_export_package_schema.json")
    amendment = load(CONFIG / "v4_batch15_verified_historical_backfill_contract.json")
    if amendment.get("amends") != "B15-EWP-001" or amendment.get("amendment_revision") != "r001":
        failures.append("AMENDMENT_IDENTITY_INVALID")
    if amendment.get("reopens_completed_work_package") is not False or amendment.get("historical_fact_preservation", {}).get("additive_only") is not True:
        failures.append("EWP001_REOPEN_OR_REWRITE_BOUNDARY_INVALID")
    if amendment.get("contracts", {}).get("import_manifest") != import_schema.get("$id"):
        failures.append("IMPORT_SCHEMA_BINDING_INVALID")
    if amendment.get("contracts", {}).get("export_package") != export_schema.get("$id"):
        failures.append("EXPORT_SCHEMA_BINDING_INVALID")

    try:
        validate_staging_path(STAGING_ROOT)
    except Exception as exc:  # pragma: no cover - exact exception is covered by focused tests
        failures.append(f"F_DRIVE_STAGING_INVALID: {exc}")
    if STAGING_ROOT.resolve() == ARCHIVE_ROOT.resolve():
        failures.append("STAGING_ARCHIVE_COLLISION")
    if not STAGING_ROOT.is_dir():
        failures.append("STAGING_ROOT_MISSING")
    archive_files = [path for path in ARCHIVE_ROOT.rglob("*") if path.is_file()]
    if archive_files:
        failures.append("ARCHIVE_WRITE_DETECTED: " + ", ".join(str(path) for path in archive_files))

    registry = load(CONFIG / "v4_batch15_execution_work_package_registry.json")
    packages = registry.get("work_packages", [])
    if len(packages) != 5:
        failures.append("EWP_REGISTRY_CARDINALITY_CHANGED")
    else:
        if packages[0].get("status") != "COMPLETE" or packages[0].get("revision") != "r002" or packages[0].get("execution_authorized") is not True:
            failures.append("EWP001_COMPLETE_FACT_NOT_PRESERVED")
        if packages[4].get("execution_authorized") is not False:
            failures.append("EWP005_AUTHORIZATION_LEAKED")

    readiness = load(CONFIG / "v4_prediction_training_readiness_review.json")
    if readiness.get("decision") != "PREDICTION_TRAINING_READINESS_BLOCKED":
        failures.append("TRAINING_READINESS_CHANGED")
    if readiness.get("historical_as_of_dataset", {}).get("candidate_sample_count") != 0:
        failures.append("CURRENT_CANDIDATE_SAMPLE_COUNT_CHANGED")
    if readiness.get("historical_as_of_dataset", {}).get("usable_training_sample_count") != 0:
        failures.append("CURRENT_USABLE_SAMPLE_COUNT_CHANGED")

    changed = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "HEAD"], check=True, capture_output=True, text=True).stdout.splitlines()
    forbidden = [path for path in changed if path.startswith(("database/", "tools/")) or "v3.3.3" in path.lower() or "v333" in path.lower() or "supabase" in path.lower()]
    if forbidden:
        failures.append("FORBIDDEN_CHANGED_PATHS: " + ", ".join(forbidden))
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 VERIFIED HISTORICAL BACKFILL VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 VERIFIED HISTORICAL BACKFILL VALIDATION: PASS")
    print("Acquisition mode: VERIFIED_HISTORICAL_BACKFILL / separate staging entrypoint")
    print("Archive write: FORBIDDEN / archive remains empty")
    print("Training readiness: BLOCKED / TRAINING_DATA_INSUFFICIENT")
    print("EWP-005 execution_authorized: false")
