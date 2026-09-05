"""Shared fail-closed helpers for the BATCH-14 pre-Freeze boundary."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from tools.migration_harness.common import sha256_json


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
STATES = frozenset(
    {
        "AVAILABLE",
        "UNKNOWN",
        "UNAVAILABLE",
        "NOT_VERIFIED",
        "CONFLICTED",
        "STALE",
        "FUTURE_DATA",
        "BLOCKED",
        "NOT_APPLICABLE",
    }
)
QUALITY_DIMENSIONS = (
    "identity",
    "availability",
    "coverage",
    "verification",
    "freshness",
    "completeness",
    "conflict",
    "provenance",
    "timestamp_validity",
    "cutoff_eligibility",
    "duplication_integrity",
    "future_data_risk",
)
ELIGIBILITY_LEVELS = ("FEATURE", "DOMAIN", "CANDIDATE_SET")
ELIGIBILITY_STATES = ("ELIGIBLE", "PARTIALLY_ELIGIBLE", "INELIGIBLE", "BLOCKED")
FORBIDDEN_TOKENS = frozenset(
    {
        "prediction",
        "recommendation",
        "model_confidence",
        "win_probability",
        "betting_confidence",
        "score",
        "score_engine",
        "engine_output",
        "risk_decision",
        "abstention",
        "frozen_input_id",
        "frozen_input_hash",
        "weight",
        "penalty",
        "probability",
    }
)


class Batch14ValidationError(ValueError):
    """A BATCH-14 input or output violates a frozen contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): freeze(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(freeze(child) for child in value)
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw(child) for child in value]
    return value


def text(value: Any, field: str, error_type=Batch14ValidationError) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def hash_value(value: Any, field: str, error_type=Batch14ValidationError) -> str:
    result = text(value, field, error_type)
    if not HASH_RE.fullmatch(result):
        raise error_type("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def timestamp(value: Any, field: str, error_type=Batch14ValidationError) -> datetime:
    raw = text(value, field, error_type)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise error_type("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise error_type("TIMEZONE_REQUIRED", f"{field} must include an explicit timezone")
    return parsed


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def find_forbidden(value: Any, path: str = "artifact") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if normalized in {"prediction_cutoff_at", "predictioncutoffat"}:
                found = find_forbidden(child, f"{path}.{key}")
                if found:
                    return found
                continue
            if normalized in {re.sub(r"[^a-z0-9_]", "", item) for item in FORBIDDEN_TOKENS}:
                return f"{path}.{key}"
            if any(term in normalized for term in ("prediction", "recommendation", "modelconfidence", "winprobability", "bettingconfidence", "scoreengine", "engineoutput", "riskdecision", "abstention", "frozeninput", "compositequality", "qualityscore")):
                return f"{path}.{key}"
            # These are valid time/assessment words, not model outputs.
            found = find_forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = find_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def reference(value: Any, field: str, *, allow_missing_hash: bool = False) -> Dict[str, Any]:
    if isinstance(value, str):
        return {"id": text(value, field)}
    if not isinstance(value, Mapping):
        raise Batch14ValidationError("REFERENCE_INVALID", f"{field} must be an object")
    result = dict(value)
    identifier = next((result.get(key) for key in ("id", "ref_id", "object_id", "feature_id", "artifact_id", "assessment_id", "evidence_id") if result.get(key)), None)
    result["id"] = text(identifier, f"{field}.id")
    raw_hash = next((result.get(key) for key in ("hash", "ref_hash", "object_hash", "output_hash", "feature_hash", "assessment_hash", "provenance_hash", "feature_snapshot_hash") if result.get(key)), None)
    if raw_hash is None and allow_missing_hash:
        result["hash"] = None
    else:
        result["hash"] = hash_value(raw_hash, f"{field}.hash")
    return result


def implementation_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_batch14_governance(repo_root: Path) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    root = Path(repo_root).resolve()
    try:
        config = json.loads((root / "docs/V4_QUALITY_GATE_CONFIG.json").read_text(encoding="utf-8"))
        matrix = json.loads((root / "docs/V4_QUALITY_GATE_MATRIX.json").read_text(encoding="utf-8"))
        reasons = json.loads((root / "docs/V4_QUALITY_GATE_REASON_REGISTRY.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Batch14ValidationError("GOVERNANCE_UNREADABLE", str(exc)) from exc
    expected = {
        "quality-gate-config@1.0.0": config,
        "quality-gate-matrix@1.0.0": matrix,
        "quality-gate-reason-registry@1.0.0": reasons,
    }
    for version, document in expected.items():
        actual_version = document.get({
            "quality-gate-config@1.0.0": "config_version",
            "quality-gate-matrix@1.0.0": "matrix_version",
            "quality-gate-reason-registry@1.0.0": "registry_version",
        }[version])
        if actual_version != version:
            raise Batch14ValidationError("GOVERNANCE_VERSION_INVALID", f"expected {version}")
        supplied = document.get("canonical_hash")
        body = dict(document)
        body.pop("canonical_hash", None)
        if supplied != sha256_json(body):
            raise Batch14ValidationError("GOVERNANCE_HASH_INVALID", f"{version} canonical hash is not recomputable")
    return config, matrix, reasons


def canonical_entity(raw: Any, error_type=Batch14ValidationError) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise error_type("CANONICAL_ENTITY_INVALID", "canonical_entity_refs must be an object")
    result = dict(raw)
    for field in ("match_id", "home_team_id", "away_team_id"):
        text(result.get(field), f"canonical_entity_refs.{field}", error_type)
    if result["home_team_id"] == result["away_team_id"]:
        raise error_type("CANONICAL_SIDE_CONFLICT", "home and away team IDs must differ")
    return result


def validate_boundary(cutoff_value: Any, kickoff_value: Any, error_type=Batch14ValidationError) -> Tuple[str, str, datetime, datetime]:
    cutoff = timestamp(cutoff_value, "prediction_cutoff_at", error_type)
    kickoff = timestamp(kickoff_value, "kickoff_at", error_type)
    if not cutoff < kickoff:
        raise error_type("CUTOFF_INVALID", "prediction_cutoff_at must precede kickoff_at")
    return iso(cutoff), iso(kickoff), cutoff, kickoff


def dimension(state: str, *, basis_refs=(), evidence_refs=(), reason_codes=(), counts=None, source_input_hashes=()) -> Dict[str, Any]:
    return {
        "state": state,
        "basis_refs": list(basis_refs),
        "evidence_refs": list(evidence_refs),
        "reason_codes": list(reason_codes),
        "counts": dict(counts or {}),
        "source_input_hashes": list(source_input_hashes),
    }


def typed_dimensions(states: Mapping[str, str], *, basis_refs=(), evidence_refs=(), reason_codes=(), counts=None, source_input_hashes=()) -> Dict[str, Any]:
    return {
        name: dimension(states.get(name, "UNKNOWN"), basis_refs=basis_refs, evidence_refs=evidence_refs, reason_codes=reason_codes, counts=counts, source_input_hashes=source_input_hashes)
        for name in QUALITY_DIMENSIONS
    }


__all__ = [
    "Batch14ValidationError", "ELIGIBILITY_LEVELS", "ELIGIBILITY_STATES", "HASH_RE", "QUALITY_DIMENSIONS", "REASON_RE", "STATES",
    "canonical_entity", "dimension", "find_forbidden", "freeze", "hash_value", "implementation_hash", "iso", "load_batch14_governance",
    "reference", "text", "timestamp", "thaw", "typed_dimensions", "validate_boundary",
]
