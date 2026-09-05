"""Validate B15-EWP-002 entry remediation without building a dataset."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
HASHED_ARTIFACTS = (
    "v4_prediction_training_dataset_contract.json",
    "v4_prediction_training_dataset_schema.json",
    "v4_historical_artifact_replay_lineage_policy.json",
    "v4_training_dataset_storage_policy.json",
    "v4_training_dataset_hash_boundary.json",
    "v4_batch15_ewp001_r003_read_interface_amendment.json",
)
HASH_RE = "sha256:"


def canonical_hash(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "canonical_hash"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return HASH_RE + hashlib.sha256(encoded).hexdigest()


def load(name: str) -> dict:
    path = CONFIG / name
    return json.loads(path.read_text(encoding="utf-8"))


def changed_paths() -> list[str]:
    tracked = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "HEAD"], check=True, capture_output=True, text=True).stdout.splitlines()
    untracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"], check=True, capture_output=True, text=True).stdout.splitlines()
    return sorted({path.replace("\\", "/") for path in tracked + untracked if path.strip()})


def validate() -> list[str]:
    failures: list[str] = []
    dataset = load("v4_prediction_training_dataset_contract.json")
    schema = load("v4_prediction_training_dataset_schema.json")
    replay = load("v4_historical_artifact_replay_lineage_policy.json")
    storage = load("v4_training_dataset_storage_policy.json")
    hash_boundary = load("v4_training_dataset_hash_boundary.json")
    amendment = load("v4_batch15_ewp001_r003_read_interface_amendment.json")
    registry = load("v4_batch15_execution_work_package_registry.json")

    for name in HASHED_ARTIFACTS:
        value = load(name)
        expected = canonical_hash(value)
        if value.get("canonical_hash") != expected:
            failures.append(f"{name}: canonical_hash mismatch")

    if dataset.get("$id") != "prediction-training-dataset@1.1.0" or dataset.get("base_contract") != "prediction-training-dataset@1.0.0":
        failures.append("dataset contract: additive version/base identity is invalid")
    required = set(dataset.get("required_fields", []))
    required_expected = {
        "training_sample_id", "match_id", "cutoff_profile", "prediction_cutoff_at", "kickoff_at",
        "feature_bundle_ref", "feature_bundle_hash", "feature_snapshot_hash", "statistical_ref", "statistical_hash",
        "football_ref", "football_hash", "market_ref", "market_hash", "tactical_ref", "tactical_hash",
        "gate_record_ref", "gate_record_hash", "source_refs", "evidence_refs", "provenance_refs", "engine_role",
        "eligibility_state", "exclusion_or_block_reason", "label_ref", "label_hash", "builder_version", "builder_hash",
        "dataset_version", "input_hash", "sample_hash", "provenance_hash", "revision", "supersedes",
    }
    if required != required_expected:
        failures.append("dataset contract: required field set is incomplete or ambiguous")
    if dataset.get("stable_identity") != ["match_id", "cutoff_profile", "engine_role"]:
        failures.append("dataset contract: stable identity is not frozen")
    handicap = dataset.get("handicap_binding", {})
    if handicap.get("source_class") != "OFFICIAL_RQSPF_ONLY" or handicap.get("sign_convention") != "home_minus_away":
        failures.append("dataset contract: official RQSPF binding is incomplete")
    if "external_asian_handicap" not in handicap.get("forbidden_substitutes", []):
        failures.append("dataset contract: external AH substitute is not forbidden")
    aliases = set(dataset.get("field_alias_policy", {}).get("ambiguous_aliases_rejected", []))
    if "sample_id" not in aliases or "target_role" not in aliases:
        failures.append("dataset contract: alias ambiguity rejection is incomplete")

    if replay.get("selection_order") != ["STORED_ACCEPTED_ARTIFACT", "DETERMINISTIC_HISTORICAL_REPLAY"]:
        failures.append("replay policy: stored artifact preference missing")
    required_replay = set(replay.get("deterministic_historical_replay", {}).get("required_proof", []))
    if len(required_replay) != 9 or replay.get("fallback_policy") != "NO_FALLBACK_TO_LATEST_GENERATOR_CONFIG_OR_MAPPING":
        failures.append("replay policy: deterministic lineage proof/fallback boundary incomplete")

    if storage.get("approved_root") != "F:\\Projects\\jcfb-v4\\approved_data\\training_datasets\\":
        failures.append("storage policy: approved F-drive root mismatch")
    if storage.get("staging_must_be_separate") is not True or storage.get("append_only", {}).get("overwrite") != "FORBIDDEN":
        failures.append("storage policy: staging/append-only boundary incomplete")
    stable_inputs = set(hash_boundary.get("stable_inputs", []))
    required_stable = {"archive_snapshot_identity", "archive_snapshot_hash", "cutoff_profile", "builder_version", "builder_hash", "dataset_schema_version", "dataset_schema_hash", "replay_policy_version", "replay_policy_hash", "sample_membership", "feature_refs_and_hashes", "eligibility", "label_refs_and_hashes"}
    if not required_stable.issubset(stable_inputs):
        failures.append("hash boundary: stable inputs incomplete")
    if not {"execution_timestamp", "logging_metadata", "host_specific_absolute_path"}.issubset(set(hash_boundary.get("volatile_exclusions", []))):
        failures.append("hash boundary: volatile exclusions incomplete")

    if amendment.get("supersedes_work_package_revision") != "r002" or amendment.get("amendment_revision") != "r003":
        failures.append("EWP-001 amendment: revision lineage is invalid")
    if amendment.get("reopens_completed_work_package") is not False or amendment.get("execution_authorized") is not False or amendment.get("amendment_authorized") is not True:
        failures.append("EWP-001 amendment: completed package was reopened or authorization boundary changed")
    packages = registry.get("work_packages", [])
    if not packages or packages[0].get("revision") != "r002" or packages[0].get("status") != "COMPLETE" or packages[0].get("execution_authorized") is not True:
        failures.append("EWP-001 original COMPLETE r002 boundary was changed")
    if any(package.get("execution_authorized") is not False for package in packages[1:]):
        failures.append("downstream EWP authorization leaked")

    archive_root = Path("F:/Projects/jcfb-v4/approved_data/historical_source_archive")
    training_root = Path("F:/Projects/jcfb-v4/approved_data/training_datasets")
    if archive_root.drive.upper() != "F:" or not archive_root.is_dir():
        failures.append("F-drive audit: archive root missing")
    if not training_root.is_dir():
        failures.append("F-drive audit: training dataset policy root missing")
    formal_files = [path for path in training_root.rglob("*") if path.is_file() and path.name != ".gitkeep"] if training_root.exists() else []
    if formal_files:
        failures.append("zero-data audit: formal training dataset artifacts exist: " + ", ".join(str(path) for path in formal_files))

    reader_source = (ROOT / "src/historical_source_archive/read_interface.py").read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "mkdir", "unlink", "rmtree"):
        if forbidden in reader_source:
            failures.append(f"read interface: forbidden write operation present: {forbidden}")
    for method in ("enumerate_approved_archive_records", "query_by_match_id", "query_by_cutoff_profile", "query_by_artifact_type", "resolve_supersedes_chain", "deterministic_candidate_snapshot"):
        if f"def {method}" not in reader_source:
            failures.append(f"read interface: missing {method}")

    forbidden_paths = [path for path in changed_paths() if "v3.3.3" in path.casefold() or path.casefold().startswith("v333/") or path.startswith("database/migrations/")]
    if forbidden_paths:
        failures.append("forbidden changed paths: " + ", ".join(forbidden_paths))
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 ENTRY REMEDIATION VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 ENTRY REMEDIATION VALIDATION: PASS")
    print("Decision: B15-EWP-002 READY FOR IMPLEMENTATION")
    print("Authorization: execution_authorized=false")
    print("Data boundary: archive_match_count=0 / usable_training_sample_count=NOT_COMPUTED")
