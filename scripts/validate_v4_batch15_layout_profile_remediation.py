"""Validator for B15-EWP-007 additive layout-profile remediation."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROFILE_CONFIG = ROOT / "config" / "official_odds_cell_extraction" / "layout_profile_remediation_1_1_0.json"
AMENDMENT = ROOT / "config" / "prediction_training" / "v4_batch15_layout_profile_remediation_amendment.json"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "canonical_hash"}
    return "sha256:" + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate() -> list[str]:
    errors: list[str] = []
    profile_config = json.loads(PROFILE_CONFIG.read_text(encoding="utf-8"))
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    if profile_config.get("$id") != "official-odds-layout-profiles@1.1.0":
        errors.append("profile registry identity mismatch")
    if profile_config.get("status") != "FROZEN_ADDITIVE":
        errors.append("profile registry is not additive/frozen")
    if len(profile_config.get("profiles", [])) != 2:
        errors.append("profile registry must contain exactly two profiles")
    if profile_config.get("canonical_hash") not in {"PENDING_RUNTIME_CANONICAL_HASH", canonical_hash(profile_config)}:
        errors.append("profile registry canonical hash mismatch")
    if amendment.get("$id") != "v4-batch15-layout-profile-remediation-amendment@1.0.0":
        errors.append("B15-EWP-007 amendment identity mismatch")
    if amendment.get("canonical_hash") not in {"PENDING_RUNTIME_CANONICAL_HASH", canonical_hash(amendment)}:
        errors.append("B15-EWP-007 amendment canonical hash mismatch")
    package = amendment.get("work_package", {})
    if (package.get("sequence"), package.get("work_package_id"), package.get("dependencies")) != (7, "B15-EWP-007", ["B15-EWP-006"]):
        errors.append("B15-EWP-007 identity/dependency mismatch")
    if package.get("status") != "COMPLETE" or package.get("execution_authorized") is not True:
        errors.append("B15-EWP-007 is not complete/authorized for its declared additive scope")
    boundary = package.get("authorization_boundary", {})
    for key in (
        "ocr_evidence_generation", "full_ocr_replay", "manual_review_value_confirmation", "accepted_official_odds_payload_write",
        "historical_source_archive_write", "archive_record_or_revision_write", "r002_package_generation", "ewp002_rerun",
        "ewp003_rerun", "ewp005_execution_authorized", "v4_076_execution", "v4_052_to_v4_055_execution", "model_fit_or_calibration",
        "production_shadow_public_supabase_migration", "v333_modification",
    ):
        if boundary.get(key) is not False:
            errors.append(f"authorization boundary leaked: {key}")
    if package.get("authorization_boundary", {}).get("profile_detection") is not True or package.get("authorization_boundary", {}).get("geometry_validation") is not True:
        errors.append("permitted profile/geometry scope is not explicit")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("B15-EWP-007 LAYOUT PROFILE REMEDIATION VALIDATION: FAIL")
        print("\n".join(failures))
        sys.exit(1)
    print("B15-EWP-007 LAYOUT PROFILE REMEDIATION VALIDATION: PASS")
    print("OCR/full replay/manual review/r002/archive: NOT AUTHORIZED")
