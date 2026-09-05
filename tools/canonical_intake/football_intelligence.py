"""V4-044 typed Football Intelligence pre-Frozen feature generator.

This module consumes accepted V4-038/V4-039 Feature Bundle lineage, V4-041 to
V4-043 statistical references, and typed Team Context/Evidence references. It
does not run a formal Engine Output, create Frozen Input, calculate a market
prediction, or assign an effect coefficient to a context value.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .feature_bundle import FeatureBundle, FeatureBundleValidationError
from .feature_snapshot import FeatureSnapshotHasher, FeatureSnapshotValidationError
from .football_intelligence_governance import (
    CONFIG_VERSION,
    CONTEXT_INTEGRATION_CONTRACT_VERSION,
    FEATURE_CONTRACT_VERSION,
    FEATURE_STATES,
    FootballIntelligenceGovernanceError,
    load_approved_config,
    validate_approved_config,
    validate_pre_freeze_artifact,
)
from .statistical_strength import StatisticalFeature


CONTRACT_VERSION = FEATURE_CONTRACT_VERSION
GENERATOR_VERSION = "v4-044-football-intelligence@1.0.0"
MAPPING_REGISTRY_VERSION = "football-intelligence-mapping@1.0.0"
TEAM_CONTEXT_CONTRACT_VERSION = "team-context@2.0.0"
EVIDENCE_CONTRACT_VERSION = "evidence@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_FEATURE_ARTIFACT"
ARTIFACT_NAMESPACE = uuid.UUID("f7e5c071-4a4e-5d27-a72e-6d8a97c9a315")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
TIME_FIELDS = ("source_timestamp", "observed_at", "effective_at", "expires_at")
FORBIDDEN_TERMS = frozenset(
    {
        "prediction",
        "recommendation",
        "model_confidence",
        "win_probability",
        "betting_confidence",
        "score_selection",
        "engine_output",
        "risk_decision",
        "lambda",
        "frozen_input_id",
        "frozen_input_hash",
    }
)
NON_CONSUMABLE_STATES = frozenset(FEATURE_STATES - {"AVAILABLE"})
CONTEXT_STATES = frozenset(
    {"CONFIRMED", "PROJECTED", "UNKNOWN", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED"}
)
QUALITY_VALUES = {
    "coverage": {"COMPLETE", "PARTIAL", "UNKNOWN"},
    "verification": {"VERIFIED", "PARTIAL", "UNKNOWN"},
    "freshness": {"CURRENT", "STALE", "UNKNOWN"},
    "completeness": {"COMPLETE", "PARTIAL", "UNKNOWN"},
    "conflict": {"NONE", "PRESENT", "UNKNOWN"},
    "provenance": {"RESOLVED", "PARTIAL", "UNKNOWN"},
}


class FootballIntelligenceValidationError(ValueError):
    """Raised when V4-044 cannot safely create a pre-Frozen artifact."""

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
        return {str(key): _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FootballIntelligenceValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise FootballIntelligenceValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FootballIntelligenceValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FootballIntelligenceValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).casefold())


def _find_forbidden(value: Any, path: str = "value") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in {"prediction_cutoff_at", "predictioncutoffat"}:
                found = _find_forbidden(child, f"{path}.{key}")
                if found:
                    return found
                continue
            if normalized in {_normalized_key(item) for item in FORBIDDEN_TERMS}:
                return f"{path}.{key}"
            if any(
                term in normalized
                for term in (
                    "prediction",
                    "recommendation",
                    "modelconfidence",
                    "winprobability",
                    "bettingconfidence",
                    "scoreselection",
                    "engineoutput",
                    "riskdecision",
                    "frozeninput",
                )
            ):
                return f"{path}.{key}"
            found = _find_forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _ref_id(value: Any, field: str) -> str:
    if isinstance(value, str):
        return _text(value, field)
    if not isinstance(value, Mapping):
        raise FootballIntelligenceValidationError("REFERENCE_INVALID", f"{field} must be an ID or object")
    for key in ("id", "ref_id", "object_id", "context_id", "evidence_id", "feature_id", "snapshot_id"):
        if isinstance(value.get(key), str) and value[key].strip():
            return value[key].strip()
    raise FootballIntelligenceValidationError("REFERENCE_ID_MISSING", f"{field} requires an ID")


def _ref_hash(value: Any, field: str) -> str:
    if not isinstance(value, Mapping):
        raise FootballIntelligenceValidationError("REFERENCE_HASH_MISSING", f"{field} requires an exact hash")
    for key in (
        "hash",
        "ref_hash",
        "object_hash",
        "context_hash",
        "evidence_hash",
        "feature_hash",
        "output_hash",
        "provenance_hash",
    ):
        if key in value:
            return _hash(value[key], f"{field}.{key}")
    for key, child in value.items():
        if str(key).endswith("_hash"):
            return _hash(child, f"{field}.{key}")
    raise FootballIntelligenceValidationError("REFERENCE_HASH_MISSING", f"{field} requires an exact hash")


def _normalize_refs(value: Any, field: str, *, allow_empty: bool = False) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise FootballIntelligenceValidationError("REFERENCE_COLLECTION_INVALID", f"{field} must be a list")
    if not value and not allow_empty:
        raise FootballIntelligenceValidationError("REFERENCE_COLLECTION_EMPTY", f"{field} cannot be empty")
    result: List[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise FootballIntelligenceValidationError("REFERENCE_INVALID", f"{field}[{index}] must be an object")
        normalized = dict(item)
        normalized["id"] = _ref_id(item, f"{field}[{index}]")
        normalized["hash"] = _ref_hash(item, f"{field}[{index}]")
        result.append(_freeze(normalized))
    return tuple(result)


def _quality(features: Sequence[Mapping[str, Any]], *, provenance: str = "RESOLVED") -> Dict[str, str]:
    states = {str(item["state"]) for item in features}
    complete = bool(features) and states == {"AVAILABLE"}
    return {
        "coverage": "COMPLETE" if complete else "PARTIAL",
        "verification": "VERIFIED" if complete else "PARTIAL",
        "freshness": "CURRENT" if not states.intersection({"STALE", "FUTURE_DATA"}) else "UNKNOWN",
        "completeness": "COMPLETE" if complete else "PARTIAL",
        "conflict": "PRESENT" if "CONFLICTED" in states else "NONE",
        "provenance": provenance,
    }


def _feature_payload_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "feature_bundle_id": raw["feature_bundle_id"],
            "role": raw["role"],
            "features": raw["features"],
            "feature_quality": raw["feature_quality"],
        }
    )


def _input_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "contract_version": raw["contract_version"],
            "artifact_kind": raw["artifact_kind"],
            "feature_bundle_ref": raw["feature_bundle_ref"],
            "canonical_entity_refs": raw["canonical_entity_refs"],
            "statistical_feature_refs": raw["statistical_feature_refs"],
            "team_context_refs": raw["team_context_refs"],
            "evidence_refs": raw["evidence_refs"],
            "prediction_cutoff_at": raw["prediction_cutoff_at"],
            "kickoff_at": raw["kickoff_at"],
            "role": raw["role"],
            "generator_version": raw["generator_version"],
            "config_version": raw["config_version"],
            "config_hash": raw["config_hash"],
            "mapping_registry_version": raw["mapping_registry_version"],
        }
    )


def _provenance_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "canonical_entity_refs": raw["canonical_entity_refs"],
            "feature_bundle_ref": raw["feature_bundle_ref"],
            "statistical_feature_refs": raw["statistical_feature_refs"],
            "team_context_refs": raw["team_context_refs"],
            "evidence_refs": raw["evidence_refs"],
            "feature_provenance": [
                {
                    "feature_key": item["feature_key"],
                    "source_refs": item["source_refs"],
                    "basis_refs": item["basis_refs"],
                    "source_timestamp": item.get("source_timestamp"),
                    "observed_at": item.get("observed_at"),
                    "effective_at": item.get("effective_at"),
                    "expires_at": item.get("expires_at"),
                }
                for item in raw["features"]
            ],
        }
    )


def _implementation_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class FootballIntelligenceFeature:
    feature_key: str
    category: str
    kind: str
    state: str
    value: Any
    unit: Optional[str]
    context_state: str
    basis_refs: Tuple[str, ...]
    source_refs: Tuple[str, ...]
    derivation_ref: str
    reason_code: Optional[str]
    reason_detail: Optional[str]
    team_id: Optional[str] = None
    side: Optional[str] = None
    raw_value: Any = None
    transformation: Optional[str] = None
    normalization: Optional[str] = None
    clipping: Optional[str] = None
    mapping_registry_version: str = MAPPING_REGISTRY_VERSION
    source_timestamp: Optional[str] = None
    observed_at: Optional[str] = None
    effective_at: Optional[str] = None
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "feature_key": self.feature_key,
            "category": self.category,
            "kind": self.kind,
            "state": self.state,
            "value": self.value,
            "unit": self.unit,
            "context_state": self.context_state,
            "basis_refs": list(self.basis_refs),
            "source_refs": list(self.source_refs),
            "derivation_ref": self.derivation_ref,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "team_id": self.team_id,
            "side": self.side,
            "raw_value": self.raw_value,
            "transformation": self.transformation,
            "normalization": self.normalization,
            "clipping": self.clipping,
            "mapping_registry_version": self.mapping_registry_version,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
        }
        return result


@dataclass(frozen=True)
class FootballIntelligenceArtifact:
    artifact_id: str
    artifact_kind: str
    contract_version: str
    feature_bundle_id: str
    feature_bundle_ref: Mapping[str, Any]
    statistical_feature_refs: Tuple[Mapping[str, Any], ...]
    team_context_refs: Tuple[Mapping[str, Any], ...]
    evidence_refs: Tuple[Mapping[str, Any], ...]
    canonical_entity_refs: Mapping[str, Any]
    role: str
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    mapping_registry_version: str
    prediction_cutoff_at: str
    kickoff_at: str
    features: Tuple[Mapping[str, Any], ...]
    feature_quality: Mapping[str, str]
    input_hash: str
    payload_hash: str
    provenance_hash: str
    revision: int
    supersedes_artifact_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "feature_bundle_id": self.feature_bundle_id,
            "feature_bundle_ref": _thaw(self.feature_bundle_ref),
            "statistical_feature_refs": [_thaw(item) for item in self.statistical_feature_refs],
            "team_context_refs": [_thaw(item) for item in self.team_context_refs],
            "evidence_refs": [_thaw(item) for item in self.evidence_refs],
            "canonical_entity_refs": _thaw(self.canonical_entity_refs),
            "role": self.role,
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "mapping_registry_version": self.mapping_registry_version,
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "features": [_thaw(item) for item in self.features],
            "feature_quality": _thaw(self.feature_quality),
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "revision": self.revision,
            "supersedes_artifact_id": self.supersedes_artifact_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config: Mapping[str, Any]) -> "FootballIntelligenceArtifact":
        if not isinstance(raw, Mapping):
            raise FootballIntelligenceValidationError("ARTIFACT_INVALID", "artifact must be an object")
        try:
            validate_pre_freeze_artifact(raw, config=config)
        except FootballIntelligenceGovernanceError as exc:
            raise FootballIntelligenceValidationError(exc.code, str(exc)) from exc
        if raw.get("generator_version") != GENERATOR_VERSION:
            raise FootballIntelligenceValidationError("GENERATOR_VERSION_INVALID", f"expected {GENERATOR_VERSION}")
        if raw.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
            raise FootballIntelligenceValidationError("MAPPING_VERSION_INVALID", f"expected {MAPPING_REGISTRY_VERSION}")
        if raw.get("config_hash") != sha256_json(config):
            raise FootballIntelligenceValidationError("CONFIG_HASH_MISMATCH", "config_hash does not identify the approved config")
        cutoff = _timestamp(raw["prediction_cutoff_at"], "prediction_cutoff_at")
        kickoff = _timestamp(raw["kickoff_at"], "kickoff_at")
        if not cutoff < kickoff:
            raise FootballIntelligenceValidationError("CUTOFF_INVALID", "prediction cutoff must precede kickoff")
        input_hash = _input_hash(raw)
        if raw.get("input_hash") != input_hash:
            raise FootballIntelligenceValidationError("INPUT_HASH_MISMATCH", "input_hash is not recomputable")
        payload_hash = _feature_payload_hash(raw)
        if raw.get("payload_hash") != payload_hash:
            raise FootballIntelligenceValidationError("PAYLOAD_HASH_MISMATCH", "payload_hash is not recomputable")
        provenance_hash = _provenance_hash(raw)
        if raw.get("provenance_hash") != provenance_hash:
            raise FootballIntelligenceValidationError("PROVENANCE_HASH_MISMATCH", "provenance_hash is not recomputable")
        expected_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"artifact|{input_hash}|{payload_hash}|{raw.get('revision', 1)}"))
        if raw.get("artifact_id") != expected_id:
            raise FootballIntelligenceValidationError("ARTIFACT_ID_MISMATCH", "artifact_id is not deterministic for this logical artifact")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise FootballIntelligenceValidationError("REVISION_INVALID", "revision must be a positive integer")
        supersedes = raw.get("supersedes_artifact_id")
        if revision == 1 and supersedes is not None:
            raise FootballIntelligenceValidationError("ROOT_SUPERSEDES_INVALID", "revision 1 cannot supersede an artifact")
        return cls(
            artifact_id=_text(raw.get("artifact_id"), "artifact_id"),
            artifact_kind=ARTIFACT_KIND,
            contract_version=CONTRACT_VERSION,
            feature_bundle_id=_text(raw.get("feature_bundle_id"), "feature_bundle_id"),
            feature_bundle_ref=_freeze(dict(raw["feature_bundle_ref"])),
            statistical_feature_refs=_normalize_refs(raw["statistical_feature_refs"], "statistical_feature_refs", allow_empty=True),
            team_context_refs=_normalize_refs(raw["team_context_refs"], "team_context_refs"),
            evidence_refs=_normalize_refs(raw["evidence_refs"], "evidence_refs"),
            canonical_entity_refs=_freeze(dict(raw["canonical_entity_refs"])),
            role=_text(raw.get("role"), "role"),
            generator_version=GENERATOR_VERSION,
            implementation_hash=_hash(raw.get("implementation_hash"), "implementation_hash"),
            config_version=CONFIG_VERSION,
            config_hash=_hash(raw.get("config_hash"), "config_hash"),
            mapping_registry_version=MAPPING_REGISTRY_VERSION,
            prediction_cutoff_at=_iso(cutoff),
            kickoff_at=_iso(kickoff),
            features=tuple(_freeze(dict(item)) for item in raw["features"]),
            feature_quality=_freeze(dict(raw["feature_quality"])),
            input_hash=input_hash,
            payload_hash=payload_hash,
            provenance_hash=provenance_hash,
            revision=revision,
            supersedes_artifact_id=_text(supersedes, "supersedes_artifact_id") if supersedes is not None else None,
        )


class FootballIntelligenceEngine:
    """V4-044 generator for typed pre-Frozen Football Intelligence features."""

    def __init__(self, config: Mapping[str, Any]):
        validate_approved_config(config)
        self.config = config
        self.config_hash = sha256_json(config)
        self.implementation_hash = _implementation_hash()
        self._numeric = {item["feature_key"]: item for item in config["numeric_mappings"]}
        self._categorical = {item["feature_key"]: item for item in config["categorical_mappings"]}

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "FootballIntelligenceEngine":
        root = Path(repo_root).resolve()
        if root.drive.upper() != "F:":
            raise FootballIntelligenceValidationError("F_DRIVE_REQUIRED", "V4-044 runtime must use the F: drive")
        return cls(load_approved_config(root))

    @staticmethod
    def _bundle(raw: Union[FeatureBundle, Mapping[str, Any]]) -> FeatureBundle:
        if isinstance(raw, FeatureBundle):
            bundle = raw
        elif isinstance(raw, Mapping):
            try:
                bundle = FeatureBundle.from_dict(raw)
            except FeatureBundleValidationError as exc:
                raise FootballIntelligenceValidationError(exc.code, str(exc)) from exc
        else:
            raise FootballIntelligenceValidationError("FEATURE_BUNDLE_REQUIRED", "accepted Feature Bundle is required")
        if bundle.contract_version != "feature-bundle@2.0.0":
            raise FootballIntelligenceValidationError("FEATURE_BUNDLE_VERSION_INVALID", "V4-044 requires feature-bundle@2.0.0")
        if not bundle.feature_snapshot_hash:
            raise FootballIntelligenceValidationError("FEATURE_SNAPSHOT_REQUIRED", "V4-044 requires an accepted feature_snapshot_hash")
        try:
            FeatureSnapshotHasher.verify(bundle, bundle.feature_snapshot_hash)
        except FeatureSnapshotValidationError as exc:
            raise FootballIntelligenceValidationError(exc.code, str(exc)) from exc
        return bundle

    @staticmethod
    def _statistical_refs(features: Sequence[Union[StatisticalFeature, Mapping[str, Any]]], target_match_id: str) -> Tuple[Mapping[str, Any], ...]:
        if not isinstance(features, (list, tuple)) or not features:
            raise FootballIntelligenceValidationError("STATISTICAL_FEATURES_REQUIRED", "V4-041 to V4-043 references are required")
        rows: List[Mapping[str, Any]] = []
        generators: set[str] = set()
        for index, item in enumerate(features):
            raw = item.to_dict() if isinstance(item, StatisticalFeature) else dict(item)
            forbidden = _find_forbidden(raw, f"statistical_features[{index}]")
            if forbidden:
                raise FootballIntelligenceValidationError("MODEL_FIELD_FORBIDDEN", f"statistical reference contains {forbidden}")
            if raw.get("target_match_id") != target_match_id:
                raise FootballIntelligenceValidationError("STATISTICAL_MATCH_MISMATCH", "statistical feature is not bound to the Feature Bundle match")
            feature_id = _text(raw.get("feature_id"), f"statistical_features[{index}].feature_id")
            output_hash = _hash(raw.get("output_hash"), f"statistical_features[{index}].output_hash")
            _hash(raw.get("input_hash"), f"statistical_features[{index}].input_hash")
            _hash(raw.get("config_hash"), f"statistical_features[{index}].config_hash")
            generator = _text(raw.get("generator_version"), f"statistical_features[{index}].generator_version")
            generators.add(generator.split("-", 2)[1] if generator.startswith("v4-") else generator)
            rows.append(_freeze({"id": feature_id, "hash": output_hash, "generator_version": generator, "feature_type": raw.get("feature_type"), "state": raw.get("state")}))
        required_markers = {"041", "042", "043"}
        if not required_markers.issubset(generators):
            raise FootballIntelligenceValidationError("STATISTICAL_LINEAGE_INCOMPLETE", "V4-041, V4-042, and V4-043 references are all required")
        return tuple(rows)

    @staticmethod
    def _known_ids(*groups: Sequence[Mapping[str, Any]]) -> set[str]:
        return {str(item["id"]) for group in groups for item in group}

    def _observation_feature(
        self,
        raw: Mapping[str, Any],
        *,
        cutoff: datetime,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
        known_ids: set[str],
    ) -> Dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise FootballIntelligenceValidationError("CONTEXT_OBSERVATION_INVALID", "context observation must be an object")
        forbidden = _find_forbidden(raw, "context_observation")
        if forbidden:
            raise FootballIntelligenceValidationError("MODEL_FIELD_FORBIDDEN", f"context observation contains {forbidden}")
        key = _text(raw.get("feature_key"), "context_observation.feature_key")
        mapping = self._numeric.get(key) or self._categorical.get(key)
        if mapping is None:
            raise FootballIntelligenceValidationError("MAPPING_NOT_APPROVED", f"no approved mapping exists for {key}")
        expected_kind = "NUMERIC" if key in self._numeric else "CATEGORICAL"
        kind = _text(raw.get("kind", expected_kind), f"{key}.kind")
        if kind != expected_kind:
            raise FootballIntelligenceValidationError("FEATURE_KIND_MISMATCH", f"{key} must remain {expected_kind}")
        category = _text(raw.get("category", mapping["category"]), f"{key}.category")
        if category != mapping["category"]:
            raise FootballIntelligenceValidationError("FEATURE_CATEGORY_MISMATCH", f"{key} category is not approved")
        state = _text(raw.get("state"), f"{key}.state").upper()
        if state not in FEATURE_STATES:
            raise FootballIntelligenceValidationError("FEATURE_STATE_INVALID", f"{key}.state is not governed")
        context_state = _text(raw.get("context_state", "CONFIRMED"), f"{key}.context_state").upper()
        if context_state not in CONTEXT_STATES:
            raise FootballIntelligenceValidationError("CONTEXT_STATE_INVALID", f"{key}.context_state is not governed")
        if context_state == "PROJECTED" and kind != "CATEGORICAL":
            raise FootballIntelligenceValidationError("PROJECTED_NUMERIC_FORBIDDEN", f"{key} projected context cannot be numeric")
        team_id = raw.get("team_id")
        if team_id is not None:
            team_id = _text(team_id, f"{key}.team_id")
            if team_id not in {home_team_id, away_team_id}:
                raise FootballIntelligenceValidationError("TEAM_IDENTITY_MISMATCH", f"{key}.team_id is not in the canonical match")
        observation_match_id = _text(raw.get("match_id"), f"{key}.match_id")
        if observation_match_id != match_id:
            raise FootballIntelligenceValidationError("MATCH_IDENTITY_MISMATCH", f"{key}.match_id is not the canonical match")
        side = raw.get("side")
        if side is not None:
            side = _text(side, f"{key}.side").upper()
            if side not in {"HOME", "AWAY"}:
                raise FootballIntelligenceValidationError("SIDE_INVALID", f"{key}.side must be HOME or AWAY")
            if team_id is not None and ((side == "HOME" and team_id != home_team_id) or (side == "AWAY" and team_id != away_team_id)):
                raise FootballIntelligenceValidationError("SIDE_TEAM_MISMATCH", f"{key}.side does not match the canonical team identity")
        source_values = raw.get("source_refs", raw.get("source_ref"))
        if isinstance(source_values, (str, Mapping)):
            source_values = [source_values]
        if not isinstance(source_values, (list, tuple)) or not source_values:
            raise FootballIntelligenceValidationError("SOURCE_REFERENCE_REQUIRED", f"{key} requires source_refs")
        source_refs = tuple(_ref_id(item, f"{key}.source_refs") for item in source_values)
        if any(item not in known_ids for item in source_refs):
            raise FootballIntelligenceValidationError("SOURCE_REFERENCE_UNRESOLVED", f"{key} source ref is not declared in the artifact envelope")
        basis_values = raw.get("basis_refs")
        if not isinstance(basis_values, (list, tuple)) or not basis_values:
            raise FootballIntelligenceValidationError("BASIS_REFERENCE_REQUIRED", f"{key} requires basis_refs")
        basis_refs = tuple(_ref_id(item, f"{key}.basis_refs") for item in basis_values)
        if any(item not in known_ids for item in basis_refs):
            raise FootballIntelligenceValidationError("BASIS_REFERENCE_UNRESOLVED", f"{key} basis ref is not declared in the artifact envelope")
        times: Dict[str, Optional[str]] = {}
        parsed_times: Dict[str, datetime] = {}
        for field in TIME_FIELDS:
            if raw.get(field) is not None:
                parsed = _timestamp(raw[field], f"{key}.{field}")
                times[field] = _iso(parsed)
                parsed_times[field] = parsed
            else:
                times[field] = None
        for earlier, later in (("source_timestamp", "observed_at"), ("observed_at", "effective_at")):
            if earlier in parsed_times and later in parsed_times and parsed_times[earlier] > parsed_times[later]:
                raise FootballIntelligenceValidationError("TIME_ORDER_INVALID", f"{key}.{earlier} cannot follow {later}")
        effective = parsed_times.get("effective_at") or parsed_times.get("source_timestamp") or parsed_times.get("observed_at")
        if effective is None:
            raise FootballIntelligenceValidationError("SOURCE_TIME_REQUIRED", f"{key} requires source_timestamp, observed_at, or effective_at")
        if effective > cutoff and state == "AVAILABLE":
            state = "FUTURE_DATA"
            context_state = "FUTURE_DATA"
            reason_code = "POST_CUTOFF_INPUT"
            reason_detail = "accepted context observation is after prediction_cutoff_at"
        elif parsed_times.get("expires_at") is not None and parsed_times["expires_at"] < cutoff and state == "AVAILABLE":
            state = "STALE"
            context_state = "STALE"
            reason_code = "SOURCE_EXPIRED"
            reason_detail = "accepted context observation expired before prediction cutoff"
        else:
            reason_code = raw.get("reason_code")
            reason_detail = raw.get("reason_detail")
        value = raw.get("value", raw.get("raw_value"))
        raw_value = raw.get("raw_value", value)
        unit = raw.get("unit", mapping.get("unit", "category"))
        if state == "AVAILABLE":
            if kind == "NUMERIC":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise FootballIntelligenceValidationError("NUMERIC_VALUE_INVALID", f"{key}.value must be a finite number")
                if unit != mapping["unit"]:
                    raise FootballIntelligenceValidationError("UNIT_INVALID", f"{key}.unit must be {mapping['unit']}")
            else:
                if not isinstance(value, str) or not value.strip():
                    raise FootballIntelligenceValidationError("CATEGORICAL_VALUE_INVALID", f"{key}.value must be a non-empty string")
                if unit != "category":
                    raise FootballIntelligenceValidationError("UNIT_INVALID", f"{key}.unit must be category")
            if context_state == "PROJECTED" and value in {"CONFIRMED_LINEUP", "CONFIRMED"}:
                raise FootballIntelligenceValidationError("CONFIRMED_PROJECTED_CONFLICT", f"{key} cannot be confirmed and projected")
        else:
            if not isinstance(reason_code, str) or not REASON_RE.fullmatch(reason_code):
                raise FootballIntelligenceValidationError("REASON_CODE_REQUIRED", f"{key}.{state} requires reason_code")
            if not isinstance(reason_detail, str) or not reason_detail.strip():
                raise FootballIntelligenceValidationError("REASON_DETAIL_REQUIRED", f"{key}.{state} requires reason_detail")
            # A value that was present on an AVAILABLE observation is not
            # carried forward after a cutoff/expiry downgrade.  The output
            # remains an explicit non-consumable state, never a replacement
            # numeric value.
            if state in {"STALE", "FUTURE_DATA"} and raw.get("state") == "AVAILABLE":
                value = None
                raw_value = None
            elif value not in (None, "", [], {}):
                raise FootballIntelligenceValidationError("NON_CONSUMABLE_VALUE_PRESENT", f"{key}.{state} cannot carry a replacement value")
            else:
                value = None
                raw_value = None
            unit = mapping.get("unit", "category") if kind == "NUMERIC" else "category"
        derivation_ref = _text(raw.get("derivation_ref", f"{MAPPING_REGISTRY_VERSION}/{key}"), f"{key}.derivation_ref")
        if not derivation_ref.startswith(f"{MAPPING_REGISTRY_VERSION}/"):
            raise FootballIntelligenceValidationError("DERIVATION_MAPPING_INVALID", f"{key} must use the approved mapping registry")
        result = {
            "feature_key": key,
            "category": category,
            "kind": kind,
            "state": state,
            "value": value,
            "unit": unit,
            "context_state": context_state,
            "basis_refs": list(basis_refs),
            "source_refs": list(source_refs),
            "derivation_ref": derivation_ref,
            "reason_code": reason_code if state != "AVAILABLE" else None,
            "reason_detail": reason_detail if state != "AVAILABLE" else None,
            "team_id": team_id,
            "side": side,
            "raw_value": raw_value,
            "transformation": mapping.get("transformation") if kind == "NUMERIC" else "categorical_state_preserved",
            "normalization": mapping.get("normalization", "NATIVE_STATE") if kind == "NUMERIC" else "SOURCE_VOCABULARY",
            "clipping": mapping.get("clipping", "NONE") if kind == "NUMERIC" else "NONE",
            "mapping_registry_version": MAPPING_REGISTRY_VERSION,
            **times,
        }
        if kind == "CATEGORICAL" and mapping.get("numeric_effect") not in {None, "FORBIDDEN"}:
            raise FootballIntelligenceValidationError("CATEGORICAL_EFFECT_POLICY_INVALID", f"{key} has an unapproved numeric effect")
        return result

    def generate(
        self,
        *,
        feature_bundle: Union[FeatureBundle, Mapping[str, Any]],
        statistical_features: Sequence[Union[StatisticalFeature, Mapping[str, Any]]],
        context_observations: Sequence[Mapping[str, Any]],
        team_context_refs: Optional[Sequence[Mapping[str, Any]]] = None,
        evidence_refs: Optional[Sequence[Mapping[str, Any]]] = None,
        revision: int = 1,
        supersedes_artifact_id: Optional[str] = None,
    ) -> FootballIntelligenceArtifact:
        bundle = self._bundle(feature_bundle)
        entity = dict(bundle.canonical_entity_refs)
        match_id = _text(entity.get("match_id"), "canonical_entity_refs.match_id")
        home_id = _text(entity.get("home_team_id"), "canonical_entity_refs.home_team_id")
        away_id = _text(entity.get("away_team_id"), "canonical_entity_refs.away_team_id")
        if home_id == away_id:
            raise FootballIntelligenceValidationError("CANONICAL_SIDE_CONFLICT", "home and away team IDs must differ")
        cutoff = _timestamp(bundle.prediction_cutoff_at, "prediction_cutoff_at")
        kickoff = _timestamp(bundle.kickoff_at, "kickoff_at")
        if not cutoff < kickoff:
            raise FootballIntelligenceValidationError("CUTOFF_INVALID", "prediction cutoff must precede kickoff")
        stats = self._statistical_refs(statistical_features, match_id)
        context_refs = _normalize_refs(
            team_context_refs if team_context_refs is not None else [_thaw(item) for item in bundle.team_context_refs],
            "team_context_refs",
        )
        evidence = _normalize_refs(
            evidence_refs if evidence_refs is not None else [_thaw(item) for item in bundle.evidence_graph_refs],
            "evidence_refs",
        )
        bundle_ref = {"id": bundle.feature_bundle_id, "feature_snapshot_hash": _hash(bundle.feature_snapshot_hash, "feature_bundle_ref.feature_snapshot_hash")}
        bundle_ref["hash"] = bundle_ref["feature_snapshot_hash"]
        known_ids = self._known_ids(stats, context_refs, evidence, (bundle_ref,))
        features = tuple(
            self._observation_feature(
                observation,
                cutoff=cutoff,
                match_id=match_id,
                home_team_id=home_id,
                away_team_id=away_id,
                known_ids=known_ids,
            )
            for observation in context_observations
        )
        if not features:
            raise FootballIntelligenceValidationError("FEATURES_REQUIRED", "V4-044 requires at least one typed context/statistical feature")
        ordered_features = tuple(sorted(features, key=lambda item: (item["feature_key"], item.get("team_id") or "", item.get("side") or "", tuple(item["source_refs"]))))
        raw: Dict[str, Any] = {
            "artifact_id": "pending",
            "artifact_kind": ARTIFACT_KIND,
            "contract_version": CONTRACT_VERSION,
            "feature_bundle_id": bundle.feature_bundle_id,
            "feature_bundle_ref": bundle_ref,
            "statistical_feature_refs": [_thaw(item) for item in stats],
            "team_context_refs": [_thaw(item) for item in context_refs],
            "evidence_refs": [_thaw(item) for item in evidence],
            "canonical_entity_refs": entity,
            "role": bundle.role,
            "generator_version": GENERATOR_VERSION,
            "implementation_hash": self.implementation_hash,
            "config_version": CONFIG_VERSION,
            "config_hash": self.config_hash,
            "mapping_registry_version": MAPPING_REGISTRY_VERSION,
            "prediction_cutoff_at": _iso(cutoff),
            "kickoff_at": _iso(kickoff),
            "features": list(ordered_features),
            "feature_quality": _quality(ordered_features),
            "input_hash": "pending",
            "payload_hash": "pending",
            "provenance_hash": "pending",
            "revision": revision,
            "supersedes_artifact_id": supersedes_artifact_id,
        }
        raw["input_hash"] = _input_hash(raw)
        raw["payload_hash"] = _feature_payload_hash(raw)
        raw["provenance_hash"] = _provenance_hash(raw)
        raw["artifact_id"] = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"artifact|{raw['input_hash']}|{raw['payload_hash']}|{revision}"))
        return FootballIntelligenceArtifact.from_dict(raw, config=self.config)


class FootballIntelligenceStore:
    """Append-only local store for V4-044 pre-Frozen artifacts."""

    def __init__(self, config: Mapping[str, Any]):
        self._config = config
        self._artifacts: Dict[str, FootballIntelligenceArtifact] = {}
        self._latest_by_family: Dict[Tuple[str, str], FootballIntelligenceArtifact] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def artifacts(self) -> Tuple[FootballIntelligenceArtifact, ...]:
        return tuple(self._artifacts.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def append(self, artifact: Union[FootballIntelligenceArtifact, Mapping[str, Any]]) -> str:
        item = artifact if isinstance(artifact, FootballIntelligenceArtifact) else FootballIntelligenceArtifact.from_dict(artifact, config=self._config)
        existing = self._artifacts.get(item.artifact_id)
        if existing is not None:
            if existing.payload_hash == item.payload_hash:
                self._events.append(_freeze({"action": "DUPLICATE_NOOP", "artifact_id": item.artifact_id}))
                return "DUPLICATE_NOOP"
            raise FootballIntelligenceValidationError("ARTIFACT_ID_REUSE", "artifact identity cannot be reused with different content")
        family = (item.feature_bundle_id, item.generator_version)
        previous = self._latest_by_family.get(family)
        if previous is None:
            if item.revision != 1 or item.supersedes_artifact_id is not None:
                raise FootballIntelligenceValidationError("REVISION_ROOT_INVALID", "first artifact revision must be 1 without supersedes")
        else:
            if item.revision != previous.revision + 1 or item.supersedes_artifact_id != previous.artifact_id:
                raise FootballIntelligenceValidationError("SUPERSEDES_REQUIRED", "correction must append a higher revision that supersedes the prior artifact")
        self._artifacts[item.artifact_id] = item
        self._latest_by_family[family] = item
        self._events.append(_freeze({"action": "APPEND", "artifact_id": item.artifact_id, "revision": item.revision}))
        return "APPEND"


__all__ = [
    "ARTIFACT_KIND",
    "CONTRACT_VERSION",
    "GENERATOR_VERSION",
    "MAPPING_REGISTRY_VERSION",
    "TEAM_CONTEXT_CONTRACT_VERSION",
    "FootballIntelligenceArtifact",
    "FootballIntelligenceEngine",
    "FootballIntelligenceFeature",
    "FootballIntelligenceStore",
    "FootballIntelligenceValidationError",
]
