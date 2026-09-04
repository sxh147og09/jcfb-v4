"""V4-020 canonical match identity and schedule intake.

This module is deliberately an in-memory, no-write boundary. It normalizes
source observations, resolves a stable V4 identity, and records append-only
mapping/conflict events for a future persistence adapter. It does not ingest
facts, run a model, or connect to a database.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.migration_harness.common import sha256_json


CONTRACT_VERSION = "canonical-match@1.0.0"
IDENTITY_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

SOURCE_TYPES = {
    "OFFICIAL_FEED",
    "OFFICIAL_DOCUMENT",
    "OFFICIAL_SCREENSHOT",
    "EXTERNAL_FEED",
    "MANUAL_VERIFIED",
}

FORBIDDEN_FIELDS = {
    "confidence",
    "confidence_grade",
    "engine",
    "engine_output",
    "interpretation",
    "model",
    "model_interpretation",
    "probability",
    "prediction",
    "recommendation",
    "risk",
    "score",
}

TIMEZONE_ALIASES = {
    "+00:00": "UTC",
    "00:00": "UTC",
    "GMT": "UTC",
    "UTC": "UTC",
    "Z": "UTC",
    "ETC/UTC": "UTC",
    "PRC": "Asia/Shanghai",
    "ASIA/CHONGQING": "Asia/Shanghai",
    "ASIA/HARBIN": "Asia/Shanghai",
    "ASIA/SHANGHAI": "Asia/Shanghai",
    "ASIA/URUMQI": "Asia/Shanghai",
    "ETC/GMT-8": "Asia/Shanghai",
    "+08:00": "Asia/Shanghai",
    "08:00": "Asia/Shanghai",
    "UTC+8": "Asia/Shanghai",
}


class IdentityValidationError(ValueError):
    """A source observation cannot form a safe canonical identity."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field_name: str, *, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise IdentityValidationError("REQUIRED_FIELD_MISSING", f"{field_name} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise IdentityValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
        return None
    return unicodedata.normalize("NFKC", value).strip()


def _key_text(value: Any, field_name: str, *, required: bool = True) -> Optional[str]:
    value = _text(value, field_name, required=required)
    return value.casefold() if value is not None else None


def _parse_timestamp(value: Any, field_name: str, *, required: bool = True) -> Optional[datetime]:
    raw = _text(value, field_name, required=required)
    if raw is None:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IdentityValidationError("TIMESTAMP_INVALID", f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentityValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field_name} must be timezone-aware")
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _normalize_timezone(value: Any) -> str:
    raw = _text(value, "timezone")
    assert raw is not None
    alias = TIMEZONE_ALIASES.get(raw.upper())
    candidate = alias or raw
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise IdentityValidationError("TIMEZONE_INVALID", f"timezone is not a recognized IANA zone: {raw}") from exc
    return candidate


def _walk_forbidden(value: Any, path: str = "metadata") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().casefold()
            if normalized in FORBIDDEN_FIELDS:
                return f"{path}.{key}"
            if any(token in normalized for token in ("v3.3.3", "v333", "jcfb_v3")):
                return f"{path}.{key}"
            found = _walk_forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _walk_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _source_observation_id(observation: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(observation, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return str(uuid.uuid5(IDENTITY_NAMESPACE, f"source-observation|{digest}"))


@dataclass(frozen=True)
class MatchObservation:
    """A single attributed schedule observation from one source."""

    source: str
    source_type: str
    source_reference: Optional[str]
    official_match_no: Optional[str]
    source_match_ref: Optional[str]
    data_date: str
    competition_id: str
    competition_name: str
    kickoff_at: datetime
    timezone: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    observed_at: datetime
    published_at: Optional[datetime]
    ingested_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MatchObservation":
        if not isinstance(raw, Mapping):
            raise IdentityValidationError("OBSERVATION_NOT_OBJECT", "match observation must be an object")
        forbidden = _walk_forbidden(raw)
        if forbidden:
            raise IdentityValidationError("MODEL_FIELD_FORBIDDEN", f"canonical identity cannot contain {forbidden}")

        source = _text(raw.get("source"), "source")
        source_type = _text(raw.get("source_type"), "source_type")
        assert source is not None and source_type is not None
        if source_type not in SOURCE_TYPES:
            raise IdentityValidationError("SOURCE_TYPE_INVALID", f"unsupported source_type: {source_type}")

        source_reference = _text(raw.get("source_reference"), "source_reference", required=False)
        if source_reference is None:
            raise IdentityValidationError("SOURCE_REFERENCE_REQUIRED", "source_reference is required for auditability")
        official_match_no = _text(
            raw.get("official_match_no", raw.get("official_match_ref")),
            "official_match_no",
            required=False,
        )
        source_match_ref = _text(raw.get("source_match_ref"), "source_match_ref", required=False)
        if official_match_no is None and source_match_ref is None:
            raise IdentityValidationError("MATCH_REFERENCE_REQUIRED", "official_match_no or source_match_ref is required")

        data_date = _text(raw.get("data_date"), "data_date")
        assert data_date is not None
        try:
            date.fromisoformat(data_date)
        except ValueError as exc:
            raise IdentityValidationError("DATA_DATE_INVALID", "data_date must be YYYY-MM-DD") from exc

        timezone_name = _normalize_timezone(raw.get("timezone"))
        kickoff = _parse_timestamp(raw.get("kickoff_at"), "kickoff_at")
        observed = _parse_timestamp(raw.get("observed_at"), "observed_at")
        published = _parse_timestamp(raw.get("published_at"), "published_at", required=False)
        ingested = _parse_timestamp(raw.get("ingested_at", raw.get("observed_at")), "ingested_at")
        assert kickoff is not None and observed is not None and ingested is not None

        expected_offset = kickoff.astimezone(ZoneInfo(timezone_name)).utcoffset()
        if kickoff.utcoffset() != expected_offset:
            raise IdentityValidationError("TIMEZONE_KICKOFF_CONFLICT", "kickoff_at offset conflicts with timezone")
        if published is not None and observed < published:
            raise IdentityValidationError("OBSERVED_BEFORE_PUBLISHED", "observed_at cannot precede published_at")

        values = {
            "competition_id": _key_text(raw.get("competition_id"), "competition_id"),
            "competition_name": _text(raw.get("competition_name"), "competition_name"),
            "home_team_id": _key_text(raw.get("home_team_id"), "home_team_id"),
            "home_team_name": _text(raw.get("home_team_name"), "home_team_name"),
            "away_team_id": _key_text(raw.get("away_team_id"), "away_team_id"),
            "away_team_name": _text(raw.get("away_team_name"), "away_team_name"),
        }
        if values["home_team_id"] == values["away_team_id"]:
            raise IdentityValidationError("TEAM_ID_COLLISION", "home_team_id and away_team_id must differ")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise IdentityValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        return cls(
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            official_match_no=official_match_no,
            source_match_ref=source_match_ref,
            data_date=data_date,
            competition_id=values["competition_id"],  # type: ignore[arg-type]
            competition_name=values["competition_name"],  # type: ignore[arg-type]
            kickoff_at=kickoff,
            timezone=timezone_name,
            home_team_id=values["home_team_id"],  # type: ignore[arg-type]
            home_team_name=values["home_team_name"],  # type: ignore[arg-type]
            away_team_id=values["away_team_id"],  # type: ignore[arg-type]
            away_team_name=values["away_team_name"],  # type: ignore[arg-type]
            observed_at=observed,
            published_at=published,
            ingested_at=ingested,
            metadata=MappingProxyType(dict(metadata)),
        )

    @property
    def observation_id(self) -> str:
        return _source_observation_id(self.to_dict())

    @property
    def normalized_kickoff_utc(self) -> str:
        return _iso(self.kickoff_at.astimezone(timezone.utc))

    @property
    def structural_key(self) -> str:
        return "|".join(
            [self.competition_id, self.home_team_id, self.away_team_id, self.normalized_kickoff_utc]
        )

    @property
    def source_ref(self) -> str:
        return self.source_match_ref or self.official_match_no or "UNKNOWN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "official_match_no": self.official_match_no,
            "source_match_ref": self.source_match_ref,
            "data_date": self.data_date,
            "competition_id": self.competition_id,
            "competition_name": self.competition_name,
            "kickoff_at": _iso(self.kickoff_at),
            "timezone": self.timezone,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "observed_at": _iso(self.observed_at),
            "published_at": _iso(self.published_at) if self.published_at else None,
            "ingested_at": _iso(self.ingested_at),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class IdentityConflict:
    code: str
    field: str
    reason: str
    existing_observation_id: Optional[str]
    incoming_observation_id: str
    existing_source_reference: Optional[str]
    incoming_source_reference: Optional[str]
    existing_value: Any
    incoming_value: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "reason": self.reason,
            "existing_observation_id": self.existing_observation_id,
            "incoming_observation_id": self.incoming_observation_id,
            "existing_source_reference": self.existing_source_reference,
            "incoming_source_reference": self.incoming_source_reference,
            "existing_value": self.existing_value,
            "incoming_value": self.incoming_value,
        }


@dataclass(frozen=True)
class CanonicalMatchIdentityEnvelope:
    """The V4-020 identity envelope; no model interpretation fields are allowed."""

    object_id: str
    contract_version: str
    created_at: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    source: str
    source_type: str
    source_reference: str
    provenance_hash: str
    payload_hash: str
    status: str
    metadata: Mapping[str, Any]
    match_id: str
    match_identity_key: str
    data_date: str
    official_match_no: str
    competition_id: str
    competition_name: str
    kickoff_at: str
    timezone: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    match_status: str
    identity_resolution_state: str
    identity_conflicts: Tuple[IdentityConflict, ...] = ()
    published_at: Optional[str] = None
    revision: int = 1
    supersedes_object_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "created_at": self.created_at,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "published_at": self.published_at,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
            "status": self.status,
            "metadata": dict(self.metadata),
            "match_id": self.match_id,
            "match_identity_key": self.match_identity_key,
            "data_date": self.data_date,
            "official_match_no": self.official_match_no,
            "competition_id": self.competition_id,
            "competition_name": self.competition_name,
            "kickoff_at": self.kickoff_at,
            "timezone": self.timezone,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "match_status": self.match_status,
            "identity_resolution_state": self.identity_resolution_state,
            "identity_conflicts": [item.to_dict() for item in self.identity_conflicts],
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
        }


@dataclass(frozen=True)
class IdentityIntakeResult:
    accepted: bool
    status: str
    resolution_action: str
    canonical_match_id: Optional[str]
    business_key: Optional[str]
    observation_id: str
    envelope: Optional[CanonicalMatchIdentityEnvelope]
    conflicts: Tuple[IdentityConflict, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "resolution_action": self.resolution_action,
            "canonical_match_id": self.canonical_match_id,
            "business_key": self.business_key,
            "observation_id": self.observation_id,
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "conflicts": [item.to_dict() for item in self.conflicts],
        }


@dataclass(frozen=True)
class _AppendOnlyEvent:
    sequence: int
    action: str
    observation_id: str
    canonical_match_id: Optional[str]
    business_key: Optional[str]
    conflicts: Tuple[IdentityConflict, ...] = ()


class CanonicalMatchIdentityStore:
    """Append-only identity resolver for local/unit-test use only."""

    def __init__(self) -> None:
        self._envelopes_by_business_key: Dict[str, CanonicalMatchIdentityEnvelope] = {}
        self._envelopes_by_match_id: Dict[str, CanonicalMatchIdentityEnvelope] = {}
        self._match_id_by_structural_key: Dict[str, str] = {}
        self._observations: Dict[str, MatchObservation] = {}
        self._delivery_keys: Dict[Tuple[str, str, str], str] = {}
        self._events: List[_AppendOnlyEvent] = []

    @property
    def observations(self) -> Tuple[MatchObservation, ...]:
        return tuple(self._observations.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "observation_id": event.observation_id,
                    "canonical_match_id": event.canonical_match_id,
                    "business_key": event.business_key,
                    "conflicts": [item.to_dict() for item in event.conflicts],
                }
            )
            for event in self._events
        )

    def get(self, match_id: str) -> Optional[CanonicalMatchIdentityEnvelope]:
        return self._envelopes_by_match_id.get(match_id)

    def ingest(self, raw: Union[MatchObservation, Mapping[str, Any]]) -> IdentityIntakeResult:
        try:
            observation = raw if isinstance(raw, MatchObservation) else MatchObservation.from_dict(raw)
        except IdentityValidationError as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            self._events.append(_AppendOnlyEvent(len(self._events) + 1, "BLOCKED_VALIDATION", observation_id, None, None))
            return IdentityIntakeResult(
                accepted=False,
                status="BLOCKED",
                resolution_action=exc.code,
                canonical_match_id=None,
                business_key=None,
                observation_id=observation_id,
                envelope=None,
                conflicts=(
                    IdentityConflict(
                        code=exc.code,
                        field="identity",
                        reason=exc.message,
                        existing_observation_id=None,
                        incoming_observation_id=observation_id,
                        existing_source_reference=None,
                        incoming_source_reference=raw.get("source_reference") if isinstance(raw, Mapping) else observation.source_reference,
                        existing_value=None,
                        incoming_value=None,
                    ),
                ),
            )

        observation_id = observation.observation_id
        self._observations.setdefault(observation_id, observation)
        business_key = (
            f"{observation.data_date}:{observation.official_match_no}"
            if observation.official_match_no
            else None
        )
        delivery_key = (observation.source.casefold(), observation.source_reference or "UNKNOWN", self._payload_hash(observation))
        if delivery_key in self._delivery_keys:
            match_id = self._delivery_keys[delivery_key]
            envelope = self._envelopes_by_match_id.get(match_id)
            self._events.append(_AppendOnlyEvent(len(self._events) + 1, "DUPLICATE_NOOP", observation_id, match_id, business_key))
            return IdentityIntakeResult(True, "AVAILABLE", "DUPLICATE_NOOP", match_id, business_key, observation_id, envelope)

        if observation.official_match_no is None:
            existing_match_id = self._match_id_by_structural_key.get(observation.structural_key)
            if existing_match_id:
                envelope = self._envelopes_by_match_id[existing_match_id]
                conflicts = self._compare(envelope, observation, observation_id)
                if conflicts:
                    self._events.append(_AppendOnlyEvent(len(self._events) + 1, "BLOCKED_CONFLICT", observation_id, existing_match_id, envelope.match_identity_key, tuple(conflicts)))
                    return IdentityIntakeResult(False, "BLOCKED", "REQUIRES_REVIEW", existing_match_id, envelope.match_identity_key, observation_id, envelope, tuple(conflicts))
                self._delivery_keys[delivery_key] = existing_match_id
                self._events.append(_AppendOnlyEvent(len(self._events) + 1, "CROSS_SOURCE_ALIAS", observation_id, existing_match_id, envelope.match_identity_key))
                return IdentityIntakeResult(True, "AVAILABLE", "CROSS_SOURCE_ALIAS", existing_match_id, envelope.match_identity_key, observation_id, envelope)
            conflict = self._conflict("OFFICIAL_MATCH_REF_REQUIRED", "official_match_no", "canonical root requires an official match reference", None, observation)
            self._events.append(_AppendOnlyEvent(len(self._events) + 1, "BLOCKED_MISSING_OFFICIAL_REF", observation_id, None, None, (conflict,)))
            return IdentityIntakeResult(False, "BLOCKED", "OFFICIAL_MATCH_REF_REQUIRED", None, None, observation_id, None, (conflict,))

        existing = self._envelopes_by_business_key.get(business_key)
        if existing:
            conflicts = self._compare(existing, observation, observation_id)
            if conflicts:
                self._events.append(_AppendOnlyEvent(len(self._events) + 1, "BLOCKED_CONFLICT", observation_id, existing.match_id, business_key, tuple(conflicts)))
                return IdentityIntakeResult(False, "BLOCKED", "REQUIRES_REVIEW", existing.match_id, business_key, observation_id, existing, tuple(conflicts))
            self._delivery_keys[delivery_key] = existing.match_id
            self._events.append(_AppendOnlyEvent(len(self._events) + 1, "SOURCE_ALIAS", observation_id, existing.match_id, business_key))
            return IdentityIntakeResult(True, "AVAILABLE", "SOURCE_ALIAS", existing.match_id, business_key, observation_id, existing)

        structural_match_id = self._match_id_by_structural_key.get(observation.structural_key)
        if structural_match_id:
            envelope = self._envelopes_by_match_id[structural_match_id]
            conflicts = self._compare(envelope, observation, observation_id)
            if conflicts:
                self._events.append(_AppendOnlyEvent(len(self._events) + 1, "BLOCKED_CONFLICT", observation_id, structural_match_id, envelope.match_identity_key, tuple(conflicts)))
                return IdentityIntakeResult(False, "BLOCKED", "REQUIRES_REVIEW", structural_match_id, envelope.match_identity_key, observation_id, envelope, tuple(conflicts))
            self._delivery_keys[delivery_key] = structural_match_id
            self._events.append(_AppendOnlyEvent(len(self._events) + 1, "CROSS_SOURCE_ALIAS", observation_id, structural_match_id, envelope.match_identity_key))
            return IdentityIntakeResult(True, "AVAILABLE", "CROSS_SOURCE_ALIAS", structural_match_id, envelope.match_identity_key, observation_id, envelope)

        match_id = str(uuid.uuid5(IDENTITY_NAMESPACE, f"match|{business_key}"))
        envelope = self._build_envelope(observation, match_id, business_key)
        self._envelopes_by_business_key[business_key] = envelope
        self._envelopes_by_match_id[match_id] = envelope
        self._match_id_by_structural_key[observation.structural_key] = match_id
        self._delivery_keys[delivery_key] = match_id
        self._events.append(_AppendOnlyEvent(len(self._events) + 1, "ROOT_CREATED", observation_id, match_id, business_key))
        return IdentityIntakeResult(True, "AVAILABLE", "ROOT_CREATED", match_id, business_key, observation_id, envelope)

    @staticmethod
    def _payload_hash(observation: MatchObservation) -> str:
        return sha256_json(
            {
                "match_identity_key": f"{observation.data_date}:{observation.official_match_no}" if observation.official_match_no else None,
                "data_date": observation.data_date,
                "official_match_no": observation.official_match_no,
                "competition_id": observation.competition_id,
                "competition_name": observation.competition_name,
                "kickoff_at": _iso(observation.kickoff_at),
                "timezone": observation.timezone,
                "home_team_id": observation.home_team_id,
                "home_team_name": observation.home_team_name,
                "away_team_id": observation.away_team_id,
                "away_team_name": observation.away_team_name,
                "source": observation.source,
                "source_type": observation.source_type,
                "source_reference": observation.source_reference,
            }
        )

    @classmethod
    def _build_envelope(cls, observation: MatchObservation, match_id: str, business_key: str) -> CanonicalMatchIdentityEnvelope:
        payload_hash = cls._payload_hash(observation)
        provenance_hash = sha256_json(
            {
                "source": observation.source,
                "source_type": observation.source_type,
                "source_reference": observation.source_reference,
                "source_match_ref": observation.source_ref,
                "published_at": _iso(observation.published_at) if observation.published_at else None,
                "observed_at": _iso(observation.observed_at),
            }
        )
        object_id = str(uuid.uuid5(IDENTITY_NAMESPACE, f"object|{business_key}|1"))
        metadata = {
            "identity_namespace": str(IDENTITY_NAMESPACE),
            "hash_exclusions": ["created_at", "ingested_at", "observed_at", "published_at"],
            "source_match_ref": observation.source_ref,
            "append_only_boundary": "V4-020 local event ledger; persistence adapter deferred",
        }
        return CanonicalMatchIdentityEnvelope(
            object_id=object_id,
            contract_version=CONTRACT_VERSION,
            created_at=_iso(observation.ingested_at),
            source_timestamp=_iso(observation.published_at or observation.observed_at),
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            published_at=_iso(observation.published_at) if observation.published_at else None,
            source=observation.source,
            source_type=observation.source_type,
            source_reference=observation.source_reference or "UNKNOWN",
            provenance_hash=provenance_hash,
            payload_hash=payload_hash,
            status="AVAILABLE",
            metadata=MappingProxyType(metadata),
            match_id=match_id,
            match_identity_key=business_key,
            data_date=observation.data_date,
            official_match_no=observation.official_match_no or "UNKNOWN",
            competition_id=observation.competition_id,
            competition_name=observation.competition_name,
            kickoff_at=_iso(observation.kickoff_at),
            timezone=observation.timezone,
            home_team_id=observation.home_team_id,
            home_team_name=observation.home_team_name,
            away_team_id=observation.away_team_id,
            away_team_name=observation.away_team_name,
            match_status="SCHEDULED",
            identity_resolution_state="RESOLVED",
        )

    @staticmethod
    def _conflict(code: str, field: str, reason: str, existing: Optional[CanonicalMatchIdentityEnvelope], incoming: MatchObservation, observation_id: str) -> IdentityConflict:
        return IdentityConflict(
            code=code,
            field=field,
            reason=reason,
            existing_observation_id=None,
            incoming_observation_id=observation_id,
            existing_source_reference=existing.source_reference if existing else None,
            incoming_source_reference=incoming.source_reference,
            existing_value=None,
            incoming_value=None,
        )

    @classmethod
    def _compare(cls, existing: CanonicalMatchIdentityEnvelope, incoming: MatchObservation, observation_id: str) -> List[IdentityConflict]:
        comparisons = (
            ("competition_id", existing.competition_id, incoming.competition_id, "COMPETITION_ID_CONFLICT"),
            (
                "kickoff_at",
                _iso(datetime.fromisoformat(existing.kickoff_at).astimezone(timezone.utc)),
                incoming.normalized_kickoff_utc,
                "KICKOFF_CONFLICT",
            ),
            ("timezone", existing.timezone, incoming.timezone, "TIMEZONE_CONFLICT"),
            ("home_team_id", existing.home_team_id, incoming.home_team_id, "HOME_AWAY_ORIENTATION_CONFLICT"),
            ("away_team_id", existing.away_team_id, incoming.away_team_id, "HOME_AWAY_ORIENTATION_CONFLICT"),
        )
        conflicts: List[IdentityConflict] = []
        for field_name, old_value, new_value, code in comparisons:
            if old_value != new_value:
                conflicts.append(
                    IdentityConflict(
                        code=code,
                        field=field_name,
                        reason=f"{field_name} differs; automatic merge is forbidden",
                        existing_observation_id=None,
                        incoming_observation_id=observation_id,
                        existing_source_reference=existing.source_reference,
                        incoming_source_reference=incoming.source_reference,
                        existing_value=old_value,
                        incoming_value=new_value,
                    )
                )
        return conflicts


def resolve_f_drive_output_path(project_root: Union[str, Path], relative_path: str) -> Path:
    """Resolve a runtime/output path and reject non-F-drive project roots."""

    root = Path(project_root).resolve()
    if root.drive.upper() != "F:":
        raise ValueError("V4 runtime and output root must be on the F: drive")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("runtime/output path must remain inside the F-drive project root") from exc
    return candidate
