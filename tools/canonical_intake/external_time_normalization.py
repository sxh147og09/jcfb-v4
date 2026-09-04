"""V4-031 external source-time normalization boundary.

The normalizer creates only auditable references to already accepted external
snapshots. It never mutates or rewrites an original snapshot, performs no new
cutoff gate, and never invents a snapshot when source time is unknown or
conflicting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.migration_harness.common import sha256_json

from .external_market import ExternalMarketSnapshot


CONTRACT_VERSION = "external-source-time-normalization@1.0.0"
NORMALIZATION_NAMESPACE = uuid.UUID("8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020")
AMBIGUOUS_SOURCE_TIMES = frozenset({"UNKNOWN", "CONFLICTED"})


class SourceTimeNormalizationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NormalizedExternalSnapshotRef:
    snapshot_id: str
    snapshot_hash: str
    provenance_hash: str
    match_id: str
    provider: str
    source_ref: str
    market: str
    line: Any
    availability_status: str
    reason_code: Optional[str]
    source_timestamp: str
    captured_at: str
    observed_at: str
    ingested_at: str
    source_time_basis: str
    normalization_key: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "provenance_hash": self.provenance_hash,
            "match_id": self.match_id,
            "provider": self.provider,
            "source_ref": self.source_ref,
            "market": self.market,
            "line": self.line,
            "availability_status": self.availability_status,
            "reason_code": self.reason_code,
            "source_timestamp": self.source_timestamp,
            "captured_at": self.captured_at,
            "observed_at": self.observed_at,
            "ingested_at": self.ingested_at,
            "source_time_basis": self.source_time_basis,
            "normalization_key": self.normalization_key,
        }


@dataclass(frozen=True)
class NormalizedExternalSnapshotSet:
    normalization_id: str
    contract_version: str
    match_id: str
    accepted: bool
    status: str
    reason_code: Optional[str]
    original_snapshot_ids: Tuple[str, ...]
    entries: Tuple[NormalizedExternalSnapshotRef, ...]
    source_time_order: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "normalization_id": self.normalization_id,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "accepted": self.accepted,
            "status": self.status,
            "reason_code": self.reason_code,
            "original_snapshot_ids": list(self.original_snapshot_ids),
            "entries": [entry.to_dict() for entry in self.entries],
            "source_time_order": list(self.source_time_order),
        }


@dataclass(frozen=True)
class SourceTimeNormalizationResult:
    accepted: bool
    action: str
    normalization: Optional[NormalizedExternalSnapshotSet]
    error_code: Optional[str] = None


class ExternalSourceTimeNormalizer:
    """Normalize accepted external snapshots without synthesizing records."""

    def normalize(self, snapshots: Sequence[ExternalMarketSnapshot]) -> SourceTimeNormalizationResult:
        if not isinstance(snapshots, (list, tuple)) or not snapshots:
            return SourceTimeNormalizationResult(False, "BLOCKED_VALIDATION", None, "SNAPSHOTS_REQUIRED")
        if any(not isinstance(item, ExternalMarketSnapshot) for item in snapshots):
            return SourceTimeNormalizationResult(False, "BLOCKED_VALIDATION", None, "SNAPSHOT_TYPE_INVALID")
        snapshot_ids = [item.snapshot_id for item in snapshots]
        if len(set(snapshot_ids)) != len(snapshot_ids):
            return SourceTimeNormalizationResult(False, "BLOCKED_VALIDATION", None, "DUPLICATE_SNAPSHOT_REF")
        match_ids = {item.match_id for item in snapshots}
        if len(match_ids) != 1:
            return SourceTimeNormalizationResult(False, "BLOCKED_BOUNDARY", None, "MATCH_SCOPE_CONFLICT")
        match_id = next(iter(match_ids))

        def sort_key(item: ExternalMarketSnapshot) -> Tuple[int, datetime, str]:
            if item.source_timestamp in AMBIGUOUS_SOURCE_TIMES:
                return (1, datetime.max, item.snapshot_id)
            return (0, datetime.fromisoformat(item.source_timestamp), item.snapshot_id)

        ordered = sorted(snapshots, key=sort_key)
        refs: List[NormalizedExternalSnapshotRef] = []
        blocked_code: Optional[str] = None
        for item in ordered:
            if item.source_timestamp in AMBIGUOUS_SOURCE_TIMES:
                blocked_code = "SOURCE_TIME_AMBIGUOUS" if item.source_timestamp == "CONFLICTED" else "SOURCE_TIME_UNKNOWN"
            if item.availability_status.value != "AVAILABLE" and blocked_code is None:
                blocked_code = "SNAPSHOT_NOT_AVAILABLE"
            source_time_basis = "SOURCE_TIMESTAMP" if item.source_timestamp not in AMBIGUOUS_SOURCE_TIMES else item.source_timestamp
            key_material = {
                "match_id": item.match_id,
                "provider": item.provider,
                "market": item.market.value,
                "line": item.line,
                "captured_at": item.captured_at,
                "source_timestamp": item.source_timestamp,
                "snapshot_id": item.snapshot_id,
                "snapshot_hash": item.snapshot_hash,
            }
            normalization_key = "external-time:" + sha256_json(key_material).split(":", 1)[1]
            refs.append(NormalizedExternalSnapshotRef(
                snapshot_id=item.snapshot_id,
                snapshot_hash=item.snapshot_hash,
                provenance_hash=item.provenance_hash,
                match_id=item.match_id,
                provider=item.provider,
                source_ref=item.source_ref,
                market=item.market.value,
                line=item.line,
                availability_status=item.availability_status.value,
                reason_code=item.reason_code,
                source_timestamp=item.source_timestamp,
                captured_at=item.captured_at,
                observed_at=item.observed_at,
                ingested_at=item.ingested_at,
                source_time_basis=source_time_basis,
                normalization_key=normalization_key,
            ))
        original_ids = tuple(item.snapshot_id for item in ordered)
        normalization_id = str(uuid.uuid5(
            NORMALIZATION_NAMESPACE,
            f"external-normalization|{sha256_json({'match_id': match_id, 'snapshot_ids': original_ids, 'snapshot_hashes': [item.snapshot_hash for item in ordered]})}",
        ))
        normalized = NormalizedExternalSnapshotSet(
            normalization_id=normalization_id,
            contract_version=CONTRACT_VERSION,
            match_id=match_id,
            accepted=blocked_code is None,
            status="AVAILABLE" if blocked_code is None else "BLOCKED",
            reason_code=blocked_code,
            original_snapshot_ids=original_ids,
            entries=tuple(refs),
            source_time_order=tuple(item.snapshot_id for item in ordered),
        )
        if blocked_code is not None:
            return SourceTimeNormalizationResult(False, "BLOCKED_SOURCE_TIME", normalized, blocked_code)
        return SourceTimeNormalizationResult(True, "NORMALIZED_REFERENCES", normalized)


ExternalSourceTimeNormalization = ExternalSourceTimeNormalizer
