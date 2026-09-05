"""Run the authorized B15-EWP-002 builder against the approved archive."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "prediction_training"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_training import HistoricalAsOfDatasetBuilder


def main() -> int:
    execution = json.loads((CONFIG / "v4_batch15_ewp002_execution_manifest.json").read_text(encoding="utf-8"))
    result = HistoricalAsOfDatasetBuilder(ROOT, execution_manifest=execution).build()
    print("B15-EWP-002 FORMAL DATASET BUILD: PASS")
    print(f"dataset_id={result.manifest['dataset_id']}")
    print(f"dataset_substantive_hash={result.manifest['dataset_substantive_hash']}")
    print(f"dataset_manifest_hash={result.manifest['manifest_hash']}")
    print(f"archived_match_count={result.manifest['archived_match_count']}")
    print(f"candidate_match_count={result.manifest['candidate_match_count']}")
    print(f"candidate_sample_count={result.manifest['candidate_sample_count']}")
    print(f"usable_training_sample_count={result.evidence['usable_training_sample_count']}")
    print(f"usable_training_sample_reason={result.evidence['usable_training_sample_reason']}")
    print(f"formal_paths={json.dumps(result.formal_paths, ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
