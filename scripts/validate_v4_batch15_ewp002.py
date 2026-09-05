"""Validate the completed B15-EWP-002 implementation and formal build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.prediction_training_contract import sha256_json, substantive_hash, validate_training_sample


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
TRAINING = ROOT / "approved_data" / "training_datasets"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(document: dict) -> str:
    body = dict(document)
    body.pop("canonical_hash", None)
    return sha256_json(body)


def validate() -> list[str]:
    failures: list[str] = []
    registry = load(CONFIG / "v4_batch15_execution_work_package_registry.json")
    execution = load(CONFIG / "v4_batch15_ewp002_execution_manifest.json")
    for name, document in (("registry", registry), ("execution", execution)):
        if not document.get("canonical_hash", "").startswith("sha256:"):
            failures.append(f"{name}: canonical hash missing")
        elif document["canonical_hash"] != canonical_hash(document):
            failures.append(f"{name}: canonical hash mismatch")
    if execution.get("work_package_id") != "B15-EWP-002" or execution.get("execution_authorized") is not True:
        failures.append("execution: EWP-002 authorization is not active")
    if execution.get("dependency_boundary", {}).get("downstream_execution_authorized") is not False:
        failures.append("execution: downstream authorization leaked")
    packages = registry.get("work_packages", [])
    if len(packages) != 5 or packages[1].get("status") != "COMPLETE" or packages[1].get("execution_authorized") is not True:
        failures.append("registry: EWP-002 is not COMPLETE and authorized")
    if any(item.get("execution_authorized") is not False for item in packages[2:]):
        failures.append("registry: EWP-003..005 authorization leaked")

    manifests = sorted((TRAINING / "manifests").glob("dataset-*-r001.json"))
    if len(manifests) != 1:
        failures.append("formal build: expected exactly one deterministic dataset manifest")
        return failures
    manifest = load(manifests[0])
    body = dict(manifest)
    expected_manifest_hash = body.pop("manifest_hash", None)
    if expected_manifest_hash != sha256_json(body):
        failures.append("formal build: manifest hash mismatch")
    if manifest.get("dataset_substantive_hash") != substantive_hash(manifest):
        failures.append("formal build: substantive hash boundary mismatch")
    if manifest.get("archived_match_count") != 0 or manifest.get("candidate_match_count") != 0 or manifest.get("candidate_sample_count") != 0:
        failures.append("formal build: zero archive counts are not preserved")
    if manifest.get("zero_archive_reason") != "ZERO_ARCHIVED_CANDIDATES":
        failures.append("formal build: zero archive reason is missing")
    artifact_path = TRAINING / manifest["dataset_artifact_ref"]
    artifact = load(artifact_path)
    artifact_body = dict(artifact)
    artifact_hash = artifact_body.pop("artifact_hash", None)
    if artifact_hash != sha256_json(artifact_body):
        failures.append("formal build: dataset artifact hash mismatch")
    if artifact_hash != manifest.get("dataset_artifact_hash"):
        failures.append("formal build: dataset artifact binding mismatch")
    lineage = load(TRAINING / manifest["lineage_manifest_ref"])
    lineage_body = dict(lineage)
    lineage_hash = lineage_body.pop("lineage_manifest_hash", None)
    if lineage_hash != sha256_json(lineage_body):
        failures.append("formal build: lineage manifest hash mismatch")
    evidence_path = TRAINING / "evidence" / f"{manifest['dataset_id']}-acceptance.json"
    evidence = load(evidence_path)
    evidence_body = dict(evidence)
    evidence_hash = evidence_body.pop("evidence_hash", None)
    if evidence_hash != sha256_json(evidence_body):
        failures.append("formal build: acceptance evidence hash mismatch")
    if evidence.get("usable_training_sample_count") != 0 or evidence.get("usable_training_sample_reason") != "ZERO_ARCHIVED_CANDIDATES":
        failures.append("formal build: usable count/reason mismatch")
    for sample in manifest.get("sample_records", []):
        sample_body = dict(sample)
        sample_hash = sample_body.pop("sample_hash", None)
        if sample_hash != sha256_json(sample_body) or validate_training_sample(sample):
            failures.append(f"formal build: invalid sample {sample.get('training_sample_id')}")
    reader_source = (ROOT / "src/historical_source_archive" / "read_interface.py").read_text(encoding="utf-8")
    if any(token in reader_source for token in ("write_text", "write_bytes", "mkdir", "unlink", "rmtree")):
        failures.append("archive reader: write operation detected")
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 B15-EWP-002 VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 B15-EWP-002 VALIDATION: PASS")
    print("Status: B15-EWP-002 STATUS: COMPLETE")
    print("Boundary: EWP-003..005 remain execution_authorized=false")
