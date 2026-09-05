import copy
import unittest
from pathlib import Path

from src.prediction_training.ewp004_contract import Ewp004ContractError, validate_model_artifact_package, validate_training_config
from src.prediction_training.ewp004_runtime import Ewp004Runtime, Ewp004RuntimeError


class V4Batch15Ewp004RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.runtime = Ewp004Runtime(cls.root)
        cls.valid_hash = "sha256:" + "a" * 64

    def binding(self, **overrides):
        value = {
            "dataset_id": "synthetic-dataset",
            "dataset_revision": "r001",
            "dataset_hash": self.valid_hash,
            "split_artifact_id": "synthetic-split",
            "split_revision": "r001",
            "split_hash": self.valid_hash,
            "readiness_report_id": "synthetic-readiness",
            "readiness_report_revision": "r001",
            "readiness_report_hash": self.valid_hash,
            "readiness_state": "READY",
            "usable_samples": 100,
        }
        value.update(overrides)
        return value

    def test_manifest_authorization_and_downstream_boundary(self):
        self.assertTrue(self.runtime.execution_manifest["execution_authorized"])
        self.assertTrue(self.runtime.execution_manifest["implementation_executed"])
        self.assertFalse(self.runtime.execution_manifest["formal_model_fit_authorized"])
        ewp005 = next(item for item in self.runtime.registry["work_packages"] if item["work_package_id"] == "B15-EWP-005")
        self.assertFalse(ewp005["execution_authorized"])

    def test_all_four_roles_are_isolated_and_both_families_dispatch(self):
        for role in ("OUTCOME", "HANDICAP", "GOALS", "HTFT"):
            profile = self.runtime.load_training_profile(role)
            self.assertEqual(role, profile["engine_role"])
            for family in ("regularized_multinomial_logistic", "gradient_boosted_decision_tree_probabilistic"):
                plan = self.runtime.dispatch_candidate_family(role, family)
                self.assertEqual(role, plan.engine_role)
                self.assertTrue(plan.config_id.startswith(role.lower() + "-"))
        with self.assertRaisesRegex(Ewp004RuntimeError, "UNSUPPORTED_ENGINE_ROLE"):
            self.runtime.dispatch_candidate_family("OTHER", "regularized_multinomial_logistic")
        with self.assertRaisesRegex(Ewp004RuntimeError, "UNSUPPORTED_MODEL_FAMILY"):
            self.runtime.dispatch_candidate_family("OUTCOME", "random_forest")

    def test_eight_configs_are_consumed_without_library_default_fallback(self):
        for role in ("OUTCOME", "HANDICAP", "GOALS", "HTFT"):
            for family in ("regularized_multinomial_logistic", "gradient_boosted_decision_tree_probabilistic"):
                consumed = self.runtime.consume_training_config(role, family, seed=7)
                self.assertEqual(7, consumed["seed"])
                self.assertNotIn("LIBRARY_DEFAULT", consumed["fixed_parameters"].values())
        broken = copy.deepcopy(self.runtime.contract)
        del broken["training_config_contract"]["configs"]["OUTCOME"]["regularized_multinomial_logistic"]
        with self.assertRaisesRegex(Ewp004ContractError, "TRAINING_CONFIG_NOT_DECLARED"):
            validate_training_config(broken, "OUTCOME", "regularized_multinomial_logistic")
        broken = copy.deepcopy(self.runtime.contract)
        broken["training_config_contract"]["configs"]["OUTCOME"]["regularized_multinomial_logistic"]["search_parameters"]["C"]["values"] = []
        with self.assertRaisesRegex(Ewp004ContractError, "INVALID_TRAINING_CONFIG"):
            validate_training_config(broken, "OUTCOME", "regularized_multinomial_logistic")

    def test_deterministic_context_binds_seed_thread_order_and_lineage(self):
        first = self.runtime.build_deterministic_context("OUTCOME", "regularized_multinomial_logistic", self.binding())
        second = self.runtime.build_deterministic_context("OUTCOME", "regularized_multinomial_logistic", self.binding())
        self.assertEqual(first["context_hash"], second["context_hash"])
        self.assertEqual(1, first["thread_count"])
        self.assertTrue(first["deterministic_mode"])
        changed = self.runtime.build_deterministic_context("OUTCOME", "regularized_multinomial_logistic", self.binding(dataset_revision="r002"))
        self.assertNotEqual(first["context_hash"], changed["context_hash"])
        self.assertEqual(first["feature_order"], [item["feature_id"] for item in self.runtime.load_training_profile("OUTCOME")["required_features"]] + [item["feature_id"] for item in self.runtime.load_training_profile("OUTCOME")["optional_features"]])

    def test_current_real_data_is_pre_fit_blocked_with_no_outputs(self):
        result = self.runtime.current_real_prefit_validation()
        self.assertFalse(result["gate"].formal_fit_allowed)
        self.assertFalse(result["gate"].artifact_generation_allowed)
        self.assertFalse(result["gate"].model_registry_write_allowed)
        self.assertTrue({"TRAINING_DATA_INSUFFICIENT", "FORMAL_SPLIT_NOT_AVAILABLE", "EWP005_NOT_AUTHORIZED"}.issubset(set(result["gate"].reasons)))
        self.assertEqual(0, result["binding"]["usable_samples"])
        self.assertFalse(result["parameter_artifacts_generated"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "FORMAL_FIT_BLOCKED"):
            self.runtime.request_formal_fit(result["binding"])

    def test_metrics_and_probability_contract_use_full_precision(self):
        observed = ["H", "D", "A"]
        probabilities = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        result = self.runtime.evaluate_metrics(observed, probabilities, ["H", "D", "A"])
        self.assertEqual(0.0, result["log_loss"])
        self.assertEqual(0.0, result["brier_score"])
        self.assertTrue(result["probability_normalization_validity"])
        self.assertEqual("NOT_CALIBRATED", result["calibration_state"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "INVALID_PROBABILITY_VECTOR"):
            self.runtime.evaluate_metrics(["H"], [[1.1, -0.1, 0.0]], ["H", "D", "A"])
        self.runtime.evaluate_metrics(["H"], [[0.5, 0.5, 0.000001]], ["H", "D", "A"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "PROBABILITY_NOT_NORMALIZED"):
            self.runtime.evaluate_metrics(["H"], [[0.5, 0.5, 0.0000011]], ["H", "D", "A"])
        zero_support = self.runtime.evaluate_metrics(["H", "H"], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], ["H", "D", "A"])
        self.assertIsNone(zero_support["classwise_recall"]["by_class"]["A"])
        self.assertEqual(0, zero_support["class_support"]["A"])

    def test_ephemeral_serialization_append_only_and_package_bindings(self):
        payload = {"coef": [0.1, 0.2], "role": "OUTCOME"}
        first_serialized = self.runtime.serialize_parameter_payload(payload)
        second_serialized = self.runtime.serialize_parameter_payload(payload)
        self.assertEqual(first_serialized, second_serialized)
        artifact = self.runtime.build_ephemeral_parameter_artifact("OUTCOME", "regularized_multinomial_logistic", self.binding(), payload)
        self.assertTrue(artifact["ephemeral"])
        entries = self.runtime.append_ephemeral_parameter_artifact([], artifact)
        replacement = self.runtime.build_ephemeral_parameter_artifact("OUTCOME", "regularized_multinomial_logistic", self.binding(), payload, revision=2, supersedes=artifact["parameter_artifact_id"])
        self.assertEqual(2, len(self.runtime.append_ephemeral_parameter_artifact(entries, replacement)))
        with self.assertRaisesRegex(Ewp004RuntimeError, "REJECT_PARAMETER_ARTIFACT_OVERWRITE"):
            self.runtime.append_ephemeral_parameter_artifact(entries, artifact)
        package = self.runtime.build_ephemeral_model_package(artifact)
        self.assertEqual("CANDIDATE", package["status"])
        self.assertTrue(package["ephemeral"])
        missing = dict(package)
        missing.pop("split_artifact_hash")
        with self.assertRaisesRegex(Ewp004ContractError, "BLOCKED_MODEL_ARTIFACT_PACKAGING_BINDING_INCOMPLETE"):
            validate_model_artifact_package(missing, self.runtime.contract)

    def test_selection_holdout_leakage_and_tie_break(self):
        candidates = [
            {"family_id": "z-family", "metrics": {"mean_out_of_time_log_loss": 0.4, "mean_out_of_time_brier_score": 0.2, "log_loss_variance": 0.01, "complexity": 1}},
            {"family_id": "a-family", "metrics": {"mean_out_of_time_log_loss": 0.4, "mean_out_of_time_brier_score": 0.2, "log_loss_variance": 0.01, "complexity": 1}},
        ]
        self.assertEqual("a-family", self.runtime.select_candidate(candidates)["family_id"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "HOLDOUT_LEAKAGE_REJECTED"):
            self.runtime.select_candidate(candidates, evaluation_partition="holdout")
        self.runtime.validate_evaluation_partition("holdout", purpose="final_independent_evaluation")
        with self.assertRaisesRegex(Ewp004RuntimeError, "EVALUATION_PARTITION_INVALID"):
            self.runtime.validate_evaluation_partition("unknown", purpose="candidate_selection")

    def test_promotion_is_manual_and_ewp004_cannot_approve_or_register(self):
        self.assertEqual("VALIDATED", self.runtime.promote_candidate("CANDIDATE", "VALIDATED")["to"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "PROMOTION_HUMAN_GATE_REQUIRED"):
            self.runtime.validate_promotion_transition("VALIDATED", "APPROVED_FOR_ENGINE")
        with self.assertRaisesRegex(Ewp004RuntimeError, "EWP004_PROMOTION_OUT_OF_SCOPE"):
            self.runtime.promote_candidate("VALIDATED", "APPROVED_FOR_ENGINE", human_gate=True)

    def test_synthetic_adapter_is_ephemeral_and_does_not_fit(self):
        result = self.runtime.adapter.fit("GOALS", "gradient_boosted_decision_tree_probabilistic", synthetic=True, rows=[{"sample_id": "s1"}])
        self.assertTrue(result["ephemeral"])
        self.assertFalse(result["fit_executed"])
        self.assertEqual("DISPATCH_VALIDATED_NO_ESTIMATOR", result["candidate_adapter_boundary"])
        with self.assertRaisesRegex(Ewp004RuntimeError, "EWP005_NOT_AUTHORIZED"):
            self.runtime.adapter.fit("GOALS", "gradient_boosted_decision_tree_probabilistic", formal_request=self.binding())

    def test_f_drive_and_v3_isolation_boundaries(self):
        with self.assertRaisesRegex(Ewp004RuntimeError, "F_DRIVE_REQUIRED"):
            Ewp004Runtime("C:/not-an-approved-root")
        boundary = self.runtime.scope_boundary()
        self.assertTrue(boundary["f_drive_pass"])
        self.assertFalse(boundary["v3_3_3_modified"])
        self.assertFalse(boundary["database_or_supabase_touched"])
        self.assertFalse(boundary["model_registry_inserted"])


if __name__ == "__main__":
    unittest.main()
