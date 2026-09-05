"""Fail-closed validation helpers for the amended training-sample contract.

This module validates sample envelopes and hash boundaries only.  It does not
enumerate archive data, build a dataset, split samples, or fit a model.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping


ENGINE_ROLES = ("OUTCOME", "HANDICAP", "GOALS", "HTFT")
ELIGIBILITY_STATES = ("BLOCKED", "INELIGIBLE", "PARTIALLY_ELIGIBLE", "ELIGIBLE")
HASH_FIELDS = {
    "feature_bundle_hash", "feature_snapshot_hash", "statistical_hash", "football_hash",
    "market_hash", "tactical_hash", "gate_record_hash", "label_hash", "builder_hash",
    "input_hash", "sample_hash", "provenance_hash", "official_rqspf_snapshot_hash",
}
ALIASES = {
    "sample_id", "target_role", "historical_feature_bundle_id", "historical_feature_bundle_hash",
    "statistical_refs_and_hashes", "football_refs_and_hashes", "market_refs_and_hashes",
    "tactical_refs_and_hashes", "quality_gate_state", "label_ref_and_hash",
}
HANDICAP_REQUIRED = {
    "official_rqspf_snapshot_ref", "official_rqspf_snapshot_hash", "official_handicap_value",
    "handicap_sign_convention", "source_availability_at", "prediction_cutoff_at",
}
STABLE_HASH_KEYS = {
    "archive_snapshot_identity", "archive_snapshot_hash", "cutoff_profile", "builder_version", "builder_hash",
    "dataset_schema_version", "dataset_schema_hash", "replay_policy_version", "replay_policy_hash",
    "generator_version", "generator_hash", "config_version", "config_hash", "mapping_version", "mapping_hash",
    "sample_membership", "feature_refs_and_hashes", "eligibility", "label_refs_and_hashes",
}
VOLATILE_KEYS = {
    "execution_timestamp", "created_at", "logging_metadata", "host_specific_absolute_path",
    "host_name", "process_id", "wall_clock_duration", "absolute_path",
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo and parsed.utcoffset() is not None else None


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def validate_training_sample(sample: Mapping[str, Any]) -> tuple[str, ...]:
    """Return deterministic contract failures; no data is persisted."""

    failures: list[str] = []
    for alias in sorted(ALIASES.intersection(sample)):
        failures.append(f"FIELD_ALIAS_AMBIGUOUS:{alias}")
    required = {
        "training_sample_id", "match_id", "cutoff_profile", "prediction_cutoff_at", "kickoff_at",
        "feature_bundle_ref", "feature_bundle_hash", "feature_snapshot_hash", "statistical_ref", "statistical_hash",
        "football_ref", "football_hash", "market_ref", "market_hash", "tactical_ref", "tactical_hash",
        "gate_record_ref", "gate_record_hash", "source_refs", "evidence_refs", "provenance_refs", "engine_role",
        "eligibility_state", "exclusion_or_block_reason", "label_ref", "label_hash", "builder_version", "builder_hash",
        "dataset_version", "input_hash", "sample_hash", "provenance_hash", "revision", "supersedes",
    }
    for field in sorted(required.difference(sample)):
        failures.append(f"REQUIRED_FIELD_MISSING:{field}")
    role = sample.get("engine_role")
    if role not in ENGINE_ROLES:
        failures.append("ENGINE_ROLE_INVALID")
    if sample.get("eligibility_state") not in ELIGIBILITY_STATES:
        failures.append("ELIGIBILITY_STATE_INVALID")
    cutoff = _parse_timestamp(sample.get("prediction_cutoff_at"))
    kickoff = _parse_timestamp(sample.get("kickoff_at"))
    availability = _parse_timestamp(sample.get("source_availability_at"))
    if not cutoff or not kickoff or not availability:
        failures.append("AS_OF_TIMESTAMP_INCOMPLETE")
    elif not availability <= cutoff < kickoff:
        failures.append("AS_OF_TIME_PREDICATE_FAILED")
    for field in sorted(HASH_FIELDS):
        if field in sample and not _is_hash(sample[field]):
            failures.append(f"HASH_INVALID:{field}")
    if sample.get("handicap_sign_convention") not in (None, "home_minus_away"):
        failures.append("HANDICAP_SIGN_CONVENTION_INVALID")
    if role == "HANDICAP":
        for field in sorted(HANDICAP_REQUIRED):
            if field not in sample:
                failures.append(f"HANDICAP_BINDING_REQUIRED:{field}")
        if sample.get("handicap_sign_convention") != "home_minus_away":
            failures.append("HANDICAP_SIGN_CONVENTION_REQUIRED")
        if sample.get("official_rqspf_snapshot_ref") in {"", None}:
            failures.append("OFFICIAL_RQSPF_SNAPSHOT_REQUIRED")
    forbidden = {"external_asian_handicap", "closing_handicap", "latest_handicap", "default_handicap"}
    if any(field in sample for field in forbidden):
        failures.append("HANDICAP_SUBSTITUTE_FORBIDDEN")
    return tuple(failures)


def evaluate_engine_eligibility(sample: Mapping[str, Any]) -> dict[str, str]:
    """Keep missing official RQSPF scoped to Handicap only."""

    result = {role: "ELIGIBLE" for role in ENGINE_ROLES}
    missing_handicap = HANDICAP_REQUIRED.difference(sample)
    if missing_handicap or sample.get("handicap_sign_convention") != "home_minus_away":
        result["HANDICAP"] = "INELIGIBLE"
    general_failures = [failure for failure in validate_training_sample(sample) if not failure.startswith("HANDICAP_BINDING_REQUIRED:") and failure not in {
        "HANDICAP_SIGN_CONVENTION_REQUIRED", "OFFICIAL_RQSPF_SNAPSHOT_REQUIRED", "HANDICAP_SIGN_CONVENTION_INVALID"
    }]
    if general_failures:
        for role in ENGINE_ROLES:
            result[role] = "INELIGIBLE"
    return result


def substantive_hash_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Select only governed stable inputs for a substantive dataset hash."""

    return {
        key: candidate[key]
        for key in sorted(STABLE_HASH_KEYS)
        if key in candidate and key not in VOLATILE_KEYS
    }


def substantive_hash(candidate: Mapping[str, Any]) -> str:
    return sha256_json(substantive_hash_payload(candidate))


__all__ = [
    "ENGINE_ROLES", "HANDICAP_REQUIRED", "evaluate_engine_eligibility", "sha256_json",
    "substantive_hash", "substantive_hash_payload", "validate_training_sample",
]
