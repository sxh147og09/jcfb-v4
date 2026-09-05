"""V4-045 typed Football Context pre-Frozen integration boundary.

The integration consumes an accepted V4-044 artifact and optional additional
typed Team Context observations. It preserves BATCH-11 and Evidence lineage,
does not resolve conflicts, and never produces a formal Engine Output,
Prediction, Score Engine result, or Frozen Input.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .football_intelligence import (
    ARTIFACT_KIND,
    CONTRACT_VERSION as FEATURE_CONTRACT_VERSION,
    FootballIntelligenceArtifact,
    FootballIntelligenceEngine,
    FootballIntelligenceValidationError,
)
from .football_intelligence_governance import (
    CONTEXT_INTEGRATION_CONTRACT_VERSION,
    CONFIG_VERSION,
    load_approved_config,
)


CONTRACT_VERSION = CONTEXT_INTEGRATION_CONTRACT_VERSION
GENERATOR_VERSION = "v4-045-context-integration@1.0.0"
MAPPING_REGISTRY_VERSION = "football-intelligence-mapping@1.0.0"
ARTIFACT_NAMESPACE = uuid.UUID("b10ac418-7e9b-5b7f-ae11-4e70718b6c52")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
STATES = frozenset({"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED"})
FORBIDDEN_KEYS = frozenset({
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
})


class ContextFeatureIntegrationValidationError(ValueError):
    """Raised when V4-045 cannot safely integrate context features."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextFeatureIntegrationValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise ContextFeatureIntegrationValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _freeze(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


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
            if normalized in {_normalized_key(item) for item in FORBIDDEN_KEYS} or any(term in normalized for term in ("prediction", "recommendation", "modelconfidence", "winprobability", "bettingconfidence", "scoreselection", "engineoutput", "riskdecision", "frozeninput")):
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


def _find_bare_confidence(value: Any, path: str = "value") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalized_key(key) == "confidence":
                return f"{path}.{key}"
            found = _find_bare_confidence(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_bare_confidence(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _ref_id(raw: Any, field: str) -> str:
    if isinstance(raw, str):
        return _text(raw, field)
    if not isinstance(raw, Mapping):
        raise ContextFeatureIntegrationValidationError("REFERENCE_INVALID", f"{field} must be an ID or object")
    for key in ("id", "ref_id", "object_id", "context_id", "evidence_id", "feature_id"):
        if isinstance(raw.get(key), str) and raw[key].strip():
            return raw[key].strip()
    raise ContextFeatureIntegrationValidationError("REFERENCE_ID_MISSING", f"{field} requires an ID")


def _ref_hash(raw: Any, field: str) -> str:
    if not isinstance(raw, Mapping):
        raise ContextFeatureIntegrationValidationError("REFERENCE_HASH_MISSING", f"{field} requires an exact hash")
    for key in ("hash", "ref_hash", "object_hash", "context_hash", "evidence_hash", "feature_hash", "output_hash", "provenance_hash"):
        if key in raw:
            return _hash(raw[key], f"{field}.{key}")
    raise ContextFeatureIntegrationValidationError("REFERENCE_HASH_MISSING", f"{field} requires an exact hash")


def _refs(value: Any, field: str) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContextFeatureIntegrationValidationError("REFERENCE_COLLECTION_INVALID", f"{field} must be a non-empty list")
    result = []
    for index, item in enumerate(value):
        result.append(_freeze({**dict(item), "id": _ref_id(item, f"{field}[{index}]"), "hash": _ref_hash(item, f"{field}[{index}]")}))
    return tuple(result)


def _quality(features: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    states = {str(item["state"]) for item in features}
    complete = bool(features) and states == {"AVAILABLE"}
    return {
        "coverage": "COMPLETE" if complete else "PARTIAL",
        "verification": "VERIFIED" if complete else "PARTIAL",
        "freshness": "UNKNOWN" if states.intersection({"STALE", "FUTURE_DATA"}) else ("CURRENT" if complete else "UNKNOWN"),
        "completeness": "COMPLETE" if complete else "PARTIAL",
        "conflict": "PRESENT" if "CONFLICTED" in states else "NONE",
        "provenance": "RESOLVED" if features else "UNKNOWN",
    }


def _input_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json({
        "contract_version": raw["contract_version"],
        "football_intelligence_artifact_ref": raw["football_intelligence_artifact_ref"],
        "feature_bundle_ref": raw["feature_bundle_ref"],
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "team_context_refs": raw["team_context_refs"],
        "statistical_feature_refs": raw["statistical_feature_refs"],
        "evidence_refs": raw["evidence_refs"],
        "prediction_cutoff_at": raw["prediction_cutoff_at"],
        "kickoff_at": raw["kickoff_at"],
        "config_version": raw["config_version"],
        "config_hash": raw["config_hash"],
        "mapping_registry_version": raw["mapping_registry_version"],
        "generator_version": raw["generator_version"],
    })


def _output_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json({
        "football_intelligence_artifact_ref": raw["football_intelligence_artifact_ref"],
        "feature_bundle_ref": raw["feature_bundle_ref"],
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "features": raw["features"],
        "feature_quality": raw["feature_quality"],
    })


def _provenance_hash(raw: Mapping[str, Any]) -> str:
    return sha256_json({
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "football_intelligence_artifact_ref": raw["football_intelligence_artifact_ref"],
        "feature_bundle_ref": raw["feature_bundle_ref"],
        "team_context_refs": raw["team_context_refs"],
        "statistical_feature_refs": raw["statistical_feature_refs"],
        "evidence_refs": raw["evidence_refs"],
        "feature_source_basis": [{"feature_key": item["feature_key"], "source_refs": item["source_refs"], "basis_refs": item["basis_refs"], "state": item["state"]} for item in raw["features"]],
    })


@dataclass(frozen=True)
class ContextFeatureIntegrationArtifact:
    integration_id: str
    contract_version: str
    football_intelligence_artifact_ref: Mapping[str, Any]
    feature_bundle_ref: Mapping[str, Any]
    canonical_entity_refs: Mapping[str, Any]
    team_context_refs: Tuple[Mapping[str, Any], ...]
    statistical_feature_refs: Tuple[Mapping[str, Any], ...]
    evidence_refs: Tuple[Mapping[str, Any], ...]
    prediction_cutoff_at: str
    kickoff_at: str
    config_version: str
    config_hash: str
    mapping_registry_version: str
    generator_version: str
    features: Tuple[Mapping[str, Any], ...]
    feature_quality: Mapping[str, str]
    input_hash: str
    output_hash: str
    provenance_hash: str
    revision: int
    supersedes_integration_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_id": self.integration_id,
            "contract_version": self.contract_version,
            "football_intelligence_artifact_ref": _thaw(self.football_intelligence_artifact_ref),
            "feature_bundle_ref": _thaw(self.feature_bundle_ref),
            "canonical_entity_refs": _thaw(self.canonical_entity_refs),
            "team_context_refs": [_thaw(item) for item in self.team_context_refs],
            "statistical_feature_refs": [_thaw(item) for item in self.statistical_feature_refs],
            "evidence_refs": [_thaw(item) for item in self.evidence_refs],
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "mapping_registry_version": self.mapping_registry_version,
            "generator_version": self.generator_version,
            "features": [_thaw(item) for item in self.features],
            "feature_quality": _thaw(self.feature_quality),
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "provenance_hash": self.provenance_hash,
            "revision": self.revision,
            "supersedes_integration_id": self.supersedes_integration_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config: Mapping[str, Any]) -> "ContextFeatureIntegrationArtifact":
        if not isinstance(raw, Mapping):
            raise ContextFeatureIntegrationValidationError("ARTIFACT_INVALID", "integration artifact must be an object")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise ContextFeatureIntegrationValidationError("MODEL_FIELD_FORBIDDEN", f"integration artifact contains {forbidden}")
        if raw.get("contract_version") != CONTRACT_VERSION:
            raise ContextFeatureIntegrationValidationError("CONTRACT_VERSION_INVALID", f"expected {CONTRACT_VERSION}")
        if "frozen_input_id" in raw or "frozen_input_hash" in raw:
            raise ContextFeatureIntegrationValidationError("FROZEN_INPUT_FORBIDDEN", "V4-045 cannot reference Frozen Input")
        for field in ("integration_id", "prediction_cutoff_at", "kickoff_at", "config_version", "config_hash", "mapping_registry_version", "generator_version", "input_hash", "output_hash", "provenance_hash"):
            _text(raw.get(field), field)
        if raw["config_version"] != CONFIG_VERSION or raw["config_hash"] != sha256_json(config):
            raise ContextFeatureIntegrationValidationError("CONFIG_HASH_MISMATCH", "integration does not identify the approved config")
        if raw["mapping_registry_version"] != MAPPING_REGISTRY_VERSION or raw["generator_version"] != GENERATOR_VERSION:
            raise ContextFeatureIntegrationValidationError("VERSION_INVALID", "integration config/generator identity is not approved")
        feature_ref = raw.get("football_intelligence_artifact_ref")
        if not isinstance(feature_ref, Mapping):
            raise ContextFeatureIntegrationValidationError("V4044_REFERENCE_REQUIRED", "V4-044 artifact reference is required")
        _text(feature_ref.get("id"), "football_intelligence_artifact_ref.id")
        _hash(feature_ref.get("hash"), "football_intelligence_artifact_ref.hash")
        bundle_ref = raw.get("feature_bundle_ref")
        if not isinstance(bundle_ref, Mapping):
            raise ContextFeatureIntegrationValidationError("FEATURE_BUNDLE_REFERENCE_REQUIRED", "feature_bundle_ref is required")
        _text(bundle_ref.get("id"), "feature_bundle_ref.id")
        _hash(bundle_ref.get("feature_snapshot_hash"), "feature_bundle_ref.feature_snapshot_hash")
        entity = raw.get("canonical_entity_refs")
        if not isinstance(entity, Mapping) or not _text(entity.get("match_id"), "canonical_entity_refs.match_id") or not _text(entity.get("home_team_id"), "canonical_entity_refs.home_team_id") or not _text(entity.get("away_team_id"), "canonical_entity_refs.away_team_id"):
            raise ContextFeatureIntegrationValidationError("CANONICAL_ENTITY_INVALID", "canonical match/team identity is required")
        teams = _refs(raw.get("team_context_refs"), "team_context_refs")
        stats = _refs(raw.get("statistical_feature_refs"), "statistical_feature_refs")
        evidence = _refs(raw.get("evidence_refs"), "evidence_refs")
        features = raw.get("features")
        if not isinstance(features, list) or not features:
            raise ContextFeatureIntegrationValidationError("FEATURES_REQUIRED", "features must be a non-empty list")
        for index, feature in enumerate(features):
            if not isinstance(feature, Mapping):
                raise ContextFeatureIntegrationValidationError("FEATURE_INVALID", f"features[{index}] must be an object")
            state = _text(feature.get("state"), f"features[{index}].state").upper()
            if state not in STATES:
                raise ContextFeatureIntegrationValidationError("FEATURE_STATE_INVALID", f"features[{index}].state is not governed")
            if not isinstance(feature.get("basis_refs"), list) or not feature["basis_refs"] or not isinstance(feature.get("source_refs"), list) or not feature["source_refs"]:
                raise ContextFeatureIntegrationValidationError("FEATURE_PROVENANCE_REQUIRED", f"features[{index}] requires source and basis refs")
            if state == "AVAILABLE" and feature.get("value") in (None, "", [], {}):
                raise ContextFeatureIntegrationValidationError("AVAILABLE_VALUE_EMPTY", f"features[{index}] AVAILABLE value is empty")
            if state != "AVAILABLE":
                if not isinstance(feature.get("reason_code"), str) or not REASON_RE.fullmatch(feature["reason_code"]):
                    raise ContextFeatureIntegrationValidationError("REASON_CODE_REQUIRED", f"features[{index}] requires reason_code")
                if not isinstance(feature.get("reason_detail"), str) or not feature["reason_detail"].strip():
                    raise ContextFeatureIntegrationValidationError("REASON_DETAIL_REQUIRED", f"features[{index}] requires reason_detail")
                if feature.get("value") not in (None, "", [], {}):
                    raise ContextFeatureIntegrationValidationError("NON_CONSUMABLE_VALUE_PRESENT", f"features[{index}] cannot carry a replacement value")
        quality = raw.get("feature_quality")
        if not isinstance(quality, Mapping) or any(not isinstance(quality.get(field), str) or not quality[field].strip() for field in ("coverage", "verification", "freshness", "completeness", "conflict", "provenance")):
            raise ContextFeatureIntegrationValidationError("FEATURE_QUALITY_INVALID", "feature_quality must contain typed quality dimensions")
        if any(key in quality for key in ("score", "confidence", "prediction_confidence", "betting_confidence")):
            raise ContextFeatureIntegrationValidationError("PREDICTION_CONFIDENCE_FORBIDDEN", "feature_quality cannot contain confidence scores")
        if raw["input_hash"] != _input_hash(raw):
            raise ContextFeatureIntegrationValidationError("INPUT_HASH_MISMATCH", "input_hash is not recomputable")
        if raw["output_hash"] != _output_hash(raw):
            raise ContextFeatureIntegrationValidationError("OUTPUT_HASH_MISMATCH", "output_hash is not recomputable")
        if raw["provenance_hash"] != _provenance_hash(raw):
            raise ContextFeatureIntegrationValidationError("PROVENANCE_HASH_MISMATCH", "provenance_hash is not recomputable")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ContextFeatureIntegrationValidationError("REVISION_INVALID", "revision must be a positive integer")
        supersedes = raw.get("supersedes_integration_id")
        if revision == 1 and supersedes is not None:
            raise ContextFeatureIntegrationValidationError("ROOT_SUPERSEDES_INVALID", "revision 1 cannot supersede")
        expected_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"integration|{raw['input_hash']}|{raw['output_hash']}|{revision}"))
        if raw["integration_id"] != expected_id:
            raise ContextFeatureIntegrationValidationError("INTEGRATION_ID_MISMATCH", "integration_id is not deterministic")
        return cls(
            integration_id=_text(raw["integration_id"], "integration_id"),
            contract_version=CONTRACT_VERSION,
            football_intelligence_artifact_ref=_freeze(dict(feature_ref)),
            feature_bundle_ref=_freeze(dict(bundle_ref)),
            canonical_entity_refs=_freeze(dict(entity)),
            team_context_refs=teams,
            statistical_feature_refs=stats,
            evidence_refs=evidence,
            prediction_cutoff_at=_text(raw["prediction_cutoff_at"], "prediction_cutoff_at"),
            kickoff_at=_text(raw["kickoff_at"], "kickoff_at"),
            config_version=CONFIG_VERSION,
            config_hash=_hash(raw["config_hash"], "config_hash"),
            mapping_registry_version=MAPPING_REGISTRY_VERSION,
            generator_version=GENERATOR_VERSION,
            features=tuple(_freeze(dict(item)) for item in features),
            feature_quality=_freeze(dict(quality)),
            input_hash=raw["input_hash"],
            output_hash=raw["output_hash"],
            provenance_hash=raw["provenance_hash"],
            revision=revision,
            supersedes_integration_id=_text(supersedes, "supersedes_integration_id") if supersedes is not None else None,
        )


class ContextFeatureIntegrationEngine:
    """V4-045 context integration generator."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self._feature_engine = FootballIntelligenceEngine(config)

    @classmethod
    def from_repo_root(cls, repo_root) -> "ContextFeatureIntegrationEngine":
        return cls(load_approved_config(repo_root))

    def generate(
        self,
        *,
        football_intelligence_artifact: Union[FootballIntelligenceArtifact, Mapping[str, Any]],
        context_observations: Sequence[Mapping[str, Any]] = (),
        revision: int = 1,
        supersedes_integration_id: Optional[str] = None,
    ) -> ContextFeatureIntegrationArtifact:
        try:
            v4044 = football_intelligence_artifact if isinstance(football_intelligence_artifact, FootballIntelligenceArtifact) else FootballIntelligenceArtifact.from_dict(football_intelligence_artifact, config=self.config)
        except FootballIntelligenceValidationError as exc:
            raise ContextFeatureIntegrationValidationError(exc.code, f"V4-044 artifact is not accepted: {exc}") from exc
        raw_v4044 = v4044.to_dict()
        if raw_v4044["contract_version"] != FEATURE_CONTRACT_VERSION or raw_v4044["artifact_kind"] != ARTIFACT_KIND:
            raise ContextFeatureIntegrationValidationError("V4044_LIFECYCLE_INVALID", "V4-045 requires a pre-Frozen V4-044 artifact")
        bare = _find_bare_confidence(context_observations)
        if bare:
            raise ContextFeatureIntegrationValidationError("BARE_CONFIDENCE_FORBIDDEN", f"Team Context input contains {bare}")
        known_ids = {item["id"] for item in raw_v4044["team_context_refs"] + raw_v4044["evidence_refs"] + raw_v4044["statistical_feature_refs"]}
        extra_features = []
        entity = raw_v4044["canonical_entity_refs"]
        for observation in context_observations:
            try:
                feature = self._feature_engine._observation_feature(
                    observation,
                    cutoff=datetime.fromisoformat(raw_v4044["prediction_cutoff_at"]),
                    match_id=entity["match_id"],
                    home_team_id=entity["home_team_id"],
                    away_team_id=entity["away_team_id"],
                    known_ids=known_ids,
                )
            except (FootballIntelligenceValidationError, ValueError) as exc:
                if isinstance(exc, FootballIntelligenceValidationError):
                    raise ContextFeatureIntegrationValidationError(exc.code, str(exc)) from exc
                raise ContextFeatureIntegrationValidationError("TIME_INVALID", str(exc)) from exc
            extra_features.append(feature)
        existing = list(raw_v4044["features"])
        seen = {(item["feature_key"], item.get("team_id"), item.get("side")) for item in existing}
        for feature in extra_features:
            key = (feature["feature_key"], feature.get("team_id"), feature.get("side"))
            if key in seen:
                prior = next(item for item in existing if (item["feature_key"], item.get("team_id"), item.get("side")) == key)
                if prior != feature:
                    raise ContextFeatureIntegrationValidationError("FEATURE_COLLISION", f"{feature['feature_key']} would overwrite an existing V4-044 feature")
                continue
            existing.append(feature)
            seen.add(key)
        features = tuple(sorted(existing, key=lambda item: (item["feature_key"], item.get("team_id") or "", item.get("side") or "", tuple(item["source_refs"]))))
        raw: Dict[str, Any] = {
            "integration_id": "pending",
            "contract_version": CONTRACT_VERSION,
            "football_intelligence_artifact_ref": {"id": v4044.artifact_id, "hash": v4044.payload_hash},
            "feature_bundle_ref": raw_v4044["feature_bundle_ref"],
            "canonical_entity_refs": raw_v4044["canonical_entity_refs"],
            "team_context_refs": raw_v4044["team_context_refs"],
            "statistical_feature_refs": raw_v4044["statistical_feature_refs"],
            "evidence_refs": raw_v4044["evidence_refs"],
            "prediction_cutoff_at": raw_v4044["prediction_cutoff_at"],
            "kickoff_at": raw_v4044["kickoff_at"],
            "config_version": CONFIG_VERSION,
            "config_hash": sha256_json(self.config),
            "mapping_registry_version": MAPPING_REGISTRY_VERSION,
            "generator_version": GENERATOR_VERSION,
            "features": list(features),
            "feature_quality": _quality(features),
            "input_hash": "pending",
            "output_hash": "pending",
            "provenance_hash": "pending",
            "revision": revision,
            "supersedes_integration_id": supersedes_integration_id,
        }
        raw["input_hash"] = _input_hash(raw)
        raw["output_hash"] = _output_hash(raw)
        raw["provenance_hash"] = _provenance_hash(raw)
        raw["integration_id"] = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"integration|{raw['input_hash']}|{raw['output_hash']}|{revision}"))
        return ContextFeatureIntegrationArtifact.from_dict(raw, config=self.config)


class ContextFeatureIntegrationStore:
    """Append-only local integration ledger."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self._items: Dict[str, ContextFeatureIntegrationArtifact] = {}
        self._latest: Dict[Tuple[str, str], ContextFeatureIntegrationArtifact] = {}

    @property
    def integrations(self) -> Tuple[ContextFeatureIntegrationArtifact, ...]:
        return tuple(self._items.values())

    def append(self, artifact: Union[ContextFeatureIntegrationArtifact, Mapping[str, Any]]) -> str:
        item = artifact if isinstance(artifact, ContextFeatureIntegrationArtifact) else ContextFeatureIntegrationArtifact.from_dict(artifact, config=self.config)
        existing = self._items.get(item.integration_id)
        if existing is not None:
            if existing.output_hash == item.output_hash:
                return "DUPLICATE_NOOP"
            raise ContextFeatureIntegrationValidationError("INTEGRATION_ID_REUSE", "integration identity cannot be reused")
        family = (item.football_intelligence_artifact_ref["id"], item.generator_version)
        previous = self._latest.get(family)
        if previous is None:
            if item.revision != 1 or item.supersedes_integration_id is not None:
                raise ContextFeatureIntegrationValidationError("REVISION_ROOT_INVALID", "first integration revision must be 1")
        elif item.revision != previous.revision + 1 or item.supersedes_integration_id != previous.integration_id:
            raise ContextFeatureIntegrationValidationError("SUPERSEDES_REQUIRED", "correction must supersede the previous integration")
        self._items[item.integration_id] = item
        self._latest[family] = item
        return "APPEND"


__all__ = [
    "CONTRACT_VERSION",
    "GENERATOR_VERSION",
    "MAPPING_REGISTRY_VERSION",
    "ContextFeatureIntegrationArtifact",
    "ContextFeatureIntegrationEngine",
    "ContextFeatureIntegrationStore",
    "ContextFeatureIntegrationValidationError",
]
