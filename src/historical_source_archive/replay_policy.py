"""Historical artifact reconstruction path selection.

The selector is deliberately pure.  It never writes archive records and never
constructs a training dataset.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import HASH_RE, sha256_json


REPLAY_REQUIRED = (
    "raw_cutoff_visible_inputs_complete",
    "exact_generator_version",
    "exact_generator_implementation_hash",
    "exact_config_version",
    "exact_config_hash",
    "exact_mapping_version",
    "exact_mapping_hash",
    "source_timestamps_valid",
    "no_post_cutoff_revision",
)


def _stored_acceptance_reasons(artifact: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if artifact.get("capture_state") != "CAPTURED":
        reasons.append("STORED_ARTIFACT_NOT_CAPTURED")
    if artifact.get("eligibility_state") != "ELIGIBLE_FOR_AS_OF_TRAINING":
        reasons.append("STORED_ARTIFACT_NOT_ACCEPTED")
    if not artifact.get("archive_record_id"):
        reasons.append("EXACT_REF_MISSING")
    if not isinstance(artifact.get("artifact_hash"), str) or not HASH_RE.fullmatch(artifact["artifact_hash"]):
        reasons.append("EXACT_HASH_MISSING")
    if not isinstance(artifact.get("revision"), int) or artifact["revision"] < 1:
        reasons.append("REVISION_MISSING")
    return reasons


def select_reconstruction_path(artifact: Mapping[str, Any], replay_context: Mapping[str, Any]) -> dict[str, Any]:
    """Prefer stored accepted artifacts; permit replay only with exact lineage."""

    stored_reasons = _stored_acceptance_reasons(artifact)
    if not stored_reasons:
        return {
            "path": "STORED_ACCEPTED_ARTIFACT",
            "status": "ELIGIBLE_FOR_AS_OF_TRAINING",
            "archive_record_id": artifact["archive_record_id"],
            "artifact_hash": artifact["artifact_hash"],
            "revision": artifact["revision"],
            "replay_performed": False,
            "reasons": [],
        }
    reasons: list[str] = [f"STORED_PATH_UNAVAILABLE:{reason}" for reason in stored_reasons]
    if replay_context.get("used_latest_generator") is True or replay_context.get("used_latest_config") is True:
        reasons.append("LATEST_GENERATOR_OR_CONFIG_FORBIDDEN")
    for key in REPLAY_REQUIRED:
        if replay_context.get(key) is not True:
            reasons.append(f"REPLAY_PROOF_MISSING:{key}")
    for key in ("exact_generator_implementation_hash", "exact_config_hash", "exact_mapping_hash"):
        if replay_context.get(key) is not True:
            continue
        supplied_hash = replay_context.get(f"{key}_value")
        if supplied_hash is not None and not HASH_RE.fullmatch(str(supplied_hash)):
            reasons.append(f"REPLAY_HASH_INVALID:{key}")
    if reasons == [f"STORED_PATH_UNAVAILABLE:{reason}" for reason in stored_reasons]:
        reasons.append("REPLAY_NOT_SELECTED")
    if any(reason.startswith("LATEST_") or reason.startswith("REPLAY_PROOF_MISSING") or reason.startswith("REPLAY_HASH_INVALID") for reason in reasons):
        return {"path": "NONE", "status": "INELIGIBLE_FOR_TRAINING", "replay_performed": False, "reasons": reasons}
    return {
        "path": "DETERMINISTIC_HISTORICAL_REPLAY",
        "status": "ELIGIBLE_FOR_AS_OF_TRAINING",
        "replay_performed": True,
        "replay_lineage_hash": sha256_json({key: replay_context.get(key) for key in REPLAY_REQUIRED}),
        "reasons": reasons,
    }


__all__ = ["REPLAY_REQUIRED", "select_reconstruction_path"]
