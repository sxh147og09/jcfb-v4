"""Batch runner for AI visual review evidence.

Without a registered visual provider the runner still emits deterministic,
fully-bound escalation records.  This makes the blocker measurable and
replayable without claiming that OCR was visual review.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .protocol import VisualPassObservation, build_review_record, canonical_hash, load_contract


ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "approved_data" / "historical_backfill_staging" / "CHATGPT-20260901-20260904-R001"
QUEUE = STAGING / "manual_review_workbench_r001_revision_001" / "review_queue.jsonl"
OUTPUT = STAGING / "ai_visual_review_r001_revision_001"
RUN_ID = "AI-VISUAL-REVIEW-20260907-R001"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def unavailable_pass(pass_id: str, method: str, reason: str) -> VisualPassObservation:
    return VisualPassObservation(pass_id, method, "NOT_EXECUTED", None, None, None, None, None, None, reason)


def run(
    *,
    queue_path: Path = QUEUE,
    output: Path = OUTPUT,
    provider_a: Optional[Callable[[Mapping[str, Any]], VisualPassObservation]] = None,
    provider_b: Optional[Callable[[Mapping[str, Any]], VisualPassObservation]] = None,
) -> dict[str, Any]:
    contract = load_contract()
    queue = _read_jsonl(queue_path)
    records: list[dict[str, Any]] = []
    for item in queue:
        if provider_a is None or provider_b is None:
            reason = "NO_SAFE_REPEATABLE_VISUAL_PROVIDER_AVAILABLE_IN_CODEX_RUNTIME"
            pass_a = unavailable_pass("PASS_A", "AI_VISUAL_FROM_DETERMINISTIC_CROP", reason)
            pass_b = unavailable_pass("PASS_B", "AI_VISUAL_FROM_ORIGINAL_IMAGE", reason)
        else:
            pass_a = provider_a(item)
            pass_b = provider_b(item)
        records.append(build_review_record(item, pass_a=pass_a, pass_b=pass_b, contract=contract, reviewer_run_id=RUN_ID))
    statuses = Counter(record["review_status"] for record in records)
    by_market: dict[str, dict[str, int]] = {}
    for market in sorted({record["market"] for record in records}):
        by_market[market] = {status: sum(record["market"] == market and record["review_status"] == status for record in records) for status in sorted(set(contract["allowed_ai_statuses"]))}
    manifest = {
        "manifest_identity": "official-odds-ai-visual-review-manifest@1.0.0",
        "contract_identity": contract["contract_identity"],
        "schema_version": contract["schema_version"],
        "status": "COMPLETE_WITH_ESCALATIONS" if statuses.get("HUMAN_ESCALATION_REQUIRED") else "COMPLETE",
        "review_run_id": RUN_ID,
        "candidate_count": len(queue),
        "record_count": len(records),
        "status_counts": dict(sorted(statuses.items())),
        "per_market": by_market,
        "provider_available": provider_a is not None and provider_b is not None,
        "source_queue_path": str(queue_path),
        "source_queue_sha256": "sha256:" + __import__("hashlib").sha256(queue_path.read_bytes()).hexdigest(),
        "accepted_payload_written": False,
        "archive_written": False,
        "training_written": False,
    }
    manifest["manifest_hash"] = canonical_hash(manifest, omit="manifest_hash")
    _write_jsonl(output / "ai_visual_review_records.jsonl", records)
    _write_jsonl(output / "human_escalation_queue.jsonl", [record for record in records if record["review_status"] != "AI_CONFIRMED" and record["review_status"] != "AI_CORRECTED"])
    _write_json(output / "ai_visual_review_manifest.json", manifest)
    _write_json(output / "ai_visual_review_summary.json", {"summary_identity": "official-odds-ai-visual-review-summary@1.0.0", "manifest_hash": manifest["manifest_hash"], "status_counts": dict(sorted(statuses.items())), "per_market": by_market, "review_status": manifest["status"]})
    return manifest
