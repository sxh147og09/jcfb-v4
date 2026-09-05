"""Append-only V4 historical source archive runtime.

This module is deliberately independent from the V3.3.3 runtime and from the
future dataset/training pipeline.  The default storage target is the approved
F: drive archive; ``persist=False`` is provided only for isolated unit tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


CONTRACT_VERSION = "historical-source-archive@1.0.0"
WORK_PACKAGE_ID = "B15-EWP-001"
ACQUISITION_MODE = "PROSPECTIVE_CAPTURE"
ACTIVATED_AT = "2026-09-05T00:00:00+08:00"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
STATES = frozenset({"PENDING", "CAPTURED", "PARTIAL", "BLOCKED", "SUPERSEDED", "INVALID"})
ELIGIBILITY_STATES = frozenset(
    {"ELIGIBLE_FOR_AS_OF_TRAINING", "NOT_ELIGIBLE_FOR_AS_OF_TRAINING", "UNKNOWN", "BLOCKED"}
)
SCREENSHOT_VERIFICATION_STATES = frozenset(
    {"OCR_ONLY", "MANUAL_VERIFIED", "OCR_PLUS_MANUAL", "NOT_VERIFIED", "CONFLICTED"}
)
PRE_MATCH_TYPES = frozenset(
    {
        "canonical_match_facts",
        "official_odds_snapshot",
        "official_odds_screenshot",
        "external_market_snapshot",
        "team_context_source_artifact",
        "evidence_graph_ref",
        "statistical_feature_artifact_ref",
        "football_intelligence_ref",
        "market_intelligence_ref",
        "tactical_league_ref",
        "feature_bundle_ref",
        "batch14_gate_record_ref",
    }
)
POST_MATCH_TYPES = frozenset(
    {"final_result", "halftime_result", "outcome_label", "handicap_label_basis", "goals_label", "htft_label"}
)
FORBIDDEN_PAYLOAD_TERMS = frozenset(
    {
        "prediction",
        "probability",
        "confidence",
        "calibration",
        "recommendation",
        "model_output",
        "model_artifact",
        "score_engine",
        "shadow",
        "production",
        "public",
        "supabase",
        "v3_3_3",
        "v333",
        "frozen_prediction",
        "frozen_input",
        "final_score",
        "half_time_score",
    }
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveValidationError("REQUIRED_FIELD_MISSING", f"{field} must be a timezone-aware ISO-8601 timestamp")
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ArchiveValidationError("TIMESTAMP_INVALID", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArchiveValidationError("TIMEZONE_REQUIRED", f"{field} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveValidationError("REQUIRED_FIELD_MISSING", f"{field} must be non-empty")
    return value.strip()


def _safe_component(value: str, field: str) -> str:
    text = _required_text(value, field)
    if len(text) > 160 or not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        raise ArchiveValidationError("PATH_COMPONENT_INVALID", f"{field} is not a safe archive path component")
    return text


def _hash(value: Any, field: str) -> str:
    result = _required_text(value, field)
    if not HASH_RE.fullmatch(result):
        raise ArchiveValidationError("HASH_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return result


def _find_forbidden(value: Any, path: str = "payload") -> Optional[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9_]", "", str(key).casefold())
            if normalized in FORBIDDEN_PAYLOAD_TERMS:
                return f"{path}.{key}"
            found = _find_forbidden(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_forbidden(child, f"{path}[{index}]")
            if found:
                return found
    return None


class ArchiveValidationError(ValueError):
    """A fail-closed archive contract violation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CaptureResult:
    accepted: bool
    action: str
    state: str
    record: Optional[Mapping[str, Any]] = None
    manifest: Optional[Mapping[str, Any]] = None
    error_code: Optional[str] = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaptureSessionResult:
    accepted: bool
    action: str
    state: str
    session: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...] = ()
    failures: tuple[Mapping[str, str], ...] = ()


class ArchiveRuntime:
    """F-drive append-only archive for one authorized EWP-001 execution.

    The runtime has no update/delete operation.  A correction must provide the
    current predecessor identity and becomes a new immutable revision.
    """

    def __init__(self, project_root: os.PathLike[str] | str = "F:/Projects/jcfb-v4", *, persist: bool = True):
        self.project_root = Path(project_root).resolve()
        if self.project_root.drive.upper() != "F:":
            raise ArchiveValidationError("F_DRIVE_REQUIRED", "archive runtime must use the F: drive")
        self.archive_root = (self.project_root / "approved_data" / "historical_source_archive").resolve()
        self._assert_inside_project(self.archive_root)
        self.persist = persist
        self.records: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.latest_by_logical_key: dict[str, str] = {}
        self.original_files: dict[str, bytes] = {}
        if self.persist:
            self.ensure_archive_root()
            self._load_persisted()

    def _assert_inside_project(self, path: Path) -> None:
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ArchiveValidationError("ARCHIVE_PATH_ESCAPE", "archive path must remain inside the F: project") from exc

    def ensure_archive_root(self) -> Path:
        for relative in (
            "pre_match",
            "post_match",
            "manifests",
            "manifests/sessions",
            "provenance",
            "revisions",
        ):
            (self.archive_root / relative).mkdir(parents=True, exist_ok=True)
        return self.archive_root

    def _load_persisted(self) -> None:
        manifests_root = self.archive_root / "manifests"
        if not manifests_root.exists():
            return
        for path in manifests_root.glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            record_id = document.get("archive_record_id")
            if record_id:
                self.manifests[record_id] = document
                record_path = self.archive_root / document["artifact_path"]
                if record_path.exists():
                    self.records[record_id] = json.loads(record_path.read_text(encoding="utf-8"))
                    original_path = self.archive_root / self.records[record_id].get("original_artifact_path", "__missing__")
                    if self.records[record_id].get("original_artifact_path") and original_path.is_file():
                        self.original_files[record_id] = original_path.read_bytes()
                    self._index_record(self.records[record_id])
        sessions_root = manifests_root / "sessions"
        if sessions_root.exists():
            for path in sessions_root.glob("*.json"):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.sessions[document["session_id"]] = document

    def _append_json(self, path: Path, document: Mapping[str, Any]) -> bool:
        data = canonical_json_bytes(document) + b"\n"
        if self.persist and path.exists():
            if path.read_bytes() == data:
                return False
            raise ArchiveValidationError("APPEND_ONLY_PATH_COLLISION", f"existing archive path differs: {path}")
        if self.persist:
            self._assert_inside_project(path.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return True

    def _append_bytes(self, path: Path, data: bytes) -> bool:
        if self.persist and path.exists():
            if path.read_bytes() == data:
                return False
            raise ArchiveValidationError("APPEND_ONLY_PATH_COLLISION", f"existing provenance file differs: {path}")
        if self.persist:
            self._assert_inside_project(path.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return True

    def _load_original(self, artifact: Mapping[str, Any], record_id: str) -> tuple[Optional[bytes], Optional[str]]:
        raw = artifact.get("original_artifact_bytes")
        source_path = artifact.get("original_artifact_path")
        if raw is not None and source_path is not None:
            raise ArchiveValidationError("ORIGINAL_ARTIFACT_AMBIGUOUS", "provide bytes or a source path, not both")
        if raw is not None:
            if not isinstance(raw, (bytes, bytearray)):
                raise ArchiveValidationError("ORIGINAL_ARTIFACT_INVALID", "original_artifact_bytes must be bytes")
            return bytes(raw), None
        if source_path is not None:
            source = Path(str(source_path)).resolve()
            if source.drive.upper() != "F:":
                raise ArchiveValidationError("F_DRIVE_REQUIRED", "original source artifacts may not be read from C:")
            if not source.is_file():
                raise ArchiveValidationError("ORIGINAL_ARTIFACT_NOT_FOUND", "original source artifact does not exist")
            forbidden = {"tests", "fixtures", ".runtime", "v3.3.3", "v333"}
            if any(part.casefold() in forbidden for part in source.parts):
                raise ArchiveValidationError("FORBIDDEN_SOURCE_BOUNDARY", "tests, runtime, and V3 source paths are not archive inputs")
            return source.read_bytes(), source.suffix.lower() or ".bin"
        return None, None

    def _times(self, source: Mapping[str, Any], *, require_cutoff: bool = True) -> dict[str, str]:
        source_timestamp = _timestamp(source.get("source_timestamp"), "source_timestamp")
        observed = _timestamp(source.get("observed_at", source.get("source_timestamp")), "observed_at")
        captured = _timestamp(source.get("captured_at"), "captured_at")
        ingested = _timestamp(source.get("ingested_at"), "ingested_at")
        availability = _timestamp(source.get("availability_at", source.get("source_timestamp")), "availability_at")
        if require_cutoff:
            cutoff = _timestamp(source.get("prediction_cutoff_at"), "prediction_cutoff_at")
            kickoff = _timestamp(source.get("kickoff_at"), "kickoff_at")
            if not cutoff < kickoff:
                raise ArchiveValidationError("CUTOFF_INVALID", "prediction_cutoff_at must precede kickoff_at")
            if availability > cutoff or not cutoff < kickoff:
                raise ArchiveValidationError("FUTURE_INFORMATION", "source availability is after the prediction cutoff")
        else:
            cutoff = None
            kickoff = _timestamp(source.get("kickoff_at"), "kickoff_at")
        if captured < source_timestamp and source.get("capture_time_policy") != "ALLOW_CAPTURE_BEFORE_SOURCE_TIME":
            raise ArchiveValidationError("TIME_ORDER_INVALID", "captured_at cannot precede source_timestamp")
        if ingested < captured:
            raise ArchiveValidationError("TIME_ORDER_INVALID", "ingested_at cannot precede captured_at")
        result = {
            "source_timestamp": _iso(source_timestamp),
            "observed_at": _iso(observed),
            "captured_at": _iso(captured),
            "ingested_at": _iso(ingested),
            "availability_at": _iso(availability),
            "source_availability_at": _iso(availability),
            "kickoff_at": _iso(kickoff),
        }
        if cutoff is not None:
            result["prediction_cutoff_at"] = _iso(cutoff)
        return result

    def _validate_execution(self, execution_context: Mapping[str, Any]) -> None:
        if execution_context.get("work_package_id") != WORK_PACKAGE_ID:
            raise ArchiveValidationError("WORK_PACKAGE_SCOPE_INVALID", "capture requires B15-EWP-001")
        if execution_context.get("execution_authorized") is not True:
            raise ArchiveValidationError("EXECUTION_NOT_AUTHORIZED", "capture requires explicit EWP-001 authorization")
        _required_text(execution_context.get("execution_id"), "execution_id")
        started = _timestamp(execution_context.get("execution_started_at", ACTIVATED_AT), "execution_started_at")
        if started < _timestamp(ACTIVATED_AT, "activated_at"):
            raise ArchiveValidationError("CAPTURE_BEFORE_ACTIVATION", "prospective capture begins at authorization activation")

    @staticmethod
    def _index_key(match_id: str, cutoff_profile: str, artifact: Mapping[str, Any], times: Mapping[str, str]) -> str:
        source_identity = artifact.get("source_identity") or artifact.get("source")
        logical = artifact.get("logical_artifact_key") or "|".join(
            (str(artifact.get("artifact_type", "")), str(source_identity), times["source_timestamp"])
        )
        return sha256_json({"match_id": match_id, "cutoff_profile": cutoff_profile, "logical_artifact_key": logical})

    def _index_record(self, record: Mapping[str, Any]) -> None:
        self.latest_by_logical_key[record["logical_artifact_key_hash"]] = record["archive_record_id"]

    def _next_revision(self, logical_hash: str, supersedes: Optional[str], supplied: Any) -> tuple[int, Optional[str]]:
        previous_id = self.latest_by_logical_key.get(logical_hash)
        if previous_id is None:
            if supersedes:
                raise ArchiveValidationError("SUPERSEDES_UNKNOWN", "supersedes must reference the current logical predecessor")
            revision = 1
        else:
            previous = self.records[previous_id]
            if supplied is not None and supplied != previous["revision"] + 1:
                raise ArchiveValidationError("REVISION_INVALID", "revision must be the exact next revision")
            if not supersedes:
                raise ArchiveValidationError("SUPERSEDES_REQUIRED", "a changed logical artifact must supersede its predecessor")
            if supersedes != previous_id:
                raise ArchiveValidationError("SUPERSEDES_NOT_LATEST", "corrections must supersede the latest revision")
            revision = previous["revision"] + 1
        if supplied is not None and supplied != revision:
            raise ArchiveValidationError("REVISION_INVALID", "revision does not match the append-only sequence")
        return revision, previous_id

    def _build_record(
        self,
        *,
        match_id: str,
        match_identity: Mapping[str, Any],
        cutoff_profile: str,
        artifact: Mapping[str, Any],
        execution_context: Mapping[str, Any],
        post_match: bool = False,
        labels: bool = False,
    ) -> CaptureResult:
        artifact_type = _safe_component(str(artifact.get("artifact_type", "")), "artifact_type")
        allowed = POST_MATCH_TYPES if post_match else PRE_MATCH_TYPES
        if artifact_type not in allowed:
            raise ArchiveValidationError("ARTIFACT_TYPE_INVALID", f"{artifact_type} is outside this archive boundary")
        source = _required_text(artifact.get("source"), "source")
        source_reference = _required_text(artifact.get("source_reference"), "source_reference")
        times = self._times(artifact, require_cutoff=not post_match)
        if post_match and _timestamp(artifact["source_timestamp"], "source_timestamp") < _timestamp(times["kickoff_at"], "kickoff_at"):
            raise ArchiveValidationError("LABEL_TIME_INVALID", "post-match label source time must not precede kickoff")
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping) or not payload:
            raise ArchiveValidationError("PAYLOAD_REQUIRED", "only an existing non-empty structured artifact may be captured")
        forbidden_path = _find_forbidden(payload)
        if post_match and forbidden_path and forbidden_path.rsplit(".", 1)[-1] in {"final_score", "half_time_score"}:
            forbidden_path = None
        if forbidden_path:
            raise ArchiveValidationError("MODEL_FIELD_FORBIDDEN", f"forbidden model/output field: {forbidden_path}")
        if not isinstance(match_identity, Mapping) or match_identity.get("match_id") != match_id:
            raise ArchiveValidationError("MATCH_IDENTITY_INVALID", "match_identity must resolve to match_id")
        original_bytes, suffix = self._load_original(artifact, "pending")
        original_hash = sha256_bytes(original_bytes) if original_bytes is not None else sha256_json(payload)
        supplied_original_hash = artifact.get("original_payload_or_file_hash")
        if supplied_original_hash is not None and _hash(supplied_original_hash, "original_payload_or_file_hash") != original_hash:
            raise ArchiveValidationError("HASH_MISMATCH", "original payload/file hash does not match the supplied artifact")
        source_identity = _required_text(artifact.get("source_identity", source), "source_identity")
        logical_hash = self._index_key(match_id, cutoff_profile, artifact, times)
        previous_id = self.latest_by_logical_key.get(logical_hash)
        if previous_id is not None:
            previous = self.records[previous_id]
            if (
                previous.get("source_reference") == source_reference
                and previous.get("original_payload_or_file_hash") == original_hash
                and previous.get("payload") == dict(payload)
            ):
                return CaptureResult(True, "DUPLICATE_NOOP", "CAPTURED", previous, self.manifests[previous_id])
        artifact_body: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "acquisition_mode": ACQUISITION_MODE if not post_match else "PROSPECTIVE_CAPTURE_POST_MATCH_LABEL",
            "archive_record_id": "PENDING",
            "match_id": match_id,
            "match_identity": dict(match_identity),
            "cutoff_profile": cutoff_profile,
            "artifact_type": artifact_type,
            "source": source,
            "source_identity": source_identity,
            "source_reference": source_reference,
            **times,
            "revision": 0,
            "supersedes": artifact.get("supersedes"),
            "logical_artifact_key_hash": logical_hash,
            "original_payload_or_file_hash": original_hash,
            "provenance": dict(artifact.get("provenance", {})),
            "payload": dict(payload),
            "capture_state": "CAPTURED",
            "eligibility_state": "ELIGIBLE_FOR_AS_OF_TRAINING" if not post_match else "UNKNOWN",
            "execution_context": {"work_package_id": execution_context["work_package_id"], "execution_id": execution_context["execution_id"]},
        }
        revision, previous_id = self._next_revision(logical_hash, artifact.get("supersedes"), artifact.get("revision"))
        artifact_body["revision"] = revision
        artifact_body["supersedes"] = previous_id
        if post_match:
            artifact_body["label_scope"] = "POST_MATCH_ONLY"
        if original_bytes is not None:
            artifact_body["original_artifact_extension"] = suffix or ".bin"
        provenance = {
            "source": source,
            "source_reference": source_reference,
            "source_timestamp": times["source_timestamp"],
            "observed_at": times["observed_at"],
            "captured_at": times["captured_at"],
            "ingested_at": times["ingested_at"],
            "availability_at": times["availability_at"],
            "original_payload_or_file_hash": original_hash,
            "match_identity": dict(match_identity),
            "revision": revision,
            "supersedes": previous_id,
            "provenance": dict(artifact.get("provenance", {})),
        }
        artifact_body["provenance"] = provenance
        artifact_body["provenance_hash"] = sha256_json(provenance)
        stable_id_input = {
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "artifact_type": artifact_type,
            "logical_artifact_key_hash": logical_hash,
            "revision": revision,
            "original_payload_or_file_hash": original_hash,
        }
        record_id = "asa-" + hashlib.sha256(canonical_json_bytes(stable_id_input)).hexdigest()[:32]
        artifact_body["archive_record_id"] = record_id
        if original_bytes is not None:
            extension = suffix or ".bin"
            original_path = self.archive_root / "provenance" / record_id / f"original{extension}"
            artifact_body["original_artifact_path"] = original_path.relative_to(self.archive_root).as_posix()
        artifact_hash = sha256_json(artifact_body)
        artifact_body["artifact_hash"] = artifact_hash
        if record_id in self.records:
            raise ArchiveValidationError("APPEND_ONLY_PATH_COLLISION", "deterministic record identity already has different content")
        relative_dir = Path("post_match" if post_match else "pre_match") / _safe_component(match_id, "match_id") / _safe_component(cutoff_profile, "cutoff_profile") / artifact_type
        artifact_path = self.archive_root / relative_dir / f"r{revision:03d}-{record_id}.json"
        relative_artifact_path = artifact_path.relative_to(self.archive_root).as_posix()
        manifest_body: dict[str, Any] = {
            "archive_record_id": record_id,
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "artifact_type": artifact_type,
            "source_identity": source_identity,
            "source_reference": source_reference,
            "source_timestamp": times["source_timestamp"],
            "artifact_hash": artifact_hash,
            "original_payload_or_file_hash": original_hash,
            "provenance_hash": artifact_body["provenance_hash"],
            "revision": revision,
            "supersedes": previous_id,
            "capture_status": "CAPTURED",
            "capture_state": "CAPTURED",
            "eligibility_state": artifact_body["eligibility_state"],
            "artifact_path": relative_artifact_path,
            "acquisition_mode": artifact_body["acquisition_mode"],
        }
        manifest_body["manifest_hash"] = sha256_json(manifest_body)
        if self.persist:
            self._append_json(artifact_path, artifact_body)
            self._append_json(self.archive_root / "manifests" / f"{record_id}.json", manifest_body)
            if original_bytes is not None:
                self._append_bytes(original_path, original_bytes)
        self.records[record_id] = artifact_body
        self.manifests[record_id] = manifest_body
        self.original_files[record_id] = original_bytes or b""
        self._index_record(artifact_body)
        return CaptureResult(True, "APPENDED", "CAPTURED", artifact_body, manifest_body)

    def capture_pre_match(
        self,
        *,
        match_id: str,
        match_identity: Mapping[str, Any],
        cutoff_profile: str,
        artifacts: Sequence[Mapping[str, Any]],
        execution_context: Mapping[str, Any],
    ) -> CaptureSessionResult:
        self._validate_execution(execution_context)
        match_id = _safe_component(match_id, "match_id")
        cutoff_profile = _safe_component(cutoff_profile, "cutoff_profile")
        if not artifacts:
            session = self._session(match_id, cutoff_profile, "BLOCKED", (), ({"code": "NO_REAL_ARTIFACTS", "message": "no artifact was supplied"},))
            return CaptureSessionResult(False, "BLOCKED", "BLOCKED", session, failures=(session["failures"][0],))
        accepted: list[Mapping[str, Any]] = []
        failures: list[Mapping[str, str]] = []
        for artifact in artifacts:
            try:
                result = self._build_record(
                    match_id=match_id,
                    match_identity=match_identity,
                    cutoff_profile=cutoff_profile,
                    artifact=artifact,
                    execution_context=execution_context,
                )
                if result.record:
                    accepted.append(result.record)
            except ArchiveValidationError as exc:
                failures.append({"code": exc.code, "message": exc.message})
        state = "CAPTURED" if accepted and not failures else "PARTIAL" if accepted else "BLOCKED"
        session = self._session(match_id, cutoff_profile, state, tuple(item["archive_record_id"] for item in accepted), tuple(failures))
        return CaptureSessionResult(bool(accepted), "APPENDED" if accepted else "BLOCKED", state, session, tuple(accepted), tuple(failures))

    def _session(
        self,
        match_id: str,
        cutoff_profile: str,
        state: str,
        record_ids: Sequence[str],
        failures: Sequence[Mapping[str, str]],
    ) -> Mapping[str, Any]:
        body = {
            "contract_version": CONTRACT_VERSION,
            "session_id": "asession-" + hashlib.sha256(canonical_json_bytes({"match_id": match_id, "cutoff_profile": cutoff_profile, "records": list(record_ids), "failures": list(failures)})).hexdigest()[:32],
            "archive_record_id": "capture-session",
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "artifact_type": "capture_session",
            "capture_status": state,
            "capture_state": state,
            "record_ids": list(record_ids),
            "failures": [dict(item) for item in failures],
            "archive_root": str(self.archive_root),
        }
        body["manifest_hash"] = sha256_json(body)
        session_id = body["session_id"]
        existing = self.sessions.get(session_id)
        if existing:
            return existing
        if self.persist:
            self._append_json(self.archive_root / "manifests" / "sessions" / f"{session_id}.json", body)
        self.sessions[session_id] = body
        return body

    def ingest_official_screenshot(
        self,
        *,
        match_id: str,
        match_identity: Mapping[str, Any],
        cutoff_profile: str,
        source: str,
        source_reference: str,
        source_timestamp: str,
        captured_at: str,
        ingested_at: str,
        prediction_cutoff_at: str,
        kickoff_at: str,
        captured_snapshot: Mapping[str, Any],
        verification_state: str,
        execution_context: Mapping[str, Any],
        original_artifact_bytes: Optional[bytes] = None,
        original_artifact_path: Optional[os.PathLike[str] | str] = None,
        observed_at: Optional[str] = None,
        provenance: Optional[Mapping[str, Any]] = None,
        supersedes: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> CaptureResult:
        if verification_state not in SCREENSHOT_VERIFICATION_STATES:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="SCREENSHOT_VERIFICATION_STATE_INVALID")
        if original_artifact_bytes is None and original_artifact_path is None:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="ORIGINAL_ARTIFACT_REQUIRED", reason_codes=("PROVENANCE_ROOT_MISSING",))
        if not isinstance(captured_snapshot, Mapping) or not captured_snapshot:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="CAPTURED_SNAPSHOT_REQUIRED")
        payload = {
            "source_is_official": True,
            "original_artifact_present": True,
            "ocr_manual_verification_state": verification_state,
            "captured_snapshot": dict(captured_snapshot),
            "match_mapping": {"match_id": match_id},
        }
        artifact = {
            "artifact_type": "official_odds_screenshot",
            "source": source,
            "source_identity": source,
            "source_reference": source_reference,
            "source_timestamp": source_timestamp,
            "observed_at": observed_at or source_timestamp,
            "captured_at": captured_at,
            "ingested_at": ingested_at,
            "availability_at": source_timestamp,
            "prediction_cutoff_at": prediction_cutoff_at,
            "kickoff_at": kickoff_at,
            "payload": payload,
            "provenance": dict(provenance or {}),
            "original_artifact_bytes": original_artifact_bytes,
            "original_artifact_path": original_artifact_path,
            "supersedes": supersedes,
            "revision": revision,
            "logical_artifact_key": f"official-screenshot|{source}|{source_timestamp}",
        }
        try:
            return self._build_record(match_id=match_id, match_identity=match_identity, cutoff_profile=cutoff_profile, artifact=artifact, execution_context=execution_context)
        except ArchiveValidationError as exc:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code=exc.code, reason_codes=(exc.code,))

    def ingest_external_snapshot(
        self,
        *,
        match_id: str,
        match_identity: Mapping[str, Any],
        cutoff_profile: str,
        provider: str,
        market_type: str,
        line: str | int | float,
        prices: Mapping[str, Any],
        source_reference: str,
        source_timestamp: str,
        captured_at: str,
        ingested_at: str,
        prediction_cutoff_at: str,
        kickoff_at: str,
        execution_context: Mapping[str, Any],
        observed_at: Optional[str] = None,
        provenance: Optional[Mapping[str, Any]] = None,
        supersedes: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> CaptureResult:
        provider = _required_text(provider, "provider")
        if provider.casefold() in {"consensus", "aggregate", "aggregated", "unknown"}:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="PROVIDER_SNAPSHOT_REQUIRED")
        if not isinstance(prices, Mapping) or not prices:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="PRICES_REQUIRED")
        payload = {"source_is_official": False, "provider": provider, "market_type": market_type, "line": line, "prices": dict(prices)}
        artifact = {
            "artifact_type": "external_market_snapshot",
            "source": provider,
            "source_identity": provider,
            "source_reference": source_reference,
            "source_timestamp": source_timestamp,
            "observed_at": observed_at or source_timestamp,
            "captured_at": captured_at,
            "ingested_at": ingested_at,
            "availability_at": source_timestamp,
            "prediction_cutoff_at": prediction_cutoff_at,
            "kickoff_at": kickoff_at,
            "payload": payload,
            "provenance": dict(provenance or {}),
            "supersedes": supersedes,
            "revision": revision,
            "logical_artifact_key": f"external|{provider}|{market_type}|{line}|{source_timestamp}",
        }
        try:
            return self._build_record(match_id=match_id, match_identity=match_identity, cutoff_profile=cutoff_profile, artifact=artifact, execution_context=execution_context)
        except ArchiveValidationError as exc:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code=exc.code, reason_codes=(exc.code,))

    def append_post_match_labels(
        self,
        *,
        match_id: str,
        match_identity: Mapping[str, Any],
        cutoff_profile: str,
        labels: Mapping[str, Any],
        source: str,
        source_reference: str,
        source_timestamp: str,
        captured_at: str,
        ingested_at: str,
        kickoff_at: str,
        execution_context: Mapping[str, Any],
        observed_at: Optional[str] = None,
        provenance: Optional[Mapping[str, Any]] = None,
        supersedes: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> CaptureResult:
        if not isinstance(labels, Mapping) or not labels:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="LABELS_REQUIRED")
        forbidden_path = _find_forbidden(labels)
        if forbidden_path and forbidden_path.rsplit(".", 1)[-1] not in {"final_score", "half_time_score"}:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code="LABEL_PAYLOAD_INVALID")
        artifact = {
            "artifact_type": "final_result",
            "source": source,
            "source_identity": source,
            "source_reference": source_reference,
            "source_timestamp": source_timestamp,
            "observed_at": observed_at or source_timestamp,
            "captured_at": captured_at,
            "ingested_at": ingested_at,
            "kickoff_at": kickoff_at,
            "payload": dict(labels),
            "provenance": dict(provenance or {}),
            "supersedes": supersedes,
            "revision": revision,
            "logical_artifact_key": f"post-match-labels|{source}|{source_timestamp}",
        }
        try:
            return self._build_record(match_id=match_id, match_identity=match_identity, cutoff_profile=cutoff_profile, artifact=artifact, execution_context=execution_context, post_match=True, labels=True)
        except ArchiveValidationError as exc:
            return CaptureResult(False, "BLOCKED", "BLOCKED", error_code=exc.code, reason_codes=(exc.code,))

    def evaluate_verified_historical_candidate(self, candidate: Mapping[str, Any]) -> Mapping[str, Any]:
        """Evaluate only; EWP-001 never imports a historical candidate."""
        reasons: list[str] = []
        if candidate.get("raw_artifact_exists") is not True:
            reasons.append("RAW_ARTIFACT_MISSING")
        if not candidate.get("historical_source_timestamp"):
            reasons.append("HISTORICAL_SOURCE_TIMESTAMP_MISSING")
        if not candidate.get("original_source_identifiable"):
            reasons.append("ORIGINAL_SOURCE_UNIDENTIFIED")
        if not candidate.get("match_identity_resolvable"):
            reasons.append("MATCH_IDENTITY_UNRESOLVED")
        if not candidate.get("provenance_intact"):
            reasons.append("PROVENANCE_INTACT_REQUIRED")
        if candidate.get("references_v3_3_3"):
            reasons.append("V3_3_3_REFERENCE_FORBIDDEN")
        eligible = not reasons
        return {
            "acquisition_mode": "VERIFIED_HISTORICAL_BACKFILL",
            "status": "ELIGIBLE_FOR_AS_OF_TRAINING" if eligible else "NOT_ELIGIBLE_FOR_AS_OF_TRAINING",
            "import_action": "NOT_PERFORMED",
            "reason_codes": reasons or ["CANDIDATE_MEETS_INTERFACE_PREDICATES_BUT_IMPORT_NOT_AUTHORIZED_IN_EWP001"],
            "training_dataset_effect": "NONE",
        }

    def verify_provenance_replay(self, archive_record_id: str) -> Mapping[str, Any]:
        record = self.records.get(archive_record_id)
        manifest = self.manifests.get(archive_record_id)
        if not record or not manifest:
            return {"status": "BLOCKED", "reason": "ARCHIVE_RECORD_NOT_FOUND"}
        body = dict(record)
        expected_artifact_hash = body.pop("artifact_hash")
        artifact_ok = expected_artifact_hash == sha256_json(body)
        provenance_ok = record["provenance_hash"] == sha256_json(record["provenance"])
        manifest_body = dict(manifest)
        expected_manifest_hash = manifest_body.pop("manifest_hash")
        manifest_ok = expected_manifest_hash == sha256_json(manifest_body)
        original_ok = True
        if record.get("original_artifact_path"):
            original = self.original_files.get(record["archive_record_id"])
            original_ok = original is not None and record["original_payload_or_file_hash"] == sha256_bytes(original)
        return {
            "status": "PASS" if artifact_ok and provenance_ok and manifest_ok and original_ok else "BLOCKED",
            "artifact_hash": "PASS" if artifact_ok else "FAIL",
            "provenance_hash": "PASS" if provenance_ok else "FAIL",
            "manifest_hash": "PASS" if manifest_ok else "FAIL",
            "original_artifact_hash": "PASS" if original_ok else "FAIL",
        }

    def counts(self) -> Mapping[str, Any]:
        matches = {record["match_id"] for record in self.records.values() if record.get("acquisition_mode") == ACQUISITION_MODE}
        return {"archived_match_count": len(matches), "usable_training_sample_count": "NOT_COMPUTED"}


from .read_interface import ArchiveReadError, GovernedArchiveReader
from .replay_policy import REPLAY_REQUIRED, select_reconstruction_path


__all__ = [
    "ACTIVATED_AT",
    "ArchiveRuntime",
    "ArchiveValidationError",
    "CaptureResult",
    "CaptureSessionResult",
    "CONTRACT_VERSION",
    "ELIGIBILITY_STATES",
    "PRE_MATCH_TYPES",
    "POST_MATCH_TYPES",
    "ArchiveReadError",
    "GovernedArchiveReader",
    "REPLAY_REQUIRED",
    "canonical_json_bytes",
    "sha256_bytes",
    "sha256_json",
    "select_reconstruction_path",
]
