from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.prediction_training import (
    DatasetBinding,
    Ewp003RuntimeError,
    TemporalSplitBuilder,
    TrainingReadinessEvaluator,
)


HASH = "sha256:" + "a" * 64
CONTRACT = {
    "$id": "b15-ewp003-temporal-split-and-readiness-contract@1.0.0",
    "canonical_hash": HASH,
    "strategy_contract": {
        "allowed_strategies": ["EXPLICIT_TEMPORAL_BOUNDARIES", "WALK_FORWARD_ROLLING_ORIGIN"],
        "explicit_temporal_boundaries": {"required_config_fields": ["strategy", "train_end", "validation_start", "validation_end", "holdout_start", "holdout_end", "ordering_field", "identical_timestamp_tie_break", "minimum_chronological_separation", "partition_inclusivity_exclusivity"], "partition_inclusivity_exclusivity": {"train": "(-infinity, train_end]", "validation": "[validation_start, validation_end]", "holdout": "[holdout_start, holdout_end]"}},
        "walk_forward_rolling_origin": {"required_config_fields": ["mode", "initial_train_period", "origin_step", "validation_horizon", "holdout_horizon", "minimum_folds", "incomplete_final_fold_policy", "same_match_grouping_policy", "fold_level_minimum_readiness_policy"]},
        "grouping_contract": {"assignment_unit": "match_id", "grouping_root": "match_id"},
    },
    "minimum_sample_readiness_contract": {"class_minimums": {"train": 5, "validation": 3, "holdout": 3}},
}
BINDING = DatasetBinding("dataset-test", "r001", HASH, HASH, "dataset@1.1.0#r001")


def sample(index: int, when: datetime, *, match_id: str | None = None, role: str = "OUTCOME", label: str = "H", state: str = "ELIGIBLE") -> dict:
    stamp = when.isoformat()
    return {
        "training_sample_id": f"sample-{index}",
        "match_id": match_id or f"match-{index}",
        "cutoff_profile": "T_MINUS_60M",
        "prediction_cutoff_at": stamp,
        "kickoff_at": (when + timedelta(hours=1)).isoformat(),
        "source_availability_at": (when - timedelta(hours=1)).isoformat(),
        "engine_role": role,
        "eligibility_state": state,
        "target_class": label,
        "league_id": "league-1",
        "feature_availability": {"f1": True},
        "sample_hash": HASH,
        "revision": 1,
    }


def scope() -> dict:
    return {"scope_type": "SINGLE_LEAGUE", "league_id": "league-1", "scope_declaration_hash": HASH}


class Ewp003RuntimeTests(unittest.TestCase):
    def test_explicit_boundaries_are_chronological_and_grouped(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        records = [sample(1, base + timedelta(days=1), match_id="m1"), sample(2, base + timedelta(days=1), match_id="m1"), sample(3, base + timedelta(days=3), match_id="m2"), sample(4, base + timedelta(days=5), match_id="m3")]
        config = {"strategy": "EXPLICIT_TEMPORAL_BOUNDARIES", "train_end": (base + timedelta(days=2)).isoformat(), "validation_start": (base + timedelta(days=3)).isoformat(), "validation_end": (base + timedelta(days=4)).isoformat(), "holdout_start": (base + timedelta(days=5)).isoformat(), "holdout_end": (base + timedelta(days=6)).isoformat(), "ordering_field": "prediction_cutoff_at", "identical_timestamp_tie_break": ["match_id_group_key", "sample_id_within_group"], "minimum_chronological_separation": "PT1S", "partition_inclusivity_exclusivity": {"train": "(-infinity, train_end]", "validation": "[validation_start, validation_end]", "holdout": "[holdout_start, holdout_end]"}}
        result = TemporalSplitBuilder(CONTRACT, config).build(records, BINDING, scope())
        self.assertEqual(["sample-1", "sample-2"], [item["training_sample_id"] for item in result.partitions["train"]])
        self.assertEqual(["sample-3"], [item["training_sample_id"] for item in result.partitions["validation"]])
        self.assertEqual(["sample-4"], [item["training_sample_id"] for item in result.partitions["holdout"]])
        self.assertEqual(result.split_substantive_hash, TemporalSplitBuilder(CONTRACT, config).build(list(reversed(records)), BINDING, scope()).split_substantive_hash)

    def test_overlap_cross_match_random_and_missing_config_fail_closed(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        records = [sample(1, base + timedelta(days=1), match_id="m1"), sample(2, base + timedelta(days=5), match_id="m1")]
        config = {"strategy": "EXPLICIT_TEMPORAL_BOUNDARIES", "train_end": (base + timedelta(days=2)).isoformat(), "validation_start": (base + timedelta(days=3)).isoformat(), "validation_end": (base + timedelta(days=4)).isoformat(), "holdout_start": (base + timedelta(days=5)).isoformat(), "holdout_end": (base + timedelta(days=6)).isoformat(), "ordering_field": "prediction_cutoff_at", "identical_timestamp_tie_break": ["match_id_group_key", "sample_id_within_group"], "minimum_chronological_separation": "PT1S", "partition_inclusivity_exclusivity": {"train": "(-infinity, train_end]", "validation": "[validation_start, validation_end]", "holdout": "[holdout_start, holdout_end]"}}
        with self.assertRaisesRegex(Ewp003RuntimeError, "SAME_MATCH_CROSSES_BOUNDARY"):
            TemporalSplitBuilder(CONTRACT, config).build(records, BINDING, scope())
        with self.assertRaisesRegex(Ewp003RuntimeError, "RANDOM_SPLIT_FORBIDDEN"):
            TemporalSplitBuilder(CONTRACT, {"strategy": "RANDOM_SPLIT"}).build(records, BINDING, scope())
        with self.assertRaisesRegex(Ewp003RuntimeError, "SPLIT_CONFIG_NOT_DECLARED"):
            TemporalSplitBuilder(CONTRACT, {}).build(records, BINDING, scope())

    def test_walk_forward_expanding_and_sliding_are_explicit(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        records = [sample(index, base + timedelta(days=index), match_id=f"m{index}") for index in range(1, 13)]
        common = {"initial_train_period": "P3D", "origin_step": "P2D", "validation_horizon": "P1D", "holdout_horizon": "P1D", "minimum_folds": 2, "incomplete_final_fold_policy": "DROP_INCOMPLETE_FINAL_FOLD", "same_match_grouping_policy": "GROUP_BY_MATCH_ID_BEFORE_FOLD_ASSIGNMENT", "fold_level_minimum_readiness_policy": "EACH_REQUIRED_FOLD_MUST_PASS_DECLARED_READINESS_RULE", "first_origin_at": (base + timedelta(days=4)).isoformat()}
        expanding = TemporalSplitBuilder(CONTRACT, {"strategy": "WALK_FORWARD_ROLLING_ORIGIN", "mode": "expanding", **common}).build(records, BINDING, scope())
        sliding = TemporalSplitBuilder(CONTRACT, {"strategy": "WALK_FORWARD_ROLLING_ORIGIN", "mode": "sliding", "sliding_window_width": "P3D", **common}).build(records, BINDING, scope())
        self.assertGreaterEqual(len(expanding.folds), 2)
        self.assertGreaterEqual(len(sliding.folds), 2)
        self.assertLess(len(sliding.folds[1]["partitions"]["train"]), len(expanding.folds[1]["partitions"]["train"]))

    def test_league_revision_future_and_zero_data_are_fail_closed(self):
        with self.assertRaisesRegex(Ewp003RuntimeError, "LEAGUE_SCOPE_NOT_DECLARED"):
            from src.prediction_training.ewp003_runtime import validate_league_scope
            validate_league_scope(None, [])
        bad = sample(1, datetime(2026, 1, 1, tzinfo=timezone.utc))
        bad["dataset_revision"] = "r002"
        with self.assertRaisesRegex(Ewp003RuntimeError, "MIXED_DATASET_REVISION"):
            TemporalSplitBuilder(CONTRACT, {"strategy": "EXPLICIT_TEMPORAL_BOUNDARIES"})._validate_sample_for_runtime(bad, BINDING)
        evaluator = TrainingReadinessEvaluator(CONTRACT, ["f1"])
        report = evaluator.evaluate([], BINDING, None, league_scope=None, zero_data_reason="TRAINING_DATA_INSUFFICIENT")
        self.assertEqual("NOT_PERFORMABLE", report["split_status"])
        self.assertEqual("BLOCKED", report["readiness_state"])
        self.assertEqual(["TRAINING_DATA_INSUFFICIENT"], report["reason_codes"])
        self.assertFalse(report["split_artifact_generated"])
        self.assertIsNone(report["model_accuracy"])


if __name__ == "__main__":
    unittest.main()
