"""Fail-closed importer for ChatGPT-assisted visual review JSONL responses."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_ocr_consensus import canonical_bytes, load_jsonl, normalize_numeric, sha256_file, sha256_json, write_jsonl  # noqa: E402


ALLOWED = {"CHATGPT_CONFIRMED", "CHATGPT_REVIEW_AMBIGUOUS", "CHATGPT_UNREADABLE", "CHATGPT_SOURCE_MISMATCH", "CHATGPT_CONFLICT"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def fail(code: str, message: str) -> None:
    raise ValueError(f"{code}: {message}")


def main() -> int:
    args = parse_args()
    if args.output.exists():
        fail("OUTPUT_OVERWRITE_FORBIDDEN", str(args.output))
    package_dir = args.package_dir
    package = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    items = load_jsonl(package_dir / "review_items.jsonl")
    responses = load_jsonl(args.response)
    if len(items) != package.get("review_item_count"):
        fail("PACKAGE_ITEM_COUNT_INVALID", "review_items count does not match package")
    item_by_id = {item["review_item_id"]: item for item in items}
    if len(item_by_id) != len(items):
        fail("PACKAGE_ITEM_ID_DUPLICATE", "review_item_id must be unique")
    seen: set[str] = set()
    imported: list[dict] = []
    for index, response in enumerate(responses, start=1):
        required = ("review_item_id", "source_raw_image_sha256", "source_crop_sha256", "value_text", "normalized_value", "review_status", "review_method")
        missing = [field for field in required if field not in response]
        if missing:
            fail("RESPONSE_FIELD_MISSING", f"row {index}: {','.join(missing)}")
        item_id = response["review_item_id"]
        if item_id not in item_by_id:
            fail("RESPONSE_ITEM_UNKNOWN", f"row {index}: {item_id}")
        if item_id in seen:
            fail("RESPONSE_ITEM_DUPLICATE", f"row {index}: {item_id}")
        seen.add(item_id)
        item = item_by_id[item_id]
        source = item["source"]
        if response["source_raw_image_sha256"] != source["raw_image_sha256"]:
            fail("SOURCE_RAW_HASH_MISMATCH", item_id)
        if response["source_crop_sha256"] != source["crop_sha256"]:
            fail("SOURCE_CROP_HASH_MISMATCH", item_id)
        if response["review_method"] != "CHATGPT_ASSISTED_VISUAL_REVIEW":
            fail("REVIEW_METHOD_FORBIDDEN", item_id)
        status = response["review_status"]
        if status not in ALLOWED:
            fail("REVIEW_STATUS_INVALID", item_id)
        normalized = response["normalized_value"]
        value_text = response["value_text"]
        if normalized is not None:
            if not isinstance(normalized, str) or normalize_numeric(normalized) != normalized:
                fail("VALUE_GRAMMAR_INVALID", item_id)
            if status != "CHATGPT_CONFIRMED":
                fail("NONCONFIRMING_STATUS_HAS_VALUE", item_id)
        if status == "CHATGPT_CONFIRMED" and normalized is None:
            fail("CONFIRMED_VALUE_MISSING", item_id)
        if status != "CHATGPT_CONFIRMED" and normalized is not None:
            fail("NONCONFIRMING_VALUE_FORBIDDEN", item_id)
        row = {
            "schema_version": "official-odds-chatgpt-assisted-visual-review-record@1.0.0",
            "review_item_id": item_id,
            "artifact_identity": item.get("artifact_identity"),
            "artifact_slot": item.get("artifact_slot"),
            "market": item.get("market"),
            "cell_label": item.get("cell_label"),
            "ordering_index": item.get("ordering_index"),
            "source_raw_image_sha256": source["raw_image_sha256"],
            "source_crop_sha256": source["crop_sha256"],
            "trace_id": item["trace_id"],
            "trace_hash": item["trace_hash"],
            "value_text": value_text,
            "normalized_value": normalized,
            "review_status": status,
            "review_method": response["review_method"],
            "notes": response.get("notes"),
            "accepted_payload_written": False,
            "training_written": False,
        }
        row["review_record_sha256"] = sha256_json(row)
        imported.append(row)
    missing_ids = sorted(set(item_by_id) - seen)
    if missing_ids:
        fail("RESPONSE_ITEM_MISSING", f"{len(missing_ids)} package items missing")
    args.output.mkdir(parents=True, exist_ok=False)
    records_path = args.output / "chatgpt_review_records.jsonl"
    write_jsonl(records_path, imported)
    summary = {
        "summary_identity": "official-odds-chatgpt-assisted-visual-review-import-summary@1.0.0",
        "package_contract": package.get("package_contract"),
        "response_sha256": sha256_file(args.response),
        "package_items_sha256": sha256_file(package_dir / "review_items.jsonl"),
        "record_count": len(imported),
        "status_counts": dict(Counter(row["review_status"] for row in imported)),
        "review_method": "CHATGPT_ASSISTED_VISUAL_REVIEW",
        "accepted_payload_written": False,
        "archive_written": False,
        "training_written": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "VALIDATED_ADDITIVE_EVIDENCE_ONLY",
    }
    (args.output / "chatgpt_review_import_summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    manifest = {
        "manifest_identity": "official-odds-chatgpt-assisted-visual-review-import-manifest@1.0.0",
        "package_dir": str(package_dir),
        "response_sha256": summary["response_sha256"],
        "record_sha256": sha256_file(records_path),
        "summary_sha256": sha256_file(args.output / "chatgpt_review_import_summary.json"),
        "record_count": len(imported),
        "substantive_hash": sha256_json({"record_sha256": sha256_file(records_path), "status_counts": summary["status_counts"], "review_method": summary["review_method"]}),
    }
    (args.output / "chatgpt_review_import_manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({"output": str(args.output), "record_count": len(imported), "status_counts": summary["status_counts"], "status": summary["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
