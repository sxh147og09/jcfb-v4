"""Reusable, no-write official screenshot cell extraction runtime for V4."""

from .contract import CONTRACT_IDENTITY, TRACE_SCHEMA_IDENTITY, load_contract, validate_contract
from .layout import CellLocatorRegistry, LayoutProfileRegistry, NormalizedRect, PixelRect
from .parser import PARSER_IDENTITY, PARSER_VERSION, ParserStatus, normalize_ocr_text
from .runtime import (
    FullTraceResult,
    build_full_trace,
    derive_unresolved_trace,
    trace_record_hash,
)

__all__ = [
    "CONTRACT_IDENTITY",
    "TRACE_SCHEMA_IDENTITY",
    "load_contract",
    "validate_contract",
    "CellLocatorRegistry",
    "LayoutProfileRegistry",
    "NormalizedRect",
    "PixelRect",
    "PARSER_IDENTITY",
    "PARSER_VERSION",
    "ParserStatus",
    "normalize_ocr_text",
    "FullTraceResult",
    "build_full_trace",
    "derive_unresolved_trace",
    "trace_record_hash",
]
