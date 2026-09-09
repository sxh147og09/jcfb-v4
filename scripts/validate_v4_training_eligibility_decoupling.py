"""Validate the active v2 training eligibility profile/gate boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_training import load_ewp004_contract, load_training_gate, load_training_profile, validate_training_gate, validate_training_profile
from src.prediction_training_contract import sha256_json


def main() -> int:
    config = ROOT / "config" / "prediction_training"
    profile = load_training_profile(config)
    gate = load_training_gate(config)
    registry = json.loads((config / "v4_training_eligibility_profile_registry.json").read_text(encoding="utf-8"))
    registry_hash = registry.pop("canonical_hash", None)
    if registry_hash != sha256_json(registry):
        raise SystemExit("profile registry hash invalid")
    old = load_ewp004_contract(config / "v4_batch15_ewp004_training_infrastructure_contract.json")
    if old["$id"] != "b15-ewp004-training-infrastructure-contract@1.0.0":
        raise SystemExit("historical EWP-004 revision missing")
    failures = validate_training_profile(profile) + validate_training_gate(gate)
    if any(item["domain"] == "TACTICAL" for role in profile["engine_profiles"].values() for item in role["required_features"]):
        failures.append("tactical minimum is not optional")
    if gate["prediction_gate_semantics"] != "UNCHANGED_AND_NOT_REUSED_FOR_TRAINING":
        failures.append("prediction gate separation invalid")
    if failures:
        raise SystemExit(";".join(failures))
    print("V4 TRAINING ELIGIBILITY DECOUPLING: PASS")
    print(f"active_profile={profile['profile_version']}")
    print(f"active_profile_hash={profile['profile_hash']}")
    print(f"active_gate={gate['gate_version']}")
    print("prediction_time_full_readiness=UNCHANGED")
    print("historical_ewp004_revision=READ_ONLY_BACKWARD_COMPATIBLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
