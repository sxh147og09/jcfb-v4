"""V4-028 typed external European 1X2 intake.

This module is a local, in-memory, no-write boundary.  It validates external
European 1X2 observations, binds every
accepted snapshot to a resolved V4-020 canonical match identity, and keeps
corrections append-only.  It never populates the official lottery odds
objects and it does not perform cutoff admission or downstream market
intelligence.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore, IdentityValidationError, _iso, _parse_timestamp


CONTRACT_VERSION = "external-market-snapshot@1.0.0"
SNAPSHOT_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
SNAPSHOT_KINDS = frozenset({"OPENING", "INTERMEDIATE", "CURRENT", "LATEST", "FINAL", "CORRECTION"})
SOURCE_TYPES = frozenset({"EXTERNAL_FEED", "EXTERNAL_SCREENSHOT"})
SOURCE_TIME_STATES = frozenset({"UNKNOWN", "CONFLICTED"})
LIQUIDITY_STATES = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
OFFICIAL_FIELDS = frozenset({"spf", "rqspf", "total_goals", "exact_score", "half_full", "official_handicap"})


class ExternalMarket(str, Enum):
    EUROPEAN_1X2 = "EUROPEAN_1X2"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    OVER_UNDER = "OVER_UNDER"


class ExternalMarketStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    BLOCKED = "BLOCKED"


NON_AVAILABLE_STATUSES = frozenset(item for item in ExternalMarketStatus if item != ExternalMarketStatus.AVAILABLE)
LINE_STATES = frozenset({"UNKNOWN", "CONFLICTED"})
PRICE_LABELS = {
    ExternalMarket.EUROPEAN_1X2: ("home", "draw", "away"),
    ExternalMarket.ASIAN_HANDICAP: ("home", "away"),
    ExternalMarket.OVER_UNDER: ("over", "under"),
}


class ExternalMarketValidationError(ValueError):
    """An external market observation cannot be represented safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalMarketValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise ExternalMarketValidationError("IDENTITY_REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _hash(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not HASH_RE.fullmatch(result):
        raise ExternalMarketValidationError("HASH_INVALID", f"{field_name} must be sha256:<64 lowercase hex>")
    return result


def _timestamp(value: Any, field_name: str) -> datetime:
    try:
        parsed = _parse_timestamp(value, field_name)
    except IdentityValidationError as exc:
        raise ExternalMarketValidationError(exc.code, exc.message) from exc
    assert parsed is not None
    return parsed


def _source_time(value: Any) -> str:
    if isinstance(value, str) and value.strip().upper() in SOURCE_TIME_STATES:
        return value.strip().upper()
    return _iso(_timestamp(value, "source_timestamp"))


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).strip().casefold())


def _find_forbidden(value: Any, path: str = "snapshot") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in OFFICIAL_FIELDS or normalized.startswith("official_"):
                return f"{path}.{key}"
            if normalized in {"prediction", "recommendation", "model", "model_interpretation", "modelinterpretation", "engine", "engine_output", "engineoutput", "score_engine", "scoreengine", "risk", "probability"}:
                return f"{path}.{key}"
            if "confidence" in normalized and normalized != "source_confidence":
                return f"{path}.{key}"
            if any(token in normalized for token in ("v333", "v3_3_3", "jcfb_v3")):
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


def _json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ExternalMarketValidationError("PAYLOAD_NUMBER_INVALID", f"{path} must be finite")
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ExternalMarketValidationError("PAYLOAD_KEY_INVALID", f"{path} keys must be strings")
        for key, child in value.items():
            _json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_value(child, f"{path}[{index}]")
        return
    raise ExternalMarketValidationError("PAYLOAD_TYPE_INVALID", f"{path} is not JSON-compatible")


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


def _line(value: Any, market: ExternalMarket, status: ExternalMarketStatus) -> Union[float, str]:
    if market == ExternalMarket.EUROPEAN_1X2:
        if value != "NOT_APPLICABLE":
            raise ExternalMarketValidationError("LINE_NOT_APPLICABLE_REQUIRED", "European 1X2 line must be NOT_APPLICABLE")
        return "NOT_APPLICABLE"
    if isinstance(value, bool):
        raise ExternalMarketValidationError("LINE_TYPE_INVALID", "line must be numeric or an explicit state")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if status != ExternalMarketStatus.AVAILABLE and isinstance(value, str) and value.strip().upper() in LINE_STATES:
        return value.strip().upper()
    raise ExternalMarketValidationError("LINE_REQUIRED", f"{market.value} requires a numeric line or explicit UNKNOWN/CONFLICTED state")


def _prices(value: Any, market: ExternalMarket, status: ExternalMarketStatus) -> Optional[Mapping[str, float]]:
    if value is None:
        if status == ExternalMarketStatus.AVAILABLE:
            raise ExternalMarketValidationError("PRICES_REQUIRED", "AVAILABLE external market snapshots require prices")
        return None
    if not isinstance(value, Mapping) or not value:
        raise ExternalMarketValidationError("PRICES_EMPTY", "prices must be a non-empty typed object when supplied")
    _json_value(value, "prices")
    if set(value) != set(PRICE_LABELS[market]):
        missing = sorted(set(PRICE_LABELS[market]) - set(value))
        extra = sorted(set(value) - set(PRICE_LABELS[market]))
        raise ExternalMarketValidationError("PRICE_SHAPE_INVALID", f"{market.value} price shape mismatch; missing={missing}, extra={extra}")
    result: Dict[str, float] = {}
    for label in PRICE_LABELS[market]:
        price = value[label]
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
            raise ExternalMarketValidationError("PRICE_VALUE_INVALID", f"prices.{label} must be a finite positive number")
        result[label] = float(price)
    return result


def _source_confidence(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExternalMarketValidationError("SOURCE_CONFIDENCE_INVALID", "source_confidence must be an explicit provider-provenance object")
    _json_value(value, "source_confidence")
    forbidden = _find_forbidden(value, "source_confidence")
    if forbidden:
        raise ExternalMarketValidationError("MODEL_FIELD_FORBIDDEN", f"external facts cannot contain {forbidden}")
    state = _text(value.get("state"), "source_confidence.state")
    basis = _text(value.get("basis"), "source_confidence.basis")
    result: Dict[str, Any] = {"state": state, "basis": basis}
    if "score" in value:
        score = value["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
            raise ExternalMarketValidationError("SOURCE_CONFIDENCE_SCORE_INVALID", "source_confidence.score must be between 0 and 1")
        result["score"] = float(score)
    return result


@dataclass(frozen=True)
class ExternalConflictEvidence:
    """One immutable source side retained for a CONFLICT snapshot."""

    provider: str
    source: str
    source_ref: str
    market: ExternalMarket
    line: Union[float, str]
    prices: Mapping[str, float]
    source_timestamp: str
    captured_at: str
    provenance_ref: str
    provenance_hash: str
    observation_id: str

    @classmethod
    def from_dict(cls, raw: Any, *, parent_market: ExternalMarket) -> "ExternalConflictEvidence":
        if not isinstance(raw, Mapping):
            raise ExternalMarketValidationError("CONFLICT_EVIDENCE_INVALID", "conflict_evidence entries must be objects")
        forbidden = _find_forbidden(raw, "conflict_evidence")
        if forbidden:
            raise ExternalMarketValidationError("MODEL_FIELD_FORBIDDEN", f"external facts cannot contain {forbidden}")
        market_raw = raw.get("market", parent_market.value)
        if not isinstance(market_raw, str) or market_raw != parent_market.value:
            raise ExternalMarketValidationError("CONFLICT_MARKET_MISMATCH", "conflict evidence market must match the parent market")
        provider = _text(raw.get("provider"), "conflict_evidence.provider")
        source = _text(raw.get("source"), "conflict_evidence.source")
        source_ref = _text(raw.get("source_ref", raw.get("source_reference")), "conflict_evidence.source_ref")
        status = ExternalMarketStatus.AVAILABLE
        line = _line(raw.get("line"), parent_market, status)
        prices = _prices(raw.get("prices"), parent_market, status)
        assert prices is not None
        source_timestamp = _source_time(raw.get("source_timestamp"))
        captured_at = _timestamp(raw.get("captured_at"), "conflict_evidence.captured_at")
        provenance_ref = _text(raw.get("provenance_ref", source_ref), "conflict_evidence.provenance_ref")
        provenance_hash = _hash(raw.get("provenance_hash"), "conflict_evidence.provenance_hash") if raw.get("provenance_hash") is not None else sha256_json({"provider": provider, "source": source, "source_ref": source_ref, "provenance_ref": provenance_ref, "source_timestamp": source_timestamp})
        observation_id = _text(raw.get("observation_id", sha256_json(raw)), "conflict_evidence.observation_id")
        return cls(provider, source, source_ref, parent_market, line, MappingProxyType(prices), source_timestamp, _iso(captured_at), provenance_ref, provenance_hash, observation_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "source": self.source,
            "source_ref": self.source_ref,
            "source_reference": self.source_ref,
            "market": self.market.value,
            "line": self.line,
            "prices": dict(self.prices),
            "source_timestamp": self.source_timestamp,
            "captured_at": self.captured_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
        }


@dataclass(frozen=True)
class ExternalMarketObservation:
    match_id: str
    snapshot_kind: str
    created_at: datetime
    source_timestamp: str
    source_published_at: Optional[datetime]
    captured_at: datetime
    observed_at: datetime
    ingested_at: datetime
    source: str
    source_type: str
    source_ref: str
    provider: str
    market: ExternalMarket
    line: Union[float, str]
    prices: Optional[Mapping[str, float]]
    availability_status: ExternalMarketStatus
    reason_code: Optional[str]
    reason_detail: Optional[str]
    liquidity_quality: Optional[Union[str, Mapping[str, Any]]]
    source_confidence: Mapping[str, Any]
    source_is_official: bool
    snapshot_id: Optional[str]
    supersedes_snapshot_id: Optional[str]
    revision_reason: Optional[str]
    conflict_evidence: Tuple[ExternalConflictEvidence, ...]
    supplied_snapshot_hash: Optional[str]
    supplied_payload_hash: Optional[str]
    supplied_provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExternalMarketObservation":
        if not isinstance(raw, Mapping):
            raise ExternalMarketValidationError("OBSERVATION_NOT_OBJECT", "external market observation must be an object")
        if any(key in raw for key in OFFICIAL_FIELDS):
            raise ExternalMarketValidationError("OFFICIAL_FIELD_FORBIDDEN", "external market observations cannot contain official odds fields")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise ExternalMarketValidationError("MODEL_FIELD_FORBIDDEN", f"external facts cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        snapshot_kind = raw.get("snapshot_kind")
        if not isinstance(snapshot_kind, str) or snapshot_kind not in SNAPSHOT_KINDS:
            raise ExternalMarketValidationError("SNAPSHOT_KIND_INVALID", "snapshot_kind must be a governed exact value")
        source_type = _text(raw.get("source_type"), "source_type")
        if source_type not in SOURCE_TYPES:
            raise ExternalMarketValidationError("EXTERNAL_SOURCE_TYPE_REQUIRED", "source_type must be EXTERNAL_FEED or EXTERNAL_SCREENSHOT")
        if raw.get("source_is_official") is not False:
            raise ExternalMarketValidationError("EXTERNAL_SOURCE_REQUIRED", "source_is_official must be false")
        source = _text(raw.get("source"), "source")
        provider = _text(raw.get("provider"), "provider")
        source_ref = _text(raw.get("source_ref", raw.get("source_reference")), "source_ref")
        if raw.get("source_ref") is not None and raw.get("source_reference") is not None and raw["source_ref"] != raw["source_reference"]:
            raise ExternalMarketValidationError("SOURCE_REFERENCE_CONFLICT", "source_ref and source_reference must agree")
        market_raw = raw.get("market")
        if not isinstance(market_raw, str):
            raise ExternalMarketValidationError("MARKET_REQUIRED", "market must be an exact external market enum")
        try:
            market = ExternalMarket(market_raw)
        except ValueError as exc:
            raise ExternalMarketValidationError("MARKET_INVALID", f"unsupported external market: {market_raw}") from exc
        status_raw = raw.get("availability_status", raw.get("status"))
        if not isinstance(status_raw, str):
            raise ExternalMarketValidationError("AVAILABILITY_STATUS_REQUIRED", "availability_status is required; no status inference is allowed")
        try:
            status = ExternalMarketStatus(status_raw)
        except ValueError as exc:
            raise ExternalMarketValidationError("AVAILABILITY_STATUS_INVALID", f"unsupported availability_status: {status_raw}") from exc
        if "prices" not in raw:
            raise ExternalMarketValidationError("PRICES_REQUIRED", "prices must be explicit, including null for a non-AVAILABLE state")
        line = _line(raw.get("line"), market, status)
        prices = _prices(raw.get("prices"), market, status)
        created_at = _timestamp(raw.get("created_at"), "created_at")
        captured_at = _timestamp(raw.get("captured_at"), "captured_at")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        if observed_at < captured_at:
            raise ExternalMarketValidationError("OBSERVED_BEFORE_CAPTURED", "observed_at cannot precede captured_at")
        if ingested_at < observed_at:
            raise ExternalMarketValidationError("INGESTED_BEFORE_OBSERVED", "ingested_at cannot precede observed_at")
        source_timestamp = _source_time(raw.get("source_timestamp"))
        source_published_at = _timestamp(raw.get("source_published_at"), "source_published_at") if raw.get("source_published_at") is not None else None
        reason_code = raw.get("reason_code")
        reason_detail = raw.get("reason_detail")
        if status in NON_AVAILABLE_STATUSES:
            reason_code = _text(reason_code, "reason_code")
            if not REASON_CODE_RE.fullmatch(reason_code):
                raise ExternalMarketValidationError("REASON_CODE_INVALID", "reason_code must be an uppercase stable code")
        elif reason_code is not None:
            reason_code = _text(reason_code, "reason_code")
            if not REASON_CODE_RE.fullmatch(reason_code):
                raise ExternalMarketValidationError("REASON_CODE_INVALID", "reason_code must be an uppercase stable code")
        if reason_detail is not None:
            reason_detail = _text(reason_detail, "reason_detail")
        if reason_detail is not None and reason_code is None:
            raise ExternalMarketValidationError("REASON_CODE_REQUIRED", "reason_detail requires reason_code")
        liquidity = raw.get("liquidity_quality")
        if liquidity is not None:
            if isinstance(liquidity, str):
                liquidity = _text(liquidity, "liquidity_quality")
                if liquidity not in LIQUIDITY_STATES:
                    raise ExternalMarketValidationError("LIQUIDITY_QUALITY_INVALID", "liquidity_quality must be governed or an object")
            elif isinstance(liquidity, Mapping):
                _json_value(liquidity, "liquidity_quality")
                liquidity = MappingProxyType(dict(liquidity))
            else:
                raise ExternalMarketValidationError("LIQUIDITY_QUALITY_INVALID", "liquidity_quality must be a governed state or object")
        source_confidence = _source_confidence(raw.get("source_confidence"))
        evidence_raw = raw.get("conflict_evidence", ())
        if evidence_raw is None:
            evidence_raw = ()
        if not isinstance(evidence_raw, (list, tuple)):
            raise ExternalMarketValidationError("CONFLICT_EVIDENCE_INVALID", "conflict_evidence must be an array")
        evidence = tuple(ExternalConflictEvidence.from_dict(item, parent_market=market) for item in evidence_raw)
        if status == ExternalMarketStatus.CONFLICT and len(evidence) < 2:
            raise ExternalMarketValidationError("CONFLICT_EVIDENCE_REQUIRED", "CONFLICT requires at least two retained source sides")
        if status != ExternalMarketStatus.CONFLICT and evidence:
            raise ExternalMarketValidationError("CONFLICT_EVIDENCE_STATUS_MISMATCH", "conflict_evidence requires CONFLICT")
        snapshot_id = _uuid(raw.get("snapshot_id"), "snapshot_id") if raw.get("snapshot_id") is not None else None
        supersedes = _uuid(raw.get("supersedes_snapshot_id"), "supersedes_snapshot_id") if raw.get("supersedes_snapshot_id") is not None else None
        revision_reason = _text(raw.get("revision_reason"), "revision_reason") if raw.get("revision_reason") is not None else None
        if snapshot_kind == "CORRECTION":
            if supersedes is None:
                raise ExternalMarketValidationError("SUPERSEDES_REQUIRED", "CORRECTION requires supersedes_snapshot_id")
            if revision_reason is None:
                raise ExternalMarketValidationError("REVISION_REASON_REQUIRED", "CORRECTION requires revision_reason")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ExternalMarketValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        _json_value(metadata, "metadata")
        return cls(
            match_id=match_id,
            snapshot_kind=snapshot_kind,
            created_at=created_at,
            source_timestamp=source_timestamp,
            source_published_at=source_published_at,
            captured_at=captured_at,
            observed_at=observed_at,
            ingested_at=ingested_at,
            source=source,
            source_type=source_type,
            source_ref=source_ref,
            provider=provider,
            market=market,
            line=line,
            prices=MappingProxyType(prices) if prices is not None else None,
            availability_status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            liquidity_quality=liquidity,
            source_confidence=MappingProxyType(dict(source_confidence)),
            source_is_official=False,
            snapshot_id=snapshot_id,
            supersedes_snapshot_id=supersedes,
            revision_reason=revision_reason,
            conflict_evidence=evidence,
            supplied_snapshot_hash=_hash(raw["snapshot_hash"], "snapshot_hash") if "snapshot_hash" in raw else None,
            supplied_payload_hash=_hash(raw["payload_hash"], "payload_hash") if "payload_hash" in raw else None,
            supplied_provenance_hash=_hash(raw["provenance_hash"], "provenance_hash") if "provenance_hash" in raw else None,
            metadata=MappingProxyType(dict(metadata)),
        )

    @property
    def observation_id(self) -> str:
        return str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"external-observation|{sha256_json(self.to_dict(include_hashes=False))}"))

    def to_dict(self, *, include_hashes: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "match_id": self.match_id,
            "snapshot_kind": self.snapshot_kind,
            "created_at": _iso(self.created_at),
            "source_timestamp": self.source_timestamp,
            "source_published_at": _iso(self.source_published_at) if self.source_published_at else None,
            "captured_at": _iso(self.captured_at),
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "source": self.source,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "source_reference": self.source_ref,
            "provider": self.provider,
            "market": self.market.value,
            "line": self.line,
            "prices": dict(self.prices) if self.prices is not None else None,
            "availability_status": self.availability_status.value,
            "status": self.availability_status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "liquidity_quality": _thaw(self.liquidity_quality),
            "source_confidence": dict(self.source_confidence),
            "source_is_official": False,
            "supersedes_snapshot_id": self.supersedes_snapshot_id,
            "revision_reason": self.revision_reason,
            "conflict_evidence": [item.to_dict() for item in self.conflict_evidence],
            "metadata": _thaw(self.metadata),
        }
        if include_hashes:
            result.update({"snapshot_id": self.snapshot_id, "snapshot_hash": None, "payload_hash": None, "provenance_hash": None})
        return result


@dataclass(frozen=True)
class ExternalMarketSnapshot:
    object_id: str
    snapshot_id: str
    contract_version: str
    match_id: str
    snapshot_kind: str
    created_at: str
    source_timestamp: str
    source_published_at: Optional[str]
    captured_at: str
    observed_at: str
    ingested_at: str
    source: str
    source_type: str
    source_ref: str
    provider: str
    market: ExternalMarket
    line: Union[float, str]
    prices: Optional[Mapping[str, float]]
    availability_status: ExternalMarketStatus
    reason_code: Optional[str]
    reason_detail: Optional[str]
    liquidity_quality: Optional[Union[str, Mapping[str, Any]]]
    source_confidence: Mapping[str, Any]
    source_is_official: bool
    snapshot_hash: str
    payload_hash: str
    provenance_hash: str
    observation_id: str
    supersedes_snapshot_id: Optional[str]
    revision: int
    revision_reason: Optional[str]
    conflict_evidence: Tuple[ExternalConflictEvidence, ...]
    metadata: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "snapshot_id": self.snapshot_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "snapshot_kind": self.snapshot_kind,
            "created_at": self.created_at,
            "source_timestamp": self.source_timestamp,
            "source_published_at": self.source_published_at,
            "captured_at": self.captured_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "source": self.source,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "source_reference": self.source_ref,
            "provider": self.provider,
            "market": self.market.value,
            "line": self.line,
            "prices": dict(self.prices) if self.prices is not None else None,
            "availability_status": self.availability_status.value,
            "status": self.availability_status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "liquidity_quality": _thaw(self.liquidity_quality),
            "source_confidence": dict(self.source_confidence),
            "source_is_official": self.source_is_official,
            "snapshot_hash": self.snapshot_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
            "supersedes_snapshot_id": self.supersedes_snapshot_id,
            "revision": self.revision,
            "revision_reason": self.revision_reason,
            "conflict_evidence": [item.to_dict() for item in self.conflict_evidence],
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class ExternalMarketIntakeResult:
    accepted: bool
    action: str
    observation_id: str
    snapshot: Optional[ExternalMarketSnapshot]
    error_code: Optional[str] = None


@dataclass(frozen=True)
class _ExternalAppendEvent:
    sequence: int
    action: str
    observation_id: str
    snapshot_id: Optional[str]
    match_id: Optional[str]
    market: Optional[str]
    status: str
    error_code: Optional[str] = None


class ExternalMarketSnapshotStore:
    """Local append-only external market store; never writes a database."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore, market: Optional[ExternalMarket] = None):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-028/029/030 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._market = market
        self._snapshots: Dict[str, ExternalMarketSnapshot] = {}
        self._observations: Dict[str, ExternalMarketObservation] = {}
        self._latest_by_key: Dict[Tuple[str, str, ExternalMarket, str], ExternalMarketSnapshot] = {}
        self._events: List[_ExternalAppendEvent] = []

    @property
    def snapshots(self) -> Tuple[ExternalMarketSnapshot, ...]:
        return tuple(self._snapshots.values())

    @property
    def observations(self) -> Tuple[ExternalMarketObservation, ...]:
        return tuple(self._observations.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(MappingProxyType({
            "sequence": event.sequence,
            "action": event.action,
            "observation_id": event.observation_id,
            "snapshot_id": event.snapshot_id,
            "match_id": event.match_id,
            "market": event.market,
            "status": event.status,
            "error_code": event.error_code,
        }) for event in self._events)

    def get(self, snapshot_id: str) -> Optional[ExternalMarketSnapshot]:
        return self._snapshots.get(snapshot_id)

    def latest(self, match_id: str, provider: Optional[str] = None, market: Optional[ExternalMarket] = None, line: Optional[Union[float, str]] = None) -> Optional[ExternalMarketSnapshot]:
        candidates = [item for item in self._snapshots.values() if item.match_id == match_id]
        if provider is not None:
            candidates = [item for item in candidates if item.provider == provider]
        if market is not None:
            candidates = [item for item in candidates if item.market == market]
        if line is not None:
            candidates = [item for item in candidates if item.line == line]
        return candidates[-1] if candidates else None

    def ingest(self, raw: Union[ExternalMarketObservation, Mapping[str, Any]]) -> ExternalMarketIntakeResult:
        try:
            observation = raw if isinstance(raw, ExternalMarketObservation) else ExternalMarketObservation.from_dict(raw)
        except (ExternalMarketValidationError, IdentityValidationError) as exc:
            source = raw.to_dict(include_hashes=False) if isinstance(raw, ExternalMarketObservation) else raw
            observation_id = str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"external-blocked|{sha256_json(source)}"))
            self._append_event("BLOCKED_VALIDATION", observation_id, None, None, None, "BLOCKED", getattr(exc, "code", "VALIDATION_FAILED"))
            return ExternalMarketIntakeResult(False, "BLOCKED_VALIDATION", observation_id, None, getattr(exc, "code", "VALIDATION_FAILED"))
        if self._market is not None and observation.market != self._market:
            return self._blocked(observation, "MARKET_ADAPTER_MISMATCH")
        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((item for item in self._snapshots.values() if item.observation_id == observation_id), None)
            self._append_event("DUPLICATE_NOOP", observation_id, existing.snapshot_id if existing else None, observation.match_id, observation.market.value, "DUPLICATE_NOOP")
            return ExternalMarketIntakeResult(True, "DUPLICATE_NOOP", observation_id, existing)
        identity = self._identity_store.get(observation.match_id)
        if identity is None:
            return self._blocked(observation, "MATCH_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, "MATCH_IDENTITY_NOT_RESOLVED")
        key = (observation.match_id, observation.provider, observation.market, str(observation.line))
        predecessor = self._latest_by_key.get(key)
        if observation.snapshot_kind == "CORRECTION":
            superseded = self._snapshots.get(observation.supersedes_snapshot_id or "")
            if superseded is None:
                return self._blocked(observation, "SUPERSEDED_SNAPSHOT_NOT_FOUND")
            if (superseded.match_id, superseded.provider, superseded.market, str(superseded.line)) != key:
                return self._blocked(observation, "SUPERSEDES_MARKET_CONFLICT")
        elif observation.supersedes_snapshot_id is not None:
            superseded = self._snapshots.get(observation.supersedes_snapshot_id)
            if superseded is None or (superseded.match_id, superseded.provider, superseded.market, str(superseded.line)) != key:
                return self._blocked(observation, "SUPERSEDES_MARKET_CONFLICT")
        logical = {
            "match_id": observation.match_id,
            "snapshot_kind": observation.snapshot_kind,
            "source_timestamp": observation.source_timestamp,
            "source_published_at": _iso(observation.source_published_at) if observation.source_published_at else None,
            "captured_at": _iso(observation.captured_at),
            "observed_at": _iso(observation.observed_at),
            "source": observation.source,
            "source_type": observation.source_type,
            "source_ref": observation.source_ref,
            "provider": observation.provider,
            "market": observation.market.value,
            "line": observation.line,
            "prices": dict(observation.prices) if observation.prices is not None else None,
            "availability_status": observation.availability_status.value,
            "reason_code": observation.reason_code,
            "reason_detail": observation.reason_detail,
            "source_confidence": dict(observation.source_confidence),
            "source_is_official": False,
            "supersedes_snapshot_id": observation.supersedes_snapshot_id,
            "conflict_evidence": [item.to_dict() for item in observation.conflict_evidence],
        }
        snapshot_id = observation.snapshot_id or str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"external-snapshot|{sha256_json(logical)}"))
        logical["snapshot_id"] = snapshot_id
        payload_hash = sha256_json({
            "market": observation.market.value,
            "line": observation.line,
            "prices": dict(observation.prices) if observation.prices is not None else None,
            "availability_status": observation.availability_status.value,
            "reason_code": observation.reason_code,
            "conflict_evidence": [item.to_dict() for item in observation.conflict_evidence],
        })
        provenance_hash = sha256_json({
            "match_id": observation.match_id,
            "provider": observation.provider,
            "source": observation.source,
            "source_type": observation.source_type,
            "source_ref": observation.source_ref,
            "source_timestamp": observation.source_timestamp,
            "source_published_at": _iso(observation.source_published_at) if observation.source_published_at else None,
            "captured_at": _iso(observation.captured_at),
            "observed_at": _iso(observation.observed_at),
            "conflict_evidence": [item.to_dict() for item in observation.conflict_evidence],
        })
        snapshot_hash = sha256_json(logical)
        for supplied, expected in ((observation.supplied_snapshot_hash, snapshot_hash), (observation.supplied_payload_hash, payload_hash), (observation.supplied_provenance_hash, provenance_hash)):
            if supplied is not None and supplied != expected:
                return self._blocked(observation, "HASH_MISMATCH")
        self._observations[observation_id] = observation
        snapshot = ExternalMarketSnapshot(
            object_id=snapshot_id,
            snapshot_id=snapshot_id,
            contract_version=CONTRACT_VERSION,
            match_id=observation.match_id,
            snapshot_kind=observation.snapshot_kind,
            created_at=_iso(observation.created_at),
            source_timestamp=observation.source_timestamp,
            source_published_at=_iso(observation.source_published_at) if observation.source_published_at else None,
            captured_at=_iso(observation.captured_at),
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            source=observation.source,
            source_type=observation.source_type,
            source_ref=observation.source_ref,
            provider=observation.provider,
            market=observation.market,
            line=observation.line,
            prices=observation.prices,
            availability_status=observation.availability_status,
            reason_code=observation.reason_code,
            reason_detail=observation.reason_detail,
            liquidity_quality=observation.liquidity_quality,
            source_confidence=observation.source_confidence,
            source_is_official=False,
            snapshot_hash=snapshot_hash,
            payload_hash=payload_hash,
            provenance_hash=provenance_hash,
            observation_id=observation_id,
            supersedes_snapshot_id=observation.supersedes_snapshot_id,
            revision=predecessor.revision + 1 if predecessor else 1,
            revision_reason=observation.revision_reason,
            conflict_evidence=observation.conflict_evidence,
            metadata=observation.metadata,
        )
        self._snapshots[snapshot_id] = snapshot
        self._latest_by_key[key] = snapshot
        self._append_event("APPEND_SNAPSHOT", observation_id, snapshot_id, observation.match_id, observation.market.value, observation.availability_status.value)
        return ExternalMarketIntakeResult(True, "APPENDED", observation_id, snapshot)

    def _blocked(self, observation: ExternalMarketObservation, code: str) -> ExternalMarketIntakeResult:
        self._append_event("BLOCKED_BOUNDARY", observation.observation_id, None, observation.match_id, observation.market.value, "BLOCKED", code)
        return ExternalMarketIntakeResult(False, code, observation.observation_id, None, code)

    def _append_event(self, action: str, observation_id: str, snapshot_id: Optional[str], match_id: Optional[str], market: Optional[str], status: str, error_code: Optional[str] = None) -> None:
        self._events.append(_ExternalAppendEvent(len(self._events) + 1, action, observation_id, snapshot_id, match_id, market, status, error_code))


class ExternalEuropean1X2Adapter(ExternalMarketSnapshotStore):
    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        super().__init__(identity_store, ExternalMarket.EUROPEAN_1X2)


# Task-oriented alias keeps the V4-028 naming discoverable without
# introducing a second architecture.
European1X2Intake = ExternalEuropean1X2Adapter
