"""Deterministic, in-memory end-to-end contract fixture.

This is intentionally not a model fit, model artifact, Frozen Input, or
Production prediction.  It exercises the envelope/payload contracts with an
explicit ``SYNTHETIC_TEST_ONLY`` status so the full chain can be tested before
real data and approved artifacts exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import build_engine_output, sha256_json, validate_engine_output


class SyntheticPipeline:
    def run(self, fixture_id: str = "synthetic-v4-e2e-r001") -> dict[str, Any]:
        if not fixture_id or not isinstance(fixture_id, str):
            raise ValueError("fixture_id must be a non-empty string")
        fixture_hash = sha256_json({"fixture_id": fixture_id})
        input_hash = sha256_json({"fixture_id": fixture_id, "features": "SYNTHETIC_ONLY"})
        # This is a test identity, not a formal Frozen Input record.
        synthetic_input_hash = sha256_json({"synthetic_fixture": fixture_id})
        now = datetime.now(timezone.utc).isoformat()
        payloads = {
            "OUTCOME": {"outcome_probability": {"H": 0.5, "D": 0.3, "A": 0.2}, "normalization_error": 0.0, "feature_refs": {"synthetic": fixture_hash}},
            "HANDICAP": {"official_handicap": "SYNTHETIC", "handicap_outcome_probability": {"H": 0.4, "D": 0.3, "A": 0.3}, "goal_difference_distribution": {"support": [-2, -1, 0, 1, 2], "probabilities": [0.1, 0.2, 0.3, 0.25, 0.15]}, "sign_convention": "home_minus_away", "feature_refs": {"synthetic": fixture_hash}},
            "GOALS": {"goal_distribution": {"0": 0.08, "1": 0.17, "2": 0.23, "3": 0.2, "4": 0.14, "5": 0.08, "6": 0.05, "7+": 0.05}, "goal_bands": {"low": ["0", "1"], "mid": ["2", "3"], "high": ["4", "5", "6", "7+"]}, "normalization_tail_policy": "EXPLICIT_7_PLUS_BUCKET", "feature_refs": {"synthetic": fixture_hash}},
            "HTFT": {"half_full_probability": {label: 1 / 9 for label in ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A")}, "feature_refs": {"synthetic": fixture_hash}},
        }
        outputs = {}
        for role, payload in payloads.items():
            output = build_engine_output(
                role="EXPERIMENT", engine_role=role, model_name="synthetic-model-fixture", model_version="synthetic-model@0.0.0",
                engine_version=f"{role.lower()}-engine@synthetic.1.0.0", revision="synthetic-r001", implementation_hash=sha256_json({"pipeline": "synthetic-v4-e2e@1.0.0"}),
                config_version=f"{role.lower()}-config@synthetic.1.0.0", config_hash=sha256_json({"role": role, "fixture": fixture_id}), input_hash=input_hash,
                frozen_input_id=f"synthetic-input-{fixture_hash[7:23]}", frozen_input_hash=synthetic_input_hash, run_at=now, run_completed_at=now,
                runtime_ms=0, payload=payload, synthetic_test_only=True,
            )
            validate_engine_output(output)
            outputs[role] = output
        return {"status": "PASS", "synthetic_test_only": True, "formal_model_fit_executed": False, "formal_artifacts_generated": False, "outputs": outputs}


__all__ = ["SyntheticPipeline"]
