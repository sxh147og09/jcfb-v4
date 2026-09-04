"""V4-026 official five-market availability and missingness gate.

This local in-memory gate consumes the V4-024 typed official snapshot and,
when present, V4-025 screenshot evidence.  It never fabricates a market,
coerces missingness into a payload, or writes to a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore
from .official_odds import MARKETS, OfficialOddsSnapshot
from .official_screenshot import OfficialScreenshotEvidence


CONTRACT_VERSION = "official-market-availability-gate@1.0.0"
GATE_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")


class MarketGateStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"


class AvailabilityGateOutcome(str, Enum):
    PASSED = "PASSED"
    EXPLICIT_MISSINGNESS = "EXPLICIT_MISSINGNESS"
    BLOCKED = "BLOCKED"


class AvailabilityGateValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MarketAvailabilityDecision:
    market: str
    status: MarketGateStatus
    reason_code: str
    reason_detail: str
    payload: Optional[Mapping[str, Any]]
    snapshot_id: str
    screenshot_evidence_id: Optional[str]
    source_status: str
    competing_evidence: Tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "payload": dict(self.payload) if self.payload is not None else None,
            "snapshot_id": self.snapshot_id,
            "screenshot_evidence_id": self.screenshot_evidence_id,
            "source_status": self.source_status,
            "competing_evidence": [dict(item) for item in self.competing_evidence],
        }


@dataclass(frozen=True)
class AvailabilityGateResult:
    gate_id: str
    contract_version: str
    match_id: str
    snapshot_id: str
    outcome: AvailabilityGateOutcome
    accepted: bool
    downstream_ready: bool
    decisions: Mapping[str, MarketAvailabilityDecision]
    reason_code: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "snapshot_id": self.snapshot_id,
            "outcome": self.outcome.value,
            "accepted": self.accepted,
            "downstream_ready": self.downstream_ready,
            "decisions": {market: decision.to_dict() for market, decision in self.decisions.items()},
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class _GateEvent:
    sequence: int
    action: str
    gate_id: str
    snapshot_id: str
    outcome: AvailabilityGateOutcome
    reason_code: Optional[str]


def _evidence_payload(evidence: OfficialScreenshotEvidence, market: str) -> Optional[Mapping[str, Any]]:
    return evidence.market_observations[market].get("payload")


class OfficialMarketAvailabilityGate:
    """Append-only local gate for official market missingness semantics."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-026 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._results: Dict[str, AvailabilityGateResult] = {}
        self._events: List[_GateEvent] = []

    @property
    def results(self) -> Tuple[AvailabilityGateResult, ...]:
        return tuple(self._results.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType({
                "sequence": item.sequence,
                "action": item.action,
                "gate_id": item.gate_id,
                "snapshot_id": item.snapshot_id,
                "outcome": item.outcome.value,
                "reason_code": item.reason_code,
            })
            for item in self._events
        )

    def evaluate(
        self,
        snapshot: OfficialOddsSnapshot,
        screenshot_evidence: Optional[OfficialScreenshotEvidence] = None,
    ) -> AvailabilityGateResult:
        if not isinstance(snapshot, OfficialOddsSnapshot):
            raise AvailabilityGateValidationError("SNAPSHOT_REQUIRED", "V4-026 requires a V4-024 OfficialOddsSnapshot")
        identity = self._identity_store.get(snapshot.match_id)
        if identity is None or identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            raise AvailabilityGateValidationError("MATCH_IDENTITY_NOT_RESOLVED", "snapshot match_id is not a resolved V4-020 identity")
        if screenshot_evidence is not None:
            if not isinstance(screenshot_evidence, OfficialScreenshotEvidence):
                raise AvailabilityGateValidationError("SCREENSHOT_EVIDENCE_INVALID", "screenshot evidence must be V4-025 OfficialScreenshotEvidence")
            if screenshot_evidence.match_id != snapshot.match_id:
                raise AvailabilityGateValidationError("MATCH_IDENTITY_CONFLICT", "snapshot and screenshot evidence match_id differ")
        evidence_id = screenshot_evidence.evidence_id if screenshot_evidence else None
        gate_id = str(uuid.uuid5(GATE_NAMESPACE, f"gate|{snapshot.snapshot_id}|{evidence_id or 'NONE'}"))
        existing = self._results.get(gate_id)
        if existing is not None:
            self._append_event("DUPLICATE_NOOP", existing)
            return existing
        decisions: Dict[str, MarketAvailabilityDecision] = {}
        for market in MARKETS:
            source = snapshot.market_availability[market]
            source_status = str(source["status"])
            source_payload = snapshot.payloads[market]
            screenshot_item = screenshot_evidence.market_observations[market] if screenshot_evidence else None
            screenshot_status = str(screenshot_item["status"]) if screenshot_item else None
            screenshot_payload = _evidence_payload(screenshot_evidence, market) if screenshot_evidence else None
            decisions[market] = self._decide_market(
                market,
                source_status,
                source["reason"],
                source_payload,
                snapshot.snapshot_id,
                evidence_id,
                screenshot_status,
                screenshot_payload,
                screenshot_item,
            )
        statuses = {decision.status for decision in decisions.values()}
        if MarketGateStatus.BLOCKED in statuses:
            outcome = AvailabilityGateOutcome.BLOCKED
            accepted = False
            downstream_ready = False
            reason_code = "MARKET_AVAILABILITY_BLOCKED"
        elif MarketGateStatus.NOT_VERIFIED in statuses:
            outcome = AvailabilityGateOutcome.BLOCKED
            accepted = False
            downstream_ready = False
            reason_code = "MARKET_NOT_VERIFIED"
        elif MarketGateStatus.UNAVAILABLE in statuses:
            outcome = AvailabilityGateOutcome.EXPLICIT_MISSINGNESS
            accepted = True
            downstream_ready = False
            reason_code = "OFFICIAL_MARKET_UNAVAILABLE"
        else:
            outcome = AvailabilityGateOutcome.PASSED
            accepted = True
            downstream_ready = True
            reason_code = None
        result = AvailabilityGateResult(gate_id, CONTRACT_VERSION, snapshot.match_id, snapshot.snapshot_id, outcome, accepted, downstream_ready, MappingProxyType(decisions), reason_code)
        self._results[gate_id] = result
        self._events.append(_GateEvent(len(self._events) + 1, "APPEND_GATE_RESULT", gate_id, snapshot.snapshot_id, outcome, reason_code))
        return result

    @staticmethod
    def _decide_market(
        market: str,
        source_status: str,
        source_reason: str,
        source_payload: Optional[Mapping[str, Any]],
        snapshot_id: str,
        evidence_id: Optional[str],
        screenshot_status: Optional[str],
        screenshot_payload: Optional[Mapping[str, Any]],
        screenshot_item: Optional[Mapping[str, Any]],
    ) -> MarketAvailabilityDecision:
        base = {
            "snapshot_id": snapshot_id,
            "screenshot_evidence_id": evidence_id,
            "source_status": source_status,
        }
        if source_status == "UNAVAILABLE":
            if source_payload is not None:
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "UNAVAILABLE_PAYLOAD_PRESENT", "source marked unavailable but contains payload", None, **base)
            if screenshot_status in {"VERIFIED", "CONFLICTED"}:
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "FEED_SCREENSHOT_AVAILABILITY_CONFLICT", "feed says unavailable but screenshot evidence contains a market claim", None, competing_evidence=({"source": "official_feed", "status": source_status, "reason": source_reason}, {"source": "official_screenshot", "status": screenshot_status, "payload": screenshot_payload}), **base)
            return MarketAvailabilityDecision(market, MarketGateStatus.UNAVAILABLE, source_reason, "official source explicitly did not supply this market", None, **base)
        if source_status == "AVAILABLE":
            if source_payload is None:
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "AVAILABLE_PAYLOAD_MISSING", "source marked available without a typed payload", None, **base)
            if screenshot_status in {"NOT_VERIFIED", "BLOCKED"}:
                return MarketAvailabilityDecision(market, MarketGateStatus.NOT_VERIFIED, "SCREENSHOT_NOT_VERIFIED", "official screenshot extraction is not verified", None, **base)
            if screenshot_status == "CONFLICTED":
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "SCREENSHOT_EXTRACTION_CONFLICT", "official screenshot retains conflicting extraction candidates", None, competing_evidence=({"source": "official_feed", "status": source_status, "payload": source_payload}, {"source": "official_screenshot", "status": screenshot_status, "candidates": screenshot_item.get("candidates", []) if screenshot_item else []}), **base)
            if screenshot_status == "UNAVAILABLE":
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "FEED_SCREENSHOT_AVAILABILITY_CONFLICT", "feed and screenshot disagree on market availability", None, competing_evidence=({"source": "official_feed", "status": source_status, "payload": source_payload}, {"source": "official_screenshot", "status": screenshot_status}), **base)
            if screenshot_status == "VERIFIED" and sha256_json(source_payload) != sha256_json(screenshot_payload):
                return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "FEED_SCREENSHOT_PAYLOAD_CONFLICT", "feed and screenshot typed payloads differ", None, competing_evidence=({"source": "official_feed", "payload": source_payload}, {"source": "official_screenshot", "payload": screenshot_payload}), **base)
            return MarketAvailabilityDecision(market, MarketGateStatus.AVAILABLE, "NOT_APPLICABLE", "official market payload passed availability checks", source_payload, **base)
        return MarketAvailabilityDecision(market, MarketGateStatus.BLOCKED, "SOURCE_MARKET_STATUS_NOT_GATED", f"source market status {source_status} is not accepted by V4-026", None, **base)

    def _append_event(self, action: str, result: AvailabilityGateResult) -> None:
        self._events.append(_GateEvent(len(self._events) + 1, action, result.gate_id, result.snapshot_id, result.outcome, result.reason_code))
