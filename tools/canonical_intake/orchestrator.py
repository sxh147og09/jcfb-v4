"""V4-023 canonical intake orchestration and idempotency.

This module composes the already accepted V4-020 identity, V4-021 fact, and
V4-022 time-lineage boundaries. It is intentionally local and no-write:
there is no database adapter, migration, Supabase connection, model runner,
or production path here.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

from tools.migration_harness.common import sha256_json

from .fact_envelope import CanonicalFactStore, FactIntakeResult
from .match_identity import CanonicalMatchIdentityStore, IdentityIntakeResult
from .time_lineage import TimeGateResult, TimeGateStatus, TimeLineageStore


CONTRACT_VERSION = "canonical-intake-orchestrator@1.0.0"
ORCHESTRATOR_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")
PACKET_KEYS = frozenset({"idempotency_key", "identity_observation", "fact_observation", "time_lineage"})


class IntakeOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    BLOCKED = "BLOCKED"
    DUPLICATE_NOOP = "DUPLICATE_NOOP"


class OrchestratorValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestratorValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
    return value.strip()


def _find_forbidden_key(value: Any, path: str = "packet") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).strip().casefold())
            if (
                normalized in {
                    "prediction",
                    "prediction_output",
                    "recommendation",
                    "confidence",
                    "modelinterpretation",
                    "engineoutput",
                }
                or (normalized.startswith("prediction_") and normalized != "prediction_cutoff_at")
                or "v333" in normalized
                or "v3_3_3" in normalized
            ):
                return f"{path}.{key}"
            found = _find_forbidden_key(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_forbidden_key(child, f"{path}[{index}]")
            if found:
                return found
    return None


@dataclass(frozen=True)
class IntakeDeliveryRecord:
    delivery_id: str
    idempotency_key: str
    request_hash: str
    identity_observation_id: Optional[str]
    fact_observation_id: Optional[str]
    time_decision_id: Optional[str]
    outcome: IntakeOutcome
    reason_code: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "contract_version": CONTRACT_VERSION,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "identity_observation_id": self.identity_observation_id,
            "fact_observation_id": self.fact_observation_id,
            "time_decision_id": self.time_decision_id,
            "outcome": self.outcome.value,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class IntakeResult:
    accepted: bool
    outcome: IntakeOutcome
    idempotency_key: Optional[str]
    delivery_id: Optional[str]
    identity: Optional[IdentityIntakeResult]
    fact: Optional[FactIntakeResult]
    time: Optional[TimeGateResult]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "outcome": self.outcome.value,
            "idempotency_key": self.idempotency_key,
            "delivery_id": self.delivery_id,
            "identity": self.identity.to_dict() if self.identity else None,
            "fact": self.fact.to_dict() if self.fact else None,
            "time": self.time.to_dict() if self.time else None,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _OrchestratorEvent:
    sequence: int
    action: str
    delivery_id: Optional[str]
    idempotency_key: Optional[str]
    outcome: IntakeOutcome
    reason_code: Optional[str]


class CanonicalIntakeOrchestrator:
    """V4-023 local coordinator for identity, fact, time, and idempotency."""

    def __init__(
        self,
        identity_store: Optional[CanonicalMatchIdentityStore] = None,
        fact_store: Optional[CanonicalFactStore] = None,
        time_store: Optional[TimeLineageStore] = None,
    ):
        self.identity_store = identity_store or CanonicalMatchIdentityStore()
        self.fact_store = fact_store or CanonicalFactStore(self.identity_store)
        self.time_store = time_store or TimeLineageStore(self.fact_store)
        if not isinstance(self.identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-023 requires a V4-020 CanonicalMatchIdentityStore")
        if not isinstance(self.fact_store, CanonicalFactStore):
            raise TypeError("V4-023 requires a V4-021 CanonicalFactStore")
        if not isinstance(self.time_store, TimeLineageStore):
            raise TypeError("V4-023 requires a V4-022 TimeLineageStore")
        self._deliveries_by_key: Dict[str, IntakeDeliveryRecord] = {}
        self._deliveries: Dict[str, IntakeDeliveryRecord] = {}
        self._events: List[_OrchestratorEvent] = []

    @property
    def deliveries(self) -> Tuple[IntakeDeliveryRecord, ...]:
        return tuple(self._deliveries.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "delivery_id": event.delivery_id,
                    "idempotency_key": event.idempotency_key,
                    "outcome": event.outcome.value,
                    "reason_code": event.reason_code,
                }
            )
            for event in self._events
        )

    def ingest(self, packet: Mapping[str, Any]) -> IntakeResult:
        request_hash = sha256_json(packet)
        try:
            idempotency_key = self._validate_packet(packet)
        except OrchestratorValidationError as exc:
            self._append_event("BLOCKED_PACKET", None, None, IntakeOutcome.BLOCKED, exc.code)
            return IntakeResult(False, IntakeOutcome.BLOCKED, None, None, None, None, None, exc.code)

        previous = self._deliveries_by_key.get(idempotency_key)
        if previous is not None:
            if previous.request_hash != request_hash:
                self._append_event("BLOCKED_IDEMPOTENCY_REUSE", previous.delivery_id, idempotency_key, IntakeOutcome.BLOCKED, "IDEMPOTENCY_KEY_REUSE_CONFLICT")
                return IntakeResult(False, IntakeOutcome.BLOCKED, idempotency_key, previous.delivery_id, None, None, None, "IDEMPOTENCY_KEY_REUSE_CONFLICT")
            self._append_event("DUPLICATE_NOOP", previous.delivery_id, idempotency_key, previous.outcome, None)
            return IntakeResult(
                previous.outcome == IntakeOutcome.ACCEPTED,
                IntakeOutcome.DUPLICATE_NOOP,
                idempotency_key,
                previous.delivery_id,
                None,
                None,
                None,
                None,
            )

        delivery_id = str(uuid.uuid5(ORCHESTRATOR_NAMESPACE, f"delivery|{idempotency_key}|{request_hash}"))
        identity_result = self.identity_store.ingest(packet["identity_observation"])
        if not identity_result.accepted:
            return self._record_delivery(
                delivery_id,
                idempotency_key,
                request_hash,
                identity_result.observation_id,
                None,
                None,
                IntakeOutcome.BLOCKED,
                identity_result.resolution_action,
                identity_result,
                None,
                None,
            )

        fact_result = self.fact_store.ingest(packet["fact_observation"])
        if not fact_result.accepted or fact_result.envelope is None:
            return self._record_delivery(
                delivery_id,
                idempotency_key,
                request_hash,
                identity_result.observation_id,
                fact_result.observation_id,
                None,
                IntakeOutcome.BLOCKED,
                fact_result.error_code or fact_result.action,
                identity_result,
                fact_result,
                None,
            )

        time_input = dict(packet["time_lineage"])
        time_input["fact_object_id"] = fact_result.envelope.object_id
        time_result = self.time_store.evaluate(time_input)
        outcome = IntakeOutcome.ACCEPTED if time_result.accepted else IntakeOutcome.BLOCKED
        reason_code = None if time_result.accepted else (time_result.error_code or (time_result.decision.reason_code if time_result.decision else "TIME_GATE_BLOCKED"))
        return self._record_delivery(
            delivery_id,
            idempotency_key,
            request_hash,
            identity_result.observation_id,
            fact_result.observation_id,
            time_result.decision.decision_id if time_result.decision else None,
            outcome,
            reason_code,
            identity_result,
            fact_result,
            time_result,
        )

    @staticmethod
    def _validate_packet(packet: Mapping[str, Any]) -> str:
        if not isinstance(packet, Mapping):
            raise OrchestratorValidationError("PACKET_NOT_OBJECT", "intake packet must be an object")
        forbidden = _find_forbidden_key(packet)
        if forbidden:
            raise OrchestratorValidationError("BOUNDARY_FIELD_FORBIDDEN", f"orchestrator packet cannot contain {forbidden}")
        unknown = set(packet) - PACKET_KEYS
        if unknown:
            raise OrchestratorValidationError("UNEXPECTED_PACKET_FIELD", f"unexpected packet fields: {sorted(unknown)}")
        key = _text(packet.get("idempotency_key"), "idempotency_key")
        if not IDEMPOTENCY_KEY_RE.fullmatch(key):
            raise OrchestratorValidationError("IDEMPOTENCY_KEY_INVALID", "idempotency_key has an invalid stable format")
        for field_name in ("identity_observation", "fact_observation", "time_lineage"):
            if not isinstance(packet.get(field_name), Mapping):
                raise OrchestratorValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be an object")
        return key

    def _record_delivery(
        self,
        delivery_id: str,
        idempotency_key: str,
        request_hash: str,
        identity_observation_id: Optional[str],
        fact_observation_id: Optional[str],
        time_decision_id: Optional[str],
        outcome: IntakeOutcome,
        reason_code: Optional[str],
        identity: Optional[IdentityIntakeResult],
        fact: Optional[FactIntakeResult],
        time: Optional[TimeGateResult],
    ) -> IntakeResult:
        record = IntakeDeliveryRecord(
            delivery_id=delivery_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            identity_observation_id=identity_observation_id,
            fact_observation_id=fact_observation_id,
            time_decision_id=time_decision_id,
            outcome=outcome,
            reason_code=reason_code,
        )
        self._deliveries_by_key[idempotency_key] = record
        self._deliveries[delivery_id] = record
        self._append_event("DELIVERY_ACCEPTED" if outcome == IntakeOutcome.ACCEPTED else "DELIVERY_BLOCKED", delivery_id, idempotency_key, outcome, reason_code)
        return IntakeResult(outcome == IntakeOutcome.ACCEPTED, outcome, idempotency_key, delivery_id, identity, fact, time, reason_code)

    def _append_event(
        self,
        action: str,
        delivery_id: Optional[str],
        idempotency_key: Optional[str],
        outcome: IntakeOutcome,
        reason_code: Optional[str],
    ) -> None:
        self._events.append(
            _OrchestratorEvent(
                sequence=len(self._events) + 1,
                action=action,
                delivery_id=delivery_id,
                idempotency_key=idempotency_key,
                outcome=outcome,
                reason_code=reason_code,
            )
        )
