"""Validate BATCH-15 execution work-package governance artifacts.

This is a no-write governance validator. It never imports archive data, opens a
database connection, or executes a training/model path.
"""

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


def canonical_hash(document: dict[str, Any]) -> str:
    value = {key: item for key, item in document.items() if key != "canonical_hash"}
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load(name: str) -> dict[str, Any]:
    path = CONFIG / name
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{name}: root must be an object")
    return value


def git_changed_paths() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def validate() -> list[str]:
    failures: list[str] = []
    schema = load("execution_work_package_schema.json")
    registry = load("v4_batch15_execution_work_package_registry.json")
    archive = load("historical_source_archive_contract.json")

    for name, value in (("execution_work_package_schema.json", schema), ("v4_batch15_execution_work_package_registry.json", registry), ("historical_source_archive_contract.json", archive)):
        if not HASH_RE.fullmatch(str(value.get("canonical_hash", ""))):
            failures.append(f"{name}: invalid canonical_hash")
        elif value["canonical_hash"] != canonical_hash(value):
            failures.append(f"{name}: canonical_hash mismatch")

    if schema.get("$id") != "execution-work-package@1.0.0":
        failures.append("schema: wrong contract identity")
    if schema.get("canonicalization", {}).get("profile") != "v4-canonical-json@1.0":
        failures.append("schema: canonical profile missing")

    if registry.get("$id") != "v4-batch-prerequisite-workpackages@1.0.0":
        failures.append("registry: wrong identity")
    if registry.get("contract_version") != "execution-work-package@1.0.0":
        failures.append("registry: wrong contract version")
    if registry.get("registry_status") != "ACTIVE_GOVERNANCE_WITH_EWP002_EXECUTION_COMPLETE":
        failures.append("registry: must record EWP-002 completion")
    if registry.get("registry_owner_decision") != "APPROVED_EWP002_HISTORICAL_AS_OF_DATASET_BUILDER_ONLY":
        failures.append("registry: EWP-002 owner approval missing")
    boundary = registry.get("task_namespace_boundary", {})
    if boundary.get("reserved_namespace") != "V4-001..V4-100":
        failures.append("namespace: authoritative V4 task namespace is not frozen")
    if boundary.get("task_ids_created") != [] or boundary.get("existing_task_ids_modified") != []:
        failures.append("namespace: task IDs were created or modified")
    if boundary.get("existing_task_dag_modified") is not False:
        failures.append("namespace: existing task DAG must remain unchanged")

    entity = registry.get("entity_rules", {})
    required_false = (
        "is_v4_task",
        "may_replace_task_registry_task",
        "may_authorize_formal_model_fit",
        "may_authorize_v4_076",
        "may_authorize_downstream_engines",
        "may_authorize_production_shadow_public",
        "may_authorize_supabase_or_migrations",
        "may_modify_v3_3_3",
    )
    for key in required_false:
        if entity.get(key) is not False:
            failures.append(f"entity boundary: {key} must be false")

    packages = registry.get("work_packages")
    if not isinstance(packages, list) or len(packages) != 5:
        failures.append("registry: exactly five BATCH-15 work packages are required")
        packages = []
    expected_ids = [f"B15-EWP-{index:03d}" for index in range(1, 6)]
    expected_deps = [[], [expected_ids[0]], [expected_ids[1]], [expected_ids[2]], [expected_ids[3]]]
    seen: set[str] = set()
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            failures.append(f"work package {index + 1}: not an object")
            continue
        identity = package.get("work_package_id")
        if identity != expected_ids[index]:
            failures.append(f"work package {index + 1}: nondeterministic or wrong identity")
        if identity in seen or re.fullmatch(r"V4-\d{3}", str(identity)):
            failures.append(f"work package {index + 1}: task namespace collision")
        seen.add(str(identity))
        if package.get("entity_type") != "EXECUTION_WORK_PACKAGE":
            failures.append(f"work package {index + 1}: wrong entity type")
        if package.get("parent_batch") != "BATCH-15":
            failures.append(f"work package {index + 1}: missing BATCH-15 binding")
        if not package.get("parent_task_scope"):
            failures.append(f"work package {index + 1}: missing parent task scope")
        expected_authorized = index in (0, 1)
        if package.get("execution_authorized") is not expected_authorized:
            failures.append(f"work package {index + 1}: authorization boundary mismatch")
        if package.get("dependencies") != expected_deps[index]:
            failures.append(f"work package {index + 1}: dependency chain mismatch")
        for field in ("definition_of_done", "evidence_manifest", "commit_lineage", "output_artifacts", "artifact_hash"):
            if field not in package:
                failures.append(f"work package {index + 1}: missing {field}")
    edges = registry.get("dependency_edges", [])
    if [edge.get("from") for edge in edges] != expected_ids[:-1] or [edge.get("to") for edge in edges] != expected_ids[1:]:
        failures.append("registry: dependency edges are not the required acyclic chain")

    if archive.get("$id") != "historical-source-archive@1.0.0":
        failures.append("archive: wrong identity")
    if set(archive.get("acquisition_modes", [])) != {"PROSPECTIVE_CAPTURE", "VERIFIED_HISTORICAL_BACKFILL"}:
        failures.append("archive: acquisition modes are incomplete")
    required_fields = set(archive.get("record_required_fields", []))
    for field in {"source", "source_reference", "source_timestamp", "captured_at", "ingested_at", "original_payload_or_file_hash", "match_identity", "revision_identity", "provenance", "availability_at"}:
        if field not in required_fields:
            failures.append(f"archive: required provenance field missing: {field}")
    if archive.get("unverifiable_time_action") != "REJECT_AS_NOT_ELIGIBLE_FOR_AS_OF_TRAINING":
        failures.append("archive: unverifiable time must be rejected")
    if archive.get("prospective_capture", {}).get("append_only") is not True:
        failures.append("archive: prospective capture must be append-only")
    if archive.get("raw_fact_reingestion", {}).get("direct_v3_runtime_reference") != "FORBIDDEN":
        failures.append("archive: direct V3 runtime reference must be forbidden")

    active_execution = registry.get("active_execution", {})
    if active_execution.get("work_package_id") != "B15-EWP-002":
        failures.append("active execution: only B15-EWP-002 may be active")
    if set(active_execution.get("forbidden_downstream_work_packages", [])) != {"B15-EWP-003", "B15-EWP-004", "B15-EWP-005"}:
        failures.append("active execution: downstream authorization boundary is incomplete")
    if not (DOCS / "JCFB_V4_BATCH_15_B15_EWP_001_ACCEPTANCE_EVIDENCE.json").is_file():
        failures.append("missing EWP-001 acceptance evidence")
    if not (CONFIG / "v4_batch15_ewp001_execution_manifest.json").is_file():
        failures.append("missing EWP-001 execution manifest")
    if not (CONFIG / "v4_batch15_ewp002_execution_manifest.json").is_file():
        failures.append("missing EWP-002 execution manifest")

    required_docs = (
        "JCFB_V4_BATCH_15_MODEL_TRAINING_ARCHITECTURE_AMENDMENT_APPROVAL_DECISION.md",
        "JCFB_V4_BATCH_15_EXECUTION_WORK_PACKAGE_CONTRACT.md",
        "JCFB_V4_HISTORICAL_SOURCE_ARCHIVE_CONTRACT.md",
        "JCFB_V4_HISTORICAL_SOURCE_ACQUISITION_MODE_POLICY.md",
        "JCFB_V4_HISTORICAL_BACKFILL_ELIGIBILITY_POLICY.md",
        "JCFB_V4_PROSPECTIVE_TRAINING_ARCHIVE_POLICY.md",
        "JCFB_V4_RAW_FACT_REINGESTION_DECISION.md",
        "JCFB_V4_BATCH_15_MODEL_TRAINING_DEPENDENCY_AMENDMENT.md",
        "JCFB_V4_F_DRIVE_HISTORICAL_ARCHIVE_STORAGE_POLICY.md",
        "JCFB_V4_BATCH_15_HISTORICAL_SOURCE_AUDIT.md",
    )
    for name in required_docs:
        path = DOCS / name
        if not path.is_file():
            failures.append(f"missing governance document: docs/{name}")
    decision_text = (DOCS / required_docs[0]).read_text(encoding="utf-8")
    for term in ("MODEL_TRAINING_TASK_REGISTRY_AMENDMENT: RESOLVED", "MODEL_TRAINING_EXECUTION_IDENTITY RESOLVED", "PREDICTION_TRAINING_READINESS_BLOCKED", "UNKNOWN", "NOT_FOUND", "F:\\Projects\\jcfb-v4\\approved_data\\historical_source_archive"):
        if term not in decision_text:
            failures.append(f"approval decision: missing {term}")
    audit_text = (DOCS / "JCFB_V4_BATCH_15_HISTORICAL_SOURCE_AUDIT.md").read_text(encoding="utf-8")
    for term in ("VERIFIED_HISTORICAL_BACKFILL: NOT FOUND", "PROSPECTIVE_CAPTURE: GOVERNANCE APPROVED", "HISTORICAL_BACKFILL_INSUFFICIENT", "UNKNOWN", "NOT_AVAILABLE", "tests", "fixtures"):
        if term not in audit_text:
            failures.append(f"source audit: missing {term}")

    forbidden_paths = [path for path in git_changed_paths() if path.startswith(("tools/", "database/migrations/")) or re.search(r"(?i)(^|/)(?:V333|v333)|v3\.3\.3", path)]
    if forbidden_paths:
        failures.append("forbidden changed paths: " + ", ".join(forbidden_paths))
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 TRAINING AMENDMENT VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 TRAINING AMENDMENT VALIDATION: PASS")
    print("Execution entity: EXECUTION_WORK_PACKAGE / execution-work-package@1.0.0")
    print("Registry: EWP-001 and EWP-002 complete / downstream EWP-003..005 unauthorized")
    print("Historical archive: runtime complete / prospective capture approved / verified backfill NOT_FOUND")
    print("Safety boundary: EWP-002 dataset build only; no split, fitting, migration, Supabase, or V3.3.3 change")
