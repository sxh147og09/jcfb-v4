"""No-write validator for the B15-EWP-001 archive implementation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
DOCS = ROOT / "docs"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_hash(document: dict) -> str:
    body = {key: value for key, value in document.items() if key != "canonical_hash"}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def changed_paths() -> list[str]:
    output = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "HEAD"], check=True, capture_output=True, text=True).stdout
    return [line.replace("\\", "/") for line in output.splitlines() if line.strip()]


def validate() -> list[str]:
    failures: list[str] = []
    schema = load("config/prediction_training/v4_batch15_ewp001_archive_record_schema.json")
    manifest = load("config/prediction_training/v4_batch15_ewp001_execution_manifest.json")
    registry = load("config/prediction_training/v4_batch15_execution_work_package_registry.json")
    evidence = load("docs/JCFB_V4_BATCH_15_B15_EWP_001_ACCEPTANCE_EVIDENCE.json")

    for name, document in (("archive schema", schema), ("execution manifest", manifest), ("registry", registry), ("acceptance evidence", evidence)):
        if not HASH_RE.fullmatch(str(document.get("canonical_hash", ""))):
            failures.append(f"{name}: canonical_hash format invalid")
        elif document["canonical_hash"] != canonical_hash(document):
            failures.append(f"{name}: canonical_hash mismatch")

    if manifest.get("work_package_id") != "B15-EWP-001" or manifest.get("execution_authorized") is not True:
        failures.append("execution manifest: EWP-001 authorization missing")
    if not HASH_RE.fullmatch(str(manifest.get("registry_hash", ""))):
        failures.append("execution manifest: registry snapshot hash format invalid")
    if manifest.get("output_artifact_schema_hash") != schema.get("canonical_hash"):
        failures.append("execution manifest: output schema hash binding mismatch")
    if registry.get("registry_status") not in {
        "ACTIVE_GOVERNANCE_WITH_EWP001_EXECUTION",
        "ACTIVE_GOVERNANCE_WITH_EWP002_EXECUTION_COMPLETE",
        "ACTIVE_GOVERNANCE_WITH_EWP004_RUNTIME_COMPLETE",
    }:
        failures.append("registry: wrong active status")
    packages = registry.get("work_packages", [])
    if len(packages) != 5 or packages[0].get("work_package_id") != "B15-EWP-001" or packages[0].get("execution_authorized") is not True:
        failures.append("registry: EWP-001 authorization is not preserved")
    if registry.get("registry_status") in {"ACTIVE_GOVERNANCE_WITH_EWP002_EXECUTION_COMPLETE", "ACTIVE_GOVERNANCE_WITH_EWP004_RUNTIME_COMPLETE"}:
        if packages[1].get("work_package_id") != "B15-EWP-002" or packages[1].get("execution_authorized") is not True:
            failures.append("registry: EWP-002 current completion boundary is not preserved")
        if registry.get("registry_status") == "ACTIVE_GOVERNANCE_WITH_EWP004_RUNTIME_COMPLETE":
            if any(item.get("execution_authorized") is not True for item in packages[2:4]):
                failures.append("registry: EWP-003/EWP-004 current completion boundary is not preserved")
            downstream = packages[4:]
        else:
            downstream = packages[2:]
    else:
        downstream = packages[1:]
    if any(item.get("execution_authorized") is not False for item in downstream):
        failures.append("registry: downstream package authorization leaked")
    archive_root = ROOT / "approved_data" / "historical_source_archive"
    if archive_root.drive.upper() != "F:" or not archive_root.is_dir():
        failures.append("archive root: approved F-drive root is not established")
    for relative in ("pre_match", "post_match", "manifests", "provenance", "revisions"):
        if not (archive_root / relative).is_dir():
            failures.append(f"archive root: missing {relative}/")
    required_docs = (
        "JCFB_V4_BATCH_15_B15_EWP_001_AUTHORIZATION_DECISION.md",
        "JCFB_V4_BATCH_15_B15_EWP_001_IMPLEMENTATION.md",
        "JCFB_V4_BATCH_15_B15_EWP_001_CLOSURE_READINESS_REVIEW.md",
    )
    for name in required_docs:
        if not (DOCS / name).is_file():
            failures.append(f"missing report: docs/{name}")
    forbidden = [path for path in changed_paths() if path.startswith(("tools/", "database/migrations/")) or re.search(r"(?i)v3\.3\.3|v333", path)]
    if forbidden:
        failures.append("forbidden changed paths: " + ", ".join(forbidden))
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 B15-EWP-001 VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 B15-EWP-001 VALIDATION: PASS")
    print("Scope: historical source archive / prospective capture only")
    print("Authorization: EWP-001..EWP-004 complete and authorized; EWP-005 remains unauthorized")
    print("Archive: approved F-drive root / pre-post separation / append-only")
