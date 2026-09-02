"""Canonical hashing and verification for the V4 runtime candidates.

The design migrations under ``database/migrations/v4`` remain untouched.  This
module operates only on ``v4_runtime_candidate`` and treats the JSON candidate
manifest as the machine-readable source of truth.

The SQL hash is deliberately self-reference safe.  The two header hash fields
and the current migration's 0009 registry-seed hash are replaced with a fixed
placeholder only while calculating the digest.  The verifier separately checks
that those fields contain the manifest hash, so changing them still fails
verification.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .common import canonical_json, is_v4_hash, normalize_dependency


CANDIDATE_MANIFEST_RELATIVE = "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json"
CANDIDATE_MARKDOWN_RELATIVE = "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md"
CANDIDATE_DIRECTORY_RELATIVE = "database/migrations/v4_runtime_candidate"
EXPECTED_CANDIDATE_COUNT = 9
PENDING_CANONICAL_HASH = "PENDING_CANONICAL_HASH"
HASH_ALGORITHM = "SHA-256"
HASH_PROFILE = "v4-canonical-json@1.0"
CANONICALIZATION_VERSION = "v4-canonical-migration@1.0.0"
SELF_HASH_PLACEHOLDER = "<SELF_HASH>"
EXPECTED_SCHEMA_CONTRACT = "v4-database-schema@1.0.0"
EXPECTED_SEQUENCES = tuple(range(1, EXPECTED_CANDIDATE_COUNT + 1))
STABLE_METADATA_FIELDS = (
    "migration_id",
    "sequence",
    "name",
    "migration_version",
    "depends_on",
    "schema_contract_version",
    "authored_at",
    "file",
)
VOLATILE_METADATA_FIELDS = (
    "applied_at",
    "applied_by",
    "execution_duration",
    "deployment_host",
    "status",
)

_HASH_VALUE = rf"(?:{re.escape(PENDING_CANONICAL_HASH)}|sha256:[0-9a-f]{{64}})"
_HASH_HEADER_RE = re.compile(
    rf"^(?P<prefix>--\s+(?P<key>canonical_migration_hash|migration_hash):\s+)(?P<value>{_HASH_VALUE})\s*$",
    re.IGNORECASE,
)
_SEED_HASH_RE = re.compile(
    rf"(?P<prefix>\(\s*'(?P<migration_id>migration@20260901\.\d{{3}})'\s*,\s*\d+.*?,\s*'{re.escape(EXPECTED_SCHEMA_CONTRACT)}'\s*,\s*'[^']+'\s*,\s*')"
    rf"(?P<value>{_HASH_VALUE})"
    rf"(?P<suffix>'\s*,\s*'DRAFT'\s*,)",
    re.IGNORECASE,
)


class CanonicalHashError(ValueError):
    """Raised when a candidate cannot be canonicalized fail-closed."""


def _issue(code: str, message: str, location: Optional[str] = None) -> Dict[str, str]:
    value = {"code": code, "message": message}
    if location:
        value["location"] = location
    return value


def load_candidate_manifest(repo_root: Path, manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    path = manifest_path or (repo_root / CANDIDATE_MANIFEST_RELATIVE)
    if not path.is_file():
        raise CanonicalHashError(f"Candidate manifest is missing: {path.as_posix()}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalHashError("Candidate manifest could not be parsed") from exc
    if not isinstance(value, dict):
        raise CanonicalHashError("Candidate manifest root must be an object")
    return value


def _required_string(entry: Mapping[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CanonicalHashError(f"Candidate metadata is missing {key}")
    return value


def canonical_metadata(entry: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the exact stable metadata envelope included in a migration hash."""

    sequence = entry.get("sequence")
    if not isinstance(sequence, int) or sequence < 1:
        raise CanonicalHashError("Candidate sequence must be a positive integer")
    depends_on = entry.get("depends_on")
    if not isinstance(depends_on, list) or any(not isinstance(item, str) or not item for item in depends_on):
        raise CanonicalHashError("Candidate depends_on must be a list of non-empty migration IDs")
    candidate_file = _required_string(entry, "candidate_file").replace("\\", "/")
    metadata = {
        "migration_id": _required_string(entry, "migration_id"),
        "sequence": f"{sequence:04d}",
        "name": _required_string(entry, "name"),
        "migration_version": _required_string(entry, "migration_version"),
        "depends_on": list(depends_on),
        "schema_contract_version": _required_string(entry, "schema_contract_version"),
        "authored_at": _required_string(entry, "authored_at"),
        "file": candidate_file,
    }
    return metadata


def _normalize_self_references(sql_text: str, migration_id: Optional[str]) -> str:
    lines = sql_text.split("\n")
    normalized: List[str] = []
    for line in lines:
        header = _HASH_HEADER_RE.fullmatch(line)
        if header:
            line = f"{header.group('prefix')}{SELF_HASH_PLACEHOLDER}"
        if migration_id:
            line = _SEED_HASH_RE.sub(
                lambda match: f"{match.group('prefix')}{SELF_HASH_PLACEHOLDER}{match.group('suffix')}"
                if match.group("migration_id") == migration_id
                else match.group(0),
                line,
            )
        normalized.append(line.rstrip(" \t"))

    # The profile has exactly one LF terminator.  Trailing blank lines are
    # terminator formatting, not SQL semantics; blank lines inside the file
    # remain unchanged.
    while normalized and normalized[-1] == "":
        normalized.pop()
    return "\n".join(normalized) + "\n"


def canonicalize_sql_text(sql_text: str, *, migration_id: Optional[str] = None) -> bytes:
    """Canonicalize SQL without parsing or rewriting SQL semantics.

    UTF-8 BOM is removed, CRLF/CR becomes LF, horizontal trailing whitespace
    is removed per line, the self-hash references are normalized, and exactly
    one final LF is emitted.  SQL tokens, comments, internal whitespace,
    statement order, and dollar-quoted bodies are otherwise preserved.
    """

    if not isinstance(sql_text, str):
        raise CanonicalHashError("SQL source must be text")
    normalized = sql_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return _normalize_self_references(normalized, migration_id).encode("utf-8")


def canonical_payload_bytes(metadata: Mapping[str, Any], canonical_sql: bytes) -> bytes:
    """Frame stable metadata and canonical SQL into the V4 hash input."""

    metadata_bytes = canonical_json(dict(metadata))
    profile_bytes = HASH_PROFILE.encode("ascii")
    version_bytes = CANONICALIZATION_VERSION.encode("ascii")
    # Length prefixes avoid delimiter ambiguity while keeping the SQL bytes
    # themselves present in the digest input.
    return b"JCFB-V4-CANONICAL-MIGRATION\0" + b"\0".join(
        (
            version_bytes,
            profile_bytes,
            len(metadata_bytes).to_bytes(8, "big"),
            metadata_bytes,
            len(canonical_sql).to_bytes(8, "big"),
            canonical_sql,
        )
    )


def canonical_hash(metadata: Mapping[str, Any], canonical_sql: bytes) -> str:
    return "sha256:" + hashlib.sha256(canonical_payload_bytes(metadata, canonical_sql)).hexdigest()


def canonical_hash_for_entry(repo_root: Path, entry: Mapping[str, Any], *, sql_text: Optional[str] = None) -> str:
    metadata = canonical_metadata(entry)
    if sql_text is None:
        # Keep direct callers fail-closed as well; the candidate SQL path must
        # remain inside v4_runtime_candidate even when no verifier is present.
        path = _entry_sql_path(repo_root, entry)
        try:
            sql_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CanonicalHashError("Candidate SQL could not be read") from exc
    return canonical_hash(metadata, canonicalize_sql_text(sql_text, migration_id=metadata["migration_id"]))


def _entry_sql_path(repo_root: Path, entry: Mapping[str, Any]) -> Path:
    relative = _required_string(entry, "candidate_file").replace("\\", "/")
    candidate_root = (repo_root / CANDIDATE_DIRECTORY_RELATIVE).resolve()
    path = (repo_root / Path(relative)).resolve()
    if path != candidate_root and candidate_root not in path.parents:
        raise CanonicalHashError("Candidate SQL path escapes the runtime candidate directory")
    return path


def _parse_header(sql_text: str, key: str) -> Optional[str]:
    match = re.search(rf"(?m)^--\s+{re.escape(key)}:\s*(.*?)\s*$", sql_text)
    return match.group(1).strip() if match else None


def _expected_depends(entry: Mapping[str, Any]) -> List[str]:
    value = entry.get("depends_on")
    return list(value) if isinstance(value, list) else []


def _seed_hashes(sql_text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line in sql_text.splitlines():
        match = _SEED_HASH_RE.search(line)
        if match:
            values[match.group("migration_id")] = match.group("value")
    return values


def _verify_manifest_shape(manifest: Mapping[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if manifest.get("$id") != "v4-runtime-candidate-manifest@1.0.0":
        issues.append(_issue("MANIFEST_ID_INVALID", "Runtime candidate manifest identity is invalid"))
    if manifest.get("candidate_count") != EXPECTED_CANDIDATE_COUNT:
        issues.append(_issue("MANIFEST_COUNT_INVALID", "Runtime candidate manifest must contain exactly nine candidates"))
    if manifest.get("production_apply") != "HARD_BLOCK":
        issues.append(_issue("PRODUCTION_POLICY_INVALID", "Runtime candidate manifest must hard-block Production apply"))
    if manifest.get("canonical_hash_status") != "GENERATED_CANONICAL_HASHES":
        issues.append(_issue("CANONICAL_STATUS_INVALID", "Runtime candidate manifest must declare generated canonical hashes"))
    profile = manifest.get("canonicalization")
    if not isinstance(profile, dict):
        issues.append(_issue("CANONICAL_PROFILE_MISSING", "Canonicalization profile is missing"))
    else:
        expected = {
            "version": CANONICALIZATION_VERSION,
            "algorithm": HASH_ALGORITHM,
            "profile": HASH_PROFILE,
            "sql_encoding": "UTF-8",
            "line_endings": "LF",
            "trailing_whitespace": "STRIP_HORIZONTAL_WHITESPACE_PER_LINE",
            "final_newline": "EXACTLY_ONE_LF",
            "self_hash_fields": "NORMALIZE_TO_SELF_HASH_PLACEHOLDER_DURING_HASH_ONLY",
        }
        for key, value in expected.items():
            if profile.get(key) != value:
                issues.append(_issue("CANONICAL_PROFILE_MISMATCH", f"Canonicalization profile field is invalid: {key}"))
        if profile.get("metadata_fields") != list(STABLE_METADATA_FIELDS):
            issues.append(_issue("CANONICAL_METADATA_FIELDS_INVALID", "Stable canonical metadata field list is invalid"))
        if profile.get("volatile_fields_excluded") != list(VOLATILE_METADATA_FIELDS):
            issues.append(_issue("CANONICAL_VOLATILE_FIELDS_INVALID", "Volatile metadata exclusion list is invalid"))
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != EXPECTED_CANDIDATE_COUNT:
        issues.append(_issue("CANDIDATE_LIST_INVALID", "Runtime candidate list must contain exactly nine entries"))
    return issues


def _verify_markdown_manifest(repo_root: Path, candidates: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    path = repo_root / CANDIDATE_MARKDOWN_RELATIVE
    if not path.is_file():
        return [_issue("MARKDOWN_MANIFEST_MISSING", "Review manifest is missing", CANDIDATE_MARKDOWN_RELATIVE)]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [_issue("MARKDOWN_MANIFEST_UNREADABLE", "Review manifest could not be read", CANDIDATE_MARKDOWN_RELATIVE)]
    issues: List[Dict[str, str]] = []
    if "Canonical migration hashes: GENERATED_CANONICAL_HASHES" not in text:
        issues.append(_issue("MARKDOWN_CANONICAL_STATUS_INVALID", "Review manifest does not declare generated canonical hashes", CANDIDATE_MARKDOWN_RELATIVE))
    if f"Canonicalization: {CANONICALIZATION_VERSION} / {HASH_ALGORITHM} / {HASH_PROFILE}" not in text:
        issues.append(_issue("MARKDOWN_CANONICAL_PROFILE_INVALID", "Review manifest canonicalization profile is missing", CANDIDATE_MARKDOWN_RELATIVE))
    row_re = re.compile(
        r"^\|\s*(?P<sequence>\d{4})\s*\|(?:[^|]*\|){3}\s*(?P<byte>[0-9a-f]{64})\s*\|\s*(?P<canonical>sha256:[0-9a-f]{64})\s*\|\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    rows = {match.group("sequence"): match.groupdict() for match in row_re.finditer(text)}
    for entry in candidates:
        sequence = entry.get("sequence")
        key = f"{sequence:04d}" if isinstance(sequence, int) else str(sequence)
        row = rows.get(key)
        if row is None:
            issues.append(_issue("MARKDOWN_CANDIDATE_ROW_MISSING", "Review manifest candidate row is missing", f"candidate:{key}"))
            continue
        if row["byte"] != str(entry.get("content_sha256_noncanonical", "")).lower() or row["canonical"] != str(entry.get("canonical_migration_hash", "")):
            issues.append(_issue("MARKDOWN_HASH_MISMATCH", "Review manifest hash columns differ from JSON manifest", f"candidate:{key}"))
    return issues


def _write_markdown_manifest(repo_root: Path, candidates: Sequence[Mapping[str, Any]]) -> None:
    path = repo_root / CANDIDATE_MARKDOWN_RELATIVE
    if not path.is_file():
        raise CanonicalHashError("Review manifest is missing")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Canonical migration hashes: PENDING_CANONICAL_HASH",
        "Canonical migration hashes: GENERATED_CANONICAL_HASHES",
    )
    text = re.sub(
        r"(?m)^- Canonicalization: .*?$",
        f"- Canonicalization: {CANONICALIZATION_VERSION} / {HASH_ALGORITHM} / {HASH_PROFILE}",
        text,
    )
    for entry in candidates:
        sequence = entry.get("sequence")
        if not isinstance(sequence, int):
            raise CanonicalHashError("Candidate sequence must be an integer")
        marker = f"| {sequence:04d} |"
        lines = text.splitlines()
        found = False
        for index, line in enumerate(lines):
            if not line.startswith(marker):
                continue
            parts = line.split("|")
            if len(parts) < 8:
                raise CanonicalHashError("Review manifest candidate row has an invalid shape")
            parts[5] = f" {str(entry.get('content_sha256_noncanonical', '')).lower()} "
            parts[6] = f" {entry.get('canonical_migration_hash')} "
            lines[index] = "|".join(parts)
            found = True
            break
        if not found:
            raise CanonicalHashError(f"Review manifest candidate row is missing: {sequence:04d}")
        text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def verify_candidate_hashes(repo_root: Path, manifest: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Recompute every candidate hash and return redacted, auditable evidence."""

    issues: List[Dict[str, str]] = []
    entries_report: List[Dict[str, Any]] = []
    try:
        loaded = dict(manifest) if manifest is not None else load_candidate_manifest(repo_root)
    except CanonicalHashError as exc:
        return {
            "status": "FAIL",
            "algorithm": HASH_ALGORITHM,
            "profile": HASH_PROFILE,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "candidate_count": 0,
            "matched_count": 0,
            "pending_count": 0,
            "dependency_status": "FAIL",
            "issues": [_issue("MANIFEST_LOAD_FAILED", str(exc))],
            "entries": [],
        }

    issues.extend(_verify_manifest_shape(loaded))
    candidates = loaded.get("candidates") if isinstance(loaded.get("candidates"), list) else []
    issues.extend(_verify_markdown_manifest(repo_root, [item for item in candidates if isinstance(item, Mapping)]))
    by_id: Dict[str, Mapping[str, Any]] = {}
    previous_id: Optional[str] = None
    for index, entry_value in enumerate(candidates):
        location = f"candidate:{index + 1:04d}"
        if not isinstance(entry_value, dict):
            issues.append(_issue("CANDIDATE_ENTRY_INVALID", "Candidate entry must be an object", location))
            continue
        entry = entry_value
        migration_id = str(entry.get("migration_id", ""))
        sequence = entry.get("sequence")
        expected_dependency = [] if previous_id is None else [previous_id]
        if sequence != index + 1:
            issues.append(_issue("SEQUENCE_MISMATCH", "Candidate sequence is not contiguous", location))
        if entry.get("depends_on") != expected_dependency:
            issues.append(_issue("DEPENDENCY_MISMATCH", "Candidate dependency is not the exact predecessor", location))
        if migration_id in by_id:
            issues.append(_issue("DUPLICATE_MIGRATION_ID", "Candidate migration identity is duplicated", location))
        by_id[migration_id] = entry
        previous_id = migration_id or previous_id

        manifest_hash = entry.get("canonical_migration_hash")
        entry_report: Dict[str, Any] = {
            "sequence": f"{sequence:04d}" if isinstance(sequence, int) else sequence,
            "migration_id": migration_id,
            "candidate_file": entry.get("candidate_file"),
            "manifest_hash": manifest_hash,
            "computed_hash": None,
            "hash_match": False,
            "byte_hash_match": False,
            "header_match": False,
            "seed_hashes_match": True,
        }
        try:
            path = _entry_sql_path(repo_root, entry)
            sql_bytes = path.read_bytes()
            sql_text = sql_bytes.decode("utf-8")
            actual_byte_hash = hashlib.sha256(sql_bytes).hexdigest()
            entry_report["byte_hash"] = actual_byte_hash
            entry_report["byte_hash_match"] = actual_byte_hash == entry.get("content_sha256_noncanonical")
            if not entry_report["byte_hash_match"]:
                issues.append(_issue("BYTE_HASH_MISMATCH", "Candidate byte provenance hash differs", str(entry.get("candidate_file"))))
            computed = canonical_hash_for_entry(repo_root, entry, sql_text=sql_text)
            entry_report["computed_hash"] = computed
            entry_report["hash_match"] = computed == manifest_hash
            if not entry_report["hash_match"]:
                issues.append(_issue("CANONICAL_HASH_MISMATCH", "Computed canonical hash differs from manifest", str(entry.get("candidate_file"))))
            header_values = {
                "migration_id": _parse_header(sql_text, "migration_id"),
                "sequence": _parse_header(sql_text, "sequence"),
                "name": _parse_header(sql_text, "name"),
                "migration_version": _parse_header(sql_text, "migration_version"),
                "depends_on": normalize_dependency(_parse_header(sql_text, "depends_on") or ""),
                "schema_contract_version": _parse_header(sql_text, "schema_contract_version"),
                "authored_at": _parse_header(sql_text, "authored_at"),
                "canonical_migration_hash": _parse_header(sql_text, "canonical_migration_hash"),
                "migration_hash": _parse_header(sql_text, "migration_hash"),
            }
            expected_sequence = f"{sequence:04d}" if isinstance(sequence, int) else ""
            header_match = (
                header_values["migration_id"] == entry.get("migration_id")
                and header_values["sequence"] == expected_sequence
                and header_values["name"] == entry.get("name")
                and header_values["migration_version"] == entry.get("migration_version")
                and header_values["depends_on"] == _expected_depends(entry)
                and header_values["schema_contract_version"] == entry.get("schema_contract_version")
                and header_values["authored_at"] == entry.get("authored_at")
                and header_values["canonical_migration_hash"] == manifest_hash
                and header_values["migration_hash"] == manifest_hash
            )
            entry_report["header_match"] = header_match
            if not header_match:
                issues.append(_issue("SQL_HEADER_MISMATCH", "Candidate SQL metadata/hash headers differ from manifest", str(entry.get("candidate_file"))))
            if sequence == 9:
                seed_hashes = _seed_hashes(sql_text)
                expected_seeds = {str(item.get("migration_id")): item.get("canonical_migration_hash") for item in candidates if isinstance(item, dict)}
                entry_report["seed_hashes_match"] = all(seed_hashes.get(key) == value for key, value in expected_seeds.items()) and len(seed_hashes) == len(expected_seeds)
                if not entry_report["seed_hashes_match"]:
                    issues.append(_issue("SEED_HASH_MISMATCH", "0009 registry seed hashes differ from the candidate manifest", str(entry.get("candidate_file"))))
        except (OSError, UnicodeDecodeError, CanonicalHashError) as exc:
            issues.append(_issue("CANDIDATE_HASH_ERROR", "Candidate hash verification could not read or canonicalize the SQL", str(entry.get("candidate_file"))))
            entry_report["error"] = type(exc).__name__
        entries_report.append(entry_report)

    pending_count = sum(1 for entry in candidates if isinstance(entry, dict) and entry.get("canonical_migration_hash") == PENDING_CANONICAL_HASH)
    matched_count = sum(1 for entry in entries_report if entry.get("hash_match") and entry.get("header_match") and entry.get("byte_hash_match") and entry.get("seed_hashes_match"))
    dependency_status = "PASS" if not any(issue["code"].startswith("DEPENDENCY") or issue["code"] in {"SEQUENCE_MISMATCH", "DUPLICATE_MIGRATION_ID"} for issue in issues) else "FAIL"
    status = "PASS" if not issues and len(entries_report) == EXPECTED_CANDIDATE_COUNT and matched_count == EXPECTED_CANDIDATE_COUNT else "FAIL"
    return {
        "status": status,
        "algorithm": HASH_ALGORITHM,
        "profile": HASH_PROFILE,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "candidate_count": len(entries_report),
        "matched_count": matched_count,
        "pending_count": pending_count,
        "dependency_status": dependency_status,
        "issues": issues,
        "entries": entries_report,
    }


def _replace_header_hashes(sql_text: str, value: str) -> str:
    return re.sub(
        rf"(?m)^(--\s+(?:canonical_migration_hash|migration_hash):\s+){_HASH_VALUE}\s*$",
        lambda match: f"{match.group(1)}{value}",
        sql_text,
        flags=re.IGNORECASE,
    )


def _replace_seed_hashes(sql_text: str, hashes: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        migration_id = match.group("migration_id")
        value = hashes.get(migration_id, match.group("value"))
        return f"{match.group('prefix')}{value}{match.group('suffix')}"

    return "\n".join(_SEED_HASH_RE.sub(replace, line) for line in sql_text.split("\n"))


def generate_candidate_hashes(repo_root: Path, manifest: Optional[MutableMapping[str, Any]] = None) -> Dict[str, str]:
    """Compute hashes in dependency order without modifying repository files."""

    loaded: MutableMapping[str, Any] = manifest if manifest is not None else load_candidate_manifest(repo_root)
    candidates = loaded.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise CanonicalHashError("Exactly nine candidates are required to generate hashes")
    hashes: Dict[str, str] = {}
    for index, entry_value in enumerate(candidates):
        if not isinstance(entry_value, dict):
            raise CanonicalHashError("Candidate entry must be an object")
        entry = dict(entry_value)
        migration_id = _required_string(entry, "migration_id")
        path = _entry_sql_path(repo_root, entry)
        sql_text = path.read_text(encoding="utf-8")
        if index == EXPECTED_CANDIDATE_COUNT - 1:
            sql_text = _replace_seed_hashes(sql_text, hashes)
        hashes[migration_id] = canonical_hash_for_entry(repo_root, entry, sql_text=sql_text)
    return hashes


def canonical_profile_summary() -> Dict[str, Any]:
    return {
        "version": CANONICALIZATION_VERSION,
        "algorithm": HASH_ALGORITHM,
        "profile": HASH_PROFILE,
        "sql_encoding": "UTF-8",
        "line_endings": "LF",
        "trailing_whitespace": "STRIP_HORIZONTAL_WHITESPACE_PER_LINE",
        "final_newline": "EXACTLY_ONE_LF",
        "self_hash_fields": "NORMALIZE_TO_SELF_HASH_PLACEHOLDER_DURING_HASH_ONLY",
        "metadata_fields": list(STABLE_METADATA_FIELDS),
        "volatile_fields_excluded": list(VOLATILE_METADATA_FIELDS),
    }


def write_candidate_hashes(repo_root: Path) -> Dict[str, Any]:
    """Write generated hashes to runtime candidates and return verification evidence.

    This is an explicit maintenance operation for the candidate package.  It
    never touches the design-only migration directory and never changes a
    lifecycle/apply field.
    """

    manifest = load_candidate_manifest(repo_root)
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise CanonicalHashError("Exactly nine candidates are required to write hashes")
    # The first runtime-candidate manifest predates the canonical metadata
    # envelope.  Populate only deterministic values derived from the existing
    # migration identity before calculating any digest; no clock or host data
    # is introduced.
    for entry_value in candidates:
        if not isinstance(entry_value, dict):
            raise CanonicalHashError("Candidate entry must be an object")
        migration_id = _required_string(entry_value, "migration_id")
        entry_value.setdefault("migration_version", migration_id)
        entry_value.setdefault("schema_contract_version", EXPECTED_SCHEMA_CONTRACT)
        entry_value.setdefault("authored_at", "2026-09-01T00:00:00+08:00")
    hashes = generate_candidate_hashes(repo_root, manifest)
    for entry_value in candidates:
        if not isinstance(entry_value, dict):
            raise CanonicalHashError("Candidate entry must be an object")
        migration_id = _required_string(entry_value, "migration_id")
        path = _entry_sql_path(repo_root, entry_value)
        sql_text = path.read_text(encoding="utf-8")
        sql_text = _replace_header_hashes(sql_text, hashes[migration_id])
        if entry_value.get("sequence") == 9:
            sql_text = _replace_seed_hashes(sql_text, hashes)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(sql_text)
        entry_value["canonical_migration_hash"] = hashes[migration_id]
        entry_value["content_sha256_noncanonical"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entry_value["migration_version"] = entry_value.get("migration_version") or migration_id
        entry_value["schema_contract_version"] = entry_value.get("schema_contract_version") or EXPECTED_SCHEMA_CONTRACT
        entry_value["authored_at"] = entry_value.get("authored_at") or "2026-09-01T00:00:00+08:00"
    manifest["canonical_hash_status"] = "GENERATED_CANONICAL_HASHES"
    manifest["canonicalization"] = canonical_profile_summary()
    manifest_path = repo_root / CANDIDATE_MANIFEST_RELATIVE
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    _write_markdown_manifest(repo_root, candidates)
    return verify_candidate_hashes(repo_root, manifest)
