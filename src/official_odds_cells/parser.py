"""Deterministic value parser over caller-provided OCR evidence."""

from __future__ import annotations

import math
import re
import unicodedata
from enum import Enum
from typing import Any, Mapping, Optional


PARSER_IDENTITY = "official-odds-cell-parser"
PARSER_VERSION = "1.0.0"
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")


class ParserStatus(str, Enum):
    PARSED = "PARSED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_PRESENT = "NOT_PRESENT"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    CONFLICT = "CONFLICT"
    UNSUPPORTED_LAYOUT = "UNSUPPORTED_LAYOUT"


def normalize_ocr_text(raw_text: Any) -> Optional[str]:
    if raw_text is None:
        return None
    if not isinstance(raw_text, str):
        raise ValueError("OCR raw_text must be a string or null")
    normalized = unicodedata.normalize("NFKC", raw_text).replace("，", ",").strip()
    return normalized or None


def normalize_evidence(raw: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("OCR evidence must be an object")
    raw_text = raw.get("raw_text")
    normalized = normalize_ocr_text(raw_text)
    supplied_normalized = raw.get("normalized_text")
    if supplied_normalized is not None and supplied_normalized != normalized:
        raise ValueError("normalized_text does not match deterministic OCR normalization")
    contradiction = raw.get("contradiction_state", "NONE")
    if contradiction not in {"NONE", "CONFLICTED", "NOT_APPLICABLE"}:
        raise ValueError("invalid OCR contradiction_state")
    candidate_values = raw.get("candidate_values", [])
    if not isinstance(candidate_values, list):
        raise ValueError("candidate_values must be a list")
    result = {
        "engine_identity": str(raw.get("engine_identity", "ADAPTER_INPUT_ONLY")),
        "engine_version": str(raw.get("engine_version", "UNKNOWN")),
        "config_hash": str(raw.get("config_hash", "UNKNOWN")),
        "raw_text": raw_text,
        "normalized_text": normalized,
        "confidence": raw.get("confidence"),
        "candidate_values": list(candidate_values),
        "contradiction_state": contradiction,
    }
    if "evidence_ref" in raw:
        result["evidence_ref"] = raw["evidence_ref"]
    return result


def parse_value(market: str, value_kind: str, evidence: Optional[Mapping[str, Any]], *, market_available: bool, cell_present: bool) -> tuple[ParserStatus, Optional[float], Optional[dict[str, Any]], str]:
    normalized = normalize_evidence(evidence)
    if not market_available:
        return ParserStatus.MARKET_UNAVAILABLE, None, normalized, "MARKET_NOT_AVAILABLE_IN_SOURCE"
    if not cell_present:
        return ParserStatus.NOT_PRESENT, None, normalized, "CELL_NOT_PRESENT_IN_SOURCE"
    if normalized is not None and normalized["contradiction_state"] == "CONFLICTED":
        return ParserStatus.CONFLICT, None, normalized, "OCR_EVIDENCE_CONFLICTED"
    if normalized is None or normalized["normalized_text"] is None:
        return ParserStatus.UNRESOLVED, None, normalized, "OCR_VALUE_UNREADABLE"
    candidates = normalized["candidate_values"]
    if len(candidates) > 1 and len({str(candidate) for candidate in candidates}) > 1:
        return ParserStatus.AMBIGUOUS, None, normalized, "OCR_CANDIDATE_VALUES_AMBIGUOUS"
    text = normalized["normalized_text"]
    if not _NUMBER_RE.fullmatch(text):
        return ParserStatus.UNRESOLVED, None, normalized, "OCR_VALUE_NOT_NUMERIC"
    try:
        value = float(text)
    except ValueError:
        return ParserStatus.UNRESOLVED, None, normalized, "OCR_VALUE_NOT_NUMERIC"
    if not math.isfinite(value) or (value <= 0 and value_kind == "ODDS"):
        return ParserStatus.UNRESOLVED, None, normalized, "OCR_VALUE_OUT_OF_RANGE"
    return ParserStatus.PARSED, value, normalized, "DETERMINISTIC_NUMERIC_PARSE"
