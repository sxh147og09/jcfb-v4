"""Append-only staging, identity mapping, and dedupe helpers for Library backfill.

This module accepts a caller-owned, already extracted package.  It validates
the package before writing a new revision directory under
``approved_data/historical_backfill_staging`` and refuses to overwrite an
existing directory.  It never writes ``historical_source_archive`` and never
changes dataset counts.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from . import IntakeValidationError, canonical_json_bytes, sha256_bytes, sha256_json, validate_staging_path
from .package_contract import normalize_zip_entry_path, validate_export_package_v1_1


SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def canonical_identity_key(identity: Mapping[str, Any]) -> str:
    """Map only an explicit canonical identity; no fuzzy team-name matching."""
    required = ("canonical_match_id", "competition", "home", "away")
    missing = [field for field in required if not isinstance(identity.get(field), str) or not identity[field].strip()]
    if missing:
        raise IntakeValidationError("CANONICAL_IDENTITY_INCOMPLETE", ",".join(missing))
    kickoff = identity.get("kickoff_at", "UNKNOWN")
    if kickoff != "UNKNOWN":
        if not isinstance(kickoff, str):
            raise IntakeValidationError("KICKOFF_IDENTITY_INVALID", "kickoff_at must be an explicit ISO timestamp or UNKNOWN")
        try:
            datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError as exc:
            raise IntakeValidationError("KICKOFF_IDENTITY_INVALID", "kickoff_at must be ISO-8601") from exc
    return sha256_json({field: identity[field].strip() for field in required} | {"kickoff_at": kickoff})


class AppendOnlyStaging:
    def __init__(self, project_root: str | Path = "F:/Projects/jcfb-v4") -> None:
        self.project_root = Path(project_root).resolve()
        self.staging_root = self.project_root / "approved_data/historical_backfill_staging"
        self.archive_root = self.project_root / "approved_data/historical_source_archive"

    def _safe_dir_name(self, value: str) -> str:
        if not isinstance(value, str) or not SAFE_NAME.fullmatch(value) or value in {".", ".."}:
            raise IntakeValidationError("STAGING_REVISION_NAME_INVALID", str(value))
        return value

    def stage_validated_package(self, package: Mapping[str, Any], *, package_name: str, raw_files: Mapping[str, bytes], metadata_files: Optional[Mapping[str, bytes]] = None) -> dict[str, Any]:
        """Write one new package directory after full v1.1 validation.

        ``raw_files`` keys must exactly match the package's declared
        ``original_filename`` values.  The package remains in staging and is
        not promoted to the historical archive.
        """
        validate_staging_path(self.staging_root, project_root=self.project_root)
        try:
            validate_export_package_v1_1(package)
        except Exception:
            raise
        target = (self.staging_root / self._safe_dir_name(package_name)).resolve()
        if target.exists():
            raise IntakeValidationError("STAGING_OVERWRITE_FORBIDDEN", str(target))
        declared = {}
        for item in package["file_manifest"]:
            name = normalize_zip_entry_path(str(item["original_filename"]))
            declared[name] = str(item["original_file_sha256"])
        if set(raw_files) != set(declared):
            raise IntakeValidationError("RAW_FILE_MANIFEST_MISMATCH", "raw_files must exactly match file_manifest names")
        for name, content in raw_files.items():
            if not isinstance(content, bytes) or sha256_bytes(content) != declared[name]:
                raise IntakeValidationError("RAW_FILE_HASH_MISMATCH", name)
        # The package itself has been hash-validated before this point.  Each
        # file is written exactly once beneath this newly-created directory.
        target.mkdir(parents=True, exist_ok=False)
        (target / "raw").mkdir()
        (target / "metadata").mkdir()
        (target / "manifests").mkdir()
        (target / "package.json").write_bytes(canonical_json_bytes(package) + b"\n")
        for name, content in raw_files.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for index, manifest in enumerate(package["manifests"]):
            manifest_id = self._safe_dir_name(str(manifest["manifest_id"]))
            (target / "manifests" / f"{manifest_id}.json").write_bytes(canonical_json_bytes(manifest) + b"\n")
        for index, metadata in enumerate(package.get("metadata_manifest", [])):
            content = (metadata_files or {}).get(str(metadata.get("manifest_id")))
            if content is not None:
                metadata_id = self._safe_dir_name(str(metadata["manifest_id"]))
                (target / "metadata" / f"{metadata_id}.bin").write_bytes(content)
        return {"status": "STAGED_APPEND_ONLY", "path": str(target), "package_id": package["export_package_id"], "package_hash": package["package_sha256"], "archive_written": False, "training_written": False}


class DedupeIndex:
    """Deterministic comparison index over existing manifests."""

    def __init__(self, existing: Iterable[Mapping[str, Any]] = ()) -> None:
        self.existing = tuple(existing)

    def compare(self, candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
        from . import duplicate_semantics
        results = []
        for item in self.existing:
            results.append({
                "existing_manifest_id": item.get("manifest_id"),
                "candidate_manifest_id": candidate.get("manifest_id"),
                "canonical_identity_key": canonical_identity_key(candidate["canonical_match_identity"]),
                "semantics": duplicate_semantics(item, candidate),
            })
        return results


def build_identity_index(manifests: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen: dict[str, str] = {}
    for manifest in manifests:
        identity = manifest.get("canonical_match_identity")
        key = canonical_identity_key(identity)
        duplicate_of = seen.get(key)
        rows.append({"manifest_id": manifest.get("manifest_id"), "canonical_identity_key": key, "duplicate_of_manifest_id": duplicate_of})
        if duplicate_of is None:
            seen[key] = str(manifest.get("manifest_id"))
    return rows


__all__ = ["AppendOnlyStaging", "DedupeIndex", "build_identity_index", "canonical_identity_key"]
