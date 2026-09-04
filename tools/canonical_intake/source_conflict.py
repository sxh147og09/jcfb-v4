"""V4-037 source quality, expiry, and conflict handling.

This module consumes the V4-036 EvidenceGraphStore.  It never rewrites an
Evidence item, invents source precedence, or removes competing evidence.
Quality assessments and conflict resolutions are separate append-only audit
records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from tools.migration_harness.common import sha256_json

from .evidence_graph import (
    ContradictionState,
    EvidenceGraphStore,
    EvidenceGraphValidationError,
    EvidenceItem,
    EvidenceRelation,
    VerificationState,
    _hash,
    _iso,
    _text,
    _timestamp,
    _validate_string_list,
    _thaw,
)


class SourceQualityBand(str):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class FreshnessState(str):
    CURRENT = "CURRENT"
    STALE = "STALE"
    FUTURE_DATA = "FUTURE_DATA"
    UNKNOWN_TIME = "UNKNOWN_TIME"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SourceQualityAssessment:
    assessment_id: str
    evidence_id: str
    quality_band: str
    quality_basis: Tuple[str, ...]
    assessed_by: str
    assessed_at: datetime
    quality_hash: str
    revision: int = 1
    supersedes_assessment_id: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SourceQualityAssessment":
        if not isinstance(raw, Mapping):
            raise EvidenceGraphValidationError("QUALITY_NOT_OBJECT", "source quality must be an object")
        assessment_id = _text(raw.get("assessment_id"), "assessment_id")
        evidence_id = _text(raw.get("evidence_id"), "evidence_id")
        quality_band = _text(raw.get("quality_band"), "quality_band")
        assert quality_band is not None
        quality_band = quality_band.upper()
        if quality_band not in {SourceQualityBand.HIGH, SourceQualityBand.MEDIUM, SourceQualityBand.LOW, SourceQualityBand.UNKNOWN}:
            raise EvidenceGraphValidationError("QUALITY_BAND_INVALID", "quality_band is not governed")
        quality_basis = _validate_string_list(raw.get("quality_basis"), "quality_basis")
        if not quality_basis:
            raise EvidenceGraphValidationError("QUALITY_BASIS_REQUIRED", "quality_basis is required")
        assessed_by = _text(raw.get("assessed_by"), "assessed_by")
        assessed_at = _timestamp(raw.get("assessed_at"), "assessed_at")
        revision = raw.get("revision", 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise EvidenceGraphValidationError("REVISION_INVALID", "quality revision must be positive")
        supersedes = _text(raw.get("supersedes_assessment_id"), "supersedes_assessment_id", required=False)
        assert assessment_id is not None and evidence_id is not None and assessed_by is not None and assessed_at is not None
        quality_hash = sha256_json({"assessment_id": assessment_id, "evidence_id": evidence_id, "quality_band": quality_band, "quality_basis": list(quality_basis), "assessed_by": assessed_by, "assessed_at": _iso(assessed_at), "revision": revision, "supersedes_assessment_id": supersedes})
        supplied = raw.get("quality_hash")
        if supplied is not None and _hash(supplied, "quality_hash") != quality_hash:
            raise EvidenceGraphValidationError("QUALITY_HASH_MISMATCH", "quality_hash does not match assessment")
        return cls(assessment_id, evidence_id, quality_band, quality_basis, assessed_by, assessed_at, quality_hash, revision, supersedes)

    def to_dict(self) -> Dict[str, Any]:
        return {"assessment_id": self.assessment_id, "evidence_id": self.evidence_id, "quality_band": self.quality_band, "quality_basis": list(self.quality_basis), "assessed_by": self.assessed_by, "assessed_at": _iso(self.assessed_at), "quality_hash": self.quality_hash, "revision": self.revision, "supersedes_assessment_id": self.supersedes_assessment_id}


@dataclass(frozen=True)
class EvidenceQualityResult:
    evidence_id: str
    quality_band: str
    freshness_state: str
    verification_state: VerificationState
    contradiction_state: ContradictionState
    eligible: bool
    blockers: Tuple[str, ...]
    quality_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {"evidence_id": self.evidence_id, "quality_band": self.quality_band, "freshness_state": self.freshness_state, "verification_state": self.verification_state.value, "contradiction_state": self.contradiction_state.value, "eligible": self.eligible, "blockers": list(self.blockers), "quality_hash": self.quality_hash}


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
            raise EvidenceGraphValidationError("RESOLUTION_SELECTION_INVALID", "selected evidence must be in retained conflict set")
        resolution_hash = sha256_json({"resolution_id": resolution_id, "claim_id": claim_id, "evidence_ids": list(evidence_ids), "resolution_reason": reason, "basis_evidence_ids": list(basis_ids), "actor": actor, "resolved_at": _iso(resolved_at), "policy_reference": policy_reference, "selected_evidence_id": selected})
        supplied = raw.get("resolution_hash")
        if supplied is not None and _hash(supplied, "resolution_hash") != resolution_hash:
            raise EvidenceGraphValidationError("RESOLUTION_HASH_MISMATCH", "resolution_hash does not match resolution record")
        return cls(resolution_id, claim_id, evidence_ids, reason, basis_ids, actor, resolved_at, policy_reference, selected, resolution_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {"resolution_id": self.resolution_id, "claim_id": self.claim_id, "evidence_ids": list(self.evidence_ids), "resolution_reason": self.resolution_reason, "basis_evidence_ids": list(self.basis_evidence_ids), "actor": self.actor, "resolved_at": _iso(self.resolved_at), "policy_reference": self.policy_reference, "selected_evidence_id": self.selected_evidence_id, "resolution_hash": self.resolution_hash, "status": ContradictionState.RESOLVED.value}


class SourceConflictResolver:
    """Assess quality/freshness and record explicit conflict resolution only."""

    def __init__(self, graph: EvidenceGraphStore):
        if not isinstance(graph, EvidenceGraphStore):
            raise TypeError("V4-037 requires a V4-036 EvidenceGraphStore")
        self._graph = graph
        self._quality: Dict[str, SourceQualityAssessment] = {}
        self._quality_history: Dict[str, SourceQualityAssessment] = {}
        self._resolutions: Dict[str, ConflictResolutionRecord] = {}
        self._events: List[Mapping[str, Any]] = []

    @property
    def quality_assessments(self) -> Tuple[SourceQualityAssessment, ...]:
        return tuple(self._quality_history.values())

    @property
    def resolutions(self) -> Tuple[ConflictResolutionRecord, ...]:
        return tuple(self._resolutions.values())

    @property
    def events(self) -> Tuple[Mapping[str, Any], ...]:
        return tuple(MappingProxyType(dict(event)) for event in self._events)

    def assess_source(self, raw: Union[SourceQualityAssessment, Mapping[str, Any]]) -> SourceQualityAssessment:
        assessment = raw if isinstance(raw, SourceQualityAssessment) else SourceQualityAssessment.from_dict(raw)
        if self._graph.get(assessment.evidence_id) is None:
            raise EvidenceGraphValidationError("EVIDENCE_NOT_FOUND", "quality assessment must reference an evidence item")
        previous = self._quality.get(assessment.evidence_id)
        if previous is not None:
            if assessment.supersedes_assessment_id != previous.assessment_id or assessment.revision != previous.revision + 1:
                raise EvidenceGraphValidationError("QUALITY_REVISION_SEQUENCE_INVALID", "quality changes require an append-only successor")
        elif assessment.supersedes_assessment_id is not None or assessment.revision != 1:
            raise EvidenceGraphValidationError("QUALITY_ROOT_REVISION_INVALID", "first quality assessment must be revision 1")
        self._quality[assessment.evidence_id] = assessment
        self._quality_history[assessment.assessment_id] = assessment
        self._events.append({"action": "QUALITY_ASSESSED", "assessment_id": assessment.assessment_id, "evidence_id": assessment.evidence_id, "supersedes_assessment_id": assessment.supersedes_assessment_id, "quality_hash": assessment.quality_hash})
        return assessment

    def conflict_state(self, claim_id: str) -> ContradictionState:
        items = self._graph.for_claim(claim_id)
        if not items:
            return ContradictionState.NONE
        if any(record.claim_id == claim_id for record in self._resolutions.values()):
            return ContradictionState.RESOLVED
        if len(items) < 2:
            return items[0].contradiction_state
        fingerprints = {sha256_json(_thaw(item.claim)) for item in items}
        if len(fingerprints) > 1 or any(item.relation == EvidenceRelation.CONTRADICTS for item in items):
            return ContradictionState.CONFLICTED
        if any(item.contradiction_state in {ContradictionState.PENDING, ContradictionState.CONFLICTED} for item in items):
            return ContradictionState.CONFLICTED
        return ContradictionState.NONE

    def conflict_set(self, claim_id: str) -> Tuple[EvidenceItem, ...]:
        return self._graph.for_claim(claim_id)

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
                freshness = FreshnessState.BLOCKED
                blockers.append("CUTOFF_NOT_BEFORE_KICKOFF")
            if item.valid_from is None or item.valid_from > cutoff or item.retrieved_at > cutoff:
                freshness = FreshnessState.FUTURE_DATA
                blockers.append("NOT_ELIGIBLE_AT_CUTOFF")
        if item.verification_state in {VerificationState.NOT_VERIFIED, VerificationState.REJECTED, VerificationState.STALE}:
            blockers.append(f"VERIFICATION_{item.verification_state.value}")
        contradiction = self.conflict_state(item.claim_id)
        if contradiction == ContradictionState.CONFLICTED:
            blockers.append("UNRESOLVED_CONFLICT")
        if item.contradiction_state in {ContradictionState.PENDING, ContradictionState.CONFLICTED} and contradiction != ContradictionState.RESOLVED:
            blockers.append("CONTRADICTION_NOT_RESOLVED")
        if band == SourceQualityBand.UNKNOWN:
            blockers.append("SOURCE_QUALITY_UNKNOWN")
        eligible = not blockers
        quality_hash = sha256_json({"evidence_id": evidence_id, "quality_band": band, "freshness_state": freshness, "verification_state": item.verification_state.value, "contradiction_state": contradiction.value, "eligible": eligible, "blockers": blockers})
        return EvidenceQualityResult(evidence_id, band, freshness, item.verification_state, contradiction, eligible, tuple(blockers), quality_hash)

    def resolve_conflict(self, raw: Union[ConflictResolutionRecord, Mapping[str, Any]]) -> ConflictResolutionRecord:
        record = raw if isinstance(raw, ConflictResolutionRecord) else ConflictResolutionRecord.from_dict(raw)
        items = self._graph.for_claim(record.claim_id)
        ids = {item.evidence_id for item in items}
        if not ids or set(record.evidence_ids) != ids or not set(record.basis_evidence_ids).issubset(ids):
            raise EvidenceGraphValidationError("RESOLUTION_REFERENCE_INVALID", "resolution must retain the complete claim evidence set")
        if self.conflict_state(record.claim_id) not in {ContradictionState.CONFLICTED, ContradictionState.RESOLVED}:
            raise EvidenceGraphValidationError("NO_CONFLICT_TO_RESOLVE", "resolution requires a conflicting claim set")
        existing = self._resolutions.get(record.resolution_id)
        if existing is not None:
            if existing.resolution_hash == record.resolution_hash:
                return existing
            raise EvidenceGraphValidationError("RESOLUTION_ID_REUSE", "resolution_id cannot be reused")
        self._resolutions[record.resolution_id] = record
        self._events.append({"action": "CONFLICT_RESOLVED", "resolution_id": record.resolution_id, "claim_id": record.claim_id, "evidence_ids": list(record.evidence_ids), "selected_evidence_id": record.selected_evidence_id, "resolution_hash": record.resolution_hash})
        return record


__all__ = [
    "ConflictResolutionRecord",
    "EvidenceQualityResult",
    "FreshnessState",
    "SourceConflictResolver",
    "SourceQualityAssessment",
    "SourceQualityBand",
]
