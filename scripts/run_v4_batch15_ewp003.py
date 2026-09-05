"""Execute the authorized B15-EWP-003 split/readiness runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_training import Ewp003Runtime, Ewp003RuntimeError


REPORT_PATH = ROOT / "config/prediction_training/v4_batch15_ewp003_readiness_report.json"
SPLIT_ROOT = ROOT / "approved_data/training_datasets/splits"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    try:
        result = Ewp003Runtime(ROOT).run_detailed()
    except Ewp003RuntimeError as exc:
        print(f"B15-EWP-003 RUNTIME: FAIL [{exc.code}] {exc.message}")
        return 1
    write_json(REPORT_PATH, result["report"])
    if result["split_artifact"] is not None:
        artifact = result["split_artifact"]
        write_json(SPLIT_ROOT / f"{artifact['dataset_id']}-{artifact['dataset_revision']}-{artifact['split_artifact_id']}.json", artifact)
    report = result["report"]
    print("B15-EWP-003 RUNTIME: PASS")
    print(f"split_status={report['split_status']}")
    print(f"readiness_state={report['readiness_state']}")
    print(f"reason_codes={','.join(report['reason_codes'])}")
    print(f"split_artifact_generated={report['split_artifact_generated']}")
    print(f"deterministic_report_hash={report['deterministic_report_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
