import unittest
from pathlib import Path

from src.prediction_runtime import EngineRuntime, FrozenInputScaffold, SyntheticPipeline, validate_engine_output
from src.prediction_runtime.model_loader import ModelArtifactLoader, ModelLoaderError


class PredictionRuntimeScaffoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]

    def test_synthetic_e2e_is_explicitly_non_formal(self):
        result = SyntheticPipeline().run()
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["synthetic_test_only"])
        self.assertFalse(result["formal_model_fit_executed"])
        self.assertFalse(result["formal_artifacts_generated"])
        self.assertEqual({"OUTCOME", "HANDICAP", "GOALS", "HTFT"}, set(result["outputs"]))
        for output in result["outputs"].values():
            self.assertEqual("SYNTHETIC_TEST_ONLY", output["status"])
            self.assertEqual("EXPERIMENT", output["role"])
            validate_engine_output(output)

    def test_scaffold_reports_model_artifact_dependency_without_emitting_record(self):
        result = FrozenInputScaffold().assess(feature_bundle_available=True, all_sources_cutoff_valid=True, approved_model_artifacts=False, accepted_gate=True)
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("approved_model_artifacts", result["missing_prerequisites"])
        self.assertFalse(result["record_emitted"])
        self.assertFalse(result["formal_frozen_input_written"])

    def test_loader_is_blocked_by_empty_registry(self):
        loader = ModelArtifactLoader(self.root)
        result = loader.resolve("OUTCOME")
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("MODEL_ARTIFACT_NOT_APPROVED", result["reason_code"])
        with self.assertRaisesRegex(ModelLoaderError, "MODEL_ARTIFACT_NOT_APPROVED"):
            loader.load("OUTCOME")

    def test_engine_shell_does_not_run_formal_path_without_authorization(self):
        result = EngineRuntime(str(self.root)).run("OUTCOME", {"frozen_input_id": "unformed"}, {})
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("EXPERIMENT", result["role"])
        self.assertEqual("FROZEN_INPUT_FIELD_MISSING", result["errors"][0]["code"])


if __name__ == "__main__":
    unittest.main()
