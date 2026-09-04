"""V4-041 to V4-043 statistical strength feature engines.

The engines are intentionally local and in-memory.  They consume a frozen
target-scoped historical manifest and emit typed statistical features only.
No prediction, score-engine, persistence, or V3.3.3 boundary is crossed here.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tools.migration_harness.common import sha256_json

from .match_identity import CanonicalMatchIdentityStore


HISTORICAL_CONTRACT_VERSION = "historical-statistical-input@1.0.0"
FEATURE_BUNDLE_CONTRACT_VERSION = "feature-bundle@2.0.0"
CONFIG_VERSION = "statistical-strength-config@1.0.0"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
FEATURE_NAMESPACE = uuid.UUID("37d2cfb7-79cc-56ad-897a-f7cf6791f2ab")


class StatisticalStrengthValidationError(ValueError):
    """Raised when a statistical input or output cannot be admitted safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class HistoricalAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    BLOCKED = "BLOCKED"
    NOT_VERIFIED = "NOT_VERIFIED"


class StatisticalFeatureState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


NUMERIC_OBSERVATION_TYPES = frozenset(
    {
        "GOALS_FOR",
        "GOALS_AGAINST",
        "POINTS",
        "XG",
        "SHOTS",
        "SHOTS_ON_TARGET",
    }
)
RESULT_TYPES = frozenset({"OFFICIAL_RESULT"})
ALLOWED_OBSERVATION_TYPES = NUMERIC_OBSERVATION_TYPES | RESULT_TYPES
FORBIDDEN_MODEL_TERMS = frozenset(
    {
        "prediction",
        "recommendation",
        "confidence",
        "model_confidence",
        "betting_confidence",
        "win_probability",
        "engine_output",
        "score_selection",
        "risk_decision",
        "model_interpretation",
        "lambda",
        "exact_score",
    }
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StatisticalStrengthValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_RE.fullmatch(result):
        raise StatisticalStrengthValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _iso(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StatisticalStrengthValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise StatisticalStrengthValidationError("TIMESTAMP_TIMEZONE_REQUIRED", f"{field} requires timezone")
    return parsed.astimezone(timezone.utc)


def _json_safe(value: Any, path: str = "value") -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise StatisticalStrengthValidationError("PAYLOAD_KEY_INVALID", f"{path} keys must be strings")
            _json_safe(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_safe(child, f"{path}[{index}]")
        return
    raise StatisticalStrengthValidationError("PAYLOAD_TYPE_INVALID", f"{path} is not JSON-compatible")


def _forbidden(value: Any, path: str = "value") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if normalized in {re.sub(r"[^a-z0-9_]", "", item) for item in FORBIDDEN_MODEL_TERMS}:
                return f"{path}.{key}"
            if normalized != "prediction_cutoff_at" and any(
                term in normalized
                for term in ("prediction", "recommendation", "confidence", "winprobability", "engineoutput", "scoreselection", "riskdecision")
            ):
                return f"{path}.{key}"
            found = _forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _implementation_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class StatisticalStrengthConfig:
    config_version: str
    config_hash: str
    dynamic_rating_min_matches: int
    attack_defence_min_matches: int
    home_advantage_min_scope_matches: int
    opponent_adjustment_min_matches: int
    form_decay_min_matches: int
    league_strength_min_scope_matches: int
    promotion_relegation_prior_min_matches: int
    max_historical_matches: int
    max_historical_days: int
    half_life_matches: int
    normalization_baseline_scope: str
    rate_unit: str
    cross_competition_policy: str
    cross_season_policy: str
    neutral_venue_policy: str
    unknown_venue_policy: str
    transition_policy: Mapping[str, str]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config_hash: str) -> "StatisticalStrengthConfig":
        if not isinstance(raw, Mapping):
            raise StatisticalStrengthValidationError("CONFIG_INVALID", "statistical config must be an object")
        version = _text(raw.get("config_version"), "config_version")
        if version != CONFIG_VERSION:
            raise StatisticalStrengthValidationError("CONFIG_VERSION_INVALID", f"expected {CONFIG_VERSION}")
        _hash(config_hash, "config_hash")
        minimum = raw.get("minimum_sample_policy")
        recency = raw.get("recency_policy")
        normalization = raw.get("normalization_policy")
        league = raw.get("league_policy")
        home_away = raw.get("home_away_policy")
        sparse = raw.get("sparse_data_policy")
        transition = raw.get("transition_policy")
        for value, name in ((minimum, "minimum_sample_policy"), (recency, "recency_policy"), (normalization, "normalization_policy"), (league, "league_policy"), (home_away, "home_away_policy"), (sparse, "sparse_data_policy"), (transition, "transition_policy")):
            if not isinstance(value, Mapping):
                raise StatisticalStrengthValidationError("CONFIG_SECTION_INVALID", f"{name} must be an object")

        def integer(section: Mapping[str, Any], key: str) -> int:
            value = section.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise StatisticalStrengthValidationError("CONFIG_INTEGER_INVALID", f"{key} must be a positive integer")
            return value

        expected_sparse = {
            "below_minimum": "NO_NUMERIC_VALUE",
            "blocked_transition": "BLOCKED",
            "feature_state": "UNKNOWN",
            "quality": "PARTIAL",
        }
        if any(sparse.get(key) != value for key, value in expected_sparse.items()):
            raise StatisticalStrengthValidationError("SPARSE_POLICY_INVALID", "sparse policy does not match the approved baseline")
        return cls(
            config_version=version,
            config_hash=config_hash,
            dynamic_rating_min_matches=integer(minimum, "dynamic_rating_min_matches"),
            attack_defence_min_matches=integer(minimum, "attack_defence_min_matches"),
            home_advantage_min_scope_matches=integer(minimum, "home_advantage_min_scope_matches"),
            opponent_adjustment_min_matches=integer(minimum, "opponent_adjustment_min_matches"),
            # The approved compact config predates the explicit form-decay key;
            # its governed minimum is the same five-match baseline as dynamic
            # rating.  Do not invent a new threshold if the two diverge.
            form_decay_min_matches=integer(
                {"form_decay_min_matches": minimum.get("form_decay_min_matches", minimum.get("dynamic_rating_min_matches"))},
                "form_decay_min_matches",
            ),
            league_strength_min_scope_matches=integer(minimum, "league_strength_min_scope_matches"),
            promotion_relegation_prior_min_matches=integer(minimum, "promotion_relegation_prior_min_matches"),
            max_historical_matches=integer(recency, "max_historical_matches"),
            max_historical_days=integer(recency, "max_historical_days"),
            half_life_matches=integer(recency, "half_life_matches"),
            normalization_baseline_scope=_text(normalization.get("baseline_scope"), "normalization_policy.baseline_scope"),
            rate_unit=_text(normalization.get("rate_unit"), "normalization_policy.rate_unit"),
            cross_competition_policy=_text(league.get("cross_competition"), "league_policy.cross_competition"),
            cross_season_policy=_text(league.get("cross_season"), "league_policy.cross_season"),
            neutral_venue_policy=_text(home_away.get("neutral_venue"), "home_away_policy.neutral_venue"),
            unknown_venue_policy=_text(home_away.get("unknown_venue"), "home_away_policy.unknown_venue"),
            transition_policy=MappingProxyType({str(key): _text(value, f"transition_policy.{key}") for key, value in transition.items()}),
        )

    @classmethod
    def load_approved(cls, project_root: Path) -> "StatisticalStrengthConfig":
        root = Path(project_root).resolve()
        if root.drive.upper() != "F:":
            raise StatisticalStrengthValidationError("F_DRIVE_REQUIRED", "statistical config must be loaded from the F: drive")
        path = root / "docs" / "V4_BATCH_11_STATISTICAL_HISTORICAL_INPUT_CONFIG.json"
        raw_bytes = path.read_bytes()
        import json

        return cls.from_dict(json.loads(raw_bytes.decode("utf-8")), config_hash="sha256:" + hashlib.sha256(raw_bytes).hexdigest())


@dataclass(frozen=True)
class HistoricalObservation:
    historical_input_id: str
    source_match_id: str
    target_match_id: str
    source_match_identity_hash: str
    target_match_identity_hash: str
    team_id: str
    competition_id: str
    season_id: str
    competition_type: str
    side: str
    venue_status: str
    observation_type: str
    value: Any
    unit: str
    source: str
    source_reference: str
    evidence_refs: Tuple[Mapping[str, str], ...]
    source_event_at: datetime
    result_known_at: Optional[datetime]
    stat_available_at: Optional[datetime]
    published_at: Optional[datetime]
    observed_at: Optional[datetime]
    retrieved_at: Optional[datetime]
    ingested_at: Optional[datetime]
    availability_at: datetime
    revision: int
    revision_visible_at_cutoff: int
    supersedes_id: Optional[str]
    availability_status: HistoricalAvailability
    verification_state: str
    quality_state: str
    payload_hash: str
    provenance_hash: str
    content_hash: str
    correction_published_at: Optional[datetime]
    opponent_team_id: Optional[str]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HistoricalObservation":
        if not isinstance(raw, Mapping):
            raise StatisticalStrengthValidationError("OBSERVATION_INVALID", "historical observation must be an object")
        forbidden = _forbidden(raw)
        if forbidden:
            raise StatisticalStrengthValidationError("MODEL_FIELD_FORBIDDEN", f"model/prediction field is forbidden: {forbidden}")
        contract = _text(raw.get("contract_version"), "contract_version")
        if contract != HISTORICAL_CONTRACT_VERSION:
            raise StatisticalStrengthValidationError("CONTRACT_VERSION_INVALID", f"expected {HISTORICAL_CONTRACT_VERSION}")
        status_raw = raw.get("availability_status")
        try:
            status = status_raw if isinstance(status_raw, HistoricalAvailability) else HistoricalAvailability(status_raw)
        except (TypeError, ValueError) as exc:
            raise StatisticalStrengthValidationError("AVAILABILITY_STATUS_INVALID", "availability_status is not governed") from exc
        source_match_id = _text(raw.get("source_match_id"), "source_match_id")
        target_match_id = _text(raw.get("target_match_id"), "target_match_id")
        if source_match_id == target_match_id:
            raise StatisticalStrengthValidationError("TARGET_SELF_RESULT_FORBIDDEN", "source_match_id must differ from target_match_id")
        observation_type = _text(raw.get("observation_type"), "observation_type")
        if observation_type not in ALLOWED_OBSERVATION_TYPES:
            raise StatisticalStrengthValidationError("OBSERVATION_TYPE_INVALID", "observation_type is not approved")
        value = raw.get("value")
        if observation_type in NUMERIC_OBSERVATION_TYPES:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise StatisticalStrengthValidationError("NUMERIC_VALUE_INVALID", f"{observation_type} requires a finite numeric value")
        elif value not in {"HOME", "DRAW", "AWAY"}:
            raise StatisticalStrengthValidationError("RESULT_VALUE_INVALID", "OFFICIAL_RESULT must be HOME, DRAW, or AWAY")
        side = _text(raw.get("side"), "side")
        if side not in {"HOME", "AWAY", "NEUTRAL"}:
            raise StatisticalStrengthValidationError("SIDE_INVALID", "side must be HOME, AWAY, or NEUTRAL")
        venue_status = _text(raw.get("venue_status"), "venue_status")
        if venue_status not in {"HOME", "AWAY", "NEUTRAL", "UNKNOWN"}:
            raise StatisticalStrengthValidationError("VENUE_STATUS_INVALID", "venue_status is invalid")
        if venue_status != "UNKNOWN" and venue_status != side:
            raise StatisticalStrengthValidationError("SIDE_VENUE_MISMATCH", "venue_status must match the canonical source side")
        source = _text(raw.get("source"), "source")
        source_reference = _text(raw.get("source_reference"), "source_reference")
        raw_evidence = raw.get("evidence_refs")
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise StatisticalStrengthValidationError("EVIDENCE_REFERENCE_REQUIRED", "evidence_refs must be a non-empty list")
        evidence: List[Mapping[str, str]] = []
        for index, item in enumerate(raw_evidence):
            if not isinstance(item, Mapping):
                raise StatisticalStrengthValidationError("EVIDENCE_REFERENCE_INVALID", f"evidence_refs[{index}] must be an object")
            evidence.append(
                MappingProxyType(
                    {
                        "evidence_id": _text(item.get("evidence_id"), f"evidence_refs[{index}].evidence_id"),
                        "evidence_hash": _hash(item.get("evidence_hash"), f"evidence_refs[{index}].evidence_hash"),
                    }
                )
            )
        status_fields = ("verification_state", "quality_state")
        verification_state = _text(raw.get("verification_state"), "verification_state")
        quality_state = _text(raw.get("quality_state"), "quality_state")
        for field in status_fields:
            if field == "verification_state" and verification_state not in {"VERIFIED", "PARTIAL", "NOT_VERIFIED", "UNKNOWN"}:
                raise StatisticalStrengthValidationError("VERIFICATION_STATE_INVALID", "verification_state is invalid")
            if field == "quality_state" and quality_state not in {"AVAILABLE", "PARTIAL", "UNKNOWN", "CONFLICT", "STALE", "BLOCKED"}:
                raise StatisticalStrengthValidationError("QUALITY_STATE_INVALID", "quality_state is invalid")
        reason_code = raw.get("reason_code")
        reason_detail = raw.get("reason_detail")
        if status is not HistoricalAvailability.AVAILABLE:
            if not isinstance(reason_code, str) or not REASON_RE.fullmatch(reason_code):
                raise StatisticalStrengthValidationError("REASON_CODE_REQUIRED", "non-AVAILABLE observations require reason_code")
            if not isinstance(reason_detail, str) or not reason_detail.strip():
                raise StatisticalStrengthValidationError("REASON_DETAIL_REQUIRED", "non-AVAILABLE observations require reason_detail")
        else:
            if verification_state != "VERIFIED" or quality_state != "AVAILABLE":
                raise StatisticalStrengthValidationError("AVAILABLE_STATUS_INCOMPLETE", "AVAILABLE requires VERIFIED and AVAILABLE quality")
        revision = raw.get("revision", raw.get("revision_visible_at_cutoff"))
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise StatisticalStrengthValidationError("REVISION_INVALID", "revision must be a positive integer")
        visible_revision = raw.get("revision_visible_at_cutoff", revision)
        if not isinstance(visible_revision, int) or isinstance(visible_revision, bool) or visible_revision < 1:
            raise StatisticalStrengthValidationError("VISIBLE_REVISION_INVALID", "revision_visible_at_cutoff must be positive")
        if visible_revision != revision:
            raise StatisticalStrengthValidationError("REVISION_VISIBILITY_MISMATCH", "revision must be the exact visible revision")
        return cls(
            historical_input_id=_text(raw.get("historical_input_id"), "historical_input_id"),
            source_match_id=source_match_id,
            target_match_id=target_match_id,
            source_match_identity_hash=_hash(raw.get("source_match_identity_hash"), "source_match_identity_hash"),
            target_match_identity_hash=_hash(raw.get("target_match_identity_hash"), "target_match_identity_hash"),
            team_id=_text(raw.get("team_id"), "team_id"),
            competition_id=_text(raw.get("competition_id"), "competition_id"),
            season_id=_text(raw.get("season_id"), "season_id"),
            competition_type=_text(raw.get("competition_type"), "competition_type"),
            side=side,
            venue_status=venue_status,
            observation_type=observation_type,
            value=value,
            unit=_text(raw.get("unit"), "unit"),
            source=source,
            source_reference=source_reference,
            evidence_refs=tuple(evidence),
            source_event_at=_iso(raw.get("source_event_at"), "source_event_at"),
            result_known_at=_iso(raw["result_known_at"], "result_known_at") if raw.get("result_known_at") else None,
            stat_available_at=_iso(raw["stat_available_at"], "stat_available_at") if raw.get("stat_available_at") else None,
            published_at=_iso(raw["published_at"], "published_at") if raw.get("published_at") else None,
            observed_at=_iso(raw["observed_at"], "observed_at") if raw.get("observed_at") else None,
            retrieved_at=_iso(raw["retrieved_at"], "retrieved_at") if raw.get("retrieved_at") else None,
            ingested_at=_iso(raw["ingested_at"], "ingested_at") if raw.get("ingested_at") else None,
            availability_at=_iso(raw.get("availability_at"), "availability_at"),
            revision=revision,
            revision_visible_at_cutoff=visible_revision,
            supersedes_id=_text(raw["supersedes_id"], "supersedes_id") if raw.get("supersedes_id") else None,
            availability_status=status,
            verification_state=verification_state,
            quality_state=quality_state,
            payload_hash=_hash(raw.get("payload_hash"), "payload_hash"),
            provenance_hash=_hash(raw.get("provenance_hash"), "provenance_hash"),
            content_hash=_hash(raw.get("content_hash"), "content_hash"),
            correction_published_at=_iso(raw["correction_published_at"], "correction_published_at") if raw.get("correction_published_at") else None,
            opponent_team_id=_text(raw["opponent_team_id"], "opponent_team_id") if raw.get("opponent_team_id") else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        def time_value(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value else None

        return {
            "historical_input_id": self.historical_input_id,
            "contract_version": HISTORICAL_CONTRACT_VERSION,
            "source_match_id": self.source_match_id,
            "target_match_id": self.target_match_id,
            "source_match_identity_hash": self.source_match_identity_hash,
            "target_match_identity_hash": self.target_match_identity_hash,
            "team_id": self.team_id,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "competition_type": self.competition_type,
            "side": self.side,
            "venue_status": self.venue_status,
            "observation_type": self.observation_type,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "source_reference": self.source_reference,
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "source_event_at": time_value(self.source_event_at),
            "result_known_at": time_value(self.result_known_at),
            "stat_available_at": time_value(self.stat_available_at),
            "published_at": time_value(self.published_at),
            "observed_at": time_value(self.observed_at),
            "retrieved_at": time_value(self.retrieved_at),
            "ingested_at": time_value(self.ingested_at),
            "availability_at": time_value(self.availability_at),
            "revision": self.revision,
            "revision_visible_at_cutoff": self.revision_visible_at_cutoff,
            "supersedes_id": self.supersedes_id,
            "availability_status": self.availability_status.value,
            "verification_state": self.verification_state,
            "quality_state": self.quality_state,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "content_hash": self.content_hash,
            "correction_published_at": time_value(self.correction_published_at),
            "opponent_team_id": self.opponent_team_id,
        }

    def eligibility_reason(self, *, target_match_id: str, cutoff_at: datetime, kickoff_at: datetime) -> Optional[str]:
        cutoff = cutoff_at.astimezone(timezone.utc)
        kickoff = kickoff_at.astimezone(timezone.utc)
        if self.target_match_id != target_match_id:
            return "TARGET_IDENTITY_MISMATCH"
        if self.source_match_id == target_match_id:
            return "TARGET_SELF_RESULT_FORBIDDEN"
        if self.availability_status is not HistoricalAvailability.AVAILABLE:
            return self.availability_status.value
        if self.source_event_at > cutoff or self.availability_at > cutoff or not cutoff < kickoff:
            return "FUTURE_DATA"
        if self.correction_published_at and self.correction_published_at > cutoff:
            return "POST_CUTOFF_CORRECTION"
        if self.revision_visible_at_cutoff != self.revision:
            return "REVISION_NOT_VISIBLE"
        if self.verification_state != "VERIFIED" or self.quality_state != "AVAILABLE":
            return "NOT_VERIFIED"
        return None


@dataclass(frozen=True)
class HistoricalInputManifest:
    historical_input_manifest_id: str
    contract_version: str
    target_match_id: str
    target_match_identity_hash: str
    target_competition_id: str
    target_season_id: str
    target_prediction_cutoff_at: datetime
    target_kickoff_at: datetime
    observations: Tuple[HistoricalObservation, ...]
    excluded_sample_counts: Mapping[str, int]
    config_version: str
    config_hash: str
    input_hash: str

    @classmethod
    def build(
        cls,
        *,
        target_match_id: str,
        target_match_identity_hash: str,
        target_competition_id: str,
        target_season_id: str,
        target_prediction_cutoff_at: str,
        target_kickoff_at: str,
        observations: Iterable[Mapping[str, Any]],
        config: StatisticalStrengthConfig,
        identity_store: CanonicalMatchIdentityStore,
    ) -> "HistoricalInputManifest":
        target_match_id = _text(target_match_id, "target_match_id")
        target_hash = _hash(target_match_identity_hash, "target_match_identity_hash")
        target_competition_id = _text(target_competition_id, "target_competition_id")
        target_season_id = _text(target_season_id, "target_season_id")
        cutoff = _iso(target_prediction_cutoff_at, "target_prediction_cutoff_at")
        kickoff = _iso(target_kickoff_at, "target_kickoff_at")
        if not cutoff < kickoff:
            raise StatisticalStrengthValidationError("TARGET_TIME_ORDER_INVALID", "target cutoff must precede target kickoff")
        target_identity = identity_store.get(target_match_id)
        if target_identity is None or target_identity.status != "AVAILABLE" or target_identity.identity_resolution_state != "RESOLVED":
            raise StatisticalStrengthValidationError("TARGET_IDENTITY_NOT_RESOLVED", "target canonical match identity is unavailable")
        if target_identity.payload_hash != target_hash:
            raise StatisticalStrengthValidationError("TARGET_IDENTITY_HASH_MISMATCH", "target canonical match identity hash does not match the manifest")
        accepted: List[HistoricalObservation] = []
        excluded: Dict[str, int] = {}
        for raw in observations:
            try:
                item = raw if isinstance(raw, HistoricalObservation) else HistoricalObservation.from_dict(raw)
            except StatisticalStrengthValidationError as exc:
                excluded[exc.code] = excluded.get(exc.code, 0) + 1
                continue
            source_identity = identity_store.get(item.source_match_id)
            if source_identity is None or source_identity.status != "AVAILABLE" or source_identity.identity_resolution_state != "RESOLVED":
                reason = "SOURCE_IDENTITY_NOT_RESOLVED"
            elif source_identity.payload_hash != item.source_match_identity_hash:
                reason = "SOURCE_IDENTITY_HASH_MISMATCH"
            elif item.competition_id != target_competition_id or item.season_id != target_season_id:
                reason = "COMPETITION_SCOPE_MISMATCH"
            else:
                reason = item.eligibility_reason(target_match_id=target_match_id, cutoff_at=cutoff, kickoff_at=kickoff)
            if reason:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            accepted.append(item)
        grouped: Dict[str, List[HistoricalObservation]] = {}
        for item in accepted:
            grouped.setdefault(item.team_id, []).append(item)
        selected: List[HistoricalObservation] = []
        for team_id, items in grouped.items():
            ordered = sorted(items, key=lambda item: (-item.source_event_at.timestamp(), item.source_match_id, item.historical_input_id))
            match_order: List[str] = []
            by_match: Dict[str, List[HistoricalObservation]] = {}
            for item in ordered:
                if item.source_match_id not in by_match:
                    match_order.append(item.source_match_id)
                    by_match[item.source_match_id] = []
                by_match[item.source_match_id].append(item)
            retained_matches = set(match_order[: config.max_historical_matches])
            for source_match_id in match_order:
                if source_match_id in retained_matches:
                    selected.extend(by_match[source_match_id])
            if len(match_order) > config.max_historical_matches:
                excluded["WINDOW_EXCLUDED"] = excluded.get("WINDOW_EXCLUDED", 0) + len(match_order) - config.max_historical_matches
        selected.sort(key=lambda item: (item.team_id, -item.source_event_at.timestamp(), item.source_match_id, item.historical_input_id))
        manifest_id = str(uuid.uuid5(FEATURE_NAMESPACE, f"manifest|{target_match_id}|{target_hash}|{cutoff.isoformat()}|{kickoff.isoformat()}|{config.config_hash}"))
        input_payload = {
            "contract_version": HISTORICAL_CONTRACT_VERSION,
            "manifest_id": manifest_id,
            "target_match_id": target_match_id,
            "target_match_identity_hash": target_hash,
            "target_competition_id": target_competition_id,
            "target_season_id": target_season_id,
            "target_prediction_cutoff_at": cutoff.isoformat(),
            "target_kickoff_at": kickoff.isoformat(),
            "config_version": config.config_version,
            "config_hash": config.config_hash,
            "observations": [
                {
                    "id": item.historical_input_id,
                    "source_match_id": item.source_match_id,
                    "revision": item.revision,
                    "content_hash": item.content_hash,
                    "payload_hash": item.payload_hash,
                    "provenance_hash": item.provenance_hash,
                    "observation_type": item.observation_type,
                    "value": item.value,
                    "unit": item.unit,
                }
                for item in selected
            ],
        }
        return cls(
            historical_input_manifest_id=manifest_id,
            contract_version=HISTORICAL_CONTRACT_VERSION,
            target_match_id=target_match_id,
            target_match_identity_hash=target_hash,
            target_competition_id=target_competition_id,
            target_season_id=target_season_id,
            target_prediction_cutoff_at=cutoff,
            target_kickoff_at=kickoff,
            observations=tuple(selected),
            excluded_sample_counts=MappingProxyType(dict(sorted(excluded.items()))),
            config_version=config.config_version,
            config_hash=config.config_hash,
            input_hash=sha256_json(input_payload),
        )

    def for_team(self, team_id: str, *, observation_types: Optional[Iterable[str]] = None) -> Tuple[HistoricalObservation, ...]:
        allowed = set(observation_types) if observation_types is not None else None
        return tuple(item for item in self.observations if item.team_id == team_id and (allowed is None or item.observation_type in allowed))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "historical_input_manifest_id": self.historical_input_manifest_id,
            "contract_version": self.contract_version,
            "target_match_id": self.target_match_id,
            "target_match_identity_hash": self.target_match_identity_hash,
            "target_competition_id": self.target_competition_id,
            "target_season_id": self.target_season_id,
            "target_prediction_cutoff_at": self.target_prediction_cutoff_at.isoformat(),
            "target_kickoff_at": self.target_kickoff_at.isoformat(),
            "observations": [item.to_dict() for item in self.observations],
            "excluded_sample_counts": dict(self.excluded_sample_counts),
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "input_hash": self.input_hash,
        }


@dataclass(frozen=True)
class FeatureQuality:
    coverage: str
    verification: str
    freshness: str
    completeness: str
    conflict: str
    provenance: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "coverage": self.coverage,
            "verification": self.verification,
            "freshness": self.freshness,
            "completeness": self.completeness,
            "conflict": self.conflict,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class StatisticalFeature:
    feature_id: str
    feature_type: str
    target_match_id: str
    team_id: Optional[str]
    state: StatisticalFeatureState
    value: Optional[float]
    unit: Optional[str]
    usable_sample_count: int
    excluded_sample_counts: Mapping[str, int]
    historical_horizon: Mapping[str, Any]
    source_match_refs: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    derivation_identity: str
    historical_input_manifest_id: str
    input_hash: str
    feature_quality: FeatureQuality
    output_hash: str
    reason_code: Optional[str] = None
    reason_detail: Optional[str] = None
    revision: int = 1
    supersedes_feature_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "target_match_id": self.target_match_id,
            "team_id": self.team_id,
            "state": self.state.value,
            "value": self.value,
            "unit": self.unit,
            "usable_sample_count": self.usable_sample_count,
            "excluded_sample_counts": dict(self.excluded_sample_counts),
            "historical_horizon": dict(self.historical_horizon),
            "source_match_refs": list(self.source_match_refs),
            "evidence_refs": list(self.evidence_refs),
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "derivation_identity": self.derivation_identity,
            "historical_input_manifest_id": self.historical_input_manifest_id,
            "input_hash": self.input_hash,
            "feature_quality": self.feature_quality.to_dict(),
            "output_hash": self.output_hash,
            "revision": self.revision,
            "supersedes_feature_id": self.supersedes_feature_id,
        }
        if self.state is not StatisticalFeatureState.AVAILABLE:
            result.update({"reason_code": self.reason_code, "reason_detail": self.reason_detail})
        return result


def _weighted_mean(items: Sequence[HistoricalObservation], value_fn) -> Optional[float]:
    if not items:
        return None
    ordered = sorted(items, key=lambda item: (-item.source_event_at.timestamp(), item.source_match_id, item.historical_input_id))
    numerator = 0.0
    denominator = 0.0
    for rank, item in enumerate(ordered):
        weight = math.exp(-math.log(2.0) * rank / item._half_life_matches) if hasattr(item, "_half_life_matches") else 1.0
        numerator += float(value_fn(item)) * weight
        denominator += weight
    return numerator / denominator if denominator else None


class _FeatureEngineBase:
    def __init__(self, config: StatisticalStrengthConfig):
        self.config = config
        self.implementation_hash = _implementation_hash()

    def _validate_bundle(self, feature_bundle: Mapping[str, Any], target_match_id: str) -> None:
        if not isinstance(feature_bundle, Mapping):
            raise StatisticalStrengthValidationError("FEATURE_BUNDLE_REQUIRED", "a versioned Feature Bundle handoff is required")
        forbidden = _forbidden(feature_bundle)
        if forbidden:
            raise StatisticalStrengthValidationError("MODEL_FIELD_FORBIDDEN", f"model/prediction field is forbidden: {forbidden}")
        if feature_bundle.get("contract_version") != FEATURE_BUNDLE_CONTRACT_VERSION:
            raise StatisticalStrengthValidationError("FEATURE_BUNDLE_VERSION_INVALID", "Feature Bundle contract version is invalid")
        entity_refs = feature_bundle.get("canonical_entity_refs")
        if not isinstance(entity_refs, Mapping) or entity_refs.get("match_id") != target_match_id:
            raise StatisticalStrengthValidationError("FEATURE_BUNDLE_MATCH_MISMATCH", "Feature Bundle is not bound to target match")
        for field in ("feature_snapshot_hash", "input_hash", "config_hash"):
            _hash(feature_bundle.get(field), f"feature_bundle.{field}")
        _text(feature_bundle.get("feature_schema_version"), "feature_bundle.feature_schema_version")
        _text(feature_bundle.get("generator_version"), "feature_bundle.generator_version")

    def _make_feature(
        self,
        *,
        generator_version: str,
        feature_type: str,
        manifest: HistoricalInputManifest,
        team_id: Optional[str],
        state: StatisticalFeatureState,
        value: Optional[float],
        unit: Optional[str],
        usable: Sequence[HistoricalObservation],
        quality: FeatureQuality,
        reason_code: Optional[str] = None,
        reason_detail: Optional[str] = None,
        extra_identity: Optional[Mapping[str, Any]] = None,
    ) -> StatisticalFeature:
        if state is StatisticalFeatureState.AVAILABLE and (value is None or not math.isfinite(float(value))):
            raise StatisticalStrengthValidationError("AVAILABLE_VALUE_INVALID", "AVAILABLE statistical feature requires a finite numeric value")
        if state is not StatisticalFeatureState.AVAILABLE and (not reason_code or not REASON_RE.fullmatch(reason_code) or not reason_detail):
            raise StatisticalStrengthValidationError("FEATURE_REASON_REQUIRED", "non-AVAILABLE statistical feature requires reason code and detail")
        source_refs = tuple(dict.fromkeys(item.source_match_id for item in usable))
        evidence_refs = tuple(sorted({evidence["evidence_id"] for item in usable for evidence in item.evidence_refs}))
        usable_count = len(source_refs)
        horizon = {
            "max_historical_matches": self.config.max_historical_matches,
            "max_historical_days": self.config.max_historical_days,
            "latest_source_event_at": max((item.source_event_at for item in usable), default=None).isoformat() if usable else None,
            "earliest_source_event_at": min((item.source_event_at for item in usable), default=None).isoformat() if usable else None,
        }
        derivation_identity = sha256_json(
            {
                "generator_version": generator_version,
                "feature_type": feature_type,
                "target_match_id": manifest.target_match_id,
                "team_id": team_id,
                "manifest_id": manifest.historical_input_manifest_id,
                "extra": dict(extra_identity or {}),
            }
        )
        payload = {
            "feature_id": str(uuid.uuid5(FEATURE_NAMESPACE, derivation_identity)),
            "feature_type": feature_type,
            "target_match_id": manifest.target_match_id,
            "team_id": team_id,
            "state": state.value,
            "value": value,
            "unit": unit,
            "usable_sample_count": usable_count,
            "excluded_sample_counts": dict(manifest.excluded_sample_counts),
            "historical_horizon": horizon,
            "source_match_refs": list(source_refs),
            "evidence_refs": list(evidence_refs),
            "generator_version": generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config.config_version,
            "config_hash": self.config.config_hash,
            "derivation_identity": derivation_identity,
            "historical_input_manifest_id": manifest.historical_input_manifest_id,
            "input_hash": manifest.input_hash,
            "feature_quality": quality.to_dict(),
            "reason_code": reason_code,
            "reason_detail": reason_detail,
            "revision": 1,
            "supersedes_feature_id": None,
        }
        return StatisticalFeature(
            feature_id=payload["feature_id"],
            feature_type=feature_type,
            target_match_id=manifest.target_match_id,
            team_id=team_id,
            state=state,
            value=value,
            unit=unit,
            usable_sample_count=usable_count,
            excluded_sample_counts=MappingProxyType(dict(manifest.excluded_sample_counts)),
            historical_horizon=MappingProxyType(horizon),
            source_match_refs=source_refs,
            evidence_refs=evidence_refs,
            generator_version=generator_version,
            implementation_hash=self.implementation_hash,
            config_version=self.config.config_version,
            config_hash=self.config.config_hash,
            derivation_identity=derivation_identity,
            historical_input_manifest_id=manifest.historical_input_manifest_id,
            input_hash=manifest.input_hash,
            feature_quality=quality,
            output_hash=sha256_json(payload),
            reason_code=reason_code,
            reason_detail=reason_detail,
        )

    def _weighted(self, items: Sequence[HistoricalObservation], value_fn) -> Optional[float]:
        ordered = sorted(items, key=lambda item: (-item.source_event_at.timestamp(), item.source_match_id, item.historical_input_id))
        match_rank: Dict[str, int] = {}
        for item in ordered:
            if item.source_match_id not in match_rank:
                match_rank[item.source_match_id] = len(match_rank)
        numerator = 0.0
        denominator = 0.0
        for item in ordered:
            rank = match_rank[item.source_match_id]
            weight = math.exp(-math.log(2.0) * rank / self.config.half_life_matches)
            numerator += float(value_fn(item)) * weight
            denominator += weight
        return numerator / denominator if denominator else None

    @staticmethod
    def _quality(*, complete: bool, provenance: str = "RESOLVED") -> FeatureQuality:
        return FeatureQuality(
            coverage="COMPLETE" if complete else "PARTIAL",
            verification="VERIFIED" if complete else "PARTIAL",
            freshness="CURRENT" if complete else "UNKNOWN",
            completeness="COMPLETE" if complete else "PARTIAL",
            conflict="NONE",
            provenance=provenance,
        )

    def _sparse(self, *, generator_version: str, feature_type: str, manifest: HistoricalInputManifest, team_id: Optional[str], usable: Sequence[HistoricalObservation], minimum: int, unit: str) -> StatisticalFeature:
        return self._make_feature(
            generator_version=generator_version,
            feature_type=feature_type,
            manifest=manifest,
            team_id=team_id,
            state=StatisticalFeatureState.UNKNOWN,
            value=None,
            unit=unit,
            usable=usable,
            quality=self._quality(complete=False),
            reason_code="INSUFFICIENT_SAMPLE",
            reason_detail=f"{len({item.source_match_id for item in usable})} eligible source matches are below the approved minimum of {minimum}",
        )


class DynamicTeamRatingEngine(_FeatureEngineBase):
    generator_version = "v4-041-dynamic-team-rating@1.0.0"

    def generate(self, *, manifest: HistoricalInputManifest, team_id: str, feature_bundle: Mapping[str, Any]) -> StatisticalFeature:
        self._validate_bundle(feature_bundle, manifest.target_match_id)
        team_id = _text(team_id, "team_id")
        items = manifest.for_team(team_id, observation_types={"POINTS"})
        if len(items) < self.config.dynamic_rating_min_matches:
            return self._sparse(
                generator_version=self.generator_version,
                feature_type="DYNAMIC_TEAM_RATING",
                manifest=manifest,
                team_id=team_id,
                usable=items,
                minimum=self.config.dynamic_rating_min_matches,
                unit="weighted_points_per_eligible_match",
            )
        value = self._weighted(items, lambda item: item.value)
        return self._make_feature(
            generator_version=self.generator_version,
            feature_type="DYNAMIC_TEAM_RATING",
            manifest=manifest,
            team_id=team_id,
            state=StatisticalFeatureState.AVAILABLE,
            value=value,
            unit="weighted_points_per_eligible_match",
            usable=items,
            quality=self._quality(complete=True),
            extra_identity={"half_life_matches": self.config.half_life_matches, "observation_type": "POINTS"},
        )


@dataclass(frozen=True)
class AttackDefenceHomeAdvantageResult:
    attack: StatisticalFeature
    defence: StatisticalFeature
    home_advantage: StatisticalFeature

    @property
    def features(self) -> Tuple[StatisticalFeature, ...]:
        return (self.attack, self.defence, self.home_advantage)


class AttackDefenceHomeAdvantageEngine(_FeatureEngineBase):
    generator_version = "v4-042-attack-defence-home-advantage@1.0.0"

    def generate(self, *, manifest: HistoricalInputManifest, team_id: str, feature_bundle: Mapping[str, Any]) -> AttackDefenceHomeAdvantageResult:
        self._validate_bundle(feature_bundle, manifest.target_match_id)
        team_id = _text(team_id, "team_id")
        attack_items = manifest.for_team(team_id, observation_types={"GOALS_FOR"})
        defence_items = manifest.for_team(team_id, observation_types={"GOALS_AGAINST"})
        attack = self._rate(
            manifest=manifest,
            team_id=team_id,
            feature_type="ATTACK_STRENGTH",
            items=attack_items,
            minimum=self.config.attack_defence_min_matches,
            unit="goals_for_per_eligible_match",
            value_fn=lambda item: item.value,
        )
        defence = self._rate(
            manifest=manifest,
            team_id=team_id,
            feature_type="DEFENCE_STRENGTH",
            items=defence_items,
            minimum=self.config.attack_defence_min_matches,
            unit="goals_against_per_eligible_match",
            value_fn=lambda item: item.value,
        )
        home_items = self._home_goal_differentials(manifest, team_id)
        if any(item.venue_status == "UNKNOWN" for item in manifest.for_team(team_id)):
            home = self._make_feature(
                generator_version=self.generator_version,
                feature_type="HOME_ADVANTAGE",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.BLOCKED,
                value=None,
                unit="goals_per_eligible_home_match",
                usable=home_items,
                quality=self._quality(complete=False, provenance="PARTIAL"),
                reason_code="VENUE_UNKNOWN",
                reason_detail="home advantage cannot infer an unknown venue",
            )
        elif len(home_items) < self.config.home_advantage_min_scope_matches:
            home = self._sparse(
                generator_version=self.generator_version,
                feature_type="HOME_ADVANTAGE",
                manifest=manifest,
                team_id=team_id,
                usable=home_items,
                minimum=self.config.home_advantage_min_scope_matches,
                unit="goals_per_eligible_home_match",
            )
        else:
            home = self._make_feature(
                generator_version=self.generator_version,
                feature_type="HOME_ADVANTAGE",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.AVAILABLE,
                value=self._weighted(home_items, lambda item: item.value),
                unit="goals_per_eligible_home_match",
                usable=home_items,
                quality=self._quality(complete=True),
                extra_identity={"scope": "HOME", "metric": "goals_for_minus_goals_against"},
            )
        return AttackDefenceHomeAdvantageResult(attack=attack, defence=defence, home_advantage=home)

    def _rate(self, *, manifest, team_id, feature_type, items, minimum, unit, value_fn) -> StatisticalFeature:
        if len(items) < minimum:
            return self._sparse(generator_version=self.generator_version, feature_type=feature_type, manifest=manifest, team_id=team_id, usable=items, minimum=minimum, unit=unit)
        return self._make_feature(
            generator_version=self.generator_version,
            feature_type=feature_type,
            manifest=manifest,
            team_id=team_id,
            state=StatisticalFeatureState.AVAILABLE,
            value=self._weighted(items, value_fn),
            unit=unit,
            usable=items,
            quality=self._quality(complete=True),
            extra_identity={"half_life_matches": self.config.half_life_matches, "unit": unit},
        )

    @staticmethod
    def _home_goal_differentials(manifest: HistoricalInputManifest, team_id: str) -> Tuple[HistoricalObservation, ...]:
        grouped: Dict[str, Dict[str, HistoricalObservation]] = {}
        for item in manifest.for_team(team_id):
            if item.side != "HOME" or item.venue_status == "UNKNOWN":
                continue
            grouped.setdefault(item.source_match_id, {})[item.observation_type] = item
        result: List[HistoricalObservation] = []
        for match_id, pair in grouped.items():
            if "GOALS_FOR" not in pair or "GOALS_AGAINST" not in pair:
                continue
            base = pair["GOALS_FOR"]
            derived = HistoricalObservation(
                historical_input_id=f"{base.historical_input_id}|home-diff",
                source_match_id=base.source_match_id,
                target_match_id=base.target_match_id,
                source_match_identity_hash=base.source_match_identity_hash,
                target_match_identity_hash=base.target_match_identity_hash,
                team_id=base.team_id,
                competition_id=base.competition_id,
                season_id=base.season_id,
                competition_type=base.competition_type,
                side=base.side,
                venue_status=base.venue_status,
                observation_type="GOALS_FOR",
                value=float(pair["GOALS_FOR"].value) - float(pair["GOALS_AGAINST"].value),
                unit="goals_per_eligible_home_match",
                source=base.source,
                source_reference=base.source_reference,
                evidence_refs=base.evidence_refs,
                source_event_at=base.source_event_at,
                result_known_at=base.result_known_at,
                stat_available_at=base.stat_available_at,
                published_at=base.published_at,
                observed_at=base.observed_at,
                retrieved_at=base.retrieved_at,
                ingested_at=base.ingested_at,
                availability_at=base.availability_at,
                revision=base.revision,
                revision_visible_at_cutoff=base.revision_visible_at_cutoff,
                supersedes_id=base.supersedes_id,
                availability_status=base.availability_status,
                verification_state=base.verification_state,
                quality_state=base.quality_state,
                payload_hash=base.payload_hash,
                provenance_hash=base.provenance_hash,
                content_hash=base.content_hash,
                correction_published_at=base.correction_published_at,
                opponent_team_id=base.opponent_team_id,
            )
            result.append(derived)
        return tuple(result)


@dataclass(frozen=True)
class OpponentFormLeagueResult:
    opponent_adjusted: StatisticalFeature
    form_decay: StatisticalFeature
    league_strength: StatisticalFeature
    transition: StatisticalFeature

    @property
    def features(self) -> Tuple[StatisticalFeature, ...]:
        return (self.opponent_adjusted, self.form_decay, self.league_strength, self.transition)


class OpponentFormLeagueStrengthEngine(_FeatureEngineBase):
    generator_version = "v4-043-opponent-form-league-strength@1.0.0"

    def generate(
        self,
        *,
        manifest: HistoricalInputManifest,
        team_id: str,
        feature_bundle: Mapping[str, Any],
        upstream_features: Sequence[StatisticalFeature],
        transition_required: bool = False,
        transition_mapping_ref: Optional[str] = None,
    ) -> OpponentFormLeagueResult:
        self._validate_bundle(feature_bundle, manifest.target_match_id)
        team_id = _text(team_id, "team_id")
        upstream = tuple(upstream_features)
        if any(item.target_match_id != manifest.target_match_id or item.config_hash != manifest.config_hash for item in upstream):
            raise StatisticalStrengthValidationError("UPSTREAM_FEATURE_LINEAGE_MISMATCH", "V4-041/V4-042 features do not match manifest/config")
        required_upstream = {"DYNAMIC_TEAM_RATING", "ATTACK_STRENGTH", "DEFENCE_STRENGTH"}
        available_upstream = {item.feature_type for item in upstream if item.state is StatisticalFeatureState.AVAILABLE}
        if not required_upstream.issubset(available_upstream):
            missing = ",".join(sorted(required_upstream - available_upstream))
            raise StatisticalStrengthValidationError("UPSTREAM_FEATURES_INCOMPLETE", f"V4-043 requires accepted V4-041/V4-042 features: {missing}")
        rating_by_team = {item.team_id: item.value for item in upstream if item.feature_type == "DYNAMIC_TEAM_RATING" and item.state is StatisticalFeatureState.AVAILABLE and item.team_id}
        points = manifest.for_team(team_id, observation_types={"POINTS"})
        opponent_items = tuple(item for item in points if item.opponent_team_id and item.opponent_team_id in rating_by_team)
        if len(opponent_items) < self.config.opponent_adjustment_min_matches:
            opponent = self._sparse(generator_version=self.generator_version, feature_type="OPPONENT_ADJUSTED_STRENGTH", manifest=manifest, team_id=team_id, usable=opponent_items, minimum=self.config.opponent_adjustment_min_matches, unit="opponent_adjusted_points_per_eligible_match")
        else:
            opponent = self._make_feature(
                generator_version=self.generator_version,
                feature_type="OPPONENT_ADJUSTED_STRENGTH",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.AVAILABLE,
                value=self._weighted(opponent_items, lambda item: float(item.value) - float(rating_by_team[item.opponent_team_id])),
                unit="opponent_adjusted_points_per_eligible_match",
                usable=opponent_items,
                quality=self._quality(complete=True),
                extra_identity={"opponent_rating_feature": "DYNAMIC_TEAM_RATING"},
            )
        if len(points) < self.config.form_decay_min_matches:
            form = self._sparse(generator_version=self.generator_version, feature_type="FORM_DECAY", manifest=manifest, team_id=team_id, usable=points, minimum=self.config.form_decay_min_matches, unit="decayed_points_per_eligible_match")
        else:
            form = self._make_feature(
                generator_version=self.generator_version,
                feature_type="FORM_DECAY",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.AVAILABLE,
                value=self._weighted(points, lambda item: item.value),
                unit="decayed_points_per_eligible_match",
                usable=points,
                quality=self._quality(complete=True),
                extra_identity={"half_life_matches": self.config.half_life_matches},
            )
        league_points = tuple(item for item in manifest.observations if item.observation_type == "POINTS")
        league_match_ids = {item.source_match_id for item in league_points}
        if len(league_match_ids) < self.config.league_strength_min_scope_matches:
            league = self._sparse(generator_version=self.generator_version, feature_type="LEAGUE_STRENGTH", manifest=manifest, team_id=None, usable=league_points, minimum=self.config.league_strength_min_scope_matches, unit="competition_season_points_per_eligible_match")
        else:
            league = self._make_feature(
                generator_version=self.generator_version,
                feature_type="LEAGUE_STRENGTH",
                manifest=manifest,
                team_id=None,
                state=StatisticalFeatureState.AVAILABLE,
                value=self._weighted(league_points, lambda item: item.value),
                unit="competition_season_points_per_eligible_match",
                usable=league_points,
                quality=self._quality(complete=True),
                extra_identity={"baseline_scope": self.config.normalization_baseline_scope},
            )
        if transition_required and not transition_mapping_ref:
            transition = self._make_feature(
                generator_version=self.generator_version,
                feature_type="PROMOTION_RELEGATION_TRANSITION",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.BLOCKED,
                value=None,
                unit=None,
                usable=points,
                quality=self._quality(complete=False, provenance="PARTIAL"),
                reason_code="TRANSITION_MAPPING_REQUIRED",
                reason_detail="approved explicit promotion/relegation transition mapping is absent",
            )
        elif transition_required:
            transition = self._make_feature(
                generator_version=self.generator_version,
                feature_type="PROMOTION_RELEGATION_TRANSITION",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.AVAILABLE,
                value=0.0,
                unit="explicit_transition_adjustment",
                usable=points,
                quality=self._quality(complete=True),
                extra_identity={"transition_mapping_ref": _text(transition_mapping_ref, "transition_mapping_ref")},
            )
        else:
            transition = self._make_feature(
                generator_version=self.generator_version,
                feature_type="PROMOTION_RELEGATION_TRANSITION",
                manifest=manifest,
                team_id=team_id,
                state=StatisticalFeatureState.NOT_APPLICABLE,
                value=None,
                unit=None,
                usable=(),
                quality=FeatureQuality("UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "NONE", "RESOLVED"),
                reason_code="NO_TRANSITION_DECLARED",
                reason_detail="no promotion/relegation transition was declared for this target scope",
            )
        return OpponentFormLeagueResult(opponent_adjusted=opponent, form_decay=form, league_strength=league, transition=transition)


class StatisticalFeatureStore:
    """Append-only local feature observation store."""

    def __init__(self) -> None:
        self._features: Dict[str, StatisticalFeature] = {}
        self._latest_by_derivation: Dict[str, StatisticalFeature] = {}

    @property
    def features(self) -> Tuple[StatisticalFeature, ...]:
        return tuple(self._features.values())

    def append(self, feature: StatisticalFeature) -> str:
        if not verify_feature_hash(feature):
            raise StatisticalStrengthValidationError("OUTPUT_HASH_MISMATCH", "feature output hash does not match its canonical payload")
        existing = self._features.get(feature.feature_id)
        if existing:
            if existing.output_hash == feature.output_hash:
                return "DUPLICATE_NOOP"
            raise StatisticalStrengthValidationError("FEATURE_ID_REUSE", "feature identity cannot be reused with different content")
        previous = self._latest_by_derivation.get(feature.derivation_identity)
        if previous:
            if feature.revision <= previous.revision or feature.supersedes_feature_id != previous.feature_id:
                raise StatisticalStrengthValidationError("SUPERSEDES_REQUIRED", "correction must append a higher revision that supersedes the prior feature")
        elif feature.revision != 1 or feature.supersedes_feature_id is not None:
            raise StatisticalStrengthValidationError("REVISION_ROOT_INVALID", "first feature revision must be 1 without supersedes")
        self._features[feature.feature_id] = feature
        self._latest_by_derivation[feature.derivation_identity] = feature
        return "APPEND"


def verify_feature_hash(feature: StatisticalFeature) -> bool:
    raw = feature.to_dict()
    expected = raw.pop("output_hash")
    return expected == sha256_json(
        {
            **raw,
            "reason_code": feature.reason_code,
            "reason_detail": feature.reason_detail,
        }
    )
