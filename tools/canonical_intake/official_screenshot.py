"""V4-025 official odds screenshot and OCR/manual verification boundary.

The store is local, in-memory, and append-only.  It records source-bound
image evidence and extraction results without running OCR or writing a
database.  Unreadable or conflicting extraction remains explicit for the
later V4-026 availability gate.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore, IdentityValidationError, _iso, _parse_timestamp
from .official_odds import OfficialOddsValidationError, MARKETS, _find_model_field, _hash, _text, _timestamp, _validate_market_payload


CONTRACT_VERSION = "evidence@1.0.0"
SCREENSHOT_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
VERIFICATION_STATES = frozenset({"VERIFIED", "NOT_VERIFIED", "CONFLICTED", "REJECTED"})
MARKET_STATES = frozenset({"VERIFIED", "UNAVAILABLE", "NOT_VERIFIED", "CONFLICTED", "BLOCKED"})
METHODS = frozenset({"OCR", "MANUAL_TRANSCRIPTION", "OCR_PLUS_MANUAL"})


class ScreenshotVerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONFLICTED = "CONFLICTED"
    REJECTED = "REJECTED"


class ScreenshotValidationError(ValueError):
    """Official screenshot evidence is not safe to accept."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise ScreenshotValidationError("IDENTITY_REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _source_time(value: Any) -> str:
    if isinstance(value, str) and value.strip().upper() in {"UNKNOWN", "CONFLICTED"}:
        return value.strip().upper()
    return _iso(_timestamp(value, "source_timestamp"))


def _candidate(market: str, raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ScreenshotValidationError("CONFLICT_CANDIDATE_INVALID", f"{market} candidate must be an object")
    method = _text(raw.get("method"), f"{market}.candidate.method")
    if method not in METHODS:
        raise ScreenshotValidationError("EXTRACTION_METHOD_INVALID", f"unsupported extraction method: {method}")
    raw_text = _text(raw.get("raw_text"), f"{market}.candidate.raw_text")
    payload = _validate_market_payload(market, raw.get("payload"))
    return {"method": method, "raw_text": raw_text, "payload": dict(payload)}


def _market_observation(market: str, raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ScreenshotValidationError("MARKET_OBSERVATION_INVALID", f"market_observations.{market} must be an object")
    status = raw.get("status")
    if not isinstance(status, str) or status not in MARKET_STATES:
        raise ScreenshotValidationError("MARKET_VERIFICATION_STATE_INVALID", f"{market}.status is not governed")
    reason = raw.get("reason")
    if status == "VERIFIED":
        payload = _validate_market_payload(market, raw.get("payload"))
        raw_text = _text(raw.get("raw_text"), f"{market}.raw_text")
        if reason not in (None, "NOT_APPLICABLE"):
            reason = _text(reason, f"{market}.reason")
        else:
            reason = "NOT_APPLICABLE"
        candidates = raw.get("candidates", [])
        if candidates:
            raise ScreenshotValidationError("CANDIDATES_STATUS_MISMATCH", f"{market} VERIFIED cannot retain unresolved candidates")
    elif status == "CONFLICTED":
        payload = None
        raw_text = raw.get("raw_text")
        if raw_text is not None:
            raw_text = _text(raw_text, f"{market}.raw_text")
        reason = _text(reason, f"{market}.reason")
        candidates_raw = raw.get("candidates")
        if not isinstance(candidates_raw, (list, tuple)) or len(candidates_raw) < 2:
            raise ScreenshotValidationError("CONFLICT_CANDIDATES_REQUIRED", f"{market} CONFLICTED requires at least two candidates")
        candidates = tuple(_candidate(market, item) for item in candidates_raw)
    else:
        payload = None
        raw_text = raw.get("raw_text")
        if raw_text is not None:
            raw_text = _text(raw_text, f"{market}.raw_text")
        reason = _text(reason, f"{market}.reason")
        candidates = ()
        if raw.get("payload") is not None:
            raise ScreenshotValidationError("UNVERIFIED_PAYLOAD_FORBIDDEN", f"{market} {status} cannot expose an official payload")
        if raw.get("candidates"):
            raise ScreenshotValidationError("CANDIDATES_STATUS_MISMATCH", f"{market} {status} cannot retain unresolved candidates")
    return {"status": status, "raw_text": raw_text, "payload": payload, "reason": reason, "candidates": tuple(candidates)}


@dataclass(frozen=True)
class OfficialScreenshotObservation:
    match_id: str
    created_at: datetime
    captured_at: datetime
    source_timestamp: str
    observed_at: datetime
    ingested_at: datetime
    source: str
    source_reference: str
    source_is_official: bool
    image_hash: str
    extraction_method: str
    verification_state: ScreenshotVerificationState
    verification_reason: str
    contradiction_state: str
    market_observations: Mapping[str, Mapping[str, Any]]
    published_at: Optional[datetime]
    supersedes_evidence_id: Optional[str]
    revision_reason: Optional[str]
    supplied_evidence_hash: Optional[str]
    supplied_payload_hash: Optional[str]
    supplied_provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OfficialScreenshotObservation":
        if not isinstance(raw, Mapping):
            raise ScreenshotValidationError("OBSERVATION_NOT_OBJECT", "screenshot observation must be an object")
        forbidden = _find_model_field(raw)
        if forbidden:
            raise ScreenshotValidationError("MODEL_FIELD_FORBIDDEN", f"screenshot evidence cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        source = _text(raw.get("source"), "source")
        if raw.get("source_type") != "OFFICIAL_SCREENSHOT":
            raise ScreenshotValidationError("OFFICIAL_SCREENSHOT_REQUIRED", "source_type must be OFFICIAL_SCREENSHOT")
        if raw.get("source_is_official") is not True:
            raise ScreenshotValidationError("OFFICIAL_SOURCE_REQUIRED", "source_is_official must be true")
        source_reference = _text(raw.get("source_reference"), "source_reference")
        image_hash = _hash(raw.get("image_hash"), "image_hash")
        method = _text(raw.get("extraction_method"), "extraction_method")
        if method not in METHODS:
            raise ScreenshotValidationError("EXTRACTION_METHOD_INVALID", f"unsupported extraction method: {method}")
        created_at = _timestamp(raw.get("created_at"), "created_at")
        captured_at = _timestamp(raw.get("captured_at"), "captured_at")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        if ingested_at < observed_at:
            raise ScreenshotValidationError("INGESTED_BEFORE_OBSERVED", "ingested_at cannot precede observed_at")
        source_timestamp = _source_time(raw.get("source_timestamp"))
        published_at = raw.get("published_at")
        if published_at is not None:
            published_at = _timestamp(published_at, "published_at")
        state_raw = raw.get("verification_state")
        if not isinstance(state_raw, str) or state_raw not in VERIFICATION_STATES:
            raise ScreenshotValidationError("VERIFICATION_STATE_INVALID", "verification_state must be a governed exact value")
        verification_reason = _text(raw.get("verification_reason"), "verification_reason")
        contradiction_state = _text(raw.get("contradiction_state"), "contradiction_state")
        if contradiction_state not in {"NONE", "PENDING", "CONFLICTED", "RESOLVED", "NOT_APPLICABLE"}:
            raise ScreenshotValidationError("CONTRADICTION_STATE_INVALID", "contradiction_state is not governed")
        observations_raw = raw.get("market_observations")
        if not isinstance(observations_raw, Mapping) or set(observations_raw) != set(MARKETS):
            raise ScreenshotValidationError("MARKET_SET_INVALID", "market_observations must cover exactly five official markets")
        observations = {market: _market_observation(market, observations_raw[market]) for market in MARKETS}
        statuses = {item["status"] for item in observations.values()}
        if state_raw == "VERIFIED" and not statuses.issubset({"VERIFIED", "UNAVAILABLE"}):
            raise ScreenshotValidationError("VERIFICATION_STATE_CONFLICT", "VERIFIED evidence cannot contain unresolved market extraction")
        if state_raw == "CONFLICTED" and "CONFLICTED" not in statuses:
            raise ScreenshotValidationError("CONFLICT_STATE_MISMATCH", "CONFLICTED evidence requires a conflicted market")
        if state_raw == "NOT_VERIFIED" and "NOT_VERIFIED" not in statuses:
            raise ScreenshotValidationError("NOT_VERIFIED_STATE_MISMATCH", "NOT_VERIFIED evidence requires an unreadable market")
        if state_raw == "CONFLICTED" and contradiction_state != "CONFLICTED":
            raise ScreenshotValidationError("CONTRADICTION_STATE_REQUIRED", "CONFLICTED evidence requires contradiction_state=CONFLICTED")
        supersedes = raw.get("supersedes_evidence_id")
        if supersedes is not None:
            supersedes = _uuid(supersedes, "supersedes_evidence_id")
        revision_reason = raw.get("revision_reason")
        if revision_reason is not None:
            revision_reason = _text(revision_reason, "revision_reason")
        if supersedes is not None and revision_reason is None:
            raise ScreenshotValidationError("REVISION_REASON_REQUIRED", "supersedes_evidence_id requires revision_reason")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ScreenshotValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        return cls(
            match_id=match_id,
            created_at=created_at,
            captured_at=captured_at,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            ingested_at=ingested_at,
            source=source,
            source_reference=source_reference,
            source_is_official=True,
            image_hash=image_hash,
            extraction_method=method,
            verification_state=ScreenshotVerificationState(state_raw),
            verification_reason=verification_reason,
            contradiction_state=contradiction_state,
            market_observations=MappingProxyType(observations),
            published_at=published_at,
            supersedes_evidence_id=supersedes,
            revision_reason=revision_reason,
            supplied_evidence_hash=_hash(raw["evidence_hash"], "evidence_hash") if "evidence_hash" in raw else None,
            supplied_payload_hash=_hash(raw["payload_hash"], "payload_hash") if "payload_hash" in raw else None,
            supplied_provenance_hash=_hash(raw["provenance_hash"], "provenance_hash") if "provenance_hash" in raw else None,
            metadata=MappingProxyType(dict(metadata)),
        )

    @property
    def observation_id(self) -> str:
        return str(uuid.uuid5(SCREENSHOT_NAMESPACE, f"screenshot|{sha256_json(self.to_dict(include_hashes=False))}"))

    def to_dict(self, *, include_hashes: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "match_id": self.match_id,
            "created_at": _iso(self.created_at),
            "captured_at": _iso(self.captured_at),
            "source_timestamp": self.source_timestamp,
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "source": self.source,
            "source_type": "OFFICIAL_SCREENSHOT",
            "source_reference": self.source_reference,
            "source_is_official": True,
            "image_hash": self.image_hash,
            "extraction_method": self.extraction_method,
            "verification_state": self.verification_state.value,
            "verification_reason": self.verification_reason,
            "contradiction_state": self.contradiction_state,
            "market_observations": {market: dict(self.market_observations[market]) for market in MARKETS},
            "published_at": _iso(self.published_at) if self.published_at else None,
            "supersedes_evidence_id": self.supersedes_evidence_id,
            "revision_reason": self.revision_reason,
            "metadata": dict(self.metadata),
        }
        if include_hashes:
            result.update({"evidence_hash": None, "payload_hash": None, "provenance_hash": None})
        return result


@dataclass(frozen=True)
class OfficialScreenshotEvidence:
    evidence_id: str
    contract_version: str
    object_id: str
    match_id: str
    created_at: str
    captured_at: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    source: str
    source_type: str
    source_reference: str
    source_is_official: bool
    image_hash: str
    extraction_method: str
    verification_state: ScreenshotVerificationState
    verification_reason: str
    contradiction_state: str
    market_observations: Mapping[str, Mapping[str, Any]]
    published_at: Optional[str]
    evidence_hash: str
    payload_hash: str
    provenance_hash: str
    observation_id: str
    supersedes_evidence_id: Optional[str]
    revision: int
    revision_reason: Optional[str]
    metadata: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "created_at": self.created_at,
            "captured_at": self.captured_at,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_is_official": self.source_is_official,
            "image_hash": self.image_hash,
            "extraction_method": self.extraction_method,
            "verification_state": self.verification_state.value,
            "verification_reason": self.verification_reason,
            "contradiction_state": self.contradiction_state,
            "market_observations": {market: dict(self.market_observations[market]) for market in MARKETS},
            "published_at": self.published_at,
            "evidence_hash": self.evidence_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "observation_id": self.observation_id,
            "supersedes_evidence_id": self.supersedes_evidence_id,
            "revision": self.revision,
            "revision_reason": self.revision_reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ScreenshotIntakeResult:
    accepted: bool
    action: str
    observation_id: str
    evidence: Optional[OfficialScreenshotEvidence]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "action": self.action, "observation_id": self.observation_id, "evidence": self.evidence.to_dict() if self.evidence else None, "error_code": self.error_code}


@dataclass(frozen=True)
class _ScreenshotEvent:
    sequence: int
    action: str
    observation_id: str
    evidence_id: Optional[str]
    match_id: Optional[str]
    state: str
    error_code: Optional[str] = None


class OfficialScreenshotEvidenceStore:
    """Local append-only screenshot evidence store; no OCR service or DB."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-025 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._evidence: Dict[str, OfficialScreenshotEvidence] = {}
        self._observations: Dict[str, OfficialScreenshotObservation] = {}
        self._events: List[_ScreenshotEvent] = []

    @property
    def evidence(self) -> Tuple[OfficialScreenshotEvidence, ...]:
        return tuple(self._evidence.values())

    @property
    def observations(self) -> Tuple[OfficialScreenshotObservation, ...]:
        return tuple(self._observations.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType({
                "sequence": item.sequence,
                "action": item.action,
                "observation_id": item.observation_id,
                "evidence_id": item.evidence_id,
                "match_id": item.match_id,
                "state": item.state,
                "error_code": item.error_code,
            })
            for item in self._events
        )

    def get(self, evidence_id: str) -> Optional[OfficialScreenshotEvidence]:
        return self._evidence.get(evidence_id)

    def ingest(self, raw: Union[OfficialScreenshotObservation, Mapping[str, Any]]) -> ScreenshotIntakeResult:
        try:
            observation = raw if isinstance(raw, OfficialScreenshotObservation) else OfficialScreenshotObservation.from_dict(raw)
        except (ScreenshotValidationError, OfficialOddsValidationError, IdentityValidationError) as exc:
            observation_id = str(uuid.uuid5(SCREENSHOT_NAMESPACE, f"blocked|{sha256_json(raw if isinstance(raw, Mapping) else raw.to_dict())}"))
            self._append_event("BLOCKED_VALIDATION", observation_id, None, None, "BLOCKED", getattr(exc, "code", "VALIDATION_FAILED"))
            return ScreenshotIntakeResult(False, "BLOCKED_VALIDATION", observation_id, None, getattr(exc, "code", "VALIDATION_FAILED"))
        observation_id = observation.observation_id
        existing = next((item for item in self._evidence.values() if item.observation_id == observation_id), None)
        if existing is not None:
            self._append_event("DUPLICATE_NOOP", observation_id, existing.evidence_id, observation.match_id, existing.verification_state.value)
            return ScreenshotIntakeResult(True, "DUPLICATE_NOOP", observation_id, existing)
        identity = self._identity_store.get(observation.match_id)
        if identity is None:
            return self._blocked(observation, observation_id, "MATCH_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, observation_id, "MATCH_IDENTITY_NOT_RESOLVED")
        if observation.supersedes_evidence_id and observation.supersedes_evidence_id not in self._evidence:
            return self._blocked(observation, observation_id, "SUPERSEDES_EVIDENCE_NOT_FOUND")
        self._observations[observation_id] = observation
        payload_logical = {"match_id": observation.match_id, "image_hash": observation.image_hash, "market_observations": {market: dict(observation.market_observations[market]) for market in MARKETS}, "verification_state": observation.verification_state.value}
        payload_hash = sha256_json(payload_logical)
        provenance_hash = sha256_json({"match_id": observation.match_id, "source": observation.source, "source_reference": observation.source_reference, "image_hash": observation.image_hash, "source_timestamp": observation.source_timestamp, "captured_at": _iso(observation.captured_at), "observed_at": _iso(observation.observed_at), "published_at": _iso(observation.published_at) if observation.published_at else None})
        evidence_logical = {"match_id": observation.match_id, "source": observation.source, "source_type": "OFFICIAL_SCREENSHOT", "source_reference": observation.source_reference, "image_hash": observation.image_hash, "extraction_method": observation.extraction_method, "verification_state": observation.verification_state.value, "verification_reason": observation.verification_reason, "contradiction_state": observation.contradiction_state, "payload_hash": payload_hash, "provenance_hash": provenance_hash, "market_observations": payload_logical["market_observations"], "supersedes_evidence_id": observation.supersedes_evidence_id}
        evidence_hash = sha256_json(evidence_logical)
        for supplied, expected in ((observation.supplied_evidence_hash, evidence_hash), (observation.supplied_payload_hash, payload_hash), (observation.supplied_provenance_hash, provenance_hash)):
            if supplied is not None and supplied != expected:
                return self._blocked(observation, observation_id, "HASH_MISMATCH")
        evidence_id = str(uuid.uuid5(SCREENSHOT_NAMESPACE, f"evidence|{evidence_hash}"))
        predecessor = self._evidence.get(observation.supersedes_evidence_id) if observation.supersedes_evidence_id else None
        revision = predecessor.revision + 1 if predecessor else 1
        record = OfficialScreenshotEvidence(
            evidence_id=evidence_id,
            contract_version=CONTRACT_VERSION,
            object_id=evidence_id,
            match_id=observation.match_id,
            created_at=_iso(observation.created_at),
            captured_at=_iso(observation.captured_at),
            source_timestamp=observation.source_timestamp,
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            source=observation.source,
            source_type="OFFICIAL_SCREENSHOT",
            source_reference=observation.source_reference,
            source_is_official=True,
            image_hash=observation.image_hash,
            extraction_method=observation.extraction_method,
            verification_state=observation.verification_state,
            verification_reason=observation.verification_reason,
            contradiction_state=observation.contradiction_state,
            market_observations=observation.market_observations,
            published_at=_iso(observation.published_at) if observation.published_at else None,
            evidence_hash=evidence_hash,
            payload_hash=payload_hash,
            provenance_hash=provenance_hash,
            observation_id=observation_id,
            supersedes_evidence_id=observation.supersedes_evidence_id,
            revision=revision,
            revision_reason=observation.revision_reason,
            metadata=observation.metadata,
        )
        self._evidence[evidence_id] = record
        self._append_event("APPEND_SCREENSHOT_EVIDENCE", observation_id, evidence_id, observation.match_id, observation.verification_state.value)
        return ScreenshotIntakeResult(True, "APPENDED", observation_id, record)

    def _blocked(self, observation: OfficialScreenshotObservation, observation_id: str, code: str) -> ScreenshotIntakeResult:
        self._append_event("BLOCKED_BOUNDARY", observation_id, None, observation.match_id, "BLOCKED", code)
        return ScreenshotIntakeResult(False, code, observation_id, None, code)

    def _append_event(self, action: str, observation_id: str, evidence_id: Optional[str], match_id: Optional[str], state: str, error_code: Optional[str] = None) -> None:
        self._events.append(_ScreenshotEvent(len(self._events) + 1, action, observation_id, evidence_id, match_id, state, error_code))
