"""Validate the local manual-review queue and append-only ledger revision."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.manual_review_workbench.core import (
    ACTIVE_MARKETS,
    TERMINAL_STATUSES,
    Workbench,
    file_hash,
    manifest_hash,
    queue_item_hash,
    record_hash,
)


def validate(output: Path | None = None) -> list[str]:
    workbench = Workbench(output=output) if output else Workbench()
    failures: list[str] = []
    queue = workbench.queue
    if len(queue) != 432:
        failures.append(f"queue count is {len(queue)}, expected 432")
    if any(queue_item_hash(item) != item.get("queue_item_sha256") for item in queue):
        failures.append("queue item hash mismatch")
    manifest = workbench.output / "review_queue_manifest.json"
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    if manifest_value.get("queue_manifest_sha256") != manifest_hash(manifest_value):
        failures.append("queue manifest hash mismatch")
    if manifest_value.get("market_unavailable_excluded") != 9:
        failures.append("MARKET_UNAVAILABLE exclusion is not 9")
    if manifest_value.get("market_counts") != {"EXACT_SCORE": 369, "TOTAL_GOALS": 3, "HTFT": 56, "SPF": 2, "RQSPF": 2}:
        failures.append("market counts do not match the governed candidate set")
    records = workbench.history()
    if any(record_hash(record) != record.get("manual_review_record_sha256") for record in records):
        failures.append("ledger record hash mismatch")
    latest = workbench.latest_by_item()
    if any(item_id not in workbench.queue_by_id for item_id in latest):
        failures.append("ledger item binding mismatch")
    counts = Counter(record["manual_review_status"] for record in latest.values())
    summary = workbench.summary()
    expected_counts = {status: counts.get(status, 0) for status in ("CONFIRMED", "UNKNOWN", "BLOCKED", "CONFLICT")}
    if summary.get("status_counts") != expected_counts:
        failures.append("summary status counts are stale")
    if summary.get("remaining") != 432 - sum(expected_counts.values()):
        failures.append("summary remaining count is inconsistent")
    remaining_path = workbench.output / "manual_review_remaining_unresolved.jsonl"
    remaining = [json.loads(line) for line in remaining_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_remaining = {item["queue_item_id"] for item in queue if item["queue_item_id"] not in latest or latest[item["queue_item_id"]]["manual_review_status"] not in TERMINAL_STATUSES}
    if {item["queue_item_id"] for item in remaining} != expected_remaining:
        failures.append("remaining unresolved export is inconsistent")
    ledger_manifest_path = workbench.output / "cell_level_manual_review_manifest.json"
    ledger_manifest = json.loads(ledger_manifest_path.read_text(encoding="utf-8"))
    ledger_path = workbench.output / "cell_level_manual_review_ledger.jsonl"
    if ledger_manifest.get("ledger_file_sha256") != file_hash(ledger_path):
        failures.append("ledger file hash in manifest is stale")
    if ledger_manifest.get("manifest_sha256") != manifest_hash(ledger_manifest):
        failures.append("ledger manifest hash mismatch")
    if set(ACTIVE_MARKETS) != set(summary.get("per_market", {})):
        failures.append("per-market progress is incomplete")
    archive_root = workbench.staging.parent.parent / "historical_source_archive"
    if archive_root.exists() and any(path.is_file() for path in archive_root.rglob("*")):
        failures.append("historical source archive contains files")
    approved_data = workbench.staging.parents[1]
    if any(path.is_file() and path.suffix.lower() == ".zip" and "r002" in path.name.casefold() for path in approved_data.rglob("*")):
        failures.append("r002 ZIP detected")
    if workbench.output.name != "manual_review_workbench_r001_revision_001":
        failures.append("unexpected workbench output revision")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    failures = validate(Path(args.output) if args.output else None)
    if failures:
        print("MANUAL REVIEW WORKBENCH VALIDATION: FAIL")
        print("\n".join(failures))
        sys.exit(1)
    print("MANUAL REVIEW WORKBENCH VALIDATION: PASS")
    print("Queue: 432; SPF MARKET_UNAVAILABLE excluded: 9")
    print("Human review values confirmed by this validator: no")
    print("Accepted odds/archive/r002/training writes: not enabled")


if __name__ == "__main__":
    main()
