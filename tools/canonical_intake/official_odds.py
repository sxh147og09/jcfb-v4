"""V4-024 official China Sports Lottery five-market snapshot intake.

This module is a local, in-memory, no-write adapter boundary.  It validates
official feed snapshots, binds them to V4-020 canonical match identity, and
computes the contract hashes needed by later V4-026/V4-027 gates.  It does
not connect to a live feed, Supabase, Production, or a migration.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore, IdentityValidationError, _iso, _parse_timestamp


CONTRACT_VERSION = "official-odds-snapshot@1.0.0"
SNAPSHOT_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MARKETS = ("spf", "rqspf", "total_goals", "exact_score", "half_full")
SNAPSHOT_KINDS = frozenset({"OPENING", "INTERMEDIATE", "CURRENT", "LATEST", "FINAL", "CORRECTION"})
OFFICIAL_SOURCE_TYPES = frozenset({"OFFICIAL_FEED"})
MARKET_STATUSES = frozenset({"AVAILABLE", "UNAVAILABLE", "UNKNOWN", "NOT_VERIFIED", "BLOCKED", "CONFLICTED"})
SOURCE_TIME_STATES = frozenset({"UNKNOWN", "CONFLICTED"})
MODEL_FIELD_TOKENS = frozenset(
    {
        "prediction",
        "recommendation",
        "model",
        "model_interpretation",
        "modelinterpretation",
        "engine",
        "engine_output",
        "engineoutput",
        "probability",
        "risk",
        "score_engine",
        "scoreengine",
    }
)


class OfficialOddsValidationError(ValueError):
    """An official odds snapshot cannot be represented safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SnapshotKind(str, Enum):
    OPENING = "OPENING"
    INTERMEDIATE = "INTERMEDIATE"
    CURRENT = "CURRENT"
    LATEST = "LATEST"
    FINAL = "FINAL"
    CORRECTION = "CORRECTION"


class MarketAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"
    CONFLICTED = "CONFLICTED"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfficialOddsValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise OfficialOddsValidationError("IDENTITY_REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _hash(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not HASH_RE.fullmatch(result):
        raise OfficialOddsValidationError("HASH_INVALID", f"{field_name} must be sha256:<64 lowercase hex>")
    return result


def _timestamp(value: Any, field_name: str) -> datetime:
    try:
        parsed = _parse_timestamp(value, field_name)
    except IdentityValidationError as exc:
        raise OfficialOddsValidationError(exc.code, exc.message) from exc
    assert parsed is not None
    return parsed


def _source_timestamp(value: Any) -> str:
    if isinstance(value, str) and value.strip().upper() in SOURCE_TIME_STATES:
        return value.strip().upper()
    return _iso(_timestamp(value, "source_timestamp"))


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).strip().casefold())


def _find_model_field(value: Any, path: str = "snapshot") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in MODEL_FIELD_TOKENS or any(token in normalized for token in ("prediction", "recommendation", "modelinterpretation", "engineoutput")):
                return f"{path}.{key}"
            found = _find_model_field(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_model_field(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise OfficialOddsValidationError("PAYLOAD_NUMBER_INVALID", f"{path} must be finite")
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise OfficialOddsValidationError("PAYLOAD_KEY_INVALID", f"{path} keys must be strings")
        for key, child in value.items():
            _json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_value(child, f"{path}[{index}]")
        return
    raise OfficialOddsValidationError("PAYLOAD_TYPE_INVALID", f"{path} is not JSON-compatible")


def _positive_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise OfficialOddsValidationError("ODDS_VALUE_INVALID", f"{path} must be a finite positive number")
    return value


def _validate_market_payload(market: str, payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or not payload:
        raise OfficialOddsValidationError("PAYLOAD_EMPTY", f"{market} AVAILABLE payload must be a non-empty object")
    _json_value(payload, market)
    forbidden = _find_model_field(payload, market)
    if forbidden:
        raise OfficialOddsValidationError("MODEL_FIELD_FORBIDDEN", f"official odds cannot contain {forbidden}")
    expected: Optional[Tuple[str, ...]] = None
    if market == "spf":
        expected = ("home", "draw", "away")
    elif market == "rqspf":
        expected = ("official_handicap", "home", "draw", "away")
    elif market == "total_goals":
        expected = ("0", "1", "2", "3", "4", "5", "6", "7+")
    elif market == "half_full":
        expected = ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A")
    elif market == "exact_score":
        if not all(isinstance(key, str) and re.fullmatch(r"\d+:\d+", key) for key in payload):
            raise OfficialOddsValidationError("MARKET_PAYLOAD_LABEL_INVALID", "exact_score labels must be home:away")
        expected = tuple(payload.keys())
    assert expected is not None
    if set(payload) != set(expected):
        missing = sorted(set(expected) - set(payload))
        extra = sorted(set(payload) - set(expected))
        raise OfficialOddsValidationError("MARKET_PAYLOAD_SHAPE_INVALID", f"{market} shape mismatch; missing={missing}, extra={extra}")
    for key, value in payload.items():
        if market == "rqspf" and key == "official_handicap":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise OfficialOddsValidationError("HANDICAP_VALUE_INVALID", "rqspf.official_handicap must be finite numeric")
        else:
            _positive_number(value, f"{market}.{key}")
    return dict(payload)


def _availability(raw: Any, market: str, payload: Any, unavailable_reason: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise OfficialOddsValidationError("MARKET_AVAILABILITY_INVALID", f"market_availability.{market} must be an object")
    available = raw.get("available")
    if not isinstance(available, bool):
        raise OfficialOddsValidationError("MARKET_AVAILABILITY_INVALID", f"market_availability.{market}.available must be boolean")
    status_raw = raw.get("status")
    if not isinstance(status_raw, str) or status_raw not in MARKET_STATUSES:
        raise OfficialOddsValidationError("MARKET_STATUS_INVALID", f"market_availability.{market}.status is not governed")
    reason = raw.get("reason", unavailable_reason)
    if available:
        if status_raw != "AVAILABLE":
            raise OfficialOddsValidationError("MARKET_STATUS_CONFLICT", f"{market} available=true requires status=AVAILABLE")
        if reason not in (None, "NOT_APPLICABLE"):
            reason = _text(reason, f"market_availability.{market}.reason")
        else:
            reason = "NOT_APPLICABLE"
        checked_payload = _validate_market_payload(market, payload)
    else:
        if status_raw == "AVAILABLE":
            raise OfficialOddsValidationError("MARKET_STATUS_CONFLICT", f"{market} available=false cannot be AVAILABLE")
        reason = _text(reason, f"market_availability.{market}.reason")
        if payload is not None:
            raise OfficialOddsValidationError("UNAVAILABLE_PAYLOAD_FORBIDDEN", f"{market} non-AVAILABLE payload must be absent")
        checked_payload = None
    return {"available": available, "status": status_raw, "reason": reason, "payload": checked_payload}


@dataclass(frozen=True)
class OfficialOddsObservation:
    match_id: str
    snapshot_kind: SnapshotKind
    created_at: datetime
    captured_at: datetime
    source_timestamp: str
    observed_at: datetime
    ingested_at: datetime
    source: str
    source_type: str
    source_reference: str
    source_is_official: bool
    market_availability: Mapping[str, Mapping[str, Any]]
    market_unavailable_reason: Mapping[str, str]
    payloads: Mapping[str, Optional[Mapping[str, Any]]]
    evidence_ref: Optional[str]
    snapshot_id: Optional[str]
    supersedes_snapshot_id: Optional[str]
    revision_reason: Optional[str]
    supplied_snapshot_hash: Optional[str]
    supplied_payload_hash: Optional[str]
    supplied_provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OfficialOddsObservation":
        if not isinstance(raw, Mapping):
            raise OfficialOddsValidationError("OBSERVATION_NOT_OBJECT", "official odds observation must be an object")
        forbidden = _find_model_field(raw)
        if forbidden:
            raise OfficialOddsValidationError("MODEL_FIELD_FORBIDDEN", f"official odds cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        kind_raw = raw.get("snapshot_kind")
        if not isinstance(kind_raw, str) or kind_raw not in SNAPSHOT_KINDS:
            raise OfficialOddsValidationError("SNAPSHOT_KIND_INVALID", "snapshot_kind must be a governed exact value")
        source_type = _text(raw.get("source_type"), "source_type")
        if source_type not in OFFICIAL_SOURCE_TYPES:
            raise OfficialOddsValidationError("OFFICIAL_SOURCE_TYPE_REQUIRED", "V4-024 accepts OFFICIAL_FEED only")
        if raw.get("source_is_official") is not True:
            raise OfficialOddsValidationError("OFFICIAL_SOURCE_REQUIRED", "source_is_official must be true")
        source = _text(raw.get("source"), "source")
        source_reference = _text(raw.get("source_reference"), "source_reference")
        created_at = _timestamp(raw.get("created_at"), "created_at")
        captured_at = _timestamp(raw.get("captured_at"), "captured_at")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        if ingested_at < observed_at:
            raise OfficialOddsValidationError("INGESTED_BEFORE_OBSERVED", "ingested_at cannot precede observed_at")
        source_timestamp = _source_timestamp(raw.get("source_timestamp"))
        availability_raw = raw.get("market_availability")
        reason_raw = raw.get("market_unavailable_reason")
        if not isinstance(availability_raw, Mapping) or set(availability_raw) != set(MARKETS):
            raise OfficialOddsValidationError("MARKET_SET_INVALID", "market_availability must cover exactly five official markets")
        if not isinstance(reason_raw, Mapping) or set(reason_raw) != set(MARKETS):
            raise OfficialOddsValidationError("MARKET_REASON_SET_INVALID", "market_unavailable_reason must cover exactly five official markets")
        payloads: Dict[str, Optional[Mapping[str, Any]]] = {}
        availabilities: Dict[str, Mapping[str, Any]] = {}
        reasons: Dict[str, str] = {}
        for market in MARKETS:
            result = _availability(availability_raw[market], market, raw.get(market), reason_raw[market])
            payloads[market] = result["payload"]
            availabilities[market] = MappingProxyType({"available": result["available"], "status": result["status"], "reason": result["reason"]})
            reasons[market] = result["reason"]
        evidence_ref = raw.get("evidence_ref")
        if evidence_ref is not None:
            evidence_ref = _text(evidence_ref, "evidence_ref")
        snapshot_id = raw.get("snapshot_id")
        if snapshot_id is not None:
            snapshot_id = _uuid(snapshot_id, "snapshot_id")
        supersedes = raw.get("supersedes_snapshot_id")
        if kind_raw == "CORRECTION":
            supersedes = _uuid(supersedes, "supersedes_snapshot_id")
            _text(raw.get("revision_reason"), "revision_reason")
        elif supersedes is not None:
            supersedes = _uuid(supersedes, "supersedes_snapshot_id")
        revision_reason = raw.get("revision_reason")
        if revision_reason is not None:
            revision_reason = _text(revision_reason, "revision_reason")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise OfficialOddsValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        return cls(
            match_id=match_id,
            snapshot_kind=SnapshotKind(kind_raw),
            created_at=created_at,
            captured_at=captured_at,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            ingested_at=ingested_at,
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            source_is_official=True,
            market_availability=MappingProxyType(availabilities),
            market_unavailable_reason=MappingProxyType(reasons),
            payloads=MappingProxyType(payloads),
            evidence_ref=evidence_ref,
            snapshot_id=snapshot_id,
            supersedes_snapshot_id=supersedes,
            revision_reason=revision_reason,
            supplied_snapshot_hash=_hash(raw["snapshot_hash"], "snapshot_hash") if "snapshot_hash" in raw else None,
            supplied_payload_hash=_hash(raw["payload_hash"], "payload_hash") if "payload_hash" in raw else None,
            supplied_provenance_hash=_hash(raw["provenance_hash"], "provenance_hash") if "provenance_hash" in raw else None,
            metadata=MappingProxyType(dict(metadata)),
        )

    @property
    def observation_id(self) -> str:
        return str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"observation|{sha256_json(self.to_dict(include_hashes=False))}"))

    def to_dict(self, *, include_hashes: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "match_id": self.match_id,
            "snapshot_kind": self.snapshot_kind.value,
            "created_at": _iso(self.created_at),
            "captured_at": _iso(self.captured_at),
            "source_timestamp": self.source_timestamp,
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_is_official": self.source_is_official,
            "market_availability": {market: dict(self.market_availability[market]) for market in MARKETS},
            "market_unavailable_reason": dict(self.market_unavailable_reason),
            "evidence_ref": self.evidence_ref,
            "supersedes_snapshot_id": self.supersedes_snapshot_id,
            "revision_reason": self.revision_reason,
            "metadata": dict(self.metadata),
        }
        result.update(self.payloads)
        if include_hashes:
            result.update({"snapshot_id": self.snapshot_id, "snapshot_hash": None, "payload_hash": None, "provenance_hash": None})
        return result


@dataclass(frozen=True)
class OfficialOddsSnapshot:
    object_id: str
    snapshot_id: str
    contract_version: str
    match_id: str
    snapshot_kind: SnapshotKind
    created_at: str
    captured_at: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    source: str
    source_type: str
    source_reference: str
    source_is_official: bool
    evidence_ref: Optional[str]
    market_availability: Mapping[str, Mapping[str, Any]]
    market_unavailable_reason: Mapping[str, str]
    payloads: Mapping[str, Optional[Mapping[str, Any]]]
    snapshot_hash: str
    payload_hash: str
    provenance_hash: str
    observation_id: str
    supersedes_snapshot_id: Optional[str]
    revision: int
    revision_reason: Optional[str]
    metadata: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "object_id": self.object_id,
            "snapshot_id": self.snapshot_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "snapshot_kind": self.snapshot_kind.value,
            "created_at": self.created_at,
            "captured_at": self.captured_at,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_is_official": self.source_is_official,
            "evidence_ref": self.evidence_ref,
            "market_availability": {market: dict(self.market_availability[market]) for market in MARKETS},
            "market_unavailable_reason": dict(self.market_unavailable_reason),
            "snapshot_hash": self.snapshot_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
            "supersedes_snapshot_id": self.supersedes_snapshot_id,
            "revision": self.revision,
            "revision_reason": self.revision_reason,
            "metadata": dict(self.metadata),
        }
        result.update(self.payloads)
        return result


@dataclass(frozen=True)
class OfficialOddsIntakeResult:
    accepted: bool
    action: str
    observation_id: str
    snapshot: Optional[OfficialOddsSnapshot]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "action": self.action, "observation_id": self.observation_id, "snapshot": self.snapshot.to_dict() if self.snapshot else None, "error_code": self.error_code}


@dataclass(frozen=True)
class _OddsAppendEvent:
    sequence: int
    action: str
    observation_id: str
    snapshot_id: Optional[str]
    match_id: Optional[str]
    status: str
    error_code: Optional[str] = None


class OfficialOddsSnapshotStore:
    """Local append-only official odds store; it never writes a database."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-024 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._snapshots: Dict[str, OfficialOddsSnapshot] = {}
        self._observations: Dict[str, OfficialOddsObservation] = {}
        self._latest_by_match: Dict[str, OfficialOddsSnapshot] = {}
        self._events: List[_OddsAppendEvent] = []

    @property
    def snapshots(self) -> Tuple[OfficialOddsSnapshot, ...]:
        return tuple(self._snapshots.values())

    @property
    def observations(self) -> Tuple[OfficialOddsObservation, ...]:
        return tuple(self._observations.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType({
                "sequence": event.sequence,
                "action": event.action,
                "observation_id": event.observation_id,
                "snapshot_id": event.snapshot_id,
                "match_id": event.match_id,
                "status": event.status,
                "error_code": event.error_code,
            })
            for event in self._events
        )

    def get(self, snapshot_id: str) -> Optional[OfficialOddsSnapshot]:
        return self._snapshots.get(snapshot_id)

    def latest(self, match_id: str) -> Optional[OfficialOddsSnapshot]:
        return self._latest_by_match.get(match_id)

    def ingest(self, raw: Union[OfficialOddsObservation, Mapping[str, Any]]) -> OfficialOddsIntakeResult:
        try:
            observation = raw if isinstance(raw, OfficialOddsObservation) else OfficialOddsObservation.from_dict(raw)
        except (OfficialOddsValidationError, IdentityValidationError) as exc:
            observation_id = str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"blocked|{sha256_json(raw if isinstance(raw, Mapping) else raw.to_dict())}"))
            self._append_event("BLOCKED_VALIDATION", observation_id, None, None, "BLOCKED", getattr(exc, "code", "VALIDATION_FAILED"))
            return OfficialOddsIntakeResult(False, "BLOCKED_VALIDATION", observation_id, None, getattr(exc, "code", "VALIDATION_FAILED"))
        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((item for item in self._snapshots.values() if item.observation_id == observation_id), None)
            self._append_event("DUPLICATE_NOOP", observation_id, existing.snapshot_id if existing else None, observation.match_id, "DUPLICATE_NOOP")
            return OfficialOddsIntakeResult(True, "DUPLICATE_NOOP", observation_id, existing)
        identity = self._identity_store.get(observation.match_id)
        if identity is None:
            return self._blocked(observation, observation_id, "MATCH_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, observation_id, "MATCH_IDENTITY_NOT_RESOLVED")
        self._observations[observation_id] = observation
        logical = {
            "match_id": observation.match_id,
            "snapshot_kind": observation.snapshot_kind.value,
            "snapshot_id": observation.snapshot_id,
            "captured_at": _iso(observation.captured_at),
            "source_timestamp": observation.source_timestamp,
            "observed_at": _iso(observation.observed_at),
            "source": observation.source,
            "source_type": observation.source_type,
            "source_reference": observation.source_reference,
            "source_is_official": True,
            "market_availability": {market: dict(observation.market_availability[market]) for market in MARKETS},
            "market_unavailable_reason": dict(observation.market_unavailable_reason),
            "payloads": {market: observation.payloads[market] for market in MARKETS},
            "supersedes_snapshot_id": observation.supersedes_snapshot_id,
        }
        snapshot_id = observation.snapshot_id or str(uuid.uuid5(SNAPSHOT_NAMESPACE, f"snapshot|{sha256_json(logical)}"))
        if observation.snapshot_kind == SnapshotKind.CORRECTION and observation.supersedes_snapshot_id not in self._snapshots:
            return self._blocked(observation, observation_id, "SUPERSEDED_SNAPSHOT_NOT_FOUND")
        if observation.supersedes_snapshot_id:
            predecessor = self._snapshots.get(observation.supersedes_snapshot_id)
            if predecessor is None or predecessor.match_id != observation.match_id:
                return self._blocked(observation, observation_id, "SUPERSEDES_MATCH_CONFLICT")
        provenance_hash = sha256_json({
            "match_id": observation.match_id,
            "source": observation.source,
            "source_type": observation.source_type,
            "source_reference": observation.source_reference,
            "source_timestamp": observation.source_timestamp,
            "captured_at": _iso(observation.captured_at),
            "observed_at": _iso(observation.observed_at),
            "evidence_ref": observation.evidence_ref,
        })
        logical["snapshot_id"] = snapshot_id
        snapshot_hash = sha256_json(logical)
        for supplied, expected, field_name in (
            (observation.supplied_snapshot_hash, snapshot_hash, "snapshot_hash"),
            (observation.supplied_payload_hash, snapshot_hash, "payload_hash"),
            (observation.supplied_provenance_hash, provenance_hash, "provenance_hash"),
        ):
            if supplied is not None and supplied != expected:
                return self._blocked(observation, observation_id, "HASH_MISMATCH")
        predecessor = self._latest_by_match.get(observation.match_id)
        revision = predecessor.revision + 1 if predecessor else 1
        snapshot = OfficialOddsSnapshot(
            object_id=snapshot_id,
            snapshot_id=snapshot_id,
            contract_version=CONTRACT_VERSION,
            match_id=observation.match_id,
            snapshot_kind=observation.snapshot_kind,
            created_at=_iso(observation.created_at),
            captured_at=_iso(observation.captured_at),
            source_timestamp=observation.source_timestamp,
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            source=observation.source,
            source_type=observation.source_type,
            source_reference=observation.source_reference,
            source_is_official=True,
            evidence_ref=observation.evidence_ref,
            market_availability=observation.market_availability,
            market_unavailable_reason=observation.market_unavailable_reason,
            payloads=observation.payloads,
            snapshot_hash=snapshot_hash,
            payload_hash=snapshot_hash,
            provenance_hash=provenance_hash,
            observation_id=observation_id,
            supersedes_snapshot_id=observation.supersedes_snapshot_id,
            revision=revision,
            revision_reason=observation.revision_reason,
            metadata=observation.metadata,
        )
        self._snapshots[snapshot_id] = snapshot
        self._latest_by_match[observation.match_id] = snapshot
        self._append_event("APPEND_SNAPSHOT", observation_id, snapshot_id, observation.match_id, "AVAILABLE")
        return OfficialOddsIntakeResult(True, "APPENDED", observation_id, snapshot)

    def _blocked(self, observation: OfficialOddsObservation, observation_id: str, code: str) -> OfficialOddsIntakeResult:
        self._append_event("BLOCKED_BOUNDARY", observation_id, None, observation.match_id, "BLOCKED", code)
        return OfficialOddsIntakeResult(False, code, observation_id, None, code)

    def _append_event(self, action: str, observation_id: str, snapshot_id: Optional[str], match_id: Optional[str], status: str, error_code: Optional[str] = None) -> None:
        self._events.append(_OddsAppendEvent(len(self._events) + 1, action, observation_id, snapshot_id, match_id, status, error_code))
