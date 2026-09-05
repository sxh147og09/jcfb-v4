"""Governed, read-only view over the approved historical source archive.

The reader consumes the approved manifest/file layout rather than the archive
runtime's internal ``records`` or ``manifests`` dictionaries.  It has no write,
update, delete, or import operation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from . import HASH_RE, PRE_MATCH_TYPES, POST_MATCH_TYPES, sha256_json


class ArchiveReadError(ValueError):
    pass


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveReadError("timestamp is required")
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArchiveReadError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _relative_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ArchiveReadError("archive path escaped approved root") from exc


class GovernedArchiveReader:
    """Read exact accepted archive records without exposing mutable internals."""

    def __init__(self, archive_root: str | Path = "F:/Projects/jcfb-v4/approved_data/historical_source_archive"):
        self.archive_root = Path(archive_root).resolve()
        if self.archive_root.drive.upper() != "F:":
            raise ArchiveReadError("approved archive read interface requires F: drive")
        if self.archive_root.name != "historical_source_archive" or self.archive_root.parent.name != "approved_data":
            raise ArchiveReadError("reader must bind to approved historical_source_archive root")

    def _read_entries(self) -> tuple[dict[str, Any], ...]:
        manifests_root = self.archive_root / "manifests"
        if not manifests_root.is_dir():
            return ()
        entries: list[dict[str, Any]] = []
        for manifest_path in sorted(manifests_root.glob("*.json"), key=lambda item: item.name):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact_path = self.archive_root / str(manifest.get("artifact_path", ""))
            record_ref = _relative_ref(self.archive_root, artifact_path)
            if not artifact_path.is_file() or record_ref.startswith("../"):
                raise ArchiveReadError(f"archive record is missing or escaped: {manifest_path.name}")
            record = json.loads(artifact_path.read_text(encoding="utf-8"))
            if record.get("archive_record_id") != manifest.get("archive_record_id"):
                raise ArchiveReadError(f"manifest/record identity mismatch: {manifest_path.name}")
            if record.get("artifact_hash") != manifest.get("artifact_hash") or not HASH_RE.fullmatch(str(record.get("artifact_hash", ""))):
                raise ArchiveReadError(f"artifact hash mismatch: {manifest_path.name}")
            manifest_body = dict(manifest)
            expected_manifest_hash = manifest_body.pop("manifest_hash", None)
            if expected_manifest_hash != sha256_json(manifest_body):
                raise ArchiveReadError(f"manifest hash mismatch: {manifest_path.name}")
            entry = dict(record)
            entry["record_ref"] = record_ref
            entry["manifest_ref"] = _relative_ref(self.archive_root, manifest_path)
            entry["artifact_domain"] = "post_match" if record.get("artifact_type") in POST_MATCH_TYPES else "pre_match"
            entries.append(entry)
        entries.sort(key=lambda item: (
            str(item.get("match_id", "")), str(item.get("cutoff_profile", "")),
            str(item.get("artifact_type", "")), int(item.get("revision", 0)), str(item.get("archive_record_id", ""))
        ))
        return tuple(entries)

    @staticmethod
    def _matches(entry: Mapping[str, Any], *, match_id: Optional[str], cutoff_profile: Optional[str], artifact_type: Optional[str], domain: Optional[str]) -> bool:
        return (
            (match_id is None or entry.get("match_id") == match_id)
            and (cutoff_profile is None or entry.get("cutoff_profile") == cutoff_profile)
            and (artifact_type is None or entry.get("artifact_type") == artifact_type)
            and (domain is None or entry.get("artifact_domain") == domain)
        )

    @staticmethod
    def _select_visible(entries: Iterable[Mapping[str, Any]], prediction_cutoff_at: Optional[str]) -> tuple[dict[str, Any], ...]:
        candidates = list(entries)
        if prediction_cutoff_at is None:
            return tuple(dict(entry) for entry in candidates)
        cutoff = _timestamp(prediction_cutoff_at)
        visible: list[dict[str, Any]] = []
        for entry in candidates:
            if entry.get("artifact_domain") == "post_match":
                visible.append(dict(entry))
                continue
            available = _timestamp(entry.get("source_availability_at", entry.get("availability_at")))
            if available <= cutoff:
                visible.append(dict(entry))
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in visible:
            key = (
                entry.get("match_id"), entry.get("cutoff_profile"), entry.get("artifact_type"),
                entry.get("logical_artifact_key_hash", entry.get("source_reference")), entry.get("artifact_domain"),
            )
            previous = grouped.get(key)
            if previous is None or int(entry.get("revision", 0)) > int(previous.get("revision", 0)):
                grouped[key] = entry
        return tuple(sorted(grouped.values(), key=lambda item: (
            str(item.get("artifact_domain")), str(item.get("artifact_type")),
            str(item.get("match_id")), str(item.get("cutoff_profile")), int(item.get("revision", 0)),
            str(item.get("archive_record_id")),
        )))

    def enumerate_approved_archive_records(
        self,
        *,
        match_id: Optional[str] = None,
        cutoff_profile: Optional[str] = None,
        artifact_type: Optional[str] = None,
        domain: Optional[str] = None,
        prediction_cutoff_at: Optional[str] = None,
    ) -> tuple[Mapping[str, Any], ...]:
        entries = [entry for entry in self._read_entries() if self._matches(entry, match_id=match_id, cutoff_profile=cutoff_profile, artifact_type=artifact_type, domain=domain)]
        return self._select_visible(entries, prediction_cutoff_at)

    def query_by_match_id(self, match_id: str, **kwargs: Any) -> tuple[Mapping[str, Any], ...]:
        return self.enumerate_approved_archive_records(match_id=match_id, **kwargs)

    def query_by_cutoff_profile(self, cutoff_profile: str, **kwargs: Any) -> tuple[Mapping[str, Any], ...]:
        return self.enumerate_approved_archive_records(cutoff_profile=cutoff_profile, **kwargs)

    def query_by_artifact_type(self, artifact_type: str, **kwargs: Any) -> tuple[Mapping[str, Any], ...]:
        if artifact_type not in PRE_MATCH_TYPES and artifact_type not in POST_MATCH_TYPES:
            raise ArchiveReadError("artifact type is outside the approved archive contract")
        return self.enumerate_approved_archive_records(artifact_type=artifact_type, **kwargs)

    def resolve_supersedes_chain(self, archive_record_id: str) -> tuple[Mapping[str, Any], ...]:
        entries = {entry["archive_record_id"]: entry for entry in self._read_entries()}
        current = entries.get(archive_record_id)
        if current is None:
            raise ArchiveReadError("archive record not found")
        chain: list[Mapping[str, Any]] = []
        visited: set[str] = set()
        while current is not None:
            record_id = str(current["archive_record_id"])
            if record_id in visited:
                raise ArchiveReadError("supersedes cycle detected")
            visited.add(record_id)
            chain.append(dict(current))
            predecessor = current.get("supersedes")
            current = entries.get(predecessor) if predecessor else None
        return tuple(chain)

    def deterministic_candidate_snapshot(self, *, match_id: str, cutoff_profile: str, prediction_cutoff_at: str) -> Mapping[str, Any]:
        pre_match = self.enumerate_approved_archive_records(match_id=match_id, cutoff_profile=cutoff_profile, domain="pre_match", prediction_cutoff_at=prediction_cutoff_at)
        post_match = self.enumerate_approved_archive_records(match_id=match_id, cutoff_profile=cutoff_profile, domain="post_match")
        stable_pre = [self._stable_entry(entry) for entry in pre_match]
        stable_post = [self._stable_entry(entry) for entry in post_match]
        body = {
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "prediction_cutoff_at": prediction_cutoff_at,
            "pre_match": stable_pre,
            "post_match_labels": stable_post,
        }
        body["snapshot_hash"] = sha256_json(body)
        return body

    @staticmethod
    def _stable_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "archive_record_id": entry.get("archive_record_id"),
            "record_ref": entry.get("record_ref"),
            "artifact_hash": entry.get("artifact_hash"),
            "revision": entry.get("revision"),
            "supersedes": entry.get("supersedes"),
            "artifact_type": entry.get("artifact_type"),
            "artifact_domain": entry.get("artifact_domain"),
            "source_availability_at": entry.get("source_availability_at"),
        }


__all__ = ["ArchiveReadError", "GovernedArchiveReader"]
