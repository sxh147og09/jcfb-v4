"""V4-021 typed canonical fact envelopes.

This module is a local, in-memory, no-write boundary.  It validates one
objective fact observation, binds it to an already-resolved V4-020 canonical
match identity, and retains immutable revisions/events for later persistence.
Cutoff admission, source-time selection, and full orchestration are deferred
to V4-022 and V4-023.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import (
    CanonicalMatchIdentityStore,
    IdentityValidationError,
    _iso,
    _parse_timestamp,
    _source_observation_id,
)


CONTRACT_VERSION = "canonical-fact@1.0.0"
FACT_ID_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    BLOCKED = "BLOCKED"


NON_AVAILABLE_STATUSES = frozenset(
    {
        AvailabilityStatus.UNKNOWN,
        AvailabilityStatus.UNAVAILABLE,
        AvailabilityStatus.CONFLICT,
        AvailabilityStatus.STALE,
        AvailabilityStatus.FUTURE_DATA,
        AvailabilityStatus.BLOCKED,
    }
)

# These are model-line fields, even when nested under payload or metadata.
# Objective fact payloads may contain a source's factual score, but the V4-021
# envelope cannot contain a model score/engine result.
FORBIDDEN_FACT_FIELDS = frozenset(
    {
        "prediction",
        "recommendation",
        "confidence",
        "model_interpretation",
        "modelinterpretation",
        "engine_output",
        "engineoutput",
        "score_engine",
        "scoreengine",
    }
)


class FactEnvelopeValidationError(ValueError):
    """An objective fact cannot be represented safely by the V4-021 contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactEnvelopeValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _validate_uuid(value: Any, field_name: str) -> str:
    result = _require_text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise FactEnvelopeValidationError("IDENTITY_REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _validate_hash(value: Any, field_name: str) -> str:
    result = _require_text(value, field_name)
    if not HASH_RE.fullmatch(result):
        raise FactEnvelopeValidationError("HASH_INVALID", f"{field_name} must be a sha256 hash reference")
    return result


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).strip().casefold())


def _find_forbidden(value: Any, path: str) -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if "v333" in normalized or "v3_3_3" in normalized:
                return f"{path}.{key}"
            if normalized in FORBIDDEN_FACT_FIELDS or any(
                token in normalized
                for token in (
                    "prediction",
                    "recommendation",
                    "confidence",
                    "modelinterpretation",
                    "engineoutput",
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


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise FactEnvelopeValidationError("PAYLOAD_KEY_INVALID", f"{path} keys must be strings")
        for key, child in value.items():
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    raise FactEnvelopeValidationError("PAYLOAD_TYPE_INVALID", f"{path} is not JSON-compatible")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _validate_payload(value: Any, field_name: str, *, required: bool) -> Optional[Mapping[str, Any]]:
    if value is None:
        if required:
            raise FactEnvelopeValidationError("PAYLOAD_REQUIRED", f"{field_name} is required for AVAILABLE")
        return None
    if not isinstance(value, Mapping):
        raise FactEnvelopeValidationError("PAYLOAD_TYPE_INVALID", f"{field_name} must be a JSON object")
    _validate_json_value(value, field_name)
    forbidden = _find_forbidden(value, field_name)
    if forbidden:
        raise FactEnvelopeValidationError("MODEL_FIELD_FORBIDDEN", f"canonical facts cannot contain {forbidden}")
    if required and not value:
        raise FactEnvelopeValidationError("PAYLOAD_EMPTY", "AVAILABLE facts require a non-empty payload")
    return value


@dataclass(frozen=True)
class CanonicalMatchReference:
    """The only subject type admitted by V4-021."""

    match_id: str
    match_identity_key: str

    @classmethod
    def from_dict(cls, raw: Any) -> "CanonicalMatchReference":
        if not isinstance(raw, Mapping):
            raise FactEnvelopeValidationError("SUBJECT_INVALID", "subject must be an object")
        return cls(
            match_id=_validate_uuid(raw.get("match_id"), "subject.match_id"),
            match_identity_key=_require_text(raw.get("match_identity_key"), "subject.match_identity_key"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {"match_id": self.match_id, "match_identity_key": self.match_identity_key}


@dataclass(frozen=True)
class FactConflictEvidence:
    """Immutable source-side evidence retained for a CONFLICT fact."""

    source: str
    source_ref: str
    payload: Mapping[str, Any]
    provenance_ref: str
    provenance_hash: str
    observation_id: str

    @classmethod
    def from_dict(cls, raw: Any, *, fallback_observation_id: str) -> "FactConflictEvidence":
        if not isinstance(raw, Mapping):
            raise FactEnvelopeValidationError("CONFLICT_EVIDENCE_INVALID", "conflict evidence must be an object")
        source = _require_text(raw.get("source"), "conflict_evidence.source")
        source_ref = _require_text(raw.get("source_ref"), "conflict_evidence.source_ref")
        payload = _validate_payload(raw.get("payload"), "conflict_evidence.payload", required=True)
        assert payload is not None
        provenance_ref = _require_text(raw.get("provenance_ref", source_ref), "conflict_evidence.provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = (
            _validate_hash(supplied_hash, "conflict_evidence.provenance_hash")
            if supplied_hash is not None
            else sha256_json({"source": source, "source_ref": source_ref, "provenance_ref": provenance_ref})
        )
        observation_id = raw.get("observation_id", fallback_observation_id)
        return cls(
            source=source,
            source_ref=source_ref,
            payload=_freeze_json(payload),
            provenance_ref=provenance_ref,
            provenance_hash=provenance_hash,
            observation_id=_require_text(observation_id, "conflict_evidence.observation_id"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_ref": self.source_ref,
            "payload": _thaw_json(self.payload),
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
        }


@dataclass(frozen=True)
class CanonicalFactObservation:
    """Validated source observation before it is assigned a fact revision."""

    fact_type: str
    subject: CanonicalMatchReference
    source: str
    source_ref: str
    payload: Optional[Mapping[str, Any]]
    availability_status: AvailabilityStatus
    reason_code: Optional[str]
    reason_detail: Optional[str]
    published_at: Optional[datetime]
    observed_at: datetime
    ingested_at: datetime
    provenance_ref: str
    provenance_hash: Optional[str]
    conflict_evidence: Tuple[FactConflictEvidence, ...] = ()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CanonicalFactObservation":
        if not isinstance(raw, Mapping):
            raise FactEnvelopeValidationError("OBSERVATION_NOT_OBJECT", "fact observation must be an object")
        forbidden = _find_forbidden(raw, "observation")
        if forbidden:
            raise FactEnvelopeValidationError("MODEL_FIELD_FORBIDDEN", f"canonical facts cannot contain {forbidden}")
        if "availability_status" not in raw:
            raise FactEnvelopeValidationError(
                "AVAILABILITY_STATUS_REQUIRED",
                "availability_status is required; status/empty payload inference is forbidden",
            )
        raw_status = raw.get("availability_status")
        if not isinstance(raw_status, str):
            raise FactEnvelopeValidationError("AVAILABILITY_STATUS_INVALID", "availability_status must be an exact string enum")
        try:
            status = AvailabilityStatus(raw_status)
        except ValueError as exc:
            raise FactEnvelopeValidationError("AVAILABILITY_STATUS_INVALID", f"unsupported availability_status: {raw_status}") from exc

        fact_type = _require_text(raw.get("fact_type"), "fact_type")
        subject = CanonicalMatchReference.from_dict(raw.get("subject"))
        source = _require_text(raw.get("source"), "source")
        source_ref = _require_text(raw.get("source_ref"), "source_ref")
        payload = _validate_payload(raw.get("payload"), "payload", required=status == AvailabilityStatus.AVAILABLE)

        reason_code = raw.get("reason_code")
        reason_detail = raw.get("reason_detail")
        if status in NON_AVAILABLE_STATUSES:
            reason_code = _require_text(reason_code, "reason_code")
            if not REASON_CODE_RE.fullmatch(reason_code):
                raise FactEnvelopeValidationError("REASON_CODE_INVALID", "reason_code must be an uppercase stable code")
        elif reason_code is not None:
            reason_code = _require_text(reason_code, "reason_code")
            if not REASON_CODE_RE.fullmatch(reason_code):
                raise FactEnvelopeValidationError("REASON_CODE_INVALID", "reason_code must be an uppercase stable code")
        if reason_detail is not None:
            reason_detail = _require_text(reason_detail, "reason_detail")
        if reason_detail is not None and reason_code is None:
            raise FactEnvelopeValidationError("REASON_CODE_REQUIRED", "reason_detail requires reason_code")

        published_at = _parse_timestamp(raw.get("published_at"), "published_at", required=False)
        observed_at = _parse_timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _parse_timestamp(raw.get("ingested_at"), "ingested_at")
        assert observed_at is not None and ingested_at is not None

        provenance_ref = _require_text(raw.get("provenance_ref", source_ref), "provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = _validate_hash(supplied_hash, "provenance_hash") if supplied_hash is not None else None

        fallback_id = _source_observation_id(_observation_identity_dict(raw))
        evidence_raw = raw.get("conflict_evidence", ())
        if evidence_raw is None:
            evidence_raw = ()
        if not isinstance(evidence_raw, (list, tuple)):
            raise FactEnvelopeValidationError("CONFLICT_EVIDENCE_INVALID", "conflict_evidence must be an array")
        evidence = tuple(
            FactConflictEvidence.from_dict(item, fallback_observation_id=fallback_id) for item in evidence_raw
        )
        if status == AvailabilityStatus.CONFLICT and len(evidence) < 2:
            raise FactEnvelopeValidationError("CONFLICT_EVIDENCE_REQUIRED", "CONFLICT requires at least two retained source sides")
        if status != AvailabilityStatus.CONFLICT and evidence:
            raise FactEnvelopeValidationError("CONFLICT_EVIDENCE_STATUS_MISMATCH", "conflict_evidence requires CONFLICT")

        return cls(
            fact_type=fact_type,
            subject=subject,
            source=source,
            source_ref=source_ref,
            payload=_freeze_json(payload) if payload is not None else None,
            availability_status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            published_at=published_at,
            observed_at=observed_at,
            ingested_at=ingested_at,
            provenance_ref=provenance_ref,
            provenance_hash=provenance_hash,
            conflict_evidence=evidence,
        )

    @property
    def observation_id(self) -> str:
        return _source_observation_id(_observation_identity_dict(self.to_dict()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_type": self.fact_type,
            "subject": self.subject.to_dict(),
            "source": self.source,
            "source_ref": self.source_ref,
            "payload": _thaw_json(self.payload) if self.payload is not None else None,
            "availability_status": self.availability_status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "published_at": _iso(self.published_at) if self.published_at else None,
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "conflict_evidence": [item.to_dict() for item in self.conflict_evidence],
        }


def _observation_identity_dict(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Exclude transport-only values that are not fact observation identity."""

    return {
        "fact_type": raw.get("fact_type"),
        "subject": raw.get("subject"),
        "source": raw.get("source"),
        "source_ref": raw.get("source_ref"),
        "payload": raw.get("payload"),
        "availability_status": raw.get("availability_status"),
        "reason_code": raw.get("reason_code"),
        "reason_detail": raw.get("reason_detail"),
        "published_at": raw.get("published_at"),
        "observed_at": raw.get("observed_at"),
        "provenance_ref": raw.get("provenance_ref"),
        "provenance_hash": raw.get("provenance_hash"),
        "conflict_evidence": raw.get("conflict_evidence", []),
    }


@dataclass(frozen=True)
class CanonicalFactEnvelope:
    """Immutable typed fact envelope bound to one V4-020 canonical match."""

    object_id: str
    contract_version: str
    schema_version: str
    fact_type: str
    subject: CanonicalMatchReference
    source: str
    source_ref: str
    payload: Optional[Mapping[str, Any]]
    availability_status: AvailabilityStatus
    reason_code: Optional[str]
    reason_detail: Optional[str]
    published_at: Optional[str]
    observed_at: str
    ingested_at: str
    provenance_ref: str
    provenance_hash: str
    payload_hash: str
    observation_id: str
    revision: int
    supersedes_object_id: Optional[str]
    conflict_evidence: Tuple[FactConflictEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "schema_version": self.schema_version,
            "fact_type": self.fact_type,
            "subject": self.subject.to_dict(),
            "source": self.source,
            "source_ref": self.source_ref,
            "payload": _thaw_json(self.payload) if self.payload is not None else None,
            "availability_status": self.availability_status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "published_at": self.published_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
            "observation_id": self.observation_id,
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
            "conflict_evidence": [item.to_dict() for item in self.conflict_evidence],
            "metadata": _thaw_json(self.metadata),
        }


@dataclass(frozen=True)
class FactIntakeResult:
    accepted: bool
    status: AvailabilityStatus
    action: str
    observation_id: str
    envelope: Optional[CanonicalFactEnvelope]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status.value,
            "action": self.action,
            "observation_id": self.observation_id,
            "envelope": self.envelope.to_dict() if self.envelope else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _FactAppendEvent:
    sequence: int
    action: str
    observation_id: str
    object_id: Optional[str]
    supersedes_object_id: Optional[str]
    status: AvailabilityStatus
    error_code: Optional[str] = None


class CanonicalFactStore:
    """Local append-only fact boundary; no database or Supabase connection."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-021 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._envelopes: Dict[str, CanonicalFactEnvelope] = {}
        self._latest_by_key: Dict[Tuple[str, str], CanonicalFactEnvelope] = {}
        self._observations: Dict[str, CanonicalFactObservation] = {}
        self._events: List[_FactAppendEvent] = []

    @property
    def observations(self) -> Tuple[CanonicalFactObservation, ...]:
        return tuple(self._observations.values())

    @property
    def envelopes(self) -> Tuple[CanonicalFactEnvelope, ...]:
        return tuple(self._envelopes.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "observation_id": event.observation_id,
                    "object_id": event.object_id,
                    "supersedes_object_id": event.supersedes_object_id,
                    "availability_status": event.status.value,
                    "error_code": event.error_code,
                }
            )
            for event in self._events
        )

    def get(self, object_id: str) -> Optional[CanonicalFactEnvelope]:
        return self._envelopes.get(object_id)

    def latest(self, match_id: str, fact_type: str) -> Optional[CanonicalFactEnvelope]:
        return self._latest_by_key.get((match_id, fact_type))

    def ingest(self, raw: Union[CanonicalFactObservation, Mapping[str, Any]]) -> FactIntakeResult:
        try:
            observation = raw if isinstance(raw, CanonicalFactObservation) else CanonicalFactObservation.from_dict(raw)
        except (FactEnvelopeValidationError, IdentityValidationError) as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._append_event("BLOCKED_VALIDATION", observation_id, None, None, AvailabilityStatus.BLOCKED, code)
            return FactIntakeResult(False, AvailabilityStatus.BLOCKED, code, observation_id, None, code)

        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = self._envelopes.get(
                str(uuid.uuid5(FACT_ID_NAMESPACE, f"fact|{observation.subject.match_id}|{observation.fact_type}|{observation_id}"))
            )
            self._append_event(
                "DUPLICATE_NOOP",
                observation_id,
                existing.object_id if existing else None,
                existing.supersedes_object_id if existing else None,
                observation.availability_status,
            )
            return FactIntakeResult(True, observation.availability_status, "DUPLICATE_NOOP", observation_id, existing)

        identity = self._identity_store.get(observation.subject.match_id)
        if identity is None:
            return self._blocked_identity(observation, "SUBJECT_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked_identity(observation, "SUBJECT_IDENTITY_NOT_RESOLVED")
        if identity.match_identity_key != observation.subject.match_identity_key:
            return self._blocked_identity(observation, "SUBJECT_IDENTITY_KEY_CONFLICT")

        self._observations[observation_id] = observation
        key = (observation.subject.match_id, observation.fact_type)
        predecessor = self._latest_by_key.get(key)
        revision = predecessor.revision + 1 if predecessor else 1
        object_id = str(uuid.uuid5(FACT_ID_NAMESPACE, f"fact|{observation.subject.match_id}|{observation.fact_type}|{observation_id}"))
        provenance_hash = observation.provenance_hash or sha256_json(
            {
                "source": observation.source,
                "source_ref": observation.source_ref,
                "provenance_ref": observation.provenance_ref,
                "published_at": _iso(observation.published_at) if observation.published_at else None,
                "observed_at": _iso(observation.observed_at),
            }
        )
        payload_hash = sha256_json(
            {
                "fact_type": observation.fact_type,
                "subject": observation.subject.to_dict(),
                "source": observation.source,
                "source_ref": observation.source_ref,
                "payload": _thaw_json(observation.payload) if observation.payload is not None else None,
                "availability_status": observation.availability_status.value,
                "reason_code": observation.reason_code,
                "reason_detail": observation.reason_detail,
                "conflict_evidence": [item.to_dict() for item in observation.conflict_evidence],
            }
        )
        envelope = CanonicalFactEnvelope(
            object_id=object_id,
            contract_version=CONTRACT_VERSION,
            schema_version="canonical-fact-envelope@1.0.0",
            fact_type=observation.fact_type,
            subject=observation.subject,
            source=observation.source,
            source_ref=observation.source_ref,
            payload=observation.payload,
            availability_status=observation.availability_status,
            reason_code=observation.reason_code,
            reason_detail=observation.reason_detail,
            published_at=_iso(observation.published_at) if observation.published_at else None,
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            provenance_ref=observation.provenance_ref,
            provenance_hash=provenance_hash,
            payload_hash=payload_hash,
            observation_id=observation_id,
            revision=revision,
            supersedes_object_id=predecessor.object_id if predecessor else None,
            conflict_evidence=observation.conflict_evidence,
            metadata=MappingProxyType(
                {
                    "append_only_boundary": "V4-021 local observation ledger; V4-023 orchestrator deferred",
                    "cutoff_gate": "V4-022 deferred",
                    "identity_object_id": identity.object_id,
                }
            ),
        )
        self._envelopes[object_id] = envelope
        self._latest_by_key[key] = envelope
        self._append_event(
            "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED",
            observation_id,
            object_id,
            predecessor.object_id if predecessor else None,
            observation.availability_status,
        )
        return FactIntakeResult(True, observation.availability_status, "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", observation_id, envelope)

    def _blocked_identity(self, observation: CanonicalFactObservation, code: str) -> FactIntakeResult:
        observation_id = observation.observation_id
        self._observations[observation_id] = observation
        self._append_event("BLOCKED_IDENTITY", observation_id, None, None, AvailabilityStatus.BLOCKED, code)
        return FactIntakeResult(False, AvailabilityStatus.BLOCKED, code, observation_id, None, code)

    def _append_event(
        self,
        action: str,
        observation_id: str,
        object_id: Optional[str],
        supersedes_object_id: Optional[str],
        status: AvailabilityStatus,
        error_code: Optional[str] = None,
    ) -> None:
        self._events.append(
            _FactAppendEvent(
                sequence=len(self._events) + 1,
                action=action,
                observation_id=observation_id,
                object_id=object_id,
                supersedes_object_id=supersedes_object_id,
                status=status,
                error_code=error_code,
            )
        )
