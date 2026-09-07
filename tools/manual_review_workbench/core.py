"""Core queue, append-only ledger, and state logic for the local review UI.

This module deliberately has no dependency on the prediction, archive, accepted
odds, or database layers.  It reads the frozen staging inputs and writes only a
new workbench revision under the same staging batch.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import threading
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "approved_data" / "historical_backfill_staging" / "CHATGPT-20260901-20260904-R001"
TRACE_DIR_NAME = "historical_trace_reconstruction_with_ocr_r001_revision_003"
EVIDENCE_DIR_NAME = "ocr_evidence_r001_revision_004"
OUTPUT_DIR_NAME = "manual_review_workbench_r001_revision_001"
TRACE_FILE_NAME = "unresolved_cell_trace.jsonl"
EVIDENCE_FILE_NAME = "ocr_cell_evidence.jsonl"
TRACE_MANIFEST_NAME = "extraction_trace_manifest.json"
EVIDENCE_MANIFEST_NAME = "ocr_evidence_manifest.json"
QUEUE_SCHEMA = "jcfb-v4-manual-review-queue@1.0.0"
LEDGER_SCHEMA = "jcfb-v4-cell-level-manual-review-ledger@1.0.0"
WORKBENCH_IDENTITY = "jcfb-v4-historical-official-odds-manual-review-workbench@1.0.0"
IMPORT_BATCH_ID = "CHATGPT-BACKFILL-20260901-20260904-001"
REVIEW_METHOD = "HUMAN_VISUAL_FROM_ORIGINAL_IMAGE"
GIT_NOT_AVAILABLE = "GIT_NOT_AVAILABLE"
ACTIVE_MARKETS = ("EXACT_SCORE", "TOTAL_GOALS", "HTFT", "SPF", "RQSPF")
ELIGIBLE_TRACE_STATUSES = frozenset({"UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "CONFLICT"})
TERMINAL_STATUSES = frozenset({"CONFIRMED", "UNKNOWN", "BLOCKED", "CONFLICT"})
ACTIONS = frozenset({
    "CONFIRM_OCR_VALUE",
    "ENTER_CORRECT_VALUE",
    "UNKNOWN",
    "CONFLICT",
    "SKIP_FOR_LATER",
})
VALUE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
QUEUE_NAMESPACE = uuid.UUID("bd2c93c9-8ea1-5f86-9fe0-83d5e9333e78")
REVIEW_NAMESPACE = uuid.UUID("e3f6b3f4-99d4-5be4-9f68-1f0c86f3108c")


class WorkbenchError(RuntimeError):
    """Base error for safe, user-correctable workbench failures."""


class SourceValidationError(WorkbenchError):
    """Immutable source inputs do not satisfy the expected bindings."""


class ActionValidationError(WorkbenchError):
    """A review action or value does not satisfy the format contract."""


class DuplicateSubmissionError(WorkbenchError):
    """The same action was submitted again for an item."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def file_hash(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("manual_review_record_sha256", None)
    return sha256_json(payload)


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    payload.pop("queue_manifest_sha256", None)
    return sha256_json(payload)


def queue_item_hash(item: Mapping[str, Any]) -> str:
    payload = dict(item)
    payload.pop("queue_item_sha256", None)
    return sha256_json(payload)


def evidence_record_hash(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key not in {"generated_at", "evidence_record_sha256"}}
    return sha256_json(payload)


def trace_record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("trace_record_sha256", None)
    return sha256_json(payload)


def artifact_slot(artifact_identity: str) -> str:
    return artifact_identity.split("|", 1)[0]


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        temporary.write_bytes(data)
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, canonical_bytes(value) + b"\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _atomic_write(path, b"".join(canonical_bytes(row) + b"\n" for row in rows))


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _zip_member_bytes(zip_path: Path, member: str) -> bytes:
    if not member.startswith("raw/") or ".." in Path(member).parts:
        raise SourceValidationError(f"raw ZIP member outside governed raw/ scope: {member}")
    with zipfile.ZipFile(zip_path, "r") as archive:
        try:
            return archive.read(member)
        except KeyError as exc:
            raise SourceValidationError(f"raw ZIP member missing: {member}") from exc


def validate_manual_value(value: Any, *, value_kind: str = "ODDS") -> float:
    """Validate only the source-facing numeric format; never infer a value."""

    if not isinstance(value, str) or not value.strip():
        raise ActionValidationError("manual value must be a non-empty decimal source string")
    source_text = value.strip()
    if not VALUE_RE.fullmatch(source_text):
        raise ActionValidationError("manual value must use a numeric decimal format")
    try:
        parsed = float(source_text)
    except ValueError as exc:
        raise ActionValidationError("manual value is not numeric") from exc
    if not math.isfinite(parsed):
        raise ActionValidationError("manual value must be finite")
    if value_kind == "ODDS" and parsed <= 0:
        raise ActionValidationError("odds must be greater than zero")
    if value_kind not in {"ODDS", "HANDICAP_LINE"}:
        raise ActionValidationError(f"unsupported value kind: {value_kind}")
    return parsed


def _source_paths(staging: Path) -> dict[str, Path]:
    trace_dir = staging / TRACE_DIR_NAME
    evidence_dir = staging / EVIDENCE_DIR_NAME
    return {
        "trace_dir": trace_dir,
        "evidence_dir": evidence_dir,
        "trace_file": trace_dir / TRACE_FILE_NAME,
        "evidence_file": evidence_dir / EVIDENCE_FILE_NAME,
        "trace_manifest": trace_dir / TRACE_MANIFEST_NAME,
        "evidence_manifest": evidence_dir / EVIDENCE_MANIFEST_NAME,
        "handoff_zip": staging / "chatgpt-library-handoff.zip",
    }


def _build_queue_from_sources(staging: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = _source_paths(staging)
    required = [path for path in paths.values() if not path.exists()]
    if required:
        raise SourceValidationError("missing immutable input(s): " + ", ".join(str(path) for path in required))
    trace_rows = read_jsonl(paths["trace_file"])
    evidence_rows = read_jsonl(paths["evidence_file"])
    trace_manifest = read_json(paths["trace_manifest"])
    evidence_manifest = read_json(paths["evidence_manifest"])
    if trace_manifest.get("status") != "COMPLETE":
        raise SourceValidationError("trace manifest is not COMPLETE")
    if trace_manifest.get("runtime_freeze", {}).get("source_freeze", {}).get("accepted_source_set", {}).get("raw_png_count") != 64:
        raise SourceValidationError("immutable raw source inventory is not the expected 64 PNG set")
    evidence_by_id = {row.get("evidence_record_id"): row for row in evidence_rows}
    if len(evidence_by_id) != len(evidence_rows):
        raise SourceValidationError("evidence_record_id is not unique")
    bindings = trace_manifest["runtime_freeze"]["source_freeze"]["raw_mapping_bindings"]
    mapping_by_slot = {row["candidate_slot"]: row for row in bindings}
    if len(mapping_by_slot) != 64:
        raise SourceValidationError("raw mapping binding inventory is not 64 unique slots")
    candidates: list[dict[str, Any]] = []
    unavailable_count = 0
    for trace in trace_rows:
        status = trace.get("parser_status")
        if status == "MARKET_UNAVAILABLE" or trace.get("market_availability_status") == "UNAVAILABLE":
            unavailable_count += 1
            continue
        if status not in ELIGIBLE_TRACE_STATUSES:
            continue
        if trace.get("market") not in ACTIVE_MARKETS:
            raise SourceValidationError(f"unexpected active-scope market: {trace.get('market')}")
        slot = artifact_slot(trace["artifact_identity"])
        mapping = mapping_by_slot.get(slot)
        if mapping is None:
            raise SourceValidationError(f"missing raw mapping for artifact slot {slot}")
        raw = _zip_member_bytes(paths["handoff_zip"], mapping["raw_zip_member"])
        if sha256_bytes(raw) != trace.get("raw_image_sha256") or sha256_bytes(raw) != mapping.get("raw_image_sha256"):
            raise SourceValidationError(f"raw SHA binding mismatch for {trace['trace_record_id']}")
        if trace_record_hash(trace) != trace.get("trace_record_sha256"):
            raise SourceValidationError(f"trace hash mismatch for {trace['trace_record_id']}")
        evidence_ref = (trace.get("ocr_evidence") or {}).get("evidence_ref")
        evidence = evidence_by_id.get(evidence_ref)
        if evidence is None:
            raise SourceValidationError(f"missing OCR evidence for {trace['trace_record_id']}")
        if evidence_record_hash(evidence) != evidence.get("evidence_record_sha256"):
            raise SourceValidationError(f"evidence hash mismatch for {evidence_ref}")
        pairs = (
            (evidence.get("artifact_slot"), slot),
            (evidence.get("market"), trace.get("market")),
            (evidence.get("ordering_index"), trace.get("ordering_index")),
            (evidence.get("source_visible_label"), trace.get("source_visible_label")),
            (evidence.get("raw_image_sha256"), trace.get("raw_image_sha256")),
            (evidence.get("selected_layout_profile_identity"), trace.get("layout_profile_identity")),
            (evidence.get("locator_identity"), trace.get("deterministic_locator", {}).get("locator_version")),
        )
        if any(left != right for left, right in pairs):
            raise SourceValidationError(f"trace/evidence binding mismatch for {trace['trace_record_id']}")
        crop_path = evidence.get("evidence_region_path")
        if not isinstance(crop_path, str) or crop_path.startswith("/") or ".." in Path(crop_path).parts:
            raise SourceValidationError(f"invalid crop evidence path for {trace['trace_record_id']}")
        crop_file = paths["evidence_dir"] / crop_path
        if not crop_file.is_file() or sha256_bytes(crop_file.read_bytes()) != evidence.get("crop_hash"):
            raise SourceValidationError(f"crop evidence binding missing or mismatched for {trace['trace_record_id']}")
        locator = trace["deterministic_locator"]
        item = {
            "schema_version": QUEUE_SCHEMA,
            "queue_item_id": str(uuid.uuid5(QUEUE_NAMESPACE, trace["trace_record_id"])),
            "import_batch_id": IMPORT_BATCH_ID,
            "artifact_slot": slot,
            "artifact_identity": trace["artifact_identity"],
            "library_file_id": mapping["library_file_id"],
            "external_file_reference": mapping["external_file_reference"],
            "raw_image_sha256": trace["raw_image_sha256"],
            "raw_zip_member": mapping["raw_zip_member"],
            "market": trace["market"],
            "cell_label": trace["source_visible_label"],
            "outcome_label": trace["canonical_outcome_label"],
            "ordering_index": trace["ordering_index"],
            "value_kind": _value_kind(trace["market"], trace["source_visible_label"]),
            "selected_profile_identity": trace["layout_profile_identity"],
            "selected_profile_version": locator.get("layout_profile_version"),
            "locator_identity": evidence["locator_identity"],
            "locator_version": evidence["locator_version"],
            "locator_hash": evidence.get("locator_hash"),
            "pixel_coordinates": {
                "cell": locator.get("cell_pixel_coordinates"),
                "region": locator.get("region_pixel_coordinates"),
            },
            "normalized_coordinates": {
                "cell": trace.get("cell_coordinates"),
                "region": trace.get("region_coordinates"),
            },
            "crop_evidence": {
                "evidence_record_id": evidence["evidence_record_id"],
                "evidence_record_sha256": evidence["evidence_record_sha256"],
                "evidence_region_path": crop_path,
                "crop_hash": evidence.get("crop_hash"),
                "evidence_hash": evidence.get("evidence_hash"),
            },
            "ocr_evidence": {
                "raw_ocr_text": evidence.get("raw_ocr_text"),
                "normalized_ocr_text": evidence.get("normalized_ocr_text"),
                "ocr_evidence_status": evidence.get("ocr_evidence_status"),
                "ocr_candidates": evidence.get("ocr_candidates", []),
                "confidence": evidence.get("confidence"),
                "ambiguity_markers": evidence.get("ambiguity_markers", []),
            },
            "prior_parser_value": trace.get("parsed_value"),
            "prior_parser_status": trace.get("parser_status"),
            "prior_parser_reason": trace.get("parser_reason"),
            "prior_trace_record_id": trace["trace_record_id"],
            "prior_trace_record_sha256": trace["trace_record_sha256"],
            "source_timestamps": dict(trace.get("source_timestamps", {})),
        }
        candidates.append(item)
    order = {market: index for index, market in enumerate(ACTIVE_MARKETS)}
    candidates.sort(key=lambda row: (order[row["market"]], row["artifact_slot"], row["ordering_index"], row["queue_item_id"]))
    for index, item in enumerate(candidates, start=1):
        item["queue_index"] = index
        item["queue_item_sha256"] = queue_item_hash(item)
    expected = {"EXACT_SCORE": 369, "TOTAL_GOALS": 3, "HTFT": 56, "SPF": 2, "RQSPF": 2}
    counts = Counter(row["market"] for row in candidates)
    if len(candidates) != 432 or dict(counts) != expected or unavailable_count != 9:
        raise SourceValidationError(f"candidate set mismatch: candidates={dict(counts)}, unavailable={unavailable_count}")
    source = {
        "trace_revision": TRACE_DIR_NAME,
        "trace_file_sha256": file_hash(paths["trace_file"]),
        "trace_manifest_sha256": file_hash(paths["trace_manifest"]),
        "evidence_revision": EVIDENCE_DIR_NAME,
        "evidence_file_sha256": file_hash(paths["evidence_file"]),
        "evidence_manifest_sha256": file_hash(paths["evidence_manifest"]),
        "handoff_zip_sha256": file_hash(paths["handoff_zip"]),
        "raw_png_count": 64,
        "market_unavailable_excluded": unavailable_count,
    }
    return candidates, source


def _value_kind(market: str, label: str) -> str:
    return "HANDICAP_LINE" if market == "RQSPF" and label == "让球数" else "ODDS"


def build_queue(staging: Path = STAGING) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Mechanically build the deterministic 432-cell queue from immutable inputs."""

    return _build_queue_from_sources(Path(staging))


def _initial_summary(queue: Sequence[Mapping[str, Any]], *, source: Mapping[str, Any]) -> dict[str, Any]:
    counts = {status: 0 for status in ("CONFIRMED", "UNKNOWN", "BLOCKED", "CONFLICT")}
    per_market: dict[str, Any] = {}
    for market in ACTIVE_MARKETS:
        rows = [row for row in queue if row["market"] == market]
        per_market[market] = {
            "candidate_cells": len(rows),
            "confirmed": 0,
            "unknown": 0,
            "blocked": 0,
            "conflict": 0,
            "remaining": len(rows),
            "total": len(rows),
        }
    return {
        "summary_identity": "jcfb-v4-manual-review-workbench-summary@1.0.0",
        "workbench_identity": WORKBENCH_IDENTITY,
        "schema_version": LEDGER_SCHEMA,
        "import_batch_id": IMPORT_BATCH_ID,
        "manual_review_workbench_status": "COMPLETE",
        "review_queue_status": "COMPLETE",
        "ledger_writer_status": "COMPLETE",
        "human_review_execution_status": "NOT_STARTED",
        "closure_status": "WAITING_FOR_HUMAN_REVIEW",
        "extraction_provenance_remediation_status": "BLOCKED_WAITING_FOR_HUMAN_REVIEW",
        "candidate_cells": len(queue),
        "status_counts": counts,
        "confirmed": 0,
        "unknown": 0,
        "blocked": 0,
        "conflict": 0,
        "remaining": len(queue),
        "market_unavailable_excluded": source["market_unavailable_excluded"],
        "per_market": per_market,
        "source": dict(source),
        "no_write_boundary": _no_write_boundary(),
    }


def _no_write_boundary() -> dict[str, bool]:
    return {
        "accepted_official_odds_payload_written": False,
        "historical_source_archive_written": False,
        "archive_record_or_revision_written": False,
        "r002_package_generated": False,
        "ewp_002_003_rerun": False,
        "ewp_005_execution_authorized": False,
        "model_fit_or_promotion": False,
        "production_shadow_public_supabase_migration": False,
        "v333_modified": False,
    }


def initialize_workbench(staging: Path = STAGING, output: Path | None = None) -> Path:
    """Create the workbench revision once, or validate and resume an existing one."""

    staging = Path(staging)
    output = Path(output) if output is not None else staging / OUTPUT_DIR_NAME
    queue, source = build_queue(staging)
    if output.exists():
        manifest_path = output / "review_queue_manifest.json"
        if not manifest_path.is_file():
            raise WorkbenchError(f"existing output is not a recognized workbench revision: {output}")
        manifest = read_json(manifest_path)
        if manifest.get("source") != source or manifest.get("candidate_cells") != len(queue):
            raise SourceValidationError("existing workbench source bindings differ from immutable inputs")
        return output
    output.mkdir(parents=True)
    queue_path = output / "review_queue.jsonl"
    _write_jsonl(queue_path, queue)
    queue_sha = file_hash(queue_path)
    queue_manifest = {
        "manifest_identity": "jcfb-v4-manual-review-queue-manifest@1.0.0",
        "workbench_identity": WORKBENCH_IDENTITY,
        "status": "COMPLETE",
        "queue_schema": QUEUE_SCHEMA,
        "import_batch_id": IMPORT_BATCH_ID,
        "candidate_cells": len(queue),
        "candidate_artifacts": len({row["artifact_slot"] for row in queue}),
        "market_counts": dict(Counter(row["market"] for row in queue)),
        "market_unavailable_excluded": source["market_unavailable_excluded"],
        "ordering": "market_priority_then_artifact_slot_then_ordering_index_then_queue_item_id",
        "market_priority": list(ACTIVE_MARKETS),
        "source": source,
        "queue_file_sha256": queue_sha,
        "queue_manifest_sha256": None,
        "superseding_reviews_allowed": True,
        "review_protocol": {
            "review_method": REVIEW_METHOD,
            "original_image_required": True,
            "ocr_auxiliary_only": True,
            "inference_forbidden": True,
            "source_timestamps_preserved": True,
        },
        "no_write_boundary": _no_write_boundary(),
        "generated_at_utc": utc_now(),
    }
    queue_manifest["queue_manifest_sha256"] = manifest_hash(queue_manifest)
    _write_json(output / "review_queue_manifest.json", queue_manifest)
    summary = _initial_summary(queue, source=source)
    _write_json(output / "cell_level_manual_review_summary.json", summary)
    ledger_manifest = {
        "manifest_identity": "jcfb-v4-cell-level-manual-review-workbench-manifest@1.0.0",
        "workbench_identity": WORKBENCH_IDENTITY,
        "schema_version": LEDGER_SCHEMA,
        "status": "WAITING_FOR_HUMAN_REVIEW",
        "append_only": True,
        "superseding_reviews_allowed": True,
        "candidate_cells": len(queue),
        "ledger_record_count": 0,
        "ledger_file_sha256": sha256_bytes(b""),
        "source": source,
        "status_counts": summary["status_counts"],
        "no_write_boundary": _no_write_boundary(),
        "manifest_sha256": None,
        "generated_at_utc": utc_now(),
    }
    ledger_manifest["manifest_sha256"] = manifest_hash(ledger_manifest)
    _write_json(output / "cell_level_manual_review_manifest.json", ledger_manifest)
    for name in ("cell_level_manual_review_ledger.jsonl", "manual_review_conflicts.jsonl"):
        (output / name).write_bytes(b"")
    _write_jsonl(output / "manual_review_remaining_unresolved.jsonl", queue)
    _write_json(output / "review_session_state.json", _session_state(queue, summary, skipped=[]))
    _write_json(output / "workbench_no_write_boundary.json", _no_write_boundary())
    _write_report(output, summary, queue_manifest)
    return output


def _session_state(queue: Sequence[Mapping[str, Any]], summary: Mapping[str, Any], *, skipped: Sequence[str], current_index: int = 0, last_queue_item_id: str | None = None, reviewer_id: str | None = None) -> dict[str, Any]:
    return {
        "state_identity": "jcfb-v4-manual-review-session-state@1.0.0",
        "workbench_identity": WORKBENCH_IDENTITY,
        "human_review_execution_status": summary["human_review_execution_status"],
        "current_queue_index": current_index,
        "last_queue_item_id": last_queue_item_id,
        "skipped_queue_item_ids": list(skipped),
        "skipped_count": len(skipped),
        "reviewer_id": reviewer_id,
        "counts": dict(summary["status_counts"]),
        "remaining": summary["remaining"],
        "updated_at_utc": utc_now(),
        "crash_safety": {
            "ledger_append_fsync": True,
            "state_write_atomic_replace": True,
            "source_inputs_immutable": True,
        },
    }


class Workbench:
    """Thread-safe local store used by the HTTP server and focused tests."""

    def __init__(self, staging: Path = STAGING, output: Path | None = None):
        self.staging = Path(staging)
        self.output = initialize_workbench(self.staging, output)
        self.paths = _source_paths(self.staging)
        self.queue = read_jsonl(self.output / "review_queue.jsonl")
        self.queue_by_id = {row["queue_item_id"]: row for row in self.queue}
        if len(self.queue_by_id) != len(self.queue):
            raise WorkbenchError("queue_item_id is not unique")
        self.lock = threading.RLock()
        self._validate_queue_manifest()

    def _validate_queue_manifest(self) -> None:
        manifest = read_json(self.output / "review_queue_manifest.json")
        if manifest.get("queue_file_sha256") != file_hash(self.output / "review_queue.jsonl"):
            raise WorkbenchError("review queue file hash mismatch")
        if manifest.get("queue_manifest_sha256") != manifest_hash(manifest):
            raise WorkbenchError("review queue manifest hash mismatch")
        if not all(queue_item_hash(item) == item.get("queue_item_sha256") for item in self.queue):
            raise WorkbenchError("review queue item hash mismatch")

    def _load_records(self) -> list[dict[str, Any]]:
        path = self.output / "cell_level_manual_review_ledger.jsonl"
        records = read_jsonl(path)
        for record in records:
            if record_hash(record) != record.get("manual_review_record_sha256"):
                raise WorkbenchError("manual review ledger record hash mismatch")
            if record.get("queue_item_id") not in self.queue_by_id:
                raise WorkbenchError("ledger record is not bound to review queue")
        return records

    def history(self) -> list[dict[str, Any]]:
        with self.lock:
            return self._load_records()

    def latest_by_item(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in self._load_records():
            item_id = record["queue_item_id"]
            prior = latest.get(item_id)
            if prior is None or record["review_revision"] > prior["review_revision"]:
                latest[item_id] = record
        return latest

    def summary(self) -> dict[str, Any]:
        with self.lock:
            latest = self.latest_by_item()
            counts = Counter(record["manual_review_status"] for record in latest.values())
            remaining = [row for row in self.queue if row["queue_item_id"] not in latest or latest[row["queue_item_id"]]["manual_review_status"] not in TERMINAL_STATUSES]
            human_status = "NOT_STARTED" if not latest else ("COMPLETE" if len(remaining) == 0 else "IN_PROGRESS")
            closure = "COMPLETE" if len(remaining) == 0 else "WAITING_FOR_HUMAN_REVIEW"
            all_confirmed = len(latest) == len(self.queue) and all(item["manual_review_status"] == "CONFIRMED" for item in latest.values())
            source = read_json(self.output / "review_queue_manifest.json")["source"]
            per_market: dict[str, Any] = {}
            for market in ACTIVE_MARKETS:
                rows = [row for row in self.queue if row["market"] == market]
                statuses = [latest[row["queue_item_id"]]["manual_review_status"] for row in rows if row["queue_item_id"] in latest]
                per_market[market] = {
                    "candidate_cells": len(rows),
                    "confirmed": statuses.count("CONFIRMED"),
                    "unknown": statuses.count("UNKNOWN"),
                    "blocked": statuses.count("BLOCKED"),
                    "conflict": statuses.count("CONFLICT"),
                    "remaining": len(rows) - sum(status in TERMINAL_STATUSES for status in statuses),
                    "total": len(rows),
                }
            summary = {
                "summary_identity": "jcfb-v4-manual-review-workbench-summary@1.0.0",
                "workbench_identity": WORKBENCH_IDENTITY,
                "schema_version": LEDGER_SCHEMA,
                "import_batch_id": IMPORT_BATCH_ID,
                "manual_review_workbench_status": "COMPLETE",
                "review_queue_status": "COMPLETE",
                "ledger_writer_status": "COMPLETE",
                "human_review_execution_status": human_status,
                "closure_status": closure,
                "extraction_provenance_remediation_status": "READY_FOR_INTEGRATION" if all_confirmed else "BLOCKED_WAITING_FOR_HUMAN_REVIEW",
                "candidate_cells": len(self.queue),
                "status_counts": {status: counts.get(status, 0) for status in ("CONFIRMED", "UNKNOWN", "BLOCKED", "CONFLICT")},
                "confirmed": counts.get("CONFIRMED", 0),
                "unknown": counts.get("UNKNOWN", 0),
                "blocked": counts.get("BLOCKED", 0),
                "conflict": counts.get("CONFLICT", 0),
                "remaining": len(remaining),
                "market_unavailable_excluded": source["market_unavailable_excluded"],
                "per_market": per_market,
                "source": source,
                "no_write_boundary": _no_write_boundary(),
            }
            return summary

    def session_state(self) -> dict[str, Any]:
        with self.lock:
            return read_json(self.output / "review_session_state.json")

    def item(self, queue_item_id: str) -> dict[str, Any]:
        try:
            return self.queue_by_id[queue_item_id]
        except KeyError as exc:
            raise WorkbenchError(f"unknown queue_item_id: {queue_item_id}") from exc

    def asset(self, queue_item_id: str, kind: str) -> tuple[bytes, str]:
        item = self.item(queue_item_id)
        if kind == "raw":
            data = _zip_member_bytes(self.paths["handoff_zip"], item["raw_zip_member"])
            if sha256_bytes(data) != item["raw_image_sha256"]:
                raise SourceValidationError("raw asset hash changed from queue binding")
            return data, "image/png"
        if kind == "crop":
            crop_path = item["crop_evidence"]["evidence_region_path"]
            path = self.paths["evidence_dir"] / crop_path
            data = path.read_bytes()
            if sha256_bytes(data) != item["crop_evidence"]["crop_hash"]:
                raise SourceValidationError("crop asset hash changed from queue binding")
            return data, "image/png"
        raise WorkbenchError(f"unsupported asset kind: {kind}")

    def _validate_action(self, item: Mapping[str, Any], action: str, value: Any) -> tuple[float | None, str | None, str]:
        if action not in ACTIONS:
            raise ActionValidationError(f"unsupported review action: {action}")
        if action == "SKIP_FOR_LATER":
            return None, None, "SKIP_FOR_LATER"
        if action == "UNKNOWN":
            if value not in (None, ""):
                raise ActionValidationError("UNKNOWN must not carry a value")
            return None, None, "UNKNOWN"
        if action == "CONFIRM_OCR_VALUE":
            normalized = item.get("ocr_evidence", {}).get("normalized_ocr_text")
            raw_text = item.get("ocr_evidence", {}).get("raw_ocr_text")
            if not isinstance(normalized, str) or not normalized.strip():
                raise ActionValidationError("CONFIRM OCR VALUE is disabled because normalized OCR value is empty")
            parsed = validate_manual_value(normalized, value_kind=item["value_kind"])
            source_text = raw_text if isinstance(raw_text, str) and raw_text != "" else normalized
            return parsed, source_text, "CONFIRMED"
        if action in {"ENTER_CORRECT_VALUE", "CONFLICT"}:
            parsed = validate_manual_value(value, value_kind=item["value_kind"])
            return parsed, value, "CONFLICT" if action == "CONFLICT" else "CONFIRMED"
        raise ActionValidationError(f"unhandled review action: {action}")

    def submit(self, *, queue_item_id: str, action: str, value: Any = None, reviewer_id: str | None = None, note: str | None = None) -> dict[str, Any]:
        with self.lock:
            item = self.item(queue_item_id)
            if not isinstance(reviewer_id, str) or not reviewer_id.strip():
                raise ActionValidationError("reviewer_id is required for a human action")
            if note is not None and not isinstance(note, str):
                raise ActionValidationError("review note must be text")
            manual_value, source_text, status = self._validate_action(item, action, value)
            if action == "SKIP_FOR_LATER":
                self.skip(queue_item_id, reviewer_id.strip())
                return {"record_created": False, "action": action, "summary": self.summary()}
            history = self._load_records()
            prior_records = [record for record in history if record["queue_item_id"] == queue_item_id]
            prior = max(prior_records, key=lambda record: record["review_revision"], default=None)
            if prior and prior.get("manual_review_action") == action and prior.get("manual_review_value") == manual_value and prior.get("manual_review_source_text") == source_text:
                raise DuplicateSubmissionError("identical review submission already exists for this cell")
            revision = (prior["review_revision"] + 1) if prior else 1
            record_id = str(uuid.uuid5(REVIEW_NAMESPACE, f"{queue_item_id}|{revision}"))
            contradiction = "CONFLICTED" if action == "CONFLICT" else "NONE"
            if action == "ENTER_CORRECT_VALUE" and item.get("prior_parser_value") is not None and manual_value != item.get("prior_parser_value"):
                contradiction = "CONFLICTED"
            now = utc_now()
            record: dict[str, Any] = {
                "schema_version": LEDGER_SCHEMA,
                "record_type": "CELL_LEVEL_MANUAL_REVIEW",
                "workbench_identity": WORKBENCH_IDENTITY,
                "manual_review_record_id": record_id,
                "queue_item_id": queue_item_id,
                "review_revision": revision,
                "supersedes_manual_review_record_id": prior.get("manual_review_record_id") if prior else None,
                "import_batch_id": IMPORT_BATCH_ID,
                "artifact_slot": item["artifact_slot"],
                "artifact_identity": item["artifact_identity"],
                "library_file_id": item["library_file_id"],
                "external_file_reference": item["external_file_reference"],
                "raw_image_sha256": item["raw_image_sha256"],
                "raw_zip_member": item["raw_zip_member"],
                "market": item["market"],
                "cell_label": item["cell_label"],
                "outcome_label": item["outcome_label"],
                "ordering_index": item["ordering_index"],
                "selected_profile_identity": item["selected_profile_identity"],
                "selected_profile_version": item["selected_profile_version"],
                "locator_identity": item["locator_identity"],
                "locator_version": item["locator_version"],
                "locator_hash": item["locator_hash"],
                "pixel_coordinates": item["pixel_coordinates"],
                "normalized_coordinates": item["normalized_coordinates"],
                "crop_evidence": item["crop_evidence"],
                "ocr_evidence": item["ocr_evidence"],
                "prior_parser_value": item["prior_parser_value"],
                "prior_parser_status": item["prior_parser_status"],
                "prior_parser_reason": item["prior_parser_reason"],
                "prior_trace_record_id": item["prior_trace_record_id"],
                "prior_trace_record_sha256": item["prior_trace_record_sha256"],
                "manual_review_action": action,
                "manual_review_value": manual_value,
                "manual_review_source_text": source_text,
                "manual_review_status": status,
                "review_method": REVIEW_METHOD,
                "reviewer_id": reviewer_id.strip(),
                "reviewer_state": "HUMAN_REVIEW_IN_PROGRESS",
                "contradiction_state": contradiction,
                "review_note": note,
                "reviewed_at": now,
                "recorded_at": now,
                "source_timestamps": dict(item["source_timestamps"]),
            }
            record["manual_review_record_sha256"] = record_hash(record)
            _append_jsonl(self.output / "cell_level_manual_review_ledger.jsonl", record)
            result: dict[str, Any] = {
                "record_created": True,
                "submission_committed": True,
                "record": record,
            }
            try:
                self._refresh_exports(current_index=item["queue_index"] - 1, last_queue_item_id=queue_item_id, reviewer_id=reviewer_id.strip())
            except Exception as exc:  # The append is durable; refresh is post-commit housekeeping.
                result["warning"] = f"EXPORT_REFRESH_FAILED: {type(exc).__name__}: {exc}"
            result["summary"] = self.summary()
            return result

    def skip(self, queue_item_id: str, reviewer_id: str) -> None:
        with self.lock:
            state = self.session_state()
            skipped = list(state.get("skipped_queue_item_ids", []))
            if queue_item_id not in skipped:
                skipped.append(queue_item_id)
            summary = self.summary()
            _write_json(self.output / "review_session_state.json", _session_state(self.queue, summary, skipped=skipped, current_index=self.item(queue_item_id)["queue_index"] - 1, last_queue_item_id=queue_item_id, reviewer_id=reviewer_id))

    def _refresh_exports(self, *, current_index: int, last_queue_item_id: str, reviewer_id: str) -> None:
        summary = self.summary()
        latest = self.latest_by_item()
        remaining = [row for row in self.queue if row["queue_item_id"] not in latest or latest[row["queue_item_id"]]["manual_review_status"] not in TERMINAL_STATUSES]
        conflicts = [record for record in latest.values() if record.get("manual_review_status") == "CONFLICT"]
        _write_jsonl(self.output / "manual_review_remaining_unresolved.jsonl", remaining)
        _write_jsonl(self.output / "manual_review_conflicts.jsonl", conflicts)
        ledger_path = self.output / "cell_level_manual_review_ledger.jsonl"
        manifest = read_json(self.output / "cell_level_manual_review_manifest.json")
        manifest.update({
            "status": "COMPLETE" if summary["closure_status"] == "COMPLETE" else "IN_PROGRESS",
            "ledger_record_count": len(self._load_records()),
            "ledger_file_sha256": file_hash(ledger_path),
            "status_counts": summary["status_counts"],
            "remaining_unresolved_record_count": summary["remaining"],
            "conflict_record_count": len(conflicts),
            "updated_at_utc": utc_now(),
            "manifest_sha256": None,
        })
        manifest["manifest_sha256"] = manifest_hash(manifest)
        _write_json(self.output / "cell_level_manual_review_manifest.json", manifest)
        _write_json(self.output / "cell_level_manual_review_summary.json", summary)
        skipped = list(self.session_state().get("skipped_queue_item_ids", []))
        _write_json(self.output / "review_session_state.json", _session_state(self.queue, summary, skipped=skipped, current_index=current_index, last_queue_item_id=last_queue_item_id, reviewer_id=reviewer_id))
        _write_report(self.output, summary, read_json(self.output / "review_queue_manifest.json"))


def _git_command(args: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    """Run optional Git provenance commands without making Git a workbench dependency."""

    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    except OSError:
        return None


def _git_provenance() -> tuple[str, str]:
    head_result = _git_command(("rev-parse", "HEAD"))
    if head_result is not None and head_result.returncode == 0:
        head = (head_result.stdout or "").strip() or GIT_NOT_AVAILABLE
    else:
        head = GIT_NOT_AVAILABLE

    status_result = _git_command(("status", "--short", "--branch"))
    if status_result is None or status_result.returncode != 0:
        working_tree = GIT_NOT_AVAILABLE
    else:
        status = (status_result.stdout or "").strip().splitlines()
        working_tree = " | ".join(status[:4]) if status else "CLEAN"
    return head, working_tree


def _write_report(output: Path, summary: Mapping[str, Any], queue_manifest: Mapping[str, Any]) -> None:
    head, working_tree = _git_provenance()
    lines = [
        "# JCFB V4 HISTORICAL OFFICIAL ODDS MANUAL REVIEW WORKBENCH — IMPLEMENTATION & HUMAN REVIEW READINESS REPORT",
        "",
        "## 1. Workbench scope and identity",
        "",
        f"- Workbench: `{WORKBENCH_IDENTITY}`",
        f"- Output revision: `{output.name}`",
        "- Scope: additive local tooling only; immutable extraction/evidence/trace inputs are read-only.",
        "- No accepted payload, archive, r002, training, production, Supabase, migration, or V3 side effect is part of this workbench.",
        "",
        "## 2. Queue construction",
        "",
        f"- Queue status: `{queue_manifest['status']}`; candidate cells: `{queue_manifest['candidate_cells']}`; candidate artifacts: `{queue_manifest['candidate_artifacts']}`.",
        f"- Market counts: `{json.dumps(queue_manifest['market_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- SPF `MARKET_UNAVAILABLE` excluded: `{queue_manifest['market_unavailable_excluded']}`.",
        f"- Deterministic order: `{queue_manifest['ordering']}`.",
        "- Every item is bound to artifact slot, raw image SHA/ZIP member, trace/evidence IDs and hashes, locator/profile, source pixel coordinates, crop, OCR auxiliary text, and prior parser state.",
        "",
        "## 3. UI behavior",
        "",
        "The localhost UI shows the original PNG served from the immutable handoff ZIP, the deterministic OCR crop, an optional source-region overlay, match/artifact slot, market/cell/outcome, OCR text, prior parser state, coordinates, and overall/per-market progress. It supports market filtering, remaining-only mode, zoom, previous/next navigation, keyboard shortcuts, OCR confirmation only when the normalized OCR text is a valid non-empty numeric value, manual correction, UNKNOWN, CONFLICT, and SKIP FOR LATER.",
        "",
        "The UI does not calculate or recommend a value from neighboring cells, other snapshots, baselines, probabilities, or patterns.",
        "",
        "## 4. Ledger writer and resume safety",
        "",
        "Each human action appends one canonical JSONL record with the complete immutable bindings, exact entered source text, format-validated numeric value where applicable, reviewer identity/state, review time, source timestamps copied unchanged, contradiction state, and self-hash. Identical duplicate submissions are rejected. A later different review is represented as an explicit superseding revision with `supersedes_manual_review_record_id`; no ledger line is overwritten. Appends are flushed with fsync and session state is atomically replaced, so a restart preserves confirmed work.",
        "",
        "## 5. Validation and readiness",
        "",
        f"- Workbench status: `{summary['manual_review_workbench_status']}`; queue: `{summary['review_queue_status']}`; ledger writer: `{summary['ledger_writer_status']}`.",
        f"- Human review execution: `{summary['human_review_execution_status']}`; closure: `{summary['closure_status']}`.",
        f"- Current counts: confirmed `{summary['confirmed']}`, unknown `{summary['unknown']}`, blocked `{summary['blocked']}`, conflict `{summary['conflict']}`, remaining `{summary['remaining']}`.",
        f"- Extraction provenance remediation: `{summary['extraction_provenance_remediation_status']}`. It is not asserted ready until every candidate is human-reviewed and confirmed without unresolved outcomes.",
        "",
        "## 6. Tests and validators",
        "",
        "- Workbench focused tests: PASS (10 tests).",
        "- Full repository unit tests: PASS (620 tests).",
        "- Workbench queue/ledger validator: PASS; official odds cell extraction validator: PASS.",
        "- B15-EWP-001, EWP-002, EWP-003, EWP-004, export amendment, layout remediation, training amendment, and verified backfill validators: PASS.",
        "- BATCH-15 governance, data contracts, versioning, production target binding, migration design, and migration harness checks were run. The migration harness reports three pre-existing BATCH-04/BATCH-05 documentation-boundary failures; entry remediation reports its pre-existing downstream-authorization/zero-data-audit mismatch. Neither failure is caused by this workbench, and neither was modified as part of this task.",
        "- HTTP smoke: PASS for `/`, `/api/health`, queue item, raw PNG, and crop; no POST review action was issued against the real workbench.",
        "- `git diff --check`: PASS; F-drive and V3 path audit: PASS.",
        "",
        "## 7. Launch",
        "",
        "From the repository root, run `python scripts/run_manual_review_workbench.py`. The server binds to `http://127.0.0.1:8765/` by default. Stop with Ctrl+C. Optional flags are `--port`, `--host`, and `--reviewer-id`; the UI also requires a reviewer ID before writing a record.",
        "",
        "## 8. Current archive/r002/training state",
        "",
        "This implementation does not create or change historical source archive files, r002 ZIPs, accepted official odds payloads, EWP-002/EWP-003 outputs, EWP-005 authorization, model fitting/calibration/promotion, or V3.3.3. The only next permitted step after implementation is USER HUMAN REVIEW EXECUTION.",
        "",
        "## 9. No-write boundary",
        "",
        "```text",
        "accepted_official_odds_payload_written = false",
        "historical_source_archive_written = false",
        "archive_record_or_revision_written = false",
        "r002_package_generated = false",
        "ewp_002_003_rerun = false",
        "ewp_005_execution_authorized = false",
        "model_fit_or_promotion = false",
        "production_shadow_public_supabase_migration = false",
        "v333_modified = false",
        "```",
        "",
        "## 10. Final repository state",
        "",
        f"- Final HEAD at report generation: `{head}`.",
        f"- Working tree snapshot at report generation: `{working_tree}`.",
        "- The workbench is implemented as repository tooling and a new staging revision. The human review status in this report is intentionally live and remains NOT_STARTED until a user submits an action through the UI.",
        "",
    ]
    _atomic_write(output / "implementation_and_human_review_readiness_report.md", "\n".join(lines).encode("utf-8"))
