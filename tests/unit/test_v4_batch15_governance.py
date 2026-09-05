from __future__ import annotations

import json
import hashlib
import subprocess
import unittest
from datetime import datetime
from pathlib import Path


class V4Batch15GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.docs = cls.root / "docs"
        cls.evidence = json.loads(
            (cls.docs / "V4_BATCH_15_GOVERNANCE_EVIDENCE.json").read_text(encoding="utf-8")
        )
        cls.decision = (cls.docs / "JCFB_V4_BATCH_15_PREDICTION_ARCHITECTURE_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")
        cls.ordering = (cls.docs / "V4_BATCH_15_FROZEN_INPUT_ORDERING_AMENDMENT.md").read_text(encoding="utf-8")
        cls.review = (cls.docs / "V4_BATCH_15_ENTRY_REVIEW.md").read_text(encoding="utf-8")
        cls.training_config = json.loads((cls.root / "config/prediction_training/v4_prediction_training_governance.json").read_text(encoding="utf-8"))
        cls.model_registry = json.loads((cls.root / "config/prediction_training/v4_prediction_model_registry.json").read_text(encoding="utf-8"))
        cls.readiness = json.loads((cls.root / "config/prediction_training/v4_prediction_training_readiness_review.json").read_text(encoding="utf-8"))

    @staticmethod
    def canonical_hash(document):
        payload = {key: value for key, value in document.items() if key != "canonical_hash"}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_ordering_is_frozen_input_before_prediction(self):
        self.assertIn("-> V4-076 Frozen Input", self.ordering)
        self.assertIn("-> V4-052 / V4-053 / V4-054 / V4-055", self.ordering)
        self.assertNotIn("V4-076 -> V4-075", self.ordering)
        self.assertNotIn("depends on Final Gate", self.ordering)

    def test_batch14_status_is_canonicalized(self):
        self.assertEqual("COMPLETE", self.evidence["batch_14"]["status"])
        self.assertEqual("PASS", self.evidence["batch_14"]["closure_gate"])
        self.assertEqual(
            {"V4-049": "COMPLETE", "V4-050": "COMPLETE", "V4-051": "COMPLETE"},
            self.evidence["batch_14"]["tasks"],
        )
        for name in (
            "V4_TASK_REGISTRY_001_100.md",
            "V4_TASK_DEPENDENCY_REGISTER.md",
            "V4_DEPENDENCY_GRAPH_012_100.md",
            "V4_BATCH_EXECUTION_PLAN.md",
            "V4_MASTER_BUILD_CHECKLIST.md",
            "V4_EXECUTION_CLASSIFICATION.md",
        ):
            text = (self.docs / name).read_text(encoding="utf-8")
            self.assertIn("BATCH-14", text)
            self.assertIn("V4-049", text)
            self.assertIn("V4-050", text)
            self.assertIn("V4-051", text)
            self.assertIn("COMPLETE", text)

    def test_gate_states_are_not_collapsed(self):
        interface = (self.docs / "V4_GATE_TO_PREDICTION_INTERFACE_CONTRACT.md").read_text(encoding="utf-8")
        for state in ("BLOCKED", "INELIGIBLE", "PARTIALLY_ELIGIBLE", "ELIGIBLE"):
            self.assertIn(state, interface)
        self.assertIn("No successful probability payload", interface)
        self.assertIn("Not globally allowed", interface)
        self.assertIn("Silent imputation", interface)

    def test_fusion_and_model_artifact_boundaries(self):
        fusion = (self.docs / "V4_PREDICTION_FUSION_GOVERNANCE.md").read_text(encoding="utf-8")
        model = (self.docs / "V4_PREDICTION_MODEL_ARTIFACT_REGISTRY_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("SEPARATE_DIMENSIONS_ONLY", fusion)
        self.assertIn("DECLARED_MODEL_FUSION_ONLY", fusion)
        self.assertIn("Statistical 40% / Football 30% / Market 30%", fusion)
        self.assertIn("PREDICTION_MODEL_ARTIFACT_NOT_APPROVED", model)
        self.assertIn("No implementation may hard-code", model)

    def test_independent_engine_profiles_and_probability_contract(self):
        engines = (self.docs / "V4_BATCH_15_ENGINE_CONTRACTS.md").read_text(encoding="utf-8")
        probability = (self.docs / "V4_PROBABILITY_SEMANTICS_CONTRACT.md").read_text(encoding="utf-8")
        for term in ("Outcome Engine", "Handicap Engine", "Goals Engine", "HTFT Engine", "home_minus_away", "7+", "H/H", "A/A"):
            self.assertIn(term, engines)
        for term in ("RAW_MODEL_SCORE_OR_LOGIT", "UNCALIBRATED_MODEL_PROBABILITY", "CALIBRATED_PROBABILITY", "NOT_CALIBRATED", "1e-6", "full-precision"):
            self.assertIn(term, probability)

    def test_entry_review_remains_blocked_without_implementation(self):
        self.assertEqual("BATCH-15_ENTRY_REVIEW_BLOCKED", self.evidence["decision"])
        for code in self.evidence["blockers"]:
            self.assertIn(code, self.review)
        for task in ("V4-076", "V4-052", "V4-053", "V4-054", "V4-055"):
            self.assertEqual("TODO", self.evidence["tasks"][task]["status"])
        self.assertEqual("NO", self.evidence["safety"]["prediction_implementation"])

    def test_amended_full_task_dag_has_no_cycle(self):
        register = (self.docs / "V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = {}
        batches = {}
        for line in register.splitlines():
            if not line.startswith("| V4-"):
                continue
            fields = [field.strip() for field in line.split("|")]
            if len(fields) < 8:
                continue
            task_id, upstream_text = fields[1], fields[4]
            upstream = {
                token.strip()
                for token in upstream_text.split(",")
                if token.strip().startswith("V4-")
            }
            graph[task_id] = upstream
            batches[task_id] = fields[3]

        self.assertEqual(100, len(graph))
        graph["V4-076"] = {"V4-022", "V4-038", "V4-039", "V4-049", "V4-050", "V4-051"}
        for task_id in ("V4-052", "V4-053", "V4-054", "V4-055"):
            graph[task_id].add("V4-076")
        graph["V4-075"].add("V4-076")
        graph["V4-077"].add("V4-075")

        indegree = {task_id: len(upstream) for task_id, upstream in graph.items()}
        ready = [task_id for task_id, degree in indegree.items() if degree == 0]
        removed = 0
        while ready:
            current = ready.pop()
            removed += 1
            for downstream, upstream in graph.items():
                if current in upstream:
                    indegree[downstream] -= 1
                    if indegree[downstream] == 0:
                        ready.append(downstream)
        self.assertEqual(100, removed, f"residual cycle nodes: {[k for k, v in indegree.items() if v > 0]}")
        self.assertNotIn("V4-075", graph["V4-076"])
        self.assertEqual("BATCH-15", self.evidence["tasks"]["V4-076"]["primary_batch"])

    def test_static_validator_passes(self):
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.root / "scripts/validate_v4_batch15_governance.ps1")],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("V4 BATCH-15 GOVERNANCE VALIDATION: PASS", result.stdout)

    def test_training_governance_hashes_and_resolution(self):
        for document in (self.training_config, self.model_registry, self.readiness):
            self.assertRegex(document["canonical_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["canonical_hash"], self.canonical_hash(document))
        self.assertEqual("PREDICTION_MODEL_TRAINING_GOVERNANCE_RESOLVED", self.training_config["decision"])
        self.assertFalse(self.training_config["task_identity"]["new_task_ids_created"])
        self.assertFalse(self.training_config["task_identity"]["execution_authorized"])

    def test_training_dataset_labels_and_leakage_are_explicit(self):
        dataset = self.training_config["training_dataset_contract"]
        labels = self.training_config["label_contract"]["targets"]
        leakage = self.training_config["leakage_prevention_contract"]
        self.assertEqual("prediction-training-dataset@1.0.0", dataset["version"])
        self.assertIn("prediction_cutoff_at", dataset["required_fields"])
        self.assertIn("historical_feature_bundle_hash", dataset["required_fields"])
        self.assertEqual("feature_availability_at <= prediction_cutoff_at < kickoff_at", dataset["required_time_relation"])
        self.assertEqual(["H", "D", "A"], labels["OUTCOME"]["classes"])
        self.assertEqual(["0", "1", "2", "3", "4", "5", "6", "7+"], labels["GOALS"]["classes"])
        self.assertEqual(9, len(labels["HTFT"]["classes"]))
        self.assertIn("exact_handicap_value_at_prediction_cutoff", labels["HANDICAP"]["required_refs"])
        self.assertIn("final_score", leakage["forbidden_feature_inputs"])
        self.assertIn("future_league_table_state", leakage["forbidden_feature_inputs"])
        self.assertEqual("PHYSICALLY_OR_LOGICALLY_SEPARATE", leakage["label_feature_storage"])

    def test_temporal_selection_and_determinism_are_governed(self):
        split = self.training_config["temporal_split_contract"]
        selection = self.training_config["model_selection_protocol"]
        deterministic = self.training_config["deterministic_training_hash_profile"]
        self.assertEqual("FORBIDDEN", split["random_split"])
        self.assertTrue(split["split_boundaries_in_hash"])
        self.assertIn("holdout_is_not_used_for_fitting_selection_or_early_stopping", split["strict_relations"])
        self.assertEqual("mean_out_of_time_log_loss", selection["primary_metric"])
        self.assertEqual("ONE_FINAL_INDEPENDENT_EVALUATION_ONLY", selection["holdout_use"])
        self.assertIn("seed", deterministic["stable_inputs"])
        self.assertIn("thread_determinism_settings", deterministic["stable_inputs"])
        self.assertIn("host_name", deterministic["volatile_exclusions"])

    def test_four_engine_profiles_and_empty_registry(self):
        profiles = self.training_config["engine_training_profiles"]
        expected = {
            "OUTCOME": ["H", "D", "A"],
            "HANDICAP": ["H", "D", "A"],
            "GOALS": ["0", "1", "2", "3", "4", "5", "6", "7+"],
            "HTFT": ["H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"],
        }
        self.assertEqual(set(expected), set(profiles))
        for role, classes in expected.items():
            self.assertEqual(classes, profiles[role]["class_order"])
            self.assertEqual(role, profiles[role]["artifact_role"])
        self.assertEqual([], self.model_registry["artifacts"])
        self.assertEqual({role: "NO_TRAINING_PIPELINE" for role in expected}, self.model_registry["role_readiness"])

    def test_readiness_is_fail_closed_and_no_counts_are_invented(self):
        self.assertEqual("PREDICTION_TRAINING_READINESS_BLOCKED", self.readiness["decision"])
        self.assertFalse(self.readiness["historical_as_of_dataset"]["constructible_now"])
        self.assertFalse(self.readiness["pipeline_readiness"]["formal_model_fit_allowed"])
        self.assertFalse(self.readiness["pipeline_readiness"]["formal_engine_implementation_allowed"])
        for role in ("OUTCOME", "HANDICAP", "GOALS", "HTFT"):
            report = self.readiness["engine_readiness"][role]
            self.assertEqual("BLOCKED", report["status"])
            self.assertEqual("UNKNOWN", report["usable_sample_count"])
            self.assertEqual("UNKNOWN", report["class_distribution"])
            self.assertEqual("UNKNOWN", report["temporal_coverage"])
            self.assertEqual("UNKNOWN", report["league_coverage"])
            self.assertEqual("UNKNOWN", report["required_feature_coverage"])

    def test_no_manual_weights_quality_feature_or_v3_reuse(self):
        boundaries = self.training_config["boundary_rules"]
        self.assertFalse(boundaries["manual_fusion_weights"])
        self.assertFalse(boundaries["quality_score_as_numeric_feature"])
        self.assertFalse(boundaries["v3_3_3_reuse"])
        self.assertEqual("FORBIDDEN", self.training_config["feature_consumption"]["manual_dimension_weights"])
        self.assertEqual("FORBIDDEN", self.training_config["v3_isolation_statement"]["repository_modification"])

    def test_as_of_cutoff_and_label_feature_separation_semantics(self):
        cutoff = datetime.fromisoformat("2026-01-10T12:00:00+08:00")
        kickoff = datetime.fromisoformat("2026-01-10T20:00:00+08:00")
        available = datetime.fromisoformat("2026-01-10T11:59:00+08:00")
        late_revision = datetime.fromisoformat("2026-01-10T12:01:00+08:00")
        self.assertTrue(available <= cutoff < kickoff)
        self.assertFalse(late_revision <= cutoff < kickoff)
        self.assertEqual(
            "LABELS_ARE_POST_MATCH_TARGETS_ONLY_AND_MUST_NOT_BE_IN_FEATURE_PAYLOAD",
            self.training_config["label_contract"]["feature_label_separation"],
        )
        self.assertIn("official_final_match_result", self.training_config["label_contract"]["targets"]["OUTCOME"]["source"])

    def test_same_match_cannot_cross_temporal_partitions(self):
        split = self.training_config["temporal_split_contract"]
        self.assertEqual("All cutoff variants remain in one temporal partition", split["same_match_multi_cutoff"])
        samples = {
            "train": {"match-1"},
            "validation": {"match-2"},
            "holdout": {"match-3"},
        }
        partitions = list(samples.values())
        for index, partition in enumerate(partitions):
            for later in partitions[index + 1 :]:
                self.assertTrue(partition.isdisjoint(later))
        self.assertEqual(
            ["match_id", "cutoff_profile", "target_role"],
            self.training_config["deduplication_contract"]["unique_key"],
        )

    def test_artifact_schema_promotion_and_frozen_binding(self):
        artifact = self.training_config["model_artifact_contract"]
        promotion = self.training_config["promotion_state_contract"]
        binding = self.training_config["frozen_input_model_binding_amendment"]
        for field in ("model_artifact_id", "role", "parameter_hash", "training_dataset_id_and_hash", "training_split_id_and_hash", "fitting_implementation_hash", "training_config_version_and_hash", "validation_metrics", "holdout_metrics", "artifact_hash", "revision"):
            self.assertIn(field, artifact["required_fields"])
        self.assertEqual(["CANDIDATE", "VALIDATED", "APPROVED_FOR_ENGINE", "REJECTED"], promotion["states"])
        self.assertFalse(promotion["promotion_rules"]["automatic_promotion"])
        self.assertIn("approved_model_artifact_identity_revision_hash_per_engine", binding["v4_076_freezes"])
        self.assertEqual("NOT_IMPLEMENTED", binding["current_state"])


if __name__ == "__main__":
    unittest.main()
