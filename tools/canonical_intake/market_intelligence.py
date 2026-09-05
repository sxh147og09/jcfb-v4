"""V4-046 typed Market Intelligence artifact foundation.

This module consumes already accepted official or external odds snapshots and
normalizes them into a source-separated, cutoff-aware, pre-Frozen artifact.
It does not calculate movement, velocity, divergence, heat, trap-risk, or any
prediction.  All state is local and append-only; no database or live source is
accessed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .external_market import ExternalMarket, ExternalMarketSnapshot, ExternalMarketStatus
from .match_identity import CanonicalMatchIdentityStore
from .official_odds import MARKETS, MarketAvailabilityStatus, OfficialOddsSnapshot


CONTRACT_VERSION = "market-intelligence-feature@1.0.0"
MOVEMENT_CONTRACT_VERSION = "market-movement@1.0.0"
RISK_CONTRACT_VERSION = "market-risk-interpretation@1.0.0"
CONFIG_VERSION = "market-intelligence-config@1.0.0"
MAPPING_REGISTRY_VERSION = "market-intelligence-mapping@1.0.0"
OFFICIAL_SNAPSHOT_CONTRACT_VERSION = "official-odds-snapshot@1.0.0"
EXTERNAL_SNAPSHOT_CONTRACT_VERSION = "external-market-snapshot@1.0.0"
GENERATOR_VERSION = "v4-046-market-intelligence@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_MARKET_INTELLIGENCE_ARTIFACT"
ARTIFACT_NAMESPACE = uuid.UUID("f1bfa260-8789-5f9e-b024-1a2252d9ea34")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TIME_STATES = frozenset({"UNKNOWN", "CONFLICTED"})
SNAPSHOT_KINDS = frozenset({"OPENING", "INTERMEDIATE", "CURRENT", "LATEST", "FINAL", "CORRECTION"})
FORBIDDEN_TERMS = frozenset(
    {
        "prediction",
        "recommendation",
        "model_confidence",
        "win_probability",
        "betting_confidence",
        "score_selection",
        "engine_output",
        "risk_decision",
        "frozen_input_id",
        "frozen_input_hash",
        "heat_score",
        "pressure_score",
        "trap_risk_score",
        "bookmaker_intent",
    }
)


class MarketIntelligenceValidationError(ValueError):
    """A market snapshot cannot safely cross the V4-046 boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketIntelligenceValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise MarketIntelligenceValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MarketIntelligenceValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketIntelligenceValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).casefold())


def _find_forbidden(value: Any, path: str = "artifact") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in {_normalized_key(term) for term in FORBIDDEN_TERMS}:
                return f"{path}.{key}"
            if normalized in {"predictioncutoffat", "prediction_cutoff_at"}:
                found = _find_forbidden(child, f"{path}.{key}")
                if found:
                    return found
                continue
            if any(token in normalized for token in ("recommendation", "modelconfidence", "winprobability", "bettingconfidence", "scoreselection", "engineoutput", "riskdecision", "frozeninput", "bookmakerintent")):
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


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _normalized_status(value: Any) -> str:
    raw = _text(value, "availability_status")
    if raw == "CONFLICT":
        return "CONFLICTED"
    return raw


def _identity_ref(identity: Any) -> Mapping[str, Any]:
    return {
        "object_id": identity.object_id,
        "match_id": identity.match_id,
        "contract_version": identity.contract_version,
        "payload_hash": identity.payload_hash,
        "provenance_hash": identity.provenance_hash,
    }


def _feature_quality(state: str, *, source_resolved: bool) -> Mapping[str, str]:
    if state == "AVAILABLE":
        return MappingProxyType(
            {
                "coverage": "COMPLETE",
                "verification": "VERIFIED" if source_resolved else "UNKNOWN",
                "freshness": "CURRENT",
                "completeness": "COMPLETE",
                "conflict": "NONE",
                "provenance": "RESOLVED" if source_resolved else "UNKNOWN",
            }
        )
    conflict = "PRESENT" if state == "CONFLICTED" else "UNKNOWN"
    freshness = "STALE" if state == "STALE" else "UNKNOWN"
    verification = "PARTIAL" if state == "NOT_VERIFIED" else "UNKNOWN"
    return MappingProxyType(
        {
            "coverage": "PARTIAL",
            "verification": verification,
            "freshness": freshness,
            "completeness": "PARTIAL",
            "conflict": conflict,
            "provenance": "RESOLVED" if source_resolved else "UNKNOWN",
        }
    )


@dataclass(frozen=True)
class MarketIntelligenceArtifact:
    artifact_id: str
    artifact_kind: str
    contract_version: str
    canonical_match_id: str
    canonical_match_ref: Mapping[str, Any]
    market: str
    semantic_market_mapping: str
    semantic_line: Union[float, str]
    provider: str
    source: str
    source_reference: str
    source_is_official: bool
    snapshot_kind: str
    snapshot_ref: Mapping[str, Any]
    source_timestamp: str
    captured_at: str
    observed_at: str
    ingested_at: str
    prediction_cutoff_at: str
    kickoff_at: str
    state: str
    typed_value: Optional[Mapping[str, Any]]
    unit: str
    reason_code: str
    reason_detail: str
    source_refs: Tuple[str, ...]
    basis_refs: Tuple[str, ...]
    feature_quality: Mapping[str, str]
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    mapping_registry_version: str
    input_hash: str
    payload_hash: str
    provenance_hash: str
    output_hash: str
    revision: int
    supersedes_artifact_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "canonical_match_id": self.canonical_match_id,
            "canonical_match_ref": _thaw(self.canonical_match_ref),
            "market": self.market,
            "semantic_market_mapping": self.semantic_market_mapping,
            "semantic_line": self.semantic_line,
            "provider": self.provider,
            "source": self.source,
            "source_reference": self.source_reference,
            "source_is_official": self.source_is_official,
            "snapshot_kind": self.snapshot_kind,
            "snapshot_ref": _thaw(self.snapshot_ref),
            "source_timestamp": self.source_timestamp,
            "captured_at": self.captured_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "state": self.state,
            "typed_value": _thaw(self.typed_value) if self.typed_value is not None else None,
            "unit": self.unit,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "source_refs": list(self.source_refs),
            "basis_refs": list(self.basis_refs),
            "feature_quality": _thaw(self.feature_quality),
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "mapping_registry_version": self.mapping_registry_version,
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "output_hash": self.output_hash,
            "revision": self.revision,
            "supersedes_artifact_id": self.supersedes_artifact_id,
        }


@dataclass(frozen=True)
class MarketIntelligenceResult:
    accepted: bool
    action: str
    artifacts: Tuple[MarketIntelligenceArtifact, ...]
    error_code: Optional[str] = None


@dataclass(frozen=True)
class _AppendEvent:
    sequence: int
    action: str
    artifact_id: Optional[str]
    match_id: Optional[str]
    market: Optional[str]
    state: str
    error_code: Optional[str]


class MarketIntelligenceEngine:
    """Normalize accepted V4-024/V4-027 or V4-028..031 snapshots."""

    def __init__(self, identity_store: CanonicalMatchIdentityStore, *, config: Optional[Mapping[str, Any]] = None, mapping: Optional[Mapping[str, Any]] = None):
        if not isinstance(identity_store, CanonicalMatchIdentityStore):
            raise TypeError("V4-046 requires a V4-020 CanonicalMatchIdentityStore")
        self.identity_store = identity_store
        self.config = dict(config or {})
        self.mapping = dict(mapping or {})
        self._validate_governance()

    @classmethod
    def from_repo_root(cls, root: Path, identity_store: CanonicalMatchIdentityStore) -> "MarketIntelligenceEngine":
        import json

        config = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_CONFIG.json").read_text(encoding="utf-8"))
        mapping = json.loads((root / "docs/V4_MARKET_INTELLIGENCE_MAPPING.json").read_text(encoding="utf-8"))
        return cls(identity_store, config=config, mapping=mapping)

    def _validate_governance(self) -> None:
        if self.config:
            if self.config.get("config_version") != CONFIG_VERSION:
                raise MarketIntelligenceValidationError("CONFIG_VERSION_INVALID", "active config version is not approved")
            if self.config.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
                raise MarketIntelligenceValidationError("MAPPING_VERSION_INVALID", "active mapping version is not approved")
            if self.config.get("lifecycle", {}).get("classification") != "PRE_FROZEN_MARKET_FEATURE_GENERATION":
                raise MarketIntelligenceValidationError("LIFECYCLE_INVALID", "V4-046 must remain pre-Frozen")
            if self.config.get("lifecycle", {}).get("frozen_input_id") != "FORBIDDEN" or self.config.get("lifecycle", {}).get("frozen_input_hash") != "FORBIDDEN":
                raise MarketIntelligenceValidationError("FROZEN_INPUT_BOUNDARY_INVALID", "V4-046 cannot depend on Frozen Input")
        if self.mapping and self.mapping.get("mapping_registry_version") != MAPPING_REGISTRY_VERSION:
            raise MarketIntelligenceValidationError("MAPPING_VERSION_INVALID", "active mapping registry is not approved")

    def normalize_snapshot(self, snapshot: Union[OfficialOddsSnapshot, ExternalMarketSnapshot], prediction_cutoff_at: Any, kickoff_at: Any, *, supersedes_artifact_ids: Optional[Mapping[str, str]] = None) -> MarketIntelligenceResult:
        try:
            cutoff = _timestamp(prediction_cutoff_at, "prediction_cutoff_at")
            kickoff = _timestamp(kickoff_at, "kickoff_at")
            if cutoff >= kickoff:
                raise MarketIntelligenceValidationError("CUTOFF_NOT_BEFORE_KICKOFF", "prediction_cutoff_at must precede kickoff_at")
            if not isinstance(snapshot, (OfficialOddsSnapshot, ExternalMarketSnapshot)):
                raise MarketIntelligenceValidationError("SNAPSHOT_TYPE_INVALID", "V4-046 accepts only typed official/external snapshots")
            identity = self.identity_store.get(snapshot.match_id)
            if identity is None:
                raise MarketIntelligenceValidationError("MATCH_IDENTITY_NOT_FOUND", "canonical match identity is required")
            if identity.status != "AVAILABLE" or identity.identity_resolution_state != "RESOLVED":
                raise MarketIntelligenceValidationError("MATCH_IDENTITY_NOT_RESOLVED", "canonical match identity is not resolved")
            source_timestamp = _text(snapshot.source_timestamp, "source_timestamp")
            source_time = None if source_timestamp.upper() in TIME_STATES else _timestamp(source_timestamp, "source_timestamp")
            captured = _timestamp(snapshot.captured_at, "captured_at")
            observed = _timestamp(snapshot.observed_at, "observed_at")
            ingested = _timestamp(snapshot.ingested_at, "ingested_at")
            if source_time is not None and source_time > captured:
                raise MarketIntelligenceValidationError("SOURCE_TIME_AFTER_CAPTURE", "source availability time cannot follow captured_at")
            if observed < captured or ingested < observed:
                raise MarketIntelligenceValidationError("TIME_ORDER_INVALID", "captured/observed/ingested time order is invalid")
            if isinstance(snapshot, OfficialOddsSnapshot):
                if snapshot.contract_version != OFFICIAL_SNAPSHOT_CONTRACT_VERSION or snapshot.source_is_official is not True:
                    raise MarketIntelligenceValidationError("OFFICIAL_SNAPSHOT_CONTRACT_INVALID", "official snapshot contract or role is invalid")
                artifacts = [self._official_artifact(snapshot, market, identity, source_time, captured, observed, ingested, cutoff, kickoff, supersedes_artifact_ids or {}) for market in MARKETS]
            else:
                if snapshot.contract_version != EXTERNAL_SNAPSHOT_CONTRACT_VERSION or snapshot.source_is_official is not False:
                    raise MarketIntelligenceValidationError("EXTERNAL_SNAPSHOT_CONTRACT_INVALID", "external snapshot contract or role is invalid")
                artifacts = [self._external_artifact(snapshot, identity, source_time, captured, observed, ingested, cutoff, kickoff, supersedes_artifact_ids or {})]
            return MarketIntelligenceResult(True, "NORMALIZED", tuple(artifacts))
        except MarketIntelligenceValidationError as exc:
            return MarketIntelligenceResult(False, "BLOCKED", (), exc.code)

    def _state(self, raw_state: str, source_time: Optional[datetime], cutoff: datetime) -> Tuple[str, str, str]:
        if source_time is None:
            return "BLOCKED", "SOURCE_TIME_UNRESOLVED", "source availability time is UNKNOWN or CONFLICTED"
        if source_time > cutoff:
            return "FUTURE_DATA", "POST_CUTOFF_SNAPSHOT", "source availability time is after prediction cutoff"
        state = _normalized_status(raw_state)
        if not state:
            raise MarketIntelligenceValidationError("STATE_REQUIRED", "snapshot state must be explicit")
        return state, "NOT_APPLICABLE" if state == "AVAILABLE" else "UPSTREAM_EXPLICIT_STATE", "state is retained from the accepted upstream snapshot"

    def _common(self, snapshot: Any, identity: Any, source_time: Optional[datetime], captured: datetime, observed: datetime, ingested: datetime, cutoff: datetime, kickoff: datetime, market: str, mapping: str, line: Union[float, str], state: str, reason_code: str, reason_detail: str, typed_value: Optional[Mapping[str, Any]], unit: str, provider: str, source_ref: str, snapshot_ref: Mapping[str, Any], supersedes: Optional[str]) -> MarketIntelligenceArtifact:
        source_timestamp = snapshot.source_timestamp
        canonical_ref = _identity_ref(identity)
        source_refs = (source_ref, snapshot_ref["snapshot_id"])
        basis_refs = (snapshot_ref["snapshot_id"], snapshot_ref["observation_id"])
        quality = _feature_quality(state, source_resolved=source_time is not None)
        logical_input = {
            "contract_version": CONTRACT_VERSION,
            "canonical_match_ref": canonical_ref,
            "market": market,
            "semantic_market_mapping": mapping,
            "semantic_line": line,
            "provider": provider,
            "source": snapshot.source,
            "source_reference": source_ref,
            "source_is_official": snapshot.source_is_official,
            "snapshot_ref": snapshot_ref,
            "source_timestamp": source_timestamp,
            "captured_at": _iso(captured),
            "observed_at": _iso(observed),
            "ingested_at": _iso(ingested),
            "prediction_cutoff_at": _iso(cutoff),
            "kickoff_at": _iso(kickoff),
            "generator_version": GENERATOR_VERSION,
            "config_version": CONFIG_VERSION,
            "config_hash": self.config.get("config_hash", sha256_json(self.config)),
            "mapping_registry_version": MAPPING_REGISTRY_VERSION,
        }
        input_hash = sha256_json(logical_input)
        payload_hash = sha256_json({"market": market, "semantic_line": line, "state": state, "typed_value": typed_value, "unit": unit, "reason_code": reason_code})
        provenance_hash = sha256_json({"canonical_match_ref": canonical_ref, "source_refs": source_refs, "basis_refs": basis_refs, "source_timestamp": source_timestamp, "captured_at": _iso(captured), "observed_at": _iso(observed), "ingested_at": _iso(ingested)})
        artifact_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"market-artifact|{input_hash}|{payload_hash}|{supersedes or ''}"))
        output_without_hash = {
            "artifact_id": artifact_id,
            "artifact_kind": ARTIFACT_KIND,
            "input_hash": input_hash,
            "payload_hash": payload_hash,
            "provenance_hash": provenance_hash,
            "state": state,
            "typed_value": typed_value,
            "feature_quality": _thaw(quality),
            "revision": 1 if supersedes is None else 2,
            "supersedes_artifact_id": supersedes,
        }
        output_hash = sha256_json(output_without_hash)
        return MarketIntelligenceArtifact(
            artifact_id=artifact_id,
            artifact_kind=ARTIFACT_KIND,
            contract_version=CONTRACT_VERSION,
            canonical_match_id=snapshot.match_id,
            canonical_match_ref=_freeze(canonical_ref),
            market=market,
            semantic_market_mapping=mapping,
            semantic_line=line,
            provider=provider,
            source=snapshot.source,
            source_reference=source_ref,
            source_is_official=snapshot.source_is_official,
            snapshot_kind=snapshot.snapshot_kind.value if hasattr(snapshot.snapshot_kind, "value") else snapshot.snapshot_kind,
            snapshot_ref=_freeze(snapshot_ref),
            source_timestamp=source_timestamp,
            captured_at=_iso(captured),
            observed_at=_iso(observed),
            ingested_at=_iso(ingested),
            prediction_cutoff_at=_iso(cutoff),
            kickoff_at=_iso(kickoff),
            state=state,
            typed_value=_freeze(typed_value) if typed_value is not None else None,
            unit=unit,
            reason_code=reason_code,
            reason_detail=reason_detail,
            source_refs=source_refs,
            basis_refs=basis_refs,
            feature_quality=_freeze(quality),
            generator_version=GENERATOR_VERSION,
            implementation_hash="sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            config_version=CONFIG_VERSION,
            config_hash=self.config.get("config_hash", sha256_json(self.config)),
            mapping_registry_version=MAPPING_REGISTRY_VERSION,
            input_hash=input_hash,
            payload_hash=payload_hash,
            provenance_hash=provenance_hash,
            output_hash=output_hash,
            revision=1 if supersedes is None else 2,
            supersedes_artifact_id=supersedes,
        )

    def _official_artifact(self, snapshot: OfficialOddsSnapshot, market: str, identity: Any, source_time: Optional[datetime], captured: datetime, observed: datetime, ingested: datetime, cutoff: datetime, kickoff: datetime, supersedes: Mapping[str, str]) -> MarketIntelligenceArtifact:
        availability = snapshot.market_availability[market]
        raw_state = str(availability["status"])
        state, reason_code, reason_detail = self._state(raw_state, source_time, cutoff)
        payload = snapshot.payloads[market]
        if state == "AVAILABLE" and (not isinstance(payload, Mapping) or not payload):
            raise MarketIntelligenceValidationError("AVAILABLE_PAYLOAD_EMPTY", f"official {market} AVAILABLE payload is empty")
        if state != "AVAILABLE":
            payload = None
            if raw_state != state and raw_state not in {"AVAILABLE"}:
                reason_code = "POST_CUTOFF_SNAPSHOT" if state == "FUTURE_DATA" else reason_code
            if state == "UPSTREAM_EXPLICIT_STATE":
                state = raw_state
        line: Union[float, str] = payload.get("official_handicap") if market == "rqspf" and isinstance(payload, Mapping) and "official_handicap" in payload else "NOT_APPLICABLE"
        mapping = f"OFFICIAL_{market.upper()}_RAW"
        typed = {"payload": dict(payload)} if payload is not None else None
        return self._common(snapshot, identity, source_time, captured, observed, ingested, cutoff, kickoff, market.upper(), mapping, line, state, reason_code, snapshot.market_unavailable_reason[market] if state == raw_state and state != "AVAILABLE" else reason_detail, typed, "official_market_payload", "CHINA_SPORTS_LOTTERY", snapshot.source_reference, {"snapshot_id": snapshot.snapshot_id, "snapshot_hash": snapshot.snapshot_hash, "observation_id": snapshot.observation_id, "provenance_hash": snapshot.provenance_hash}, supersedes.get(market))

    def _external_artifact(self, snapshot: ExternalMarketSnapshot, identity: Any, source_time: Optional[datetime], captured: datetime, observed: datetime, ingested: datetime, cutoff: datetime, kickoff: datetime, supersedes: Mapping[str, str]) -> MarketIntelligenceArtifact:
        raw_state = snapshot.availability_status.value if isinstance(snapshot.availability_status, ExternalMarketStatus) else str(snapshot.availability_status)
        state, reason_code, reason_detail = self._state(raw_state, source_time, cutoff)
        if state == "AVAILABLE" and (snapshot.prices is None or not snapshot.prices):
            raise MarketIntelligenceValidationError("AVAILABLE_PAYLOAD_EMPTY", "external AVAILABLE prices are empty")
        if state != "AVAILABLE":
            typed = None
            if state == "CONFLICTED" and snapshot.conflict_evidence:
                typed = {"conflict_evidence": [item.to_dict() for item in snapshot.conflict_evidence]}
        else:
            typed = {"line": snapshot.line, "prices": dict(snapshot.prices or {})}
        market = snapshot.market.value if isinstance(snapshot.market, ExternalMarket) else str(snapshot.market)
        mapping = f"EXTERNAL_{market}_RAW"
        unit = "external_market_quote" if state == "AVAILABLE" else "conflict_evidence" if state == "CONFLICTED" else "external_market_quote"
        return self._common(snapshot, identity, source_time, captured, observed, ingested, cutoff, kickoff, market, mapping, snapshot.line, state, reason_code, snapshot.reason_detail or reason_detail, typed, unit, snapshot.provider, snapshot.source_ref, {"snapshot_id": snapshot.snapshot_id, "snapshot_hash": snapshot.snapshot_hash, "observation_id": snapshot.observation_id, "provenance_hash": snapshot.provenance_hash}, supersedes.get(market))


class MarketIntelligenceStore:
    """Append-only local artifact store for V4-046."""

    def __init__(self):
        self._artifacts: Dict[str, MarketIntelligenceArtifact] = {}
        self._events: List[_AppendEvent] = []

    @property
    def artifacts(self) -> Tuple[MarketIntelligenceArtifact, ...]:
        return tuple(self._artifacts.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(MappingProxyType({"sequence": item.sequence, "action": item.action, "artifact_id": item.artifact_id, "match_id": item.match_id, "market": item.market, "state": item.state, "error_code": item.error_code}) for item in self._events)

    def append(self, artifact: MarketIntelligenceArtifact) -> str:
        if not isinstance(artifact, MarketIntelligenceArtifact):
            raise TypeError("MarketIntelligenceStore accepts MarketIntelligenceArtifact only")
        forbidden = _find_forbidden(artifact.to_dict())
        if forbidden:
            self._event("BLOCKED", artifact, "MODEL_FIELD_FORBIDDEN")
            raise MarketIntelligenceValidationError("MODEL_FIELD_FORBIDDEN", f"forbidden field at {forbidden}")
        existing = self._artifacts.get(artifact.artifact_id)
        if existing is not None:
            if existing.to_dict() == artifact.to_dict():
                self._event("DUPLICATE_NOOP", artifact, None)
                return "DUPLICATE_NOOP"
            self._event("BLOCKED", artifact, "ARTIFACT_ID_REUSE")
            raise MarketIntelligenceValidationError("ARTIFACT_ID_REUSE", "artifact identity cannot be reused with different content")
        if artifact.supersedes_artifact_id is not None:
            predecessor = self._artifacts.get(artifact.supersedes_artifact_id)
            if predecessor is None:
                self._event("BLOCKED", artifact, "SUPERSEDES_ARTIFACT_NOT_FOUND")
                raise MarketIntelligenceValidationError("SUPERSEDES_ARTIFACT_NOT_FOUND", "supersedes artifact is not present")
            if predecessor.canonical_match_id != artifact.canonical_match_id or predecessor.market != artifact.market or predecessor.provider != artifact.provider or predecessor.semantic_line != artifact.semantic_line:
                self._event("BLOCKED", artifact, "SUPERSEDES_SCOPE_CONFLICT")
                raise MarketIntelligenceValidationError("SUPERSEDES_SCOPE_CONFLICT", "supersedes artifact must share match/provider/market/semantic line")
            if artifact.revision != predecessor.revision + 1:
                self._event("BLOCKED", artifact, "REVISION_INVALID")
                raise MarketIntelligenceValidationError("REVISION_INVALID", "correction revision must increment by one")
        elif artifact.revision != 1:
            self._event("BLOCKED", artifact, "SUPERSEDES_REQUIRED")
            raise MarketIntelligenceValidationError("SUPERSEDES_REQUIRED", "revisions after the first require supersedes_artifact_id")
        self._artifacts[artifact.artifact_id] = artifact
        self._event("APPEND", artifact, None)
        return "APPEND"

    def latest_eligible(self, match_id: str, market: str, provider: str, semantic_line: Union[float, str], cutoff: Any) -> Optional[MarketIntelligenceArtifact]:
        cutoff_time = _timestamp(cutoff, "prediction_cutoff_at")
        candidates = []
        for artifact in self._artifacts.values():
            if artifact.canonical_match_id != match_id or artifact.market != market or artifact.provider != provider or artifact.semantic_line != semantic_line:
                continue
            if artifact.state != "AVAILABLE" or artifact.source_timestamp.upper() in TIME_STATES:
                continue
            if _timestamp(artifact.source_timestamp, "source_timestamp") > cutoff_time:
                continue
            candidates.append(artifact)
        return max(candidates, key=lambda item: (_timestamp(item.source_timestamp, "source_timestamp"), _timestamp(item.captured_at, "captured_at"), item.snapshot_ref["snapshot_hash"])) if candidates else None

    def _event(self, action: str, artifact: MarketIntelligenceArtifact, error_code: Optional[str]) -> None:
        self._events.append(_AppendEvent(len(self._events) + 1, action, artifact.artifact_id, artifact.canonical_match_id, artifact.market, artifact.state, error_code))


__all__ = [
    "ARTIFACT_KIND",
    "CONFIG_VERSION",
    "CONTRACT_VERSION",
    "GENERATOR_VERSION",
    "MAPPING_REGISTRY_VERSION",
    "MarketIntelligenceArtifact",
    "MarketIntelligenceEngine",
    "MarketIntelligenceResult",
    "MarketIntelligenceStore",
    "MarketIntelligenceValidationError",
]
