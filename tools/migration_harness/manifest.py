"""Deterministic text-only manifest and SQL-header loader.

The Markdown manifest is authoritative.  The JSON fixture is deliberately not
used as a source of truth.  SQL is read as text and is never passed to a
database or shell.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .common import (
    MIGRATION_ID_RE,
    is_v4_hash,
    normalize_dependency,
    sha256_json,
    strip_code_ticks,
)
from .models import Issue, ManifestEntry, ManifestLoadResult


EXPECTED_SEQUENCES = [f"000{i}" for i in range(1, 10)]
EXPECTED_SCHEMA_CONTRACT = "v4-database-schema@1.0.0"
MANIFEST_RELATIVE_PATH = "database/migrations/v4/0000_manifest.md"
SQL_DIRECTORY_RELATIVE_PATH = "database/migrations/v4"
SQL_HEADER_KEYS = (
    "migration_id",
    "sequence",
    "name",
    "migration_version",
    "depends_on",
    "schema_contract_version",
    "authored_at",
    "migration_hash",
    "status",
)


def _manifest_rows(text: str) -> List[Tuple[int, List[str]]]:
    rows: List[Tuple[int, List[str]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^\|\s*000[1-9]\s*\|", line):
            cells = [cell.strip() for cell in line.strip().split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            rows.append((line_number, cells))
    return rows


def _parse_id_version(cell: str) -> Tuple[str, str]:
    value = strip_code_ticks(cell)
    if "/" in value:
        left, right = [strip_code_ticks(part) for part in value.split("/", 1)]
        return left, right
    return value, value


def parse_manifest_text(text: str) -> Tuple[List[ManifestEntry], List[Issue]]:
    entries: List[ManifestEntry] = []
    issues: List[Issue] = []
    for line_number, cells in _manifest_rows(text):
        if len(cells) < 7:
            issues.append(Issue("MANIFEST_ROW_MALFORMED", "Manifest row has fewer than seven semantic cells", f"line:{line_number}"))
            continue
        sequence = strip_code_ticks(cells[0])
        file_name = strip_code_ticks(cells[1])
        file_path = file_name if file_name.startswith("database/") else f"{SQL_DIRECTORY_RELATIVE_PATH}/{file_name}"
        migration_id, migration_version = _parse_id_version(cells[2])
        name = strip_code_ticks(cells[3])
        depends_on = normalize_dependency(cells[4])
        expected_text = strip_code_ticks(cells[5])
        expected_objects = [expected_text] if expected_text else []
        status = strip_code_ticks(cells[-1])
        entries.append(
            ManifestEntry(
                sequence=sequence,
                file=file_path,
                migration_id=migration_id,
                migration_version=migration_version,
                name=name,
                depends_on=depends_on,
                schema_contract_version=EXPECTED_SCHEMA_CONTRACT,
                authored_at="",
                migration_hash="",
                status=status,
                expected_objects=expected_objects,
            )
        )
    if not entries:
        issues.append(Issue("MANIFEST_ROWS_MISSING", "No numbered migration rows were found"))
    return entries, issues


def parse_sql_headers(sql_text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for key in SQL_HEADER_KEYS:
        match = re.search(rf"(?m)^--\s*{re.escape(key)}:\s*(.+?)\s*$", sql_text)
        if match:
            values[key] = match.group(1).strip()
    return values


def _copy_with_sql_metadata(entry: ManifestEntry, headers: Dict[str, str]) -> ManifestEntry:
    return ManifestEntry(
        sequence=entry.sequence,
        file=entry.file,
        migration_id=entry.migration_id,
        migration_version=entry.migration_version,
        name=entry.name,
        depends_on=list(entry.depends_on),
        schema_contract_version=headers.get("schema_contract_version", entry.schema_contract_version),
        authored_at=headers.get("authored_at", entry.authored_at),
        migration_hash=headers.get("migration_hash", entry.migration_hash),
        status=headers.get("status", entry.status),
        expected_objects=list(entry.expected_objects),
    )


def _validate_unique(entries: Sequence[ManifestEntry], issues: List[Issue]) -> None:
    fields = (
        ("sequence", "MANIFEST_DUPLICATE_SEQUENCE"),
        ("file", "MANIFEST_DUPLICATE_FILE"),
        ("migration_id", "MANIFEST_DUPLICATE_ID"),
        ("migration_version", "MANIFEST_DUPLICATE_VERSION"),
        ("name", "MANIFEST_DUPLICATE_NAME"),
    )
    for field_name, code in fields:
        values = [str(getattr(entry, field_name)) for entry in entries]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            issues.append(Issue(code, f"Duplicate manifest {field_name}: {', '.join(duplicates)}"))


def _validate_graph(entries: Sequence[ManifestEntry], issues: List[Issue]) -> None:
    if [entry.sequence for entry in entries] != EXPECTED_SEQUENCES:
        issues.append(Issue("DEPENDENCY_SEQUENCE_INVALID", "Manifest must contain exactly 0001 through 0009 in order"))
    by_id = {entry.migration_id: entry for entry in entries}
    for index, entry in enumerate(entries):
        if index == 0:
            expected: List[str] = []
        else:
            expected = [entries[index - 1].migration_id]
        if entry.depends_on != expected:
            issues.append(
                Issue(
                    "DEPENDENCY_PREDECESSOR_INVALID",
                    f"{entry.sequence} depends_on does not equal the exact predecessor",
                    entry.file,
                )
            )
        for parent in entry.depends_on:
            if parent not in by_id:
                issues.append(Issue("DEPENDENCY_PARENT_MISSING", f"{entry.sequence} references a missing parent", entry.file))
            elif by_id[parent].sequence >= entry.sequence:
                issues.append(Issue("DEPENDENCY_FORWARD_REFERENCE", f"{entry.sequence} references a non-predecessor", entry.file))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            issues.append(Issue("DEPENDENCY_CYCLE", "Migration dependency graph contains a cycle"))
            return
        if node in visited or node not in by_id:
            return
        visiting.add(node)
        for parent in by_id[node].depends_on:
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for entry in entries:
        visit(entry.migration_id)


def _validate_identity(entries: Sequence[ManifestEntry], issues: List[Issue]) -> None:
    for entry in entries:
        if not re.fullmatch(r"000[1-9]", entry.sequence):
            issues.append(Issue("MANIFEST_SEQUENCE_INVALID", "Sequence must be four digits from 0001 through 0009", entry.file))
        expected_id = f"migration@20260901.{entry.sequence[1:]}" if re.fullmatch(r"000[1-9]", entry.sequence) else ""
        if not MIGRATION_ID_RE.fullmatch(entry.migration_id) or entry.migration_id != expected_id:
            issues.append(Issue("MANIFEST_ID_INVALID", f"Migration identity is invalid for {entry.sequence}", entry.file))
        if entry.migration_version != entry.migration_id:
            issues.append(Issue("MANIFEST_VERSION_INVALID", "Migration version must equal migration_id in this design", entry.file))
        if not re.fullmatch(r"v4-[a-z0-9]+(?:-[a-z0-9]+)*", entry.name):
            issues.append(Issue("MANIFEST_NAME_INVALID", "Migration name is not lower-kebab", entry.file))
        if entry.schema_contract_version != EXPECTED_SCHEMA_CONTRACT:
            issues.append(Issue("MANIFEST_SCHEMA_CONTRACT_INVALID", "Schema contract version is not the approved V4 contract", entry.file))
        if not entry.authored_at:
            issues.append(Issue("MANIFEST_AUTHORED_AT_MISSING", "authored_at is missing", entry.file))
        if not entry.migration_hash:
            issues.append(Issue("HASH_METADATA_MISSING", "migration_hash is missing", entry.file))
        elif entry.migration_hash != "PENDING_CANONICAL_HASH" and not is_v4_hash(entry.migration_hash):
            issues.append(Issue("HASH_FORMAT_INVALID", "migration_hash is neither pending nor a canonical SHA-256", entry.file))
        if entry.status not in {"DRAFT", "APPROVED_FOR_DEPLOYMENT", "APPLIED", "FAILED", "SUPERSEDED"}:
            issues.append(Issue("MANIFEST_STATUS_INVALID", "Migration lifecycle status is invalid", entry.file))


def _validate_sql_safety(entry: ManifestEntry, sql_text: str, headers: Dict[str, str], issues: List[Issue]) -> None:
    if not sql_text.startswith("-- DESIGN ONLY - DO NOT APPLY"):
        issues.append(Issue("SQL_SAFETY_MARKER_MISSING", "SQL source is missing the design-only safety marker", entry.file))
    forbidden_patterns = (
        r"(?im)^\s*\\connect\b",
        r"(?im)^\s*\\(?:i|ir|include|copy|gexec)\b",
        r"(?im)^\s*supabase\s+(?:db\s+)?(?:push|query|reset)\b",
        r"(?im)\bapply_migration\b",
        r"(?is)\bDROP\s+.*?\bCASCADE\b",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, sql_text):
            issues.append(Issue("SQL_EXECUTION_PATH_PRESENT", "SQL source contains a forbidden execution or destructive directive", entry.file))
            break
    for key in SQL_HEADER_KEYS:
        if key not in headers:
            issues.append(Issue("SQL_METADATA_MISSING", f"SQL header is missing {key}", entry.file))
    expected_values = {
        "migration_id": entry.migration_id,
        "sequence": entry.sequence,
        "name": entry.name,
        "migration_version": entry.migration_version,
        "depends_on": "[]" if not entry.depends_on else "[" + ",".join(entry.depends_on) + "]",
        "schema_contract_version": entry.schema_contract_version,
        "authored_at": entry.authored_at,
        "migration_hash": entry.migration_hash,
        "status": entry.status,
    }
    for key, expected in expected_values.items():
        actual = headers.get(key)
        if actual is not None and actual != expected:
            issues.append(Issue("SQL_METADATA_MISMATCH", f"SQL header {key} does not match the Markdown manifest", entry.file))


def validate_manifest(
    manifest_text: str,
    sql_texts: Optional[Dict[str, str]] = None,
    *,
    source_manifest: str = MANIFEST_RELATIVE_PATH,
) -> ManifestLoadResult:
    raw_entries, issues = parse_manifest_text(manifest_text)
    _validate_unique(raw_entries, issues)
    _validate_graph(raw_entries, issues)

    entries: List[ManifestEntry] = []
    for raw_entry in raw_entries:
        sql_text = (sql_texts or {}).get(raw_entry.file)
        if sql_text is None:
            issues.append(Issue("SQL_SOURCE_MISSING", "Numbered SQL source is missing", raw_entry.file))
            entries.append(raw_entry)
            continue
        headers = parse_sql_headers(sql_text)
        enriched = _copy_with_sql_metadata(raw_entry, headers)
        entries.append(enriched)
        _validate_sql_safety(enriched, sql_text, headers, issues)

    _validate_identity(entries, issues)

    # A source manifest with fewer/more than nine rows is always invalid even
    # when a malformed duplicate happens to make the sequence look ordered.
    if len(entries) != 9:
        issues.append(Issue("MANIFEST_ENTRY_COUNT_INVALID", "Exactly nine migrations are required"))
    return ManifestLoadResult(
        entries=entries,
        issues=issues,
        source_manifest=source_manifest,
        source_sql_directory=SQL_DIRECTORY_RELATIVE_PATH,
    )


def load_manifest(repo_root: Path) -> ManifestLoadResult:
    manifest_path = repo_root / Path(MANIFEST_RELATIVE_PATH)
    if not manifest_path.is_file():
        return ManifestLoadResult(
            entries=[],
            issues=[Issue("MANIFEST_SOURCE_MISSING", "Authoritative Markdown manifest is missing", MANIFEST_RELATIVE_PATH)],
            source_manifest=MANIFEST_RELATIVE_PATH,
            source_sql_directory=SQL_DIRECTORY_RELATIVE_PATH,
        )
    manifest_text = manifest_path.read_text(encoding="utf-8")
    sql_texts: Dict[str, str] = {}
    for sequence in EXPECTED_SEQUENCES:
        matches = list((repo_root / Path(SQL_DIRECTORY_RELATIVE_PATH)).glob(f"{sequence}_*.sql"))
        if len(matches) == 1:
            sql_texts[f"{SQL_DIRECTORY_RELATIVE_PATH}/{matches[0].name}"] = matches[0].read_text(encoding="utf-8")
    return validate_manifest(manifest_text, sql_texts)


def manifest_identity_hash(result: ManifestLoadResult) -> str:
    """Hash metadata only; this is not an approved migration hash."""

    payload = {
        "source_manifest": result.source_manifest,
        "source_sql_directory": result.source_sql_directory,
        "entries": [
            {
                key: getattr(entry, key)
                for key in (
                    "sequence",
                    "file",
                    "migration_id",
                    "migration_version",
                    "name",
                    "depends_on",
                    "schema_contract_version",
                    "authored_at",
                    "migration_hash",
                    "status",
                )
            }
            for entry in result.entries
        ],
    }
    return sha256_json(payload)


def validate_history_integrity(
    history_rows: Iterable[Dict[str, object]],
    manifest: ManifestLoadResult,
) -> Tuple[bool, List[Issue]]:
    """Validate supplied history evidence without opening a database."""

    issues: List[Issue] = []
    by_id = {entry.migration_id: entry for entry in manifest.entries}
    seen: set[str] = set()
    for row in history_rows:
        migration_id = str(row.get("migration_id", ""))
        if migration_id in seen:
            issues.append(Issue("HISTORY_DUPLICATE_ID", "Migration history contains more than one terminal row", migration_id))
        seen.add(migration_id)
        entry = by_id.get(migration_id)
        if entry is None:
            issues.append(Issue("HISTORY_UNKNOWN_ID", "Migration history references an unknown identity", migration_id))
            continue
        history_hash = row.get("migration_hash")
        if history_hash != entry.migration_hash:
            issues.append(Issue("HISTORY_HASH_MISMATCH", "Migration history hash differs from the immutable manifest identity", migration_id))
        if row.get("status") == "APPLIED" and not is_v4_hash(history_hash):
            issues.append(Issue("HISTORY_PENDING_HASH_APPLIED", "A pending/non-canonical hash cannot be recorded as APPLIED", migration_id))
        if row.get("partial_applied") is True or row.get("status") in {"PARTIAL", "PARTIAL_FAIL"}:
            issues.append(Issue("HISTORY_PARTIAL_APPLIED", "Partial migration state must be retained and blocked", migration_id))
    return not issues, issues
