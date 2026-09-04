"""V4-032 team-context identity linking.

This module is a local, in-memory, append-only boundary.  It resolves a
source team label to the already accepted V4-020 canonical match/team/side
identity.  It deliberately does not create a context feature, evidence
graph, model output, or persistence write.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .match_identity import (
    CanonicalMatchIdentityStore,
    IdentityValidationError,
    _iso,
    _parse_timestamp,
    _source_observation_id,
)


CONTRACT_VERSION = "team-context@1.0.0"
TEAM_CONTEXT_ID_NAMESPACE = uuid.UUID("d3b37b9a-0d19-5b91-8f6a-d5d2c4ed5d5a")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

MODEL_FIELD_TOKENS = (
    "prediction",
    "recommendation",
    "feature",
    "model",
    "engine",
    "score",
    "risk",
    "probability",
)


class TeamContextValidationError(ValueError):
    """A source identity observation cannot be admitted safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TeamSide(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"


def _text(value: Any, field_name: str, *, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise TeamContextValidationError("REQUIRED_FIELD_MISSING", f"{field_name} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise TeamContextValidationError("REQUIRED_FIELD_MISSING", f"{field_name} must be non-empty")
        return None
    return unicodedata.normalize("NFKC", value).strip()


def _uuid(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    assert result is not None
    if not UUID_RE.fullmatch(result):
        raise TeamContextValidationError("IDENTITY_REFERENCE_INVALID", f"{field_name} must be a valid UUID")
    return result


def _timestamp(value: Any, field_name: str) -> datetime:
    try:
        parsed = _parse_timestamp(value, field_name)
    except IdentityValidationError as exc:
        raise TeamContextValidationError(exc.code, exc.message) from exc
    assert parsed is not None
    return parsed


def _hash(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    assert result is not None
    if not HASH_RE.fullmatch(result):
        raise TeamContextValidationError("HASH_INVALID", f"{field_name} must be sha256:<64 hex>")
    return result


def _token(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    assert result is not None
    normalized = result.upper()
    if not TOKEN_RE.fullmatch(normalized):
        raise TeamContextValidationError("ENUM_INVALID", f"{field_name} must be an uppercase governed token")
    return normalized


def _alias_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


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


def _find_forbidden(value: Any, path: str = "observation") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if "v333" in normalized or "v3_3_3" in normalized:
                return f"{path}.{key}"
            if any(token in normalized for token in MODEL_FIELD_TOKENS):
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


@dataclass(frozen=True)
class TeamIdentityConflict:
    code: str
    field: str
    reason: str
    existing_source_reference: Optional[str]
    incoming_source_reference: str
    existing_value: Any
    incoming_value: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "reason": self.reason,
            "existing_source_reference": self.existing_source_reference,
            "incoming_source_reference": self.incoming_source_reference,
            "existing_value": _thaw(self.existing_value),
            "incoming_value": _thaw(self.incoming_value),
        }


@dataclass(frozen=True)
class TeamIdentityLinkObservation:
    """A source-side team label awaiting canonical identity admission."""

    match_id: str
    side: TeamSide
    team_alias: str
    team_id: Optional[str]
    team_display_name: Optional[str]
    source: str
    source_type: str
    source_reference: str
    source_timestamp: datetime
    observed_at: datetime
    ingested_at: datetime
    effective_at: datetime
    cutoff_at: datetime
    provenance_ref: str
    provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TeamIdentityLinkObservation":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("OBSERVATION_NOT_OBJECT", "team identity observation must be an object")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"team identity cannot contain {forbidden}")

        match_id = _uuid(raw.get("match_id"), "match_id")
        side_raw = _text(raw.get("side"), "side")
        assert side_raw is not None
        try:
            side = TeamSide(side_raw.upper())
        except ValueError as exc:
            raise TeamContextValidationError("SIDE_INVALID", "side must be HOME or AWAY") from exc
        team_alias = _text(raw.get("team_alias", raw.get("source_team_name")), "team_alias")
        assert team_alias is not None
        team_id = _text(raw.get("team_id"), "team_id", required=False)
        team_display_name = _text(raw.get("team_display_name"), "team_display_name", required=False)
        source = _text(raw.get("source"), "source")
        source_type = _token(raw.get("source_type", "TEAM_CONTEXT_SOURCE"), "source_type")
        source_reference = _text(raw.get("source_reference", raw.get("source_ref")), "source_reference")
        source_timestamp = _timestamp(raw.get("source_timestamp"), "source_timestamp")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        effective_at = _timestamp(raw.get("effective_at", raw.get("as_of_at")), "effective_at")
        cutoff_at = _timestamp(raw.get("cutoff_at"), "cutoff_at")
        if source_timestamp > observed_at:
            raise TeamContextValidationError("SOURCE_TIME_AFTER_OBSERVED", "source_timestamp cannot follow observed_at")
        if observed_at > ingested_at:
            raise TeamContextValidationError("OBSERVED_AFTER_INGESTED", "observed_at cannot follow ingested_at")
        if effective_at > cutoff_at:
            raise TeamContextValidationError("EFFECTIVE_AFTER_CUTOFF", "effective_at cannot follow cutoff_at")
        if observed_at > cutoff_at:
            raise TeamContextValidationError("OBSERVED_AFTER_CUTOFF", "observed_at cannot follow cutoff_at")
        provenance_ref = _text(raw.get("provenance_ref", source_reference), "provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = _hash(supplied_hash, "provenance_hash") if supplied_hash is not None else None
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TeamContextValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        assert source is not None and source_reference is not None and provenance_ref is not None
        return cls(
            match_id=match_id,
            side=side,
            team_alias=team_alias,
            team_id=team_id,
            team_display_name=team_display_name,
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            ingested_at=ingested_at,
            effective_at=effective_at,
            cutoff_at=cutoff_at,
            provenance_ref=provenance_ref,
            provenance_hash=provenance_hash,
            metadata=_freeze(metadata),
        )

    @property
    def observation_id(self) -> str:
        return _source_observation_id(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "side": self.side.value,
            "team_alias": self.team_alias,
            "team_id": self.team_id,
            "team_display_name": self.team_display_name,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": _iso(self.source_timestamp),
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "effective_at": _iso(self.effective_at),
            "cutoff_at": _iso(self.cutoff_at),
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class TeamIdentityLink:
    object_id: str
    contract_version: str
    match_id: str
    team_id: str
    team_display_name: str
    side: TeamSide
    source_team_alias: str
    source: str
    source_type: str
    source_reference: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    effective_at: str
    cutoff_at: str
    provenance_ref: str
    provenance_hash: str
    mapping_hash: str
    observation_id: str
    revision: int
    supersedes_object_id: Optional[str]
    status: str = "AVAILABLE"
    conflicts: Tuple[TeamIdentityConflict, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "team_id": self.team_id,
            "team_display_name": self.team_display_name,
            "side": self.side.value,
            "source_team_alias": self.source_team_alias,
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "effective_at": self.effective_at,
            "cutoff_at": self.cutoff_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "mapping_hash": self.mapping_hash,
            "observation_id": self.observation_id,
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
            "status": self.status,
            "conflicts": [item.to_dict() for item in self.conflicts],
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class TeamIdentityLinkResult:
    accepted: bool
    status: str
    action: str
    observation_id: str
    link: Optional[TeamIdentityLink]
    conflicts: Tuple[TeamIdentityConflict, ...] = ()
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "action": self.action,
            "observation_id": self.observation_id,
            "link": self.link.to_dict() if self.link else None,
            "conflicts": [item.to_dict() for item in self.conflicts],
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class _TeamAppendEvent:
    sequence: int
    action: str
    observation_id: str
    object_id: Optional[str]
    match_id: Optional[str]
    team_id: Optional[str]
    side: Optional[TeamSide]
    error_code: Optional[str] = None


class TeamContextIdentityLinker:
    """V4-032 local append-only source-to-identity linker."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-032 requires a V4-020 CanonicalMatchIdentityStore")
        self._identity_store = identity_store
        self._observations: Dict[str, TeamIdentityLinkObservation] = {}
        self._links: Dict[str, TeamIdentityLink] = {}
        self._latest_by_team: Dict[Tuple[str, str, TeamSide], TeamIdentityLink] = {}
        self._by_source_ref: Dict[Tuple[str, str], TeamIdentityLink] = {}
        self._events: List[_TeamAppendEvent] = []

    @property
    def observations(self) -> Tuple[TeamIdentityLinkObservation, ...]:
        return tuple(self._observations.values())

    @property
    def links(self) -> Tuple[TeamIdentityLink, ...]:
        return tuple(self._links.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(
                {
                    "sequence": event.sequence,
                    "action": event.action,
                    "observation_id": event.observation_id,
                    "object_id": event.object_id,
                    "match_id": event.match_id,
                    "team_id": event.team_id,
                    "side": event.side.value if event.side else None,
                    "error_code": event.error_code,
                }
            )
            for event in self._events
        )

    def get(self, object_id: str) -> Optional[TeamIdentityLink]:
        return self._links.get(object_id)

    def get_identity(self, match_id: str) -> Optional[Any]:
        """Expose the already-resolved V4-020 identity for downstream validation."""

        return self._identity_store.get(match_id)

    def latest(self, match_id: str, team_id: str, side: Union[TeamSide, str]) -> Optional[TeamIdentityLink]:
        try:
            normalized_side = side if isinstance(side, TeamSide) else TeamSide(str(side).upper())
        except ValueError:
            return None
        return self._latest_by_team.get((match_id, team_id, normalized_side))

    def ingest(self, raw: Union[TeamIdentityLinkObservation, Mapping[str, Any]]) -> TeamIdentityLinkResult:
        try:
            observation = raw if isinstance(raw, TeamIdentityLinkObservation) else TeamIdentityLinkObservation.from_dict(raw)
        except (TeamContextValidationError, IdentityValidationError) as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._append_event("BLOCKED_VALIDATION", observation_id, None, None, None, None, code)
            return TeamIdentityLinkResult(False, "BLOCKED", code, observation_id, None, error_code=code)

        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((link for link in self._links.values() if link.observation_id == observation_id), None)
            self._append_event(
                "DUPLICATE_NOOP",
                observation_id,
                existing.object_id if existing else None,
                observation.match_id,
                existing.team_id if existing else observation.team_id,
                observation.side,
            )
            return TeamIdentityLinkResult(True, "AVAILABLE", "DUPLICATE_NOOP", observation_id, existing)

        identity = self._identity_store.get(observation.match_id)
        if identity is None:
            return self._blocked(observation, "MATCH_IDENTITY_NOT_FOUND")
        if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, "MATCH_IDENTITY_NOT_RESOLVED")

        expected_team_id, expected_display_name = self._expected_team(identity, observation.side)
        if observation.team_id is not None and observation.team_id != expected_team_id:
            conflict = self._conflict(
                "TEAM_ID_SIDE_CONFLICT",
                "team_id",
                "provided team_id does not match the canonical team for side",
                None,
                observation.source_reference,
                expected_team_id,
                observation.team_id,
            )
            return self._blocked(observation, "TEAM_ID_SIDE_CONFLICT", (conflict,))

        alias_key = _alias_key(observation.team_alias)
        canonical_key = _alias_key(expected_display_name)
        if observation.team_id is None and alias_key != canonical_key:
            wrong_side = self._other_team_name(identity, observation.side)
            code = "ALIAS_SIDE_CONFLICT" if alias_key == _alias_key(wrong_side) else "ALIAS_UNRESOLVED"
            conflict = self._conflict(
                code,
                "team_alias",
                "source alias cannot be resolved to the canonical team without guessing",
                None,
                observation.source_reference,
                expected_display_name,
                observation.team_alias,
            )
            return self._blocked(observation, code, (conflict,))

        source_key = (observation.match_id, observation.source_reference)
        prior_source = self._by_source_ref.get(source_key)
        if prior_source and (prior_source.team_id != expected_team_id or prior_source.side != observation.side):
            conflict = self._conflict(
                "SOURCE_REFERENCE_IDENTITY_CONFLICT",
                "source_reference",
                "one source reference cannot map to multiple canonical teams or sides",
                prior_source.source_reference,
                observation.source_reference,
                {"team_id": prior_source.team_id, "side": prior_source.side.value},
                {"team_id": expected_team_id, "side": observation.side.value},
            )
            return self._blocked(observation, "SOURCE_REFERENCE_IDENTITY_CONFLICT", (conflict,))

        self._observations[observation_id] = observation
        key = (observation.match_id, expected_team_id, observation.side)
        predecessor = self._latest_by_team.get(key)
        revision = predecessor.revision + 1 if predecessor else 1
        provenance_hash = observation.provenance_hash or sha256_json(
            {
                "source": observation.source,
                "source_type": observation.source_type,
                "source_reference": observation.source_reference,
                "provenance_ref": observation.provenance_ref,
                "source_timestamp": _iso(observation.source_timestamp),
                "observed_at": _iso(observation.observed_at),
                "effective_at": _iso(observation.effective_at),
            }
        )
        mapping_hash = sha256_json(
            {
                "match_id": observation.match_id,
                "team_id": expected_team_id,
                "team_display_name": expected_display_name,
                "side": observation.side.value,
                "source_team_alias": observation.team_alias,
                "source": observation.source,
                "source_type": observation.source_type,
                "source_reference": observation.source_reference,
                "source_timestamp": _iso(observation.source_timestamp),
                "effective_at": _iso(observation.effective_at),
                "cutoff_at": _iso(observation.cutoff_at),
                "provenance_ref": observation.provenance_ref,
                "provenance_hash": provenance_hash,
            }
        )
        object_id = str(
            uuid.uuid5(
                TEAM_CONTEXT_ID_NAMESPACE,
                f"team-link|{observation.match_id}|{expected_team_id}|{observation.side.value}|{observation_id}",
            )
        )
        link = TeamIdentityLink(
            object_id=object_id,
            contract_version=CONTRACT_VERSION,
            match_id=observation.match_id,
            team_id=expected_team_id,
            team_display_name=expected_display_name,
            side=observation.side,
            source_team_alias=observation.team_alias,
            source=observation.source,
            source_type=observation.source_type,
            source_reference=observation.source_reference,
            source_timestamp=_iso(observation.source_timestamp),
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            effective_at=_iso(observation.effective_at),
            cutoff_at=_iso(observation.cutoff_at),
            provenance_ref=observation.provenance_ref,
            provenance_hash=provenance_hash,
            mapping_hash=mapping_hash,
            observation_id=observation_id,
            revision=revision,
            supersedes_object_id=predecessor.object_id if predecessor else None,
            metadata=MappingProxyType(
                {
                    "display_name_join_key": False,
                    "append_only_boundary": "V4-032 local team identity mapping ledger; persistence adapter deferred",
                    "v4_023_orchestrator": "consumed identity authority only; no new orchestration",
                }
            ),
        )
        self._links[object_id] = link
        self._latest_by_team[key] = link
        self._by_source_ref[source_key] = link
        self._append_event(
            "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED",
            observation_id,
            object_id,
            observation.match_id,
            expected_team_id,
            observation.side,
        )
        return TeamIdentityLinkResult(
            True,
            "AVAILABLE",
            "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED",
            observation_id,
            link,
        )

    @staticmethod
    def _expected_team(identity: Any, side: TeamSide) -> Tuple[str, str]:
        if side == TeamSide.HOME:
            return identity.home_team_id, identity.home_team_name
        return identity.away_team_id, identity.away_team_name

    @staticmethod
    def _other_team_name(identity: Any, side: TeamSide) -> str:
        return identity.away_team_name if side == TeamSide.HOME else identity.home_team_name

    @staticmethod
    def _conflict(
        code: str,
        field: str,
        reason: str,
        existing_ref: Optional[str],
        incoming_ref: str,
        existing_value: Any,
        incoming_value: Any,
    ) -> TeamIdentityConflict:
        return TeamIdentityConflict(
            code=code,
            field=field,
            reason=reason,
            existing_source_reference=existing_ref,
            incoming_source_reference=incoming_ref,
            existing_value=_freeze(existing_value),
            incoming_value=_freeze(incoming_value),
        )

    def _blocked(
        self,
        observation: TeamIdentityLinkObservation,
        code: str,
        conflicts: Tuple[TeamIdentityConflict, ...] = (),
    ) -> TeamIdentityLinkResult:
        observation_id = observation.observation_id
        self._observations.setdefault(observation_id, observation)
        self._append_event(
            "BLOCKED_IDENTITY",
            observation_id,
            None,
            observation.match_id,
            observation.team_id,
            observation.side,
            code,
        )
        return TeamIdentityLinkResult(False, "BLOCKED", code, observation_id, None, conflicts, code)

    def _append_event(
        self,
        action: str,
        observation_id: str,
        object_id: Optional[str],
        match_id: Optional[str],
        team_id: Optional[str],
        side: Optional[TeamSide],
        error_code: Optional[str] = None,
    ) -> None:
        self._events.append(
            _TeamAppendEvent(
                sequence=len(self._events) + 1,
                action=action,
                observation_id=observation_id,
                object_id=object_id,
                match_id=match_id,
                team_id=team_id,
                side=side,
                error_code=error_code,
            )
        )


CONTEXT_STATES = frozenset(
    {
        "AVAILABLE",
        "UNKNOWN",
        "NONE_CONFIRMED",
        "NOT_VERIFIED",
        "CONFLICTED",
        "STALE",
        "FUTURE_DATA",
        "BLOCKED",
    }
)


@dataclass(frozen=True)
class TypedFactCollection:
    """Explicit collection semantics for injuries, suspensions, or availability."""

    state: str
    items: Optional[Tuple[Mapping[str, Any], ...]]
    basis_refs: Tuple[str, ...]
    reason: Optional[str]

    @classmethod
    def from_dict(cls, raw: Any, field_name: str) -> "TypedFactCollection":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("FACT_COLLECTION_INVALID", f"{field_name} must be a typed object")
        state = _text(raw.get("state"), f"{field_name}.state")
        assert state is not None
        state = state.upper()
        if state not in CONTEXT_STATES:
            raise TeamContextValidationError("CONTEXT_STATE_INVALID", f"{field_name}.state is not governed")
        raw_items = raw.get("items")
        if raw_items is not None and not isinstance(raw_items, (list, tuple)):
            raise TeamContextValidationError("FACT_COLLECTION_ITEMS_INVALID", f"{field_name}.items must be an array")
        if state == "UNKNOWN" and raw_items is not None:
            raise TeamContextValidationError("UNKNOWN_ITEMS_FORBIDDEN", f"{field_name}.UNKNOWN must omit items")
        if state == "NONE_CONFIRMED":
            if raw_items != []:
                raise TeamContextValidationError("NONE_CONFIRMED_ITEMS_REQUIRED", f"{field_name}.NONE_CONFIRMED requires items=[]")
        if state == "AVAILABLE" and not raw_items:
            raise TeamContextValidationError("AVAILABLE_ITEMS_REQUIRED", f"{field_name}.AVAILABLE requires non-empty items")
        basis_raw = raw.get("basis_refs", [])
        if not isinstance(basis_raw, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in basis_raw):
            raise TeamContextValidationError("BASIS_REFS_INVALID", f"{field_name}.basis_refs must be non-empty strings")
        basis_refs = tuple(item.strip() for item in basis_raw)
        if state == "NONE_CONFIRMED" and not basis_refs:
            raise TeamContextValidationError("NONE_CONFIRMED_EVIDENCE_REQUIRED", f"{field_name}.NONE_CONFIRMED requires basis_refs")
        if state == "CONFLICTED" and len(basis_refs) < 2:
            raise TeamContextValidationError("CONFLICT_EVIDENCE_REQUIRED", f"{field_name}.CONFLICTED requires both claim refs")
        reason = _text(raw.get("reason"), f"{field_name}.reason", required=False)
        if state != "AVAILABLE" and reason is None:
            raise TeamContextValidationError("REASON_REQUIRED", f"{field_name}.{state} requires reason")
        items: Optional[Tuple[Mapping[str, Any], ...]] = None
        if raw_items is not None:
            frozen_items = []
            for index, item in enumerate(raw_items):
                if not isinstance(item, Mapping):
                    raise TeamContextValidationError("FACT_ITEM_INVALID", f"{field_name}.items[{index}] must be an object")
                forbidden = _find_forbidden(item, f"{field_name}.items[{index}]")
                if forbidden:
                    raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"context fact cannot contain {forbidden}")
                frozen_items.append(_freeze(item))
            items = tuple(frozen_items)
        return cls(state, items, basis_refs, reason)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "state": self.state,
            "basis_refs": list(self.basis_refs),
        }
        if self.items is not None:
            result["items"] = [_thaw(item) for item in self.items]
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class AvailabilityContextObservation:
    match_id: str
    team_id: str
    side: TeamSide
    injuries: TypedFactCollection
    suspensions: TypedFactCollection
    availability: TypedFactCollection
    source: str
    source_type: str
    source_reference: str
    source_timestamp: datetime
    observed_at: datetime
    ingested_at: datetime
    effective_at: datetime
    cutoff_at: datetime
    expires_at: Optional[datetime]
    provenance_ref: str
    provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AvailabilityContextObservation":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("OBSERVATION_NOT_OBJECT", "availability observation must be an object")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"availability context cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        team_id = _text(raw.get("team_id"), "team_id")
        assert team_id is not None
        side_raw = _text(raw.get("side"), "side")
        assert side_raw is not None
        try:
            side = TeamSide(side_raw.upper())
        except ValueError as exc:
            raise TeamContextValidationError("SIDE_INVALID", "side must be HOME or AWAY") from exc
        collections = {
            name: TypedFactCollection.from_dict(raw.get(name), name)
            for name in ("injuries", "suspensions", "availability")
        }
        source = _text(raw.get("source"), "source")
        source_type = _token(raw.get("source_type", "TEAM_CONTEXT_SOURCE"), "source_type")
        source_reference = _text(raw.get("source_reference", raw.get("source_ref")), "source_reference")
        source_timestamp = _timestamp(raw.get("source_timestamp"), "source_timestamp")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        effective_at = _timestamp(raw.get("effective_at", raw.get("as_of_at")), "effective_at")
        cutoff_at = _timestamp(raw.get("cutoff_at"), "cutoff_at")
        expires_at = _timestamp(raw.get("expires_at"), "expires_at") if raw.get("expires_at") is not None else None
        if source_timestamp > observed_at:
            raise TeamContextValidationError("SOURCE_TIME_AFTER_OBSERVED", "source_timestamp cannot follow observed_at")
        if observed_at > ingested_at:
            raise TeamContextValidationError("OBSERVED_AFTER_INGESTED", "observed_at cannot follow ingested_at")
        if effective_at > cutoff_at or observed_at > cutoff_at or source_timestamp > cutoff_at:
            raise TeamContextValidationError("POST_CUTOFF_CONTEXT", "availability context is not eligible at cutoff")
        if expires_at is not None and expires_at < effective_at:
            raise TeamContextValidationError("EXPIRY_BEFORE_EFFECTIVE", "expires_at cannot precede effective_at")
        if any(collection.state == "STALE" for collection in collections.values()) and expires_at is None:
            raise TeamContextValidationError("STALE_EXPIRY_REQUIRED", "STALE collections require expires_at")
        provenance_ref = _text(raw.get("provenance_ref", source_reference), "provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = _hash(supplied_hash, "provenance_hash") if supplied_hash is not None else None
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TeamContextValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        assert source is not None and source_reference is not None and provenance_ref is not None
        return cls(
            match_id=match_id,
            team_id=team_id,
            side=side,
            injuries=collections["injuries"],
            suspensions=collections["suspensions"],
            availability=collections["availability"],
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            ingested_at=ingested_at,
            effective_at=effective_at,
            cutoff_at=cutoff_at,
            expires_at=expires_at,
            provenance_ref=provenance_ref,
            provenance_hash=provenance_hash,
            metadata=_freeze(metadata),
        )

    @property
    def observation_id(self) -> str:
        return _source_observation_id(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "injuries": self.injuries.to_dict(),
            "suspensions": self.suspensions.to_dict(),
            "availability": self.availability.to_dict(),
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": _iso(self.source_timestamp),
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "effective_at": _iso(self.effective_at),
            "cutoff_at": _iso(self.cutoff_at),
            "expires_at": _iso(self.expires_at) if self.expires_at else None,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class AvailabilityContextRecord:
    object_id: str
    contract_version: str
    match_id: str
    team_id: str
    side: TeamSide
    injuries: TypedFactCollection
    suspensions: TypedFactCollection
    availability: TypedFactCollection
    source: str
    source_type: str
    source_reference: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    effective_at: str
    cutoff_at: str
    expires_at: Optional[str]
    provenance_ref: str
    provenance_hash: str
    payload_hash: str
    context_hash: str
    observation_id: str
    revision: int
    supersedes_object_id: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "injuries": self.injuries.to_dict(),
            "suspensions": self.suspensions.to_dict(),
            "availability": self.availability.to_dict(),
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "effective_at": self.effective_at,
            "cutoff_at": self.cutoff_at,
            "expires_at": self.expires_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
            "context_hash": self.context_hash,
            "observation_id": self.observation_id,
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class AvailabilityContextResult:
    accepted: bool
    status: str
    action: str
    observation_id: str
    record: Optional[AvailabilityContextRecord]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "action": self.action,
            "observation_id": self.observation_id,
            "record": self.record.to_dict() if self.record else None,
            "error_code": self.error_code,
        }


class AvailabilityContextStore:
    """V4-033 append-only availability/injury/suspension intake."""

    def __init__(self, linker: TeamContextIdentityLinker):
        if not isinstance(linker, TeamContextIdentityLinker):
            raise TypeError("V4-033 requires a V4-032 TeamContextIdentityLinker")
        self._linker = linker
        self._observations: Dict[str, AvailabilityContextObservation] = {}
        self._records: Dict[str, AvailabilityContextRecord] = {}
        self._latest: Dict[Tuple[str, str, TeamSide], AvailabilityContextRecord] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def observations(self) -> Tuple[AvailabilityContextObservation, ...]:
        return tuple(self._observations.values())

    @property
    def records(self) -> Tuple[AvailabilityContextRecord, ...]:
        return tuple(self._records.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def latest(self, match_id: str, team_id: str, side: Union[TeamSide, str]) -> Optional[AvailabilityContextRecord]:
        normalized = side if isinstance(side, TeamSide) else TeamSide(str(side).upper())
        return self._latest.get((match_id, team_id, normalized))

    def ingest(self, raw: Union[AvailabilityContextObservation, Mapping[str, Any]]) -> AvailabilityContextResult:
        try:
            observation = raw if isinstance(raw, AvailabilityContextObservation) else AvailabilityContextObservation.from_dict(raw)
        except (TeamContextValidationError, IdentityValidationError) as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._events.append({"action": "BLOCKED_VALIDATION", "observation_id": observation_id, "error_code": code})
            return AvailabilityContextResult(False, "BLOCKED", code, observation_id, None, code)
        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((record for record in self._records.values() if record.observation_id == observation_id), None)
            self._events.append({"action": "DUPLICATE_NOOP", "observation_id": observation_id, "object_id": existing.object_id if existing else None})
            return AvailabilityContextResult(True, "AVAILABLE", "DUPLICATE_NOOP", observation_id, existing)

        identity = self._linker.get_identity(observation.match_id)
        if identity is None or identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, "MATCH_IDENTITY_NOT_RESOLVED")
        expected_team = identity.home_team_id if observation.side == TeamSide.HOME else identity.away_team_id
        if observation.team_id != expected_team:
            return self._blocked(observation, "TEAM_ID_SIDE_CONFLICT")
        link = self._linker.latest(observation.match_id, observation.team_id, observation.side)
        if link is None:
            return self._blocked(observation, "TEAM_CONTEXT_LINK_NOT_FOUND")
        kickoff = datetime.fromisoformat(identity.kickoff_at)
        if not observation.cutoff_at < kickoff:
            return self._blocked(observation, "CUTOFF_NOT_BEFORE_KICKOFF")
        if any(
            collection.state == "FUTURE_DATA"
            for collection in (observation.injuries, observation.suspensions, observation.availability)
        ):
            return self._blocked(observation, "FUTURE_DATA_NOT_ELIGIBLE")

        self._observations[observation_id] = observation
        key = (observation.match_id, observation.team_id, observation.side)
        predecessor = self._latest.get(key)
        revision = predecessor.revision + 1 if predecessor else 1
        provenance_hash = observation.provenance_hash or sha256_json(
            {
                "source": observation.source,
                "source_type": observation.source_type,
                "source_reference": observation.source_reference,
                "provenance_ref": observation.provenance_ref,
                "source_timestamp": _iso(observation.source_timestamp),
                "observed_at": _iso(observation.observed_at),
                "effective_at": _iso(observation.effective_at),
            }
        )
        logical = {
            "match_id": observation.match_id,
            "team_id": observation.team_id,
            "side": observation.side.value,
            "injuries": observation.injuries.to_dict(),
            "suspensions": observation.suspensions.to_dict(),
            "availability": observation.availability.to_dict(),
            "source_reference": observation.source_reference,
            "source_timestamp": _iso(observation.source_timestamp),
            "effective_at": _iso(observation.effective_at),
            "cutoff_at": _iso(observation.cutoff_at),
            "expires_at": _iso(observation.expires_at) if observation.expires_at else None,
            "provenance_ref": observation.provenance_ref,
            "provenance_hash": provenance_hash,
        }
        payload_hash = sha256_json(logical)
        context_hash = sha256_json({"identity_link_object_id": link.object_id, **logical})
        object_id = str(uuid.uuid5(TEAM_CONTEXT_ID_NAMESPACE, f"availability|{observation.match_id}|{observation.team_id}|{observation.side.value}|{observation_id}"))
        record = AvailabilityContextRecord(
            object_id=object_id,
            contract_version=CONTRACT_VERSION,
            match_id=observation.match_id,
            team_id=observation.team_id,
            side=observation.side,
            injuries=observation.injuries,
            suspensions=observation.suspensions,
            availability=observation.availability,
            source=observation.source,
            source_type=observation.source_type,
            source_reference=observation.source_reference,
            source_timestamp=_iso(observation.source_timestamp),
            observed_at=_iso(observation.observed_at),
            ingested_at=_iso(observation.ingested_at),
            effective_at=_iso(observation.effective_at),
            cutoff_at=_iso(observation.cutoff_at),
            expires_at=_iso(observation.expires_at) if observation.expires_at else None,
            provenance_ref=observation.provenance_ref,
            provenance_hash=provenance_hash,
            payload_hash=payload_hash,
            context_hash=context_hash,
            observation_id=observation_id,
            revision=revision,
            supersedes_object_id=predecessor.object_id if predecessor else None,
            metadata=MappingProxyType({"identity_link_object_id": link.object_id, "append_only_boundary": "V4-033 local context ledger; V4-036/V4-037 deferred"}),
        )
        self._records[object_id] = record
        self._latest[key] = record
        self._events.append({"action": "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", "observation_id": observation_id, "object_id": object_id, "supersedes_object_id": predecessor.object_id if predecessor else None})
        return AvailabilityContextResult(True, "AVAILABLE", "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", observation_id, record)

    def _blocked(self, observation: AvailabilityContextObservation, code: str) -> AvailabilityContextResult:
        observation_id = observation.observation_id
        self._observations.setdefault(observation_id, observation)
        self._events.append({"action": "BLOCKED_CONTEXT", "observation_id": observation_id, "match_id": observation.match_id, "team_id": observation.team_id, "side": observation.side.value, "error_code": code})
        return AvailabilityContextResult(False, "BLOCKED", code, observation_id, None, code)


LINEUP_STATES = frozenset({"CONFIRMED", "PROJECTED", "UNKNOWN", "NOT_VERIFIED", "BLOCKED"})


@dataclass(frozen=True)
class ContextValue:
    """A source-attributed context value, never a model interpretation."""

    state: str
    value: Any
    basis_refs: Tuple[str, ...]
    reason: Optional[str]

    @classmethod
    def from_dict(cls, raw: Any, field_name: str, *, allowed_states: frozenset[str] = CONTEXT_STATES) -> "ContextValue":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("CONTEXT_VALUE_INVALID", f"{field_name} must be a typed object")
        state = _text(raw.get("state"), f"{field_name}.state")
        assert state is not None
        state = state.upper()
        if state not in allowed_states:
            raise TeamContextValidationError("CONTEXT_STATE_INVALID", f"{field_name}.state is not governed")
        value = raw.get("value")
        if state in {"AVAILABLE", "CONFIRMED", "PROJECTED"} and value is None:
            raise TeamContextValidationError("CONTEXT_VALUE_REQUIRED", f"{field_name}.{state} requires value")
        basis_raw = raw.get("basis_refs", [])
        if not isinstance(basis_raw, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in basis_raw):
            raise TeamContextValidationError("BASIS_REFS_INVALID", f"{field_name}.basis_refs must be strings")
        basis_refs = tuple(item.strip() for item in basis_raw)
        if state in {"AVAILABLE", "CONFIRMED", "PROJECTED"} and not basis_refs:
            raise TeamContextValidationError("CONTEXT_EVIDENCE_REQUIRED", f"{field_name}.{state} requires basis_refs")
        reason = _text(raw.get("reason"), f"{field_name}.reason", required=False)
        if state not in {"AVAILABLE", "CONFIRMED", "PROJECTED"} and reason is None:
            raise TeamContextValidationError("REASON_REQUIRED", f"{field_name}.{state} requires reason")
        if value is not None:
            forbidden = _find_forbidden(value, f"{field_name}.value")
            if forbidden:
                raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"context value cannot contain {forbidden}")
        return cls(state, _freeze(value), basis_refs, reason)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"state": self.state, "basis_refs": list(self.basis_refs)}
        if self.value is not None:
            result["value"] = _thaw(self.value)
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class StartingXIContext:
    state: str
    players: Optional[Tuple[str, ...]]
    basis_refs: Tuple[str, ...]
    reason: Optional[str]

    @classmethod
    def from_dict(cls, raw: Any) -> "StartingXIContext":
        field_name = "starting_xi"
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("STARTING_XI_INVALID", "starting_xi must be a typed object")
        state = _text(raw.get("state"), f"{field_name}.state")
        assert state is not None
        state = state.upper()
        if state not in LINEUP_STATES:
            raise TeamContextValidationError("LINEUP_STATE_INVALID", "starting_xi.state is not governed")
        raw_players = raw.get("players")
        if raw_players is not None and not isinstance(raw_players, (list, tuple)):
            raise TeamContextValidationError("STARTING_XI_PLAYERS_INVALID", "starting_xi.players must be an array")
        if state in {"UNKNOWN", "NOT_VERIFIED", "BLOCKED"} and raw_players is not None:
            raise TeamContextValidationError("STARTING_XI_PLAYERS_FORBIDDEN", f"starting_xi.{state} must omit players")
        if state in {"CONFIRMED", "PROJECTED"} and not raw_players:
            raise TeamContextValidationError("STARTING_XI_PLAYERS_REQUIRED", f"starting_xi.{state} requires players")
        players: Optional[Tuple[str, ...]] = None
        if raw_players is not None:
            normalized: List[str] = []
            for index, player in enumerate(raw_players):
                if isinstance(player, Mapping):
                    player = player.get("player_id")
                player_id = _text(player, f"{field_name}.players[{index}]")
                assert player_id is not None
                normalized.append(player_id)
            if len(set(normalized)) != len(normalized):
                raise TeamContextValidationError("STARTING_XI_DUPLICATE_PLAYER", "starting_xi.players must be unique")
            players = tuple(normalized)
        basis_raw = raw.get("basis_refs", [])
        if not isinstance(basis_raw, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in basis_raw):
            raise TeamContextValidationError("BASIS_REFS_INVALID", "starting_xi.basis_refs must be strings")
        basis_refs = tuple(item.strip() for item in basis_raw)
        if state in {"CONFIRMED", "PROJECTED"} and not basis_refs:
            raise TeamContextValidationError("STARTING_XI_EVIDENCE_REQUIRED", f"starting_xi.{state} requires basis_refs")
        reason = _text(raw.get("reason"), f"{field_name}.reason", required=False)
        if state not in {"CONFIRMED", "PROJECTED"} and reason is None:
            raise TeamContextValidationError("REASON_REQUIRED", f"starting_xi.{state} requires reason")
        return cls(state, players, basis_refs, reason)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"state": self.state, "basis_refs": list(self.basis_refs)}
        if self.players is not None:
            result["players"] = list(self.players)
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class LineupCoachTacticalObservation:
    match_id: str
    team_id: str
    side: TeamSide
    lineup_status: ContextValue
    starting_xi: StartingXIContext
    coach: ContextValue
    tactical_style: ContextValue
    motivation: ContextValue
    source: str
    source_type: str
    source_reference: str
    source_timestamp: datetime
    observed_at: datetime
    ingested_at: datetime
    effective_at: datetime
    cutoff_at: datetime
    provenance_ref: str
    provenance_hash: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LineupCoachTacticalObservation":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("OBSERVATION_NOT_OBJECT", "lineup/context observation must be an object")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"lineup context cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        team_id = _text(raw.get("team_id"), "team_id")
        assert team_id is not None
        side_raw = _text(raw.get("side"), "side")
        assert side_raw is not None
        try:
            side = TeamSide(side_raw.upper())
        except ValueError as exc:
            raise TeamContextValidationError("SIDE_INVALID", "side must be HOME or AWAY") from exc
        lineup_status = ContextValue.from_dict(raw.get("lineup_status"), "lineup_status", allowed_states=LINEUP_STATES)
        if lineup_status.state in {"CONFIRMED", "PROJECTED"} and lineup_status.value != lineup_status.state:
            raise TeamContextValidationError("LINEUP_STATUS_COERCION", "lineup_status value must equal its explicit state")
        starting_xi = StartingXIContext.from_dict(raw.get("starting_xi"))
        if starting_xi.state != lineup_status.state:
            raise TeamContextValidationError("LINEUP_STATE_CONFLICT", "lineup_status and starting_xi states must agree")
        coach = ContextValue.from_dict(raw.get("coach"), "coach")
        tactical_style = ContextValue.from_dict(raw.get("tactical_style"), "tactical_style")
        motivation = ContextValue.from_dict(raw.get("motivation"), "motivation")
        source = _text(raw.get("source"), "source")
        source_type = _token(raw.get("source_type", "TEAM_CONTEXT_SOURCE"), "source_type")
        source_reference = _text(raw.get("source_reference", raw.get("source_ref")), "source_reference")
        source_timestamp = _timestamp(raw.get("source_timestamp"), "source_timestamp")
        observed_at = _timestamp(raw.get("observed_at"), "observed_at")
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        effective_at = _timestamp(raw.get("effective_at", raw.get("as_of_at")), "effective_at")
        cutoff_at = _timestamp(raw.get("cutoff_at"), "cutoff_at")
        if source_timestamp > observed_at:
            raise TeamContextValidationError("SOURCE_TIME_AFTER_OBSERVED", "source_timestamp cannot follow observed_at")
        if observed_at > ingested_at:
            raise TeamContextValidationError("OBSERVED_AFTER_INGESTED", "observed_at cannot follow ingested_at")
        if source_timestamp > cutoff_at or observed_at > cutoff_at or effective_at > cutoff_at:
            raise TeamContextValidationError("POST_CUTOFF_CONTEXT", "lineup/context is not eligible at cutoff")
        provenance_ref = _text(raw.get("provenance_ref", source_reference), "provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = _hash(supplied_hash, "provenance_hash") if supplied_hash is not None else None
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TeamContextValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        assert source is not None and source_reference is not None and provenance_ref is not None
        return cls(
            match_id=match_id,
            team_id=team_id,
            side=side,
            lineup_status=lineup_status,
            starting_xi=starting_xi,
            coach=coach,
            tactical_style=tactical_style,
            motivation=motivation,
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            ingested_at=ingested_at,
            effective_at=effective_at,
            cutoff_at=cutoff_at,
            provenance_ref=provenance_ref,
            provenance_hash=provenance_hash,
            metadata=_freeze(metadata),
        )

    @property
    def observation_id(self) -> str:
        return _source_observation_id(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "lineup_status": self.lineup_status.to_dict(),
            "starting_xi": self.starting_xi.to_dict(),
            "coach": self.coach.to_dict(),
            "tactical_style": self.tactical_style.to_dict(),
            "motivation": self.motivation.to_dict(),
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": _iso(self.source_timestamp),
            "observed_at": _iso(self.observed_at),
            "ingested_at": _iso(self.ingested_at),
            "effective_at": _iso(self.effective_at),
            "cutoff_at": _iso(self.cutoff_at),
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class LineupCoachTacticalRecord:
    object_id: str
    contract_version: str
    match_id: str
    team_id: str
    side: TeamSide
    lineup_status: ContextValue
    starting_xi: StartingXIContext
    coach: ContextValue
    tactical_style: ContextValue
    motivation: ContextValue
    source: str
    source_type: str
    source_reference: str
    source_timestamp: str
    observed_at: str
    ingested_at: str
    effective_at: str
    cutoff_at: str
    provenance_ref: str
    provenance_hash: str
    payload_hash: str
    context_hash: str
    observation_id: str
    revision: int
    supersedes_object_id: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "lineup_status": self.lineup_status.to_dict(),
            "starting_xi": self.starting_xi.to_dict(),
            "coach": self.coach.to_dict(),
            "tactical_style": self.tactical_style.to_dict(),
            "motivation": self.motivation.to_dict(),
            "source": self.source,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "source_timestamp": self.source_timestamp,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "effective_at": self.effective_at,
            "cutoff_at": self.cutoff_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
            "context_hash": self.context_hash,
            "observation_id": self.observation_id,
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class LineupCoachTacticalResult:
    accepted: bool
    status: str
    action: str
    observation_id: str
    record: Optional[LineupCoachTacticalRecord]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "status": self.status, "action": self.action, "observation_id": self.observation_id, "record": self.record.to_dict() if self.record else None, "error_code": self.error_code}


class LineupCoachTacticalStore:
    """V4-034 attributed pre-match lineup/coach/tactical context store."""

    def __init__(self, linker: TeamContextIdentityLinker):
        if not isinstance(linker, TeamContextIdentityLinker):
            raise TypeError("V4-034 requires a V4-032 TeamContextIdentityLinker")
        self._linker = linker
        self._observations: Dict[str, LineupCoachTacticalObservation] = {}
        self._records: Dict[str, LineupCoachTacticalRecord] = {}
        self._latest: Dict[Tuple[str, str, TeamSide], LineupCoachTacticalRecord] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def observations(self) -> Tuple[LineupCoachTacticalObservation, ...]:
        return tuple(self._observations.values())

    @property
    def records(self) -> Tuple[LineupCoachTacticalRecord, ...]:
        return tuple(self._records.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def ingest(self, raw: Union[LineupCoachTacticalObservation, Mapping[str, Any]]) -> LineupCoachTacticalResult:
        try:
            observation = raw if isinstance(raw, LineupCoachTacticalObservation) else LineupCoachTacticalObservation.from_dict(raw)
        except (TeamContextValidationError, IdentityValidationError) as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._events.append({"action": "BLOCKED_VALIDATION", "observation_id": observation_id, "error_code": code})
            return LineupCoachTacticalResult(False, "BLOCKED", code, observation_id, None, code)
        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((record for record in self._records.values() if record.observation_id == observation_id), None)
            self._events.append({"action": "DUPLICATE_NOOP", "observation_id": observation_id, "object_id": existing.object_id if existing else None})
            return LineupCoachTacticalResult(True, "AVAILABLE", "DUPLICATE_NOOP", observation_id, existing)
        identity = self._linker.get_identity(observation.match_id)
        if identity is None or identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, "MATCH_IDENTITY_NOT_RESOLVED")
        expected_team = identity.home_team_id if observation.side == TeamSide.HOME else identity.away_team_id
        if observation.team_id != expected_team:
            return self._blocked(observation, "TEAM_ID_SIDE_CONFLICT")
        link = self._linker.latest(observation.match_id, observation.team_id, observation.side)
        if link is None:
            return self._blocked(observation, "TEAM_CONTEXT_LINK_NOT_FOUND")
        kickoff = datetime.fromisoformat(identity.kickoff_at)
        if not observation.cutoff_at < kickoff:
            return self._blocked(observation, "CUTOFF_NOT_BEFORE_KICKOFF")
        if any(moment >= kickoff for moment in (observation.source_timestamp, observation.observed_at, observation.effective_at)):
            return self._blocked(observation, "POST_KICKOFF_CONTEXT")
        self._observations[observation_id] = observation
        key = (observation.match_id, observation.team_id, observation.side)
        predecessor = self._latest.get(key)
        revision = predecessor.revision + 1 if predecessor else 1
        provenance_hash = observation.provenance_hash or sha256_json({"source": observation.source, "source_type": observation.source_type, "source_reference": observation.source_reference, "provenance_ref": observation.provenance_ref, "source_timestamp": _iso(observation.source_timestamp), "observed_at": _iso(observation.observed_at), "effective_at": _iso(observation.effective_at)})
        logical = {"match_id": observation.match_id, "team_id": observation.team_id, "side": observation.side.value, "lineup_status": observation.lineup_status.to_dict(), "starting_xi": observation.starting_xi.to_dict(), "coach": observation.coach.to_dict(), "tactical_style": observation.tactical_style.to_dict(), "motivation": observation.motivation.to_dict(), "source_reference": observation.source_reference, "source_timestamp": _iso(observation.source_timestamp), "effective_at": _iso(observation.effective_at), "cutoff_at": _iso(observation.cutoff_at), "provenance_ref": observation.provenance_ref, "provenance_hash": provenance_hash}
        payload_hash = sha256_json(logical)
        context_hash = sha256_json({"identity_link_object_id": link.object_id, **logical})
        object_id = str(uuid.uuid5(TEAM_CONTEXT_ID_NAMESPACE, f"lineup|{observation.match_id}|{observation.team_id}|{observation.side.value}|{observation_id}"))
        record = LineupCoachTacticalRecord(object_id, CONTRACT_VERSION, observation.match_id, observation.team_id, observation.side, observation.lineup_status, observation.starting_xi, observation.coach, observation.tactical_style, observation.motivation, observation.source, observation.source_type, observation.source_reference, _iso(observation.source_timestamp), _iso(observation.observed_at), _iso(observation.ingested_at), _iso(observation.effective_at), _iso(observation.cutoff_at), observation.provenance_ref, provenance_hash, payload_hash, context_hash, observation_id, revision, predecessor.object_id if predecessor else None, MappingProxyType({"identity_link_object_id": link.object_id, "append_only_boundary": "V4-034 local context ledger; V4-036/V4-037 deferred", "attributed_fact_only": True}))
        self._records[object_id] = record
        self._latest[key] = record
        self._events.append({"action": "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", "observation_id": observation_id, "object_id": object_id, "supersedes_object_id": predecessor.object_id if predecessor else None})
        return LineupCoachTacticalResult(True, "AVAILABLE", "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", observation_id, record)

    def _blocked(self, observation: LineupCoachTacticalObservation, code: str) -> LineupCoachTacticalResult:
        observation_id = observation.observation_id
        self._observations.setdefault(observation_id, observation)
        self._events.append({"action": "BLOCKED_CONTEXT", "observation_id": observation_id, "match_id": observation.match_id, "team_id": observation.team_id, "side": observation.side.value, "error_code": code})
        return LineupCoachTacticalResult(False, "BLOCKED", code, observation_id, None, code)


OPERATIONAL_CONTEXT_FIELDS = ("schedule_pressure", "fatigue", "travel", "weather", "pitch")
OPERATIONAL_CONTEXT_STATES = frozenset(set(CONTEXT_STATES) | {"UNAVAILABLE"})


@dataclass(frozen=True)
class OperationalContextItem:
    category: str
    state: str
    payload: Optional[Mapping[str, Any]]
    reason: Optional[str]
    source: str
    source_reference: str
    source_timestamp: datetime
    retrieved_at: datetime
    effective_at: datetime
    expires_at: datetime
    provenance_ref: str
    provenance_hash: Optional[str]
    payload_hash: str

    @classmethod
    def from_dict(cls, category: str, raw: Any) -> "OperationalContextItem":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("OPERATIONAL_ITEM_INVALID", f"{category} must be a typed object")
        state = _text(raw.get("state"), f"{category}.state")
        assert state is not None
        state = state.upper()
        if state not in OPERATIONAL_CONTEXT_STATES:
            raise TeamContextValidationError("CONTEXT_STATE_INVALID", f"{category}.state is not governed")
        payload_raw = raw.get("payload")
        if payload_raw is not None and not isinstance(payload_raw, Mapping):
            raise TeamContextValidationError("OPERATIONAL_PAYLOAD_INVALID", f"{category}.payload must be an object")
        if state == "AVAILABLE" and not payload_raw:
            raise TeamContextValidationError("AVAILABLE_PAYLOAD_REQUIRED", f"{category}.AVAILABLE requires a non-empty payload")
        if state != "AVAILABLE" and payload_raw is not None:
            forbidden = _find_forbidden(payload_raw, f"{category}.payload")
            if forbidden:
                raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"operational context cannot contain {forbidden}")
        if payload_raw is not None:
            forbidden = _find_forbidden(payload_raw, f"{category}.payload")
            if forbidden:
                raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"operational context cannot contain {forbidden}")
        reason = _text(raw.get("reason"), f"{category}.reason", required=False)
        if state != "AVAILABLE" and reason is None:
            raise TeamContextValidationError("REASON_REQUIRED", f"{category}.{state} requires reason")
        basis_refs = raw.get("basis_refs", [])
        if not isinstance(basis_refs, (list, tuple)) or any(not isinstance(ref, str) or not ref.strip() for ref in basis_refs):
            raise TeamContextValidationError("BASIS_REFS_INVALID", f"{category}.basis_refs must be strings")
        if state == "AVAILABLE" and not basis_refs:
            raise TeamContextValidationError("CONTEXT_EVIDENCE_REQUIRED", f"{category}.AVAILABLE requires basis_refs")
        if state == "CONFLICTED" and len(basis_refs) < 2:
            raise TeamContextValidationError("CONFLICT_EVIDENCE_REQUIRED", f"{category}.CONFLICTED requires both claim refs")
        source = _text(raw.get("source"), f"{category}.source")
        source_reference = _text(raw.get("source_reference", raw.get("source_ref")), f"{category}.source_reference")
        source_timestamp = _timestamp(raw.get("source_timestamp"), f"{category}.source_timestamp")
        retrieved_at = _timestamp(raw.get("retrieved_at", raw.get("observed_at")), f"{category}.retrieved_at")
        effective_at = _timestamp(raw.get("effective_at", raw.get("as_of_at")), f"{category}.effective_at")
        expires_at = _timestamp(raw.get("expires_at"), f"{category}.expires_at")
        if source_timestamp > retrieved_at:
            raise TeamContextValidationError("SOURCE_TIME_AFTER_RETRIEVED", f"{category}.source_timestamp cannot follow retrieved_at")
        if expires_at < effective_at:
            raise TeamContextValidationError("EXPIRY_BEFORE_EFFECTIVE", f"{category}.expires_at cannot precede effective_at")
        provenance_ref = _text(raw.get("provenance_ref", source_reference), f"{category}.provenance_ref")
        supplied_hash = raw.get("provenance_hash")
        provenance_hash = _hash(supplied_hash, f"{category}.provenance_hash") if supplied_hash is not None else None
        payload = _freeze(payload_raw) if payload_raw is not None else None
        payload_hash = sha256_json({"category": category, "state": state, "payload": _thaw(payload), "reason": reason, "basis_refs": list(basis_refs)})
        assert source is not None and source_reference is not None and provenance_ref is not None
        return cls(category, state, payload, reason, source, source_reference, source_timestamp, retrieved_at, effective_at, expires_at, provenance_ref, provenance_hash, payload_hash)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "category": self.category,
            "state": self.state,
            "source": self.source,
            "source_reference": self.source_reference,
            "source_timestamp": _iso(self.source_timestamp),
            "retrieved_at": _iso(self.retrieved_at),
            "effective_at": _iso(self.effective_at),
            "expires_at": _iso(self.expires_at),
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
        }
        if self.payload is not None:
            result["payload"] = _thaw(self.payload)
        if self.reason is not None:
            result["reason"] = self.reason
        return result


@dataclass(frozen=True)
class OperationalContextObservation:
    match_id: str
    team_id: str
    side: TeamSide
    schedule_pressure: OperationalContextItem
    fatigue: OperationalContextItem
    travel: OperationalContextItem
    weather: OperationalContextItem
    pitch: OperationalContextItem
    ingested_at: datetime
    cutoff_at: datetime
    provenance_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OperationalContextObservation":
        if not isinstance(raw, Mapping):
            raise TeamContextValidationError("OBSERVATION_NOT_OBJECT", "operational context observation must be an object")
        forbidden = _find_forbidden(raw)
        if forbidden:
            raise TeamContextValidationError("MODEL_FIELD_FORBIDDEN", f"operational context cannot contain {forbidden}")
        match_id = _uuid(raw.get("match_id"), "match_id")
        team_id = _text(raw.get("team_id"), "team_id")
        assert team_id is not None
        side_raw = _text(raw.get("side"), "side")
        assert side_raw is not None
        try:
            side = TeamSide(side_raw.upper())
        except ValueError as exc:
            raise TeamContextValidationError("SIDE_INVALID", "side must be HOME or AWAY") from exc
        items = {category: OperationalContextItem.from_dict(category, raw.get(category)) for category in OPERATIONAL_CONTEXT_FIELDS}
        ingested_at = _timestamp(raw.get("ingested_at"), "ingested_at")
        cutoff_at = _timestamp(raw.get("cutoff_at"), "cutoff_at")
        for item in items.values():
            if item.retrieved_at > cutoff_at or item.source_timestamp > cutoff_at or item.effective_at > cutoff_at:
                raise TeamContextValidationError("POST_CUTOFF_CONTEXT", f"{item.category} is not eligible at cutoff")
            if item.state == "FUTURE_DATA":
                raise TeamContextValidationError("FUTURE_DATA_NOT_ELIGIBLE", f"{item.category} is future data")
        provenance_ref = _text(raw.get("provenance_ref", f"context://{match_id}/{team_id}/{side.value}"), "provenance_ref")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise TeamContextValidationError("METADATA_NOT_OBJECT", "metadata must be an object")
        assert provenance_ref is not None
        return cls(match_id, team_id, side, items["schedule_pressure"], items["fatigue"], items["travel"], items["weather"], items["pitch"], ingested_at, cutoff_at, provenance_ref, _freeze(metadata))

    @property
    def observation_id(self) -> str:
        return _source_observation_id(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "schedule_pressure": self.schedule_pressure.to_dict(),
            "fatigue": self.fatigue.to_dict(),
            "travel": self.travel.to_dict(),
            "weather": self.weather.to_dict(),
            "pitch": self.pitch.to_dict(),
            "ingested_at": _iso(self.ingested_at),
            "cutoff_at": _iso(self.cutoff_at),
            "provenance_ref": self.provenance_ref,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class OperationalContextRecord:
    object_id: str
    contract_version: str
    match_id: str
    team_id: str
    side: TeamSide
    schedule_pressure: OperationalContextItem
    fatigue: OperationalContextItem
    travel: OperationalContextItem
    weather: OperationalContextItem
    pitch: OperationalContextItem
    ingested_at: str
    cutoff_at: str
    provenance_ref: str
    provenance_hash: str
    payload_hash: str
    context_hash: str
    observation_id: str
    revision: int
    supersedes_object_id: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "team_id": self.team_id,
            "side": self.side.value,
            "schedule_pressure": self.schedule_pressure.to_dict(),
            "fatigue": self.fatigue.to_dict(),
            "travel": self.travel.to_dict(),
            "weather": self.weather.to_dict(),
            "pitch": self.pitch.to_dict(),
            "ingested_at": self.ingested_at,
            "cutoff_at": self.cutoff_at,
            "provenance_ref": self.provenance_ref,
            "provenance_hash": self.provenance_hash,
            "payload_hash": self.payload_hash,
            "context_hash": self.context_hash,
            "observation_id": self.observation_id,
            "revision": self.revision,
            "supersedes_object_id": self.supersedes_object_id,
            "metadata": _thaw(self.metadata),
        }


@dataclass(frozen=True)
class OperationalContextResult:
    accepted: bool
    status: str
    action: str
    observation_id: str
    record: Optional[OperationalContextRecord]
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "status": self.status, "action": self.action, "observation_id": self.observation_id, "record": self.record.to_dict() if self.record else None, "error_code": self.error_code}


class OperationalContextStore:
    """V4-035 time-bound operational context intake without feature derivation."""

    def __init__(self, linker: TeamContextIdentityLinker):
        if not isinstance(linker, TeamContextIdentityLinker):
            raise TypeError("V4-035 requires a V4-032 TeamContextIdentityLinker")
        self._linker = linker
        self._observations: Dict[str, OperationalContextObservation] = {}
        self._records: Dict[str, OperationalContextRecord] = {}
        self._latest: Dict[Tuple[str, str, TeamSide], OperationalContextRecord] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def observations(self) -> Tuple[OperationalContextObservation, ...]:
        return tuple(self._observations.values())

    @property
    def records(self) -> Tuple[OperationalContextRecord, ...]:
        return tuple(self._records.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(self._events)

    def ingest(self, raw: Union[OperationalContextObservation, Mapping[str, Any]]) -> OperationalContextResult:
        try:
            observation = raw if isinstance(raw, OperationalContextObservation) else OperationalContextObservation.from_dict(raw)
        except (TeamContextValidationError, IdentityValidationError) as exc:
            observation_id = _source_observation_id(raw if isinstance(raw, Mapping) else raw.to_dict())
            code = getattr(exc, "code", "VALIDATION_FAILED")
            self._events.append({"action": "BLOCKED_VALIDATION", "observation_id": observation_id, "error_code": code})
            return OperationalContextResult(False, "BLOCKED", code, observation_id, None, code)
        observation_id = observation.observation_id
        if observation_id in self._observations:
            existing = next((record for record in self._records.values() if record.observation_id == observation_id), None)
            self._events.append({"action": "DUPLICATE_NOOP", "observation_id": observation_id, "object_id": existing.object_id if existing else None})
            return OperationalContextResult(True, "AVAILABLE", "DUPLICATE_NOOP", observation_id, existing)
        identity = self._linker.get_identity(observation.match_id)
        if identity is None or identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
            return self._blocked(observation, "MATCH_IDENTITY_NOT_RESOLVED")
        expected_team = identity.home_team_id if observation.side == TeamSide.HOME else identity.away_team_id
        if observation.team_id != expected_team:
            return self._blocked(observation, "TEAM_ID_SIDE_CONFLICT")
        link = self._linker.latest(observation.match_id, observation.team_id, observation.side)
        if link is None:
            return self._blocked(observation, "TEAM_CONTEXT_LINK_NOT_FOUND")
        kickoff = datetime.fromisoformat(identity.kickoff_at)
        if not observation.cutoff_at < kickoff:
            return self._blocked(observation, "CUTOFF_NOT_BEFORE_KICKOFF")
        self._observations[observation_id] = observation
        key = (observation.match_id, observation.team_id, observation.side)
        predecessor = self._latest.get(key)
        revision = predecessor.revision + 1 if predecessor else 1
        items = [getattr(observation, category) for category in OPERATIONAL_CONTEXT_FIELDS]
        provenance_hash = sha256_json({"provenance_ref": observation.provenance_ref, "items": [{"source": item.source, "source_reference": item.source_reference, "source_timestamp": _iso(item.source_timestamp), "retrieved_at": _iso(item.retrieved_at), "effective_at": _iso(item.effective_at), "expires_at": _iso(item.expires_at), "provenance_hash": item.provenance_hash} for item in items]})
        payload_hash = sha256_json({"match_id": observation.match_id, "team_id": observation.team_id, "side": observation.side.value, "items": [item.to_dict() for item in items]})
        context_hash = sha256_json({"identity_link_object_id": link.object_id, "payload_hash": payload_hash, "cutoff_at": _iso(observation.cutoff_at), "provenance_hash": provenance_hash})
        object_id = str(uuid.uuid5(TEAM_CONTEXT_ID_NAMESPACE, f"operational|{observation.match_id}|{observation.team_id}|{observation.side.value}|{observation_id}"))
        record = OperationalContextRecord(object_id, CONTRACT_VERSION, observation.match_id, observation.team_id, observation.side, observation.schedule_pressure, observation.fatigue, observation.travel, observation.weather, observation.pitch, _iso(observation.ingested_at), _iso(observation.cutoff_at), observation.provenance_ref, provenance_hash, payload_hash, context_hash, observation_id, revision, predecessor.object_id if predecessor else None, MappingProxyType({"identity_link_object_id": link.object_id, "append_only_boundary": "V4-035 local context ledger; feature/market intelligence deferred", "default_fallback": False}))
        self._records[object_id] = record
        self._latest[key] = record
        self._events.append({"action": "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", "observation_id": observation_id, "object_id": object_id, "supersedes_object_id": predecessor.object_id if predecessor else None})
        return OperationalContextResult(True, "AVAILABLE", "ROOT_CREATED" if predecessor is None else "REVISION_APPENDED", observation_id, record)

    def _blocked(self, observation: OperationalContextObservation, code: str) -> OperationalContextResult:
        observation_id = observation.observation_id
        self._observations.setdefault(observation_id, observation)
        self._events.append({"action": "BLOCKED_CONTEXT", "observation_id": observation_id, "match_id": observation.match_id, "team_id": observation.team_id, "side": observation.side.value, "error_code": code})
        return OperationalContextResult(False, "BLOCKED", code, observation_id, None, code)
