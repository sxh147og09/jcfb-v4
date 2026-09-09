"""Refresh self-hashes for the checked-in v2 training profile and gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_training_contract import sha256_json


def refresh(path: Path, *, child_field: str | None = None, child_hash_field: str | None = None, root_hash_field: str) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    if child_field and child_hash_field:
        for child in document[child_field].values():
            for feature in child.get("optional_features", []):
                if feature.get("feature_id") == "tactical_context_overlay":
                    feature["type"] = "categorical_or_relational"
            child[child_hash_field] = sha256_json({key: value for key, value in child.items() if key != child_hash_field})
    document[root_hash_field] = sha256_json({key: value for key, value in document.items() if key != root_hash_field})
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    config = ROOT / "config" / "prediction_training"
    refresh(config / "v4_model_training_minimum_feature_set_v2.json", child_field="engine_profiles", child_hash_field="profile_hash", root_hash_field="profile_hash")
    refresh(config / "v4_training_eligibility_gate_v2.json", root_hash_field="gate_hash")
    refresh(config / "v4_training_eligibility_profile_registry.json", root_hash_field="canonical_hash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
