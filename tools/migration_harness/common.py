"""Deterministic, redaction-safe helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


V4_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION_ID_RE = re.compile(r"^migration@20260901\.00[1-9]$")
TARGET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
CREDENTIAL_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def is_v4_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(V4_HASH_RE.fullmatch(value))


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def strip_code_ticks(value: str) -> str:
    return value.strip().strip("`").strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def normalize_dependency(value: str) -> List[str]:
    text = strip_code_ticks(value).strip()
    if text.lower() in {"", "none", "[]"}:
        return []
    text = text.strip("[]")
    result: List[str] = []
    for raw in text.split(","):
        item = strip_code_ticks(raw).strip().strip("'\"")
        if not item:
            continue
        if re.fullmatch(r"000[1-9]", item):
            item = "migration@20260901." + item[1:]
        result.append(item)
    return result


def normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return [str(value)]


def list_from_catalog(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def object_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("qualified_name"):
            return str(value["qualified_name"])
        schema = value.get("schema")
        name = value.get("name") or value.get("object_name")
        if schema and name:
            return f"{schema}.{name}"
        if name:
            return str(name)
    return str(value)


def count_by_kind(catalog: Optional[Dict[str, Any]], kinds: Iterable[str]) -> Dict[str, int]:
    source = catalog or {}
    return {kind: len(list_from_catalog(source.get(kind))) for kind in kinds}


def safe_issue_message(message: str) -> str:
    """Keep failure text structural; never include a value from a secret field."""

    return message.replace("password", "credential").replace("token", "credential")
