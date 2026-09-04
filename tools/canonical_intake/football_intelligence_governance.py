"""BATCH-12 pre-Frozen Football Intelligence governance validators.

This module validates the governance boundary for V4-044 and V4-045.  It
does not generate football features, run a model, calculate a prediction, or
create a Frozen Input.  It exists so the approved pre-Frozen artifact and
configuration semantics are testable before implementation begins.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from tools.migration_harness.common import sha256_json


FEATURE_CONTRACT_VERSION = "football-intelligence-feature@1.0.0"
CONTEXT_INTEGRATION_CONTRACT_VERSION = "football-context-integration@1.0.0"
CONFIG_VERSION = "football-intelligence-config@1.0.0"
CONFIG_PATH = Path("docs/V4_FOOTBALL_INTELLIGENCE_CONFIG.json")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

FEATURE_STATES = frozenset(
    {
        "AVAILABLE",
        "UNKNOWN",
        "UNAVAILABLE",
        "NOT_VERIFIED",
        "CONFLICTED",
        "STALE",
        "FUTURE_DATA",
        "BLOCKED",
    }
)
CONTEXT_STATES = frozenset(
    {"CONFIRMED", "PROJECTED", "UNKNOWN", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED"}
)
NON_CONSUMABLE_STATES = frozenset(
    {"UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED"}
)
FORBIDDEN_TOKENS = frozenset(
    {
        "prediction",
        "recommendation",
        "model_confidence",
        "win_probability",
        "betting_confidence",
        "score_selection",
        "engine_output",
        "frozen_input_id",
        "frozen_input_hash",
        "lambda",
    }
)


class FootballIntelligenceGovernanceError(ValueError):
    """A pre-Frozen artifact or config violates the approved boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).casefold())


def _forbidden(value: Any, path: str = "artifact") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in {"predictioncutoffat", "prediction_cutoff_at"}:
                found = _forbidden(child, f"{path}.{key}")
                if found:
                    return found
                continue
            if normalized in {_normalized_key(token) for token in FORBIDDEN_TOKENS}:
                return f"{path}.{key}"
            if any(token in normalized for token in ("prediction", "recommendation", "winprobability", "bettingconfidence", "scoreselection", "engineoutput", "frozeninput", "modelconfidence")):
                return f"{path}.{key}"
            found = _forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FootballIntelligenceGovernanceError("REQUIRED_FIELD_MISSING", f"{field_name} is required")
    return value.strip()


def _hash(value: Any, field_name: str) -> str:
    result = _required_text(value, field_name)
    if not HASH_RE.fullmatch(result):
        raise FootballIntelligenceGovernanceError("HASH_INVALID", f"{field_name} must be sha256:<64 lowercase hex>")
    return result


def _ref(value: Any, field_name: str, hash_field: str = "hash") -> None:
    if not isinstance(value, Mapping):
        raise FootballIntelligenceGovernanceError("REFERENCE_INVALID", f"{field_name} must be an object")
    _required_text(value.get("id"), f"{field_name}.id")
    _hash(value.get(hash_field), f"{field_name}.{hash_field}")


def load_approved_config(repo_root: Path) -> Mapping[str, Any]:
    """Load and validate the immutable BATCH-12 config artifact."""

    path = repo_root / CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FootballIntelligenceGovernanceError("CONFIG_UNREADABLE", str(exc)) from exc
    validate_approved_config(raw)
    return raw


def validate_approved_config(raw: Any) -> None:
    if not isinstance(raw, Mapping):
        raise FootballIntelligenceGovernanceError("CONFIG_INVALID", "config must be an object")
    if raw.get("config_version") != CONFIG_VERSION:
        raise FootballIntelligenceGovernanceError("CONFIG_VERSION_INVALID", f"expected {CONFIG_VERSION}")
    if raw.get("mapping_registry_version") != "football-intelligence-mapping@1.0.0":
        raise FootballIntelligenceGovernanceError("MAPPING_VERSION_INVALID", "mapping registry version is not approved")
    if raw.get("approved_model_effect_coefficients") != []:
        raise FootballIntelligenceGovernanceError("UNAPPROVED_COEFFICIENT", "BATCH-12 has no approved model-effect coefficients")
    policy = raw.get("policy")
    if not isinstance(policy, Mapping):
        raise FootballIntelligenceGovernanceError("CONFIG_POLICY_INVALID", "policy must be an object")
    if policy.get("non_consumable_states") != sorted(NON_CONSUMABLE_STATES):
        raise FootballIntelligenceGovernanceError("STATE_POLICY_INVALID", "non-consumable state policy drifted")
    if policy.get("interaction_default") != "SEPARATE_DIMENSIONS_ONLY":
        raise FootballIntelligenceGovernanceError("INTERACTION_POLICY_INVALID", "unapproved interaction default")
    numeric = raw.get("numeric_mappings")
    categorical = raw.get("categorical_mappings")
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise FootballIntelligenceGovernanceError("MAPPING_COLLECTION_INVALID", "numeric and categorical mappings must be lists")
    for index, mapping in enumerate(numeric):
        if not isinstance(mapping, Mapping):
            raise FootballIntelligenceGovernanceError("MAPPING_INVALID", f"numeric_mappings[{index}] must be an object")
        for field in ("feature_key", "unit", "raw_source", "transformation", "normalization", "clipping", "missing_behavior"):
            _required_text(mapping.get(field), f"numeric_mappings[{index}].{field}")
        if mapping.get("model_effect_coefficient") is not None or mapping.get("weights") is not None:
            raise FootballIntelligenceGovernanceError("UNAPPROVED_COEFFICIENT", f"numeric_mappings[{index}] contains a coefficient/weight")
        if mapping.get("missing_behavior") != "PRESERVE_STATE":
            raise FootballIntelligenceGovernanceError("MISSINGNESS_POLICY_INVALID", f"numeric_mappings[{index}] must preserve state")
    interaction = raw.get("interaction_policy")
    if not isinstance(interaction, Mapping) or interaction.get("approved_rules") != []:
        raise FootballIntelligenceGovernanceError("INTERACTION_RULE_UNAPPROVED", "no BATCH-12 interaction rule is approved")


def validate_pre_freeze_artifact(raw: Any, *, config: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Validate one pre-Frozen derived feature artifact without generating it."""

    if not isinstance(raw, Mapping):
        raise FootballIntelligenceGovernanceError("ARTIFACT_INVALID", "artifact must be an object")
    if "frozen_input_id" in raw or "frozen_input_hash" in raw:
        raise FootballIntelligenceGovernanceError("FROZEN_INPUT_FORBIDDEN", "pre-Frozen artifact cannot reference Frozen Input")
    forbidden = _forbidden(raw)
    if forbidden:
        raise FootballIntelligenceGovernanceError("MODEL_FIELD_FORBIDDEN", f"pre-Frozen artifact cannot contain {forbidden}")
    if raw.get("contract_version") != FEATURE_CONTRACT_VERSION:
        raise FootballIntelligenceGovernanceError("CONTRACT_VERSION_INVALID", f"expected {FEATURE_CONTRACT_VERSION}")
    if raw.get("artifact_kind") != "PRE_FREEZE_FEATURE_ARTIFACT":
        raise FootballIntelligenceGovernanceError("LIFECYCLE_INVALID", "artifact must be explicitly pre-Frozen")
    for field in ("artifact_id", "feature_bundle_id", "role", "generator_version", "config_version", "config_hash", "mapping_registry_version", "prediction_cutoff_at", "kickoff_at", "input_hash", "payload_hash", "provenance_hash"):
        _required_text(raw.get(field), field)
    if raw.get("config_version") != CONFIG_VERSION:
        raise FootballIntelligenceGovernanceError("CONFIG_VERSION_INVALID", f"expected {CONFIG_VERSION}")
    _hash(raw.get("input_hash"), "input_hash")
    _hash(raw.get("config_hash"), "config_hash")
    _hash(raw.get("payload_hash"), "payload_hash")
    _hash(raw.get("provenance_hash"), "provenance_hash")
    try:
        cutoff = datetime.fromisoformat(_required_text(raw.get("prediction_cutoff_at"), "prediction_cutoff_at"))
        kickoff = datetime.fromisoformat(_required_text(raw.get("kickoff_at"), "kickoff_at"))
    except ValueError as exc:
        raise FootballIntelligenceGovernanceError("TIME_INVALID", "cutoff and kickoff must be timezone-aware ISO timestamps") from exc
    if cutoff.tzinfo is None or kickoff.tzinfo is None or cutoff >= kickoff:
        raise FootballIntelligenceGovernanceError("CUTOFF_INVALID", "prediction_cutoff_at must precede kickoff_at")
    refs = raw.get("feature_bundle_ref")
    _ref(refs, "feature_bundle_ref", "feature_snapshot_hash")
    for field in ("statistical_feature_refs", "team_context_refs", "evidence_refs"):
        values = raw.get(field)
        if not isinstance(values, list):
            raise FootballIntelligenceGovernanceError("REFERENCE_COLLECTION_INVALID", f"{field} must be a list")
        for index, value in enumerate(values):
            _ref(value, f"{field}[{index}]")

    features = raw.get("features")
    if not isinstance(features, list) or not features:
        raise FootballIntelligenceGovernanceError("FEATURES_MISSING", "features must be a non-empty list")
    for index, feature in enumerate(features):
        path = f"features[{index}]"
        if not isinstance(feature, Mapping):
            raise FootballIntelligenceGovernanceError("FEATURE_INVALID", f"{path} must be an object")
        for field in ("feature_key", "category", "kind", "state", "basis_refs"):
            if field not in feature:
                raise FootballIntelligenceGovernanceError("FEATURE_FIELD_MISSING", f"{path}.{field} is required")
        state = _required_text(feature.get("state"), f"{path}.state").upper()
        if state not in FEATURE_STATES:
            raise FootballIntelligenceGovernanceError("FEATURE_STATE_INVALID", f"{path}.state is not governed")
        basis_refs = feature.get("basis_refs")
        if not isinstance(basis_refs, list) or not basis_refs or any(not isinstance(item, str) or not item.strip() for item in basis_refs):
            raise FootballIntelligenceGovernanceError("BASIS_REFERENCE_REQUIRED", f"{path}.basis_refs is required")
        if state == "AVAILABLE":
            if feature.get("value") is None or feature.get("value") == "" or feature.get("value") == {}:
                raise FootballIntelligenceGovernanceError("AVAILABLE_VALUE_EMPTY", f"{path} cannot have an empty value")
            _required_text(feature.get("unit"), f"{path}.unit")
        else:
            _required_text(feature.get("reason_code"), f"{path}.reason_code")
            _required_text(feature.get("reason_detail"), f"{path}.reason_detail")
            if state in NON_CONSUMABLE_STATES and feature.get("value") is not None:
                raise FootballIntelligenceGovernanceError("NON_CONSUMABLE_VALUE_PRESENT", f"{path} must not carry a numeric replacement value")
        context_state = feature.get("context_state")
        if context_state is not None and _required_text(context_state, f"{path}.context_state").upper() not in CONTEXT_STATES:
            raise FootballIntelligenceGovernanceError("CONTEXT_STATE_INVALID", f"{path}.context_state is not governed")
        if context_state == "PROJECTED" and feature.get("kind") != "CATEGORICAL":
            raise FootballIntelligenceGovernanceError("PROJECTED_NUMERIC_FORBIDDEN", f"{path} projected context must remain categorical")
        if context_state == "CONFIRMED" and feature.get("kind") == "CATEGORICAL" and feature.get("value") == "PROJECTED_LINEUP":
            raise FootballIntelligenceGovernanceError("CONFIRMED_PROJECTED_CONFLICT", f"{path} cannot label projected data as confirmed")
    quality = raw.get("feature_quality")
    if not isinstance(quality, Mapping):
        raise FootballIntelligenceGovernanceError("FEATURE_QUALITY_INVALID", "feature_quality must be typed")
    for field in ("coverage", "verification", "freshness", "completeness", "conflict", "provenance"):
        _required_text(quality.get(field), f"feature_quality.{field}")
    if any(key in quality for key in ("score", "confidence", "prediction_confidence", "betting_confidence")):
        raise FootballIntelligenceGovernanceError("PREDICTION_CONFIDENCE_FORBIDDEN", "feature_quality cannot be prediction-like")
    if config is not None:
        validate_approved_config(config)
        if raw.get("config_hash") != calculate_governance_hash(config):
            raise FootballIntelligenceGovernanceError(
                "CONFIG_HASH_MISMATCH",
                "config_hash must identify the exact approved BATCH-12 config",
            )
    return dict(raw)


def calculate_governance_hash(payload: Mapping[str, Any]) -> str:
    """Expose the repository canonical JSON hash for governance tests."""

    return sha256_json(payload)


__all__ = [
    "CONFIG_PATH",
    "CONFIG_VERSION",
    "CONTEXT_INTEGRATION_CONTRACT_VERSION",
    "CONTEXT_STATES",
    "FEATURE_CONTRACT_VERSION",
    "FEATURE_STATES",
    "FootballIntelligenceGovernanceError",
    "calculate_governance_hash",
    "load_approved_config",
    "validate_approved_config",
    "validate_pre_freeze_artifact",
]
