"""V4-040 typed Feature Bundle assembly and schema-adapter boundary.

The assembler accepts only versioned, identity-bound V4 objects and an
already-typed Feature Bundle. It never reads raw source material and never
calculates a model feature or prediction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .feature_bundle import FEATURE_CATEGORIES, FeatureBundle, FeatureBundleValidationError


CONTRACT_VERSION = "feature-assembly@1.0.0"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_KINDS = (
    "canonical_fact",
    "official_odds_snapshot",
    "external_market_snapshot",
    "team_context",
    "evidence_graph",
)
ALLOWED_STATES = {"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED", "NOT_APPLICABLE"}
RAW_SOURCE_KEYS = {
    "raw_screenshot",
    "screenshot_bytes",
    "ocr_raw_text",
    "provider_raw_response",
    "free_form_news",
    "unversioned_json",
    "display_name_join",
    "join_key",
}


class FeatureAssemblyValidationError(ValueError):
    """A Feature Bundle assembly input is unsafe or incompatible."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeatureAssemblyValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise FeatureAssemblyValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _json_walk(value: Any, path: str = "input") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in RAW_SOURCE_KEYS or "v333" in normalized or "v3_3_3" in normalized:
                raise FeatureAssemblyValidationError("RAW_SOURCE_BYPASS", f"raw/unversioned or V3.3.3 field is forbidden: {path}.{key}")
            if normalized == "display_name" and path != "input.feature_values":
                # A display name can be descriptive payload, but this boundary
                # rejects it in the assembly envelope so it cannot become a join key.
                raise FeatureAssemblyValidationError("DISPLAY_NAME_JOIN_FORBIDDEN", f"display_name cannot identify an assembly input: {path}.{key}")
            _json_walk(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_walk(child, f"{path}[{index}]")


def _time(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FeatureAssemblyValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeatureAssemblyValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} must be timezone-aware")
    return parsed


@dataclass(frozen=True)
class VersionedSourceObject:
    source_kind: str
    schema_version: str
    object_id: str
    object_hash: str
    match_id: str
    source: str
    source_reference: str
    source_is_official: Optional[bool]
    status: str
    available_at: str
    provenance_hash: str
    payload: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Any, index: int) -> "VersionedSourceObject":
        if not isinstance(raw, Mapping):
            raise FeatureAssemblyValidationError("SOURCE_OBJECT_INVALID", f"source_objects[{index}] must be an object")
        source_kind = _text(raw.get("source_kind"), f"source_objects[{index}].source_kind")
        if source_kind not in SOURCE_KINDS:
            raise FeatureAssemblyValidationError("SOURCE_KIND_INVALID", f"source_objects[{index}].source_kind is not approved")
        schema_version = _text(raw.get("schema_version"), f"source_objects[{index}].schema_version")
        object_id = _text(raw.get("object_id"), f"source_objects[{index}].object_id")
        object_hash = _hash(raw.get("object_hash"), f"source_objects[{index}].object_hash")
        match_id = _text(raw.get("match_id"), f"source_objects[{index}].match_id")
        source = _text(raw.get("source"), f"source_objects[{index}].source")
        source_reference = _text(raw.get("source_reference"), f"source_objects[{index}].source_reference")
        status = _text(raw.get("status"), f"source_objects[{index}].status")
        if status not in ALLOWED_STATES:
            raise FeatureAssemblyValidationError("SOURCE_STATUS_INVALID", f"source_objects[{index}].status is not governed")
        available_at = _text(raw.get("available_at", raw.get("observed_at")), f"source_objects[{index}].available_at")
        _time(available_at, f"source_objects[{index}].available_at")
        provenance_hash = _hash(raw.get("provenance_hash"), f"source_objects[{index}].provenance_hash")
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise FeatureAssemblyValidationError("SOURCE_PAYLOAD_INVALID", f"source_objects[{index}].payload must be an object")
        source_is_official = raw.get("source_is_official")
        if source_kind == "official_odds_snapshot" and source_is_official is not True:
            raise FeatureAssemblyValidationError("OFFICIAL_SOURCE_ROLE_INVALID", "official odds source must declare source_is_official=true")
        if source_kind == "external_market_snapshot" and source_is_official is not False:
            raise FeatureAssemblyValidationError("EXTERNAL_SOURCE_ROLE_INVALID", "external market source must declare source_is_official=false")
        return cls(source_kind, schema_version, object_id, object_hash, match_id, source, source_reference, source_is_official, status, available_at, provenance_hash, MappingProxyType(dict(payload)))

    def to_ref(self) -> Dict[str, Any]:
        result = {"ref_id": self.object_id, "hash": self.object_hash, "source": self.source, "source_reference": self.source_reference, "provenance_hash": self.provenance_hash}
        if self.source_is_official is not None:
            result["source_is_official"] = self.source_is_official
        return result


@dataclass(frozen=True)
class SchemaAdapter:
    source_kind: str
    source_schema_version: str
    target_feature_schema_version: str
    adapter_version: str

    @classmethod
    def from_dict(cls, raw: Any) -> "SchemaAdapter":
        if not isinstance(raw, Mapping):
            raise FeatureAssemblyValidationError("ADAPTER_INVALID", "schema adapter must be an object")
        source_kind = _text(raw.get("source_kind"), "schema_adapter.source_kind")
        if source_kind not in SOURCE_KINDS:
            raise FeatureAssemblyValidationError("SOURCE_KIND_INVALID", "schema adapter source kind is not approved")
        return cls(source_kind, _text(raw.get("source_schema_version"), "schema_adapter.source_schema_version"), _text(raw.get("target_feature_schema_version"), "schema_adapter.target_feature_schema_version"), _text(raw.get("adapter_version"), "schema_adapter.adapter_version"))


class SchemaAdapterRegistry:
    def __init__(self):
        self._adapters: Dict[Tuple[str, str, str], SchemaAdapter] = {}

    @property
    def adapters(self) -> Tuple[SchemaAdapter, ...]:
        return tuple(self._adapters.values())

    def register(self, raw: Union[SchemaAdapter, Mapping[str, Any]]) -> SchemaAdapter:
        adapter = raw if isinstance(raw, SchemaAdapter) else SchemaAdapter.from_dict(raw)
        key = (adapter.source_kind, adapter.source_schema_version, adapter.target_feature_schema_version)
        if key in self._adapters:
            raise FeatureAssemblyValidationError("ADAPTER_ID_REUSE", "schema adapter identity already exists")
        self._adapters[key] = adapter
        return adapter

    def resolve(self, source_kind: str, source_schema_version: str, target_feature_schema_version: str) -> Optional[SchemaAdapter]:
        return self._adapters.get((source_kind, source_schema_version, target_feature_schema_version))


def _missingness(feature_values: Mapping[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for category in FEATURE_CATEGORIES:
        for record in feature_values[category]:
            state = record.state.value
            counts[state] = counts.get(state, 0) + 1
    return counts


@dataclass(frozen=True)
class FeatureAssemblyResult:
    accepted: bool
    action: str
    bundle: Optional[FeatureBundle]
    handoff: Optional[Mapping[str, Any]]
    error_code: Optional[str] = None


class FeatureAssemblyStore:
    """Append-only downstream handoff ledger for assembled Feature Bundles."""

    def __init__(self, adapter_registry: SchemaAdapterRegistry):
        self._adapter_registry = adapter_registry
        self._handoffs: Dict[str, Mapping[str, Any]] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def handoffs(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._handoffs.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def assemble(self, raw: Mapping[str, Any]) -> FeatureAssemblyResult:
        try:
            _json_walk(raw)
            request = self._parse_request(raw)
            bundle = self._build_bundle(request)
            handoff = self._handoff(bundle, request["adapter_refs"])
        except (FeatureAssemblyValidationError, FeatureBundleValidationError) as exc:
            self._events.append({"sequence": len(self._events) + 1, "action": "BLOCKED", "error_code": getattr(exc, "code", "VALIDATION_FAILED")})
            return FeatureAssemblyResult(False, "BLOCKED", None, None, getattr(exc, "code", "VALIDATION_FAILED"))
        existing = self._handoffs.get(bundle.feature_bundle_id)
        if existing is not None:
            if existing == handoff:
                self._events.append({"sequence": len(self._events) + 1, "action": "DUPLICATE_NOOP", "feature_bundle_id": bundle.feature_bundle_id})
                return FeatureAssemblyResult(True, "DUPLICATE_NOOP", bundle, existing)
            self._events.append({"sequence": len(self._events) + 1, "action": "BLOCKED", "feature_bundle_id": bundle.feature_bundle_id, "error_code": "ASSEMBLY_ID_REUSE"})
            return FeatureAssemblyResult(False, "BLOCKED", None, None, "ASSEMBLY_ID_REUSE")
        self._handoffs[bundle.feature_bundle_id] = MappingProxyType(dict(handoff))
        self._events.append({"sequence": len(self._events) + 1, "action": "APPEND", "feature_bundle_id": bundle.feature_bundle_id})
        return FeatureAssemblyResult(True, "APPEND", bundle, self._handoffs[bundle.feature_bundle_id])

    def _parse_request(self, raw: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise FeatureAssemblyValidationError("ASSEMBLY_REQUEST_INVALID", "assembly request must be an object")
        feature_schema_version = _text(raw.get("target_feature_schema_version"), "target_feature_schema_version")
        generator_version = _text(raw.get("generator_version"), "generator_version")
        role = _text(raw.get("role"), "role")
        config_version = _text(raw.get("config_version"), "config_version")
        config_hash = _hash(raw.get("config_hash"), "config_hash")
        canonical_entity_refs = raw.get("canonical_entity_refs")
        if not isinstance(canonical_entity_refs, Mapping):
            raise FeatureAssemblyValidationError("CANONICAL_ENTITY_REFS_INVALID", "canonical_entity_refs is required")
        match_id = _text(canonical_entity_refs.get("match_id"), "canonical_entity_refs.match_id")
        source_objects_raw = raw.get("source_objects")
        if not isinstance(source_objects_raw, (list, tuple)) or not source_objects_raw:
            raise FeatureAssemblyValidationError("SOURCE_OBJECTS_REQUIRED", "versioned source_objects are required")
        source_objects = tuple(VersionedSourceObject.from_dict(item, i) for i, item in enumerate(source_objects_raw))
        for item in source_objects:
            if item.match_id != match_id:
                raise FeatureAssemblyValidationError("SOURCE_MATCH_CONFLICT", "all source objects must use the canonical match_id")
            if _time(item.available_at, "available_at") > _time(raw.get("prediction_cutoff_at"), "prediction_cutoff_at"):
                raise FeatureAssemblyValidationError("FUTURE_DATA", f"{item.object_id} is not eligible at cutoff")
        adapters_raw = raw.get("schema_adapters")
        if not isinstance(adapters_raw, (list, tuple)):
            raise FeatureAssemblyValidationError("SCHEMA_ADAPTERS_REQUIRED", "schema_adapters are required")
        adapter_refs: List[SchemaAdapter] = []
        for item in source_objects:
            adapter = self._adapter_registry.resolve(item.source_kind, item.schema_version, feature_schema_version)
            if adapter is None:
                raise FeatureAssemblyValidationError("SCHEMA_ADAPTER_NOT_FOUND", f"no compatible adapter for {item.source_kind}/{item.schema_version} -> {feature_schema_version}")
            adapter_refs.append(adapter)
        declared_keys = {(SchemaAdapter.from_dict(item).source_kind, SchemaAdapter.from_dict(item).source_schema_version, SchemaAdapter.from_dict(item).target_feature_schema_version) for item in adapters_raw}
        if any((adapter.source_kind, adapter.source_schema_version, adapter.target_feature_schema_version) not in declared_keys for adapter in adapter_refs):
            raise FeatureAssemblyValidationError("SCHEMA_ADAPTER_DECLARATION_MISMATCH", "declared adapters do not cover every source object")
        bundle_raw = raw.get("feature_bundle")
        if not isinstance(bundle_raw, Mapping):
            raise FeatureAssemblyValidationError("FEATURE_BUNDLE_REQUIRED", "assembly requires an already-typed feature_bundle")
        try:
            bundle = FeatureBundle.from_dict(bundle_raw)
        except FeatureBundleValidationError as exc:
            raise FeatureAssemblyValidationError(exc.code, str(exc)) from exc
        if bundle.feature_schema_version != feature_schema_version or bundle.generator_version != generator_version or bundle.role != role or bundle.config_hash != config_hash or bundle.config_version != config_version:
            raise FeatureAssemblyValidationError("BUNDLE_ASSEMBLY_IDENTITY_MISMATCH", "bundle identity does not match assembly target")
        if bundle.canonical_entity_refs["match_id"] != match_id:
            raise FeatureAssemblyValidationError("BUNDLE_MATCH_CONFLICT", "Feature Bundle match_id differs from assembly match_id")
        if bundle.feature_snapshot_hash is None:
            raise FeatureAssemblyValidationError("FEATURE_SNAPSHOT_REQUIRED", "V4-040 requires the V4-039 feature_snapshot_hash")
        expected_missingness = _missingness(bundle.feature_values)
        supplied_missingness = {str(key): int(value) for key, value in bundle.missingness_summary.items()}
        if supplied_missingness != expected_missingness:
            raise FeatureAssemblyValidationError("MISSINGNESS_MISMATCH", "missingness_summary does not reconcile with typed feature states")
        return {"feature_schema_version": feature_schema_version, "generator_version": generator_version, "role": role, "config_version": config_version, "config_hash": config_hash, "canonical_entity_refs": canonical_entity_refs, "source_objects": source_objects, "adapter_refs": tuple(adapter_refs), "prediction_cutoff_at": _text(raw.get("prediction_cutoff_at"), "prediction_cutoff_at"), "kickoff_at": _text(raw.get("kickoff_at"), "kickoff_at"), "bundle": bundle}

    @staticmethod
    def _build_bundle(request: Mapping[str, Any]) -> FeatureBundle:
        # The typed bundle is the only representation consumed. Assembly only
        # checks and preserves it; it does not derive or fill feature values.
        return request["bundle"]

    @staticmethod
    def _handoff(bundle: FeatureBundle, adapters: Tuple[SchemaAdapter, ...]) -> Dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "feature_bundle_id": bundle.feature_bundle_id,
            "feature_snapshot_hash": bundle.feature_snapshot_hash,
            "feature_schema_version": bundle.feature_schema_version,
            "generator_version": bundle.generator_version,
            "input_hash": bundle.input_hash,
            "provenance_hash": bundle.provenance_hash,
            "missingness_summary": bundle.to_dict()["missingness_summary"],
            "feature_quality": bundle.feature_quality.to_dict(),
            "source_schema_adapters": [{"source_kind": item.source_kind, "source_schema_version": item.source_schema_version, "target_feature_schema_version": item.target_feature_schema_version, "adapter_version": item.adapter_version} for item in adapters],
            "downstream_boundary": "V4-040 handoff; no Prediction/Score Engine/Market Intelligence output",
        }


__all__ = ["CONTRACT_VERSION", "SOURCE_KINDS", "VersionedSourceObject", "SchemaAdapter", "SchemaAdapterRegistry", "FeatureAssemblyResult", "FeatureAssemblyStore", "FeatureAssemblyValidationError"]
