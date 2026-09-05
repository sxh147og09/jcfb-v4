from __future__ import annotations

import json
import subprocess
import unittest
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


if __name__ == "__main__":
    unittest.main()
