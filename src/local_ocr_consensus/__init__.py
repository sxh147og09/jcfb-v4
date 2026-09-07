"""Additive local OCR consensus runtime for unresolved official-odds cells.

The runtime is deliberately conservative: multiple preprocessing passes through
one Tesseract binary are evidence enrichment only.  Automatic confirmation is
permitted only when two distinct engine identities are available and agree on
the same valid numeric value.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import uuid
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


CONTRACT_IDENTITY = "official-odds-local-ocr-consensus@1.0.0"
SCHEMA_IDENTITY = "official-odds-local-ocr-consensus-record@1.0.0"
STATUS_CONFIRMED = "OCR_CONSENSUS_CONFIRMED"
STATUS_AMBIGUOUS = "OCR_CONSENSUS_AMBIGUOUS"
STATUS_CONFLICT = "OCR_CONSENSUS_CONFLICT"
STATUS_UNRESOLVED = "OCR_UNRESOLVED"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
NUMERIC_RE = re.compile(r"^(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,4})?$")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def normalize_numeric(raw: str) -> str | None:
    """Normalize only unambiguous OCR formatting; never infer from neighbors."""
    if not isinstance(raw, str):
        return None
    value = raw.strip().replace("\r", "").replace("\n", "").replace(" ", "").replace(",", ".")
    if value.count(".") > 1:
        return None
    if not NUMERIC_RE.fullmatch(value):
        return None
    try:
        if float(value) <= 0 or float(value) > 9999:
            return None
    except ValueError:
        return None
    return value


def discover_engines() -> list[dict[str, Any]]:
    """Discover locally usable OCR engines without installing dependencies."""
    candidates: list[tuple[str, str | None, str]] = [
        ("tesseract", shutil.which("tesseract"), "PATH"),
        ("tesseract", r"C:\Program Files\Tesseract-OCR\tesseract.exe", "COMMON_WINDOWS_PATH"),
        ("tesseract", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe", "COMMON_WINDOWS_PATH"),
    ]
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for identity, candidate, discovery in candidates:
        if not candidate:
            continue
        path = str(Path(candidate).resolve())
        if path in seen or not Path(path).is_file():
            continue
        seen.add(path)
        try:
            completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
            version = (completed.stdout or completed.stderr).splitlines()[0].strip()
            results.append({
                "engine_identity": identity,
                "engine_path": path,
                "engine_version": version,
                "available": completed.returncode == 0,
                "discovery": discovery,
            })
        except (OSError, subprocess.SubprocessError) as exc:
            results.append({
                "engine_identity": identity,
                "engine_path": path,
                "engine_version": "UNKNOWN",
                "available": False,
                "discovery": discovery,
                "error": type(exc).__name__,
            })
    unavailable = [
        ("easyocr", "python package not installed"),
        ("paddleocr", "python package not installed"),
        ("windows-ocr", "Windows OCR binding not installed"),
    ]
    for identity, reason in unavailable:
        results.append({"engine_identity": identity, "available": False, "reason": reason})
    return results


def _read_png(path: Path) -> tuple[int, int, list[list[int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    offset = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or compression != 0 or filtering != 0 or interlace != 0:
                raise ValueError("only non-interlaced 8-bit PNGs are supported")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None or color_type is None:
        raise ValueError("PNG header missing")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"unsupported PNG color type: {color_type}")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows: list[list[int]] = []
    prior = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        current = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        for i in range(stride):
            left = current[i - channels] if i >= channels else 0
            up = prior[i]
            up_left = prior[i - channels] if i >= channels else 0
            if filter_type == 1:
                current[i] = (current[i] + left) & 255
            elif filter_type == 2:
                current[i] = (current[i] + up) & 255
            elif filter_type == 3:
                current[i] = (current[i] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                estimate = left + up - up_left
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
                predictor = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
                current[i] = (current[i] + predictor) & 255
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter: {filter_type}")
        if color_type == 0:
            gray = list(current)
        elif color_type == 2:
            gray = [int(0.299 * current[i] + 0.587 * current[i + 1] + 0.114 * current[i + 2]) for i in range(0, stride, 3)]
        elif color_type == 4:
            gray = list(current[0::2])
        else:
            gray = [int(0.299 * current[i] + 0.587 * current[i + 1] + 0.114 * current[i + 2]) for i in range(0, stride, 4)]
        rows.append(gray)
        prior = current
    return width, height, rows


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _write_png(path: Path, width: int, height: int, rows: list[list[int]]) -> None:
    raw = b"".join(b"\x00" + bytes(max(0, min(255, value)) for value in row) for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def _resize(rows: list[list[int]], factor: int) -> tuple[int, int, list[list[int]]]:
    height, width = len(rows), len(rows[0]) if rows else 0
    return width * factor, height * factor, [[rows[y // factor][x // factor] for x in range(width * factor)] for y in range(height * factor)]


def _contrast(rows: list[list[int]]) -> list[list[int]]:
    values = [value for row in rows for value in row]
    if not values:
        return rows
    low, high = min(values), max(values)
    if high <= low:
        return rows
    return [[round((value - low) * 255 / (high - low)) for value in row] for row in rows]


def _adaptive_threshold(rows: list[list[int]], radius: int = 3, bias: int = 7) -> list[list[int]]:
    height, width = len(rows), len(rows[0]) if rows else 0
    integral = [[0] * (width + 1) for _ in range(height + 1)]
    for y in range(height):
        row_sum = 0
        for x in range(width):
            row_sum += rows[y][x]
            integral[y + 1][x + 1] = integral[y][x + 1] + row_sum
    output: list[list[int]] = []
    for y in range(height):
        line: list[int] = []
        for x in range(width):
            top, left = max(0, y - radius), max(0, x - radius)
            bottom, right = min(height, y + radius + 1), min(width, x + radius + 1)
            total = integral[bottom][right] - integral[top][right] - integral[bottom][left] + integral[top][left]
            area = (bottom - top) * (right - left)
            line.append(255 if rows[y][x] >= (total / area - bias) else 0)
        output.append(line)
    return output


def _sharpen(rows: list[list[int]]) -> list[list[int]]:
    height, width = len(rows), len(rows[0]) if rows else 0
    output = [row[:] for row in rows]
    kernel = ((0, -1, 0), (-1, 5, -1), (0, -1, 0))
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            value = sum(kernel[dy + 1][dx + 1] * rows[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
            output[y][x] = max(0, min(255, value))
    return output


def render_preprocessed(source: Path, target: Path, transform: str) -> str:
    width, height, rows = _read_png(source)
    if transform == "original":
        processed = rows
        out_width, out_height = width, height
    else:
        factor = 4 if "4x" in transform else 2
        out_width, out_height, processed = _resize(rows, factor)
        if "contrast" in transform:
            processed = _contrast(processed)
        if "threshold" in transform:
            processed = _adaptive_threshold(processed)
        if "sharpen" in transform:
            processed = _sharpen(processed)
    _write_png(target, out_width, out_height, processed)
    return sha256_file(target)


PREPROCESSING_PASSES = (
    {"pass_id": "ORIGINAL_PSM7", "transform": "original", "psm": "7"},
    {"pass_id": "GRAY_2X_PSM7", "transform": "gray_2x", "psm": "7"},
    {"pass_id": "GRAY_4X_PSM7", "transform": "gray_4x", "psm": "7"},
    {"pass_id": "CONTRAST_4X_PSM7", "transform": "contrast_4x", "psm": "7"},
    {"pass_id": "THRESHOLD_2X_PSM7", "transform": "threshold_2x", "psm": "7"},
    {"pass_id": "THRESHOLD_4X_PSM7", "transform": "threshold_4x", "psm": "7"},
    {"pass_id": "SHARPEN_4X_PSM7", "transform": "sharpen_4x", "psm": "7"},
    {"pass_id": "THRESHOLD_4X_PSM13", "transform": "threshold_4x", "psm": "13"},
)


def preprocessing_config_hash() -> str:
    return sha256_json({"passes": PREPROCESSING_PASSES, "implementation": "local-ocr-png-pipeline@1.0.0"})


def run_tesseract(binary: str, image: Path, psm: str) -> tuple[str, str]:
    args = [binary, str(image), "stdout", "--oem", "1", "--psm", psm, "-c", "tessedit_char_whitelist=0123456789.,"]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    return (completed.stdout or "").strip(), (completed.stderr or "").strip()


def stable_trace_id(review_item_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{CONTRACT_IDENTITY}:{review_item_id}"))


def consensus_from_runs(runs: Iterable[Mapping[str, Any]], *, engine_count: int) -> dict[str, Any]:
    normalized = [run.get("normalized_value") for run in runs if run.get("normalized_value") is not None]
    counts = Counter(normalized)
    distinct = sorted(counts)
    if not distinct:
        return {"status": STATUS_UNRESOLVED, "value": None, "reason": "NO_LEGAL_NUMERIC_OCR_OUTPUT", "distinct_values": []}
    if len(distinct) > 1:
        return {"status": STATUS_CONFLICT, "value": None, "reason": "LEGAL_NUMERIC_OUTPUTS_CONFLICT", "distinct_values": distinct, "counts": dict(counts)}
    value = distinct[0]
    if engine_count >= 2:
        return {"status": STATUS_CONFIRMED, "value": value, "reason": "TWO_DISTINCT_ENGINE_IDENTITIES_AGREE", "distinct_values": distinct, "counts": dict(counts)}
    return {"status": STATUS_AMBIGUOUS, "value": value, "reason": "SINGLE_ENGINE_MULTI_PASS_ONLY_AUTO_CONFIRM_DISABLED", "distinct_values": distinct, "counts": dict(counts)}


def record_hash(record: Mapping[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "consensus_record_sha256"}
    return sha256_json(body)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> str:
    payload = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    path.write_bytes(payload)
    return sha256_bytes(payload)


__all__ = [
    "CONTRACT_IDENTITY", "NUMERIC_RE", "PREPROCESSING_PASSES", "SCHEMA_IDENTITY", "STATUS_AMBIGUOUS",
    "STATUS_CONFIRMED", "STATUS_CONFLICT", "STATUS_UNRESOLVED", "canonical_bytes", "consensus_from_runs",
    "discover_engines", "load_jsonl", "normalize_numeric", "preprocessing_config_hash", "record_hash",
    "render_preprocessed", "run_tesseract", "sha256_bytes", "sha256_file", "sha256_json", "stable_trace_id",
    "write_jsonl",
]
