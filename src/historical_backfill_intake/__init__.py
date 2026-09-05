"""Fail-closed, no-write intake governance for verified historical backfill.

This module is intentionally separate from ``historical_source_archive``.  It
validates an export/staging package and produces a review decision; it never
creates an archive record, changes training counts, or writes a file.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


MANIFEST_CONTRACT = "verified-historical-backfill-import-manifest@1.0.0"
EXPORT_PACKAGE_CONTRACT = "verified-historical-backfill-export-package@1.0.0"
ACQUISITION_MODE = "VERIFIED_HISTORICAL_BACKFILL"
SOURCE_ORIGIN = "CHATGPT_LIBRARY_EXPORT"
STAGING_ROOT = Path("F:/Projects/jcfb-v4/approved_data/historical_backfill_staging")
ARCHIVE_ROOT = Path("F:/Projects/jcfb-v4/approved_data/historical_source_archive")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UNKNOWN = "UNKNOWN"

REVIEW_DECISIONS = frozenset(
    {"PROCEED_TO_EXPORT_INTAKE_VERIFICATION", "REVIEW_REQUIRED", "EXCLUDED", "CONFLICT"}
)
DRY_RUN_STATES = frozenset(
    {"VALID_FOR_INTAKE", "REVIEW_REQUIRED", "REJECTED", "DUPLICATE_NOOP_CANDIDATE", "CONFLICT"}
)
TIMESTAMP_FIELDS = (
    "chatgpt_upload_timestamp",
    "source_timestamp",
    "source_uploaded_at",
    "observed_at",
    "captured_at",
    "exported_at",
    "ingested_at",
    "prediction_cutoff_at",
    "kickoff_at",
)
VOLATILE_PACKAGE_FIELDS = frozenset({"created_at", "exported_at"})
MARKETS = ("SPF", "RQSPF", "EXACT_SCORE", "TOTAL_GOALS", "HTFT")
MARKET_STATES = frozenset({"AVAILABLE", "UNAVAILABLE", "NOT_VERIFIED", "BLOCKED"})
ENGINE_ROLES = ("OUTCOME", "HANDICAP", "GOALS", "HTFT")
ELIGIBILITY_DECISIONS = frozenset({"NOT_YET_EVALUATED", "REVIEW_REQUIRED", "NOT_ELIGIBLE_FOR_AS_OF_TRAINING", "CONFLICT"})


class IntakeValidationError(ValueError):
    """A machine-readable manifest or package contract failure."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise IntakeValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _timestamp(value: Any, field: str, *, allow_unknown: bool = True) -> datetime | None:
    if value == UNKNOWN and allow_unknown:
        return None
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError("TIMESTAMP_REQUIRED", f"{field} must be an ISO-8601 timestamp or UNKNOWN")
    normalized = value.strip()
    if normalized.casefold() == "unknown":
        if allow_unknown:
            return None
        raise IntakeValidationError("TIMESTAMP_UNKNOWN", f"{field} may not be UNKNOWN")
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IntakeValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntakeValidationError("TIMEZONE_REQUIRED", f"{field} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _require_fields(document: Mapping[str, Any], fields: Sequence[str], *, kind: str) -> None:
    for field in fields:
        if field not in document:
            raise IntakeValidationError("REQUIRED_FIELD_MISSING", f"{kind}.{field} is required; use UNKNOWN explicitly where allowed")


def _substantive_body(document: Mapping[str, Any], *, exclude: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in exclude}


def _package_substantive_body(package: Mapping[str, Any]) -> dict[str, Any]:
    body = _substantive_body(package, exclude=frozenset({"package_substantive_hash", "package_sha256", *VOLATILE_PACKAGE_FIELDS}))
    body["manifests"] = [
        {key: value for key, value in manifest.items() if key not in {"export_package_hash", "package_substantive_hash"}}
        if isinstance(manifest, Mapping) else manifest
        for manifest in package.get("manifests", [])
    ]
    return body


def _canonical_match_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = manifest.get("canonical_match_identity")
    if not isinstance(value, Mapping):
        raise IntakeValidationError("MATCH_IDENTITY_REQUIRED", "canonical_match_identity must be an object")
    _require_fields(value, ("canonical_match_id", "competition", "home", "away"), kind="canonical_match_identity")
    for field in ("canonical_match_id", "competition", "home", "away"):
        _text(value.get(field), f"canonical_match_identity.{field}")
    kickoff = manifest.get("kickoff_at")
    if kickoff == UNKNOWN:
        return dict(value)
    return dict(value)


def _detect_candidate_conflicts(manifest: Mapping[str, Any]) -> list[str]:
    conflicts = manifest.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise IntakeValidationError("CONFLICTS_INVALID", "conflicts must be an array")
    reasons = [str(item) for item in conflicts if str(item).strip()]
    extraction = manifest.get("extraction", {})
    if isinstance(extraction, Mapping) and extraction.get("extraction_status") == "CONFLICT":
        reasons.append("EXTRACTION_CONFLICT")
    for group in (
        "image_observed_values",
        "ocr_extracted_values",
        "manual_extracted_values",
        "match_identity_candidates",
        "kickoff_candidates",
        "handicap_candidates",
        "market_availability_candidates",
    ):
        values = manifest.get(group)
        if isinstance(values, list) and len({json.dumps(item, ensure_ascii=False, sort_keys=True) for item in values}) > 1:
            reasons.append(f"{group.upper()}_CONFLICT")
    return list(dict.fromkeys(reasons))


def validate_staging_path(path: str | Path, *, project_root: str | Path = "F:/Projects/jcfb-v4") -> Path:
    root = Path(project_root).resolve()
    staging = Path(path).resolve()
    expected = (root / "approved_data" / "historical_backfill_staging").resolve()
    archive = (root / "approved_data" / "historical_source_archive").resolve()
    if root.drive.upper() != "F:" or staging.drive.upper() != "F:":
        raise IntakeValidationError("F_DRIVE_REQUIRED", "historical backfill staging must be on F:")
    if staging == archive or archive in staging.parents:
        raise IntakeValidationError("ARCHIVE_ROOT_FORBIDDEN", "historical staging must remain separate from final archive")
    try:
        staging.relative_to(expected)
    except ValueError as exc:
        raise IntakeValidationError("STAGING_ROOT_INVALID", f"staging path must remain below {expected}") from exc
    return staging


def evaluate_timestamp_evidence(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Apply upload-time evidence without treating upload time as source time."""
    upload = _timestamp(manifest.get("chatgpt_upload_timestamp"), "chatgpt_upload_timestamp")
    kickoff = _timestamp(manifest.get("kickoff_at"), "kickoff_at")
    if upload is None:
        return {
            "status": "REVIEW_REQUIRED",
            "as_of_training_decision": "REVIEW_REQUIRED",
            "reason_codes": ["CHATGPT_UPLOAD_TIMESTAMP_UNKNOWN"],
            "import_action": "NOT_PERFORMED",
        }
    if kickoff is None:
        return {
            "status": "REVIEW_REQUIRED",
            "as_of_training_decision": "REVIEW_REQUIRED",
            "reason_codes": ["KICKOFF_TIMESTAMP_UNKNOWN"],
            "import_action": "NOT_PERFORMED",
        }
    if upload >= kickoff:
        return {
            "status": "NOT_ELIGIBLE_FOR_AS_OF_TRAINING",
            "as_of_training_decision": "NOT_ELIGIBLE_FOR_AS_OF_TRAINING",
            "reason_codes": ["UPLOAD_AT_OR_AFTER_KICKOFF"],
            "import_action": "NOT_PERFORMED",
        }
    return {
        "status": "PROCEED_TO_EXPORT_INTAKE_VERIFICATION",
        "as_of_training_decision": "REVIEW_REQUIRED",
        "reason_codes": ["UPLOAD_BEFORE_KICKOFF_ONLY_PROVES_EXISTENCE_BY_UPLOAD_TIME"],
        "import_action": "NOT_PERFORMED",
    }


def _validate_official_coverage(manifest: Mapping[str, Any]) -> None:
    coverage = manifest.get("official_play_coverage")
    if not isinstance(coverage, Mapping):
        raise IntakeValidationError("OFFICIAL_COVERAGE_REQUIRED", "official_play_coverage must be an object")
    for market in MARKETS:
        item = coverage.get(market)
        if not isinstance(item, Mapping):
            raise IntakeValidationError("MARKET_COVERAGE_REQUIRED", f"official_play_coverage.{market} is required")
        state = item.get("state")
        if state not in MARKET_STATES:
            raise IntakeValidationError("MARKET_STATE_INVALID", f"official_play_coverage.{market}.state is invalid")
        if state == "UNAVAILABLE" and not isinstance(item.get("unavailable_reason"), str):
            raise IntakeValidationError("MARKET_UNAVAILABLE_REASON_REQUIRED", f"{market} unavailable reason is required")


def _engine_eligibility(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    coverage = manifest["official_play_coverage"]
    result: dict[str, dict[str, Any]] = {}
    spf_available = coverage["SPF"].get("state") == "AVAILABLE"
    rqspf = coverage["RQSPF"]
    exact_rqspf = rqspf.get("state") == "AVAILABLE" and bool(rqspf.get("exact_cutoff_visible")) and bool(rqspf.get("handicap_line"))
    goals_available = coverage["TOTAL_GOALS"].get("state") == "AVAILABLE"
    htft = coverage["HTFT"]
    htft_available = htft.get("state") == "AVAILABLE" and bool(htft.get("halftime_label")) and bool(htft.get("fulltime_label"))
    result["OUTCOME"] = {"status": "ELIGIBLE_FOR_REVIEW" if spf_available else "REVIEW_REQUIRED", "reason_codes": [] if spf_available else ["SPF_NOT_AVAILABLE"]}
    result["HANDICAP"] = {"status": "ELIGIBLE_FOR_REVIEW" if exact_rqspf else "REVIEW_REQUIRED", "reason_codes": [] if exact_rqspf else ["EXACT_CUTOFF_VISIBLE_RQSPF_LINE_REQUIRED"]}
    result["GOALS"] = {"status": "ELIGIBLE_FOR_REVIEW" if goals_available else "REVIEW_REQUIRED", "reason_codes": [] if goals_available else ["TOTAL_GOALS_NOT_AVAILABLE"]}
    result["HTFT"] = {"status": "ELIGIBLE_FOR_REVIEW" if htft_available else "REVIEW_REQUIRED", "reason_codes": [] if htft_available else ["HALFTIME_AND_FULLTIME_LABEL_REQUIRED"]}
    return result


def validate_manifest(manifest: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    required = (
        "manifest_id", "import_batch_id", "revision", "acquisition_mode", "source_origin", "export_package_id",
        "export_package_hash", "external_source_identity", "original_filename", "original_file_sha256",
        "metadata_snapshot_sha256", "source_type", "source_identity", "source_reference", "timestamp_evidence_basis",
        "canonical_match_identity", "intended_cutoff_profile", "official_play_coverage", "extraction", "artifact_classification",
        "review_decision", "eligibility_decision", "revision_lineage", "artifact_substantive_hash",
        "provenance_root", "reviewer", "reviewed_at", "package_substantive_hash", "manifest_substantive_hash",
        *TIMESTAMP_FIELDS,
    )
    _require_fields(manifest, required, kind="manifest")
    if manifest.get("acquisition_mode") != ACQUISITION_MODE:
        raise IntakeValidationError("ACQUISITION_MODE_INVALID", "historical candidates require VERIFIED_HISTORICAL_BACKFILL")
    if manifest.get("source_origin") != SOURCE_ORIGIN:
        raise IntakeValidationError("SOURCE_ORIGIN_INVALID", "source_origin must be CHATGPT_LIBRARY_EXPORT")
    if not isinstance(manifest.get("revision"), int) or manifest["revision"] < 1:
        raise IntakeValidationError("REVISION_INVALID", "revision must be a positive integer")
    _text(manifest.get("manifest_id"), "manifest_id")
    _text(manifest.get("import_batch_id"), "import_batch_id")
    _text(manifest.get("export_package_id"), "export_package_id")
    _hash(manifest.get("export_package_hash"), "export_package_hash")
    _hash(manifest.get("original_file_sha256"), "original_file_sha256")
    _hash(manifest.get("metadata_snapshot_sha256"), "metadata_snapshot_sha256")
    _hash(manifest.get("artifact_substantive_hash"), "artifact_substantive_hash")
    _hash(manifest.get("provenance_root"), "provenance_root")
    _hash(manifest.get("package_substantive_hash"), "package_substantive_hash")
    _hash(manifest.get("manifest_substantive_hash"), "manifest_substantive_hash")
    for field in TIMESTAMP_FIELDS:
        _timestamp(manifest.get(field), field)
    identity = manifest["external_source_identity"]
    if not isinstance(identity, Mapping):
        raise IntakeValidationError("EXTERNAL_IDENTITY_REQUIRED", "external_source_identity must be an object")
    _require_fields(identity, ("provider", "library_file_id_or_ref"), kind="external_source_identity")
    _text(identity.get("provider"), "external_source_identity.provider")
    _text(identity.get("library_file_id_or_ref"), "external_source_identity.library_file_id_or_ref")
    _canonical_match_identity(manifest)
    _text(manifest.get("original_filename"), "original_filename")
    _text(manifest.get("source_type"), "source_type")
    _text(manifest.get("source_identity"), "source_identity")
    _text(manifest.get("source_reference"), "source_reference")
    _text(manifest.get("timestamp_evidence_basis"), "timestamp_evidence_basis")
    _text(manifest.get("intended_cutoff_profile"), "intended_cutoff_profile")
    _text(manifest.get("reviewer"), "reviewer")
    _timestamp(manifest.get("reviewed_at"), "reviewed_at", allow_unknown=False)
    extraction = manifest["extraction"]
    if not isinstance(extraction, Mapping):
        raise IntakeValidationError("EXTRACTION_REQUIRED", "extraction must be an object")
    _require_fields(extraction, ("extraction_method", "extraction_status", "extracted_market_payload"), kind="extraction")
    _text(extraction.get("extraction_method"), "extraction.extraction_method")
    _text(extraction.get("extraction_status"), "extraction.extraction_status")
    if not isinstance(extraction.get("extracted_market_payload"), Mapping):
        raise IntakeValidationError("EXTRACTION_PAYLOAD_REQUIRED", "extracted_market_payload must be an object")
    _validate_official_coverage(manifest)
    if manifest.get("review_decision") not in REVIEW_DECISIONS:
        raise IntakeValidationError("REVIEW_DECISION_INVALID", "review_decision is outside the frozen review vocabulary")
    lineage = manifest["revision_lineage"]
    if not isinstance(lineage, Mapping) or "supersedes" not in lineage:
        raise IntakeValidationError("REVISION_LINEAGE_REQUIRED", "revision_lineage.supersedes is required and may be null")
    if manifest["revision"] == 1 and lineage.get("supersedes") is not None:
        raise IntakeValidationError("REVISION_LINEAGE_INVALID", "revision 1 cannot supersede another manifest")
    if manifest["revision"] > 1 and not isinstance(lineage.get("supersedes"), str):
        raise IntakeValidationError("SUPERSEDES_REQUIRED", "revisions after r001 require supersedes")
    artifact_class = manifest.get("artifact_classification")
    if artifact_class != "RAW_FACT" or manifest.get("generated_artifact") is True:
        raise IntakeValidationError("GENERATED_ARTIFACT_EXCLUDED", "generated predictions, dashboards, slips, and recommendations are excluded")
    if manifest.get("eligibility_decision") not in ELIGIBILITY_DECISIONS:
        raise IntakeValidationError("ELIGIBILITY_DECISION_INVALID", "eligibility_decision cannot invent an archive approval state")
    conflicts = _detect_candidate_conflicts(manifest)
    if verify_hash:
        expected = sha256_json(_substantive_body(manifest, exclude=frozenset({"manifest_substantive_hash", "exported_at", "export_package_hash"})))
        if manifest["manifest_substantive_hash"] != expected:
            raise IntakeValidationError("MANIFEST_HASH_MISMATCH", "manifest_substantive_hash does not match canonical substantive fields")
    timestamp = evaluate_timestamp_evidence(manifest)
    engines = _engine_eligibility(manifest)
    if conflicts:
        timestamp = dict(timestamp, status="CONFLICT", reason_codes=conflicts)
    return {"manifest_id": manifest["manifest_id"], "timestamp_evidence": timestamp, "engine_eligibility": engines, "conflicts": conflicts}


def validate_export_package(package: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    _require_fields(package, ("export_package_id", "revision", "contract_version", "source_origin", "created_at", "exported_at", "file_manifest", "metadata_manifest", "manifests", "package_substantive_hash", "package_sha256"), kind="export_package")
    if package.get("contract_version") != EXPORT_PACKAGE_CONTRACT:
        raise IntakeValidationError("PACKAGE_CONTRACT_INVALID", "wrong export package contract")
    if package.get("source_origin") != SOURCE_ORIGIN:
        raise IntakeValidationError("SOURCE_ORIGIN_INVALID", "package source_origin must be CHATGPT_LIBRARY_EXPORT")
    if not isinstance(package.get("revision"), int) or package["revision"] < 1:
        raise IntakeValidationError("REVISION_INVALID", "package revision must be positive")
    for field in ("created_at", "exported_at"):
        _timestamp(package[field], field, allow_unknown=False)
    files = package["file_manifest"]
    metadata = package["metadata_manifest"]
    manifests = package["manifests"]
    if not isinstance(files, list) or not files:
        raise IntakeValidationError("FILE_MANIFEST_REQUIRED", "file_manifest must contain at least one file")
    if not isinstance(metadata, list) or len(metadata) != len(files):
        raise IntakeValidationError("METADATA_MANIFEST_MISMATCH", "metadata_manifest must have one entry per file")
    if not isinstance(manifests, list) or len(manifests) != len(files):
        raise IntakeValidationError("MANIFEST_FILE_MISMATCH", "one import manifest is required per file")
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            raise IntakeValidationError("FILE_MANIFEST_INVALID", f"file_manifest[{index}] must be an object")
        _require_fields(item, ("manifest_id", "original_filename", "original_file_sha256", "library_file_id_or_ref"), kind=f"file_manifest[{index}]")
        _hash(item["original_file_sha256"], f"file_manifest[{index}].original_file_sha256")
        _text(item["library_file_id_or_ref"], f"file_manifest[{index}].library_file_id_or_ref")
        metadata_item = metadata[index]
        if not isinstance(metadata_item, Mapping):
            raise IntakeValidationError("METADATA_MANIFEST_INVALID", f"metadata_manifest[{index}] must be an object")
        _require_fields(metadata_item, ("manifest_id", "metadata_snapshot_sha256"), kind=f"metadata_manifest[{index}]")
        _hash(metadata_item["metadata_snapshot_sha256"], f"metadata_manifest[{index}].metadata_snapshot_sha256")
        result = validate_manifest(manifests[index], verify_hash=verify_hash)
        if manifests[index]["manifest_id"] != item["manifest_id"] or manifests[index]["original_file_sha256"] != item["original_file_sha256"]:
            raise IntakeValidationError("FILE_MANIFEST_BINDING_INVALID", f"file_manifest[{index}] does not bind its manifest")
        if manifests[index]["manifest_id"] != metadata_item["manifest_id"] or manifests[index]["metadata_snapshot_sha256"] != metadata_item["metadata_snapshot_sha256"]:
            raise IntakeValidationError("METADATA_MANIFEST_BINDING_INVALID", f"metadata_manifest[{index}] does not bind its manifest")
        if manifests[index]["export_package_hash"] != package["package_substantive_hash"]:
            raise IntakeValidationError("PACKAGE_MANIFEST_BINDING_INVALID", f"manifest {manifests[index]['manifest_id']} is bound to another package")
        if result["timestamp_evidence"]["status"] == "CONFLICT":
            raise IntakeValidationError("PACKAGE_CONFLICT", f"manifest {manifests[index]['manifest_id']} has conflicts")
    _hash(package["package_substantive_hash"], "package_substantive_hash")
    _hash(package["package_sha256"], "package_sha256")
    if verify_hash:
        body = _package_substantive_body(package)
        if package["package_substantive_hash"] != sha256_json(body):
            raise IntakeValidationError("PACKAGE_SUBSTANTIVE_HASH_MISMATCH", "package_substantive_hash does not match canonical substantive fields")
        package_bytes_body = _substantive_body(package, exclude=frozenset({"package_sha256"}))
        if package["package_sha256"] != sha256_json(package_bytes_body):
            raise IntakeValidationError("PACKAGE_SHA256_MISMATCH", "package_sha256 does not match package contents")
    return {"manifest_count": len(manifests), "package_id": package["export_package_id"]}


def duplicate_semantics(existing: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    same_bytes = existing.get("original_file_sha256") == candidate.get("original_file_sha256")
    same_source = existing.get("external_source_identity") == candidate.get("external_source_identity")
    same_match = existing.get("canonical_match_identity") == candidate.get("canonical_match_identity")
    same_payload = existing.get("extraction", {}).get("extracted_market_payload") == candidate.get("extraction", {}).get("extracted_market_payload")
    same_observation = existing.get("chatgpt_upload_timestamp") == candidate.get("chatgpt_upload_timestamp")
    if same_bytes and same_source and same_match and same_payload and same_observation:
        return "DUPLICATE_NOOP"
    if same_bytes and same_source:
        return "SAME_BYTES_DIFFERENT_EXTERNAL_OBSERVATION"
    if same_match:
        return "RETAIN_AS_DISTINCT_SNAPSHOT"
    return "DISTINCT_ARTIFACT"


def dry_run_validate(package: Mapping[str, Any], *, staging_path: str | Path = STAGING_ROOT) -> dict[str, Any]:
    """Validate a future staging package; this function has no write path."""
    try:
        validate_staging_path(staging_path)
        validate_export_package(package)
    except IntakeValidationError as exc:
        state = "CONFLICT" if exc.code in {"PACKAGE_CONFLICT", "TIMESTAMP_FIELD_SUBSTITUTION"} else "REJECTED"
        return {"state": state, "write_performed": False, "reason_codes": [exc.code], "message": exc.message}
    decisions = [evaluate_timestamp_evidence(item)["status"] for item in package["manifests"]]
    if any(decision == "NOT_ELIGIBLE_FOR_AS_OF_TRAINING" for decision in decisions):
        return {"state": "REVIEW_REQUIRED", "write_performed": False, "reason_codes": ["ONE_OR_MORE_MANIFESTS_NOT_ELIGIBLE_FOR_AS_OF_TRAINING"]}
    if any(decision == "REVIEW_REQUIRED" for decision in decisions):
        return {"state": "REVIEW_REQUIRED", "write_performed": False, "reason_codes": ["TIMESTAMP_REVIEW_REQUIRED"]}
    return {"state": "VALID_FOR_INTAKE", "write_performed": False, "reason_codes": ["EXPORT_PACKAGE_VALID_FOR_SEPARATE_INTAKE_AUTHORIZATION"]}


__all__ = [
    "ACQUISITION_MODE", "ARCHIVE_ROOT", "DRY_RUN_STATES", "EXPORT_PACKAGE_CONTRACT", "IntakeValidationError",
    "MANIFEST_CONTRACT", "SOURCE_ORIGIN", "STAGING_ROOT", "UNKNOWN", "canonical_json_bytes", "duplicate_semantics",
    "dry_run_validate", "evaluate_timestamp_evidence", "sha256_bytes", "sha256_json", "validate_export_package",
    "validate_manifest", "validate_staging_path",
]
