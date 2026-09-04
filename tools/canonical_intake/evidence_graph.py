"""V4-036 and V4-037 local evidence graph boundaries.

The implementation is deliberately local and append-only.  It provides an
independently addressable claim/evidence model first (V4-036), then the
quality, expiry, and explicitly documented conflict handling boundary
(V4-037).  It does not create features, predictions, model output, database
objects, or Production/Supabase connections.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import (
    CanonicalMatchIdentityStore,
    IdentityValidationError,
    _iso,
    _parse_timestamp,
)


EVIDENCE_CONTRACT_VERSION = "evidence@1.0.0"
EVIDENCE_SCHEMA_VERSION = "evidence-graph@1.0.0"
EVIDENCE_ID_NAMESPACE = uuid.UUID("e580f0a9-94da-5bf8-9d09-43ea89d5f0d1")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"
    REJECTED = "REJECTED"


class ContradictionState(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    CONFLICTED = "CONFLICTED"
    RESOLVED = "RESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceRelation(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CORROBORATES = "CORROBORATES"
    NEUTRAL = "NEUTRAL"


class SourceQualityBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class FreshnessState(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    UNKNOWN_TIME = "UNKNOWN_TIME"
    BLOCKED = "BLOCKED"


FORBIDDEN_TOKENS = (
    "prediction",
    "recommendation",
    "confidence",
    "model",
    "engine",
    "feature",
    "probability",
    "risk",
    "score_selection",
    "frozen_input",
    "v333",
    "v3_3_3",
)


class EvidenceGraphValidationError(ValueError):
    """An evidence or resolution record cannot be admitted safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field_name: str, *, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise EvidenceGraphValidationError("REQUIRED_FIELD_MISSING", f"{field_name} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise EvidenceGraphValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
        return None
    return value.strip()


def _token(value: Any, field_name: str, *, required: bool = True) -> Optional[str]:
    result = _text(value, field_name, required=required)
    if result is None:
        return None
    normalized = result.upper()
    if not TOKEN_RE.fullmatch(normalized):
        raise EvidenceGraphValidationError("ENUM_INVALID", f"{field_name} must be a governed uppercase token")
    return normalized


def _timestamp(value: Any, field_name: str, *, required: bool = True) -> Optional[datetime]:
    try:
        parsed = _parse_timestamp(value, field_name, required=required)
    except IdentityValidationError as exc:
        raise EvidenceGraphValidationError(exc.code, exc.message) from exc
    return parsed


def _hash(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    assert result is not None
    if not HASH_RE.fullmatch(result):
        raise EvidenceGraphValidationError("HASH_INVALID", f"{field_name} must be sha256:<64 hex>")
    return result


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


def _find_forbidden(value: Any, path: str) -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if any(token in normalized for token in FORBIDDEN_TOKENS):
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


def _validate_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise EvidenceGraphValidationError("JSON_KEY_INVALID", f"{path} keys must be strings")
        for key, child in value.items():
            _validate_json(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json(child, f"{path}[{index}]")
        return
    raise EvidenceGraphValidationError("JSON_VALUE_INVALID", f"{path} is not JSON-compatible")


def _validate_refs(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise EvidenceGraphValidationError("ENTITY_REFS_REQUIRED", f"{field_name} must be a non-empty object")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise EvidenceGraphValidationError("ENTITY_REFS_INVALID", f"{field_name} keys must be non-empty strings")
    _validate_json(value, field_name)
    if not isinstance(value.get("match_id"), str) or not UUID_RE.fullmatch(value["match_id"]):
        raise EvidenceGraphValidationError("MATCH_ID_REQUIRED", "entity_refs.match_id must be a V4 canonical UUID")
    return value


def _validate_string_list(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise EvidenceGraphValidationError("REFERENCE_LIST_INVALID", f"{field_name} must be an array")
    result = tuple(_text(item, f"{field_name}[{index}]") for index, item in enumerate(value))
    return tuple(item for item in result if item is not None)


@dataclass(frozen=True)
class EvidenceConfidence:
    """Source/evidence quality only; never a prediction probability."""

    source_quality: str
    verification_quality: str
    freshness: str
    coverage: str
    conflict_level: str

    @classmethod
    def from_dict(cls, raw: Any) -> "EvidenceConfidence":
        if not isinstance(raw, Mapping):
            raise EvidenceGraphValidationError("CONFIDENCE_INVALID", "confidence must be a quality object")
        forbidden = _find_forbidden(raw, "confidence")
        if forbidden:
            raise EvidenceGraphValidationError("MODEL_FIELD_FORBIDDEN", f"confidence cannot contain {forbidden}")
        values = {
            name: _token(raw.get(name), f"confidence.{name}")
            for name in ("source_quality", "verification_quality", "freshness", "coverage", "conflict_level")
        }
        return cls(**values)  # type: ignore[arg-type]

    def to_dict(self) -> Dict[str, str]:
        return {
            "source_quality": self.source_quality,
            "verification_quality": self.verification_quality,
            "freshness": self.freshness,
            "coverage": self.coverage,
            "conflict_level": self.conflict_level,
        }


@dataclass(frozen=True)
class EvidenceItem:
    """An independently addressable, immutable source-bound evidence item."""

    evidence_id: str
    claim_id: str
    claim_type: str
    claim: Mapping[str, Any]
    entity_refs: Mapping[str, Any]
    relation: EvidenceRelation
    source: str
    source_type: str
    source_reference: str
    published_at: Optional[datetime]
    published_time_state: str
    retrieved_at: datetime
    valid_from: Optional[datetime]
    valid_from_state: str
    expires_at: Optional[datetime]
    confidence: EvidenceConfidence
    verification_state: VerificationState
    contradiction_state: ContradictionState
    evidence_hash: str
    payload_hash: str
    provenance_hash: str
    status: str
    basis_refs: Tuple[str, ...]
    supersedes_evidence_id: Optional[str]
    revision: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EvidenceItem":
        if not isinstance(raw, Mapping):
            raise EvidenceGraphValidationError("EVIDENCE_NOT_OBJECT", "evidence must be an object")
        # The contract's top-level ``confidence`` is an evidence-quality
        # object.  Nested or model-style confidence fields remain forbidden.
        forbidden = _find_forbidden({key: value for key, value in raw.items() if key != "confidence"}, "evidence")
        if forbidden:
            raise EvidenceGraphValidationError("MODEL_FIELD_FORBIDDEN", f"evidence cannot contain {forbidden}")

        evidence_id = _text(raw.get("evidence_id", raw.get("object_id")), "evidence_id")
        claim_id = _text(raw.get("claim_id", raw.get("claim_ref")), "claim_id")
        claim_type = _token(raw.get("claim_type"), "claim_type")
        claim = raw.get("claim")
        if not isinstance(claim, Mapping) or not claim:
            raise EvidenceGraphValidationError("CLAIM_REQUIRED", "claim must be a non-empty structured object")
        _validate_json(claim, "claim")
        forbidden = _find_forbidden(claim, "claim")
        if forbidden:
            raise EvidenceGraphValidationError("MODEL_FIELD_FORBIDDEN", f"claim cannot contain {forbidden}")
        entity_refs = _validate_refs(raw.get("entity_refs"), "entity_refs")

        relation_raw = _text(raw.get("relation", EvidenceRelation.SUPPORTS.value), "relation")
        assert relation_raw is not None
        try:
            relation = EvidenceRelation(relation_raw.upper())
        except ValueError as exc:
            raise EvidenceGraphValidationError("RELATION_INVALID", "relation is not governed") from exc

        source = _text(raw.get("source"), "source")
        source_type = _token(raw.get("source_type"), "source_type")
        source_reference = _text(raw.get("source_reference", raw.get("source_ref")), "source_reference")
        published_at = _timestamp(raw.get("published_at"), "published_at", required=False)
        published_time_state = _token(
            raw.get("published_time_state", "KNOWN" if published_at is not None else "UNKNOWN_TIME"),
            "published_time_state",
        )
        retrieved_at = _timestamp(raw.get("retrieved_at"), "retrieved_at")
        valid_from = _timestamp(raw.get("valid_from"), "valid_from", required=False)
        valid_from_state = _token(
            raw.get("valid_from_state", "KNOWN" if valid_from is not None else "UNKNOWN_TIME"),
            "valid_from_state",
        )
        expires_at = _timestamp(raw.get("expires_at"), "expires_at", required=False)
        if published_at is not None and published_at > retrieved_at:
            raise EvidenceGraphValidationError("PUBLISHED_AFTER_RETRIEVED", "published_at cannot follow retrieved_at")
        if valid_from is not None and valid_from > retrieved_at:
            raise EvidenceGraphValidationError("VALID_FROM_AFTER_RETRIEVED", "valid_from cannot follow retrieved_at")
        if expires_at is not None and valid_from is not None and expires_at < valid_from:
            raise EvidenceGraphValidationError("EXPIRY_BEFORE_VALID_FROM", "expires_at cannot precede valid_from")

        confidence = EvidenceConfidence.from_dict(raw.get("confidence"))
        try:
            verification_state = VerificationState(_text(raw.get("verification_state"), "verification_state"))
            contradiction_state = ContradictionState(_text(raw.get("contradiction_state"), "contradiction_state"))
        except ValueError as exc:
            raise EvidenceGraphValidationError("STATE_INVALID", "verification or contradiction state is not governed") from exc

        basis_refs = _validate_string_list(raw.get("basis_refs", []), "basis_refs")
        supersedes = _text(raw.get("supersedes_evidence_id"), "supersedes_evidence_id", required=False)
        revision_raw = raw.get("revision", 1)
        if not isinstance(revision_raw, int) or isinstance(revision_raw, bool) or revision_raw < 1:
            raise EvidenceGraphValidationError("REVISION_INVALID", "revision must be a positive integer")
        status = _token(raw.get("status", "ACTIVE"), "status")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise EvidenceGraphValidationError("METADATA_INVALID", "metadata must be an object")
        _validate_json(metadata, "metadata")
        forbidden = _find_forbidden(metadata, "metadata")
        if forbidden:
            raise EvidenceGraphValidationError("MODEL_FIELD_FORBIDDEN", f"metadata cannot contain {forbidden}")

        payload_hash = sha256_json({"claim": claim, "entity_refs": entity_refs, "relation": relation.value})
        provenance_hash = sha256_json(
            {
                "source": source,
                "source_type": source_type,
                "source_reference": source_reference,
                "published_at": _iso(published_at) if published_at else None,
                "published_time_state": published_time_state,
                "retrieved_at": _iso(retrieved_at),
                "valid_from": _iso(valid_from) if valid_from else None,
                "valid_from_state": valid_from_state,
                "expires_at": _iso(expires_at) if expires_at else None,
            }
        )
        evidence_hash = sha256_json(
            {
                "evidence_id": evidence_id,
                "claim_id": claim_id,
                "claim_type": claim_type,
                "claim": claim,
                "entity_refs": entity_refs,
                "relation": relation.value,
                "payload_hash": payload_hash,
                "provenance_hash": provenance_hash,
                "confidence": confidence.to_dict(),
                "verification_state": verification_state.value,
                "contradiction_state": contradiction_state.value,
                "status": status,
                "basis_refs": list(basis_refs),
                "supersedes_evidence_id": supersedes,
                "revision": revision_raw,
            }
        )
        supplied_payload_hash = raw.get("payload_hash")
        supplied_provenance_hash = raw.get("provenance_hash")
        supplied_evidence_hash = raw.get("evidence_hash")
        if supplied_payload_hash is not None and _hash(supplied_payload_hash, "payload_hash") != payload_hash:
            raise EvidenceGraphValidationError("PAYLOAD_HASH_MISMATCH", "payload_hash does not match declared boundary")
        if supplied_provenance_hash is not None and _hash(supplied_provenance_hash, "provenance_hash") != provenance_hash:
            raise EvidenceGraphValidationError("PROVENANCE_HASH_MISMATCH", "provenance_hash does not match declared boundary")
        if supplied_evidence_hash is not None and _hash(supplied_evidence_hash, "evidence_hash") != evidence_hash:
            raise EvidenceGraphValidationError("EVIDENCE_HASH_MISMATCH", "evidence_hash does not match declared boundary")

        assert evidence_id is not None and claim_id is not None and claim_type is not None
        assert source is not None and source_type is not None and source_reference is not None
        return cls(
            evidence_id=evidence_id,
            claim_id=claim_id,
            claim_type=claim_type,
            claim=_freeze(claim),
            entity_refs=_freeze(entity_refs),
            relation=relation,
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            published_at=published_at,
            published_time_state=published_time_state,
            retrieved_at=retrieved_at,
            valid_from=valid_from,
            valid_from_state=valid_from_state,
            expires_at=expires_at,
            confidence=confidence,
            verification_state=verification_state,
            contradiction_state=contradiction_state,
            evidence_hash=evidence_hash,
            payload_hash=payload_hash,
            provenance_hash=provenance_hash,
            status=status,
            basis_refs=basis_refs,
            supersedes_evidence_id=supersedes,
            revision=revision_raw,
            metadata=_freeze(metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "contract_version": EVIDENCE_CONTRACT_VERSION,
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "claim": _thaw(self.claim),
            "entity_refs": _thaw(self.entity_refs),
            "relation": self.relation.value,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "published_at": _iso(self.published_at) if self.published_at else None,
            "published_time_state": self.published_time_state,
            "retrieved_at": _iso(self.retrieved_at),
            "valid_from": _iso(self.valid_from) if self.valid_from else None,
            "valid_from_state": self.valid_from_state,
            "expires_at": _iso(self.expires_at) if self.expires_at else None,
            "confidence": self.confidence.to_dict(),
            "verification_state": self.verification_state.value,
            "contradiction_state": self.contradiction_state.value,
            "evidence_hash": self.evidence_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "status": self.status,
            "basis_refs": list(self.basis_refs),
            "supersedes_evidence_id": self.supersedes_evidence_id,
            "revision": self.revision,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class EvidenceIntakeResult:
    accepted: bool
    action: str
    evidence_id: str
    item: Optional[EvidenceItem]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action": self.action,
            "evidence_id": self.evidence_id,
            "item": self.item.to_dict() if self.item else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _EvidenceEvent:
    sequence: int
    action: str
    evidence_id: str
    supersedes_evidence_id: Optional[str]
    error_code: Optional[str] = None


class EvidenceGraphStore:
    """V4-036 local append-only evidence graph, bound to V4-020 identity."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-036 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._items: Dict[str, EvidenceItem] = {}
        self._events: List[_EvidenceEvent] = []
        self._resolutions: Dict[str, "ConflictResolutionRecord"] = {}
        self._quality: Dict[str, "SourceQualityAssessment"] = {}

    @property
    def items(self) -> Tuple[EvidenceItem, ...]:
        return tuple(self._items.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "evidence_id": event.evidence_id,
                    "supersedes_evidence_id": event.supersedes_evidence_id,
                    "error_code": event.error_code,
                }
            )
            for event in self._events
        )

    def get(self, evidence_id: str) -> Optional[EvidenceItem]:
        return self._items.get(evidence_id)

    def for_claim(self, claim_id: str) -> Tuple[EvidenceItem, ...]:
        return tuple(item for item in self._items.values() if item.claim_id == claim_id)

    def ingest(self, raw: Union[EvidenceItem, Mapping[str, Any]]) -> EvidenceIntakeResult:
        evidence_id = raw.evidence_id if isinstance(raw, EvidenceItem) else str(raw.get("evidence_id", raw.get("object_id", "blocked-evidence")))
        try:
            item = raw if isinstance(raw, EvidenceItem) else EvidenceItem.from_dict(raw)
        except (EvidenceGraphValidationError, IdentityValidationError) as exc:
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._append_event("BLOCKED_VALIDATION", evidence_id, None, code)
            return EvidenceIntakeResult(False, "BLOCKED", evidence_id, None, code)

        match_id = item.entity_refs["match_id"]
        identity = self._identity_store.get(match_id)
        if identity is None:
            return self._blocked(item, "MATCH_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(item, "MATCH_IDENTITY_NOT_RESOLVED")
        declared_key = item.entity_refs.get("match_identity_key")
        if declared_key is not None and declared_key != identity.match_identity_key:
            return self._blocked(item, "MATCH_IDENTITY_KEY_CONFLICT")

        existing = self._items.get(item.evidence_id)
        if existing is not None:
            if existing.evidence_hash == item.evidence_hash:
                self._append_event("DUPLICATE_NOOP", item.evidence_id, None, None)
                return EvidenceIntakeResult(True, "DUPLICATE_NOOP", item.evidence_id, existing)
            return self._blocked(item, "EVIDENCE_ID_REUSE")

        if item.supersedes_evidence_id is not None:
            predecessor = self._items.get(item.supersedes_evidence_id)
            if predecessor is None:
                return self._blocked(item, "SUPERSEDES_TARGET_NOT_FOUND")
            if predecessor.claim_id != item.claim_id or predecessor.entity_refs.get("match_id") != match_id:
                return self._blocked(item, "SUPERSEDES_FAMILY_CONFLICT")
            if item.revision != predecessor.revision + 1:
                return self._blocked(item, "REVISION_SEQUENCE_INVALID")
        elif item.revision != 1:
            return self._blocked(item, "ROOT_REVISION_INVALID")

        self._items[item.evidence_id] = item
        self._append_event("REVISION_APPENDED" if item.supersedes_evidence_id else "ROOT_CREATED", item.evidence_id, item.supersedes_evidence_id, None)
        return EvidenceIntakeResult(True, "REVISION_APPENDED" if item.supersedes_evidence_id else "ROOT_CREATED", item.evidence_id, item)

    def _blocked(self, item: EvidenceItem, code: str) -> EvidenceIntakeResult:
        self._append_event("BLOCKED", item.evidence_id, item.supersedes_evidence_id, code)
        return EvidenceIntakeResult(False, "BLOCKED", item.evidence_id, None, code)

    def _append_event(self, action: str, evidence_id: str, supersedes: Optional[str], error_code: Optional[str]) -> None:
        self._events.append(_EvidenceEvent(len(self._events) + 1, action, evidence_id, supersedes, error_code))


@dataclass(frozen=True)
class SourceQualityAssessment:
    evidence_id: str
    quality_band: SourceQualityBand
    quality_basis: Tuple[str, ...]
    assessed_by: str
    assessed_at: datetime
    quality_hash: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SourceQualityAssessment":
        if not isinstance(raw, Mapping):
            raise EvidenceGraphValidationError("QUALITY_NOT_OBJECT", "source quality must be an object")
        evidence_id = _text(raw.get("evidence_id"), "evidence_id")
        band_raw = _text(raw.get("quality_band"), "quality_band")
        assert band_raw is not None
        try:
            band = SourceQualityBand(band_raw.upper())
        except ValueError as exc:
            raise EvidenceGraphValidationError("QUALITY_BAND_INVALID", "quality_band is not governed") from exc
        basis = _validate_string_list(raw.get("quality_basis"), "quality_basis")
        if not basis:
            raise EvidenceGraphValidationError("QUALITY_BASIS_REQUIRED", "quality_basis is required")
        assessed_by = _text(raw.get("assessed_by"), "assessed_by")
        assessed_at = _timestamp(raw.get("assessed_at"), "assessed_at")
        assert evidence_id is not None and assessed_by is not None and assessed_at is not None
        quality_hash = sha256_json({"evidence_id": evidence_id, "quality_band": band.value, "quality_basis": list(basis), "assessed_by": assessed_by, "assessed_at": _iso(assessed_at)})
        supplied = raw.get("quality_hash")
        if supplied is not None and _hash(supplied, "quality_hash") != quality_hash:
            raise EvidenceGraphValidationError("QUALITY_HASH_MISMATCH", "quality_hash does not match assessment")
        return cls(evidence_id, band, basis, assessed_by, assessed_at, quality_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {"evidence_id": self.evidence_id, "quality_band": self.quality_band.value, "quality_basis": list(self.quality_basis), "assessed_by": self.assessed_by, "assessed_at": _iso(self.assessed_at), "quality_hash": self.quality_hash}


@dataclass(frozen=True)
class EvidenceQualityResult:
    evidence_id: str
    quality_band: SourceQualityBand
    freshness_state: FreshnessState
    verification_state: VerificationState
    contradiction_state: ContradictionState
    eligible: bool
    blockers: Tuple[str, ...]
    quality_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {"evidence_id": self.evidence_id, "quality_band": self.quality_band.value, "freshness_state": self.freshness_state.value, "verification_state": self.verification_state.value, "contradiction_state": self.contradiction_state.value, "eligible": self.eligible, "blockers": list(self.blockers), "quality_hash": self.quality_hash}


@dataclass(frozen=True)
class ConflictResolutionRecord:
    resolution_id: str
    claim_id: str
    evidence_ids: Tuple[str, ...]
    resolution_reason: str
    basis_evidence_ids: Tuple[str, ...]
    actor: str
    resolved_at: datetime
    policy_reference: str
    selected_evidence_id: Optional[str]
    resolution_hash: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ConflictResolutionRecord":
        if not isinstance(raw, Mapping):
            raise EvidenceGraphValidationError("RESOLUTION_NOT_OBJECT", "resolution must be an object")
        resolution_id = _text(raw.get("resolution_id"), "resolution_id")
        claim_id = _text(raw.get("claim_id"), "claim_id")
        evidence_ids = _validate_string_list(raw.get("evidence_ids"), "evidence_ids")
        basis_ids = _validate_string_list(raw.get("basis_evidence_ids"), "basis_evidence_ids")
        if not evidence_ids or not basis_ids:
            raise EvidenceGraphValidationError("RESOLUTION_EVIDENCE_REQUIRED", "resolution must retain evidence and basis references")
        reason = _text(raw.get("resolution_reason"), "resolution_reason")
        actor = _text(raw.get("actor"), "actor")
        resolved_at = _timestamp(raw.get("resolved_at"), "resolved_at")
        policy_reference = _text(raw.get("policy_reference"), "policy_reference")
        selected = _text(raw.get("selected_evidence_id"), "selected_evidence_id", required=False)
        assert resolution_id is not None and claim_id is not None and reason is not None and actor is not None and resolved_at is not None and policy_reference is not None
        if selected is not None and selected not in evidence_ids:
            raise EvidenceGraphValidationError("RESOLUTION_SELECTION_INVALID", "selected evidence must be in the retained conflict set")
        resolution_hash = sha256_json({"resolution_id": resolution_id, "claim_id": claim_id, "evidence_ids": list(evidence_ids), "resolution_reason": reason, "basis_evidence_ids": list(basis_ids), "actor": actor, "resolved_at": _iso(resolved_at), "policy_reference": policy_reference, "selected_evidence_id": selected})
        supplied = raw.get("resolution_hash")
        if supplied is not None and _hash(supplied, "resolution_hash") != resolution_hash:
            raise EvidenceGraphValidationError("RESOLUTION_HASH_MISMATCH", "resolution_hash does not match resolution record")
        return cls(resolution_id, claim_id, evidence_ids, reason, basis_ids, actor, resolved_at, policy_reference, selected, resolution_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {"resolution_id": self.resolution_id, "claim_id": self.claim_id, "evidence_ids": list(self.evidence_ids), "resolution_reason": self.resolution_reason, "basis_evidence_ids": list(self.basis_evidence_ids), "actor": self.actor, "resolved_at": _iso(self.resolved_at), "policy_reference": self.policy_reference, "selected_evidence_id": self.selected_evidence_id, "resolution_hash": self.resolution_hash, "status": ContradictionState.RESOLVED.value}


class SourceConflictResolver:
    """V4-037 quality/expiry/conflict boundary without silent source choice."""

    def __init__(self, graph: EvidenceGraphStore):
        if not isinstance(graph, EvidenceGraphStore):
            raise TypeError("V4-037 requires a V4-036 EvidenceGraphStore")
        self._graph = graph
        self._quality: Dict[str, SourceQualityAssessment] = {}
        self._resolutions: Dict[str, ConflictResolutionRecord] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def quality_assessments(self) -> Tuple[SourceQualityAssessment, ...]:
        return tuple(self._quality.values())

    @property
    def resolutions(self) -> Tuple[ConflictResolutionRecord, ...]:
        return tuple(self._resolutions.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def assess_source(self, raw: Union[SourceQualityAssessment, Mapping[str, Any]]) -> SourceQualityAssessment:
        assessment = raw if isinstance(raw, SourceQualityAssessment) else SourceQualityAssessment.from_dict(raw)
        if self._graph.get(assessment.evidence_id) is None:
            raise EvidenceGraphValidationError("EVIDENCE_NOT_FOUND", "quality assessment must reference an evidence item")
        existing = self._quality.get(assessment.evidence_id)
        if existing is not None and existing.quality_hash != assessment.quality_hash:
            raise EvidenceGraphValidationError("QUALITY_REVISION_REQUIRES_APPEND", "quality changes require a new audited assessment")
        self._quality[assessment.evidence_id] = assessment
        self._events.append({"action": "QUALITY_ASSESSED" if existing is None else "QUALITY_DUPLICATE_NOOP", "evidence_id": assessment.evidence_id, "quality_hash": assessment.quality_hash})
        return assessment

    def evaluate(self, evidence_id: str, *, as_of: Any, cutoff_at: Any = None, kickoff_at: Any = None) -> EvidenceQualityResult:
        item = self._graph.get(evidence_id)
        if item is None:
            raise EvidenceGraphValidationError("EVIDENCE_NOT_FOUND", "cannot evaluate missing evidence")
        now = _timestamp(as_of, "as_of")
        cutoff = _timestamp(cutoff_at, "cutoff_at", required=False)
        kickoff = _timestamp(kickoff_at, "kickoff_at", required=False)
        assert now is not None
        assessment = self._quality.get(evidence_id)
        band = assessment.quality_band if assessment else SourceQualityBand.UNKNOWN
        blockers: List[str] = []
        if item.valid_from is None:
            freshness = FreshnessState.UNKNOWN_TIME
            blockers.append("VALID_FROM_UNKNOWN_TIME")
        elif item.valid_from > now:
            freshness = FreshnessState.FUTURE_DATA
            blockers.append("VALID_FROM_AFTER_AS_OF")
        elif item.expires_at is not None and item.expires_at < now:
            freshness = FreshnessState.STALE
            blockers.append("EXPIRED")
        else:
            freshness = FreshnessState.CURRENT
        if cutoff is not None:
            if kickoff is not None and not cutoff < kickoff:
                blockers.append("CUTOFF_NOT_BEFORE_KICKOFF")
            if item.valid_from is None or item.valid_from > cutoff or item.retrieved_at > cutoff:
                freshness = FreshnessState.FUTURE_DATA
                blockers.append("NOT_ELIGIBLE_AT_CUTOFF")
        if item.verification_state in {VerificationState.NOT_VERIFIED, VerificationState.REJECTED, VerificationState.STALE}:
            blockers.append(f"VERIFICATION_{item.verification_state.value}")
        conflict_state = self.conflict_state(item.claim_id)
        if conflict_state == ContradictionState.CONFLICTED:
            blockers.append("UNRESOLVED_CONFLICT")
        if item.contradiction_state in {ContradictionState.PENDING, ContradictionState.CONFLICTED} and conflict_state != ContradictionState.RESOLVED:
            blockers.append("CONTRADICTION_NOT_RESOLVED")
        if band == SourceQualityBand.UNKNOWN:
            blockers.append("SOURCE_QUALITY_UNKNOWN")
        eligible = not blockers
        quality_hash = sha256_json({"evidence_id": evidence_id, "quality_band": band.value, "freshness_state": freshness.value, "verification_state": item.verification_state.value, "contradiction_state": conflict_state.value, "eligible": eligible, "blockers": blockers})
        return EvidenceQualityResult(evidence_id, band, freshness, item.verification_state, conflict_state, eligible, tuple(blockers), quality_hash)

    def conflict_state(self, claim_id: str) -> ContradictionState:
        items = self._graph.for_claim(claim_id)
        if len(items) < 2:
            return items[0].contradiction_state if items else ContradictionState.NONE
        if claim_id in self._resolutions:
            return ContradictionState.RESOLVED
        if any(item.relation == EvidenceRelation.CONTRADICTS or item.contradiction_state in {ContradictionState.CONFLICTED, ContradictionState.PENDING} for item in items):
            return ContradictionState.CONFLICTED
        claim_fingerprints = {sha256_json(_thaw(item.claim)) for item in items}
        return ContradictionState.CONFLICTED if len(claim_fingerprints) > 1 else ContradictionState.NONE

    def conflict_set(self, claim_id: str) -> Tuple[EvidenceItem, ...]:
        return self._graph.for_claim(claim_id)

    def resolve_conflict(self, raw: Union[ConflictResolutionRecord, Mapping[str, Any]]) -> ConflictResolutionRecord:
        record = raw if isinstance(raw, ConflictResolutionRecord) else ConflictResolutionRecord.from_dict(raw)
        items = self._graph.for_claim(record.claim_id)
        ids = {item.evidence_id for item in items}
        if not ids or not set(record.evidence_ids).issubset(ids) or not set(record.basis_evidence_ids).issubset(ids):
            raise EvidenceGraphValidationError("RESOLUTION_REFERENCE_INVALID", "resolution references must resolve to the full retained claim evidence set")
        if self.conflict_state(record.claim_id) not in {ContradictionState.CONFLICTED, ContradictionState.RESOLVED}:
            raise EvidenceGraphValidationError("NO_CONFLICT_TO_RESOLVE", "resolution requires a conflicting claim set")
        if record.resolution_id in self._resolutions:
            existing = self._resolutions[record.resolution_id]
            if existing.resolution_hash == record.resolution_hash:
                return existing
            raise EvidenceGraphValidationError("RESOLUTION_ID_REUSE", "resolution_id cannot be reused")
        self._resolutions[record.resolution_id] = record
        self._events.append({"action": "CONFLICT_RESOLVED", "resolution_id": record.resolution_id, "claim_id": record.claim_id, "evidence_ids": list(record.evidence_ids), "selected_evidence_id": record.selected_evidence_id, "resolution_hash": record.resolution_hash})
        return record


__all__ = [
    "ContradictionState",
    "ConflictResolutionRecord",
    "EvidenceConfidence",
    "EvidenceGraphStore",
    "EvidenceGraphValidationError",
    "EvidenceIntakeResult",
    "EvidenceItem",
    "EvidenceRelation",
    "FreshnessState",
    "SourceConflictResolver",
    "SourceQualityAssessment",
    "SourceQualityBand",
    "VerificationState",
]
