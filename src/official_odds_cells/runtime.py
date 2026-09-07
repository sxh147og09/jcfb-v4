"""In-memory full trace builder and mechanical unresolved-trace derivation."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from tools.migration_harness.common import sha256_json

from .contract import MARKETS, UNRESOLVED_STATUSES, load_contract, parser_config_hash
from .layout import CellLocatorRegistry, LayoutProfileRegistry
from .parser import PARSER_IDENTITY, PARSER_VERSION, ParserStatus, parse_value


TRACE_NAMESPACE = uuid.UUID("a6c0f2d2-8f49-5ef9-b930-7e6b7a41f7c0")
DEFAULT_PROFILE_ID = "cn-sports-lottery-odds-grid-v1"
IMPLEMENTATION_HASH = "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class FullTraceResult:
    raw_image_sha256: str
    layout_status: str
    layout_reason: str
    records: tuple[dict[str, Any], ...]

    @property
    def unresolved_records(self) -> tuple[dict[str, Any], ...]:
        return derive_unresolved_trace(self.records)

    def to_jsonl(self, *, unresolved_only: bool = False) -> bytes:
        import json

        records = self.unresolved_records if unresolved_only else self.records
        return b"".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for record in records)


def _image_hash(raw_image: bytes) -> str:
    if not isinstance(raw_image, bytes) or not raw_image:
        raise ValueError("raw_image must be non-empty immutable bytes")
    return "sha256:" + hashlib.sha256(raw_image).hexdigest()


def _evidence_for(evidence: Optional[Mapping[Any, Any]], market: str, label: str) -> Optional[Mapping[str, Any]]:
    if not evidence:
        return None
    for key in ((market, label), f"{market}|{label}", f"{market}:{label}"):
        if key in evidence:
            return evidence[key]
    nested = evidence.get(market)
    if isinstance(nested, Mapping):
        item = nested.get(label)
        if isinstance(item, Mapping):
            return item
    return None


def _timestamps(raw: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    names = ("source_timestamp", "captured_at", "observed_at", "ingested_at")
    result = {name: "UNKNOWN" for name in names}
    if raw is None:
        return result
    if not isinstance(raw, Mapping):
        raise ValueError("source_timestamps must be an object")
    for name in names:
        if name in raw:
            value = raw[name]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string or omitted")
            result[name] = value.strip()
    return result


def trace_record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("trace_record_sha256", None)
    return sha256_json(payload)


def _trace_id(artifact_identity: str, raw_hash: str, market: str, label: str, ordering_index: int, locator_key: str) -> str:
    key = "|".join((artifact_identity, raw_hash, market, label, str(ordering_index), locator_key))
    return str(uuid.uuid5(TRACE_NAMESPACE, key))


def build_full_trace(
    raw_image: bytes,
    *,
    artifact_identity: str,
    source_width: int,
    source_height: int,
    layout_profile_id: str = DEFAULT_PROFILE_ID,
    layout_regions: Optional[Mapping[str, Mapping[str, Any]]] = None,
    evidence: Optional[Mapping[Any, Any]] = None,
    market_availability: Optional[Mapping[str, str]] = None,
    cell_presence: Optional[Mapping[Any, bool]] = None,
    source_timestamps: Optional[Mapping[str, Any]] = None,
    contract: Optional[Mapping[str, Any]] = None,
) -> FullTraceResult:
    if not isinstance(artifact_identity, str) or not artifact_identity.strip():
        raise ValueError("artifact_identity must be non-empty")
    if not isinstance(source_width, int) or not isinstance(source_height, int) or source_width <= 0 or source_height <= 0:
        raise ValueError("source_width and source_height must be positive source-pixel integers")
    frozen_contract = dict(contract or load_contract())
    raw_hash = _image_hash(raw_image)
    layout_registry = LayoutProfileRegistry(frozen_contract)
    locator_registry = CellLocatorRegistry(frozen_contract)
    detection = layout_registry.detect(layout_profile_id, layout_regions)
    timestamps = _timestamps(source_timestamps)
    availability = {market: "AVAILABLE" for market in MARKETS}
    if market_availability:
        for market, state in market_availability.items():
            if market not in MARKETS or state not in {"AVAILABLE", "UNAVAILABLE", "UNKNOWN", "BLOCKED"}:
                raise ValueError(f"invalid market availability: {market}={state}")
            availability[market] = state
    implementation_hash = "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    config_hash = parser_config_hash(frozen_contract)
    records: list[dict[str, Any]] = []
    for market in MARKETS:
        for item in locator_registry.inventory(market):
            label = item["source_visible_label"]
            if detection.status == "MATCHED":
                locator = locator_registry.locate(layout_profile_id, market, label, source_width, source_height)
                region_coordinates = locator["region_coordinates"]
                cell_coordinates = locator["cell_coordinates"]
            else:
                locator = locator_registry.unsupported_locator(layout_profile_id, market, item)
                region_coordinates = None
                cell_coordinates = None
            item_evidence = _evidence_for(evidence, market, label)
            present = True
            if cell_presence:
                for key in ((market, label), f"{market}|{label}", f"{market}:{label}"):
                    if key in cell_presence:
                        present = bool(cell_presence[key])
                        break
            status = ParserStatus.UNSUPPORTED_LAYOUT
            parsed_value = None
            normalized_evidence = None
            reason = detection.reason
            contradiction = "NONE"
            if detection.status == "MATCHED":
                status, parsed_value, normalized_evidence, reason = parse_value(
                    market,
                    item["value_kind"],
                    item_evidence,
                    market_available=availability[market] == "AVAILABLE",
                    cell_present=present,
                )
                contradiction = normalized_evidence.get("contradiction_state", "NONE") if normalized_evidence else "NONE"
            record = {
                "trace_record_id": _trace_id(artifact_identity, raw_hash, market, label, item["ordering_index"], locator["locator_key"]),
                "artifact_identity": artifact_identity,
                "raw_image_sha256": raw_hash,
                "layout_profile_identity": f"{detection.profile_id}@{detection.profile_version}",
                "market": market,
                "source_visible_label": label,
                "canonical_outcome_label": item["canonical_outcome_label"],
                "ordering_index": item["ordering_index"],
                "deterministic_locator": locator,
                "region_coordinates": region_coordinates,
                "cell_coordinates": cell_coordinates,
                "implementation_identity": PARSER_IDENTITY,
                "implementation_version": PARSER_VERSION,
                "implementation_hash": implementation_hash,
                "parser_config_identity": frozen_contract["parser_contract"]["config_identity"],
                "parser_config_hash": config_hash,
                "ocr_evidence": normalized_evidence,
                "parsed_value": parsed_value,
                "parser_status": status.value,
                "parser_reason": reason,
                "contradiction_state": contradiction,
                "market_availability_status": availability[market],
                "source_timestamps": dict(timestamps),
                "trace_record_sha256": None,
            }
            record["trace_record_sha256"] = trace_record_hash(record)
            records.append(record)
    return FullTraceResult(raw_hash, detection.status, detection.reason, tuple(records))


def derive_unresolved_trace(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Mechanically retain governed unresolved statuses in the original trace order."""

    result = []
    for record in records:
        if record.get("parser_status") in UNRESOLVED_STATUSES:
            result.append(dict(record))
    return tuple(result)
