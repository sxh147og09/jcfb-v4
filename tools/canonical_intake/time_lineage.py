"""V4-022 timestamp, availability, and no-future-leakage lineage.

This module is a local, in-memory, no-write boundary. It consumes one
V4-021 fact envelope by object identity, requires an explicit source-time
basis, evaluates the declared pre-match cutoff, and retains every decision in
an append-only local ledger. Batch orchestration and source deduplication are
deferred to V4-023.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .fact_envelope import AvailabilityStatus, CanonicalFactEnvelope, CanonicalFactStore
from .match_identity import IdentityValidationError, _iso, _parse_timestamp


CONTRACT_VERSION = "time-lineage@1.0.0"
TIME_LINEAGE_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class AvailabilityTimeBasis(str, Enum):
    SOURCE_PUBLISHED_AT = "SOURCE_PUBLISHED_AT"
    SOURCE_TIMESTAMP = "SOURCE_TIMESTAMP"
    OBSERVED_AT = "OBSERVED_AT"


class TimeGateStatus(str, Enum):
    PREMATCH_ALLOWED = "PREMATCH_ALLOWED"
    POSTMATCH_ONLY = "POSTMATCH_ONLY"
    FUTURE_INFORMATION_LEAKAGE = "FUTURE_INFORMATION_LEAKAGE"
    BLOCKED = "BLOCKED"


class TimeLineageValidationError(ValueError):
    """A timestamp lineage cannot prove safe pre-match eligibility."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TimeLineageValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise TimeLineageValidationError("REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _time(value: Any, field_name: str, *, required: bool = True) -> Optional[datetime]:
    try:
        return _parse_timestamp(value, field_name, required=required)
    except IdentityValidationError as exc:
        raise TimeLineageValidationError(exc.code, exc.message) from exc


def _hash_time(value: Optional[datetime]) -> Optional[str]:
    """Canonical UTC representation used only for deterministic hashes."""

    return value.astimezone(timezone.utc).isoformat(timespec="seconds") if value else None


@dataclass(frozen=True)
class TimeLineageInput:
    """Explicit time-gate request for one V4-021 fact envelope."""

    fact_object_id: str
    prediction_cutoff_at: datetime
    kickoff_at: datetime
    availability_time_basis: AvailabilityTimeBasis
    source_timestamp: Optional[datetime]
    source_published_at: Optional[datetime]
    observed_at: datetime
    ingested_at: datetime
    expected_match_id: Optional[str] = None
    expected_source_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], envelope: CanonicalFactEnvelope) -> "TimeLineageInput":
        if not isinstance(raw, Mapping):
            raise TimeLineageValidationError("INPUT_NOT_OBJECT", "time lineage input must be an object")
        fact_object_id = _uuid(raw.get("fact_object_id"), "fact_object_id")
        cutoff = _time(raw.get("prediction_cutoff_at"), "prediction_cutoff_at")
        kickoff = _time(raw.get("kickoff_at"), "kickoff_at")
        assert cutoff is not None and kickoff is not None

        basis_value = raw.get("availability_time_basis")
        if not isinstance(basis_value, str):
            raise TimeLineageValidationError(
                "AVAILABILITY_BASIS_REQUIRED",
                "availability_time_basis must be explicitly selected",
            )
        try:
            basis = AvailabilityTimeBasis(basis_value)
        except ValueError as exc:
            raise TimeLineageValidationError(
                "AVAILABILITY_BASIS_INVALID", f"unsupported availability_time_basis: {basis_value}"
            ) from exc

        source_timestamp = _time(raw.get("source_timestamp"), "source_timestamp", required=False)
        source_published_raw = raw.get("source_published_at", raw.get("published_at", envelope.published_at))
        source_published_at = _time(source_published_raw, "source_published_at", required=False)
        observed_at = _time(raw.get("observed_at", envelope.observed_at), "observed_at")
        ingested_at = _time(raw.get("ingested_at", envelope.ingested_at), "ingested_at")
        assert observed_at is not None and ingested_at is not None

        expected_match_id = raw.get("match_id")
        if expected_match_id is not None:
            expected_match_id = _uuid(expected_match_id, "match_id")
        expected_source_ref = raw.get("source_ref")
        if expected_source_ref is not None:
            expected_source_ref = _text(expected_source_ref, "source_ref")

        return cls(
            fact_object_id=fact_object_id,
            prediction_cutoff_at=cutoff,
            kickoff_at=kickoff,
            availability_time_basis=basis,
            source_timestamp=source_timestamp,
            source_published_at=source_published_at,
            observed_at=observed_at,
            ingested_at=ingested_at,
            expected_match_id=expected_match_id,
            expected_source_ref=expected_source_ref,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_object_id": self.fact_object_id,
            "prediction_cutoff_at": _iso(self.prediction_cutoff_at),
            "kickoff_at": _iso(self.kickoff_at),
            "availability_time_basis": self.availability_time_basis.value,
            "source_timestamp": _iso(self.source_timestamp) if self.source_timestamp else None,
            "source_published_at": _iso(self.source_published_at) if self.source_published_at else None,
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "match_id": self.expected_match_id,
            "source_ref": self.expected_source_ref,
        }


@dataclass(frozen=True)
class TimeLineageDecision:
    """Immutable, auditable result of the V4-022 time gate."""

    decision_id: str
    contract_version: str
    fact_object_id: str
    fact_observation_id: str
    match_id: str
    source_ref: str
    source_timestamp: Optional[str]
    source_published_at: Optional[str]
    observed_at: str
    ingested_at: str
    availability_at: Optional[str]
    availability_time_basis: Optional[AvailabilityTimeBasis]
    prediction_cutoff_at: str
    kickoff_at: str
    status: TimeGateStatus
    reason_code: str
    reason_detail: str
    provenance_hash: str
    lineage_hash: str
    future_information_leakage: bool
    run_invalid: bool
    tier_a_eligible: bool
    promotion_evidence: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "contract_version": self.contract_version,
            "fact_object_id": self.fact_object_id,
            "fact_observation_id": self.fact_observation_id,
            "match_id": self.match_id,
            "source_ref": self.source_ref,
            "source_timestamp": self.source_timestamp,
            "source_published_at": self.source_published_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "availability_at": self.availability_at,
            "availability_time_basis": self.availability_time_basis.value if self.availability_time_basis else None,
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "provenance_hash": self.provenance_hash,
            "lineage_hash": self.lineage_hash,
            "future_information_leakage": self.future_information_leakage,
            "run_invalid": self.run_invalid,
            "tier_a_eligible": self.tier_a_eligible,
            "promotion_evidence": self.promotion_evidence,
        }


@dataclass(frozen=True)
class TimeGateResult:
    accepted: bool
    status: TimeGateStatus
    action: str
    decision: Optional[TimeLineageDecision]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status.value,
            "action": self.action,
            "decision": self.decision.to_dict() if self.decision else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _TimeAppendEvent:
    sequence: int
    action: str
    decision_id: Optional[str]
    fact_object_id: Optional[str]
    status: TimeGateStatus
    reason_code: Optional[str]


class TimeLineageStore:
    """Local V4-022 time-lineage decision ledger; no database writes."""

    def __init__(self, fact_store: CanonicalFactStore):
        if not isinstance(fact_store, CanonicalFactStore):
            raise TypeError("V4-022 requires a V4-021 CanonicalFactStore")
        self._fact_store = fact_store
        self._decisions: Dict[str, TimeLineageDecision] = {}
        self._events: List[_TimeAppendEvent] = []

    @property
    def decisions(self) -> Tuple[TimeLineageDecision, ...]:
        return tuple(self._decisions.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "decision_id": event.decision_id,
                    "fact_object_id": event.fact_object_id,
                    "status": event.status.value,
                    "reason_code": event.reason_code,
                }
            )
            for event in self._events
        )

    def get(self, decision_id: str) -> Optional[TimeLineageDecision]:
        return self._decisions.get(decision_id)

    def evaluate(self, raw: Mapping[str, Any]) -> TimeGateResult:
        fact_object_id = raw.get("fact_object_id") if isinstance(raw, Mapping) else None
        envelope = self._fact_store.get(fact_object_id) if isinstance(fact_object_id, str) else None
        if envelope is None:
            code = "FACT_REFERENCE_NOT_FOUND"
            self._append_event("BLOCKED_REFERENCE", None, fact_object_id if isinstance(fact_object_id, str) else None, TimeGateStatus.BLOCKED, code)
            return TimeGateResult(False, TimeGateStatus.BLOCKED, code, None, code)

        try:
            request = TimeLineageInput.from_dict(raw, envelope)
            self._validate_reference(request, envelope)
            decision = self._decide(request, envelope)
        except TimeLineageValidationError as exc:
            self._append_event("BLOCKED_VALIDATION", None, envelope.object_id, TimeGateStatus.BLOCKED, exc.code)
            return TimeGateResult(False, TimeGateStatus.BLOCKED, exc.code, None, exc.code)

        existing = self._decisions.get(decision.decision_id)
        if existing is not None:
            self._append_event("DUPLICATE_NOOP", existing.decision_id, envelope.object_id, existing.status, None)
            return TimeGateResult(
                existing.status == TimeGateStatus.PREMATCH_ALLOWED,
                existing.status,
                "DUPLICATE_NOOP",
                existing,
                None,
            )

        self._decisions[decision.decision_id] = decision
        self._append_event("DECISION_APPENDED", decision.decision_id, envelope.object_id, decision.status, decision.reason_code)
        return TimeGateResult(
            decision.status == TimeGateStatus.PREMATCH_ALLOWED,
            decision.status,
            "DECISION_APPENDED",
            decision,
            None,
        )

    @staticmethod
    def _validate_reference(request: TimeLineageInput, envelope: CanonicalFactEnvelope) -> None:
        if request.fact_object_id != envelope.object_id:
            raise TimeLineageValidationError("FACT_REFERENCE_CONFLICT", "fact_object_id does not resolve to the supplied envelope")
        if request.expected_match_id is not None and request.expected_match_id != envelope.subject.match_id:
            raise TimeLineageValidationError("MATCH_REFERENCE_CONFLICT", "match_id conflicts with the canonical fact subject")
        if request.expected_source_ref is not None and request.expected_source_ref != envelope.source_ref:
            raise TimeLineageValidationError("SOURCE_REFERENCE_CONFLICT", "source_ref conflicts with the canonical fact source")

    @classmethod
    def _decide(cls, request: TimeLineageInput, envelope: CanonicalFactEnvelope) -> TimeLineageDecision:
        if request.prediction_cutoff_at >= request.kickoff_at:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=None,
                reason_code="CUTOFF_NOT_BEFORE_KICKOFF",
                reason_detail="prediction_cutoff_at must be strictly before kickoff_at",
                future=False,
            )
        if request.ingested_at < request.observed_at:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=None,
                reason_code="INGESTED_BEFORE_OBSERVED",
                reason_detail="ingested_at cannot precede observed_at",
                future=False,
            )
        if request.source_published_at is not None and request.observed_at < request.source_published_at:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=None,
                reason_code="OBSERVED_BEFORE_PUBLISHED",
                reason_detail="observed_at cannot precede source_published_at",
                future=False,
            )
        if request.source_timestamp is not None and request.observed_at < request.source_timestamp:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=None,
                reason_code="OBSERVED_BEFORE_SOURCE_TIMESTAMP",
                reason_detail="observed_at cannot precede source_timestamp",
                future=False,
            )

        availability = {
            AvailabilityTimeBasis.SOURCE_PUBLISHED_AT: request.source_published_at,
            AvailabilityTimeBasis.SOURCE_TIMESTAMP: request.source_timestamp,
            AvailabilityTimeBasis.OBSERVED_AT: request.observed_at,
        }[request.availability_time_basis]
        if availability is None:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=None,
                reason_code="AVAILABILITY_TIME_UNKNOWN",
                reason_detail=f"{request.availability_time_basis.value} was selected but not supplied",
                future=False,
            )

        if envelope.availability_status == AvailabilityStatus.FUTURE_DATA:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.FUTURE_INFORMATION_LEAKAGE,
                availability_at=availability,
                reason_code="FACT_MARKED_FUTURE_DATA",
                reason_detail="V4-021 marked this fact as FUTURE_DATA; it cannot enter a pre-match path",
                future=True,
            )
        if envelope.availability_status != AvailabilityStatus.AVAILABLE:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.BLOCKED,
                availability_at=availability,
                reason_code="FACT_STATUS_NOT_FORMALLY_ELIGIBLE",
                reason_detail=f"V4-021 fact status is {envelope.availability_status.value}",
                future=False,
            )
        if availability >= request.kickoff_at:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.POSTMATCH_ONLY,
                availability_at=availability,
                reason_code="AVAILABLE_AT_OR_AFTER_KICKOFF",
                reason_detail="source availability is post-match information",
                future=True,
            )
        if availability > request.prediction_cutoff_at:
            return cls._decision(
                request,
                envelope,
                status=TimeGateStatus.FUTURE_INFORMATION_LEAKAGE,
                availability_at=availability,
                reason_code="AFTER_DECLARED_CUTOFF",
                reason_detail="availability_at is after prediction_cutoff_at",
                future=True,
            )
        return cls._decision(
            request,
            envelope,
            status=TimeGateStatus.PREMATCH_ALLOWED,
            availability_at=availability,
            reason_code="PREMATCH_CUTOFF_PASSED",
            reason_detail="availability_at <= prediction_cutoff_at < kickoff_at",
            future=False,
        )

    @classmethod
    def _decision(
        cls,
        request: TimeLineageInput,
        envelope: CanonicalFactEnvelope,
        *,
        status: TimeGateStatus,
        availability_at: Optional[datetime],
        reason_code: str,
        reason_detail: str,
        future: bool,
    ) -> TimeLineageDecision:
        decision_payload = {
            "fact_object_id": envelope.object_id,
            "fact_observation_id": envelope.observation_id,
            "match_id": envelope.subject.match_id,
            "source_ref": envelope.source_ref,
            "source_timestamp": _hash_time(request.source_timestamp),
            "source_published_at": _hash_time(request.source_published_at),
            "observed_at": _hash_time(request.observed_at),
            "ingested_at": _hash_time(request.ingested_at),
            "availability_at": _hash_time(availability_at),
            "availability_time_basis": request.availability_time_basis.value,
            "prediction_cutoff_at": _hash_time(request.prediction_cutoff_at),
            "kickoff_at": _hash_time(request.kickoff_at),
            "status": status.value,
            "reason_code": reason_code,
        }
        decision_id = str(uuid.uuid5(TIME_LINEAGE_NAMESPACE, f"decision|{sha256_json(decision_payload)}"))
        provenance_hash = sha256_json(
            {
                "fact_object_id": envelope.object_id,
                "fact_observation_id": envelope.observation_id,
                "source": envelope.source,
                "source_ref": envelope.source_ref,
                "source_timestamp": _hash_time(request.source_timestamp),
                "source_published_at": _hash_time(request.source_published_at),
                "observed_at": _hash_time(request.observed_at),
                "ingested_at": _hash_time(request.ingested_at),
            }
        )
        lineage_hash = sha256_json({"decision": decision_payload, "provenance_hash": provenance_hash})
        return TimeLineageDecision(
            decision_id=decision_id,
            contract_version=CONTRACT_VERSION,
            fact_object_id=envelope.object_id,
            fact_observation_id=envelope.observation_id,
            match_id=envelope.subject.match_id,
            source_ref=envelope.source_ref,
            source_timestamp=_iso(request.source_timestamp) if request.source_timestamp else None,
            source_published_at=_iso(request.source_published_at) if request.source_published_at else None,
            observed_at=_iso(request.observed_at),
            ingested_at=_iso(request.ingested_at),
            availability_at=_iso(availability_at) if availability_at else None,
            availability_time_basis=request.availability_time_basis,
            prediction_cutoff_at=_iso(request.prediction_cutoff_at),
            kickoff_at=_iso(request.kickoff_at),
            status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            provenance_hash=provenance_hash,
            lineage_hash=lineage_hash,
            future_information_leakage=future,
            run_invalid=future,
            tier_a_eligible=not future and status == TimeGateStatus.PREMATCH_ALLOWED,
            promotion_evidence=not future and status == TimeGateStatus.PREMATCH_ALLOWED,
        )

    def _append_event(
        self,
        action: str,
        decision_id: Optional[str],
        fact_object_id: Optional[str],
        status: TimeGateStatus,
        reason_code: Optional[str],
    ) -> None:
        self._events.append(
            _TimeAppendEvent(
                sequence=len(self._events) + 1,
                action=action,
                decision_id=decision_id,
                fact_object_id=fact_object_id,
                status=status,
                reason_code=reason_code,
            )
        )
