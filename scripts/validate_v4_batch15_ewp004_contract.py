"""Validate B15-EWP-004 runtime authorization and contract boundaries.

The validator is read-only.  It does not import historical data, fit a model,
create an artifact, write a registry, or change any readiness state.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
sys.path.insert(0, str(ROOT))

from src.prediction_training.ewp004_contract import (  # noqa: E402
    ENGINE_ROLES,
    MODEL_FAMILIES,
    canonical_hash,
    validate_contract,
)


def load(name: str) -> dict:
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
    contract = load("v4_batch15_ewp004_training_infrastructure_contract.json")
    failures.extend(validate_contract(contract))
    manifest = load("v4_batch15_ewp004_execution_manifest.json")
    if manifest.get("canonical_hash") != canonical_hash(manifest):
        failures.append("execution manifest canonical hash mismatch")
    if manifest.get("work_package_id") != "B15-EWP-004" or manifest.get("execution_authorized") is not True or manifest.get("implementation_executed") is not True:
        failures.append("execution manifest is not authorized and implementation-complete")
    if manifest.get("formal_model_fit_authorized") is not False or manifest.get("contract_hash") != contract.get("canonical_hash"):
        failures.append("execution manifest formal-fit or contract binding leaked")
    if manifest.get("scope_hash") != canonical_hash(manifest.get("scope", {}), exclude=()):
        failures.append("execution manifest scope hash mismatch")
    if manifest.get("dod_hash") != canonical_hash({"definition_of_done": manifest.get("definition_of_done", [])}, exclude=()):
        failures.append("execution manifest DoD hash mismatch")
    for field in ("contract_hash", "implementation_hash", "scope_hash", "candidate_model_family_registry", "engine_training_profiles", "hyperparameter_configs", "deterministic_runtime_profile", "fitting_implementation_contract", "readiness_input_binding_contract", "parameter_artifact_contract", "evaluation_metric_contract", "model_artifact_packaging_contract", "dependency_boundary", "evidence_path", "closure_path"):
        if field not in manifest:
            failures.append(f"execution manifest missing {field}")
    evidence_path = ROOT / "docs" / "JCFB_V4_BATCH_15_B15_EWP_004_ACCEPTANCE_EVIDENCE.json"
    if not evidence_path.is_file():
        failures.append("acceptance evidence is missing")
    else:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("canonical_hash") != canonical_hash(evidence):
            failures.append("acceptance evidence canonical hash mismatch")
        if evidence.get("status") != "COMPLETE" or evidence.get("formal_model_fit_authorized") is not False:
            failures.append("acceptance evidence status or formal-fit boundary is invalid")
    if not (ROOT / "docs" / "JCFB_V4_BATCH_15_B15_EWP_004_CLOSURE_READINESS_REVIEW.md").is_file():
        failures.append("closure readiness review is missing")
    if not (ROOT / "docs" / "JCFB_V4_BATCH_15_B15_EWP_005_SCOPE_ENTRY_REVIEW.md").is_file():
        failures.append("EWP-005 scope/entry review is missing")

    registry = load("v4_batch15_execution_work_package_registry.json")
    ewp004 = next((item for item in registry.get("work_packages", []) if item.get("work_package_id") == "B15-EWP-004"), {})
    ewp005 = next((item for item in registry.get("work_packages", []) if item.get("work_package_id") == "B15-EWP-005"), {})
    if ewp004.get("execution_authorized") is not True or ewp004.get("status") != "COMPLETE":
        failures.append("registry: EWP-004 is not runtime-complete and authorized")
    if ewp005.get("execution_authorized") is not False or ewp005.get("status") != "SEPARATE_APPROVAL_REQUIRED":
        failures.append("registry: EWP-005 authorization/status boundary changed")
    if "B15-EWP-003" not in ewp004.get("dependencies", []):
        failures.append("registry: EWP-004 dependency on EWP-003 is missing")

    readiness = load("v4_batch15_ewp003_readiness_report.json")
    if readiness.get("readiness_state") != "BLOCKED" or readiness.get("split_status") != "NOT_PERFORMABLE":
        failures.append("current real-data readiness is no longer blocked/not-performable")
    if readiness.get("reason_codes") != ["TRAINING_DATA_INSUFFICIENT"]:
        failures.append("current real-data readiness reason is not TRAINING_DATA_INSUFFICIENT")
    if readiness.get("sample_counts", {}).get("usable_samples") != 0:
        failures.append("current real-data readiness has a non-zero usable count")

    model_registry = load("v4_prediction_model_registry.json")
    if model_registry.get("artifacts") != [] or model_registry.get("status") != "NO_APPROVED_ARTIFACTS_PRESENT":
        failures.append("model registry is not empty/no-approved-artifacts")

    if contract.get("authorization_boundary", {}).get("implementation_readiness") not in {"B15-EWP-004 READY FOR IMPLEMENTATION", "B15-EWP-004 RUNTIME IMPLEMENTATION COMPLETE"}:
        failures.append("implementation readiness decision is not complete")
    if contract.get("authorization_boundary", {}).get("current_real_dataset_fitting_readiness") != "BLOCKED / TRAINING_DATA_INSUFFICIENT":
        failures.append("current real-data fitting readiness is not the required blocked state")
    if contract.get("authorization_boundary", {}).get("formal_model_fit_authorization") != "NOT_AUTHORIZED":
        failures.append("formal model fit authorization is not NOT_AUTHORIZED")
    if set(contract.get("blocker_resolution", {})) != {
        "CANDIDATE_MODEL_FAMILY_REGISTRY_NOT_EXECUTABLE",
        "FOUR_ENGINE_TRAINING_PROFILES_INCOMPLETE",
        "TRAINING_CONFIG_NOT_DECLARED",
        "DETERMINISTIC_FITTING_BOUNDARY_NOT_FROZEN",
        "FITTING_IMPLEMENTATION_IDENTITY_NOT_FROZEN",
        "TRAINING_READINESS_REPORT_BINDING_NOT_DECLARED",
        "PARAMETER_ARTIFACT_CONTRACT_NOT_FROZEN",
        "EVALUATION_METRIC_SEMANTICS_NOT_FROZEN",
    } or any(value != "RESOLVED" for value in contract["blocker_resolution"].values()):
        failures.append("the exact eight EWP-004 blockers are not all marked RESOLVED")

    if not (ROOT / "src/prediction_training/ewp004_runtime.py").exists():
        failures.append("EWP-004 runtime implementation is missing")
    if (ROOT / "scripts/run_v4_batch15_ewp004.py").exists():
        failures.append("formal fitting execution script must not exist")
    forbidden = [path for path in changed_paths() if re.search(r"(?i)(^|/)(?:tools/|database/migrations/|migrations/|v333/|v3\.3\.3)", path)]
    if forbidden:
        failures.append("forbidden changed paths: " + ", ".join(forbidden))
    if any(path.startswith("approved_data/") and ("model" in path.casefold() or "parameter" in path.casefold()) for path in changed_paths()):
        failures.append("model or parameter artifacts were added under approved_data")
    return failures


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("V4 BATCH-15 EWP-004 CONTRACT VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("V4 BATCH-15 EWP-004 CONTRACT VALIDATION: PASS")
    print("Training infrastructure contract: AUTHORIZED RUNTIME IMPLEMENTATION COMPLETE")
    print("EWP-004 execution authorization: true")
    print("Current real dataset fitting readiness: BLOCKED / TRAINING_DATA_INSUFFICIENT")
    print("Formal model fit authorization: NOT_AUTHORIZED")
    print("Model/parameter artifacts: NONE_GENERATED")
