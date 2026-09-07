"""Validate the Wednesday fast-track infrastructure without side effects."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_runtime import SyntheticPipeline
from src.prediction_runtime.model_loader import ModelArtifactLoader
from tools.ai_visual_review.provider import OpenAICompatibleVisionProvider, ProviderNeutralBatchVisionAdapter


def main() -> int:
    failures: list[str] = []
    synthetic = SyntheticPipeline().run()
    if synthetic.get("status") != "PASS" or not synthetic.get("synthetic_test_only") or synthetic.get("formal_model_fit_executed"):
        failures.append("synthetic pipeline boundary invalid")
    registry = ModelArtifactLoader(ROOT).resolve("OUTCOME")
    if registry.get("status") != "BLOCKED" or registry.get("reason_code") != "MODEL_ARTIFACT_NOT_APPROVED":
        failures.append("empty model registry did not fail closed")
    provider = OpenAICompatibleVisionProvider()
    if provider.available:
        # A credential appearing in the environment is not used by this
        # validator; it only confirms that the adapter can be constructed.
        ProviderNeutralBatchVisionAdapter(provider)
    request = json.loads((ROOT / "docs/ADDITIONAL_LIBRARY_BACKFILL_REQUEST.json").read_text(encoding="utf-8"))
    if request.get("status") != "COMPLETE" or request.get("quantity_targets", {}).get("distinct_matches") != 99:
        failures.append("additional Library request is incomplete")
    if failures:
        print("V4 FAST-TRACK SYSTEM VALIDATION: FAIL")
        print("\n".join(failures))
        return 1
    print("V4 FAST-TRACK SYSTEM VALIDATION: PASS")
    print("SYSTEM_INFRASTRUCTURE_READINESS=PASS")
    print("FORMAL_MODEL_TRAINING=NOT_STARTED")
    print("MODEL_ARTIFACTS_GENERATED=false")
    print("ARCHIVE_WRITTEN=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
