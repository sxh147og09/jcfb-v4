"""Focused no-write validator for B15-EWP-001-ADDENDUM-002."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
sys.path.insert(0, str(ROOT))

from src.historical_backfill_intake import ARCHIVE_ROOT, STAGING_ROOT, sha256_json, validate_staging_path
from src.historical_backfill_intake.package_contract import (
    EXCLUSION_MANIFEST_SCHEMA,
    PACKAGE_CONTRACT_V1_0,
    PACKAGE_CONTRACT_V1_1,
    ZIP_PROFILE,
    run_synthetic_validation,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> list[str]:
    failures: list[str] = []
    schema_path = CONFIG / "v4_batch15_verified_historical_backfill_export_package_schema_1_1_0.json"
    amendment_path = CONFIG / "v4_batch15_verified_historical_backfill_contract_amendment_002.json"
    base_schema_path = CONFIG / "v4_batch15_verified_historical_backfill_export_package_schema.json"
    base_contract_path = CONFIG / "v4_batch15_verified_historical_backfill_contract.json"
    schema = load(schema_path)
    amendment = load(amendment_path)
    base_schema = load(base_schema_path)
    base_contract = load(base_contract_path)
    for name, document in ((schema_path.name, schema), (amendment_path.name, amendment)):
        expected = sha256_json({key: value for key, value in document.items() if key != "canonical_hash"})
        if document.get("canonical_hash") != expected:
            failures.append(f"CANONICAL_HASH_MISMATCH: {name}")
    if schema.get("$id") != PACKAGE_CONTRACT_V1_1 or schema.get("base_contract") != PACKAGE_CONTRACT_V1_0:
        failures.append("PACKAGE_CONTRACT_VERSION_LINEAGE_INVALID")
    if schema.get("zip_serialization_profile", {}).get("profile_id") != ZIP_PROFILE:
        failures.append("ZIP_PROFILE_NOT_BOUND")
    if schema.get("exclusion_manifest", {}).get("schema_identity") != EXCLUSION_MANIFEST_SCHEMA:
        failures.append("EXCLUSION_SCHEMA_NOT_BOUND")
    if not schema.get("frozen_base_semantics_unchanged") or schema.get("compatibility") != "MINOR_COMPATIBLE":
        failures.append("BASE_CONTRACT_COMPATIBILITY_INVALID")
    if amendment.get("amendment_id") != "B15-EWP-001-ADDENDUM-002" or amendment.get("amendment_revision") != "r002":
        failures.append("AMENDMENT_IDENTITY_INVALID")
    if amendment.get("reopens_completed_work_package") is not False or amendment.get("additive_only") is not True:
        failures.append("ADDITIVE_BOUNDARY_INVALID")
    if base_schema.get("$id") != PACKAGE_CONTRACT_V1_0 or base_contract.get("amendment_revision") != "r001":
        failures.append("FROZEN_BASE_ARTIFACT_CHANGED_OR_MISBOUND")
    try:
        validate_staging_path(STAGING_ROOT)
    except Exception as exc:
        failures.append(f"F_DRIVE_STAGING_INVALID: {exc}")
    archive_files = [path for path in ARCHIVE_ROOT.rglob("*") if path.is_file()]
    if archive_files:
        failures.append("ARCHIVE_WRITE_DETECTED: " + ", ".join(str(path) for path in archive_files))
    if not STAGING_ROOT.is_dir():
        failures.append("STAGING_ROOT_MISSING")
    try:
        synthetic = run_synthetic_validation()
        if not synthetic.get("package_substantive_hash") or not synthetic.get("package_zip_sha256"):
            failures.append("SYNTHETIC_HASHES_MISSING")
    except Exception as exc:
        failures.append(f"SYNTHETIC_VALIDATION_FAILED: {exc}")
    readiness = load(CONFIG / "v4_prediction_training_readiness_review.json")
    if readiness.get("decision") != "PREDICTION_TRAINING_READINESS_BLOCKED":
        failures.append("TRAINING_READINESS_CHANGED")
    if readiness.get("historical_as_of_dataset", {}).get("candidate_sample_count") != 0 or readiness.get("historical_as_of_dataset", {}).get("usable_training_sample_count") != 0:
        failures.append("TRAINING_SAMPLE_COUNTS_CHANGED")
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 EXPORT PACKAGE ADDENDUM-002 VALIDATION: FAIL")
        print("\n".join(errors))
        raise SystemExit(1)
    print("V4 BATCH-15 EXPORT PACKAGE ADDENDUM-002 VALIDATION: PASS")
    print("Deterministic ZIP: v4-deterministic-zip@1.0 / ZIP32 / STORED / UTF-8 / fixed DOS metadata")
    print("Exclusion manifest: required / bound / included in package substantive hash")
    print("Archive write: FORBIDDEN / archive remains empty")
    print("Training readiness: BLOCKED / TRAINING_DATA_INSUFFICIENT")
