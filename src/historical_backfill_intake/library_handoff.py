"""ChatGPT Library backfill handoff and candidate-manifest intake helpers.

This contract describes what may arrive from the ChatGPT Library. It does not
claim that the bytes exist, and it never writes the historical archive.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from . import IntakeValidationError, sha256_json
from .staging import canonical_identity_key


HANDOFF_CONTRACT = "chatgpt-library-backfill-handoff@1.0.0"
CANDIDATE_MANIFEST_CONTRACT = "chatgpt-library-backfill-candidate-manifest@1.0.0"
SOURCE_TYPES = {"RAW_SCREENSHOT", "AUDITABLE_DERIVATIVE", "POSTMATCH_RESULT_EVIDENCE", "STRUCTURED_OFFICIAL_ODDS_CANDIDATE"}
MARKETS = {"SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HTFT"}
PROVENANCE_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
TIMESTAMP_SEMANTICS = {"CREATED", "UPLOADED", "CAPTURED", "PUBLISHED", "OBSERVED", "UNKNOWN"}


def _require_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise IntakeValidationError("HANDOFF_HASH_INVALID", field)


def _require_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError("HANDOFF_FIELD_INVALID", field)


def validate_candidate_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    required = ("candidate_id", "file_id_or_external_ref", "filename", "sha256", "timestamp_semantics", "match_identity_candidate", "market_coverage", "source_type", "provenance_confidence", "eligible_for_raw_reingestion", "excluded_reasons")
    for field in required:
        if field not in candidate:
            raise IntakeValidationError("CANDIDATE_FIELD_MISSING", field)
    for field in ("candidate_id", "file_id_or_external_ref", "filename"):
        _require_text(candidate[field], field)
    _require_hash(candidate["sha256"], "sha256")
    if candidate["timestamp_semantics"] not in TIMESTAMP_SEMANTICS:
        raise IntakeValidationError("TIMESTAMP_SEMANTICS_INVALID", str(candidate["candidate_id"]))
    if not isinstance(candidate["market_coverage"], list) or any(item not in MARKETS for item in candidate["market_coverage"]):
        raise IntakeValidationError("MARKET_COVERAGE_INVALID", str(candidate["candidate_id"]))
    if candidate["source_type"] not in SOURCE_TYPES:
        raise IntakeValidationError("SOURCE_TYPE_INVALID", str(candidate["candidate_id"]))
    if candidate["provenance_confidence"] not in PROVENANCE_CONFIDENCE:
        raise IntakeValidationError("PROVENANCE_CONFIDENCE_INVALID", str(candidate["candidate_id"]))
    if not isinstance(candidate["eligible_for_raw_reingestion"], bool):
        raise IntakeValidationError("RAW_REINGESTION_FLAG_INVALID", str(candidate["candidate_id"]))
    if not isinstance(candidate["excluded_reasons"], list) or any(not isinstance(item, str) for item in candidate["excluded_reasons"]):
        raise IntakeValidationError("EXCLUDED_REASONS_INVALID", str(candidate["candidate_id"]))
    identity = candidate["match_identity_candidate"]
    if not isinstance(identity, Mapping):
        raise IntakeValidationError("MATCH_IDENTITY_CANDIDATE_INVALID", str(candidate["candidate_id"]))
    identity_status = identity.get("status", "UNVERIFIED")
    if identity_status == "EXPLICIT":
        canonical_identity_key(identity)
    elif identity_status not in {"UNVERIFIED", "AMBIGUOUS", "REJECTED"}:
        raise IntakeValidationError("MATCH_IDENTITY_STATUS_INVALID", str(candidate["candidate_id"]))
    if candidate["eligible_for_raw_reingestion"] and candidate["source_type"] not in {"RAW_SCREENSHOT", "AUDITABLE_DERIVATIVE"}:
        raise IntakeValidationError("RAW_REINGESTION_SOURCE_TYPE_INVALID", str(candidate["candidate_id"]))
    return {"candidate_id": candidate["candidate_id"], "identity_status": identity_status, "eligible": candidate["eligible_for_raw_reingestion"]}


def validate_candidate_manifest(candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(candidates)
    seen: set[str] = set()
    summaries: list[dict[str, Any]] = []
    for candidate in rows:
        result = validate_candidate_record(candidate)
        if result["candidate_id"] in seen:
            raise IntakeValidationError("CANDIDATE_ID_DUPLICATE", result["candidate_id"])
        seen.add(result["candidate_id"])
        summaries.append(result)
    return {"candidate_count": len(rows), "eligible_count": sum(1 for item in summaries if item["eligible"]), "status_counts": dict(Counter(item["identity_status"] for item in summaries))}


def validate_handoff(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("contract_identity") != HANDOFF_CONTRACT:
        raise IntakeValidationError("HANDOFF_CONTRACT_INVALID", str(manifest.get("contract_identity")))
    _require_text(manifest.get("handoff_id"), "handoff_id")
    if manifest.get("source_origin") != "CHATGPT_LIBRARY_EXPORT_PENDING_LOCAL_MATERIALIZATION":
        raise IntakeValidationError("HANDOFF_SOURCE_ORIGIN_INVALID", str(manifest.get("source_origin")))
    if manifest.get("archive_write_allowed") is not False or manifest.get("training_write_allowed") is not False:
        raise IntakeValidationError("HANDOFF_WRITE_BOUNDARY_INVALID", "archive/training must remain false")
    artifacts = manifest.get("source_artifacts")
    if not isinstance(artifacts, list):
        raise IntakeValidationError("SOURCE_ARTIFACTS_INVALID", "source_artifacts")
    for artifact in artifacts:
        if artifact.get("role") not in {"RAW_SCREENSHOT", "AUDITABLE_DERIVATIVE", "POSTMATCH_RESULT_EVIDENCE"}:
            raise IntakeValidationError("SOURCE_ARTIFACT_ROLE_INVALID", str(artifact.get("artifact_id")))
        _require_text(artifact.get("artifact_id"), "source_artifacts.artifact_id")
        if artifact.get("sha256") != "UNKNOWN":
            _require_hash(artifact.get("sha256"), "source_artifacts.sha256")
    candidate_result = validate_candidate_manifest(manifest.get("candidate_manifest", []))
    if manifest.get("distinct_match_target", 0) != 99:
        raise IntakeValidationError("DISTINCT_MATCH_TARGET_INVALID", str(manifest.get("distinct_match_target")))
    return {"contract_identity": HANDOFF_CONTRACT, "source_artifact_count": len(artifacts), **candidate_result, "status": "VALIDATED_INTAKE_SCHEMA_ONLY"}


def candidate_dedupe_key(candidate: Mapping[str, Any]) -> str:
    identity = candidate.get("match_identity_candidate", {})
    identity_key = canonical_identity_key(identity) if identity.get("status") == "EXPLICIT" else "UNVERIFIED"
    return sha256_json({
        "raw_bytes_sha256": candidate.get("sha256"),
        "external_source_identity": candidate.get("file_id_or_external_ref"),
        "canonical_match_identity": identity_key,
        "observation_timestamp": candidate.get("observation_timestamp", "UNKNOWN"),
        "extracted_market_payload_hash": candidate.get("extracted_market_payload_hash", "UNKNOWN"),
    })


def build_candidate_dedupe_index(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate_dedupe_key(candidate)
        duplicate_of = seen.get(key)
        result.append({"candidate_id": candidate.get("candidate_id"), "dedupe_key": key, "duplicate_of_candidate_id": duplicate_of})
        if duplicate_of is None:
            seen[key] = str(candidate.get("candidate_id"))
    return result


__all__ = ["CANDIDATE_MANIFEST_CONTRACT", "HANDOFF_CONTRACT", "build_candidate_dedupe_index", "candidate_dedupe_key", "validate_candidate_manifest", "validate_candidate_record", "validate_handoff"]
