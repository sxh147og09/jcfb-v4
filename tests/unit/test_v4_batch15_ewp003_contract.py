from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


class V4Batch15Ewp003ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.config = cls.root / "config" / "prediction_training"
        cls.contract = json.loads((cls.config / "v4_batch15_ewp003_temporal_split_contract.json").read_text(encoding="utf-8"))
        cls.execution = json.loads((cls.config / "v4_batch15_ewp003_execution_manifest.json").read_text(encoding="utf-8"))
        cls.report = json.loads((cls.config / "v4_batch15_ewp003_readiness_report.json").read_text(encoding="utf-8"))
        cls.governance = json.loads((cls.config / "v4_prediction_training_governance.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((cls.config / "v4_batch15_execution_work_package_registry.json").read_text(encoding="utf-8"))

    @staticmethod
    def canonical_hash(document):
        value = {key: item for key, item in document.items() if key != "canonical_hash"}
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def test_frozen_contract_is_bound_to_authorized_runtime_manifest(self):
        self.assertEqual("B15-EWP-003", self.contract["work_package_id"])
        self.assertEqual("r002", self.contract["work_package_revision"])
        self.assertEqual("CONTRACT_FROZEN_IMPLEMENTATION_NOT_AUTHORIZED", self.contract["status"])
        self.assertFalse(self.contract["execution_authorized"])
        package = next(item for item in self.registry["work_packages"] if item["work_package_id"] == "B15-EWP-003")
        self.assertEqual("r002", package["revision"])
        self.assertTrue(package["execution_authorized"])
        self.assertEqual("COMPLETE", package["status"])
        self.assertEqual("COMPLETE", package["runtime_implementation_readiness"])
        self.assertTrue(self.execution["execution_authorized"])
        self.assertFalse(self.execution["downstream_execution_authorized"])
        self.assertEqual(self.contract["canonical_hash"], self.execution["contract_hash"])

    def test_explicit_boundaries_and_partition_semantics_are_complete(self):
        strategy = self.contract["strategy_contract"]
        explicit = strategy["explicit_temporal_boundaries"]
        self.assertEqual("EXPLICIT_CONFIG_REQUIRED", strategy["strategy_selection"])
        self.assertIsNone(strategy["default_strategy"])
        self.assertEqual("FORBIDDEN", strategy["random_split"])
        self.assertTrue({"train_end", "validation_start", "validation_end", "holdout_start", "holdout_end"}.issubset(explicit["required_config_fields"]))
        self.assertEqual("(-infinity, train_end]", explicit["partition_inclusivity_exclusivity"]["train"])
        self.assertEqual(["match_id_group_key", "sample_id_within_group"], explicit["identical_timestamp_tie_break"])
        self.assertIn("max(train.prediction_cutoff_at) < min(validation.prediction_cutoff_at)", explicit["strict_relations"])
        self.assertIn("max(validation.prediction_cutoff_at) < min(holdout.prediction_cutoff_at)", explicit["strict_relations"])

    def test_walk_forward_schema_fails_closed_without_defaults(self):
        walk = self.contract["strategy_contract"]["walk_forward_rolling_origin"]
        self.assertEqual({"expanding", "sliding"}, set(walk["mode_values"]))
        required = {"mode", "initial_train_period", "origin_step", "validation_horizon", "holdout_horizon", "minimum_folds", "incomplete_final_fold_policy", "same_match_grouping_policy", "fold_level_minimum_readiness_policy"}
        self.assertTrue(required.issubset(set(walk["required_config_fields"])))
        self.assertEqual("SPLIT_CONFIG_NOT_DECLARED", walk["missing_parameter_action"])
        self.assertEqual("NONE", walk["numeric_defaults"])
        self.assertEqual("REQUIRED_WHEN_MODE_IS_SLIDING; FORBIDDEN_AS_IMPLICIT_DEFAULT", walk["sliding_window_width"])

    def test_readiness_rule_is_structural_and_preserves_frozen_minimums(self):
        rule = self.contract["minimum_sample_readiness_contract"]
        self.assertEqual({"train": 5, "validation": 3, "holdout": 3}, rule["class_minimums"])
        self.assertEqual(1.0, rule["required_feature_availability"]["pass_value"])
        self.assertEqual(["PASS", "UNSTABLE", "UNKNOWN"], rule["stability_status_values"])
        self.assertIn("NOT_APPROVED", rule["numeric_stability_threshold"])
        self.assertIn("each_required_temporal_partition", rule["diagnostic_windows"]["source"])
        self.assertIn("class_support_in_window / eligible_samples_in_window", rule["class_rate"]["formula"])

    def test_league_scope_and_revision_binding_are_fail_closed(self):
        league = self.contract["league_scope_contract"]
        self.assertEqual("DATASET_MANIFEST", league["canonical_source"])
        self.assertEqual("LEAGUE_SCOPE_NOT_DECLARED", league["scope_not_declared_result"])
        self.assertTrue(league["sample_content_inference"] == "FORBIDDEN")
        self.assertEqual({"SINGLE_LEAGUE", "DECLARED_MULTI_LEAGUE"}, set(league["scope_types"]))
        binding = self.contract["dataset_revision_binding"]
        self.assertEqual(["dataset_id", "dataset_revision", "dataset_manifest_hash", "dataset_substantive_hash"], binding["required_identity"])
        self.assertEqual("REJECT", binding["superseded_revision_consumption"])
        self.assertTrue(binding["historical_replay"].startswith("EXPLICIT_REPLAY_MODE_REQUIRED"))

    def test_zero_data_report_is_not_a_fake_split(self):
        self.assertEqual("NOT_PERFORMABLE", self.report["split_status"])
        self.assertEqual("BLOCKED", self.report["readiness_state"])
        self.assertEqual(["TRAINING_DATA_INSUFFICIENT"], self.report["reason_codes"])
        self.assertEqual(0, self.report["sample_counts"]["candidate_samples"])
        self.assertEqual(0, self.report["sample_counts"]["usable_samples"])
        self.assertEqual("ZERO_ARCHIVED_CANDIDATES", self.report["sample_counts"]["reason"])
        self.assertFalse(self.report["split_artifact_generated"])
        self.assertIsNone(self.report["formal_split_artifact_ref"])
        self.assertIsNone(self.report["model_accuracy"])

    def test_all_machine_readable_hashes_recompute(self):
        for document in (self.contract, self.report, self.governance, self.registry, self.execution):
            self.assertRegex(document["canonical_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["canonical_hash"], self.canonical_hash(document))

    def test_focused_validator_passes(self):
        result = subprocess.run(["python", str(self.root / "scripts" / "validate_v4_batch15_ewp003_contract.py")], cwd=self.root, check=False, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("V4 BATCH-15 EWP-003 CONTRACT VALIDATION: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
