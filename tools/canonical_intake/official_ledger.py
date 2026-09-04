"""V4-027 official odds timestamp and provenance ledger.

This module consumes the accepted V4-024 snapshot and V4-026 availability
gate, optionally retaining the V4-025 screenshot evidence reference.  It is a
local append-only, no-write boundary.  V4-022's governed time statuses and
availability-time basis are reused; no new cutoff enum or persistence adapter
is introduced here.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from tools.migration_harness.common import sha256_json

from .match_identity import IdentityValidationError, _iso, _parse_timestamp
from .official_availability import AvailabilityGateOutcome, AvailabilityGateResult, MarketGateStatus
from .official_odds import MARKETS, OfficialOddsSnapshot
from .official_screenshot import OfficialScreenshotEvidence
from .time_lineage import AvailabilityTimeBasis, TimeGateStatus


CONTRACT_VERSION = "official-odds-provenance-ledger@1.0.0"
LEDGER_NAMESPACE = uuid.UUID("d0bf5c16-6d2c-58f4-bb34-1eb4ff0c4d42")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class OfficialOddsLedgerValidationError(ValueError):
    """A source, gate, or time lineage cannot be recorded safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LedgerAction(str, Enum):
    APPENDED = "APPENDED"
    DUPLICATE_NOOP = "DUPLICATE_NOOP"
    BLOCKED = "BLOCKED"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfficialOddsLedgerValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not UUID_RE.fullmatch(result):
        raise OfficialOddsLedgerValidationError("REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _time(value: Any, field_name: str) -> datetime:
    try:
        parsed = _parse_timestamp(value, field_name)
    except IdentityValidationError as exc:
        raise OfficialOddsLedgerValidationError(exc.code, exc.message) from exc
    assert parsed is not None
    return parsed


def _hash_time(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds") if value else None


def _source_time(value: str, field_name: str) -> Optional[datetime]:
    if value in {"UNKNOWN", "CONFLICTED"}:
        return None
    return _time(value, field_name)


@dataclass(frozen=True)
class OddsLedgerRequest:
    prediction_cutoff_at: datetime
    kickoff_at: datetime
    availability_time_basis: AvailabilityTimeBasis
    supersedes_ledger_id: Optional[str] = None

    @classmethod
    def from_values(
        cls,
        prediction_cutoff_at: Any,
        kickoff_at: Any,
        availability_time_basis: Any,
        supersedes_ledger_id: Optional[str] = None,
    ) -> "OddsLedgerRequest":
        cutoff = _time(prediction_cutoff_at, "prediction_cutoff_at")
        kickoff = _time(kickoff_at, "kickoff_at")
        if not isinstance(availability_time_basis, (AvailabilityTimeBasis, str)):
            raise OfficialOddsLedgerValidationError(
                "AVAILABILITY_BASIS_REQUIRED", "availability_time_basis must be explicitly selected"
            )
        try:
            basis = AvailabilityTimeBasis(availability_time_basis)
        except ValueError as exc:
            raise OfficialOddsLedgerValidationError(
                "AVAILABILITY_BASIS_INVALID", f"unsupported availability_time_basis: {availability_time_basis}"
            ) from exc
        supersedes = _uuid(supersedes_ledger_id, "supersedes_ledger_id") if supersedes_ledger_id is not None else None
        return cls(cutoff, kickoff, basis, supersedes)


@dataclass(frozen=True)
class OddsProvenanceLedgerEntry:
    ledger_id: str
    contract_version: str
    match_id: str
    snapshot_id: str
    snapshot_observation_id: str
    gate_id: str
    screenshot_evidence_id: Optional[str]
    source: str
    source_type: str
    source_reference: str
    source_is_official: bool
    source_timestamp: Optional[str]
    published_at: Optional[str]
    captured_at: str
    observed_at: str
    ingested_at: str
    evidence_source_timestamp: Optional[str]
    evidence_captured_at: Optional[str]
    evidence_observed_at: Optional[str]
    evidence_ingested_at: Optional[str]
    availability_at: Optional[str]
    availability_time_basis: AvailabilityTimeBasis
    prediction_cutoff_at: str
    kickoff_at: str
    gate_outcome: AvailabilityGateOutcome
    market_statuses: Mapping[str, MarketGateStatus]
    status: TimeGateStatus
    reason_code: str
    reason_detail: str
    snapshot_hash: str
    payload_hash: str
    snapshot_provenance_hash: str
    screenshot_provenance_hash: Optional[str]
    provenance_hash: str
    ledger_hash: str
    future_information_leakage: bool
    run_invalid: bool
    supersedes_ledger_id: Optional[str]
    revision: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_observation_id": self.snapshot_observation_id,
            "gate_id": self.gate_id,
            "screenshot_evidence_id": self.screenshot_evidence_id,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_is_official": self.source_is_official,
            "source_timestamp": self.source_timestamp,
            "published_at": self.published_at,
            "captured_at": self.captured_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "evidence_source_timestamp": self.evidence_source_timestamp,
            "evidence_captured_at": self.evidence_captured_at,
            "evidence_observed_at": self.evidence_observed_at,
            "evidence_ingested_at": self.evidence_ingested_at,
            "availability_at": self.availability_at,
            "availability_time_basis": self.availability_time_basis.value,
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "gate_outcome": self.gate_outcome.value,
            "market_statuses": {market: status.value for market, status in self.market_statuses.items()},
            "status": self.status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "snapshot_hash": self.snapshot_hash,
            "payload_hash": self.payload_hash,
            "snapshot_provenance_hash": self.snapshot_provenance_hash,
            "screenshot_provenance_hash": self.screenshot_provenance_hash,
            "provenance_hash": self.provenance_hash,
            "ledger_hash": self.ledger_hash,
            "future_information_leakage": self.future_information_leakage,
            "run_invalid": self.run_invalid,
            "supersedes_ledger_id": self.supersedes_ledger_id,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class OddsLedgerResult:
    accepted: bool
    action: LedgerAction
    status: TimeGateStatus
    entry: Optional[OddsProvenanceLedgerEntry]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action": self.action.value,
            "status": self.status.value,
            "entry": self.entry.to_dict() if self.entry else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _LedgerEvent:
    sequence: int
    action: LedgerAction
    ledger_id: Optional[str]
    snapshot_id: Optional[str]
    status: TimeGateStatus
    reason_code: Optional[str]


class OfficialOddsProvenanceLedger:
    """Append-only local provenance ledger for official odds snapshots."""

    def __init__(self):
        self._entries: Dict[str, OddsProvenanceLedgerEntry] = {}
        self._events: List[_LedgerEvent] = []

    @property
    def entries(self) -> Tuple[OddsProvenanceLedgerEntry, ...]:
        return tuple(self._entries.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action.value,
                    "ledger_id": event.ledger_id,
                    "snapshot_id": event.snapshot_id,
                    "status": event.status.value,
                    "reason_code": event.reason_code,
                }
            )
            for event in self._events
        )

    def get(self, ledger_id: str) -> Optional[OddsProvenanceLedgerEntry]:
        return self._entries.get(ledger_id)

    def record(
        self,
        snapshot: OfficialOddsSnapshot,
        gate_result: AvailabilityGateResult,
        prediction_cutoff_at: Any,
        kickoff_at: Any,
        availability_time_basis: Any = AvailabilityTimeBasis.SOURCE_TIMESTAMP,
        screenshot_evidence: Optional[OfficialScreenshotEvidence] = None,
        supersedes_ledger_id: Optional[str] = None,
    ) -> OddsLedgerResult:
        try:
            request = OddsLedgerRequest.from_values(
                prediction_cutoff_at,
                kickoff_at,
                availability_time_basis,
                supersedes_ledger_id,
            )
            self._validate_inputs(snapshot, gate_result, screenshot_evidence, request)
            logical = self._logical_identity(snapshot, gate_result, screenshot_evidence, request)
            ledger_id = str(uuid.uuid5(LEDGER_NAMESPACE, f"ledger|{sha256_json(logical)}"))
            existing = self._entries.get(ledger_id)
            if existing is not None:
                self._append_event(LedgerAction.DUPLICATE_NOOP, existing, None)
                return OddsLedgerResult(existing.status == TimeGateStatus.PREMATCH_ALLOWED, LedgerAction.DUPLICATE_NOOP, existing.status, existing)
            predecessor = self._entries.get(request.supersedes_ledger_id) if request.supersedes_ledger_id else None
            if request.supersedes_ledger_id is not None:
                if predecessor is None:
                    return self._blocked(snapshot, "SUPERSEDES_LEDGER_NOT_FOUND", "supersedes_ledger_id does not identify an existing ledger entry")
                if predecessor.match_id != snapshot.match_id:
                    return self._blocked(snapshot, "SUPERSEDES_MATCH_CONFLICT", "superseded ledger entry belongs to another canonical match")
            entry = self._build_entry(snapshot, gate_result, screenshot_evidence, request, ledger_id, revision=(predecessor.revision + 1 if predecessor else 1))
            self._entries[ledger_id] = entry
            self._append_event(LedgerAction.APPENDED, entry, entry.reason_code)
            return OddsLedgerResult(entry.status == TimeGateStatus.PREMATCH_ALLOWED, LedgerAction.APPENDED, entry.status, entry)
        except OfficialOddsLedgerValidationError as exc:
            snapshot_id = snapshot.snapshot_id if isinstance(snapshot, OfficialOddsSnapshot) else None
            self._append_event(LedgerAction.BLOCKED, None, exc.code, snapshot_id=snapshot_id)
            return OddsLedgerResult(False, LedgerAction.BLOCKED, TimeGateStatus.BLOCKED, None, exc.code)

    @staticmethod
    def _validate_inputs(
        snapshot: OfficialOddsSnapshot,
        gate_result: AvailabilityGateResult,
        screenshot_evidence: Optional[OfficialScreenshotEvidence],
        request: OddsLedgerRequest,
    ) -> None:
        if not isinstance(snapshot, OfficialOddsSnapshot):
            raise OfficialOddsLedgerValidationError("SNAPSHOT_REQUIRED", "V4-027 requires a V4-024 OfficialOddsSnapshot")
        if not isinstance(gate_result, AvailabilityGateResult):
            raise OfficialOddsLedgerValidationError("GATE_RESULT_REQUIRED", "V4-027 requires a V4-026 AvailabilityGateResult")
        if not gate_result.gate_id or gate_result.match_id != snapshot.match_id or gate_result.snapshot_id != snapshot.snapshot_id:
            raise OfficialOddsLedgerValidationError("GATE_REFERENCE_CONFLICT", "gate result does not bind to the supplied snapshot")
        if set(gate_result.decisions) != set(MARKETS):
            raise OfficialOddsLedgerValidationError("GATE_MARKET_SET_INVALID", "gate result must cover exactly five official markets")
        if screenshot_evidence is not None:
            if not isinstance(screenshot_evidence, OfficialScreenshotEvidence):
                raise OfficialOddsLedgerValidationError("SCREENSHOT_EVIDENCE_INVALID", "screenshot evidence must be V4-025 OfficialScreenshotEvidence")
            if screenshot_evidence.match_id != snapshot.match_id:
                raise OfficialOddsLedgerValidationError("MATCH_IDENTITY_CONFLICT", "snapshot and screenshot evidence match_id differ")
            evidence_ids = {decision.screenshot_evidence_id for decision in gate_result.decisions.values()}
            if evidence_ids - {screenshot_evidence.evidence_id, None}:
                raise OfficialOddsLedgerValidationError("EVIDENCE_REFERENCE_CONFLICT", "gate result points to a different screenshot evidence record")
        if request.prediction_cutoff_at >= request.kickoff_at:
            raise OfficialOddsLedgerValidationError("CUTOFF_NOT_BEFORE_KICKOFF", "prediction_cutoff_at must be strictly before kickoff_at")
        if _time(snapshot.ingested_at, "snapshot.ingested_at") < _time(snapshot.observed_at, "snapshot.observed_at"):
            raise OfficialOddsLedgerValidationError("INGESTED_BEFORE_OBSERVED", "snapshot ingested_at cannot precede observed_at")
        if screenshot_evidence is not None:
            if _time(screenshot_evidence.ingested_at, "screenshot.ingested_at") < _time(screenshot_evidence.observed_at, "screenshot.observed_at"):
                raise OfficialOddsLedgerValidationError("INGESTED_BEFORE_OBSERVED", "screenshot ingested_at cannot precede observed_at")
            snapshot_time = _source_time(snapshot.source_timestamp, "snapshot.source_timestamp")
            evidence_time = _source_time(screenshot_evidence.source_timestamp, "screenshot.source_timestamp")
            if snapshot_time is not None and evidence_time is not None and snapshot_time != evidence_time:
                raise OfficialOddsLedgerValidationError("SOURCE_TIMESTAMP_CONFLICT", "feed and screenshot source timestamps differ")

    @staticmethod
    def _logical_identity(
        snapshot: OfficialOddsSnapshot,
        gate_result: AvailabilityGateResult,
        screenshot_evidence: Optional[OfficialScreenshotEvidence],
        request: OddsLedgerRequest,
    ) -> Dict[str, Any]:
        return {
            "match_id": snapshot.match_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_observation_id": snapshot.observation_id,
            "gate_id": gate_result.gate_id,
            "screenshot_evidence_id": screenshot_evidence.evidence_id if screenshot_evidence else None,
            "availability_time_basis": request.availability_time_basis.value,
            "prediction_cutoff_at": _hash_time(request.prediction_cutoff_at),
            "kickoff_at": _hash_time(request.kickoff_at),
            "supersedes_ledger_id": request.supersedes_ledger_id,
        }

    @classmethod
    def _build_entry(
        cls,
        snapshot: OfficialOddsSnapshot,
        gate_result: AvailabilityGateResult,
        screenshot_evidence: Optional[OfficialScreenshotEvidence],
        request: OddsLedgerRequest,
        ledger_id: str,
        revision: int,
    ) -> OddsProvenanceLedgerEntry:
        source_time = _source_time(snapshot.source_timestamp, "snapshot.source_timestamp")
        published_at = None
        if screenshot_evidence is not None and screenshot_evidence.published_at is not None:
            published_at = _time(screenshot_evidence.published_at, "screenshot.published_at")
        selected = {
            AvailabilityTimeBasis.SOURCE_PUBLISHED_AT: published_at,
            AvailabilityTimeBasis.SOURCE_TIMESTAMP: source_time,
            AvailabilityTimeBasis.OBSERVED_AT: _time(snapshot.observed_at, "snapshot.observed_at"),
        }[request.availability_time_basis]
        status, reason_code, reason_detail, future = cls._decide_time(gate_result, request, selected)
        market_statuses = MappingProxyType({market: gate_result.decisions[market].status for market in MARKETS})
        provenance_logical = {
            "match_id": snapshot.match_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_observation_id": snapshot.observation_id,
            "gate_id": gate_result.gate_id,
            "screenshot_evidence_id": screenshot_evidence.evidence_id if screenshot_evidence else None,
            "source": snapshot.source,
            "source_type": snapshot.source_type,
            "source_reference": snapshot.source_reference,
            "source_timestamp": snapshot.source_timestamp,
            "published_at": _iso(published_at) if published_at else None,
            "captured_at": snapshot.captured_at,
            "observed_at": snapshot.observed_at,
            "ingested_at": snapshot.ingested_at,
            "evidence_source_timestamp": screenshot_evidence.source_timestamp if screenshot_evidence else None,
            "evidence_captured_at": screenshot_evidence.captured_at if screenshot_evidence else None,
            "evidence_observed_at": screenshot_evidence.observed_at if screenshot_evidence else None,
            "evidence_ingested_at": screenshot_evidence.ingested_at if screenshot_evidence else None,
            "availability_at": _iso(selected) if selected else None,
            "availability_time_basis": request.availability_time_basis.value,
            "prediction_cutoff_at": _iso(request.prediction_cutoff_at),
            "kickoff_at": _iso(request.kickoff_at),
            "gate_outcome": gate_result.outcome.value,
            "market_statuses": {market: market_statuses[market].value for market in MARKETS},
            "status": status.value,
            "reason_code": reason_code,
            "snapshot_provenance_hash": snapshot.provenance_hash,
            "screenshot_provenance_hash": screenshot_evidence.provenance_hash if screenshot_evidence else None,
        }
        provenance_hash = sha256_json(provenance_logical)
        ledger_logical = {"ledger_id": ledger_id, "provenance_hash": provenance_hash, "reason_detail": reason_detail}
        ledger_hash = sha256_json(ledger_logical)
        return OddsProvenanceLedgerEntry(
            ledger_id=ledger_id,
            contract_version=CONTRACT_VERSION,
            match_id=snapshot.match_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_observation_id=snapshot.observation_id,
            gate_id=gate_result.gate_id,
            screenshot_evidence_id=screenshot_evidence.evidence_id if screenshot_evidence else None,
            source=snapshot.source,
            source_type=snapshot.source_type,
            source_reference=snapshot.source_reference,
            source_is_official=snapshot.source_is_official,
            source_timestamp=snapshot.source_timestamp,
            published_at=_iso(published_at) if published_at else None,
            captured_at=snapshot.captured_at,
            observed_at=snapshot.observed_at,
            ingested_at=snapshot.ingested_at,
            evidence_source_timestamp=screenshot_evidence.source_timestamp if screenshot_evidence else None,
            evidence_captured_at=screenshot_evidence.captured_at if screenshot_evidence else None,
            evidence_observed_at=screenshot_evidence.observed_at if screenshot_evidence else None,
            evidence_ingested_at=screenshot_evidence.ingested_at if screenshot_evidence else None,
            availability_at=_iso(selected) if selected else None,
            availability_time_basis=request.availability_time_basis,
            prediction_cutoff_at=_iso(request.prediction_cutoff_at),
            kickoff_at=_iso(request.kickoff_at),
            gate_outcome=gate_result.outcome,
            market_statuses=market_statuses,
            status=status,
            reason_code=reason_code,
            reason_detail=reason_detail,
            snapshot_hash=snapshot.snapshot_hash,
            payload_hash=snapshot.payload_hash,
            snapshot_provenance_hash=snapshot.provenance_hash,
            screenshot_provenance_hash=screenshot_evidence.provenance_hash if screenshot_evidence else None,
            provenance_hash=provenance_hash,
            ledger_hash=ledger_hash,
            future_information_leakage=future,
            run_invalid=future or not gate_result.downstream_ready,
            supersedes_ledger_id=request.supersedes_ledger_id,
            revision=revision,
        )

    @staticmethod
    def _decide_time(
        gate_result: AvailabilityGateResult,
        request: OddsLedgerRequest,
        availability: Optional[datetime],
    ) -> Tuple[TimeGateStatus, str, str, bool]:
        if gate_result.outcome == AvailabilityGateOutcome.BLOCKED or not gate_result.accepted:
            return TimeGateStatus.BLOCKED, "AVAILABILITY_GATE_BLOCKED", "V4-026 availability gate did not accept this official snapshot", False
        if gate_result.outcome == AvailabilityGateOutcome.EXPLICIT_MISSINGNESS or not gate_result.downstream_ready:
            return TimeGateStatus.BLOCKED, "OFFICIAL_MARKET_MISSINGNESS_NOT_READY", "official market availability is explicit but not downstream-ready", False
        if availability is None:
            return TimeGateStatus.BLOCKED, "UNKNOWN_TIME_BLOCKED", "selected official source availability time is UNKNOWN or CONFLICTED", False
        if availability >= request.kickoff_at:
            return TimeGateStatus.POSTMATCH_ONLY, "AVAILABLE_AT_OR_AFTER_KICKOFF", "official odds availability is at or after canonical kickoff", True
        if availability > request.prediction_cutoff_at:
            return TimeGateStatus.FUTURE_INFORMATION_LEAKAGE, "AFTER_DECLARED_CUTOFF", "official odds availability is after the declared cutoff", True
        return TimeGateStatus.PREMATCH_ALLOWED, "PREMATCH_CUTOFF_PASSED", "availability_at <= prediction_cutoff_at < kickoff_at", False

    def _blocked(self, snapshot: Any, code: str, detail: str, *, snapshot_id: Optional[str] = None) -> OddsLedgerResult:
        actual_snapshot_id = snapshot_id or (snapshot.snapshot_id if isinstance(snapshot, OfficialOddsSnapshot) else None)
        self._events.append(_LedgerEvent(len(self._events) + 1, LedgerAction.BLOCKED, None, actual_snapshot_id, TimeGateStatus.BLOCKED, code))
        return OddsLedgerResult(False, LedgerAction.BLOCKED, TimeGateStatus.BLOCKED, None, code)

    def _append_event(self, action: LedgerAction, entry: Optional[OddsProvenanceLedgerEntry], reason_code: Optional[str], *, snapshot_id: Optional[str] = None) -> None:
        self._events.append(
            _LedgerEvent(
                len(self._events) + 1,
                action,
                entry.ledger_id if entry else None,
                entry.snapshot_id if entry else snapshot_id,
                entry.status if entry else TimeGateStatus.BLOCKED,
                reason_code,
            )
        )
