"""Additive r002 package contract: deterministic ZIP and exclusions.

This module is a no-write contract/validation surface.  It builds ZIP bytes only
in memory for synthetic fixtures or a caller-owned buffer; it has no archive
intake or database path.
"""

from __future__ import annotations

import binascii
import io
import json
import re
import struct
import unicodedata
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from . import IntakeValidationError, HASH_RE, canonical_json_bytes, sha256_bytes, sha256_json


PACKAGE_CONTRACT_V1_1 = "verified-historical-backfill-export-package@1.1.0"
PACKAGE_CONTRACT_V1_0 = "verified-historical-backfill-export-package@1.0.0"
EXCLUSION_MANIFEST_SCHEMA = "verified-historical-backfill-exclusion-manifest@1.0.0"
ZIP_PROFILE = "v4-deterministic-zip@1.0"
DOS_EPOCH = (1980, 1, 1, 0, 0, 0)
ZIP_VERSION = 20
EXCLUSION_REASONS = {
    "BETTING_SLIP": "BETTING_SLIP_NOT_RAW_FACT",
    "GENERATED_PREDICTION_DASHBOARD": "GENERATED_PREDICTION_NOT_RAW_FACT",
    "RECOMMENDATION_ARTIFACT": "RECOMMENDATION_NOT_RAW_FACT",
}
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def normalize_zip_entry_path(path: str) -> str:
    """Return the only accepted POSIX/NFC relative member path."""
    if not isinstance(path, str) or not path:
        raise IntakeValidationError("ZIP_ENTRY_PATH_INVALID", "entry path must be a non-empty string")
    normalized = unicodedata.normalize("NFC", path)
    if normalized != path:
        path = normalized
    if "\x00" in path or "\\" in path or path.startswith("/") or _DRIVE_PREFIX.match(path):
        raise IntakeValidationError("ZIP_ENTRY_PATH_INVALID", f"entry path is not a relative POSIX path: {path!r}")
    if path.endswith("/") or "//" in path:
        raise IntakeValidationError("ZIP_DIRECTORY_ENTRY_FORBIDDEN", f"directory or duplicate separator: {path!r}")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise IntakeValidationError("ZIP_ENTRY_PATH_INVALID", f"dot/empty path segment: {path!r}")
    if str(PurePosixPath(path)) != path:
        raise IntakeValidationError("ZIP_ENTRY_PATH_INVALID", f"non-canonical POSIX path: {path!r}")
    try:
        path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IntakeValidationError("ZIP_FILENAME_NOT_UTF8", f"entry path is not UTF-8 encodable: {path!r}") from exc
    return path


def _entry_sort_key(path: str) -> bytes:
    return path.encode("utf-8")


def serialize_manifest_text(value: Any) -> bytes:
    """Serialize generated JSON manifest text as UTF-8 plus exactly one LF."""
    payload = canonical_json_bytes(value)
    if b"\r" in payload or b"\n" in payload:
        raise IntakeValidationError("MANIFEST_TEXT_INVALID", "canonical JSON unexpectedly contains a line break")
    return payload + b"\n"


def build_deterministic_zip(entries: Mapping[str, bytes]) -> bytes:
    """Build canonical ZIP32 bytes from an in-memory path-to-bytes mapping.

    The small writer is intentional: ``zipfile.writestr`` may add interpreter-
    dependent defaults such as a Unix mode or omit EFS for ASCII-only names.
    """
    if not isinstance(entries, Mapping) or not entries:
        raise IntakeValidationError("ZIP_ENTRIES_REQUIRED", "at least one file entry is required")
    normalized: dict[str, bytes] = {}
    for raw_path, content in entries.items():
        path = normalize_zip_entry_path(raw_path)
        if not isinstance(content, bytes):
            raise IntakeValidationError("ZIP_ENTRY_BYTES_REQUIRED", f"{path} must be bytes")
        if path in normalized:
            raise IntakeValidationError("ZIP_ENTRY_DUPLICATE", f"duplicate normalized path: {path}")
        normalized[path] = content
    if len(normalized) > 65535 or sum(len(content) for content in normalized.values()) >= 2**32:
        raise IntakeValidationError("ZIP32_LIMIT_EXCEEDED", "ZIP32 profile does not permit this archive size")

    output = io.BytesIO()
    central: list[tuple[str, bytes, int, int]] = []
    dos_time = 0
    dos_date = (1 << 5) | 1  # 1980-01-01 in DOS date encoding
    for path in sorted(normalized, key=_entry_sort_key):
        name = path.encode("utf-8")
        content = normalized[path]
        crc = binascii.crc32(content) & 0xFFFFFFFF
        offset = output.tell()
        if offset >= 2**32:
            raise IntakeValidationError("ZIP32_LIMIT_EXCEEDED", "local header offset exceeds ZIP32")
        output.write(struct.pack("<4s5H3L2H", b"PK\x03\x04", ZIP_VERSION, 0x800, zipfile.ZIP_STORED, dos_time, dos_date, crc, len(content), len(content), len(name), 0))
        output.write(name)
        output.write(content)
        central.append((path, name, crc, offset))
    central_offset = output.tell()
    for path, name, crc, offset in central:
        content_size = len(normalized[path])
        output.write(struct.pack("<4s6H3L5H2L", b"PK\x01\x02", ZIP_VERSION, ZIP_VERSION, 0x800, zipfile.ZIP_STORED, dos_time, dos_date, crc, content_size, content_size, len(name), 0, 0, 0, 0, 0x20, offset))
        output.write(name)
    central_size = output.tell() - central_offset
    if central_offset >= 2**32 or central_size >= 2**32:
        raise IntakeValidationError("ZIP32_LIMIT_EXCEEDED", "central directory exceeds ZIP32")
    output.write(struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, len(central), len(central), central_size, central_offset, 0))
    return output.getvalue()


def zip_sha256(zip_bytes: bytes) -> str:
    if not isinstance(zip_bytes, bytes):
        raise IntakeValidationError("ZIP_BYTES_REQUIRED", "ZIP bytes are required")
    return sha256_bytes(zip_bytes)


def validate_deterministic_zip(zip_bytes: bytes, expected_entries: Mapping[str, bytes]) -> str:
    """Validate canonical member bytes/metadata and return the ZIP byte hash."""
    expected: dict[str, bytes] = {}
    for raw_path, content in expected_entries.items():
        path = normalize_zip_entry_path(raw_path)
        if path in expected:
            raise IntakeValidationError("ZIP_ENTRY_DUPLICATE", f"duplicate normalized path: {path}")
        if not isinstance(content, bytes):
            raise IntakeValidationError("ZIP_ENTRY_BYTES_REQUIRED", f"{path} must be bytes")
        expected[path] = content
    expected_names = sorted(expected, key=_entry_sort_key)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as archive:
            if archive.comment != b"":
                raise IntakeValidationError("ZIP_ARCHIVE_COMMENT_INVALID", "archive comment must be empty")
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != expected_names:
                raise IntakeValidationError("ZIP_ENTRY_ORDER_INVALID", "entry order or normalized names differ")
            for info in infos:
                path = normalize_zip_entry_path(info.filename)
                content = archive.read(info)
                if content != expected[path]:
                    raise IntakeValidationError("ZIP_ENTRY_BYTES_MISMATCH", f"entry bytes differ: {path}")
                if info.is_dir() or info.date_time != DOS_EPOCH:
                    raise IntakeValidationError("ZIP_METADATA_INVALID", f"timestamp/directory metadata differs: {path}")
                if (
                    info.compress_type != zipfile.ZIP_STORED
                    or info.create_system != 0
                    or info.create_version != ZIP_VERSION
                    or info.extract_version != ZIP_VERSION
                    or info.flag_bits & 0x800 == 0
                    or info.volume != 0
                    or info.internal_attr != 0
                    or info.external_attr != 0x20
                    or info.extra != b""
                    or info.comment != b""
                    or info.compress_size != len(content)
                    or info.file_size != len(content)
                    or info.CRC != binascii.crc32(content) & 0xFFFFFFFF
                ):
                    raise IntakeValidationError("ZIP_METADATA_INVALID", f"normalized metadata differs: {path}")
    except zipfile.BadZipFile as exc:
        raise IntakeValidationError("ZIP_INVALID", "bytes are not a readable ZIP archive") from exc
    return zip_sha256(zip_bytes)


def _require_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise IntakeValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")


def _record_order_key(record: Mapping[str, Any]) -> tuple[bytes, ...]:
    return tuple(str(record[field]).encode("utf-8") for field in ("category", "source_reference", "source_filename", "source_sha256", "exclusion_id"))


def exclusion_record_hash(record: Mapping[str, Any]) -> str:
    return sha256_json({key: value for key, value in record.items() if key != "record_sha256"})


def exclusion_manifest_hash(manifest: Mapping[str, Any]) -> str:
    body = {
        "schema_version": manifest.get("schema_version"),
        "records": manifest.get("records"),
    }
    return sha256_json(body)


def validate_exclusion_manifest(
    manifest: Mapping[str, Any],
    accepted_file_manifest: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate exclusion records and ensure excluded identities stay outside RAW_FACT."""
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != EXCLUSION_MANIFEST_SCHEMA:
        raise IntakeValidationError("EXCLUSION_SCHEMA_INVALID", "wrong exclusion manifest schema identity")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise IntakeValidationError("EXCLUSION_RECORDS_INVALID", "exclusion records must be an array")
    if records != sorted(records, key=_record_order_key):
        raise IntakeValidationError("EXCLUSION_ORDER_INVALID", "exclusion records are not in deterministic order")
    accepted = list(accepted_file_manifest)
    excluded_identities: set[tuple[Any, ...]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise IntakeValidationError("EXCLUSION_RECORD_INVALID", f"records[{index}] must be an object")
        required = ("exclusion_id", "category", "reason_code", "source_filename", "source_reference", "source_sha256", "artifact_classification", "record_sha256")
        for field in required:
            if field not in record or not isinstance(record[field], str) or not record[field].strip():
                raise IntakeValidationError("EXCLUSION_FIELD_MISSING", f"records[{index}].{field} is required")
        category = record["category"]
        if category not in EXCLUSION_REASONS or record["reason_code"] != EXCLUSION_REASONS[category]:
            raise IntakeValidationError("EXCLUSION_REASON_INVALID", f"records[{index}] has an invalid category/reason pair")
        if record["artifact_classification"] != "EXCLUDED":
            raise IntakeValidationError("EXCLUSION_CLASSIFICATION_INVALID", f"records[{index}] must be EXCLUDED")
        _require_hash(record["source_sha256"], f"records[{index}].source_sha256")
        _require_hash(record["record_sha256"], f"records[{index}].record_sha256")
        if record["record_sha256"] != exclusion_record_hash(record):
            raise IntakeValidationError("EXCLUSION_RECORD_HASH_MISMATCH", f"records[{index}] record hash mismatch")
        identity = (record["source_filename"], record["source_reference"], record["source_sha256"])
        excluded_identities.add(identity)
    if manifest.get("manifest_sha256") != exclusion_manifest_hash(manifest):
        raise IntakeValidationError("EXCLUSION_MANIFEST_HASH_MISMATCH", "manifest_sha256 does not match records")
    for index, item in enumerate(accepted):
        if not isinstance(item, Mapping):
            raise IntakeValidationError("RAW_FILE_MANIFEST_INVALID", f"file_manifest[{index}] must be an object")
        identity = (item.get("original_filename"), item.get("library_file_id_or_ref"), item.get("original_file_sha256"))
        if identity in excluded_identities:
            raise IntakeValidationError("EXCLUDED_ARTIFACT_LEAK", f"excluded source occurs in accepted file_manifest[{index}]")
        if item.get("artifact_classification") in set(EXCLUSION_REASONS) or item.get("generated_artifact") is True:
            raise IntakeValidationError("EXCLUDED_ARTIFACT_LEAK", f"generated/excluded classification occurs in accepted file_manifest[{index}]")
    return {"record_count": len(records), "schema_version": EXCLUSION_MANIFEST_SCHEMA}


def package_substantive_body(package: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {"created_at", "exported_at", "package_substantive_hash", "package_sha256", "package_zip_sha256"}
    body = {key: value for key, value in package.items() if key not in excluded}
    body["manifests"] = [
        {key: value for key, value in item.items() if key not in {"export_package_hash", "package_substantive_hash"}}
        if isinstance(item, Mapping) else item
        for item in package.get("manifests", [])
    ]
    return body


def package_object_body(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in package.items() if key != "package_sha256"}


def recompute_package_hashes(package: Mapping[str, Any]) -> dict[str, str]:
    return {
        "package_substantive_hash": sha256_json(package_substantive_body(package)),
        "package_sha256": sha256_json(package_object_body(package)),
    }


def validate_export_package_v1_1(package: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    required = ("export_package_id", "revision", "contract_version", "source_origin", "created_at", "exported_at", "file_manifest", "metadata_manifest", "manifests", "exclusion_manifest", "zip_serialization_profile", "package_substantive_hash", "package_sha256", "package_zip_sha256")
    missing = [field for field in required if field not in package]
    if missing:
        raise IntakeValidationError("PACKAGE_FIELD_MISSING", ", ".join(missing))
    if package["contract_version"] != PACKAGE_CONTRACT_V1_1:
        raise IntakeValidationError("PACKAGE_CONTRACT_INVALID", "r002 requires additive package contract @1.1.0")
    if package["source_origin"] != "CHATGPT_LIBRARY_EXPORT" or not isinstance(package["revision"], int) or package["revision"] < 1:
        raise IntakeValidationError("PACKAGE_IDENTITY_INVALID", "source origin and positive revision are required")
    if package["zip_serialization_profile"] != ZIP_PROFILE:
        raise IntakeValidationError("ZIP_PROFILE_INVALID", "package is not bound to v4-deterministic-zip@1.0")
    files = package["file_manifest"]
    metadata = package["metadata_manifest"]
    manifests = package["manifests"]
    if not isinstance(files, list) or not files or not isinstance(metadata, list) or not isinstance(manifests, list) or len(files) != len(metadata) or len(files) != len(manifests):
        raise IntakeValidationError("PACKAGE_MANIFEST_CARDINALITY_INVALID", "file, metadata, and import manifests must be index-aligned")
    validate_exclusion_manifest(package["exclusion_manifest"], files)
    for index, item in enumerate(files):
        for field in ("manifest_id", "original_filename", "original_file_sha256", "library_file_id_or_ref"):
            if field not in item:
                raise IntakeValidationError("FILE_MANIFEST_FIELD_MISSING", f"file_manifest[{index}].{field}")
        _require_hash(item["original_file_sha256"], f"file_manifest[{index}].original_file_sha256")
        if manifests[index].get("manifest_id") != item["manifest_id"] or manifests[index].get("original_file_sha256") != item["original_file_sha256"]:
            raise IntakeValidationError("FILE_MANIFEST_BINDING_INVALID", f"file_manifest[{index}] does not bind its import manifest")
        if metadata[index].get("manifest_id") != item["manifest_id"] or metadata[index].get("metadata_snapshot_sha256") != manifests[index].get("metadata_snapshot_sha256"):
            raise IntakeValidationError("METADATA_MANIFEST_BINDING_INVALID", f"metadata_manifest[{index}] does not bind its import manifest")
    _require_hash(package["package_substantive_hash"], "package_substantive_hash")
    _require_hash(package["package_sha256"], "package_sha256")
    _require_hash(package["package_zip_sha256"], "package_zip_sha256")
    if verify_hash:
        expected = recompute_package_hashes(package)
        if package["package_substantive_hash"] != expected["package_substantive_hash"]:
            raise IntakeValidationError("PACKAGE_SUBSTANTIVE_HASH_MISMATCH", "package substantive hash mismatch")
        if package["package_sha256"] != expected["package_sha256"]:
            raise IntakeValidationError("PACKAGE_OBJECT_HASH_MISMATCH", "package object hash mismatch")
    return {"manifest_count": len(manifests), "exclusion_count": len(package["exclusion_manifest"]["records"]), "package_contract": PACKAGE_CONTRACT_V1_1}


def synthetic_fixture() -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return a tiny package-like fixture and its canonical ZIP entries."""
    source_hash = sha256_bytes(b"synthetic-raw-fact")
    metadata_hash = sha256_bytes(b"synthetic-metadata")
    record = {
        "exclusion_id": "ex-001",
        "category": "BETTING_SLIP",
        "reason_code": EXCLUSION_REASONS["BETTING_SLIP"],
        "source_filename": "betting-slip.png",
        "source_reference": "library://synthetic/betting-slip",
        "source_sha256": sha256_bytes(b"synthetic-betting-slip"),
        "artifact_classification": "EXCLUDED",
    }
    record["record_sha256"] = exclusion_record_hash(record)
    exclusions = {"schema_version": EXCLUSION_MANIFEST_SCHEMA, "records": [record]}
    exclusions["manifest_sha256"] = exclusion_manifest_hash(exclusions)
    manifest = {
        "manifest_id": "m-001",
        "original_file_sha256": source_hash,
        "metadata_snapshot_sha256": metadata_hash,
        "export_package_hash": "sha256:" + "0" * 64,
        "package_substantive_hash": "sha256:" + "0" * 64,
    }
    package = {
        "export_package_id": "synthetic-r002",
        "revision": 2,
        "contract_version": PACKAGE_CONTRACT_V1_1,
        "source_origin": "CHATGPT_LIBRARY_EXPORT",
        "created_at": "2026-09-07T00:00:00+00:00",
        "exported_at": "2026-09-07T00:00:00+00:00",
        "file_manifest": [{"manifest_id": "m-001", "original_filename": "raw/001.png", "original_file_sha256": source_hash, "library_file_id_or_ref": "library://synthetic/raw-001"}],
        "metadata_manifest": [{"manifest_id": "m-001", "metadata_snapshot_sha256": metadata_hash}],
        "manifests": [manifest],
        "exclusion_manifest": exclusions,
        "zip_serialization_profile": ZIP_PROFILE,
        "package_substantive_hash": "sha256:" + "0" * 64,
        "package_sha256": "sha256:" + "0" * 64,
        "package_zip_sha256": "sha256:" + "0" * 64,
    }
    package["package_substantive_hash"] = sha256_json(package_substantive_body(package))
    package["manifests"][0]["export_package_hash"] = package["package_substantive_hash"]
    package["manifests"][0]["package_substantive_hash"] = package["package_substantive_hash"]
    package["package_sha256"] = sha256_json(package_object_body(package))
    entries = {
        "package.json": serialize_manifest_text(package),
        "exclusions/manifest.json": serialize_manifest_text(exclusions),
        "raw/001.png": b"synthetic-raw-fact",
    }
    zip_bytes = build_deterministic_zip(entries)
    package["package_zip_sha256"] = zip_sha256(zip_bytes)
    package["package_sha256"] = sha256_json(package_object_body(package))
    return package, entries


def run_synthetic_validation() -> dict[str, Any]:
    package, entries = synthetic_fixture()
    validate_export_package_v1_1(package)
    first = build_deterministic_zip(entries)
    second = build_deterministic_zip(entries)
    if first != second or zip_sha256(first) != zip_sha256(second):
        raise IntakeValidationError("ZIP_REBUILD_NONDETERMINISTIC", "same inputs produced different ZIP bytes")
    if validate_deterministic_zip(first, entries) != package["package_zip_sha256"]:
        raise IntakeValidationError("ZIP_HASH_BINDING_INVALID", "package ZIP hash does not bind final bytes")
    return {"package_substantive_hash": package["package_substantive_hash"], "package_zip_sha256": package["package_zip_sha256"], "entry_count": len(entries)}


__all__ = [
    "EXCLUSION_MANIFEST_SCHEMA",
    "EXCLUSION_REASONS",
    "PACKAGE_CONTRACT_V1_0",
    "PACKAGE_CONTRACT_V1_1",
    "ZIP_PROFILE",
    "build_deterministic_zip",
    "exclusion_manifest_hash",
    "exclusion_record_hash",
    "normalize_zip_entry_path",
    "package_object_body",
    "package_substantive_body",
    "recompute_package_hashes",
    "run_synthetic_validation",
    "serialize_manifest_text",
    "synthetic_fixture",
    "validate_deterministic_zip",
    "validate_exclusion_manifest",
    "validate_export_package_v1_1",
    "zip_sha256",
]
