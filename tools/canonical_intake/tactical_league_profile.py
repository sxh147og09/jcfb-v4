"""V4-049 typed tactical, league, and matchup pre-Freeze features."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .batch14_common import (
    Batch14ValidationError,
    STATES,
    canonical_entity,
    find_forbidden,
    freeze,
    hash_value,
    iso,
    load_batch14_governance,
    reference,
    text,
    timestamp,
    thaw,
    validate_boundary,
)
from .context_feature_integration import ContextFeatureIntegrationArtifact
from .feature_bundle import FeatureBundle, FeatureBundleValidationError
from .feature_snapshot import FeatureSnapshotHasher, FeatureSnapshotValidationError
from .football_intelligence_governance import load_approved_config


CONTRACT_VERSION = "tactical-league-profile-feature@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_TACTICAL_LEAGUE_PROFILE"
GENERATOR_VERSION = "v4-049-tactical-league-profile@1.0.0"
MAPPING_REGISTRY_VERSION = "tactical-league-profile-mapping@1.0.0"
ARTIFACT_NAMESPACE = uuid.UUID("9fba9914-97ad-5df0-bc7d-48e5908efcb3")
FEATURE_KEYS = {
    "style_relation": ("tactical", "CATEGORICAL"),
    "tactical_style": ("tactical", "CATEGORICAL"),
    "formation_relation": ("tactical", "CATEGORICAL"),
    "formation_state": ("tactical", "CATEGORICAL"),
    "press_build_up_relation": ("matchup", "RELATIONAL"),
    "width_transition_relation": ("matchup", "RELATIONAL"),
    "tactical_matchup": ("matchup", "RELATIONAL"),
    "league_tactical_context_profile": ("league", "CATEGORICAL"),
    "competition_context": ("league", "CATEGORICAL"),
    "league_context": ("league", "CATEGORICAL"),
}
FORBIDDEN_FEATURE_KEYS = frozenset(
    {
        "tactical_advantage_score",
        "matchup_impact",
        "league_adjustment_multiplier",
        "league_strength",
        "statistical_league_strength",
        "feature_importance",
    }
)


class TacticalLeagueProfileValidationError(Batch14ValidationError):
    """A tactical/league artifact cannot be safely admitted."""


def _hash(value: Any, field: str) -> str:
    return hash_value(value, field, TacticalLeagueProfileValidationError)


def _ref_list(value: Any, field: str, *, allow_empty: bool = True) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        raise TacticalLeagueProfileValidationError("REFERENCE_COLLECTION_INVALID", f"{field} must be a list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TacticalLeagueProfileValidationError("REFERENCE_INVALID", f"{field}[{index}] must be an object")
        normalized = dict(item)
        identifier = next((normalized.get(key) for key in ("id", "ref_id", "object_id", "feature_id", "artifact_id", "evidence_id") if normalized.get(key)), None)
        normalized["id"] = text(identifier, f"{field}[{index}].id", TacticalLeagueProfileValidationError)
        raw_hash = next((normalized.get(key) for key in ("hash", "ref_hash", "object_hash", "feature_hash", "output_hash", "provenance_hash", "feature_snapshot_hash") if normalized.get(key)), None)
        normalized["hash"] = _hash(raw_hash, f"{field}[{index}].hash")
        result.append(freeze(normalized))
    return tuple(result)


def _known_ref_ids(*groups: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(item["id"]) for group in groups for item in group}


def _observation_ref_list(raw: Any, field: str, known_ids: set[str]) -> Tuple[str, ...]:
    value = raw.get(field)
    if value is None and field == "source_refs":
        value = raw.get("source_ref")
    if value is None and field == "basis_refs":
        value = raw.get("evidence_refs")
    if isinstance(value, (str, Mapping)):
        value = [value]
    if not isinstance(value, (list, tuple)) or not value:
        raise TacticalLeagueProfileValidationError("FEATURE_PROVENANCE_REQUIRED", f"{field} must be a non-empty list")
    values = []
    for index, item in enumerate(value):
        identifier = item if isinstance(item, str) else item.get("id", item.get("ref_id")) if isinstance(item, Mapping) else None
        identifier = text(identifier, f"{field}[{index}].id", TacticalLeagueProfileValidationError)
        if identifier not in known_ids:
            raise TacticalLeagueProfileValidationError("REFERENCE_UNRESOLVED", f"{field}[{index}] is not declared in the artifact envelope")
        values.append(identifier)
    return tuple(values)


def _quality(features: Sequence[Mapping[str, Any]]) -> Mapping[str, str]:
    states = {str(item["state"]) for item in features}
    complete = bool(features) and states == {"AVAILABLE"}
    return {
        "coverage": "COMPLETE" if complete else "PARTIAL",
        "verification": "VERIFIED" if complete else "PARTIAL",
        "freshness": "UNKNOWN" if states.intersection({"STALE", "FUTURE_DATA", "BLOCKED"}) else ("CURRENT" if complete else "UNKNOWN"),
        "completeness": "COMPLETE" if complete else "PARTIAL",
        "conflict": "PRESENT" if "CONFLICTED" in states else "NONE",
        "provenance": "RESOLVED" if features and all(item.get("source_refs") and item.get("basis_refs") for item in features) else "UNKNOWN",
    }


def _hash_payload(raw: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    input_hash = sha256_json({
        "contract_version": raw["contract_version"],
        "feature_bundle_ref": raw["feature_bundle_ref"],
        "context_feature_artifact_ref": raw["context_feature_artifact_ref"],
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "team_context_refs": raw["team_context_refs"],
        "evidence_refs": raw["evidence_refs"],
        "prediction_cutoff_at": raw["prediction_cutoff_at"],
        "kickoff_at": raw["kickoff_at"],
        "generator_version": raw["generator_version"],
        "implementation_hash": raw["implementation_hash"],
        "config_version": raw["config_version"],
        "config_hash": raw["config_hash"],
        "mapping_registry_version": raw["mapping_registry_version"],
        "source_observations": raw["source_observations"],
    })
    payload_hash = sha256_json({"features": raw["features"], "feature_quality": raw["feature_quality"], "quality_flags": raw["quality_flags"]})
    provenance_hash = sha256_json({
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "feature_bundle_ref": raw["feature_bundle_ref"],
        "context_feature_artifact_ref": raw["context_feature_artifact_ref"],
        "team_context_refs": raw["team_context_refs"],
        "evidence_refs": raw["evidence_refs"],
        "feature_provenance": [{"feature_key": item["feature_key"], "source_refs": item["source_refs"], "basis_refs": item["basis_refs"], "state": item["state"]} for item in raw["features"]],
    })
    output_hash = sha256_json({"artifact_kind": raw["artifact_kind"], "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash, "features": raw["features"], "feature_quality": raw["feature_quality"], "quality_flags": raw["quality_flags"]})
    return input_hash, payload_hash, provenance_hash, output_hash


def _implementation_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _validate_feature(raw: Mapping[str, Any], index: int, known_ids: set[str], cutoff: datetime, kickoff: datetime) -> Dict[str, Any]:
    key = text(raw.get("feature_key"), f"features[{index}].feature_key", TacticalLeagueProfileValidationError).casefold()
    if key in FORBIDDEN_FEATURE_KEYS or any(token in key for token in ("score", "multiplier", "impact", "importance")):
        raise TacticalLeagueProfileValidationError("ARBITRARY_TACTICAL_SCORE_FORBIDDEN", f"features[{index}] is not an approved typed relation")
    if key not in FEATURE_KEYS:
        raise TacticalLeagueProfileValidationError("FEATURE_MAPPING_NOT_APPROVED", f"features[{index}].feature_key has no approved vocabulary mapping")
    category, expected_kind = FEATURE_KEYS[key]
    kind = text(raw.get("kind", expected_kind), f"features[{index}].kind", TacticalLeagueProfileValidationError).upper()
    if kind != expected_kind:
        raise TacticalLeagueProfileValidationError("FEATURE_KIND_INVALID", f"{key} must remain {expected_kind}")
    supplied_category = text(raw.get("category", category), f"features[{index}].category", TacticalLeagueProfileValidationError).casefold()
    if supplied_category != category:
        raise TacticalLeagueProfileValidationError("FEATURE_CATEGORY_INVALID", f"{key} belongs to {category}")
    state = text(raw.get("state", "AVAILABLE"), f"features[{index}].state", TacticalLeagueProfileValidationError).upper()
    if state not in STATES - {"NOT_APPLICABLE"}:
        raise TacticalLeagueProfileValidationError("FEATURE_STATE_INVALID", f"features[{index}].state is not governed")
    source_refs = _observation_ref_list(raw, "source_refs", known_ids)
    basis_refs = _observation_ref_list(raw, "basis_refs", known_ids)
    value = raw.get("value")
    if state == "AVAILABLE":
        if value in (None, "", [], {}):
            raise TacticalLeagueProfileValidationError("AVAILABLE_VALUE_EMPTY", f"features[{index}] AVAILABLE requires a typed value")
        if kind == "CATEGORICAL" and not isinstance(value, str):
            raise TacticalLeagueProfileValidationError("CATEGORICAL_VALUE_INVALID", f"features[{index}] categorical value must be text")
        if kind == "RELATIONAL" and not isinstance(value, Mapping):
            raise TacticalLeagueProfileValidationError("RELATIONAL_VALUE_INVALID", f"features[{index}] relational value must be an object")
    else:
        if value not in (None, "", [], {}):
            raise TacticalLeagueProfileValidationError("NON_CONSUMABLE_VALUE_PRESENT", f"features[{index}] non-consumable state cannot carry a replacement value")
        reason_code = text(raw.get("reason_code"), f"features[{index}].reason_code", TacticalLeagueProfileValidationError).upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code):
            raise TacticalLeagueProfileValidationError("REASON_CODE_INVALID", f"features[{index}].reason_code is invalid")
        reason_detail = text(raw.get("reason_detail"), f"features[{index}].reason_detail", TacticalLeagueProfileValidationError)
    times: Dict[str, Optional[str]] = {}
    parsed: Dict[str, datetime] = {}
    for field in ("source_timestamp", "observed_at", "effective_at", "expires_at"):
        if raw.get(field) is not None:
            parsed[field] = timestamp(raw[field], f"features[{index}].{field}", TacticalLeagueProfileValidationError)
            times[field] = iso(parsed[field])
        else:
            times[field] = None
    availability = parsed.get("effective_at") or parsed.get("source_timestamp") or parsed.get("observed_at")
    if availability is None:
        state = "BLOCKED"
        value = None
        reason_code = "SOURCE_TIMESTAMP_UNKNOWN"
        reason_detail = "No timezone-aware source/effective/observed timestamp was supplied."
    elif availability > cutoff:
        state = "FUTURE_DATA"
        value = None
        reason_code = "FUTURE_DATA"
        reason_detail = "The tactical observation is after prediction_cutoff_at."
    elif parsed.get("expires_at") is not None and parsed["expires_at"] < cutoff and state == "AVAILABLE":
        state = "STALE"
        value = None
        reason_code = "STALE_REQUIRES_UPSTREAM_POLICY"
        reason_detail = "The tactical observation expired before prediction_cutoff_at."
    result = {
        "feature_key": key,
        "category": category,
        "kind": kind,
        "state": state,
        "value": value,
        "unit": text(raw.get("unit", "relation"), f"features[{index}].unit", TacticalLeagueProfileValidationError),
        "source_refs": list(source_refs),
        "basis_refs": list(basis_refs),
        "reason_code": None,
        "reason_detail": None,
        "required": bool(raw.get("required", False)),
        "source_timestamp": times["source_timestamp"],
        "observed_at": times["observed_at"],
        "effective_at": times["effective_at"],
        "expires_at": times["expires_at"],
    }
    if state != "AVAILABLE":
        result["reason_code"] = reason_code
        result["reason_detail"] = reason_detail
    return result


@dataclass(frozen=True)
class TacticalLeagueProfileArtifact:
    artifact_id: str
    artifact_kind: str
    contract_version: str
    feature_bundle_ref: Mapping[str, Any]
    context_feature_artifact_ref: Mapping[str, Any]
    canonical_entity_refs: Mapping[str, Any]
    team_context_refs: Tuple[Mapping[str, Any], ...]
    evidence_refs: Tuple[Mapping[str, Any], ...]
    prediction_cutoff_at: str
    kickoff_at: str
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    mapping_registry_version: str
    source_observations: Tuple[Mapping[str, Any], ...]
    features: Tuple[Mapping[str, Any], ...]
    feature_quality: Mapping[str, str]
    quality_flags: Tuple[str, ...]
    input_hash: str
    payload_hash: str
    provenance_hash: str
    output_hash: str
    revision: int
    supersedes_artifact_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "feature_bundle_ref": thaw(self.feature_bundle_ref),
            "context_feature_artifact_ref": thaw(self.context_feature_artifact_ref),
            "canonical_entity_refs": thaw(self.canonical_entity_refs),
            "team_context_refs": [thaw(item) for item in self.team_context_refs],
            "evidence_refs": [thaw(item) for item in self.evidence_refs],
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "mapping_registry_version": self.mapping_registry_version,
            "source_observations": [thaw(item) for item in self.source_observations],
            "features": [thaw(item) for item in self.features],
            "feature_quality": thaw(self.feature_quality),
            "quality_flags": list(self.quality_flags),
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "output_hash": self.output_hash,
            "revision": self.revision,
            "supersedes_artifact_id": self.supersedes_artifact_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config: Mapping[str, Any], matrix: Optional[Mapping[str, Any]] = None, reasons: Optional[Mapping[str, Any]] = None) -> "TacticalLeagueProfileArtifact":
        if not isinstance(raw, Mapping):
            raise TacticalLeagueProfileValidationError("ARTIFACT_INVALID", "artifact must be an object")
        forbidden = find_forbidden(raw)
        if forbidden:
            raise TacticalLeagueProfileValidationError("FORBIDDEN_FIELD", f"artifact contains {forbidden}")
        if raw.get("artifact_kind") != ARTIFACT_KIND or raw.get("contract_version") != CONTRACT_VERSION:
            raise TacticalLeagueProfileValidationError("CONTRACT_VERSION_INVALID", "artifact kind or contract version is not approved")
        entity = canonical_entity(raw.get("canonical_entity_refs"), TacticalLeagueProfileValidationError)
        cutoff_text, kickoff_text, cutoff, kickoff = validate_boundary(raw.get("prediction_cutoff_at"), raw.get("kickoff_at"), TacticalLeagueProfileValidationError)
        if raw.get("generator_version") != GENERATOR_VERSION or raw.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
            raise TacticalLeagueProfileValidationError("VERSION_INVALID", "generator or mapping registry version is not approved")
        if raw.get("config_version") != config.get("config_version") or raw.get("config_hash") != config.get("canonical_hash"):
            raise TacticalLeagueProfileValidationError("CONFIG_HASH_MISMATCH", "artifact does not identify the approved BATCH-14 config")
        bundle_ref = _ref_list([raw.get("feature_bundle_ref")], "feature_bundle_ref", allow_empty=False)[0]
        context_ref = _ref_list([raw.get("context_feature_artifact_ref")], "context_feature_artifact_ref", allow_empty=False)[0]
        team_refs = _ref_list(raw.get("team_context_refs"), "team_context_refs")
        evidence_refs = _ref_list(raw.get("evidence_refs"), "evidence_refs")
        source_observations = _ref_list(raw.get("source_observations"), "source_observations", allow_empty=False)
        features_raw = raw.get("features")
        if not isinstance(features_raw, list) or not features_raw:
            raise TacticalLeagueProfileValidationError("FEATURES_REQUIRED", "features must be a non-empty list")
        known = _known_ref_ids(team_refs, evidence_refs, source_observations)
        features = tuple(freeze(_validate_feature(item, index, known, cutoff, kickoff)) for index, item in enumerate(features_raw))
        quality = raw.get("feature_quality")
        if not isinstance(quality, Mapping) or set(quality) != {"coverage", "verification", "freshness", "completeness", "conflict", "provenance"}:
            raise TacticalLeagueProfileValidationError("FEATURE_QUALITY_INVALID", "feature_quality must be six typed dimensions")
        flags_raw = raw.get("quality_flags", [])
        if not isinstance(flags_raw, list):
            raise TacticalLeagueProfileValidationError("QUALITY_FLAGS_INVALID", "quality_flags must be a list")
        normalized = dict(raw)
        normalized.update({
            "feature_bundle_ref": thaw(bundle_ref), "context_feature_artifact_ref": thaw(context_ref), "canonical_entity_refs": entity,
            "team_context_refs": [thaw(item) for item in team_refs], "evidence_refs": [thaw(item) for item in evidence_refs],
            "prediction_cutoff_at": cutoff_text, "kickoff_at": kickoff_text, "source_observations": [thaw(item) for item in source_observations],
            "features": [thaw(item) for item in features], "feature_quality": dict(quality), "quality_flags": list(flags_raw),
        })
        calculated = _hash_payload(normalized)
        for name, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), calculated):
            if raw.get(name) != value:
                raise TacticalLeagueProfileValidationError(f"{name.upper()}_MISMATCH", f"{name} is not recomputable")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise TacticalLeagueProfileValidationError("REVISION_INVALID", "revision must be a positive integer")
        supersedes = raw.get("supersedes_artifact_id")
        if revision == 1 and supersedes is not None:
            raise TacticalLeagueProfileValidationError("ROOT_SUPERSEDES_INVALID", "revision 1 cannot supersede an artifact")
        expected_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"artifact|{calculated[0]}|{calculated[1]}|{revision}"))
        if raw.get("artifact_id") != expected_id:
            raise TacticalLeagueProfileValidationError("ARTIFACT_ID_MISMATCH", "artifact_id is not deterministic")
        if raw.get("implementation_hash") != _implementation_hash():
            raise TacticalLeagueProfileValidationError("IMPLEMENTATION_HASH_MISMATCH", "implementation_hash does not identify this implementation")
        return cls(
            artifact_id=expected_id, artifact_kind=ARTIFACT_KIND, contract_version=CONTRACT_VERSION,
            feature_bundle_ref=bundle_ref, context_feature_artifact_ref=context_ref, canonical_entity_refs=freeze(entity),
            team_context_refs=team_refs, evidence_refs=evidence_refs, prediction_cutoff_at=cutoff_text, kickoff_at=kickoff_text,
            generator_version=GENERATOR_VERSION, implementation_hash=_hash(raw.get("implementation_hash"), "implementation_hash"),
            config_version=text(raw["config_version"], "config_version", TacticalLeagueProfileValidationError), config_hash=_hash(raw["config_hash"], "config_hash"),
            mapping_registry_version=MAPPING_REGISTRY_VERSION, source_observations=source_observations,
            features=features, feature_quality=freeze(dict(quality)), quality_flags=tuple(text(item, "quality_flags[]", TacticalLeagueProfileValidationError) for item in flags_raw),
            input_hash=calculated[0], payload_hash=calculated[1], provenance_hash=calculated[2], output_hash=calculated[3], revision=revision,
            supersedes_artifact_id=text(supersedes, "supersedes_artifact_id", TacticalLeagueProfileValidationError) if supersedes is not None else None,
        )


class TacticalLeagueProfileEngine:
    """Generate typed relations without tactical scores or league-strength values."""

    def __init__(self, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any], repo_root: Path):
        self.config = config
        self.matrix = matrix
        self.reasons = reasons
        self.repo_root = Path(repo_root).resolve()
        self.config_hash = config["canonical_hash"]
        self.implementation_hash = _implementation_hash()

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "TacticalLeagueProfileEngine":
        root = Path(repo_root).resolve()
        if root.drive.upper() != "F:":
            raise TacticalLeagueProfileValidationError("F_DRIVE_REQUIRED", "V4-049 runtime must use the F: drive")
        config, matrix, reasons = load_batch14_governance(root)
        return cls(config, matrix, reasons, root)

    @staticmethod
    def _bundle(raw: Union[FeatureBundle, Mapping[str, Any]]) -> FeatureBundle:
        try:
            bundle = raw if isinstance(raw, FeatureBundle) else FeatureBundle.from_dict(raw)
            if not bundle.feature_snapshot_hash:
                raise TacticalLeagueProfileValidationError("FEATURE_SNAPSHOT_REQUIRED", "V4-049 requires an accepted Feature Snapshot hash")
            FeatureSnapshotHasher.verify(bundle, bundle.feature_snapshot_hash)
            return bundle
        except (FeatureBundleValidationError, FeatureSnapshotValidationError) as exc:
            raise TacticalLeagueProfileValidationError(exc.code, str(exc)) from exc

    def generate(
        self,
        *,
        feature_bundle: Union[FeatureBundle, Mapping[str, Any]],
        context_feature_artifact: Union[ContextFeatureIntegrationArtifact, Mapping[str, Any]],
        tactical_observations: Optional[Sequence[Mapping[str, Any]]] = None,
        league_observations: Optional[Sequence[Mapping[str, Any]]] = None,
        observations: Optional[Sequence[Mapping[str, Any]]] = None,
        revision: int = 1,
        supersedes_artifact_id: Optional[str] = None,
    ) -> TacticalLeagueProfileArtifact:
        bundle = self._bundle(feature_bundle)
        try:
            context = context_feature_artifact if isinstance(context_feature_artifact, ContextFeatureIntegrationArtifact) else ContextFeatureIntegrationArtifact.from_dict(context_feature_artifact, config=load_approved_config(self.repo_root))
        except Exception as exc:
            if isinstance(exc, TacticalLeagueProfileValidationError):
                raise
            raise TacticalLeagueProfileValidationError(getattr(exc, "code", "UPSTREAM_CONTEXT_INVALID"), str(exc)) from exc
        bundle_raw = bundle.to_dict()
        context_raw = context.to_dict()
        match_id = bundle_raw["canonical_entity_refs"]["match_id"]
        if context_raw["canonical_entity_refs"]["match_id"] != match_id:
            raise TacticalLeagueProfileValidationError("CANONICAL_IDENTITY_MISMATCH", "V4-045 context artifact is bound to another match")
        cutoff_text, kickoff_text, cutoff, kickoff = validate_boundary(bundle.prediction_cutoff_at, bundle.kickoff_at, TacticalLeagueProfileValidationError)
        context_cutoff = timestamp(context.prediction_cutoff_at, "context.prediction_cutoff_at", TacticalLeagueProfileValidationError)
        context_kickoff = timestamp(context.kickoff_at, "context.kickoff_at", TacticalLeagueProfileValidationError)
        if context_cutoff != cutoff or context_kickoff != kickoff:
            raise TacticalLeagueProfileValidationError("TIME_BOUNDARY_MISMATCH", "upstream context cutoff/kickoff differs from the Feature Bundle")
        def refs(values: Iterable[Mapping[str, Any]], field: str) -> Tuple[Mapping[str, Any], ...]:
            normalized = []
            for item in values:
                raw = dict(item)
                identifier = raw.get("id", raw.get("ref_id"))
                raw["id"] = text(identifier, f"{field}.id", TacticalLeagueProfileValidationError)
                raw["hash"] = _hash(raw.get("hash", raw.get("ref_hash", raw.get("output_hash", raw.get("feature_snapshot_hash")))), f"{field}.hash")
                normalized.append(freeze(raw))
            return tuple(normalized)
        team_refs = refs(context_raw["team_context_refs"], "team_context_refs")
        evidence_refs = refs(context_raw["evidence_refs"], "evidence_refs")
        feature_bundle_ref = freeze({"id": bundle.feature_bundle_id, "hash": bundle.feature_snapshot_hash})
        context_ref = freeze({"id": context.integration_id, "hash": context.output_hash})
        source_refs = refs(list(team_refs) + list(evidence_refs), "source_observations")
        known_ids = _known_ref_ids(team_refs, evidence_refs, source_refs)
        rows: List[Mapping[str, Any]] = []
        combined = list(observations or []) + list(tactical_observations or []) + list(league_observations or [])
        if not combined:
            raise TacticalLeagueProfileValidationError("TACTICAL_OBSERVATIONS_REQUIRED", "at least one typed tactical or league observation is required")
        for index, observation in enumerate(combined):
            if not isinstance(observation, Mapping):
                raise TacticalLeagueProfileValidationError("OBSERVATION_INVALID", f"observations[{index}] must be an object")
            forbidden = find_forbidden(observation, f"observations[{index}]")
            if forbidden:
                raise TacticalLeagueProfileValidationError("FORBIDDEN_FIELD", f"observation contains {forbidden}")
            # Observations are lineage references in the output; their source/basis refs
            # remain the accepted upstream refs, never free-form source material.
            rows.append(freeze(dict(observation)))
        features = tuple(freeze(_validate_feature(item, index, known_ids, cutoff, kickoff)) for index, item in enumerate(combined))
        flags = []
        if any(item["state"] in {"UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "CONFLICTED", "STALE", "FUTURE_DATA", "BLOCKED"} for item in features):
            flags.append("NON_CONSUMABLE_TACTICAL_OR_LEAGUE_INPUT_PRESENT")
        raw = {
            "artifact_id": "",
            "artifact_kind": ARTIFACT_KIND,
            "contract_version": CONTRACT_VERSION,
            "feature_bundle_ref": thaw(feature_bundle_ref),
            "context_feature_artifact_ref": thaw(context_ref),
            "canonical_entity_refs": bundle_raw["canonical_entity_refs"],
            "team_context_refs": [thaw(item) for item in team_refs],
            "evidence_refs": [thaw(item) for item in evidence_refs],
            "prediction_cutoff_at": cutoff_text,
            "kickoff_at": kickoff_text,
            "generator_version": GENERATOR_VERSION,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config["config_version"],
            "config_hash": self.config_hash,
            "mapping_registry_version": MAPPING_REGISTRY_VERSION,
            "source_observations": [thaw(item) for item in source_refs],
            "features": [thaw(item) for item in features],
            "feature_quality": dict(_quality(features)),
            "quality_flags": flags,
            "revision": revision,
            "supersedes_artifact_id": supersedes_artifact_id,
        }
        hashes = _hash_payload(raw)
        raw.update({name: value for name, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), hashes)})
        raw["artifact_id"] = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"artifact|{hashes[0]}|{hashes[1]}|{revision}"))
        return TacticalLeagueProfileArtifact.from_dict(raw, config=self.config, matrix=self.matrix, reasons=self.reasons)


class TacticalLeagueProfileStore:
    """Append-only local store for V4-049 artifacts."""

    def __init__(self, config: Mapping[str, Any], matrix: Optional[Mapping[str, Any]] = None, reasons: Optional[Mapping[str, Any]] = None):
        self.config, self.matrix, self.reasons = config, matrix or {}, reasons or {}
        self._artifacts: Dict[str, TacticalLeagueProfileArtifact] = {}

    @property
    def artifacts(self) -> Tuple[TacticalLeagueProfileArtifact, ...]:
        return tuple(self._artifacts.values())

    def append(self, artifact: Union[TacticalLeagueProfileArtifact, Mapping[str, Any]]) -> str:
        item = artifact if isinstance(artifact, TacticalLeagueProfileArtifact) else TacticalLeagueProfileArtifact.from_dict(artifact, config=self.config, matrix=self.matrix, reasons=self.reasons)
        existing = self._artifacts.get(item.artifact_id)
        if existing is not None:
            if existing.to_dict() == item.to_dict():
                return "DUPLICATE_NOOP"
            raise TacticalLeagueProfileValidationError("ARTIFACT_ID_REUSE", "artifact identity cannot be reused")
        if item.supersedes_artifact_id is not None:
            predecessor = self._artifacts.get(item.supersedes_artifact_id)
            if predecessor is None or predecessor.revision + 1 != item.revision:
                raise TacticalLeagueProfileValidationError("SUPERSEDES_INVALID", "corrections require the immediate predecessor and next revision")
            if predecessor.canonical_entity_refs["match_id"] != item.canonical_entity_refs["match_id"]:
                raise TacticalLeagueProfileValidationError("SUPERSEDES_FAMILY_CONFLICT", "correction must remain in the same match family")
        elif item.revision != 1:
            raise TacticalLeagueProfileValidationError("SUPERSEDES_REQUIRED", "a non-root revision must explicitly supersede the prior artifact")
        self._artifacts[item.artifact_id] = item
        return "APPEND"


__all__ = [
    "ARTIFACT_KIND", "CONTRACT_VERSION", "GENERATOR_VERSION", "MAPPING_REGISTRY_VERSION", "TacticalLeagueProfileArtifact",
    "TacticalLeagueProfileEngine", "TacticalLeagueProfileStore", "TacticalLeagueProfileValidationError",
]
