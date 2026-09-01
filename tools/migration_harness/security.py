"""Repository secret scan with redacted evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import CheckStatus


TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".ps1",
    ".py",
    ".js",
    ".ts",
    ".sql",
    ".env",
    ".example",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password|service[_-]?role[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9./+=_-]{20,}"),
    re.compile(r"(?i)postgres(?:ql)?://[^\s\"']+"),
)


def _candidate_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.name == ".env.example" or path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def secret_scan(repo_root: Path) -> Dict[str, Any]:
    hits: List[str] = []
    scanned = 0
    for path in _candidate_files(repo_root):
        scanned += 1
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            # Only the relative filename is retained.  Values and matching
            # lines are intentionally never emitted.
            hits.append(path.relative_to(repo_root).as_posix())
    return {
        "status": CheckStatus.PASS.value if not hits else CheckStatus.FAIL.value,
        "files_scanned": scanned,
        "hit_count": len(hits),
        "hit_files": hits,
        "values_logged": False,
        "reason": "No high-signal credential material found" if not hits else "Credential-like material found; values withheld",
    }
