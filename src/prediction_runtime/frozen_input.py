"""Frozen Input v2 validation and pre-training assembly scaffold."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ALIASES = {"latest", "current", "default"}
REQUIRED = (
    "frozen_input_id", "contract_version", "frozen_input_revision", "canonical_match_identity_ref",
    "official_odds_snapshot_refs", "external_market_snapshot_refs", "team_context_ref", "evidence_bundle_ref",
    "feature_schema_version", "feature_bundle_id", "feature_snapshot_hash", "feature_bundle_contract_version",
    "prediction_cutoff_at", "kickoff_at", "model_version_registry_refs", "engine_version_registry_refs",
    "config_version_registry_refs", "dataset_version", "schema_version", "frozen_at", "frozen_input_hash",
    "status", "immutable",
)


class FrozenInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def logical_hash(value: Mapping[str, Any]) -> str:
    volatile = {"created_at", "ingested_at", "observed_at", "frozen_at", "frozen_input_hash"}
    return "sha256:" + hashlib.sha256(canonical_bytes({key: item for key, item in value.items() if key not in volatile})).hexdigest()


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise FrozenInputError("TIMESTAMP_INVALID", field)
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FrozenInputError("TIMESTAMP_INVALID", field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FrozenInputError("TIMEZONE_REQUIRED", field)
    return parsed


def _hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise FrozenInputError("HASH_INVALID", field)


def _ref(value: Any, field: str) -> None:
    if not isinstance(value, Mapping) or not value:
        raise FrozenInputError("REFERENCE_INVALID", field)
    if not any(key.endswith(("_hash", "_sha256", "payload_hash", "bundle_hash")) for key in value):
        raise FrozenInputError("REFERENCE_HASH_REQUIRED", field)


def validate_frozen_input(value: Mapping[str, Any], *, require_formal_frozen: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FrozenInputError("FROZEN_INPUT_OBJECT_REQUIRED", "input must be an object")
    missing = [field for field in REQUIRED if field not in value]
    if missing:
        raise FrozenInputError("FROZEN_INPUT_FIELD_MISSING", ",".join(missing))
    if value.get("contract_version") != "frozen-input@2.0.0" or value.get("feature_bundle_contract_version") != "feature-bundle@2.0.0":
        raise FrozenInputError("FROZEN_INPUT_CONTRACT_INVALID", "v2.0.0 and feature-bundle@2.0.0 are required")
    if value.get("status") not in {"FROZEN", "SUPERSEDED", "BLOCKED"} or value.get("immutable") is not True:
        raise FrozenInputError("FROZEN_INPUT_STATE_INVALID", "status or immutable flag invalid")
    if require_formal_frozen and value.get("status") != "FROZEN":
        raise FrozenInputError("FROZEN_INPUT_NOT_USABLE", "formal runs require status FROZEN")
    for field in ("feature_snapshot_hash", "frozen_input_hash"):
        _hash(value[field], field)
    if value.get("frozen_input_hash") != logical_hash(value):
        raise FrozenInputError("FROZEN_INPUT_HASH_MISMATCH", "frozen_input_hash does not match logical freeze boundary")
    for field in ("canonical_match_identity_ref", "team_context_ref", "evidence_bundle_ref"):
        _ref(value[field], field)
    if not isinstance(value["official_odds_snapshot_refs"], list) or not value["official_odds_snapshot_refs"]:
        raise FrozenInputError("OFFICIAL_ODDS_REFS_REQUIRED", "at least one official snapshot, including explicit unavailable, is required")
    if not isinstance(value["external_market_snapshot_refs"], list):
        raise FrozenInputError("EXTERNAL_MARKET_REFS_INVALID", "external refs must be an explicit array")
    for index, item in enumerate(value["official_odds_snapshot_refs"] + value["external_market_snapshot_refs"]):
        _ref(item, f"snapshot_refs[{index}]")
    for field in ("model_version_registry_refs", "engine_version_registry_refs", "config_version_registry_refs"):
        refs = value[field]
        if not isinstance(refs, list) or not refs or any(not isinstance(item, str) or not item.strip() or item.casefold() in ALIASES for item in refs):
            raise FrozenInputError("VERSION_REFS_INVALID", field)
    cutoff = _timestamp(value["prediction_cutoff_at"], "prediction_cutoff_at")
    kickoff = _timestamp(value["kickoff_at"], "kickoff_at")
    if cutoff >= kickoff:
        raise FrozenInputError("CUTOFF_AFTER_KICKOFF", "prediction cutoff must precede kickoff")
    forbidden = json.dumps(value, ensure_ascii=False).casefold()
    if "v3.3.3" in forbidden or "v333" in forbidden or "prediction_output" in forbidden:
        raise FrozenInputError("V3_ISOLATION_VIOLATION", "Frozen Input cannot contain legacy prediction/model output")
    return {"status": "PASS", "frozen_input_id": value["frozen_input_id"], "frozen_input_hash": value["frozen_input_hash"]}


class FrozenInputScaffold:
    """Prepare a readiness assessment without emitting a Frozen Input record."""

    def assess(self, *, feature_bundle_available: bool, all_sources_cutoff_valid: bool, approved_model_artifacts: bool, accepted_gate: bool) -> dict[str, Any]:
        checks = {
            "feature_bundle_available": feature_bundle_available,
            "all_sources_cutoff_valid": all_sources_cutoff_valid,
            "approved_model_artifacts": approved_model_artifacts,
            "accepted_gate": accepted_gate,
        }
        missing = [name for name, passed in checks.items() if not passed]
        return {
            "contract_version": "frozen-input@2.0.0",
            "status": "READY_FOR_FORMATION" if not missing else "BLOCKED",
            "missing_prerequisites": missing,
            "record_emitted": False,
            "formal_frozen_input_written": False,
        }


__all__ = ["FrozenInputError", "FrozenInputScaffold", "logical_hash", "validate_frozen_input"]
