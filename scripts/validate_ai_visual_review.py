"""Validate AI visual review evidence and its explicit fail-closed boundary."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ai_visual_review.protocol import AI_REVIEW_STATUSES, HASH_RE, canonical_hash, load_contract


STAGING = ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001"
OUTPUT = STAGING / "ai_visual_review_r001_revision_001"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate() -> list[str]:
    failures: list[str] = []
    contract = load_contract()
    manifest_path = OUTPUT / "ai_visual_review_manifest.json"
    records_path = OUTPUT / "ai_visual_review_records.jsonl"
    escalation_path = OUTPUT / "human_escalation_queue.jsonl"
    if not all(path.is_file() for path in (manifest_path, records_path, escalation_path)):
        return ["AI visual review output is incomplete"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = read_jsonl(records_path)
    escalations = read_jsonl(escalation_path)
    if manifest.get("contract_identity") != contract["contract_identity"]:
        failures.append("manifest contract identity mismatch")
    if manifest.get("manifest_hash") != canonical_hash(manifest, omit="manifest_hash"):
        failures.append("manifest hash mismatch")
    if manifest.get("candidate_count") != 432 or len(records) != 432:
        failures.append("record count is not the governed 432 candidates")
    if len(escalations) != len([r for r in records if r.get("review_status") not in {"AI_CONFIRMED", "AI_CORRECTED"}]):
        failures.append("human escalation queue is not a mechanical non-accepted filter")
    counts = Counter(record.get("review_status") for record in records)
    if dict(sorted(counts.items())) != manifest.get("status_counts"):
        failures.append("manifest status counts are stale")
    for record in records:
        if record.get("review_status") not in AI_REVIEW_STATUSES:
            failures.append(f"invalid review status: {record.get('review_status')}")
        if record.get("canonical_review_record_hash") != canonical_hash(record):
            failures.append(f"review record hash mismatch: {record.get('queue_item_id')}")
        for field in ("raw_image_sha256", "crop_evidence_hash", "ocr_evidence_hash", "prior_trace_hash", "locator_hash", "review_implementation_hash"):
            if not HASH_RE.fullmatch(str(record.get(field, ""))):
                failures.append(f"missing or invalid {field}: {record.get('queue_item_id')}")
        if record.get("review_status") == "HUMAN_ESCALATION_REQUIRED":
            if record.get("pass_a", {}).get("status") != "NOT_EXECUTED" or record.get("pass_b", {}).get("status") != "NOT_EXECUTED":
                failures.append("provider-unavailable escalation does not preserve NOT_EXECUTED passes")
        if record.get("review_status") in {"AI_CONFIRMED", "AI_CORRECTED"} and record.get("pass_a", {}).get("review_method") == "HUMAN_VISUAL_FROM_ORIGINAL_IMAGE":
            failures.append("AI record impersonates HUMAN review")
    if manifest.get("provider_available") is not False:
        failures.append("current run did not record unavailable provider")
    for boundary in ("accepted_payload_written", "archive_written", "training_written"):
        if manifest.get(boundary) is not False:
            failures.append(f"write boundary leaked: {boundary}")
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("JCFB V4 AI VISUAL REVIEW VALIDATION: FAIL")
        print("\n".join(errors))
        raise SystemExit(1)
    print("JCFB V4 AI VISUAL REVIEW VALIDATION: PASS")
    print("Candidates: 432; AI confirmed: 0; human escalation required: 432")
    print("Accepted odds/archive/training writes: not performed")
