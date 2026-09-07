"""Run conservative local OCR enrichment over the 432-cell review queue."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_ocr_consensus import (  # noqa: E402
    CONTRACT_IDENTITY,
    PREPROCESSING_PASSES,
    SCHEMA_IDENTITY,
    STATUS_AMBIGUOUS,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_UNRESOLVED,
    canonical_bytes,
    consensus_from_runs,
    discover_engines,
    load_jsonl,
    normalize_numeric,
    preprocessing_config_hash,
    record_hash,
    render_preprocessed,
    run_tesseract,
    sha256_bytes,
    sha256_file,
    sha256_json,
    stable_trace_id,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/manual_review_workbench_r001_revision_001/review_queue.jsonl")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/ocr_evidence_r001_revision_004")
    parser.add_argument("--output", type=Path, default=ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/local_ocr_consensus_r001_revision_001")
    parser.add_argument("--limit", type=int, default=0, help="debug-only limit; production run uses 0")
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def resolve_crop(evidence_root: Path, item: dict) -> Path:
    relative = item.get("crop_evidence", {}).get("evidence_region_path")
    if not relative:
        raise RuntimeError(f"missing evidence_region_path for {item.get('queue_item_id')}")
    path = evidence_root / relative
    if not path.is_file():
        raise RuntimeError(f"crop missing: {path}")
    expected = item.get("crop_evidence", {}).get("crop_hash")
    actual = sha256_file(path)
    if expected and expected != actual:
        raise RuntimeError(f"crop hash mismatch for {item.get('queue_item_id')}: expected={expected} actual={actual}")
    return path


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    queue = load_jsonl(args.queue)
    if args.limit:
        queue = queue[: args.limit]
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    engines = discover_engines()
    available = [item for item in engines if item.get("available")]
    tesseract = next((item for item in available if item.get("engine_identity") == "tesseract"), None)
    run_id = f"LOCAL-OCR-CONSENSUS-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    records: list[dict] = []
    errors: list[dict] = []
    preprocess_hash = preprocessing_config_hash()
    def process_one(index: int, item: dict, temp: Path) -> tuple[int, dict, list[dict]]:
        item_id = str(item["queue_item_id"])
        crop = resolve_crop(args.evidence_root, item)
        runs: list[dict] = []
        local_errors: list[dict] = []
        if tesseract:
            for pass_spec in PREPROCESSING_PASSES:
                transformed = temp / f"{index:04d}_{pass_spec['pass_id']}.png"
                try:
                    transformed_hash = render_preprocessed(crop, transformed, pass_spec["transform"])
                    raw_text, stderr = run_tesseract(tesseract["engine_path"], transformed, pass_spec["psm"])
                    runs.append({
                        "engine_identity": "tesseract",
                        "engine_version": tesseract.get("engine_version"),
                        "engine_path_sha256": sha256_bytes(tesseract["engine_path"].encode("utf-8")),
                        "pass_id": pass_spec["pass_id"],
                        "preprocessing_transform": pass_spec["transform"],
                        "preprocessing_config_hash": preprocess_hash,
                        "transformed_image_sha256": transformed_hash,
                        "raw_output": raw_text,
                        "normalized_value": normalize_numeric(raw_text),
                        "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
                    })
                except Exception as exc:  # retain the cell and fail closed
                    local_errors.append({"queue_item_id": item_id, "pass_id": pass_spec["pass_id"], "error": type(exc).__name__, "message": str(exc)})
        else:
            runs.append({
                "engine_identity": "NO_ENGINE_AVAILABLE",
                "engine_version": None,
                "pass_id": "NO_ENGINE",
                "preprocessing_config_hash": preprocess_hash,
                "raw_output": "",
                "normalized_value": None,
            })
        result = consensus_from_runs(runs, engine_count=len({run.get("engine_identity") for run in runs if run.get("engine_identity") not in {None, "NO_ENGINE_AVAILABLE"}}))
        trace_id = stable_trace_id(item_id)
        record = {
            "schema_version": SCHEMA_IDENTITY,
            "contract_identity": CONTRACT_IDENTITY,
            "run_id": run_id,
            "review_item_id": item_id,
            "stable_trace_id": trace_id,
            "source": {
                "artifact_identity": item.get("artifact_identity"),
                "artifact_slot": item.get("artifact_slot"),
                "market": item.get("market"),
                "cell_label": item.get("cell_label"),
                "ordering_index": item.get("ordering_index"),
                "raw_image_sha256": item.get("raw_image_sha256"),
                "raw_zip_member": item.get("raw_zip_member"),
                "crop_hash": item.get("crop_evidence", {}).get("crop_hash"),
                "crop_path": item.get("crop_evidence", {}).get("evidence_region_path"),
                "prior_trace_record_id": item.get("prior_trace_record_id"),
                "prior_trace_record_sha256": item.get("prior_trace_record_sha256"),
            },
            "preprocessing_config_hash": preprocess_hash,
            "engine_inventory": engines,
            "engine_runs": runs,
            "consensus": result,
            "auto_confirm_policy": {
                "minimum_distinct_engine_identities": 2,
                "single_engine_multi_pass_auto_confirm": False,
                "grammar": "positive decimal, max 4 fractional digits, no inference",
            },
            "source_mutation": False,
        }
        record["consensus_trace_hash"] = sha256_json({"stable_trace_id": trace_id, "runs": runs, "consensus": result})
        record["consensus_record_sha256"] = record_hash(record)
        return index, record, local_errors

    with tempfile.TemporaryDirectory(prefix="jcfb_local_ocr_") as temp_dir:
        temp = Path(temp_dir)
        futures = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            for index, item in enumerate(queue, start=1):
                futures.append(executor.submit(process_one, index, item, temp))
            completed: dict[int, dict] = {}
            error_by_index: dict[int, list[dict]] = {}
            for future in as_completed(futures):
                index, record, local_errors = future.result()
                completed[index] = record
                error_by_index[index] = local_errors
        records = [completed[index] for index in sorted(completed)]
        for index in sorted(error_by_index):
            errors.extend(error_by_index[index])
        # The result list is sorted by input order after parallel execution.
    consensus_path = output / "local_ocr_consensus_records.jsonl"
    exception_path = output / "exception_queue.jsonl"
    confirmed = [record for record in records if record["consensus"]["status"] == STATUS_CONFIRMED]
    exceptions = [record for record in records if record["consensus"]["status"] != STATUS_CONFIRMED]
    write_jsonl(consensus_path, records)
    write_jsonl(exception_path, exceptions)
    per_market: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        per_market[record["source"]["market"]][record["consensus"]["status"]] += 1
    summary = {
        "summary_identity": "official-odds-local-ocr-consensus-summary@1.0.0",
        "contract_identity": CONTRACT_IDENTITY,
        "run_id": run_id,
        "input_queue": str(args.queue),
        "input_queue_sha256": sha256_file(args.queue),
        "candidate_count": len(records),
        "auto_confirmed_count": len(confirmed),
        "exception_count": len(exceptions),
        "status_counts": dict(Counter(record["consensus"]["status"] for record in records)),
        "per_market": {market: dict(counts) for market, counts in sorted(per_market.items())},
        "engine_inventory": engines,
        "preprocessing_config_hash": preprocess_hash,
        "errors": {"count": len(errors), "sha256": sha256_json(errors)},
        "training_written": False,
        "accepted_payload_written": False,
        "archive_written": False,
    }
    (output / "engine_inventory.json").write_bytes(canonical_bytes(engines) + b"\n")
    (output / "run_errors.json").write_bytes(canonical_bytes(errors) + b"\n")
    (output / "local_ocr_consensus_summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    manifest = {
        "manifest_identity": "official-odds-local-ocr-consensus-manifest@1.0.0",
        "schema_version": SCHEMA_IDENTITY,
        "run_id": run_id,
        "record_count": len(records),
        "exception_count": len(exceptions),
        "consensus_records_sha256": sha256_file(consensus_path),
        "exception_queue_sha256": sha256_file(exception_path),
        "summary_sha256": sha256_file(output / "local_ocr_consensus_summary.json"),
        "substantive_hash": sha256_json({"summary": summary, "record_count": len(records), "exception_count": len(exceptions), "preprocessing_config_hash": preprocess_hash}),
    }
    (output / "local_ocr_consensus_manifest.json").write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({"output": str(output), "candidate_count": len(records), "auto_confirmed": len(confirmed), "exceptions": len(exceptions), "statuses": summary["status_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
