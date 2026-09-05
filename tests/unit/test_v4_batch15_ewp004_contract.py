from __future__ import annotations

import json
import copy
import subprocess
import unittest
from pathlib import Path

from src.prediction_training.ewp004_contract import (
    ENGINE_ROLES,
    Ewp004ContractError,
    append_parameter_artifact,
    class_support,
    classwise_recall,
    load_contract,
    multiclass_brier_score,
    multiclass_log_loss,
    validate_feature_payload,
    validate_model_artifact_package,
    validate_model_family,
    validate_parameter_artifact,
    validate_probability_vector,
    validate_readiness_binding,
    validate_training_config,
)


class V4Batch15Ewp004ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.contract = load_contract()

    def test_contract_is_remediated_without_execution_authorization(self):
        self.assertEqual([], __import__("src.prediction_training.ewp004_contract", fromlist=["validate_contract"]).validate_contract(self.contract))
        self.assertFalse(self.contract["execution_authorized"])
        self.assertFalse(self.contract["implementation_executed"])
        self.assertFalse(self.contract["formal_model_fit_authorized"])
        self.assertEqual("NOT_CALIBRATED", self.contract["calibration_state"])

    def test_exact_two_families_and_four_independent_profiles(self):
        families = {item["family_id"] for item in self.contract["candidate_model_family_registry"]["families"]}
        self.assertEqual({"regularized_multinomial_logistic", "gradient_boosted_decision_tree_probabilistic"}, families)
        profiles = self.contract["engine_training_profiles"]
        self.assertEqual(set(ENGINE_ROLES), set(profiles))
        self.assertEqual(4, len({profile["profile_hash"] for profile in profiles.values()}))
        for role, profile in profiles.items():
            self.assertEqual(role, profile["engine_role"])
            self.assertEqual(profile["output_class_schema"]["classes"], profile["output_class_schema"]["order"])
            self.assertTrue(profile["required_features"])
            self.assertEqual("NOT_CALIBRATED", profile["calibration_state_expectation"])

    def test_unsupported_family_is_rejected(self):
        with self.assertRaisesRegex(Ewp004ContractError, "UNSUPPORTED_MODEL_FAMILY"):
            validate_model_family(self.contract, "unregistered_black_box", "OUTCOME")

    def test_all_role_family_configs_are_explicit_and_defaults_cannot_fallback(self):
        configs = self.contract["training_config_contract"]["configs"]
        self.assertEqual(set(ENGINE_ROLES), set(configs))
        for role in ENGINE_ROLES:
            for family in self.contract["candidate_model_family_registry"]["families"]:
                family_id = family["family_id"]
                config = validate_training_config(self.contract, role, family_id)
                self.assertTrue(config["fixed_parameters"])
                self.assertTrue(config["search_parameters"])
                self.assertNotEqual("LIBRARY_DEFAULT", config["fixed_parameters"].get("validation_fraction"))
        self.assertEqual("REJECT_TRAINING_CONFIG_NOT_DECLARED", self.contract["training_config_contract"]["library_default_fallback"])
        self.assertEqual(
            self.contract["training_config_contract"]["configs"]["OUTCOME"]["regularized_multinomial_logistic"]["config_hash"],
            self.contract["model_selection_protocol"]["bound_config_bindings"]["OUTCOME"]["regularized_multinomial_logistic"]["config_hash"],
        )
        missing_config_contract = copy.deepcopy(self.contract)
        del missing_config_contract["training_config_contract"]["configs"]["OUTCOME"]["regularized_multinomial_logistic"]
        with self.assertRaisesRegex(Ewp004ContractError, "TRAINING_CONFIG_NOT_DECLARED"):
            validate_training_config(missing_config_contract, "OUTCOME", "regularized_multinomial_logistic")

    def test_feature_profiles_reject_missing_and_undeclared_features(self):
        profile = self.contract["engine_training_profiles"]["HANDICAP"]
        payload = {feature["feature_id"]: 1.0 for feature in profile["required_features"]}
        validate_feature_payload(profile, payload)
        payload[profile["optional_features"][0]["feature_id"]] = {"state": "NOT_AVAILABLE"}
        validate_feature_payload(profile, payload)
        missing = dict(payload)
        missing.pop(profile["required_features"][0]["feature_id"])
        with self.assertRaisesRegex(Ewp004ContractError, "REQUIRED_FEATURE_MISSING"):
            validate_feature_payload(profile, missing)
        with self.assertRaisesRegex(Ewp004ContractError, "UNDECLARED_FEATURE"):
            validate_feature_payload(profile, {**{feature["feature_id"]: 1.0 for feature in profile["required_features"]}, "implicit_default": 1.0})

    def test_readiness_binding_is_complete_but_blocked_state_rejects_fit(self):
        binding = {
            "dataset_id": "dataset-1", "dataset_revision": "r001", "dataset_hash": "sha256:" + "a" * 64,
            "split_artifact_id": "split-1", "split_revision": "r001", "split_hash": "sha256:" + "b" * 64,
            "training_readiness_report_id": "report-1", "readiness_report_revision": "r001", "readiness_report_hash": "sha256:" + "c" * 64,
            "readiness_state": "BLOCKED",
        }
        with self.assertRaisesRegex(Ewp004ContractError, "REJECT_FORMAL_FIT_READINESS_NOT_ACTIVE"):
            validate_readiness_binding(binding, self.contract)
        binding["readiness_state"] = "READY"
        validate_readiness_binding(binding, self.contract)

    def test_probability_contract_and_metric_formulas(self):
        self.assertEqual((1.0, 0.0, 0.0), validate_probability_vector([1.0, 0.0, 0.0], 3))
        with self.assertRaisesRegex(Ewp004ContractError, "INVALID_PROBABILITY_VECTOR"):
            validate_probability_vector([1.2, -0.1, -0.1], 3)
        with self.assertRaisesRegex(Ewp004ContractError, "PROBABILITY_NOT_NORMALIZED"):
            validate_probability_vector([0.5, 0.5, 0.01], 3)
        observed = ["H", "D", "A"]
        probabilities = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        self.assertAlmostEqual(0.0, multiclass_log_loss(observed, probabilities, ["H", "D", "A"]))
        self.assertAlmostEqual(0.0, multiclass_brier_score(observed, probabilities, ["H", "D", "A"]))

    def test_zero_support_recall_is_null_and_excluded_from_macro(self):
        result = classwise_recall(["H", "H"], ["H", "D"], ["H", "D", "A"])
        self.assertEqual({"H": 2, "D": 0, "A": 0}, class_support(["H", "H"], ["H", "D", "A"]))
        self.assertEqual(0.5, result["by_class"]["H"])
        self.assertIsNone(result["by_class"]["D"])
        self.assertIsNone(result["by_class"]["A"])
        self.assertEqual(0.5, result["macro"])
        self.assertEqual("NULL_AND_EXCLUDED_FROM_MACRO", result["zero_support_behavior"])

    def _parameter_artifact(self, revision=1, supersedes=None):
        valid = "sha256:" + "a" * 64
        return {
            "parameter_artifact_id": "parameter-outcome-logistic",
            "engine_role": "OUTCOME", "model_family_id": "regularized_multinomial_logistic", "model_family_version": "regularized-multinomial-logistic@1.0.0",
            "dataset_id": "dataset-1", "dataset_revision": "r001", "dataset_hash": valid,
            "split_artifact_id": "split-1", "split_revision": "r001", "split_hash": valid,
            "readiness_report_id": "report-1", "readiness_report_revision": "r001", "readiness_report_hash": valid,
            "training_config_id": "outcome-regularized-multinomial-logistic-config@1.0.0", "training_config_revision": "r001", "training_config_hash": valid,
            "fitting_implementation_id": "v4-training-fitting-boundary@1.0.0", "fitting_implementation_version": "r001", "fitting_implementation_hash": valid,
            "deterministic_runtime_profile_id": "fitting-runtime-profile@1.0.0", "deterministic_runtime_profile_revision": "r001", "deterministic_runtime_profile_hash": valid,
            "random_seed": 20260905, "parameter_payload_or_ref": {"coef": [0.1, 0.2]}, "parameter_hash": valid,
            "serialization_identity": "canonical-json@v4-1.0", "created_at": "2026-09-05T00:00:00+08:00", "revision": revision, "supersedes": supersedes,
        }

    def test_parameter_artifact_is_append_only(self):
        first = self._parameter_artifact()
        validate_parameter_artifact(first, self.contract)
        entries = append_parameter_artifact([], first, self.contract)
        with self.assertRaisesRegex(Ewp004ContractError, "REJECT_PARAMETER_ARTIFACT_OVERWRITE"):
            append_parameter_artifact(entries, dict(first), self.contract)
        replacement = self._parameter_artifact(revision=2, supersedes="parameter-outcome-logistic")
        self.assertEqual(2, len(append_parameter_artifact(entries, replacement, self.contract)))

    def test_model_packaging_requires_every_binding(self):
        package = {field: "value" for field in self.contract["model_artifact_packaging_contract"]["required_bindings"]}
        for field in ("parameter_artifact_hash", "training_readiness_report_hash", "split_artifact_hash", "dataset_hash", "engine_training_profile_hash", "model_family_registry_hash", "training_config_hash", "deterministic_runtime_profile_hash", "fitting_implementation_hash"):
            package[field] = "sha256:" + "a" * 64
        validate_model_artifact_package(package, self.contract)
        package.pop("split_artifact_hash")
        with self.assertRaisesRegex(Ewp004ContractError, "BLOCKED_MODEL_ARTIFACT_PACKAGING_BINDING_INCOMPLETE"):
            validate_model_artifact_package(package, self.contract)

    def test_static_validator_and_no_fit_entrypoint(self):
        result = subprocess.run(["python", str(self.root / "scripts/validate_v4_batch15_ewp004_contract.py")], cwd=self.root, check=False, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("EWP-004 execution authorization: false", result.stdout)
        self.assertFalse((self.root / "src/prediction_training/ewp004_runtime.py").exists())
        self.assertFalse((self.root / "scripts/run_v4_batch15_ewp004.py").exists())


if __name__ == "__main__":
    unittest.main()
