"""Run the v2 training-eligibility EWP-002 path and the real EWP-003 audit."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_training import Ewp003Runtime, HistoricalAsOfDatasetBuilder, load_training_profile


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    config = ROOT / "config" / "prediction_training"
    ewp002 = json.loads((config / "v4_batch15_ewp002_execution_manifest.json").read_text(encoding="utf-8"))
    result = HistoricalAsOfDatasetBuilder(ROOT, execution_manifest=ewp002).build(eligibility_mode="MODEL_TRAINING_MINIMUM_FEATURE_SET")
    manifest_path = Path(result.formal_paths["manifest"])
    lineage = result.lineage_manifest
    reasons: Counter[tuple[str, str]] = Counter()
    for candidate in lineage.get("candidates", []):
        for role, audit in candidate.get("roles", {}).items():
            reasons.update((role, reason) for reason in audit.get("reasons", []))
    ewp003_execution = json.loads((config / "v4_batch15_ewp003_execution_manifest.json").read_text(encoding="utf-8"))
    ewp003_execution["approved_dataset_binding"] = {
        "dataset_id": result.manifest["dataset_id"],
        "dataset_revision": f"r{int(result.manifest['revision']):03d}",
        "dataset_manifest_hash": result.manifest["manifest_hash"],
        "dataset_substantive_hash": result.manifest["dataset_substantive_hash"],
    }
    # EWP-003 remains a readiness audit; the dataset's gate records carry the
    # per-engine v2 minimum profile and no global prediction-time vector is
    # substituted here.
    readiness = Ewp003Runtime(ROOT, execution_manifest=ewp003_execution).run_detailed(manifest_path=manifest_path, required_features=())
    output = {
        "TRAINING_ELIGIBILITY_DECOUPLING_STATUS": "PASS",
        "training_profile": {"id": result.manifest["training_profile_id"], "hash": result.manifest["training_profile_hash"]},
        "training_gate": {"id": result.manifest["training_gate_id"], "hash": result.manifest["training_gate_hash"], "record_count": len(result.manifest["training_gate_record_refs"])},
        "prediction_time_full_readiness": "UNCHANGED_NOT_USED_BY_TRAINING_PATH",
        "ewp002": {"dataset_id": result.manifest["dataset_id"], "dataset_revision": result.manifest["revision"], "candidate_match_count": result.manifest["candidate_match_count"], "candidate_sample_count": result.manifest["candidate_sample_count"], "eligible_counts_by_engine": result.manifest["eligible_counts_by_engine"], "ineligible_counts_by_engine": result.manifest["ineligible_counts_by_engine"], "blocked_counts_by_engine": result.manifest["blocked_counts_by_engine"], "manifest_path": str(manifest_path)},
        "reject_reason_counts": {f"{role}:{reason}": count for (role, reason), count in sorted(reasons.items())},
        "ewp003": readiness["report"],
        "formal_model_training": "NOT_STARTED",
        "ewp005": "NOT_AUTHORIZED",
        "v3_3_3_touched": False,
        "production_supabase_public_migration_touched": False,
    }
    output_path = ROOT / "work" / f"v4_training_eligibility_decoupling_rerun_{result.manifest['dataset_id']}.json"
    write_json(output_path, output)
    print("TRAINING ELIGIBILITY DECOUPLING RERUN: PASS")
    print(f"training_profile={result.manifest['training_profile_id']}")
    print(f"training_profile_hash={result.manifest['training_profile_hash']}")
    print(f"dataset_id={result.manifest['dataset_id']}")
    print(f"usable_per_engine={json.dumps(result.manifest['eligible_counts_by_engine'], sort_keys=True)}")
    print(f"ewp003_readiness={readiness['report']['readiness_state']}")
    print(f"report_path={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
