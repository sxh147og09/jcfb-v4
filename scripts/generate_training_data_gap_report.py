"""Generate a fail-closed, quantitative training-data expansion request."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/prediction_training/v4_batch15_ewp003_temporal_split_contract.json"
DATASET = ROOT / "approved_data/training_datasets/manifests/dataset-13c4b050dc50e2de3ec8a961a9c9b029-r001.json"
JSON_OUT = ROOT / "docs/V4_TRAINING_DATA_EXPANSION_REQUIRED.json"
MD_OUT = ROOT / "docs/V4_TRAINING_DATA_EXPANSION_REQUIRED.md"

ENGINE_CLASSES = {
    "OUTCOME": ["H", "D", "A"],
    "HANDICAP": ["H", "D", "A"],
    "GOALS": ["0", "1", "2", "3", "4", "5", "6", "7+"],
    "HTFT": ["H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"],
}


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    minimums = contract["minimum_sample_readiness_contract"]["class_minimums"]
    partition_order = ("train", "validation", "holdout")
    per_engine = {}
    for role, classes in ENGINE_CLASSES.items():
        class_requirements = {
            label: {partition: int(minimums[partition]) for partition in partition_order}
            for label in classes
        }
        per_partition = {partition: len(classes) * int(minimums[partition]) for partition in partition_order}
        per_engine[role] = {
            "classes": classes,
            "class_support_required": class_requirements,
            "minimum_additional_eligible_samples_lower_bound": sum(per_partition.values()),
            "minimum_additional_matches_lower_bound": sum(per_partition.values()),
            "partition_match_lower_bounds": per_partition,
            "status": "BLOCKED_NO_APPROVED_ELIGIBLE_SAMPLES",
        }
    contract_body = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract_hash = "sha256:" + hashlib.sha256(json.dumps(contract_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    report = {
        "report_identity": "jcfb-v4-training-data-expansion-required@1.0.0",
        "status": "TRAINING_DATA_EXPANSION_REQUIRED",
        "contract_identity": "b15-ewp003-temporal-split-and-readiness-contract@1.0.0",
        "contract_hash": contract_hash,
        "active_dataset": {
            "dataset_id": dataset.get("dataset_id"),
            "dataset_revision": dataset.get("revision"),
            "candidate_sample_count": dataset.get("candidate_sample_count", 0),
            "usable_training_sample_count": dataset.get("usable_training_sample_count", 0),
            "reason": dataset.get("zero_archive_reason", "ZERO_ARCHIVED_CANDIDATES"),
        },
        "current_approved_archive": {
            "eligible_archive_record_count": 0,
            "source_archive_files_present": False,
            "r002_package_accepted": False,
            "reason": "AI_VISUAL_REVIEW_BLOCKED_AND_NO_ACCEPTED_ARCHIVE_RECORDS",
        },
        "readiness": {
            "roles_that_can_proceed_now": [],
            "roles_blocked_now": list(ENGINE_CLASSES),
            "minimums_are_unchanged": True,
            "random_split": "FORBIDDEN",
            "same_match_grouping": "REQUIRED",
            "league_scope": "MUST_BE_EXPLICITLY_DECLARED",
        },
        "per_engine": per_engine,
        "joint_acquisition_lower_bound": {
            "distinct_matches": 99,
            "basis": "HTFT has 9 classes and dominates: 9 * (5 train + 3 validation + 3 holdout)",
            "partition_targets": {"train": 45, "validation": 27, "holdout": 27},
            "caveat": "This is a contractual lower bound assuming every acquired match supplies one valid sample per role and exact class quotas. Actual need may be higher after league, feature, cutoff, and source-quality gates.",
        },
        "additional_library_backfill_request": {
            "request_identity": "ADDITIONAL_LIBRARY_BACKFILL_REQUEST",
            "status": "READY_TO_PACKAGE_FROM_LIBRARY",
            "distinct_match_count_minimum": 99,
            "date_buckets": [
                {"bucket": "TRAIN", "minimum_distinct_matches": 45, "date_rule": "earliest chronological bucket; exact calendar dates must come from source metadata"},
                {"bucket": "VALIDATION", "minimum_distinct_matches": 27, "date_rule": "strictly after TRAIN with declared positive separation"},
                {"bucket": "HOLDOUT", "minimum_distinct_matches": 27, "date_rule": "strictly after VALIDATION with declared positive separation"}
            ],
            "class_quotas": {
                "OUTCOME": {"H": {"train": 5, "validation": 3, "holdout": 3}, "D": {"train": 5, "validation": 3, "holdout": 3}, "A": {"train": 5, "validation": 3, "holdout": 3}},
                "HANDICAP": "same three-class quota as OUTCOME",
                "GOALS": {label: {"train": 5, "validation": 3, "holdout": 3} for label in ENGINE_CLASSES["GOALS"]},
                "HTFT": {label: {"train": 5, "validation": 3, "holdout": 3} for label in ENGINE_CLASSES["HTFT"]},
            },
            "required_fields": [
                "data_date", "official_match_no", "canonical_match_identity", "league_id", "kickoff_at", "prediction_cutoff_at", "source_availability_at",
                "official_pre_match_screenshot_or_source_bytes", "SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HTFT", "final_result", "halftime_result",
                "raw_image_sha256", "source_reference", "artifact_hash", "capture_or_publication_time_if_available"
            ],
            "prohibited_inputs": ["V3.3.3 predictions", "V3.3.3 models", "V3.3.3 parameters", "post_match_features", "guessed_or_inferred_odds"],
        },
    }
    report["canonical_hash"] = "sha256:" + hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# V4 TRAINING_DATA_EXPANSION_REQUIRED",
        "",
        "当前没有任何已接受的 eligible historical archive record，4 个 engine role 均不能进入 formal fitting。现行 class support 门槛保持不变：train=5、validation=3、holdout=3。",
        "",
        "## 量化下限",
        "",
        "| Engine | Classes | Train | Validation | Holdout | 最低新增 matches 下限 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for role, values in per_engine.items():
        lines.append(f"| {role} | {len(values['classes'])} | {values['partition_match_lower_bounds']['train']} | {values['partition_match_lower_bounds']['validation']} | {values['partition_match_lower_bounds']['holdout']} | {values['minimum_additional_matches_lower_bound']} |")
    lines += [
        "",
        "联合采集的最低下限是 99 个 distinct matches：TRAIN 45、VALIDATION 27、HOLDOUT 27；这是共享同一批 match 为各 engine 提供各自标签的理想下限，实际数量可能因 league、feature、cutoff 和来源质量门槛增加。",
        "",
        "当前可推进 engine：无。当前所有 engine：`TRAINING_DATA_EXPANSION_REQUIRED`。",
        "",
        "机器可读请求见 `V4_TRAINING_DATA_EXPANSION_REQUIRED.json`，包含日期桶规则、每类配额、必需字段和禁止输入。",
    ]
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("TRAINING_DATA_EXPANSION_REQUIRED")
    print("roles_can_proceed_now=[]")
    print("joint_distinct_match_lower_bound=99")
    print("partition_targets=train:45,validation:27,holdout:27")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
