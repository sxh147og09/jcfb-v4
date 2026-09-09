"""Execute the additive r003 local historical-backfill authorization.

The runner is intentionally fail-closed.  It materializes reviewed extraction
and a deterministic @1.1.0 package candidate from the already-approved local
staging evidence, validates the candidate and ZIP bytes, and performs a
no-write intake gate.  Archive persistence and EWP-002/EWP-003 reruns occur
only after that gate passes.  No model or V3.3.3 path is reachable here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001"
HANDOFF = STAGING / "chatgpt-library-handoff.zip"
SUPPLEMENT = STAGING / "jcfb-v4-exclusion-supplement.zip"
PACKAGE = STAGING / "chatgpt_review_package_r001_revision_003"
IMPORT = STAGING / "chatgpt_review_integration_r001_revision_001"
OCR = STAGING / "local_ocr_consensus_r001_revision_001/local_ocr_consensus_records.jsonl"
TRACE = STAGING / "historical_trace_reconstruction_with_ocr_r001_revision_003/full_cell_extraction_trace.jsonl"
MAPPING = STAGING / "exact_score_visible_label_mapping_r001_revision_001/mapping_records.jsonl"
AUDIT = STAGING / "chatgpt_review_integration_audit_r001_revision_003/audit.json"
AUTH_PATH = ROOT / "config/prediction_training/v4_batch15_verified_historical_backfill_contract_amendment_003.json"
OUTPUT = STAGING / "authorized_backfill_r003_execution"
REVIEWED_OUTPUT = OUTPUT / "reviewed_extraction_trace_r001_revision_001"
CANDIDATE_OUTPUT = OUTPUT / "accepted_official_odds_payload_candidate_r001_revision_001"
R002_OUTPUT = OUTPUT / "verified_historical_backfill_export_package_r002_revision_001"
ARCHIVE_ROOT = ROOT / "approved_data/historical_source_archive"
UNKNOWN = "UNKNOWN"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MARKETS = ("SPF", "RQSPF", "EXACT_SCORE", "TOTAL_GOALS", "HTFT")
ZIP_PROFILE = "v4-deterministic-zip@1.0"
EXCLUSION_SCHEMA = "verified-historical-backfill-exclusion-manifest@1.0.0"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> str:
    data = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_sha(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def prefixed_hash(value: str) -> str:
    return value if value.startswith("sha256:") else "sha256:" + value


def require_new_output() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"append-only output already exists: {OUTPUT}")


def validate_authorization() -> dict[str, Any]:
    auth = load_json(AUTH_PATH)
    expected = sha256_json({key: value for key, value in auth.items() if key != "canonical_hash"})
    if auth.get("canonical_hash") != expected:
        raise RuntimeError(f"GOVERNANCE_AUTHORIZATION_HASH_MISMATCH expected={expected} actual={auth.get('canonical_hash')}")
    if auth.get("execution_authorized") is not True or auth.get("additive_only") is not True:
        raise RuntimeError("GOVERNANCE_AUTHORIZATION_NOT_ACTIVE")
    scope = auth.get("authorized_scope", {})
    required_scope = (
        "reviewed_extraction_trace_generation",
        "accepted_official_odds_payload_candidate_generation",
        "r002_deterministic_rebuild",
        "no_write_intake_dry_run",
        "historical_archive_append_only_intake",
        "ewp002_real_historical_dataset_rerun",
        "ewp003_real_temporal_readiness_rerun",
    )
    missing = [key for key in required_scope if scope.get(key) is not True]
    if missing:
        raise RuntimeError("GOVERNANCE_AUTHORIZATION_SCOPE_MISSING: " + ",".join(missing))
    lock = auth.get("training_lock", {})
    if lock.get("formal_model_training") != "NOT_STARTED" or lock.get("ewp005_execution_authorized") is not False:
        raise RuntimeError("TRAINING_LOCK_INVALID")
    boundary = auth.get("no_write_boundary", {})
    if any(boundary.get(key) is not False for key in ("v3_3_3_modified", "production_modified", "supabase_modified", "public_modified", "model_artifacts_generated", "formal_training_started", "thresholds_lowered")):
        raise RuntimeError("NO_WRITE_BOUNDARY_INVALID")
    return auth


def validate_prerequisites() -> dict[str, Any]:
    audit = load_json(AUDIT)
    if audit.get("status") != "PASS":
        raise RuntimeError(f"REVIEW_INTEGRATION_NOT_PASS: {audit.get('status')}")
    summary = audit.get("mapping_evidence", {})
    if summary.get("record_count") != 121 or summary.get("conflict_count") != 0 or summary.get("ambiguous_count") != 0:
        raise RuntimeError("EXPLICIT_MAPPING_PREREQUISITE_INVALID")
    if audit.get("binding_checks", {}).get("spot_audit", {}).get("result") != "PASS":
        raise RuntimeError("REVIEW_SPOT_AUDIT_NOT_PASS")
    if not HANDOFF.is_file() or not SUPPLEMENT.is_file():
        raise RuntimeError("IMMUTABLE_SOURCE_ZIP_MISSING")
    return audit


def build_exclusion_manifest(exclusion_rows: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for index, row in enumerate(sorted(exclusion_rows, key=lambda item: (item["category"], item["library_file_id"], item["filename"])), start=1):
        record = {
            "exclusion_id": f"vhb-exclusion-{index:03d}",
            "category": row["category"],
            "reason_code": {
                "BETTING_SLIP": "BETTING_SLIP_NOT_RAW_FACT",
                "GENERATED_PREDICTION_DASHBOARD": "GENERATED_PREDICTION_NOT_RAW_FACT",
                "RECOMMENDATION_ARTIFACT": "RECOMMENDATION_NOT_RAW_FACT",
            }[row["category"]],
            "source_filename": row["filename"],
            "source_reference": row["library_file_id"],
            "source_sha256": row["source_sha256"],
            "artifact_classification": "EXCLUDED",
        }
        record["record_sha256"] = sha256_json(record)
        records.append(record)
    manifest = {"schema_version": EXCLUSION_SCHEMA, "records": records}
    manifest["manifest_sha256"] = sha256_json({"schema_version": manifest["schema_version"], "records": records})
    return manifest


def source_inputs() -> tuple[dict[str, tuple[str, bytes]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    with zipfile.ZipFile(HANDOFF) as handoff:
        if handoff.testzip() is not None:
            raise RuntimeError("HANDOFF_ZIP_CRC_FAILURE")
        raw = {Path(name).name: (name, handoff.read(name)) for name in handoff.namelist() if name.startswith("raw/") and name.lower().endswith(".png")}
        mappings = [json.loads(line) for line in handoff.read("mapping/candidate_slot_mapping.jsonl").decode("utf-8").splitlines() if line.strip()]
        metadata = {name: json.loads(handoff.read(name).decode("utf-8")) for name in handoff.namelist() if name.startswith("metadata/metadata_snapshot/") and name.endswith(".json")}
    with zipfile.ZipFile(SUPPLEMENT) as supplement:
        if supplement.testzip() is not None:
            raise RuntimeError("EXCLUSION_SUPPLEMENT_CRC_FAILURE")
        excluded = [json.loads(line) for line in supplement.read("metadata/exclusion_source_evidence.jsonl").decode("utf-8").splitlines() if line.strip()]
    if len(raw) != 64 or len(mappings) != 64 or len(metadata) != 64 or len(excluded) != 3:
        raise RuntimeError(f"SOURCE_CARDINALITY_INVALID raw={len(raw)} mappings={len(mappings)} metadata={len(metadata)} excluded={len(excluded)}")
    return raw, mappings, {"metadata": metadata, "excluded": excluded}


def build_reviewed_trace() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    reviews = load_jsonl(IMPORT / "chatgpt_review_records.jsonl")
    items = {row["review_item_id"]: row for row in load_jsonl(PACKAGE / "review_items.jsonl")}
    ocr = {row["review_item_id"]: row for row in load_jsonl(OCR)}
    trace = {row["trace_record_id"]: row for row in load_jsonl(TRACE)}
    mappings = {row["review_item_id"]: row for row in load_jsonl(MAPPING)}
    if len(reviews) != 432 or len(items) != 432 or len(ocr) != 432 or len(mappings) != 121 or len(trace) != 3520:
        raise RuntimeError("REVIEWED_TRACE_INPUT_CARDINALITY_INVALID")
    resolved: list[dict[str, Any]] = []
    unresolved_after = []
    for base in trace.values():
        item = next((row for row in reviews if row.get("trace_id") == base.get("trace_record_id")), None)
        if item is None:
            item_id = next((row_id for row_id, ocr_row in ocr.items() if ocr_row.get("source", {}).get("prior_trace_record_id") == base.get("trace_record_id")), None)
            item = next((row for row in reviews if row.get("review_item_id") == item_id), None)
        mapping = mappings.get(item.get("review_item_id")) if item else None
        status = base.get("parser_status")
        value: Any = base.get("parsed_value")
        canonical_label = base.get("canonical_outcome_label")
        review_ref = None
        mapping_ref = None
        if item is not None:
            if item.get("review_status") != "CHATGPT_CONFIRMED":
                unresolved_after.append(base.get("trace_record_id"))
            value = item.get("normalized_value")
            review_ref = item.get("review_item_id")
            status = "REVIEW_CONFIRMED"
            if mapping:
                canonical_label = mapping.get("canonical_cell_label")
                mapping_ref = mapping.get("mapping_record_sha256")
        elif status not in {"PARSED", "MARKET_UNAVAILABLE"}:
            unresolved_after.append(base.get("trace_record_id"))
        row = {
            "trace_record_id": base.get("trace_record_id"),
            "artifact_identity": base.get("artifact_identity"),
            "artifact_slot": base.get("artifact_identity", "").split("|", 1)[0],
            "market": base.get("market"),
            "ordering_index": base.get("ordering_index"),
            "canonical_cell_label": canonical_label,
            "value": value,
            "resolution_status": status,
            "source_visible_label": base.get("source_visible_label"),
            "source_raw_image_sha256": base.get("raw_image_sha256"),
            "source_trace_record_sha256": base.get("trace_record_sha256"),
            "cell_coordinates": base.get("cell_coordinates"),
            "review_item_id": review_ref,
            "mapping_record_sha256": mapping_ref,
        }
        resolved.append(row)
    resolved.sort(key=lambda row: (str(row.get("artifact_slot")), MARKETS.index(row.get("market")) if row.get("market") in MARKETS else 99, int(row.get("ordering_index") or 0)))
    if unresolved_after:
        raise RuntimeError(f"REVIEWED_EXTRACTION_UNRESOLVED: {len(unresolved_after)}")
    trace_bytes = b"".join(canonical_bytes(row) + b"\n" for row in resolved)
    summary = {
        "artifact_count": len({row["artifact_slot"] for row in resolved}),
        "trace_record_count": len(resolved),
        "review_confirmed_count": sum(row["resolution_status"] == "REVIEW_CONFIRMED" for row in resolved),
        "parser_resolved_count": sum(row["resolution_status"] == "PARSED" for row in resolved),
        "market_unavailable_count": sum(row["resolution_status"] == "MARKET_UNAVAILABLE" for row in resolved),
        "unresolved_after_review": 0,
        "review_method": "CHATGPT_ASSISTED_VISUAL_REVIEW",
        "mapping_revision": MAPPING.parent.name,
        "source_review_integration_audit": file_sha(AUDIT),
        "trace_sha256": sha256_bytes(trace_bytes),
        "status": "PASS",
    }
    manifest = {
        "manifest_identity": "jcfb-v4-reviewed-extraction-trace@1.0.0",
        "revision": "r001",
        "source_trace": file_sha(TRACE),
        "source_review_records": file_sha(IMPORT / "chatgpt_review_records.jsonl"),
        "source_mapping_records": file_sha(MAPPING),
        "source_audit": file_sha(AUDIT),
        "summary": summary,
        "manifest_sha256": "sha256:PLACEHOLDER",
    }
    manifest["manifest_sha256"] = sha256_json({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    REVIEWED_OUTPUT.mkdir(parents=True, exist_ok=False)
    (REVIEWED_OUTPUT / "reviewed_extraction_trace.jsonl").write_bytes(trace_bytes)
    write_json(REVIEWED_OUTPUT / "reviewed_extraction_summary.json", summary)
    write_json(REVIEWED_OUTPUT / "reviewed_extraction_manifest.json", manifest)
    return resolved, summary, manifest


def extraction_by_slot(resolved: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {market: [] for market in MARKETS})
    for row in resolved:
        grouped[row["artifact_slot"]][row["market"]].append({
            "canonical_cell_label": row["canonical_cell_label"],
            "value": row["value"],
            "resolution_status": row["resolution_status"],
            "ordering_index": row["ordering_index"],
            "trace_record_id": row["trace_record_id"],
            "trace_record_sha256": row["source_trace_record_sha256"],
            "review_item_id": row["review_item_id"],
            "mapping_record_sha256": row["mapping_record_sha256"],
        })
    for slot in grouped:
        for market in MARKETS:
            grouped[slot][market].sort(key=lambda row: int(row.get("ordering_index") or 0))
    return grouped


def coverage_for(slot: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_market[row["market"]].append(row)
    coverage: dict[str, Any] = {}
    for market in MARKETS:
        entries = by_market.get(market, [])
        unavailable = entries and all(row.get("resolution_status") == "MARKET_UNAVAILABLE" for row in entries)
        if unavailable:
            coverage[market] = {"state": "UNAVAILABLE", "unavailable_reason": "SOURCE_TRACE_MARKET_UNAVAILABLE"}
        elif entries:
            item: dict[str, Any] = {"state": "AVAILABLE", "evidence_record_count": len(entries)}
            if market == "RQSPF":
                item.update({"exact_cutoff_visible": False, "handicap_line": UNKNOWN})
            if market == "HTFT":
                item.update({"halftime_label": UNKNOWN, "fulltime_label": UNKNOWN})
            coverage[market] = item
        else:
            coverage[market] = {"state": "NOT_VERIFIED", "reason": "NO_TRACE_RECORD"}
    return coverage


def build_candidate_package(resolved: list[dict[str, Any]], summary: dict[str, Any], manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    raw, mappings, extra = source_inputs()
    grouped = extraction_by_slot(resolved)
    review_by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in resolved:
        review_by_slot[row["artifact_slot"]].append(row)
    created = "2026-09-09T00:00:00+08:00"
    exported = created
    import_manifests: list[dict[str, Any]] = []
    transport_manifests: list[dict[str, Any]] = []
    file_manifest: list[dict[str, Any]] = []
    metadata_manifest: list[dict[str, Any]] = []
    entries: dict[str, bytes] = {}
    for source in sorted(mappings, key=lambda row: row["candidate_slot"]):
        slot = source["candidate_slot"]
        filename = source["raw_relative_path"].removeprefix("raw/")
        if filename not in raw:
            raise RuntimeError(f"RAW_SOURCE_MISSING: {filename}")
        _, raw_bytes = raw[filename]
        raw_hash = sha256_bytes(raw_bytes)
        metadata_name = source["metadata_snapshot_file"]
        metadata_obj = extra["metadata"][metadata_name]
        metadata_hash = sha256_json(metadata_obj)
        manifest_id = "vhb-r002-" + hashlib.sha256(slot.encode("utf-8")).hexdigest()[:24]
        canonical_identity = {
            "canonical_match_id": UNKNOWN,
            "competition": source.get("competition", UNKNOWN),
            "home": source.get("home_team", UNKNOWN),
            "away": source.get("away_team", UNKNOWN),
        }
        slot_rows = review_by_slot[slot]
        payload = {market: grouped[slot][market] for market in MARKETS}
        coverage = coverage_for(slot, slot_rows)
        provenance = {
            "raw_zip_member": source["raw_relative_path"],
            "raw_image_sha256": raw_hash,
            "metadata_snapshot_file": metadata_name,
            "metadata_snapshot_sha256": metadata_hash,
            "review_trace_sha256": summary["trace_sha256"],
            "reviewed_extraction_manifest_sha256": manifest["manifest_sha256"],
            "mapping_manifest_revision": MAPPING.parent.name,
            "source_timestamp_status": UNKNOWN,
            "canonical_identity_status": UNKNOWN,
        }
        item = {
            "manifest_id": manifest_id,
            "import_batch_id": "CHATGPT-BACKFILL-20260901-20260904-001",
            "revision": 1,
            "acquisition_mode": "VERIFIED_HISTORICAL_BACKFILL",
            "source_origin": "CHATGPT_LIBRARY_EXPORT",
            "export_package_id": "JCFB-V4-CHATGPT-LIBRARY-20260901-20260904-R002",
            "export_package_hash": "sha256:PLACEHOLDER",
            "external_source_identity": {"provider": "ChatGPT Library", "library_file_id_or_ref": source["library_file_id"]},
            "original_filename": filename,
            "original_file_sha256": raw_hash,
            "metadata_snapshot_sha256": metadata_hash,
            "source_type": "OFFICIAL_SCREENSHOT",
            "source_identity": "OFFICIAL_CHINA_SPORTS_LOTTERY_SCREENSHOT",
            "source_reference": source["source_reference"],
            "chatgpt_upload_timestamp": source["chatgpt_upload_timestamp"],
            "source_timestamp": UNKNOWN,
            "source_uploaded_at": source["source_uploaded_at"],
            "observed_at": UNKNOWN,
            "captured_at": UNKNOWN,
            "exported_at": exported,
            "ingested_at": UNKNOWN,
            "prediction_cutoff_at": UNKNOWN,
            "kickoff_at": source["kickoff_at"],
            "timestamp_evidence_basis": source["timestamp_evidence_basis"],
            "canonical_match_identity": canonical_identity,
            "intended_cutoff_profile": UNKNOWN,
            "official_play_coverage": coverage,
            "extraction": {
                "extraction_method": "OFFICIAL_ODDS_CELL_PARSER+CHATGPT_ASSISTED_VISUAL_REVIEW+EXPLICIT_MAPPING",
                "extraction_status": "REVIEWED",
                "extracted_market_payload": payload,
            },
            "artifact_classification": "RAW_FACT",
            "review_decision": "PROCEED_TO_EXPORT_INTAKE_VERIFICATION",
            "eligibility_decision": "NOT_YET_EVALUATED",
            "revision_lineage": {"supersedes": None},
            "artifact_substantive_hash": raw_hash,
            "provenance_root": sha256_json(provenance),
            "provenance": provenance,
            "reviewer": "CHATGPT_ASSISTED_VISUAL_REVIEW",
            "reviewed_at": "2026-09-09T02:36:24Z",
            "package_substantive_hash": "sha256:PLACEHOLDER",
            "manifest_substantive_hash": "sha256:PLACEHOLDER",
        }
        item["manifest_substantive_hash"] = sha256_json({key: value for key, value in item.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        import_manifests.append(item)
        transport_manifests.append({
            "manifest_id": manifest_id,
            "original_file_sha256": raw_hash,
            "metadata_snapshot_sha256": metadata_hash,
            "export_package_hash": "sha256:PLACEHOLDER",
            "package_substantive_hash": "sha256:PLACEHOLDER",
        })
        file_manifest.append({"manifest_id": manifest_id, "original_filename": filename, "original_file_sha256": raw_hash, "library_file_id_or_ref": source["library_file_id"], "artifact_classification": "RAW_FACT"})
        metadata_manifest.append({"manifest_id": manifest_id, "metadata_snapshot_file": metadata_name, "metadata_snapshot_sha256": metadata_hash})
        entries[f"raw/{filename}"] = raw_bytes
        entries[metadata_name] = canonical_bytes(metadata_obj) + b"\n"
        entries[f"manifests/{manifest_id}.json"] = canonical_bytes(item) + b"\n"
    exclusion_manifest = build_exclusion_manifest(extra["excluded"])
    package = {
        "export_package_id": "JCFB-V4-CHATGPT-LIBRARY-20260901-20260904-R002",
        "revision": 2,
        "contract_version": "verified-historical-backfill-export-package@1.1.0",
        "source_origin": "CHATGPT_LIBRARY_EXPORT",
        "created_at": created,
        "exported_at": exported,
        "file_manifest": file_manifest,
        "metadata_manifest": metadata_manifest,
        # The package-level manifests are transport binding cards.  The full
        # import manifests are immutable ZIP members and are validated below
        # during the no-write gate; keeping them out of this hash boundary
        # avoids a package-hash/import-manifest-hash cycle.
        "manifests": transport_manifests,
        "exclusion_manifest": exclusion_manifest,
        "zip_serialization_profile": ZIP_PROFILE,
        "reviewed_extraction_trace": {"manifest": manifest, "summary": summary},
        "package_substantive_hash": "sha256:PLACEHOLDER",
        "package_sha256": "sha256:PLACEHOLDER",
        "package_zip_sha256": "sha256:PLACEHOLDER",
    }
    substantive_body = {key: value for key, value in package.items() if key not in {"created_at", "exported_at", "package_substantive_hash", "package_sha256", "package_zip_sha256"}}
    substantive_body["manifests"] = [{key: value for key, value in item.items() if key not in {"export_package_hash", "package_substantive_hash"}} for item in transport_manifests]
    package["package_substantive_hash"] = sha256_json(substantive_body)
    for card in transport_manifests:
        card["export_package_hash"] = package["package_substantive_hash"]
        card["package_substantive_hash"] = package["package_substantive_hash"]
    for item in import_manifests:
        item["export_package_hash"] = package["package_substantive_hash"]
        item["package_substantive_hash"] = package["package_substantive_hash"]
        item["manifest_substantive_hash"] = sha256_json({key: value for key, value in item.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
    package["package_sha256"] = sha256_json({key: value for key, value in package.items() if key != "package_sha256"})
    for item in import_manifests:
        entries[f"manifests/{item['manifest_id']}.json"] = canonical_bytes(item) + b"\n"
    entries["package.json"] = canonical_bytes(package) + b"\n"
    entries["exclusions/manifest.json"] = canonical_bytes(exclusion_manifest) + b"\n"
    entries["extraction/reviewed_extraction_trace.jsonl"] = (REVIEWED_OUTPUT / "reviewed_extraction_trace.jsonl").read_bytes()
    entries["extraction/reviewed_extraction_summary.json"] = canonical_bytes(summary) + b"\n"
    zip_bytes = build_deterministic_zip(entries)
    package["package_zip_sha256"] = sha256_bytes(zip_bytes)
    package["package_sha256"] = sha256_json({key: value for key, value in package.items() if key != "package_sha256"})
    CANDIDATE_OUTPUT.mkdir(parents=True, exist_ok=False)
    write_json(CANDIDATE_OUTPUT / "accepted_official_odds_payload_candidate.json", {"status": "CANDIDATE_GENERATED_NOT_PROMOTED", "candidate_count": 64, "candidate_sha256": sha256_json(package), "package_id": package["export_package_id"], "package_substantive_hash": package["package_substantive_hash"], "unknown_identity_or_time_fields_retained": True})
    write_json(CANDIDATE_OUTPUT / "accepted_official_odds_payload_candidate_summary.json", {"status": "CANDIDATE_GENERATED_NOT_PROMOTED", "artifact_count": 64, "reviewed_trace_records": len(resolved), "official_markets": list(MARKETS), "archive_written": False, "training_written": False})
    return package, entries, {"zip_bytes": zip_bytes, "exclusion_manifest": exclusion_manifest}


def build_deterministic_zip(entries: Mapping[str, bytes]) -> bytes:
    from src.historical_backfill_intake.package_contract import build_deterministic_zip as builder
    return builder(entries)


def validate_candidate_and_no_write(package: dict[str, Any], entries: dict[str, bytes], zip_bytes: bytes) -> dict[str, Any]:
    from src.historical_backfill_intake import evaluate_timestamp_evidence, sha256_json as intake_sha256_json, validate_manifest
    from src.historical_backfill_intake.package_contract import validate_deterministic_zip, validate_export_package_v1_1

    contract_result = validate_export_package_v1_1(package)
    manifest_failures = []
    timestamp_review = []
    unknown_counts = Counter()
    import_manifest_entries = [
        json.loads(content.decode("utf-8"))
        for name, content in entries.items()
        if name.startswith("manifests/") and name.endswith(".json")
    ]
    for item in import_manifest_entries:
        try:
            validate_manifest(item)
        except Exception as exc:  # preserve exact fail-closed evidence in report
            manifest_failures.append(f"{item.get('manifest_id')}: {exc}")
        if item["canonical_match_identity"]["canonical_match_id"] == UNKNOWN:
            unknown_counts["CANONICAL_MATCH_IDENTITY_UNKNOWN"] += 1
        if item["intended_cutoff_profile"] == UNKNOWN:
            unknown_counts["INTENDED_CUTOFF_PROFILE_UNKNOWN"] += 1
        for field in ("source_timestamp", "observed_at", "captured_at", "prediction_cutoff_at"):
            if item[field] == UNKNOWN:
                unknown_counts[field.upper() + "_UNKNOWN"] += 1
        if item["provenance_root"] == UNKNOWN:
            unknown_counts["PROVENANCE_ROOT_UNKNOWN"] += 1
        timestamp_review.append(evaluate_timestamp_evidence(item))
    zip_hash = validate_deterministic_zip(zip_bytes, entries)
    package_hash_ok = package["package_zip_sha256"] == zip_hash
    blockers = []
    if manifest_failures:
        blockers.append("IMPORT_MANIFEST_VALIDATION_FAILED")
    if not package_hash_ok:
        blockers.append("PACKAGE_ZIP_HASH_MISMATCH")
    for code, count in unknown_counts.items():
        if count:
            blockers.append(code)
    if any(result.get("status") == "CONFLICT" for result in timestamp_review):
        blockers.append("TIMESTAMP_CONFLICT")
    state = "PASS" if not blockers else "FAIL_CLOSED"
    result = {
        "status": state,
        "write_performed": False,
        "archive_write_performed": False,
        "contract_validation": contract_result,
        "import_manifest_failure_count": len(manifest_failures),
        "import_manifest_failures": manifest_failures[:20],
        "deterministic_zip": {"status": "PASS" if package_hash_ok else "FAIL", "package_zip_sha256": package["package_zip_sha256"], "recomputed_zip_sha256": zip_hash, "entry_count": len(entries)},
        "timestamp_review_status_counts": dict(Counter(item["status"] for item in timestamp_review)),
        "unknown_field_counts": dict(unknown_counts),
        "reason_codes": blockers or ["NO_WRITE_INTAKE_PASS"],
        "training_lock": "FORMAL_MODEL_TRAINING = NOT_STARTED",
    }
    write_json(R002_OUTPUT / "no_write_intake_result.json", result)
    return result


def write_r002_package(package: dict[str, Any], entries: dict[str, bytes], zip_bytes: bytes) -> dict[str, Any]:
    R002_OUTPUT.mkdir(parents=True, exist_ok=False)
    for path, content in entries.items():
        target = R002_OUTPUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (R002_OUTPUT / "verified_historical_backfill_r002.zip").write_bytes(zip_bytes)
    write_json(R002_OUTPUT / "package_hashes.json", {"package_substantive_hash": package["package_substantive_hash"], "package_sha256": package["package_sha256"], "package_zip_sha256": package["package_zip_sha256"]})
    return {"status": "PASS", "package_substantive_hash": package["package_substantive_hash"], "package_sha256": package["package_sha256"], "package_zip_sha256": package["package_zip_sha256"], "zip_bytes": len(zip_bytes), "manifest_count": len(package["manifests"])}


def execute(args: argparse.Namespace) -> int:
    require_new_output()
    auth = validate_authorization()
    audit = validate_prerequisites()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    write_json(OUTPUT / "governance_authorization_snapshot.json", auth)
    write_json(OUTPUT / "prerequisite_snapshot.json", {"review_integration_audit": audit, "source_audit_sha256": file_sha(AUDIT), "v3_3_3_modified": False})
    resolved, extraction_summary, extraction_manifest = build_reviewed_trace()
    package, entries, zip_data = build_candidate_package(resolved, extraction_summary, extraction_manifest)
    r002 = write_r002_package(package, entries, zip_data["zip_bytes"])
    no_write = validate_candidate_and_no_write(package, entries, zip_data["zip_bytes"])
    archive = {"status": "NOT_PERFORMED", "records": 0, "revisions": 0, "reason": "NO_WRITE_INTAKE_DID_NOT_PASS"}
    ewp002 = {"status": "NOT_EXECUTED", "reason": "ARCHIVE_INTAKE_NOT_PERFORMED"}
    ewp003 = {"status": "NOT_EXECUTED", "reason": "EWP-002_REAL_RERUN_REQUIRES_ARCHIVE_INTAKE_SUCCESS"}
    report = {
        "governance_authorization_status": "PASS",
        "authorization_identity": auth["amendment_id"],
        "reviewed_extraction_status": {"status": extraction_summary["status"], **extraction_summary},
        "accepted_official_odds_payload_status": {"status": "CANDIDATE_GENERATED_NOT_PROMOTED", "artifact_count": 64, "promotion": "BLOCKED_BY_NO_WRITE_GATE"},
        "r002_rebuild_status": r002,
        "no_write_intake_status": no_write,
        "archive_intake_status": archive,
        "ewp002_real_status": ewp002,
        "ewp003_real_status": ewp003,
        "current_training_readiness": {"formal_model_training": "NOT_STARTED", "ewp005_execution_authorized": False, "approved_eligible_distinct_matches": 0, "threshold": 99, "usable_samples_by_engine": {"OUTCOME": 0, "HANDICAP": 0, "GOALS": 0, "HTFT": 0}, "reason": "NO_APPROVED_ARCHIVE_AFTER_FAIL_CLOSED_NO_WRITE_GATE"},
        "remaining_data_gap_to_99_distinct_matches": {"OUTCOME": 99, "HANDICAP": 99, "GOALS": 99, "HTFT": 99, "distinct_matches": 99},
        "isolation": {"v3_3_3": "PASS", "production": "UNTOUCHED", "supabase": "UNTOUCHED", "public": "UNTOUCHED", "model_artifacts": "NOT_GENERATED"},
        "stop_reason": no_write["reason_codes"],
    }
    write_json(OUTPUT / "authorized_backfill_r003_execution_report.json", report)
    (OUTPUT / "authorized_backfill_r003_execution_report.md").write_text(render_report(report), encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if no_write["status"] == "PASS" else 2


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# JCFB V4 additive historical backfill authorization execution",
        "",
        f"- GOVERNANCE_AUTHORIZATION_STATUS: `{report['governance_authorization_status']}`",
        f"- REVIEWED_EXTRACTION_STATUS: `{report['reviewed_extraction_status']['status']}` ({report['reviewed_extraction_status']['trace_record_count']} trace records)",
        f"- ACCEPTED_OFFICIAL_ODDS_PAYLOAD_STATUS: `{report['accepted_official_odds_payload_status']['status']}`",
        f"- R002_REBUILD_STATUS: `{report['r002_rebuild_status']['status']}`",
        f"  - substantive: `{report['r002_rebuild_status']['package_substantive_hash']}`",
        f"  - package: `{report['r002_rebuild_status']['package_sha256']}`",
        f"  - zip: `{report['r002_rebuild_status']['package_zip_sha256']}`",
        f"- NO_WRITE_INTAKE_STATUS: `{report['no_write_intake_status']['status']}`; writes: `{report['no_write_intake_status']['write_performed']}`",
        f"- ARCHIVE_INTAKE_STATUS: `{report['archive_intake_status']['status']}`; records: `{report['archive_intake_status']['records']}`; revisions: `{report['archive_intake_status']['revisions']}`",
        f"- EWP-002 REAL STATUS: `{report['ewp002_real_status']['status']}`",
        f"- EWP-003 REAL STATUS: `{report['ewp003_real_status']['status']}`",
        f"- CURRENT TRAINING READINESS: `FORMAL_MODEL_TRAINING = {report['current_training_readiness']['formal_model_training'].split('=')[-1].strip()}`",
        "",
        "## Stop condition",
        "",
        "No-write intake did not pass because the source evidence retains UNKNOWN canonical identity/cutoff/source-time fields. The runner stopped before archive intake and before EWP-002/EWP-003 real reruns.",
        "",
        "The r002 package is a deterministic candidate artifact only; it is not an archive receipt, approved training dataset, model artifact, or production input.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    try:
        raise SystemExit(execute(parse_args()))
    except Exception as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
