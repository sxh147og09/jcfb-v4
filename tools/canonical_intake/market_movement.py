"""V4-047 same-source market movement and divergence features.

The engine consumes only accepted V4-046 MarketIntelligenceArtifact objects.
It keeps line and price movement separate, uses source availability time for
ordering, and emits descriptive market observables only.  It does not create
heat, pressure, trap-risk, bookmaker-intent, prediction, or score output.
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tools.migration_harness.common import sha256_json

from .market_intelligence import MarketIntelligenceArtifact


CONTRACT_VERSION = "market-movement@1.0.0"
CONFIG_VERSION = "market-intelligence-config@1.0.0"
MAPPING_REGISTRY_VERSION = "market-intelligence-mapping@1.0.0"
GENERATOR_VERSION = "v4-047-market-movement@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_MARKET_MOVEMENT_ARTIFACT"
ARTIFACT_NAMESPACE = uuid.UUID("9ab4cd18-1b0f-5725-9e33-8fc92db3d76c")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UNKNOWN_TIME_STATES = frozenset({"UNKNOWN", "CONFLICTED"})
ONE_X_TWO_MARKETS = frozenset({"SPF", "EUROPEAN_1X2"})
LINE_MARKETS = frozenset({"RQSPF", "ASIAN_HANDICAP", "OVER_UNDER"})
PRICE_SELECTIONS = {
    "SPF": ("home", "draw", "away"),
    "EUROPEAN_1X2": ("home", "draw", "away"),
    "RQSPF": ("home", "draw", "away"),
    "ASIAN_HANDICAP": ("home", "away"),
    "OVER_UNDER": ("over", "under"),
}


class MarketMovementValidationError(ValueError):
    """A V4-047 series or semantic comparison is unsafe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketMovementValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise MarketMovementValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MarketMovementValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketMovementValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} must be timezone-aware")
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


def _artifact_value(artifact: MarketIntelligenceArtifact) -> Tuple[Mapping[str, float], Union[float, str]]:
    typed = artifact.typed_value
    if not isinstance(typed, Mapping):
        raise MarketMovementValidationError("TYPED_VALUE_MISSING", "AVAILABLE V4-046 artifact has no typed value")
    if "prices" in typed:
        prices = typed["prices"]
    elif "payload" in typed and isinstance(typed["payload"], Mapping):
        prices = {key: value for key, value in typed["payload"].items() if key != "official_handicap"}
    else:
        raise MarketMovementValidationError("PRICE_PAYLOAD_MISSING", "V4-046 artifact has no price payload")
    if not isinstance(prices, Mapping) or not prices:
        raise MarketMovementValidationError("PRICE_PAYLOAD_INVALID", "price payload must be a non-empty object")
    result: Dict[str, float] = {}
    for key, value in prices.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
            raise MarketMovementValidationError("PRICE_PAYLOAD_INVALID", f"price {key} must be finite and positive")
        result[str(key)] = float(value)
    return result, artifact.semantic_line


def _source_time(artifact: MarketIntelligenceArtifact) -> datetime:
    if artifact.source_timestamp.upper() in UNKNOWN_TIME_STATES:
        raise MarketMovementValidationError("SOURCE_TIME_UNRESOLVED", "unknown or conflicted source time is blocked")
    return _timestamp(artifact.source_timestamp, "source_timestamp")


def _selection_keys(market: str, prices: Mapping[str, float]) -> Tuple[str, ...]:
    expected = PRICE_SELECTIONS.get(market)
    if expected is None:
        raise MarketMovementValidationError("MARKET_UNSUPPORTED", f"market {market} is not approved for V4-047")
    if set(prices) != set(expected):
        raise MarketMovementValidationError("PRICE_SHAPE_INVALID", f"{market} price selections do not match the approved market shape")
    return expected


def _implied(prices: Mapping[str, float], market: str) -> Mapping[str, float]:
    _selection_keys(market, prices)
    raw = {key: 1.0 / float(prices[key]) for key in prices}
    total = sum(raw.values())
    if total <= 0:
        raise MarketMovementValidationError("IMPLIED_PROBABILITY_INVALID", "implied probability denominator must be positive")
    return {key: raw[key] / total for key in raw}


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def _iqr(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        lower, upper = ordered[:midpoint], ordered[midpoint + 1 :]
    else:
        lower, upper = ordered[:midpoint], ordered[midpoint:]
    return float(statistics.median(upper) - statistics.median(lower))


def _mad(values: Sequence[float]) -> float:
    center = _median(values)
    return _median([abs(value - center) for value in values])


@dataclass(frozen=True)
class MarketMovementArtifact:
    movement_id: str
    artifact_kind: str
    contract_version: str
    canonical_match_id: str
    market: str
    movement_type: str
    selection: str
    provider: str
    source: str
    source_is_official: Optional[bool]
    semantic_line_before: Union[float, str, None]
    semantic_line_after: Union[float, str, None]
    line_before: Union[float, str, None]
    line_after: Union[float, str, None]
    price_before: Optional[float]
    price_after: Optional[float]
    elapsed_hours: Optional[float]
    source_time_before: Optional[str]
    source_time_after: Optional[str]
    prediction_cutoff_at: str
    kickoff_at: str
    state: str
    typed_value: Optional[Mapping[str, Any]]
    unit: str
    reason_code: str
    reason_detail: str
    snapshot_refs: Tuple[Mapping[str, Any], ...]
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
    supersedes_movement_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "movement_id": self.movement_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "canonical_match_id": self.canonical_match_id,
            "market": self.market,
            "movement_type": self.movement_type,
            "selection": self.selection,
            "provider": self.provider,
            "source": self.source,
            "source_is_official": self.source_is_official,
            "semantic_line_before": self.semantic_line_before,
            "semantic_line_after": self.semantic_line_after,
            "line_before": self.line_before,
            "line_after": self.line_after,
            "price_before": self.price_before,
            "price_after": self.price_after,
            "elapsed_hours": self.elapsed_hours,
            "source_time_before": self.source_time_before,
            "source_time_after": self.source_time_after,
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "state": self.state,
            "typed_value": _thaw(self.typed_value) if self.typed_value is not None else None,
            "unit": self.unit,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "snapshot_refs": _thaw(self.snapshot_refs),
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
            "supersedes_movement_id": self.supersedes_movement_id,
        }


@dataclass(frozen=True)
class MarketMovementResult:
    accepted: bool
    action: str
    artifacts: Tuple[MarketMovementArtifact, ...]
    error_code: Optional[str] = None


class MarketMovementEngine:
    """Calculate only approved V4-047 market observables."""

    def __init__(self, *, config: Optional[Mapping[str, Any]] = None, mapping: Optional[Mapping[str, Any]] = None):
        self.config = dict(config or {})
        self.mapping = dict(mapping or {})
        self._validate_governance()

    @classmethod
    def from_repo_root(cls, root: Path) -> "MarketMovementEngine":
        import json

        config = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_CONFIG.json").read_text(encoding="utf-8"))
        mapping = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_MAPPING.json").read_text(encoding="utf-8"))
        return cls(config=config, mapping=mapping)

    def _validate_governance(self) -> None:
        if self.config:
            if self.config.get("config_version") != CONFIG_VERSION:
                raise MarketMovementValidationError("CONFIG_VERSION_INVALID", "V4-047 config version is not approved")
            if self.config.get("movement_policy", {}).get("velocity_formula") != "value_delta_divided_by_elapsed_hours":
                raise MarketMovementValidationError("VELOCITY_POLICY_INVALID", "V4-047 velocity formula drifted")
            if self.config.get("movement_policy", {}).get("non_positive_elapsed_time") != "BLOCKED":
                raise MarketMovementValidationError("TIME_POLICY_INVALID", "non-positive elapsed time must block")
            if self.config.get("provider_policy", {}).get("aggregation_policy") != "EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION":
                raise MarketMovementValidationError("PROVIDER_POLICY_INVALID", "provider aggregation policy drifted")
        if self.mapping and self.mapping.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
            raise MarketMovementValidationError("MAPPING_VERSION_INVALID", "V4-047 mapping version is not approved")

    def compute_pair(self, before: MarketIntelligenceArtifact, after: MarketIntelligenceArtifact, prediction_cutoff_at: Any, kickoff_at: Any, *, movement_type: str = "PRICE_MOVEMENT") -> MarketMovementResult:
        try:
            cutoff = _timestamp(prediction_cutoff_at, "prediction_cutoff_at")
            kickoff = _timestamp(kickoff_at, "kickoff_at")
            self._validate_pair(before, after, cutoff, kickoff, movement_type)
            before_prices, before_line = _artifact_value(before)
            after_prices, after_line = _artifact_value(after)
            selections = _selection_keys(before.market, before_prices)
            if movement_type == "LINE_MOVEMENT":
                if before.market not in LINE_MARKETS:
                    raise MarketMovementValidationError("LINE_MOVEMENT_NOT_APPLICABLE", "line movement is only approved for line markets")
                return MarketMovementResult(True, "COMPUTED", (self._build_pair(before, after, cutoff, kickoff, movement_type, "MARKET_LINE", float(before_line) if isinstance(before_line, (int, float)) else before_line, float(after_line) if isinstance(after_line, (int, float)) else after_line, None, None, float(after_line) - float(before_line), "line_units"),))
            if movement_type == "IMPLIED_PROBABILITY_MOVEMENT":
                if before.market not in ONE_X_TWO_MARKETS:
                    raise MarketMovementValidationError("IMPLIED_PROBABILITY_NOT_APPLICABLE", "market implied probability is only approved for 1X2 markets")
                before_values, after_values = _implied(before_prices, before.market), _implied(after_prices, after.market)
                return MarketMovementResult(True, "COMPUTED", tuple(self._build_pair(before, after, cutoff, kickoff, movement_type, selection, before_line, after_line, before_prices[selection], after_prices[selection], after_values[selection] - before_values[selection], "probability_points", typed_values_before=before_values[selection], typed_values_after=after_values[selection]) for selection in selections))
            if movement_type != "PRICE_MOVEMENT":
                raise MarketMovementValidationError("MOVEMENT_TYPE_INVALID", "movement_type is not approved")
            if before.semantic_line != after.semantic_line:
                raise MarketMovementValidationError("SEMANTIC_LINE_CONFLICT", "price movement requires the same semantic line")
            return MarketMovementResult(True, "COMPUTED", tuple(self._build_pair(before, after, cutoff, kickoff, movement_type, selection, before_line, after_line, before_prices[selection], after_prices[selection], after_prices[selection] - before_prices[selection], "decimal_price") for selection in selections))
        except MarketMovementValidationError as exc:
            return MarketMovementResult(False, "BLOCKED", (), exc.code)

    def compute_series(self, artifacts: Sequence[MarketIntelligenceArtifact], prediction_cutoff_at: Any, kickoff_at: Any, *, movement_type: str = "PRICE_MOVEMENT") -> MarketMovementResult:
        try:
            if not artifacts:
                raise MarketMovementValidationError("SERIES_EMPTY", "same-source series cannot be empty")
            self._validate_series_scope(artifacts)
            ordered = sorted(artifacts, key=lambda item: (_source_time(item), _timestamp(item.captured_at, "captured_at"), item.snapshot_ref["snapshot_hash"]))
            output: List[MarketMovementArtifact] = []
            for before, after in zip(ordered, ordered[1:]):
                pair = self.compute_pair(before, after, prediction_cutoff_at, kickoff_at, movement_type=movement_type)
                if not pair.accepted:
                    return pair
                output.extend(pair.artifacts)
            return MarketMovementResult(True, "COMPUTED", tuple(output))
        except MarketMovementValidationError as exc:
            return MarketMovementResult(False, "BLOCKED", (), exc.code)

    def compute_acceleration(self, artifacts: Sequence[MarketIntelligenceArtifact], prediction_cutoff_at: Any, kickoff_at: Any, *, selection: str, value_kind: str = "price") -> MarketMovementResult:
        try:
            if len(artifacts) < 3:
                return MarketMovementResult(True, "INSUFFICIENT_SERIES", (self._insufficient_acceleration(artifacts, prediction_cutoff_at, kickoff_at, selection, value_kind),))
            self._validate_series_scope(artifacts)
            ordered = sorted(artifacts, key=lambda item: (_source_time(item), _timestamp(item.captured_at, "captured_at"), item.snapshot_ref["snapshot_hash"]))
            pairs: List[Tuple[MarketIntelligenceArtifact, MarketIntelligenceArtifact, float, float]] = []
            for before, after in zip(ordered, ordered[1:]):
                pair_type = "LINE_MOVEMENT" if value_kind == "line" else "PRICE_MOVEMENT"
                self._validate_pair(before, after, _timestamp(prediction_cutoff_at, "prediction_cutoff_at"), _timestamp(kickoff_at, "kickoff_at"), pair_type)
                before_prices, _ = _artifact_value(before)
                after_prices, _ = _artifact_value(after)
                if selection not in before_prices or selection not in after_prices:
                    raise MarketMovementValidationError("SELECTION_INVALID", "selection is not present in the series")
                elapsed = (_source_time(after) - _source_time(before)).total_seconds() / 3600
                before_value = before_prices[selection]
                after_value = after_prices[selection]
                if value_kind == "implied_probability":
                    before_value = _implied(before_prices, before.market)[selection]
                    after_value = _implied(after_prices, after.market)[selection]
                elif value_kind == "line":
                    before_value = float(before.semantic_line)
                    after_value = float(after.semantic_line)
                pairs.append((before, after, (after_value - before_value) / elapsed, elapsed))
            prior, current = pairs[-2], pairs[-1]
            between_velocity_hours = (_source_time(current[1]) - _source_time(prior[1])).total_seconds() / 3600
            if between_velocity_hours <= 0:
                raise MarketMovementValidationError("NON_POSITIVE_ELAPSED_TIME", "acceleration interval must be positive")
            acceleration = (current[2] - prior[2]) / between_velocity_hours
            unit = {"price": "decimal_price_per_hour_squared", "implied_probability": "probability_points_per_hour_squared", "line": "line_units_per_hour_squared"}.get(value_kind)
            if unit is None:
                raise MarketMovementValidationError("VALUE_KIND_INVALID", "acceleration value_kind is not approved")
            artifact = self._build_pair(current[0], current[1], _timestamp(prediction_cutoff_at, "prediction_cutoff_at"), _timestamp(kickoff_at, "kickoff_at"), "ACCELERATION", selection, current[0].semantic_line, current[1].semantic_line, current[2], prior[2], acceleration, unit, elapsed_hours=between_velocity_hours, typed_extra={"minimum_valid_snapshots": 3, "velocity_before": prior[2], "velocity_after": current[2]})
            return MarketMovementResult(True, "COMPUTED", (artifact,))
        except MarketMovementValidationError as exc:
            return MarketMovementResult(False, "BLOCKED", (), exc.code)

    def aggregate_providers(self, artifacts: Sequence[MarketIntelligenceArtifact], prediction_cutoff_at: Any, kickoff_at: Any, *, selection: str) -> MarketMovementResult:
        try:
            if not artifacts:
                raise MarketMovementValidationError("SERIES_EMPTY", "provider aggregation cannot be empty")
            self._validate_common_identity(artifacts)
            cutoff = _timestamp(prediction_cutoff_at, "prediction_cutoff_at")
            kickoff = _timestamp(kickoff_at, "kickoff_at")
            latest: Dict[str, MarketIntelligenceArtifact] = {}
            excluded = 0
            for item in artifacts:
                if item.state != "AVAILABLE" or item.source_timestamp.upper() in UNKNOWN_TIME_STATES or _source_time(item) > cutoff:
                    excluded += 1
                    continue
                prices, _ = _artifact_value(item)
                if selection not in prices:
                    raise MarketMovementValidationError("SELECTION_INVALID", "selection is not present in provider artifacts")
                prior = latest.get(item.provider)
                if prior is None or (_source_time(item), item.snapshot_ref["snapshot_hash"]) > (_source_time(prior), prior.snapshot_ref["snapshot_hash"]):
                    latest[item.provider] = item
            if not latest:
                raise MarketMovementValidationError("NO_ELIGIBLE_PROVIDER", "no eligible provider observation remains")
            values = [_artifact_value(item)[0][selection] for item in latest.values()]
            typed = {"eligible_provider_count": len(values), "excluded_provider_count": excluded, "median": _median(values), "iqr": _iqr(values), "mad": _mad(values), "aggregation_policy": "EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION", "source_refs": [item.source_reference for item in latest.values()]}
            return MarketMovementResult(True, "COMPUTED", (self._build_aggregate(next(iter(latest.values())), cutoff, kickoff, selection, typed, tuple(latest.values())),))
        except MarketMovementValidationError as exc:
            return MarketMovementResult(False, "BLOCKED", (), exc.code)

    def compare_official_external(self, official: MarketIntelligenceArtifact, external: MarketIntelligenceArtifact, prediction_cutoff_at: Any, kickoff_at: Any) -> MarketMovementResult:
        try:
            cutoff = _timestamp(prediction_cutoff_at, "prediction_cutoff_at")
            kickoff = _timestamp(kickoff_at, "kickoff_at")
            if official.canonical_match_id != external.canonical_match_id:
                raise MarketMovementValidationError("MATCH_IDENTITY_CONFLICT", "divergence inputs must share canonical match_id")
            if official.state != "AVAILABLE" or external.state != "AVAILABLE":
                raise MarketMovementValidationError("NON_CONSUMABLE_INPUT", "divergence requires available V4-046 inputs")
            if official.source_is_official is not True or external.source_is_official is not False:
                raise MarketMovementValidationError("SOURCE_ROLE_INVALID", "divergence requires one official and one external artifact")
            if official.market == "SPF" and external.market == "EUROPEAN_1X2":
                official_prices, official_line = _artifact_value(official)
                external_prices, external_line = _artifact_value(external)
                if _source_time(official) != _source_time(external):
                    raise MarketMovementValidationError("SOURCE_TIME_NOT_ALIGNED", "numeric divergence requires aligned source times")
                official_values, external_values = _implied(official_prices, official.market), _implied(external_prices, external.market)
                artifacts = tuple(self._build_pair(official, external, cutoff, kickoff, "OFFICIAL_EXTERNAL_DIVERGENCE", selection, official_line, external_line, official_values[selection], external_values[selection], external_values[selection] - official_values[selection], "probability_points", provider="OFFICIAL_EXTERNAL_COMPARISON", source="OFFICIAL_SPF_TO_EXTERNAL_EUROPEAN_1X2", source_is_official=None, typed_extra={"semantic_mapping": "OFFICIAL_SPF_TO_EXTERNAL_EUROPEAN_1X2_MARKET_IMPLIED_PROBABILITY", "official_snapshot_ref": official.snapshot_ref, "external_snapshot_ref": external.snapshot_ref}) for selection in ("home", "draw", "away"))
                return MarketMovementResult(True, "COMPUTED", artifacts)
            relation = self._not_comparable_relation(official, external, cutoff, kickoff)
            return MarketMovementResult(True, "NOT_COMPARABLE", (relation,))
        except MarketMovementValidationError as exc:
            return MarketMovementResult(False, "BLOCKED", (), exc.code)

    def _validate_pair(self, before: MarketIntelligenceArtifact, after: MarketIntelligenceArtifact, cutoff: datetime, kickoff: datetime, movement_type: str) -> None:
        self._validate_pair_identity(before, after)
        if before.contract_version != "market-intelligence-feature@1.0.0" or after.contract_version != "market-intelligence-feature@1.0.0":
            raise MarketMovementValidationError("UPSTREAM_CONTRACT_INVALID", "V4-047 requires V4-046 feature artifacts")
        if before.state != "AVAILABLE" or after.state != "AVAILABLE":
            raise MarketMovementValidationError("NON_CONSUMABLE_INPUT", "non-AVAILABLE V4-046 state cannot become movement")
        before_time, after_time = _source_time(before), _source_time(after)
        if before_time > cutoff or after_time > cutoff:
            raise MarketMovementValidationError("POST_CUTOFF_INPUT", "movement cannot use post-cutoff input")
        if cutoff >= kickoff:
            raise MarketMovementValidationError("CUTOFF_NOT_BEFORE_KICKOFF", "cutoff must precede kickoff")
        if after_time <= before_time:
            raise MarketMovementValidationError("NON_POSITIVE_ELAPSED_TIME", "movement requires a positive source-time interval")
        if movement_type not in {"PRICE_MOVEMENT", "LINE_MOVEMENT", "IMPLIED_PROBABILITY_MOVEMENT"}:
            raise MarketMovementValidationError("MOVEMENT_TYPE_INVALID", "movement_type is not approved")

    @staticmethod
    def _validate_pair_identity(before: MarketIntelligenceArtifact, after: MarketIntelligenceArtifact) -> None:
        if before.canonical_match_id != after.canonical_match_id:
            raise MarketMovementValidationError("MATCH_IDENTITY_CONFLICT", "movement inputs must share canonical match_id")
        if before.market != after.market:
            raise MarketMovementValidationError("MARKET_SCOPE_CONFLICT", "movement inputs must share market")
        if before.provider != after.provider or before.source != after.source or before.source_is_official != after.source_is_official:
            raise MarketMovementValidationError("SOURCE_SCOPE_CONFLICT", "movement inputs must share provider/source role")

    @staticmethod
    def _validate_common_identity(artifacts: Sequence[MarketIntelligenceArtifact]) -> None:
        first = artifacts[0]
        for item in artifacts[1:]:
            if item.canonical_match_id != first.canonical_match_id or item.market != first.market or item.source_is_official != first.source_is_official:
                raise MarketMovementValidationError("SERIES_SCOPE_CONFLICT", "series must share canonical match, market, and role")

    def _validate_series_scope(self, artifacts: Sequence[MarketIntelligenceArtifact]) -> None:
        self._validate_common_identity(artifacts)
        first = artifacts[0]
        if any(item.provider != first.provider or item.source != first.source for item in artifacts[1:]):
            raise MarketMovementValidationError("SOURCE_SCOPE_CONFLICT", "different providers cannot form one movement series")

    def _build_pair(self, before: MarketIntelligenceArtifact, after: MarketIntelligenceArtifact, cutoff: datetime, kickoff: datetime, movement_type: str, selection: str, line_before: Union[float, str, None], line_after: Union[float, str, None], price_before: Optional[float], price_after: Optional[float], value_delta: float, unit: str, *, provider: Optional[str] = None, source: Optional[str] = None, source_is_official: Optional[bool] = None, elapsed_hours: Optional[float] = None, typed_values_before: Any = None, typed_values_after: Any = None, typed_extra: Optional[Mapping[str, Any]] = None) -> MarketMovementArtifact:
        before_time, after_time = _source_time(before), _source_time(after)
        elapsed = elapsed_hours if elapsed_hours is not None else (after_time - before_time).total_seconds() / 3600
        if movement_type == "OFFICIAL_EXTERNAL_DIVERGENCE":
            elapsed = None
        elif elapsed <= 0:
            raise MarketMovementValidationError("NON_POSITIVE_ELAPSED_TIME", "movement elapsed time must be positive")
        effective_source_role = None if movement_type == "OFFICIAL_EXTERNAL_DIVERGENCE" else before.source_is_official if source_is_official is None else source_is_official
        typed = {"selection": selection, "value_before": price_before if typed_values_before is None else typed_values_before, "value_after": price_after if typed_values_after is None else typed_values_after, "value_delta": value_delta}
        if typed_extra:
            typed.update(dict(typed_extra))
        typed_plain = _thaw(typed)
        snapshot_refs = ({"snapshot_id": before.snapshot_ref["snapshot_id"], "snapshot_hash": before.snapshot_ref["snapshot_hash"]}, {"snapshot_id": after.snapshot_ref["snapshot_id"], "snapshot_hash": after.snapshot_ref["snapshot_hash"]})
        input_hash = sha256_json({"contract_version": CONTRACT_VERSION, "movement_type": movement_type, "selection": selection, "before": snapshot_refs[0], "after": snapshot_refs[1], "match_id": before.canonical_match_id, "market": before.market, "provider": provider or before.provider, "source": source or before.source, "source_is_official": effective_source_role, "source_times": [before.source_timestamp, after.source_timestamp], "cutoff": _iso(cutoff), "kickoff": _iso(kickoff), "semantic_lines": [line_before, line_after], "config_version": CONFIG_VERSION, "mapping_registry_version": MAPPING_REGISTRY_VERSION})
        payload_hash = sha256_json({"movement_type": movement_type, "selection": selection, "line_before": line_before, "line_after": line_after, "typed_value": typed_plain, "unit": unit})
        provenance_hash = sha256_json({"source_refs": [before.source_reference, after.source_reference], "snapshot_refs": snapshot_refs, "basis_refs": [*before.basis_refs, *after.basis_refs], "source_times": [before.source_timestamp, after.source_timestamp]})
        movement_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"movement|{input_hash}|{payload_hash}"))
        quality = {"coverage": "COMPLETE", "verification": "VERIFIED", "freshness": "CURRENT", "completeness": "COMPLETE", "conflict": "NONE", "provenance": "RESOLVED"}
        output_hash = sha256_json({"movement_id": movement_id, "movement_type": movement_type, "state": "AVAILABLE", "typed_value": typed_plain, "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash, "snapshot_refs": snapshot_refs})
        return MarketMovementArtifact(movement_id, ARTIFACT_KIND, CONTRACT_VERSION, before.canonical_match_id, before.market, movement_type, selection, provider or before.provider, source or before.source, effective_source_role, line_before, line_after, line_before, line_after, price_before, price_after, elapsed, before.source_timestamp, after.source_timestamp, _iso(cutoff), _iso(kickoff), "AVAILABLE", _freeze(typed_plain), unit, "NOT_APPLICABLE", "movement calculated from adjacent eligible same-source artifacts", snapshot_refs, tuple([*before.basis_refs, *after.basis_refs]), _freeze(quality), GENERATOR_VERSION, "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), CONFIG_VERSION, self.config.get("config_hash", sha256_json(self.config)), MAPPING_REGISTRY_VERSION, input_hash, payload_hash, provenance_hash, output_hash)

    def _build_aggregate(self, seed: MarketIntelligenceArtifact, cutoff: datetime, kickoff: datetime, selection: str, typed: Mapping[str, Any], items: Sequence[MarketIntelligenceArtifact]) -> MarketMovementArtifact:
        refs = tuple({"snapshot_id": item.snapshot_ref["snapshot_id"], "snapshot_hash": item.snapshot_ref["snapshot_hash"]} for item in items)
        input_hash = sha256_json({"movement_type": "PROVIDER_AGGREGATE", "match_id": seed.canonical_match_id, "market": seed.market, "selection": selection, "provider_refs": refs, "cutoff": _iso(cutoff), "kickoff": _iso(kickoff), "config_version": CONFIG_VERSION, "mapping_registry_version": MAPPING_REGISTRY_VERSION})
        payload_hash = sha256_json(typed)
        provenance_hash = sha256_json({"refs": refs, "source_refs": [item.source_reference for item in items]})
        movement_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"aggregate|{input_hash}|{payload_hash}"))
        output_hash = sha256_json({"movement_id": movement_id, "movement_type": "PROVIDER_AGGREGATE", "typed_value": typed, "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash})
        quality = {"coverage": "COMPLETE", "verification": "VERIFIED", "freshness": "CURRENT", "completeness": "COMPLETE", "conflict": "NONE", "provenance": "RESOLVED"}
        return MarketMovementArtifact(movement_id, ARTIFACT_KIND, CONTRACT_VERSION, seed.canonical_match_id, seed.market, "PROVIDER_AGGREGATE", selection, "MULTI_PROVIDER", "MULTI_PROVIDER", None, seed.semantic_line, seed.semantic_line, seed.semantic_line, seed.semantic_line, None, None, None, None, None, _iso(cutoff), _iso(kickoff), "AVAILABLE", _freeze(typed), "market_native_unit", "NOT_APPLICABLE", "equal eligible provider descriptive aggregate", refs, tuple(ref["snapshot_id"] for ref in refs), _freeze(quality), GENERATOR_VERSION, "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), CONFIG_VERSION, self.config.get("config_hash", sha256_json(self.config)), MAPPING_REGISTRY_VERSION, input_hash, payload_hash, provenance_hash, output_hash)

    def _not_comparable_relation(self, official: MarketIntelligenceArtifact, external: MarketIntelligenceArtifact, cutoff: datetime, kickoff: datetime) -> MarketMovementArtifact:
        typed = {"relation": "NOT_COMPARABLE", "official_market": official.market, "external_market": external.market, "official_snapshot_ref": _thaw(official.snapshot_ref), "external_snapshot_ref": _thaw(external.snapshot_ref), "reason": "no approved numeric semantic mapping"}
        input_hash = sha256_json({"movement_type": "OFFICIAL_EXTERNAL_DIVERGENCE", "state": "NOT_COMPARABLE", "official": _thaw(official.snapshot_ref), "external": _thaw(external.snapshot_ref), "mapping": "NOT_COMPARABLE"})
        payload_hash = sha256_json(typed)
        provenance_hash = sha256_json({"official_source": official.source_reference, "external_source": external.source_reference})
        movement_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"not-comparable|{input_hash}|{payload_hash}"))
        output_hash = sha256_json({"movement_id": movement_id, "state": "NOT_COMPARABLE", "typed_value": typed, "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash})
        quality = {"coverage": "PARTIAL", "verification": "VERIFIED", "freshness": "CURRENT", "completeness": "PARTIAL", "conflict": "UNKNOWN", "provenance": "RESOLVED"}
        refs = ({"snapshot_id": official.snapshot_ref["snapshot_id"], "snapshot_hash": official.snapshot_ref["snapshot_hash"]}, {"snapshot_id": external.snapshot_ref["snapshot_id"], "snapshot_hash": external.snapshot_ref["snapshot_hash"]})
        return MarketMovementArtifact(movement_id, ARTIFACT_KIND, CONTRACT_VERSION, official.canonical_match_id, f"{official.market}__{external.market}", "OFFICIAL_EXTERNAL_DIVERGENCE", "MARKET_RELATION", "OFFICIAL_EXTERNAL_COMPARISON", "OFFICIAL_EXTERNAL_COMPARISON", None, official.semantic_line, external.semantic_line, official.semantic_line, external.semantic_line, None, None, None, official.source_timestamp, external.source_timestamp, _iso(cutoff), _iso(kickoff), "NOT_COMPARABLE", _freeze(typed), "structured_relation", "NOT_COMPARABLE_MARKET_SEMANTICS", "official and external markets have no approved numeric semantic mapping", refs, (official.snapshot_ref["snapshot_id"], external.snapshot_ref["snapshot_id"]), _freeze(quality), GENERATOR_VERSION, "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), CONFIG_VERSION, self.config.get("config_hash", sha256_json(self.config)), MAPPING_REGISTRY_VERSION, input_hash, payload_hash, provenance_hash, output_hash)

    def _insufficient_acceleration(self, artifacts: Sequence[MarketIntelligenceArtifact], cutoff: Any, kickoff: Any, selection: str, value_kind: str) -> MarketMovementArtifact:
        seed = artifacts[0] if artifacts else None
        cutoff_dt, kickoff_dt = _timestamp(cutoff, "prediction_cutoff_at"), _timestamp(kickoff, "kickoff_at")
        if seed is None:
            raise MarketMovementValidationError("SERIES_EMPTY", "insufficient acceleration requires at least one artifact")
        refs = tuple({"snapshot_id": item.snapshot_ref["snapshot_id"], "snapshot_hash": item.snapshot_ref["snapshot_hash"]} for item in artifacts)
        typed = {"selection": selection, "value_kind": value_kind, "minimum_valid_snapshots": 3, "observed_snapshot_count": len(artifacts)}
        input_hash = sha256_json({"movement_type": "ACCELERATION", "state": "UNKNOWN", "reason_code": "INSUFFICIENT_SERIES", "refs": refs, "selection": selection, "value_kind": value_kind})
        payload_hash = sha256_json(typed)
        provenance_hash = sha256_json({"refs": refs})
        movement_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"insufficient-acceleration|{input_hash}|{payload_hash}"))
        output_hash = sha256_json({"movement_id": movement_id, "state": "UNKNOWN", "input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash})
        quality = {"coverage": "PARTIAL", "verification": "PARTIAL", "freshness": "UNKNOWN", "completeness": "PARTIAL", "conflict": "UNKNOWN", "provenance": "RESOLVED"}
        return MarketMovementArtifact(movement_id, ARTIFACT_KIND, CONTRACT_VERSION, seed.canonical_match_id, seed.market, "ACCELERATION", selection, seed.provider, seed.source, seed.source_is_official, seed.semantic_line, seed.semantic_line, seed.semantic_line, seed.semantic_line, None, None, None, None, None, _iso(cutoff_dt), _iso(kickoff_dt), "UNKNOWN", _freeze(typed), "market_native_unit_per_hour_squared", "INSUFFICIENT_SERIES", "at least three consecutive valid same-source snapshots are required", refs, tuple(ref["snapshot_id"] for ref in refs), _freeze(quality), GENERATOR_VERSION, "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), CONFIG_VERSION, self.config.get("config_hash", sha256_json(self.config)), MAPPING_REGISTRY_VERSION, input_hash, payload_hash, provenance_hash, output_hash)


class MarketMovementStore:
    """Append-only local V4-047 artifact ledger."""

    def __init__(self):
        self._artifacts: Dict[str, MarketMovementArtifact] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def artifacts(self) -> Tuple[MarketMovementArtifact, ...]:
        return tuple(self._artifacts.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def append(self, artifact: MarketMovementArtifact) -> str:
        if not isinstance(artifact, MarketMovementArtifact):
            raise TypeError("MarketMovementStore accepts MarketMovementArtifact only")
        existing = self._artifacts.get(artifact.movement_id)
        if existing is not None:
            if existing.to_dict() == artifact.to_dict():
                self._events.append({"sequence": len(self._events) + 1, "action": "DUPLICATE_NOOP", "movement_id": artifact.movement_id})
                return "DUPLICATE_NOOP"
            raise MarketMovementValidationError("MOVEMENT_ID_REUSE", "movement identity cannot be reused")
        if artifact.revision > 1 and not artifact.supersedes_movement_id:
            raise MarketMovementValidationError("SUPERSEDES_REQUIRED", "revisions require supersedes_movement_id")
        if artifact.supersedes_movement_id and artifact.supersedes_movement_id not in self._artifacts:
            raise MarketMovementValidationError("SUPERSEDES_NOT_FOUND", "superseded movement is not present")
        self._artifacts[artifact.movement_id] = artifact
        self._events.append({"sequence": len(self._events) + 1, "action": "APPEND", "movement_id": artifact.movement_id, "state": artifact.state})
        return "APPEND"


__all__ = [
    "ARTIFACT_KIND",
    "CONFIG_VERSION",
    "CONTRACT_VERSION",
    "GENERATOR_VERSION",
    "MAPPING_REGISTRY_VERSION",
    "MarketMovementArtifact",
    "MarketMovementEngine",
    "MarketMovementResult",
    "MarketMovementStore",
    "MarketMovementValidationError",
]
