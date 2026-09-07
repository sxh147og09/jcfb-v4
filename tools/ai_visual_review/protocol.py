"""Versioned, additive AI visual review protocol.

The protocol accepts observations from an actual visual provider.  It never
turns OCR, numeric plausibility, neighboring cells, or an absent provider into
a visual observation.  A missing provider therefore produces an explicit
escalation record rather than an accepted value.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "config" / "official_odds" / "ai_visual_review_contract.json"
AI_REVIEW_STATUSES = frozenset({
    "AI_CONFIRMED", "AI_CORRECTED", "AI_REVIEW_AMBIGUOUS", "CONFLICT",
    "HUMAN_ESCALATION_REQUIRED",
})
PASS_STATUSES = frozenset({"READABLE", "UNREADABLE", "AMBIGUOUS", "CONFLICT", "NOT_EXECUTED"})
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")


class ReviewProtocolError(ValueError):
    """A fail-closed review contract violation."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_hash(value: Mapping[str, Any], *, omit: str = "canonical_review_record_hash") -> str:
    body = dict(value)
    body.pop(omit, None)
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN":
        raise ReviewProtocolError("AI review contract is not FROZEN")
    required = {"AI_VISUAL_FROM_ORIGINAL_IMAGE", "AI_VISUAL_FROM_DETERMINISTIC_CROP", "HUMAN_VISUAL_FROM_ORIGINAL_IMAGE"}
    if not required.issubset(set(value.get("review_methods", []))):
        raise ReviewProtocolError("review method registry is incomplete")
    if value.get("protocol", {}).get("inference") != "FORBIDDEN":
        raise ReviewProtocolError("inference prohibition is missing")
    return value


@dataclass(frozen=True)
class VisualPassObservation:
    """A provider-supplied observation for exactly one governed cell."""

    pass_id: str
    review_method: str
    status: str
    value_text: Optional[str]
    label_text: Optional[str]
    evidence_hash: Optional[str]
    provider_identity: Optional[str]
    provider_version: Optional[str]
    provider_hash: Optional[str]
    reason: Optional[str] = None

    def validate(self, *, expected_method: str, expected_label: str) -> None:
        if self.review_method != expected_method:
            raise ReviewProtocolError(f"{self.pass_id}: wrong review method")
        if self.status not in PASS_STATUSES:
            raise ReviewProtocolError(f"{self.pass_id}: invalid pass status")
        if self.status == "READABLE" and self.label_text != expected_label:
            raise ReviewProtocolError(f"{self.pass_id}: readable observation must bind the exact cell label")
        if self.label_text is not None and self.label_text != expected_label:
            raise ReviewProtocolError(f"{self.pass_id}: cell label mapping conflict")
        if self.status == "READABLE":
            if not isinstance(self.value_text, str) or not NUMERIC_RE.fullmatch(self.value_text.strip()):
                raise ReviewProtocolError(f"{self.pass_id}: readable observation must carry a numeric source string")
            if not isinstance(self.evidence_hash, str) or not HASH_RE.fullmatch(self.evidence_hash):
                raise ReviewProtocolError(f"{self.pass_id}: readable observation must carry evidence hash")
            if not all(isinstance(item, str) and item.strip() for item in (self.provider_identity, self.provider_version, self.provider_hash)):
                raise ReviewProtocolError(f"{self.pass_id}: provider identity/version/hash are required")
        elif self.value_text is not None:
            raise ReviewProtocolError(f"{self.pass_id}: non-readable observation must not carry a value")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _numeric(value: Optional[str]) -> Optional[float]:
    return float(value.strip()) if isinstance(value, str) and NUMERIC_RE.fullmatch(value.strip()) else None


def _decision(item: Mapping[str, Any], pass_a: VisualPassObservation, pass_b: VisualPassObservation) -> tuple[str, Optional[float], str]:
    ocr = item.get("ocr_evidence", {})
    ocr_value = _numeric(ocr.get("normalized_ocr_text"))
    a_value = _numeric(pass_a.value_text)
    b_value = _numeric(pass_b.value_text)
    if pass_a.status == "CONFLICT" or pass_b.status == "CONFLICT":
        return "CONFLICT", None, "VISUAL_PROVIDER_CONFLICT"
    if pass_a.status == "AMBIGUOUS" or pass_b.status == "AMBIGUOUS":
        return "AI_REVIEW_AMBIGUOUS", None, "VISUAL_PASS_AMBIGUOUS"
    if pass_a.status != "READABLE" or pass_b.status != "READABLE":
        return "HUMAN_ESCALATION_REQUIRED", None, "SAFE_VISUAL_PASS_NOT_COMPLETE"
    if a_value is None or b_value is None or a_value != b_value:
        return "CONFLICT", None, "PASS_A_PASS_B_VALUE_CONFLICT"
    if ocr_value is not None:
        if a_value != ocr_value:
            return "CONFLICT", None, "OCR_VISUAL_VALUE_CONFLICT"
        return "AI_CONFIRMED", a_value, "PASS_A_PASS_B_OCR_EQUAL"
    if pass_a.label_text != item.get("cell_label") or pass_b.label_text != item.get("cell_label"):
        return "AI_REVIEW_AMBIGUOUS", None, "LABEL_VALUE_MAPPING_UNCERTAIN"
    return "AI_CONFIRMED", a_value, "PASS_A_PASS_B_EQUAL_OCR_EMPTY"


def build_review_record(
    item: Mapping[str, Any],
    *,
    pass_a: VisualPassObservation,
    pass_b: VisualPassObservation,
    contract: Optional[Mapping[str, Any]] = None,
    review_implementation_identity: str = "jcfb-v4-ai-visual-review-runtime",
    review_implementation_version: str = "1.0.0",
    review_implementation_hash: Optional[str] = None,
    reviewer_run_id: str = "UNSPECIFIED",
) -> dict[str, Any]:
    contract = dict(contract or load_contract())
    expected_a = "AI_VISUAL_FROM_DETERMINISTIC_CROP"
    expected_b = "AI_VISUAL_FROM_ORIGINAL_IMAGE"
    pass_a.validate(expected_method=expected_a, expected_label=str(item.get("cell_label", "")))
    pass_b.validate(expected_method=expected_b, expected_label=str(item.get("cell_label", "")))
    required_hashes = (item.get("raw_image_sha256"), item.get("prior_trace_record_sha256"), item.get("crop_evidence", {}).get("crop_hash"), item.get("crop_evidence", {}).get("evidence_record_sha256"))
    if any(not isinstance(value, str) or not HASH_RE.fullmatch(value) for value in required_hashes):
        raise ReviewProtocolError("source/evidence hash binding is incomplete")
    status, value, reason = _decision(item, pass_a, pass_b)
    implementation_hash = review_implementation_hash or "sha256:" + hashlib.sha256(b"jcfb-v4-ai-visual-review-runtime@1.0.0").hexdigest()
    record: dict[str, Any] = {
        "schema_version": contract["schema_version"],
        "review_contract_identity": contract["contract_identity"],
        "review_run_id": reviewer_run_id,
        "queue_item_id": item.get("queue_item_id"),
        "artifact_slot": item.get("artifact_slot"),
        "artifact_identity": item.get("artifact_identity"),
        "raw_image_sha256": item.get("raw_image_sha256"),
        "market": item.get("market"),
        "cell_label": item.get("cell_label"),
        "outcome_label": item.get("outcome_label"),
        "selected_profile_identity": item.get("selected_profile_identity"),
        "selected_profile_version": item.get("selected_profile_version"),
        "locator_identity": item.get("locator_identity"),
        "locator_version": item.get("locator_version"),
        "locator_hash": item.get("locator_hash"),
        "crop_evidence_hash": item.get("crop_evidence", {}).get("crop_hash"),
        "ocr_evidence_id": item.get("crop_evidence", {}).get("evidence_record_id"),
        "ocr_evidence_hash": item.get("crop_evidence", {}).get("evidence_record_sha256"),
        "prior_trace_id": item.get("prior_trace_record_id"),
        "prior_trace_hash": item.get("prior_trace_record_sha256"),
        "prior_parser_status": item.get("prior_parser_status"),
        "pass_a": pass_a.as_dict(),
        "pass_b": pass_b.as_dict(),
        "cross_check_decision": {"status": status, "reason": reason, "ocr_value_used": _numeric(item.get("ocr_evidence", {}).get("normalized_ocr_text")) is not None},
        "review_status": status,
        "review_value": value,
        "review_implementation_identity": review_implementation_identity,
        "review_implementation_version": review_implementation_version,
        "review_implementation_hash": implementation_hash,
        "source_timestamps": dict(item.get("source_timestamps", {})),
    }
    record["canonical_review_record_hash"] = canonical_hash(record)
    return record
