"""Validate the B15-EWP-003 contract remediation without executing a split."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
DOCS = ROOT / "docs"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ROLES = ("OUTCOME", "HANDICAP", "GOALS", "HTFT")


def canonical_hash(document: dict[str, Any]) -> str:
    value = {key: item for key, item in document.items() if key != "canonical_hash"}
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_config(name: str) -> dict[str, Any]:
    value = json.loads((CONFIG / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{name}: root must be an object")
    return value


def changed_paths() -> list[str]:
    tracked = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "HEAD"], check=True, capture_output=True, text=True).stdout.splitlines()
    untracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"], check=True, capture_output=True, text=True).stdout.splitlines()
    return sorted({path.replace("\\", "/") for path in tracked + untracked if path.strip()})


def validate() -> list[str]:
    failures: list[str] = []
    contract = load_config("v4_batch15_ewp003_temporal_split_contract.json")
    report = load_config("v4_batch15_ewp003_readiness_report.json")
    governance = load_config("v4_prediction_training_governance.json")
    readiness = load_config("v4_prediction_training_readiness_review.json")
    registry = load_config("v4_batch15_execution_work_package_registry.json")

    for name, value in (("contract", contract), ("report", report), ("governance", governance), ("readiness", readiness), ("registry", registry)):
        if not HASH_RE.fullmatch(str(value.get("canonical_hash", ""))):
            failures.append(f"{name}: invalid canonical_hash")
        elif value["canonical_hash"] != canonical_hash(value):
            failures.append(f"{name}: canonical_hash mismatch")

    if contract.get("work_package_id") != "B15-EWP-003" or contract.get("work_package_revision") != "r002":
        failures.append("contract: EWP-003 identity/revision is not r002")
    if contract.get("execution_authorized") is not False or contract.get("status") != "CONTRACT_FROZEN_IMPLEMENTATION_NOT_AUTHORIZED":
        failures.append("contract: implementation authorization leaked")
    strategy = contract.get("strategy_contract", {})
    if strategy.get("default_strategy") is not None or strategy.get("strategy_selection") != "EXPLICIT_CONFIG_REQUIRED":
        failures.append("strategy: implicit/default strategy is present")
    if strategy.get("random_split") != "FORBIDDEN":
        failures.append("strategy: random split is not forbidden")
    explicit = strategy.get("explicit_temporal_boundaries", {})
    for field in ("train_end", "validation_start", "validation_end", "holdout_start", "holdout_end"):
        if field not in explicit.get("required_config_fields", []):
            failures.append(f"explicit boundary: missing required field {field}")
    if explicit.get("identical_timestamp_tie_break") != ["match_id_group_key", "sample_id_within_group"]:
        failures.append("explicit boundary: deterministic tie-break is not frozen")
    walk = strategy.get("walk_forward_rolling_origin", {})
    required_walk = {"mode", "initial_train_period", "origin_step", "validation_horizon", "holdout_horizon", "minimum_folds", "incomplete_final_fold_policy", "same_match_grouping_policy", "fold_level_minimum_readiness_policy"}
    if not required_walk.issubset(set(walk.get("required_config_fields", []))):
        failures.append("walk-forward: required parameter schema is incomplete")
    if walk.get("missing_parameter_action") != "SPLIT_CONFIG_NOT_DECLARED" or walk.get("numeric_defaults") != "NONE":
        failures.append("walk-forward: missing parameters do not fail closed")
    if strategy.get("grouping_contract", {}).get("assignment_unit") != "match_id":
        failures.append("grouping: assignment unit is not match_id")
    if strategy.get("leakage_contract", {}).get("holdout_in_fitting") != "FORBIDDEN":
        failures.append("leakage: holdout fitting use is not forbidden")

    league = contract.get("league_scope_contract", {})
    if league.get("canonical_source") != "DATASET_MANIFEST" or league.get("scope_not_declared_result") != "LEAGUE_SCOPE_NOT_DECLARED":
        failures.append("league scope: canonical source or missing-scope result is invalid")
    if league.get("sample_content_inference") != "FORBIDDEN":
        failures.append("league scope: sample-content inference is not forbidden")
    readiness_rule = contract.get("minimum_sample_readiness_contract", {})
    if readiness_rule.get("class_minimums") != {"train": 5, "validation": 3, "holdout": 3}:
        failures.append("readiness: frozen class minimums changed")
    if readiness_rule.get("required_feature_availability", {}).get("pass_value") != 1.0:
        failures.append("readiness: required feature availability is not 100 percent")
    if readiness_rule.get("stability_status_values") != ["PASS", "UNSTABLE", "UNKNOWN"]:
        failures.append("readiness: stability states are incomplete")
    if readiness_rule.get("numeric_stability_threshold") != "NOT_APPROVED; IF_REQUIRED_REMAINS_AN_INDEPENDENT_BLOCKER":
        failures.append("readiness: an unapproved numeric stability threshold was introduced")

    binding = contract.get("dataset_revision_binding", {})
    if binding.get("required_identity") != ["dataset_id", "dataset_revision", "dataset_manifest_hash", "dataset_substantive_hash"]:
        failures.append("revision binding: exact identity set is incomplete")
    if binding.get("superseded_revision_consumption") != "REJECT" or binding.get("historical_replay", "").startswith("EXPLICIT_REPLAY_MODE_REQUIRED") is False:
        failures.append("revision binding: superseded/replay boundary is incomplete")

    if report.get("split_status") != "NOT_PERFORMABLE" or report.get("readiness_state") != "BLOCKED":
        failures.append("zero-data report: status is not blocked/not-performable")
    if report.get("reason_codes") != ["TRAINING_DATA_INSUFFICIENT"]:
        failures.append("zero-data report: reason code is not TRAINING_DATA_INSUFFICIENT")
    counts = report.get("sample_counts", {})
    if counts.get("candidate_samples") != 0 or counts.get("usable_samples") != 0 or counts.get("reason") != "ZERO_ARCHIVED_CANDIDATES":
        failures.append("zero-data report: current real dataset counts/reason are not bound")
    for role in ROLES:
        if report.get("per_engine_counts", {}).get(role, {}).get("usable") != 0:
            failures.append(f"zero-data report: {role} usable count is not zero")
    if report.get("split_artifact_generated") is not False or report.get("formal_split_artifact_ref") is not None:
        failures.append("zero-data report: formal split artifact was claimed")
    if report.get("model_accuracy") is not None:
        failures.append("zero-data report: model accuracy must be absent")

    archive_root = Path("F:/Projects/jcfb-v4/approved_data/historical_source_archive")
    training_root = Path("F:/Projects/jcfb-v4/approved_data/training_datasets")
    if archive_root.drive.upper() != "F:" or not archive_root.is_dir():
        failures.append("F-drive audit: approved historical archive root is missing")
    if training_root.drive.upper() != "F:" or not training_root.is_dir():
        failures.append("F-drive audit: approved training dataset root is missing")
    manifest_path = training_root / "manifests" / "dataset-13c4b050dc50e2de3ec8a961a9c9b029-r001.json"
    if not manifest_path.is_file():
        failures.append("F-drive audit: active EWP-002 dataset manifest is missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("candidate_sample_count") != 0 or manifest.get("zero_archive_reason") != "ZERO_ARCHIVED_CANDIDATES":
            failures.append("F-drive audit: active manifest is not the verified zero-candidate dataset")
    split_files = [path for path in training_root.rglob("*") if path.is_file() and any(token in path.name.casefold() for token in ("temporal-split", "split-artifact", "split_artifact"))]
    if split_files:
        failures.append("F-drive audit: formal split files exist: " + ", ".join(str(path) for path in split_files))

    if readiness.get("historical_as_of_dataset", {}).get("dataset_artifact") != "dataset-13c4b050dc50e2de3ec8a961a9c9b029":
        failures.append("governance cross-reference: current dataset artifact is stale")
    if readiness.get("historical_as_of_dataset", {}).get("candidate_sample_count") != 0 or readiness.get("historical_as_of_dataset", {}).get("usable_training_sample_count") != 0:
        failures.append("governance cross-reference: current zero counts are not explicit")
    if readiness.get("pipeline_readiness", {}).get("formal_model_fit_allowed") is not False:
        failures.append("governance cross-reference: formal model fit was allowed")
    package = next((item for item in registry.get("work_packages", []) if item.get("work_package_id") == "B15-EWP-003"), {})
    if package.get("revision") != "r002" or package.get("execution_authorized") is not False:
        failures.append("registry: EWP-003 r002 remains unauthorized")

    forbidden = [path for path in changed_paths() if re.search(r"(?i)(^|/)(?:tools/|database/migrations/|migrations/|v333/|v3\.3\.3)", path)]
    if forbidden:
        failures.append("forbidden changed paths: " + ", ".join(forbidden))
    if any(path.startswith("src/prediction_training/") for path in changed_paths()):
        failures.append("runtime boundary: prediction_training runtime was modified")
    if any("split" in path.casefold() and path.startswith("approved_data/") for path in changed_paths()):
        failures.append("artifact boundary: formal split output was added")
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 EWP-003 CONTRACT VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 EWP-003 CONTRACT VALIDATION: PASS")
    print("Runtime implementation: not authorized")
    print("Current real dataset split readiness: BLOCKED / TRAINING_DATA_INSUFFICIENT")
    print("Formal model fit readiness: BLOCKED")
