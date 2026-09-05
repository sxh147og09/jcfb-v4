"""V4-048 descriptive market heat and anomaly evidence profiles.

This module consumes accepted V4-047 movement artifacts only.  Heat and
pressure are component objects and trap-risk is an evidence profile; no
single score, bookmaker intent, prediction, recommendation, or final risk
decision is emitted.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from tools.migration_harness.common import sha256_json

from .market_movement import MarketMovementArtifact


CONTRACT_VERSION = "market-risk-interpretation@1.0.0"
MOVEMENT_CONTRACT_VERSION = "market-movement@1.0.0"
CONFIG_VERSION = "market-intelligence-config@1.0.0"
MAPPING_REGISTRY_VERSION = "market-intelligence-mapping@1.0.0"
GENERATOR_VERSION = "v4-048-market-risk-interpretation@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_MARKET_RISK_INTERPRETATION_ARTIFACT"
ARTIFACT_NAMESPACE = uuid.UUID("73bbf33e-c0ad-5f61-85b0-b6515ad16b9f")
APPROVED_FLAGS = frozenset({
    "DIRECTION_REVERSAL",
    "PROVIDER_DISPERSION",
    "OFFICIAL_EXTERNAL_DIVERGENCE",
    "SPARSE_MARKET",
    "STALE_MARKET",
    "CONFLICTED_MARKET",
})
DISABLED_FLAGS = frozenset({
    "LINE_PRICE_DISLOCATION",
    "RAPID_MOVEMENT",
    "MULTI_PROVIDER_DIRECTION_CONCENTRATION",
    "LATE_MOVEMENT",
})
INTERPRETATION_STATES = frozenset({"NONE_OBSERVED", "SIGNAL_PRESENT", "MULTIPLE_SIGNALS", "INSUFFICIENT_DATA", "CONFLICTED", "BLOCKED"})


class MarketRiskInterpretationValidationError(ValueError):
    """A V4-048 input or evidence profile is unsafe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketRiskInterpretationValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MarketRiskInterpretationValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketRiskInterpretationValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


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


def _sign(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return 1 if number > 0 else -1 if number < 0 else 0


def _source_time(item: MarketMovementArtifact, field: str = "source_time_after") -> Optional[datetime]:
    value = getattr(item, field)
    return None if value is None else _timestamp(value, field)


@dataclass(frozen=True)
class MarketRiskInterpretationArtifact:
    artifact_id: str
    artifact_kind: str
    contract_version: str
    canonical_match_id: str
    market: str
    movement_refs: Tuple[Mapping[str, Any], ...]
    prediction_cutoff_at: str
    kickoff_at: str
    heat_profile: Mapping[str, Any]
    pressure_profile: Mapping[str, Any]
    anomaly_profile: Mapping[str, Any]
    interpretation_state: str
    source_refs: Tuple[str, ...]
    basis_refs: Tuple[str, ...]
    feature_quality: Mapping[str, str]
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    mapping_registry_version: str
    input_hash: str
    payload_hash: str
    provenance_hash: str
    output_hash: str
    revision: int = 1
    supersedes_artifact_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "canonical_match_id": self.canonical_match_id,
            "market": self.market,
            "movement_refs": _thaw(self.movement_refs),
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "heat_profile": _thaw(self.heat_profile),
            "pressure_profile": _thaw(self.pressure_profile),
            "anomaly_profile": _thaw(self.anomaly_profile),
            "interpretation_state": self.interpretation_state,
            "source_refs": list(self.source_refs),
            "basis_refs": list(self.basis_refs),
            "feature_quality": _thaw(self.feature_quality),
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "mapping_registry_version": self.mapping_registry_version,
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "output_hash": self.output_hash,
            "revision": self.revision,
            "supersedes_artifact_id": self.supersedes_artifact_id,
        }


@dataclass(frozen=True)
class MarketRiskInterpretationResult:
    accepted: bool
    action: str
    artifact: Optional[MarketRiskInterpretationArtifact]
    error_code: Optional[str] = None


class MarketRiskInterpretationEngine:
    """Build multidimensional heat/pressure and structural evidence only."""

    def __init__(self, *, config: Optional[Mapping[str, Any]] = None, mapping: Optional[Mapping[str, Any]] = None):
        self.config = dict(config or {})
        self.mapping = dict(mapping or {})
        self._validate_governance()

    @classmethod
    def from_repo_root(cls, root: Path) -> "MarketRiskInterpretationEngine":
        config = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_CONFIG.json").read_text(encoding="utf-8"))
        mapping = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_MAPPING.json").read_text(encoding="utf-8"))
        return cls(config=config, mapping=mapping)

    def _validate_governance(self) -> None:
        if self.config:
            if self.config.get("config_version") != CONFIG_VERSION:
                raise MarketRiskInterpretationValidationError("CONFIG_VERSION_INVALID", "V4-048 config version is not approved")
            heat = self.config.get("heat_policy", {})
            if heat.get("representation") != "MULTIDIMENSIONAL_ACTIVITY_OBJECT":
                raise MarketRiskInterpretationValidationError("HEAT_POLICY_INVALID", "heat must remain multidimensional")
            if set(heat.get("components", [])) != {"snapshot_count", "price_change_count", "line_change_count", "total_absolute_price_movement", "total_absolute_line_movement", "movement_velocity", "provider_breadth", "direction_agreement", "observation_span", "minutes_to_kickoff"}:
                raise MarketRiskInterpretationValidationError("HEAT_COMPONENTS_INVALID", "heat components drifted")
            if self.config.get("pressure_policy", {}).get("representation") != "COMPONENT_OBJECT":
                raise MarketRiskInterpretationValidationError("PRESSURE_POLICY_INVALID", "pressure must remain a component object")
            if self.config.get("risk_interpretation_policy", {}).get("trap_risk_score") != "FORBIDDEN":
                raise MarketRiskInterpretationValidationError("TRAP_SCORE_POLICY_INVALID", "trap-risk score must remain forbidden")
            configured_flags = set(self.config.get("risk_interpretation_policy", {}).get("flags", []))
            if configured_flags != APPROVED_FLAGS:
                raise MarketRiskInterpretationValidationError("RISK_FLAGS_INVALID", "approved structural flag set drifted")
            if not DISABLED_FLAGS.issubset(set(self.config.get("risk_interpretation_policy", {}).get("disabled_until_explicit_threshold", []))):
                raise MarketRiskInterpretationValidationError("DISABLED_FLAGS_INVALID", "disabled threshold flags drifted")
        if self.mapping and self.mapping.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
            raise MarketRiskInterpretationValidationError("MAPPING_VERSION_INVALID", "V4-048 mapping version is not approved")

    def interpret(self, movements: Sequence[MarketMovementArtifact], prediction_cutoff_at: Any, kickoff_at: Any) -> MarketRiskInterpretationResult:
        try:
            cutoff = _timestamp(prediction_cutoff_at, "prediction_cutoff_at")
            kickoff = _timestamp(kickoff_at, "kickoff_at")
            if cutoff >= kickoff:
                raise MarketRiskInterpretationValidationError("CUTOFF_NOT_BEFORE_KICKOFF", "cutoff must precede kickoff")
            self._validate_inputs(movements, cutoff, kickoff)
            if not movements:
                raise MarketRiskInterpretationValidationError("MOVEMENT_INPUT_EMPTY", "V4-048 requires an explicit movement input collection")
            heat = self._heat(movements, kickoff)
            pressure = self._pressure(movements)
            anomaly, state = self._anomaly(movements)
            movement_refs = tuple({"movement_id": item.movement_id, "output_hash": item.output_hash} for item in movements)
            source_refs = tuple(sorted({item.source for item in movements}))
            basis_refs = tuple(sorted({ref for item in movements for ref in item.basis_refs}))
            quality = {"coverage": "COMPLETE", "verification": "VERIFIED", "freshness": "CURRENT", "completeness": "COMPLETE", "conflict": "PRESENT" if state == "CONFLICTED" else "NONE", "provenance": "RESOLVED"}
            input_hash = sha256_json({"contract_version": CONTRACT_VERSION, "movement_refs": movement_refs, "match_id": movements[0].canonical_match_id, "market": movements[0].market, "cutoff": _iso(cutoff), "kickoff": _iso(kickoff), "config_version": CONFIG_VERSION, "mapping_registry_version": MAPPING_REGISTRY_VERSION})
            payload = {"heat_profile": heat, "pressure_profile": pressure, "anomaly_profile": anomaly, "interpretation_state": state}
            payload_hash = sha256_json(payload)
            provenance_hash = sha256_json({"source_refs": source_refs, "basis_refs": basis_refs, "movement_refs": movement_refs})
            artifact_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"risk-interpretation|{input_hash}|{payload_hash}"))
            output_hash = sha256_json({"artifact_id": artifact_id, "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash, **payload})
            artifact = MarketRiskInterpretationArtifact(artifact_id, ARTIFACT_KIND, CONTRACT_VERSION, movements[0].canonical_match_id, movements[0].market, _freeze(movement_refs), _iso(cutoff), _iso(kickoff), _freeze(heat), _freeze(pressure), _freeze(anomaly), state, source_refs, basis_refs, _freeze(quality), GENERATOR_VERSION, "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), CONFIG_VERSION, self.config.get("config_hash", sha256_json(self.config)), MAPPING_REGISTRY_VERSION, input_hash, payload_hash, provenance_hash, output_hash)
            return MarketRiskInterpretationResult(True, "APPROVED_PROFILE", artifact)
        except MarketRiskInterpretationValidationError as exc:
            return MarketRiskInterpretationResult(False, "BLOCKED", None, exc.code)

    def _validate_inputs(self, movements: Sequence[MarketMovementArtifact], cutoff: datetime, kickoff: datetime) -> None:
        for item in movements:
            if not isinstance(item, MarketMovementArtifact):
                raise MarketRiskInterpretationValidationError("MOVEMENT_TYPE_INVALID", "V4-048 accepts V4-047 artifacts only")
            if item.contract_version != MOVEMENT_CONTRACT_VERSION:
                raise MarketRiskInterpretationValidationError("MOVEMENT_CONTRACT_INVALID", "V4-048 requires market-movement@1.0.0")
            if item.state not in {"AVAILABLE", "UNKNOWN", "NOT_COMPARABLE", "STALE", "CONFLICTED"}:
                raise MarketRiskInterpretationValidationError("MOVEMENT_STATE_INVALID", "movement state is not consumable by V4-048")
            if item.prediction_cutoff_at != _iso(cutoff) or item.kickoff_at != _iso(kickoff):
                raise MarketRiskInterpretationValidationError("TIME_BOUNDARY_CONFLICT", "all movement artifacts must share cutoff and kickoff")
            if item.source_time_after is not None and _timestamp(item.source_time_after, "source_time_after") > cutoff:
                raise MarketRiskInterpretationValidationError("POST_CUTOFF_INPUT", "post-cutoff movement cannot enter V4-048")
        first = movements[0]
        if any(item.canonical_match_id != first.canonical_match_id or item.market != first.market for item in movements[1:]):
            raise MarketRiskInterpretationValidationError("MOVEMENT_SCOPE_CONFLICT", "all movements must share canonical match and market")

    def _heat(self, movements: Sequence[MarketMovementArtifact], kickoff: datetime) -> Mapping[str, Any]:
        refs = {ref["snapshot_id"] for item in movements for ref in item.snapshot_refs}
        price = [item for item in movements if item.movement_type == "PRICE_MOVEMENT" and item.state == "AVAILABLE"]
        line = [item for item in movements if item.movement_type == "LINE_MOVEMENT" and item.state == "AVAILABLE"]
        velocities = []
        for item in movements:
            if item.state == "AVAILABLE" and item.elapsed_hours and item.typed_value and item.typed_value.get("value_delta") is not None:
                velocities.append({"movement_id": item.movement_id, "selection": item.selection, "value_per_hour": item.typed_value["value_delta"] / item.elapsed_hours, "unit": item.unit, "provider": item.provider})
        times = [_source_time(item, "source_time_before") for item in movements if item.source_time_before] + [_source_time(item, "source_time_after") for item in movements if item.source_time_after]
        valid_times = [item for item in times if item is not None]
        span = (max(valid_times) - min(valid_times)).total_seconds() / 3600 if len(valid_times) >= 2 else 0.0
        latest = max(valid_times) if valid_times else None
        signs = [_sign(item.typed_value.get("value_delta")) for item in price + line if item.typed_value]
        return {
            "snapshot_count": len(refs),
            "price_change_count": sum(1 for item in price if _sign(item.typed_value.get("value_delta")) != 0),
            "line_change_count": sum(1 for item in line if _sign(item.typed_value.get("value_delta")) != 0),
            "total_absolute_price_movement": sum(abs(float(item.typed_value["value_delta"])) for item in price),
            "total_absolute_line_movement": sum(abs(float(item.typed_value["value_delta"])) for item in line),
            "movement_velocity": velocities,
            "provider_breadth": len({item.provider for item in movements if item.provider != "MULTI_PROVIDER"}),
            "direction_agreement": {"positive_count": signs.count(1), "negative_count": signs.count(-1), "zero_count": signs.count(0)},
            "observation_span": {"hours": span, "source_time_start": _iso(min(valid_times)) if valid_times else None, "source_time_end": _iso(max(valid_times)) if valid_times else None},
            "minutes_to_kickoff": (kickoff - latest).total_seconds() / 60 if latest else None,
        }

    def _pressure(self, movements: Sequence[MarketMovementArtifact]) -> Mapping[str, Any]:
        points = [item for item in movements if item.movement_type in {"PRICE_MOVEMENT", "LINE_MOVEMENT", "IMPLIED_PROBABILITY_MOVEMENT"} and item.state == "AVAILABLE" and item.typed_value]
        signs = [_sign(item.typed_value.get("value_delta")) for item in points]
        nonzero = [item for item in signs if item]
        runs: List[int] = []
        current = 0
        previous = None
        for sign in nonzero:
            current = current + 1 if sign == previous else 1
            runs.append(current)
            previous = sign
        reversal = any(left != right for left, right in zip(nonzero, nonzero[1:]))
        return {
            "direction": "MIXED" if len(set(nonzero)) > 1 else "POSITIVE" if nonzero and nonzero[0] > 0 else "NEGATIVE" if nonzero else "NONE",
            "persistence": {"max_same_direction_run": max(runs) if runs else 0, "observed_direction_points": len(nonzero)},
            "breadth": len({item.provider for item in points if item.provider != "MULTI_PROVIDER"}),
            "velocity": [{"movement_id": item.movement_id, "value_per_hour": item.typed_value["value_delta"] / item.elapsed_hours, "unit": item.unit} for item in points if item.elapsed_hours],
            "line_change_presence": any(item.movement_type == "LINE_MOVEMENT" and _sign(item.typed_value.get("value_delta")) != 0 for item in points),
            "reversal_presence": reversal,
        }

    def _anomaly(self, movements: Sequence[MarketMovementArtifact]) -> Tuple[Mapping[str, Any], str]:
        flags: List[Mapping[str, Any]] = []
        ordered = sorted([item for item in movements if item.source_time_after], key=lambda item: (_source_time(item, "source_time_after"), item.movement_id))
        signs = [_sign(item.typed_value.get("value_delta")) for item in ordered if item.typed_value and item.movement_type in {"PRICE_MOVEMENT", "LINE_MOVEMENT", "IMPLIED_PROBABILITY_MOVEMENT"}]
        if any(left != right and left != 0 and right != 0 for left, right in zip(signs, signs[1:])):
            flags.append(self._flag("DIRECTION_REVERSAL", "adjacent accepted movement directions contain a non-zero sign reversal", ordered))
        aggregates = [item for item in movements if item.movement_type == "PROVIDER_AGGREGATE" and item.typed_value]
        if any(float(item.typed_value.get("iqr", 0)) > 0 or float(item.typed_value.get("mad", 0)) > 0 for item in aggregates):
            flags.append(self._flag("PROVIDER_DISPERSION", "eligible provider aggregate retains non-zero IQR or MAD", aggregates))
        if any(item.movement_type == "OFFICIAL_EXTERNAL_DIVERGENCE" and item.state == "AVAILABLE" for item in movements):
            flags.append(self._flag("OFFICIAL_EXTERNAL_DIVERGENCE", "approved official/external comparable divergence is present", [item for item in movements if item.movement_type == "OFFICIAL_EXTERNAL_DIVERGENCE"]))
        unique_snapshots = {ref["snapshot_id"] for item in movements for ref in item.snapshot_refs}
        if len(unique_snapshots) < 2:
            flags.append(self._flag("SPARSE_MARKET", "fewer than two movement source snapshots are available", movements))
        if any(item.state == "STALE" for item in movements):
            flags.append(self._flag("STALE_MARKET", "an upstream movement state is explicitly STALE", movements))
        if any(item.state == "CONFLICTED" for item in movements):
            flags.append(self._flag("CONFLICTED_MARKET", "an upstream movement state is explicitly CONFLICTED", movements))
        if any(flag["flag"] in {"CONFLICTED_MARKET"} for flag in flags):
            state = "CONFLICTED"
        elif len(unique_snapshots) < 2 and not any(flag["flag"] in {"DIRECTION_REVERSAL", "PROVIDER_DISPERSION", "OFFICIAL_EXTERNAL_DIVERGENCE"} for flag in flags):
            state = "INSUFFICIENT_DATA"
        elif len(flags) == 0:
            state = "NONE_OBSERVED"
        elif len(flags) == 1:
            state = "SIGNAL_PRESENT"
        else:
            state = "MULTIPLE_SIGNALS"
        return {"flags": flags, "approved_flag_set": sorted(APPROVED_FLAGS), "disabled_threshold_flags": sorted(DISABLED_FLAGS)}, state

    @staticmethod
    def _flag(flag: str, predicate: str, items: Sequence[MarketMovementArtifact]) -> Mapping[str, Any]:
        if flag not in APPROVED_FLAGS:
            raise MarketRiskInterpretationValidationError("FLAG_NOT_APPROVED", f"flag {flag} is not approved")
        return {"flag": flag, "predicate": predicate, "source_refs": sorted({item.source for item in items}), "movement_refs": sorted({item.movement_id for item in items}), "source_times": sorted({time for item in items for time in (item.source_time_before, item.source_time_after) if time}), "config_version": CONFIG_VERSION, "mapping_registry_version": MAPPING_REGISTRY_VERSION}


class MarketRiskInterpretationStore:
    """Append-only local V4-048 profile ledger."""

    def __init__(self):
        self._artifacts: Dict[str, MarketRiskInterpretationArtifact] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def artifacts(self) -> Tuple[MarketRiskInterpretationArtifact, ...]:
        return tuple(self._artifacts.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def append(self, artifact: MarketRiskInterpretationArtifact) -> str:
        if not isinstance(artifact, MarketRiskInterpretationArtifact):
            raise TypeError("MarketRiskInterpretationStore accepts V4-048 artifacts only")
        existing = self._artifacts.get(artifact.artifact_id)
        if existing is not None:
            if existing.to_dict() == artifact.to_dict():
                self._events.append({"sequence": len(self._events) + 1, "action": "DUPLICATE_NOOP", "artifact_id": artifact.artifact_id})
                return "DUPLICATE_NOOP"
            raise MarketRiskInterpretationValidationError("ARTIFACT_ID_REUSE", "risk interpretation artifact identity cannot be reused")
        if artifact.revision > 1 and not artifact.supersedes_artifact_id:
            raise MarketRiskInterpretationValidationError("SUPERSEDES_REQUIRED", "correction requires supersedes_artifact_id")
        if artifact.supersedes_artifact_id and artifact.supersedes_artifact_id not in self._artifacts:
            raise MarketRiskInterpretationValidationError("SUPERSEDES_NOT_FOUND", "superseded artifact is not present")
        self._artifacts[artifact.artifact_id] = artifact
        self._events.append({"sequence": len(self._events) + 1, "action": "APPEND", "artifact_id": artifact.artifact_id, "state": artifact.interpretation_state})
        return "APPEND"


__all__ = [
    "ARTIFACT_KIND",
    "CONFIG_VERSION",
    "CONTRACT_VERSION",
    "GENERATOR_VERSION",
    "MAPPING_REGISTRY_VERSION",
    "MarketRiskInterpretationArtifact",
    "MarketRiskInterpretationEngine",
    "MarketRiskInterpretationResult",
    "MarketRiskInterpretationStore",
    "MarketRiskInterpretationValidationError",
]
