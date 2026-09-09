"""Versioned historical-training eligibility separate from prediction readiness.

The active profile in this module is deliberately narrower than the
prediction-time Feature Bundle/Batch-14 contract.  It accepts only features
that are present in the approved archive or deterministically reconstructed
from information available at the replay cutoff.  Missing values remain
typed and visible; this module never imputes a value.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.prediction_training_contract import ENGINE_ROLES, sha256_json


PROFILE_ID = "model-training-minimum-feature-set@2.0.0"
PROFILE_PATH_NAME = "v4_model_training_minimum_feature_set_v2.json"
TRAINING_GATE_ID = "training-eligibility-gate@2.0.0"
TRAINING_GATE_PATH_NAME = "v4_training_eligibility_gate_v2.json"
AVAILABILITY_STATES = ("AVAILABLE", "UNAVAILABLE", "UNKNOWN")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class TrainingEligibilityError(ValueError):
    """A fail-closed training-profile or training-gate violation."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


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
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HASH_RE.fullmatch(value))


def _payload(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    value = entry.get("payload")
    return value if isinstance(value, Mapping) else {}


def _hash_without(document: Mapping[str, Any], field: str) -> str:
    return sha256_json({key: value for key, value in document.items() if key != field})


def _feature(
    feature_id: str,
    domain: str,
    *,
    market_source: str | None = None,
    optional: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "feature_id": feature_id,
        "type": "categorical_or_relational" if optional and domain == "TACTICAL" else "number",
        "domain": domain,
        "missing": "MASK" if optional else "REJECT",
        "availability_states": list(AVAILABILITY_STATES),
    }
    if market_source:
        value["native_market_source"] = market_source
    return value


def _build_default_profile() -> dict[str, Any]:
    total_goals = [f"market_official_total_goals_{value}" for value in ("0", "1", "2", "3", "4", "5", "6", "7_plus")]
    htft = [f"market_official_htft_{value}" for value in ("h_h", "h_d", "h_a", "d_h", "d_d", "d_a", "a_h", "a_d", "a_a")]
    profiles = {
        "OUTCOME": {
            "engine_role": "OUTCOME",
            "required_features": [
                _feature("statistical_strength_home", "STATISTICAL"),
                _feature("statistical_strength_away", "STATISTICAL"),
                _feature("football_form_home", "FOOTBALL"),
                _feature("football_form_away", "FOOTBALL"),
                _feature("market_official_1x2_home", "MARKET", market_source="SPF"),
                _feature("market_official_1x2_draw", "MARKET", market_source="SPF"),
                _feature("market_official_1x2_away", "MARKET", market_source="SPF"),
            ],
            "optional_features": [
                _feature("tactical_context_overlay", "TACTICAL", optional=True),
                _feature("external_market_overlay", "MARKET", optional=True),
            ],
            "market_core": {"source": "official SPF", "vector": ["H", "D", "A"]},
        },
        "HANDICAP": {
            "engine_role": "HANDICAP",
            "required_features": [
                _feature("statistical_strength_home", "STATISTICAL"),
                _feature("statistical_strength_away", "STATISTICAL"),
                _feature("football_form_home", "FOOTBALL"),
                _feature("football_form_away", "FOOTBALL"),
                _feature("official_rqspf_handicap_value_at_cutoff", "MARKET", market_source="RQSPF"),
                _feature("market_handicap_home", "MARKET", market_source="RQSPF"),
                _feature("market_handicap_draw", "MARKET", market_source="RQSPF"),
                _feature("market_handicap_away", "MARKET", market_source="RQSPF"),
            ],
            "optional_features": [
                _feature("tactical_context_overlay", "TACTICAL", optional=True),
                _feature("external_asian_handicap_overlay", "MARKET", optional=True),
            ],
            "market_core": {"source": "official RQSPF", "vector": ["official_handicap", "H", "D", "A"], "sign_convention": "home_minus_away"},
        },
        "GOALS": {
            "engine_role": "GOALS",
            "required_features": [
                _feature("statistical_goals_rate_home", "STATISTICAL"),
                _feature("statistical_goals_rate_away", "STATISTICAL"),
                _feature("football_goals_form_home", "FOOTBALL"),
                _feature("football_goals_form_away", "FOOTBALL"),
                *[_feature(value, "MARKET", market_source="TOTAL_GOALS") for value in total_goals],
            ],
            "optional_features": [
                _feature("tactical_context_overlay", "TACTICAL", optional=True),
                _feature("external_over_under_overlay", "MARKET", optional=True),
            ],
            "market_core": {"source": "official Total Goals", "vector": ["0", "1", "2", "3", "4", "5", "6", "7+"]},
        },
        "HTFT": {
            "engine_role": "HTFT",
            "required_features": [
                _feature("statistical_strength_home", "STATISTICAL"),
                _feature("statistical_strength_away", "STATISTICAL"),
                _feature("football_first_half_form_home", "FOOTBALL"),
                _feature("football_first_half_form_away", "FOOTBALL"),
                *[_feature(value, "MARKET", market_source="HTFT") for value in htft],
            ],
            "optional_features": [
                _feature("tactical_context_overlay", "TACTICAL", optional=True),
                _feature("market_official_1x2_context", "MARKET", optional=True),
            ],
            "market_core": {"source": "official HTFT", "vector": ["H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"]},
        },
    }
    for role, profile in profiles.items():
        profile["profile_id"] = f"{role.lower()}-training-minimum@2.0.0"
        profile["profile_revision"] = "r002"
        profile["profile_hash"] = _hash_without(profile, "profile_hash")
    document: dict[str, Any] = {
        "$id": PROFILE_ID,
        "profile_name": "MODEL_TRAINING_MINIMUM_FEATURE_SET",
        "profile_version": PROFILE_ID,
        "profile_revision": "r002",
        "status": "ACTIVE",
        "supersedes": "b15-ewp004-training-infrastructure-contract@1.0.0/engine_training_profiles",
        "prediction_time_full_readiness": {
            "identity": "PREDICTION_TIME_FULL_READINESS",
            "status": "UNCHANGED",
            "authoritative_contracts": ["V4_FEATURE_BUNDLE_CONTRACT", "V4_BATCH14_FULL_GATE"],
        },
        "inference_time_richer_overlay": {
            "identity": "INFERENCE_TIME_RICHER_OVERLAY",
            "missing_overlay_action": "MASK_AND_RETAIN_BASE_FEATURE_VECTOR",
            "allowed_overlay_domains": ["TACTICAL", "LINEUP", "EXTERNAL_MARKET", "ADDITIONAL_CONTEXT"],
            "feature_vector_mutation": "FORBIDDEN",
        },
        "availability_states": list(AVAILABILITY_STATES),
        "required_feature_provenance": [
            "source_availability_at", "information_time", "source_refs", "source_hashes",
            "reconstruction_rule", "reconstruction_version", "reconstruction_hash", "missingness_mask",
        ],
        "deterministic_reconstruction_policy": {
            "as_of_predicate": "source_availability_at <= prediction_cutoff_at < kickoff_at",
            "silent_imputation": "FORBIDDEN",
            "default_mean_zero_fill": "FORBIDDEN",
            "derived_feature_requires_rule_version_hash": True,
        },
        "tactical_status": "OPTIONAL_AVAILABILITY_AWARE_OVERLAY_NO_MANDATORY_NUMERIC_ENCODING",
        "engine_profiles": profiles,
    }
    document["profile_hash"] = _hash_without(document, "profile_hash")
    return document


def _build_default_gate() -> dict[str, Any]:
    document: dict[str, Any] = {
        "$id": TRAINING_GATE_ID,
        "gate_name": "TRAINING_ELIGIBILITY_GATE",
        "gate_version": TRAINING_GATE_ID,
        "gate_revision": "r002",
        "status": "ACTIVE",
        "profile_ref": PROFILE_ID,
        "prediction_gate_ref": "V4_BATCH14_FULL_GATE",
        "prediction_gate_semantics": "UNCHANGED_AND_NOT_REUSED_FOR_TRAINING",
        "required_checks": [
            "canonical_identity", "cutoff_binding", "native_market_source_refs",
            "required_minimum_feature_provenance", "postmatch_label_partition_separation",
            "temporal_no_leakage", "deterministic_reconstruction_metadata",
        ],
        "optional_overlay_policy": "MISSING_OPTIONAL_OVERLAY_MASKS_ONLY",
        "tactical_policy": "NOT_REQUIRED_FOR_TRAINING_MINIMUM",
        "market_native_alignment": {
            "OUTCOME": "official SPF",
            "HANDICAP": "official RQSPF handicap + RQSPF odds",
            "GOALS": "official Total Goals 0-7+ vector",
            "HTFT": "official HTFT 9-state odds",
            "EXACT_SCORE": "NOT_MANDATORY",
            "external_markets": "OPTIONAL_OVERLAY_ONLY",
        },
        "fail_closed": {
            "required_feature_missing": "INELIGIBLE",
            "required_provenance_missing": "INELIGIBLE",
            "optional_overlay_missing": "ELIGIBLE_WITH_MASK",
            "imputation_detected": "INELIGIBLE",
        },
        "record_schema": {
            "required_fields": [
                "training_gate_record_id", "gate_version", "profile_hash", "match_id", "cutoff_profile",
                "prediction_cutoff_at", "kickoff_at", "engine_role", "eligibility_state", "reasons",
                "feature_envelope", "availability_mask", "domain_coverage", "source_refs", "label_partition",
                "deterministic_reconstruction", "record_hash", "revision", "supersedes",
            ],
            "append_only": True,
        },
    }
    document["gate_hash"] = _hash_without(document, "gate_hash")
    return document


def load_training_profile(config_root: str | Path) -> Mapping[str, Any]:
    path = Path(config_root) / PROFILE_PATH_NAME
    if not path.is_file():
        raise TrainingEligibilityError("TRAINING_PROFILE_MISSING", str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingEligibilityError("TRAINING_PROFILE_LOAD_FAILED", str(path)) from exc
    failures = validate_training_profile(document)
    if failures:
        raise TrainingEligibilityError("TRAINING_PROFILE_INVALID", ";".join(failures))
    return document


def load_training_gate(config_root: str | Path) -> Mapping[str, Any]:
    path = Path(config_root) / TRAINING_GATE_PATH_NAME
    if not path.is_file():
        raise TrainingEligibilityError("TRAINING_GATE_CONTRACT_MISSING", str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingEligibilityError("TRAINING_GATE_LOAD_FAILED", str(path)) from exc
    failures = validate_training_gate(document)
    if failures:
        raise TrainingEligibilityError("TRAINING_GATE_CONTRACT_INVALID", ";".join(failures))
    return document


def validate_training_profile(document: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if document.get("$id") != PROFILE_ID or document.get("status") != "ACTIVE":
        failures.append("identity_or_status_invalid")
    if document.get("profile_name") != "MODEL_TRAINING_MINIMUM_FEATURE_SET":
        failures.append("profile_name_invalid")
    if document.get("profile_version") != PROFILE_ID or document.get("profile_revision") != "r002":
        failures.append("profile_version_invalid")
    if not _is_hash(document.get("profile_hash")) or document.get("profile_hash") != _hash_without(document, "profile_hash"):
        failures.append("profile_hash_invalid")
    if document.get("availability_states") != list(AVAILABILITY_STATES):
        failures.append("availability_states_invalid")
    policy = document.get("deterministic_reconstruction_policy", {})
    if policy.get("silent_imputation") != "FORBIDDEN" or policy.get("default_mean_zero_fill") != "FORBIDDEN" or policy.get("derived_feature_requires_rule_version_hash") is not True:
        failures.append("imputation_or_reconstruction_policy_invalid")
    profiles = document.get("engine_profiles", {})
    if set(profiles) != set(ENGINE_ROLES):
        failures.append("engine_profiles_incomplete")
    for role in ENGINE_ROLES:
        profile = profiles.get(role, {})
        if profile.get("engine_role") != role or profile.get("profile_revision") != "r002":
            failures.append(f"{role}:profile_identity_invalid")
        if not _is_hash(profile.get("profile_hash")) or profile.get("profile_hash") != _hash_without(profile, "profile_hash"):
            failures.append(f"{role}:profile_hash_invalid")
        required = profile.get("required_features", [])
        if not required:
            failures.append(f"{role}:required_features_empty")
        if any(item.get("domain") == "TACTICAL" or str(item.get("feature_id", "")).startswith("tactical_") for item in required if isinstance(item, Mapping)):
            failures.append(f"{role}:tactical_required_in_training_minimum")
        for item in (*required, *profile.get("optional_features", [])):
            if not isinstance(item, Mapping) or not item.get("feature_id") or item.get("type") not in {"number", "categorical_or_relational"} or item.get("domain") not in {"STATISTICAL", "FOOTBALL", "MARKET", "TACTICAL"}:
                failures.append(f"{role}:feature_declaration_invalid")
        for item in required:
            if item.get("type") != "number" or item.get("missing") != "REJECT" or item.get("availability_states") != list(AVAILABILITY_STATES):
                failures.append(f"{role}:required_missing_policy_invalid")
    return failures


def validate_training_gate(document: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if document.get("$id") != TRAINING_GATE_ID or document.get("status") != "ACTIVE":
        failures.append("identity_or_status_invalid")
    if document.get("gate_version") != TRAINING_GATE_ID or document.get("profile_ref") != PROFILE_ID:
        failures.append("gate_binding_invalid")
    if document.get("prediction_gate_semantics") != "UNCHANGED_AND_NOT_REUSED_FOR_TRAINING":
        failures.append("prediction_gate_reuse_invalid")
    if document.get("tactical_policy") != "NOT_REQUIRED_FOR_TRAINING_MINIMUM":
        failures.append("tactical_policy_invalid")
    if not _is_hash(document.get("gate_hash")) or document.get("gate_hash") != _hash_without(document, "gate_hash"):
        failures.append("gate_hash_invalid")
    if document.get("record_schema", {}).get("append_only") is not True:
        failures.append("record_append_only_invalid")
    return failures


def _unwrap_feature_values(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("feature_values", "features", "minimum_features", "training_features"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return payload


def _metadata_for(entry: Mapping[str, Any], value: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, Mapping):
        state = str(value.get("state", "AVAILABLE"))
        raw_value = value.get("value")
        metadata = dict(value)
    else:
        state = "AVAILABLE"
        raw_value = value
        metadata = {}
    metadata.setdefault("state", state)
    metadata.setdefault("source_availability_at", entry.get("source_availability_at", entry.get("availability_at")))
    metadata.setdefault("information_time", _payload(entry).get("information_time", metadata.get("source_availability_at")))
    metadata.setdefault("source_refs", [entry.get("record_ref")] if entry.get("record_ref") else [])
    metadata.setdefault("source_hashes", [entry.get("artifact_hash")] if entry.get("artifact_hash") else [])
    metadata.setdefault("missingness_mask", state != "AVAILABLE")
    return raw_value, metadata


def _valid_number(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            return False
        return bool(value.strip())
    return False


def _number(value: Any) -> float:
    if not _valid_number(value):
        raise ValueError("not a numeric value")
    return float(value)


def _rows(payload: Mapping[str, Any], key: str, labels: Sequence[str]) -> tuple[dict[str, float], list[str]]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        return {}, [f"MARKET_NATIVE_CORE_MISSING:{key}"]
    values: dict[str, float] = {}
    reasons: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping):
            reasons.append(f"MARKET_NATIVE_CORE_INVALID:{key}")
            continue
        label = str(item.get("canonical_cell_label", ""))
        value = item.get("value")
        if label not in labels or not _valid_number(value) or str(item.get("resolution_status", "PARSED")) not in {"PARSED", "REVIEW_CONFIRMED"}:
            reasons.append(f"MARKET_NATIVE_CORE_INVALID:{key}")
            continue
        values[label] = _number(value)
    missing = [label for label in labels if label not in values]
    if missing:
        reasons.append(f"MARKET_NATIVE_CORE_INCOMPLETE:{key}")
    if len(values) != len(labels):
        reasons.append(f"MARKET_NATIVE_CORE_CARDINALITY:{key}")
    return values, sorted(set(reasons))


def _find_entry(entries: Sequence[Mapping[str, Any]], ref: Any, artifact_type: str | None = None) -> Mapping[str, Any] | None:
    for entry in entries:
        if artifact_type and entry.get("artifact_type") != artifact_type:
            continue
        if ref and ref in {entry.get("record_ref"), entry.get("source_reference"), entry.get("archive_record_id")}:
            return entry
    return None


def _domain_entry(entries: Sequence[Mapping[str, Any]], artifact_type: str) -> Mapping[str, Any] | None:
    candidates = [item for item in entries if item.get("artifact_type") == artifact_type]
    candidates.sort(key=lambda item: (int(item.get("revision", 0)), str(item.get("archive_record_id"))), reverse=True)
    return candidates[0] if candidates else None


def _market_envelope(
    role: str,
    profile: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    cutoff: datetime,
    kickoff: datetime,
) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, Any]]:
    envelope: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    market = _domain_entry(entries, "market_intelligence_ref")
    official = None
    if market:
        market_payload = _payload(market)
        official = _find_entry(entries, market_payload.get("official_odds_record_ref"), "official_odds_screenshot")
        if official is None:
            official = _find_entry(entries, market_payload.get("official_odds_record_ref"), "official_odds_snapshot")
    if market is None or official is None:
        reasons.append("MISSING_NATIVE_MARKET_SOURCE_REF")
        return envelope, reasons, {"market_entry": market, "official_entry": official}
    official_payload = _payload(official)
    if role == "OUTCOME":
        values, errors = _rows(official_payload, "SPF", ("H", "D", "A"))
        mapping = {"H": "market_official_1x2_home", "D": "market_official_1x2_draw", "A": "market_official_1x2_away"}
    elif role == "HANDICAP":
        values, errors = _rows(official_payload, "RQSPF", ("official_handicap", "H", "D", "A"))
        mapping = {"official_handicap": "official_rqspf_handicap_value_at_cutoff", "H": "market_handicap_home", "D": "market_handicap_draw", "A": "market_handicap_away"}
    elif role == "GOALS":
        values, errors = _rows(official_payload, "TOTAL_GOALS", ("0", "1", "2", "3", "4", "5", "6", "7+"))
        mapping = {label: f"market_official_total_goals_{'7_plus' if label == '7+' else label}" for label in values}
    else:
        values, errors = _rows(official_payload, "HTFT", ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"))
        mapping = {label: f"market_official_htft_{label.lower().replace('/', '_')}" for label in values}
    reasons.extend(errors)
    availability = _parse_timestamp(official.get("source_availability_at", official.get("availability_at")))
    if availability is None or not availability <= cutoff < kickoff:
        reasons.append("MARKET_SOURCE_AS_OF_BOUNDARY_FAILED")
    for label, feature_id in mapping.items():
        if label not in values:
            continue
        envelope[feature_id] = {
            "value": values[label], "state": "AVAILABLE", "source_availability_at": official.get("source_availability_at", official.get("availability_at")),
            "information_time": _payload(official).get("information_time", official.get("source_availability_at", official.get("availability_at"))),
            "source_refs": [str(official.get("record_ref")), str(market.get("record_ref"))],
            "source_hashes": [official.get("artifact_hash"), market.get("artifact_hash")],
            "reconstruction_rule": "OBSERVED_OFFICIAL_MARKET_CELL",
            "reconstruction_version": "official-market-cell@1.0.0",
            "reconstruction_hash": official.get("artifact_hash"),
            "missingness_mask": False,
        }
    if role == "HANDICAP":
        official_value = envelope.get("official_rqspf_handicap_value_at_cutoff")
        if official_value:
            envelope["official_rqspf_handicap_value_at_cutoff"]["sign_convention"] = "home_minus_away"
    return envelope, sorted(set(reasons)), {"market_entry": market, "official_entry": official}


def evaluate_training_eligibility(
    role: str,
    profile_document: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    match_id: str,
    cutoff_profile: str,
    prediction_cutoff_at: str,
    kickoff_at: str,
    label: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if role not in ENGINE_ROLES:
        raise TrainingEligibilityError("UNSUPPORTED_ENGINE_ROLE", role)
    cutoff = _parse_timestamp(prediction_cutoff_at)
    kickoff = _parse_timestamp(kickoff_at)
    if cutoff is None or kickoff is None or not cutoff < kickoff:
        raise TrainingEligibilityError("CUTOFF_BINDING_INVALID", match_id)
    profile = profile_document["engine_profiles"][role]
    envelope, reasons, market_refs = _market_envelope(role, profile, entries, cutoff, kickoff)
    domain_coverage: dict[str, Any] = {domain: {"required": False, "available": False, "source_refs": []} for domain in ("STATISTICAL", "FOOTBALL", "MARKET", "TACTICAL")}
    for feature in profile.get("required_features", []):
        feature_id = str(feature["feature_id"])
        domain = str(feature["domain"])
        domain_coverage[domain]["required"] = True
        if domain == "MARKET":
            item = envelope.get(feature_id)
        else:
            entry = _domain_entry(entries, {"STATISTICAL": "statistical_feature_artifact_ref", "FOOTBALL": "football_intelligence_ref"}.get(domain, ""))
            values = _unwrap_feature_values(_payload(entry)) if entry else {}
            item_value = values.get(feature_id) if isinstance(values, Mapping) else None
            raw_value, metadata = _metadata_for(entry or {}, item_value)
            item = dict(metadata, value=raw_value)
            if entry:
                item.setdefault("reconstruction_rule", _payload(entry).get("reconstruction_rule"))
                item.setdefault("reconstruction_version", _payload(entry).get("reconstruction_version"))
                item.setdefault("reconstruction_hash", _payload(entry).get("reconstruction_hash"))
            if item_value is not None:
                envelope[feature_id] = item
        if not isinstance(item, Mapping) or item.get("state") != "AVAILABLE" or not _valid_number(item.get("value")):
            reasons.append(f"MISSING_REQUIRED_MINIMUM_FEATURE:{feature_id}")
            continue
        availability = _parse_timestamp(item.get("source_availability_at"))
        if availability is None or not availability <= cutoff < kickoff:
            reasons.append(f"FEATURE_AS_OF_BOUNDARY_FAILED:{feature_id}")
        source_refs = item.get("source_refs")
        source_hashes = item.get("source_hashes")
        if not isinstance(source_refs, list) or not source_refs or not isinstance(source_hashes, list) or not source_hashes or any(not _is_hash(value) for value in source_hashes):
            reasons.append(f"REQUIRED_FEATURE_PROVENANCE_MISSING:{feature_id}")
        if not item.get("information_time") or not item.get("reconstruction_rule") or not item.get("reconstruction_version") or not _is_hash(item.get("reconstruction_hash")):
            reasons.append(f"DETERMINISTIC_RECONSTRUCTION_METADATA_MISSING:{feature_id}")
        domain_coverage[domain]["available"] = True
        domain_coverage[domain]["source_refs"].extend(str(value) for value in source_refs if value)
    if label is None:
        reasons.append("MISSING_POST_MATCH_LABEL")
    else:
        label_time = _parse_timestamp(label.get("source_timestamp"))
        if label_time is None or label_time < kickoff:
            reasons.append("POST_MATCH_LABEL_TIME_INVALID")
        if not _is_hash(label.get("artifact_hash")) or not label.get("record_ref") or not label.get("manifest_ref"):
            reasons.append("LABEL_PROVENANCE_INVALID")
    if role == "HANDICAP" and "official_rqspf_handicap_value_at_cutoff" not in envelope:
        reasons.append("OFFICIAL_RQSPF_REQUIRED")
    reasons = sorted(set(reasons))
    state = "ELIGIBLE" if not reasons else "INELIGIBLE"
    mask = {feature["feature_id"]: envelope.get(feature["feature_id"], {"state": "UNKNOWN", "missingness_mask": True}).get("state", "UNKNOWN") for feature in (*profile.get("required_features", []), *profile.get("optional_features", []))}
    deterministic = {
        "as_of_predicate": "source_availability_at <= prediction_cutoff_at < kickoff_at",
        "reconstruction_rule_versions_hash": sha256_json({key: {"rule": value.get("reconstruction_rule"), "version": value.get("reconstruction_version"), "hash": value.get("reconstruction_hash")} for key, value in sorted(envelope.items())}),
    }
    return {
        "profile_hash": profile_document["profile_hash"],
        "profile_version": PROFILE_ID,
        "engine_role": role,
        "match_id": match_id,
        "cutoff_profile": cutoff_profile,
        "prediction_cutoff_at": prediction_cutoff_at,
        "kickoff_at": kickoff_at,
        "eligibility_state": state,
        "reasons": reasons,
        "feature_envelope": envelope,
        "availability_mask": mask,
        "domain_coverage": domain_coverage,
        "source_refs": sorted({str(entry.get("record_ref")) for entry in entries if entry.get("record_ref")} | {str(value) for value in domain_coverage.get("MARKET", {}).get("source_refs", [])}),
        "label_partition": {"feature_partition": "PRE_MATCH", "label_partition": "POST_MATCH", "label_ref": label.get("record_ref") if label else None, "label_hash": label.get("artifact_hash") if label else None},
        "deterministic_reconstruction": deterministic,
        "market_source_refs": {key: (value.get("record_ref") if value else None) for key, value in market_refs.items()},
        "tactical_required": False,
    }


def make_training_gate_record(evaluation: Mapping[str, Any], *, gate_document: Mapping[str, Any], record_ref: str, revision: int = 1, supersedes: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "training_gate_record_id": "tgr-" + sha256_json({"match_id": evaluation["match_id"], "cutoff_profile": evaluation["cutoff_profile"], "engine_role": evaluation["engine_role"], "profile_hash": evaluation["profile_hash"]})[7:39],
        "gate_version": TRAINING_GATE_ID,
        "gate_hash": gate_document["gate_hash"],
        "profile_version": PROFILE_ID,
        "profile_hash": evaluation["profile_hash"],
        "match_id": evaluation["match_id"],
        "cutoff_profile": evaluation["cutoff_profile"],
        "prediction_cutoff_at": evaluation["prediction_cutoff_at"],
        "kickoff_at": evaluation["kickoff_at"],
        "engine_role": evaluation["engine_role"],
        "eligibility_state": evaluation["eligibility_state"],
        "reasons": list(evaluation["reasons"]),
        "feature_envelope": evaluation["feature_envelope"],
        "availability_mask": evaluation["availability_mask"],
        "domain_coverage": evaluation["domain_coverage"],
        "source_refs": evaluation["source_refs"],
        "label_partition": evaluation["label_partition"],
        "deterministic_reconstruction": evaluation["deterministic_reconstruction"],
        "market_source_refs": evaluation["market_source_refs"],
        "tactical_required": False,
        "record_ref": record_ref,
        "revision": revision,
        "supersedes": supersedes,
    }
    record["record_hash"] = sha256_json(record)
    return record


def make_profile_file() -> dict[str, Any]:
    """Return the canonical active profile document for repository generation."""

    return _build_default_profile()


def make_gate_file() -> dict[str, Any]:
    """Return the canonical active gate document for repository generation."""

    return _build_default_gate()


__all__ = [
    "PROFILE_PATH_NAME", "AVAILABILITY_STATES", "PROFILE_ID", "TRAINING_GATE_ID", "TrainingEligibilityError",
    "evaluate_training_eligibility", "load_training_gate", "load_training_profile", "make_gate_file", "make_profile_file",
    "make_training_gate_record", "validate_training_gate", "validate_training_profile",
]
