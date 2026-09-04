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

