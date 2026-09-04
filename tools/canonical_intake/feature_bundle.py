"""V4-038 typed Feature Bundle contract and version registry.

This is an in-memory, append-only representation boundary.  It validates
accepted upstream lineage and feature schemas, but it does not calculate
football, market, statistical, prediction, or score-engine features.
Frozen Input is deliberately downstream and is never required here.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore


CONTRACT_VERSION = "feature-bundle@2.0.0"
SCHEMA_CONTRACT_VERSION = "feature-schema@1.0.0"
FEATURE_BUNDLE_NAMESPACE = uuid.UUID("a86a8589-cdb0-5b9d-a63a-5d46c3f5c3f3")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

FEATURE_CATEGORIES = (
    "statistical_features",
    "football_context_features",
    "market_features",
    "league_features",
    "tactical_features",
    "score_features",
    "quality_features",
)


class FeatureState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


NON_AVAILABLE_STATES = frozenset(state for state in FeatureState if state is not FeatureState.AVAILABLE)
FORBIDDEN_FIELDS = frozenset(
    {
        "prediction",
        "recommendation",
        "confidence",
        "model_confidence",
        "betting_confidence",
        "win_probability",
        "engine_output",
        "risk_decision",
        "score_selection",
        "model_interpretation",
        "frozen_input_id",
        "frozen_input_hash",
    }
)


class FeatureBundleValidationError(ValueError):
    """A Feature Bundle cannot be safely admitted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeatureBundleValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _hash(value: Any, field_name: str) -> str:
    result = _required_text(value, field_name)
    if not HASH_RE.fullmatch(result):
        raise FeatureBundleValidationError("HASH_INVALID", f"{field_name} must be sha256:<64 lowercase hex>")
    return result


def _json_safe(value: Any, path: str = "value") -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise FeatureBundleValidationError("PAYLOAD_KEY_INVALID", f"{path} keys must be strings")
            _json_safe(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_safe(child, f"{path}[{index}]")
        return
    raise FeatureBundleValidationError("PAYLOAD_TYPE_INVALID", f"{path} is not JSON-compatible")


def _forbidden(value: Any, path: str = "bundle") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if normalized in {re.sub(r"[^a-z0-9_]", "", item) for item in FORBIDDEN_FIELDS}:
                return f"{path}.{key}"
            if normalized != "prediction_cutoff_at" and any(token in normalized for token in ("prediction", "recommendation", "modelconfidence", "bettingconfidence", "winprobability", "engineoutput", "riskdecision")):
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


def _ref_id(value: Mapping[str, Any], field_name: str) -> str:
    for key in ("ref_id", "id", "object_id", "snapshot_id", "context_id", "evidence_id", "evidence_bundle_id"):
        if key in value and isinstance(value[key], str) and value[key].strip():
            return value[key].strip()
    raise FeatureBundleValidationError("LINEAGE_REFERENCE_ID_MISSING", f"{field_name} requires a stable reference ID")


def _ref_hash(value: Mapping[str, Any], field_name: str) -> str:
    candidates = ["hash", "ref_hash", "object_hash", "snapshot_hash", "context_hash", "evidence_hash", "provenance_hash"]
    for key in candidates:
        if key in value:
            return _hash(value[key], f"{field_name}.{key}")
    for key, child in value.items():
        if str(key).endswith("_hash"):
            return _hash(child, f"{field_name}.{key}")
    raise FeatureBundleValidationError("LINEAGE_REFERENCE_HASH_MISSING", f"{field_name} requires an exact hash")


def _validate_refs(value: Any, field_name: str, *, allow_empty: bool = True, source_role: Optional[bool] = None) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise FeatureBundleValidationError("LINEAGE_COLLECTION_INVALID", f"{field_name} must be an explicit list")
    if not value and not allow_empty:
        raise FeatureBundleValidationError("LINEAGE_COLLECTION_EMPTY", f"{field_name} cannot be empty")
    result: List[Mapping[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise FeatureBundleValidationError("LINEAGE_REFERENCE_INVALID", f"{field_name}[{index}] must be an object")
        item = dict(raw)
        _ref_id(item, f"{field_name}[{index}]")
        _ref_hash(item, f"{field_name}[{index}]")
        if source_role is not None:
            if "source_is_official" not in item or item["source_is_official"] is not source_role:
                expected = "true" if source_role else "false"
                raise FeatureBundleValidationError("SOURCE_ROLE_CONFLICT", f"{field_name}[{index}] must declare source_is_official={expected}")
        result.append(_freeze(item))
    return tuple(result)


def _validate_entity_refs(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FeatureBundleValidationError("CANONICAL_ENTITY_REFS_INVALID", "canonical_entity_refs must be an object")
    result = dict(value)
    match_id = _required_text(result.get("match_id"), "canonical_entity_refs.match_id")
    result["match_id"] = match_id
    _ref_hash(result, "canonical_entity_refs")
    for field_name in ("home_team_id", "away_team_id"):
        _required_text(result.get(field_name), f"canonical_entity_refs.{field_name}")
    if result["home_team_id"] == result["away_team_id"]:
        raise FeatureBundleValidationError("CANONICAL_SIDE_CONFLICT", "home and away team IDs must differ")
    _json_safe(result, "canonical_entity_refs")
    return _freeze(result)


@dataclass(frozen=True)
class FeatureQuality:
    coverage: str
    verification: str
    freshness: str
    completeness: str
    conflict: str
    provenance: str

    @classmethod
    def from_dict(cls, raw: Any) -> "FeatureQuality":
        if not isinstance(raw, Mapping):
            raise FeatureBundleValidationError("FEATURE_QUALITY_INVALID", "feature_quality must be an object")
        allowed = {
            "coverage": {"COMPLETE", "PARTIAL", "UNKNOWN"},
            "verification": {"VERIFIED", "PARTIAL", "UNKNOWN"},
            "freshness": {"CURRENT", "STALE", "UNKNOWN"},
            "completeness": {"COMPLETE", "PARTIAL", "UNKNOWN"},
            "conflict": {"NONE", "PRESENT", "UNKNOWN"},
            "provenance": {"RESOLVED", "PARTIAL", "UNKNOWN"},
        }
        values: Dict[str, str] = {}
        for field_name, choices in allowed.items():
            value = _required_text(raw.get(field_name), f"feature_quality.{field_name}")
            if value not in choices:
                raise FeatureBundleValidationError("FEATURE_QUALITY_VALUE_INVALID", f"feature_quality.{field_name} is invalid")
            values[field_name] = value
        if "score" in raw or "confidence" in raw:
            raise FeatureBundleValidationError("PREDICTION_CONFIDENCE_FORBIDDEN", "feature_quality cannot contain a numeric or bare confidence score")
        return cls(**values)

    def to_dict(self) -> Dict[str, str]:
        return {
            "coverage": self.coverage,
            "verification": self.verification,
            "freshness": self.freshness,
            "completeness": self.completeness,
            "conflict": self.conflict,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class FeatureRecord:
    value: Any
    state: FeatureState
    unit: Optional[str]
    source_refs: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    derivation_ref: Optional[str]
    generator_ref: str
    reason_code: Optional[str]
    reason_detail: Optional[str]

    @classmethod
    def from_dict(cls, raw: Any, path: str, generator_ref: str) -> "FeatureRecord":
        if not isinstance(raw, Mapping):
            raise FeatureBundleValidationError("FEATURE_RECORD_INVALID", f"{path} must be an object")
        state_raw = raw.get("state")
        try:
            state = state_raw if isinstance(state_raw, FeatureState) else FeatureState(state_raw)
        except (TypeError, ValueError) as exc:
            raise FeatureBundleValidationError("FEATURE_STATE_INVALID", f"{path}.state is not a governed state") from exc
        value = raw.get("value")
        if state is FeatureState.AVAILABLE:
            if value is None or value == "" or value == [] or value == {}:
                raise FeatureBundleValidationError("AVAILABLE_VALUE_EMPTY", f"{path}.AVAILABLE requires a non-empty value")
        else:
            reason_code = raw.get("reason_code")
            if not isinstance(reason_code, str) or not REASON_CODE_RE.fullmatch(reason_code):
                raise FeatureBundleValidationError("FEATURE_REASON_REQUIRED", f"{path} requires an explicit reason_code")
            if not isinstance(raw.get("reason_detail"), str) or not raw["reason_detail"].strip():
                raise FeatureBundleValidationError("FEATURE_REASON_DETAIL_REQUIRED", f"{path} requires reason_detail")
        source_refs = tuple(_required_text(item, f"{path}.source_refs") for item in raw.get("source_refs", []))
        evidence_refs = tuple(_required_text(item, f"{path}.evidence_refs") for item in raw.get("evidence_refs", []))
        if not source_refs and not evidence_refs:
            raise FeatureBundleValidationError("FEATURE_PROVENANCE_MISSING", f"{path} requires source_refs or evidence_refs")
        unit = raw.get("unit")
        if unit is not None:
            unit = _required_text(unit, f"{path}.unit")
        derivation = raw.get("derivation_ref")
        if derivation is not None:
            derivation = _required_text(derivation, f"{path}.derivation_ref")
        _json_safe(value, f"{path}.value")
        return cls(
            value=_freeze(value),
            state=state,
            unit=unit,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            derivation_ref=derivation,
            generator_ref=_required_text(generator_ref, f"{path}.generator_ref"),
            reason_code=raw.get("reason_code") if state is not FeatureState.AVAILABLE else None,
            reason_detail=raw.get("reason_detail") if state is not FeatureState.AVAILABLE else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "value": _thaw(self.value),
            "state": self.state.value,
            "unit": self.unit,
            "source_refs": list(self.source_refs),
            "evidence_refs": list(self.evidence_refs),
            "derivation_ref": self.derivation_ref,
            "generator_ref": self.generator_ref,
        }
        if self.state is not FeatureState.AVAILABLE:
            result.update({"reason_code": self.reason_code, "reason_detail": self.reason_detail})
        return result


@dataclass(frozen=True)
class FeatureSchema:
    schema_version: str
    generator_version: str
    categories: Tuple[str, ...]
    registered_by: str
    metadata: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Any) -> "FeatureSchema":
        if not isinstance(raw, Mapping):
            raise FeatureBundleValidationError("FEATURE_SCHEMA_INVALID", "feature schema must be an object")
        schema_version = _required_text(raw.get("schema_version"), "schema_version")
        generator_version = _required_text(raw.get("generator_version"), "generator_version")
        categories = tuple(raw.get("categories", ()))
        if categories != FEATURE_CATEGORIES:
            raise FeatureBundleValidationError("FEATURE_CATEGORIES_INVALID", "schema must declare the seven categories in canonical order")
        registered_by = _required_text(raw.get("registered_by"), "registered_by")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise FeatureBundleValidationError("FEATURE_SCHEMA_METADATA_INVALID", "schema metadata must be an object")
        return cls(schema_version, generator_version, categories, registered_by, _freeze(metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generator_version": self.generator_version,
            "categories": list(self.categories),
            "registered_by": self.registered_by,
            "metadata": _thaw(self.metadata),
        }


class FeatureSchemaRegistry:
    """Append-only registry for exact feature schema/generator identities."""

    def __init__(self):
        self._schemas: Dict[Tuple[str, str], FeatureSchema] = {}

    @property
    def schemas(self) -> Tuple[FeatureSchema, ...]:
        return tuple(self._schemas.values())

    def register(self, raw: Union[FeatureSchema, Mapping[str, Any]]) -> FeatureSchema:
        schema = raw if isinstance(raw, FeatureSchema) else FeatureSchema.from_dict(raw)
        key = (schema.schema_version, schema.generator_version)
        if key in self._schemas:
            raise FeatureBundleValidationError("FEATURE_SCHEMA_ID_REUSE", "schema/generator identity is already registered")
        self._schemas[key] = schema
        return schema

    def resolve(self, schema_version: str, generator_version: str) -> Optional[FeatureSchema]:
        return self._schemas.get((schema_version, generator_version))


@dataclass(frozen=True)
class FeatureBundle:
    object_id: str
    feature_bundle_id: str
    contract_version: str
    feature_schema_version: str
    generator_version: str
    role: str
    config_version: str
    config_hash: str
    canonical_entity_refs: Mapping[str, Any]
    canonical_fact_refs: Tuple[Mapping[str, Any], ...]
    official_odds_snapshot_refs: Tuple[Mapping[str, Any], ...]
    external_market_refs: Tuple[Mapping[str, Any], ...]
    team_context_refs: Tuple[Mapping[str, Any], ...]
    evidence_graph_refs: Tuple[Mapping[str, Any], ...]
    prediction_cutoff_at: str
    kickoff_at: str
    generated_at: str
    feature_values: Mapping[str, Tuple[FeatureRecord, ...]]
    missingness_summary: Mapping[str, Any]
    feature_quality: FeatureQuality
    quality_flags: Tuple[str, ...]
    input_hash: str
    feature_hash: str
    payload_hash: str
    provenance_hash: str
    feature_snapshot_hash: Optional[str]
    status: str
    revision: int
    supersedes_feature_bundle_id: Optional[str]
    metadata: Mapping[str, Any]

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, Any],
        *,
        identity_store: Optional[CanonicalMatchIdentityStore] = None,
        schema_registry: Optional[FeatureSchemaRegistry] = None,
    ) -> "FeatureBundle":
        if not isinstance(raw, Mapping):
            raise FeatureBundleValidationError("BUNDLE_INVALID", "Feature Bundle must be an object")
        forbidden = _forbidden(raw)
        if forbidden:
            if forbidden.endswith("frozen_input_id") or forbidden.endswith("frozen_input_hash"):
                raise FeatureBundleValidationError("FROZEN_INPUT_UPSTREAM_FORBIDDEN", "Frozen Input is downstream and cannot be a V4-038 input")
            raise FeatureBundleValidationError("MODEL_FIELD_FORBIDDEN", f"model/prediction field is forbidden: {forbidden}")
        contract = _required_text(raw.get("contract_version"), "contract_version")
        if contract != CONTRACT_VERSION:
            raise FeatureBundleValidationError("CONTRACT_VERSION_INVALID", f"expected {CONTRACT_VERSION}")
        feature_schema_version = _required_text(raw.get("feature_schema_version"), "feature_schema_version")
        generator_version = _required_text(raw.get("generator_version"), "generator_version")
        if schema_registry is not None and schema_registry.resolve(feature_schema_version, generator_version) is None:
            raise FeatureBundleValidationError("FEATURE_SCHEMA_NOT_REGISTERED", "schema/generator identity is not registered")
        role = _required_text(raw.get("role"), "role")
        if role not in {"PRODUCTION", "SHADOW", "EXPERIMENT"}:
            raise FeatureBundleValidationError("ROLE_INVALID", "role must be PRODUCTION, SHADOW, or EXPERIMENT")
        config_version = _required_text(raw.get("config_version"), "config_version")
        config_hash = _hash(raw.get("config_hash"), "config_hash")
        entity_refs = _validate_entity_refs(raw.get("canonical_entity_refs"))
        match_id = entity_refs["match_id"]
        if identity_store is not None:
            identity = identity_store.get(match_id)
            if identity is None:
                raise FeatureBundleValidationError("MATCH_IDENTITY_NOT_FOUND", "canonical match identity does not exist")
            if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
                raise FeatureBundleValidationError("MATCH_IDENTITY_NOT_RESOLVED", "canonical match identity is not resolved")
        canonical_facts = _validate_refs(raw.get("canonical_fact_refs"), "canonical_fact_refs", allow_empty=False)
        official = _validate_refs(raw.get("official_odds_snapshot_refs"), "official_odds_snapshot_refs", source_role=True)
        external = _validate_refs(raw.get("external_market_refs"), "external_market_refs", source_role=False)
        team_context = _validate_refs(raw.get("team_context_refs"), "team_context_refs")
        evidence = _validate_refs(raw.get("evidence_graph_refs"), "evidence_graph_refs")
        cutoff = _required_text(raw.get("prediction_cutoff_at"), "prediction_cutoff_at")
        kickoff = _required_text(raw.get("kickoff_at"), "kickoff_at")
        generated_at = _required_text(raw.get("generated_at"), "generated_at")
        raw_features = raw.get("feature_values")
        if not isinstance(raw_features, Mapping) or tuple(raw_features.keys()) != FEATURE_CATEGORIES:
            raise FeatureBundleValidationError("FEATURE_CATEGORIES_INVALID", "feature_values must contain the seven categories in canonical order")
        features: Dict[str, Tuple[FeatureRecord, ...]] = {}
        for category in FEATURE_CATEGORIES:
            values = raw_features[category]
            if not isinstance(values, (list, tuple)):
                raise FeatureBundleValidationError("FEATURE_CATEGORY_INVALID", f"{category} must be a list")
            features[category] = tuple(FeatureRecord.from_dict(item, f"feature_values.{category}[{i}]", generator_version) for i, item in enumerate(values))
        missingness = raw.get("missingness_summary")
        if not isinstance(missingness, Mapping):
            raise FeatureBundleValidationError("MISSINGNESS_SUMMARY_INVALID", "missingness_summary must be an object")
        quality = FeatureQuality.from_dict(raw.get("feature_quality"))
        flags_raw = raw.get("quality_flags", [])
        if not isinstance(flags_raw, (list, tuple)):
            raise FeatureBundleValidationError("QUALITY_FLAGS_INVALID", "quality_flags must be a list")
        quality_flags = tuple(_required_text(item, "quality_flags") for item in flags_raw)
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise FeatureBundleValidationError("METADATA_INVALID", "metadata must be an object")
        input_payload = {
            "contract_version": contract,
            "feature_schema_version": feature_schema_version,
            "generator_version": generator_version,
            "role": role,
            "config_version": config_version,
            "config_hash": config_hash,
            "canonical_entity_refs": _thaw(entity_refs),
            "canonical_fact_refs": [_thaw(item) for item in canonical_facts],
            "official_odds_snapshot_refs": [_thaw(item) for item in official],
            "external_market_refs": [_thaw(item) for item in external],
            "team_context_refs": [_thaw(item) for item in team_context],
            "evidence_graph_refs": [_thaw(item) for item in evidence],
            "prediction_cutoff_at": cutoff,
            "kickoff_at": kickoff,
        }
        calculated_input_hash = sha256_json(input_payload)
        supplied_input_hash = raw.get("input_hash")
        input_hash = calculated_input_hash if supplied_input_hash is None else _hash(supplied_input_hash, "input_hash")
        if input_hash != calculated_input_hash:
            raise FeatureBundleValidationError("INPUT_HASH_MISMATCH", "input_hash does not match accepted upstream lineage")
        feature_payload = {category: [item.to_dict() for item in features[category]] for category in FEATURE_CATEGORIES}
        calculated_feature_hash = sha256_json(feature_payload)
        feature_hash = calculated_feature_hash if raw.get("feature_hash") is None else _hash(raw["feature_hash"], "feature_hash")
        if feature_hash != calculated_feature_hash:
            raise FeatureBundleValidationError("FEATURE_HASH_MISMATCH", "feature_hash is not recomputable")
        payload_hash = sha256_json({"feature_values": feature_payload, "missingness_summary": dict(missingness), "quality_flags": list(quality_flags)})
        if raw.get("payload_hash") is not None and _hash(raw["payload_hash"], "payload_hash") != payload_hash:
            raise FeatureBundleValidationError("PAYLOAD_HASH_MISMATCH", "payload_hash is not recomputable")
        provenance_hash = sha256_json({"canonical_entity_refs": _thaw(entity_refs), "canonical_fact_refs": [_thaw(item) for item in canonical_facts], "official_odds_snapshot_refs": [_thaw(item) for item in official], "external_market_refs": [_thaw(item) for item in external], "team_context_refs": [_thaw(item) for item in team_context], "evidence_graph_refs": [_thaw(item) for item in evidence]})
        if raw.get("provenance_hash") is not None and _hash(raw["provenance_hash"], "provenance_hash") != provenance_hash:
            raise FeatureBundleValidationError("PROVENANCE_HASH_MISMATCH", "provenance_hash is not recomputable")
        snapshot_hash = raw.get("feature_snapshot_hash")
        if snapshot_hash is not None:
            snapshot_hash = _hash(snapshot_hash, "feature_snapshot_hash")
        bundle_id = raw.get("feature_bundle_id") or str(uuid.uuid5(FEATURE_BUNDLE_NAMESPACE, f"bundle|{input_hash}|{feature_hash}|{raw.get('revision', 1)}"))
        object_id = raw.get("object_id") or bundle_id
        revision = raw.get("revision", 1)
        if not isinstance(revision, int) or revision < 1:
            raise FeatureBundleValidationError("REVISION_INVALID", "revision must be a positive integer")
        return cls(
            object_id=_required_text(object_id, "object_id"), feature_bundle_id=_required_text(bundle_id, "feature_bundle_id"), contract_version=contract,
            feature_schema_version=feature_schema_version, generator_version=generator_version, role=role, config_version=config_version, config_hash=config_hash,
            canonical_entity_refs=entity_refs, canonical_fact_refs=canonical_facts, official_odds_snapshot_refs=official, external_market_refs=external,
            team_context_refs=team_context, evidence_graph_refs=evidence, prediction_cutoff_at=cutoff, kickoff_at=kickoff, generated_at=generated_at, feature_values=_freeze(features),
            missingness_summary=_freeze(missingness), feature_quality=quality, quality_flags=quality_flags, input_hash=input_hash, feature_hash=feature_hash,
            payload_hash=payload_hash, provenance_hash=provenance_hash, feature_snapshot_hash=snapshot_hash,
            status=_required_text(raw.get("status", "CREATED"), "status"), revision=revision,
            supersedes_feature_bundle_id=raw.get("supersedes_feature_bundle_id"), metadata=_freeze(metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id, "feature_bundle_id": self.feature_bundle_id, "contract_version": self.contract_version,
            "feature_schema_version": self.feature_schema_version, "generator_version": self.generator_version, "role": self.role,
            "config_version": self.config_version, "config_hash": self.config_hash, "canonical_entity_refs": _thaw(self.canonical_entity_refs),
            "canonical_fact_refs": [_thaw(item) for item in self.canonical_fact_refs], "official_odds_snapshot_refs": [_thaw(item) for item in self.official_odds_snapshot_refs],
            "external_market_refs": [_thaw(item) for item in self.external_market_refs], "team_context_refs": [_thaw(item) for item in self.team_context_refs],
            "evidence_graph_refs": [_thaw(item) for item in self.evidence_graph_refs], "prediction_cutoff_at": self.prediction_cutoff_at, "kickoff_at": self.kickoff_at, "generated_at": self.generated_at,
            "feature_values": {category: [item.to_dict() for item in self.feature_values[category]] for category in FEATURE_CATEGORIES},
            "missingness_summary": _thaw(self.missingness_summary), "feature_quality": self.feature_quality.to_dict(), "quality_flags": list(self.quality_flags),
            "input_hash": self.input_hash, "feature_hash": self.feature_hash, "payload_hash": self.payload_hash, "provenance_hash": self.provenance_hash,
            "feature_snapshot_hash": self.feature_snapshot_hash, "status": self.status, "revision": self.revision,
            "supersedes_feature_bundle_id": self.supersedes_feature_bundle_id, "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class FeatureBundleResult:
    accepted: bool
    action: str
    feature_bundle_id: str
    bundle: Optional[FeatureBundle]
    error_code: Optional[str] = None


@dataclass(frozen=True)
class _BundleEvent:
    sequence: int
    action: str
    feature_bundle_id: str
    revision: Optional[int]
    supersedes_feature_bundle_id: Optional[str]
    error_code: Optional[str] = None


class FeatureBundleStore:
    """Append-only local Feature Bundle store bound to V4-020 identity."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore, schema_registry: Optional[FeatureSchemaRegistry] = None):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-038 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._schema_registry = schema_registry or FeatureSchemaRegistry()
        self._bundles: Dict[str, FeatureBundle] = {}
        self._events: List[_BundleEvent] = []

    @property
    def bundles(self) -> Tuple[FeatureBundle, ...]:
        return tuple(self._bundles.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(MappingProxyType({"sequence": event.sequence, "action": event.action, "feature_bundle_id": event.feature_bundle_id, "revision": event.revision, "supersedes_feature_bundle_id": event.supersedes_feature_bundle_id, "error_code": event.error_code}) for event in self._events)

    def get(self, feature_bundle_id: str) -> Optional[FeatureBundle]:
        return self._bundles.get(feature_bundle_id)

    def ingest(self, raw: Mapping[str, Any]) -> FeatureBundleResult:
        bundle_id = str(raw.get("feature_bundle_id", raw.get("object_id", "blocked-feature-bundle"))) if isinstance(raw, Mapping) else "blocked-feature-bundle"
        try:
            bundle = FeatureBundle.from_dict(raw, identity_store=self._identity_store, schema_registry=self._schema_registry)
        except FeatureBundleValidationError as exc:
            self._events.append(_BundleEvent(len(self._events) + 1, "BLOCKED", bundle_id, None, None, exc.code))
            return FeatureBundleResult(False, "BLOCKED", bundle_id, None, exc.code)
        existing = self._bundles.get(bundle.feature_bundle_id)
        if existing is not None:
            if existing.to_dict() == bundle.to_dict():
                self._events.append(_BundleEvent(len(self._events) + 1, "DUPLICATE_NOOP", bundle.feature_bundle_id, existing.revision, None))
                return FeatureBundleResult(True, "DUPLICATE_NOOP", bundle.feature_bundle_id, existing)
            self._events.append(_BundleEvent(len(self._events) + 1, "BLOCKED", bundle.feature_bundle_id, None, None, "FEATURE_BUNDLE_ID_REUSE"))
            return FeatureBundleResult(False, "BLOCKED", bundle.feature_bundle_id, None, "FEATURE_BUNDLE_ID_REUSE")
        if bundle.supersedes_feature_bundle_id is not None:
            predecessor = self._bundles.get(bundle.supersedes_feature_bundle_id)
            if predecessor is None:
                return self._blocked(bundle.feature_bundle_id, "SUPERSEDES_TARGET_NOT_FOUND")
            if predecessor.canonical_entity_refs["match_id"] != bundle.canonical_entity_refs["match_id"] or bundle.revision != predecessor.revision + 1:
                return self._blocked(bundle.feature_bundle_id, "SUPERSEDES_FAMILY_OR_REVISION_CONFLICT")
        self._bundles[bundle.feature_bundle_id] = bundle
        self._events.append(_BundleEvent(len(self._events) + 1, "APPEND", bundle.feature_bundle_id, bundle.revision, bundle.supersedes_feature_bundle_id))
        return FeatureBundleResult(True, "APPEND", bundle.feature_bundle_id, bundle)

    def _blocked(self, feature_bundle_id: str, code: str) -> FeatureBundleResult:
        self._events.append(_BundleEvent(len(self._events) + 1, "BLOCKED", feature_bundle_id, None, None, code))
        return FeatureBundleResult(False, "BLOCKED", feature_bundle_id, None, code)


__all__ = [
    "CONTRACT_VERSION", "FEATURE_CATEGORIES", "FeatureState", "FeatureQuality", "FeatureRecord", "FeatureSchema", "FeatureSchemaRegistry",
    "FeatureBundle", "FeatureBundleResult", "FeatureBundleStore", "FeatureBundleValidationError",
]
