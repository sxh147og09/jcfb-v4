"""Build a deterministic, single-upload ChatGPT visual review package."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_ocr_consensus import (  # noqa: E402
    CONTRACT_IDENTITY,
    canonical_bytes,
    load_jsonl,
    sha256_bytes,
    sha256_file,
    sha256_json,
    write_jsonl,
)


PACKAGE_CONTRACT = "official-odds-chatgpt-assisted-visual-review-package@1.0.0"
RESPONSE_CONTRACT = "official-odds-chatgpt-assisted-visual-review-response@1.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exception-queue", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/local_ocr_consensus_r001_revision_001/exception_queue.jsonl")
    parser.add_argument("--queue", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/manual_review_workbench_r001_revision_001/review_queue.jsonl")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/ocr_evidence_r001_revision_004")
    parser.add_argument("--handoff-zip", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/chatgpt-library-handoff.zip")
    parser.add_argument("--output", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/chatgpt_review_package_r001_revision_001")
    return parser.parse_args()


def fixed_zip(entries: dict[str, bytes]) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    queue = load_jsonl(args.exception_queue)
    source_queue = {item["queue_item_id"]: item for item in load_jsonl(args.queue)}
    output = args.output
    (output / "crops").mkdir(parents=True, exist_ok=False)
    (output / "originals").mkdir()
    (output / "schema").mkdir()
    entries: dict[str, bytes] = {}
    items: list[dict] = []
    originals: dict[str, bytes] = {}
    with zipfile.ZipFile(args.handoff_zip, "r") as handoff:
        names = set(handoff.namelist())
        for index, record in enumerate(queue, start=1):
            source = record["source"]
            review_item_id = record["review_item_id"]
            original_queue_item = source_queue.get(review_item_id)
            if original_queue_item is None:
                raise RuntimeError(f"review item missing from source queue: {review_item_id}")
            crop_relative = source["crop_path"]
            crop_path = args.evidence_root / crop_relative
            crop_bytes = crop_path.read_bytes()
            crop_hash = sha256_bytes(crop_bytes)
            if crop_hash != source["crop_hash"]:
                raise RuntimeError(f"crop hash mismatch for {review_item_id}")
            raw_member = source["raw_zip_member"]
            if raw_member not in names:
                raise RuntimeError(f"raw member missing for {review_item_id}: {raw_member}")
            raw_bytes = handoff.read(raw_member)
            raw_hash = sha256_bytes(raw_bytes)
            if raw_hash != source["raw_image_sha256"]:
                raise RuntimeError(f"raw image hash mismatch for {review_item_id}")
            crop_name = f"crops/{review_item_id}.png"
            original_name = f"originals/{raw_hash.removeprefix('sha256:')}.png"
            entries[crop_name] = crop_bytes
            entries[original_name] = raw_bytes
            originals[original_name] = raw_bytes
            item = {
                "review_item_id": review_item_id,
                "ordering_index": index,
                "artifact_identity": source.get("artifact_identity"),
                "artifact_slot": source.get("artifact_slot"),
                "market": source.get("market"),
                "cell_label": source.get("cell_label"),
                "source": {
                    "raw_image_sha256": source["raw_image_sha256"],
                    "raw_zip_member": source["raw_zip_member"],
                    "crop_sha256": crop_hash,
                    "crop_package_path": crop_name,
                    "original_package_path": original_name,
                    "prior_trace_record_id": source.get("prior_trace_record_id"),
                    "prior_trace_record_sha256": source.get("prior_trace_record_sha256"),
                },
                "coordinates": {
                    "pixel": original_queue_item.get("pixel_coordinates"),
                    "normalized": original_queue_item.get("normalized_coordinates"),
                    "locator_hash": original_queue_item.get("locator_hash"),
                },
                "local_ocr_consensus": {
                    "status": record["consensus"]["status"],
                    "reason": record["consensus"]["reason"],
                    "value": record["consensus"].get("value"),
                    "distinct_values": record["consensus"].get("distinct_values", []),
                    "evidence_hash": record.get("consensus_trace_hash"),
                    "engine_runs": record.get("engine_runs", []),
                },
                "trace_id": record["stable_trace_id"],
                "trace_hash": record["consensus_trace_hash"],
                "expected_answer_schema": {
                    "value_text": "string or null",
                    "normalized_value": "positive decimal string or null",
                    "review_status": ["CHATGPT_CONFIRMED", "CHATGPT_REVIEW_AMBIGUOUS", "CHATGPT_UNREADABLE", "CHATGPT_SOURCE_MISMATCH", "CHATGPT_CONFLICT"],
                    "review_method": "CHATGPT_ASSISTED_VISUAL_REVIEW",
                },
            }
            items.append(item)
    items_bytes = b"".join(canonical_bytes(item) + b"\n" for item in items)
    entries["review_items.jsonl"] = items_bytes
    response_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": RESPONSE_CONTRACT,
        "type": "object",
        "required": ["review_item_id", "source_raw_image_sha256", "source_crop_sha256", "value_text", "normalized_value", "review_status", "review_method"],
        "properties": {
            "review_item_id": {"type": "string"},
            "source_raw_image_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "source_crop_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "value_text": {"type": ["string", "null"]},
            "normalized_value": {"type": ["string", "null"]},
            "review_status": {"enum": ["CHATGPT_CONFIRMED", "CHATGPT_REVIEW_AMBIGUOUS", "CHATGPT_UNREADABLE", "CHATGPT_SOURCE_MISMATCH", "CHATGPT_CONFLICT"]},
            "review_method": {"const": "CHATGPT_ASSISTED_VISUAL_REVIEW"},
            "notes": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    }
    entries["schema/review_response.schema.json"] = canonical_bytes(response_schema) + b"\n"
    package = {
        "package_contract": PACKAGE_CONTRACT,
        "package_version": "1.0.0",
        "review_role": "CHATGPT_ASSISTED_VISUAL_REVIEW",
        "review_is_human": False,
        "review_item_count": len(items),
        "source_exception_queue_sha256": sha256_file(args.exception_queue),
        "source_handoff_zip_sha256": sha256_file(args.handoff_zip),
        "local_ocr_contract": CONTRACT_IDENTITY,
        "response_contract": RESPONSE_CONTRACT,
        "accepted_payload_written": False,
        "archive_written": False,
        "training_written": False,
        "package_substantive_hash": sha256_json({"review_items_sha256": sha256_bytes(items_bytes), "item_count": len(items), "file_names": sorted(entries)}),
        "zip_serialization": {"profile": "fixed-timestamp-sorted-deflate-level-9", "timestamp": "1980-01-01T00:00:00Z"},
    }
    entries["package.json"] = canonical_bytes(package) + b"\n"
    manifest = {
        "manifest_identity": "official-odds-chatgpt-review-package-manifest@1.0.0",
        "package_contract": PACKAGE_CONTRACT,
        "review_item_count": len(items),
        "crop_count": len(items),
        "unique_original_count": len(originals),
        "file_count": len(entries) + 2,
        "item_count_by_market": {market: sum(1 for item in items if item["market"] == market) for market in sorted({item["market"] for item in items})},
        "review_items_sha256": sha256_bytes(items_bytes),
        "package_substantive_hash": package["package_substantive_hash"],
    }
    entries["manifest.json"] = canonical_bytes(manifest) + b"\n"
    readme = """# JCFB V4 ChatGPT visual review package\n\nThis package is additive evidence only. Review each crop against its paired original image. Return one JSON object per `review_item_id` using `schema/review_response.schema.json`.\n\nThe allowed method is `CHATGPT_ASSISTED_VISUAL_REVIEW`; do not label these observations as HUMAN review. Do not infer from neighboring cells, later snapshots, odds plausibility, predictions, or model output. Use `normalized_value` only when the visible crop supports an exact positive decimal value; otherwise use an explicit non-confirming status.\n\nThe local runtime will fail closed on missing items, extra items, source SHA mismatches, crop SHA mismatches, invalid values, or any method other than `CHATGPT_ASSISTED_VISUAL_REVIEW`.\n"""
    entries["README.md"] = readme.encode("utf-8")
    zip_bytes = fixed_zip(entries)
    zip_path = output / "chatgpt_review_package.zip"
    zip_path.write_bytes(zip_bytes)
    (output / "review_items.jsonl").write_bytes(items_bytes)
    (output / "package.json").write_bytes(entries["package.json"])
    (output / "manifest.json").write_bytes(entries["manifest.json"])
    (output / "README.md").write_bytes(entries["README.md"])
    (output / "schema" / "review_response.schema.json").write_bytes(entries["schema/review_response.schema.json"])
    for name, content in entries.items():
        if name.startswith("crops/") or name.startswith("originals/"):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    zip_sha256 = sha256_bytes(zip_bytes)
    hashes = {
        "hash_manifest_identity": "official-odds-chatgpt-review-package-hashes@1.0.0",
        "zip_sha256": zip_sha256,
        "package_substantive_hash": package["package_substantive_hash"],
        "zip_file_count": len(entries),
        "review_item_count": len(items),
    }
    (output / "package.json").write_bytes(entries["package.json"])
    (output / "manifest.json").write_bytes(entries["manifest.json"])
    (output / "zip_hashes.json").write_bytes(canonical_bytes(hashes) + b"\n")
    print(json.dumps({"output": str(output), "zip": str(zip_path), "zip_sha256": zip_sha256, "item_count": len(items), "file_count": len(entries), "substantive_hash": package["package_substantive_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
