from __future__ import annotations

import copy
import json
import re
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    FootballIntelligenceGovernanceError,
    calculate_governance_hash,
    load_approved_config,
    validate_pre_freeze_artifact,
)


class V4Batch12GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_012/football_intelligence_cases.json").read_text(encoding="utf-8"))
        cls.config = load_approved_config(cls.root)

    def artifact(self):
        return copy.deepcopy(self.fixture["base_artifact"])

    def test_versioned_config_has_no_model_effect_coefficients(self):
        self.assertEqual("football-intelligence-config@1.0.0", self.config["config_version"])
        self.assertEqual("football-intelligence-mapping@1.0.0", self.config["mapping_registry_version"])
        self.assertEqual([], self.config["approved_model_effect_coefficients"])
        self.assertEqual("SEPARATE_DIMENSIONS_ONLY", self.config["policy"]["interaction_default"])
        self.assertEqual("PRESERVE_STATE", self.config["policy"]["missing_behavior"])

    def test_pre_freeze_artifact_is_typed_and_replayable(self):
        artifact = self.artifact()
        validate_pre_freeze_artifact(artifact, config=self.config)
        self.assertEqual(calculate_governance_hash(artifact), calculate_governance_hash(copy.deepcopy(artifact)))
        self.assertNotIn("frozen_input_id", artifact)
        self.assertNotIn("frozen_input_hash", artifact)

    def test_frozen_input_is_not_a_pre_freeze_dependency(self):
        artifact = self.artifact()
        artifact["frozen_input_id"] = "not-allowed"
        with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "pre-Frozen artifact cannot reference Frozen Input"):
            validate_pre_freeze_artifact(artifact, config=self.config)

    def test_non_consumable_state_requires_reason_and_has_no_replacement_value(self):
        for state in self.fixture["non_consumable_states"]:
            artifact = self.artifact()
            feature = artifact["features"][0]
            feature["state"] = state
            feature["value"] = None
            feature["reason_code"] = f"{state}_EXPLICIT"
            feature["reason_detail"] = "The accepted upstream state is preserved."
            validate_pre_freeze_artifact(artifact, config=self.config)

            invalid = copy.deepcopy(artifact)
            invalid["features"][0]["value"] = 0
            with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "must not carry a numeric replacement value"):
                validate_pre_freeze_artifact(invalid, config=self.config)

    def test_projected_context_remains_categorical(self):
        artifact = self.artifact()
        projected = artifact["features"][1]
        projected["kind"] = "NUMERIC"
        with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "projected context must remain categorical"):
            validate_pre_freeze_artifact(artifact, config=self.config)

    def test_bare_confidence_and_prediction_like_fields_are_rejected(self):
        artifact = self.artifact()
        artifact["feature_quality"]["confidence"] = {"score": 0.8}
        with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "feature_quality cannot be prediction-like"):
            validate_pre_freeze_artifact(artifact, config=self.config)

        forbidden = self.artifact()
        forbidden["features"][0]["prediction"] = "HOME"
        with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "cannot contain"):
            validate_pre_freeze_artifact(forbidden, config=self.config)

    def test_cutoff_and_time_boundaries_fail_closed(self):
        artifact = self.artifact()
        artifact["prediction_cutoff_at"] = artifact["kickoff_at"]
        with self.assertRaisesRegex(FootballIntelligenceGovernanceError, "must precede kickoff_at"):
            validate_pre_freeze_artifact(artifact, config=self.config)

    def test_dependency_and_contract_governance_documents_are_consistent(self):
        plan = (self.root / "docs/V4_BATCH_EXECUTION_PLAN.md").read_text(encoding="utf-8")
        register = (self.root / "docs/V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = (self.root / "docs/V4_DEPENDENCY_GRAPH_012_100.md").read_text(encoding="utf-8")
        decision = (self.root / "docs/V4_BATCH_12_ARCHITECTURE_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")
        registry = (self.root / "docs/V4_TASK_REGISTRY_001_100.md").read_text(encoding="utf-8")
        engine_output = (self.root / "docs/V4_ENGINE_OUTPUT_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("BATCH-10, BATCH-11", plan)
        self.assertIn("current approved BATCH-12 batch-level upstream set is `BATCH-10, BATCH-11`", register)
        self.assertIn("current approved batch-level upstream set is `BATCH-10, BATCH-11`", graph)
        self.assertIn("PRE-FROZEN FEATURE GENERATORS", decision)
        self.assertIn("football-intelligence", decision.casefold())
        self.assertIn("pre-Frozen feature generators", registry)
        self.assertIn("pre-frozen feature artifact boundary", engine_output.casefold())

    def test_dependency_register_is_acyclic_and_has_batch12_edges(self):
        register = (self.root / "docs/V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = (self.root / "docs/V4_DEPENDENCY_GRAPH_012_100.md").read_text(encoding="utf-8")
        task_rows = {}
        for line in register.splitlines():
            if not re.match(r"^\| V4-\d{3} \|", line):
                continue
            columns = [column.strip() for column in line.split("|")[1:-1]]
            if len(columns) < 5:
                continue
            task_id = columns[0]
            upstream_ids = set(re.findall(r"V4-\d{3}", columns[3]))
            task_rows[task_id] = upstream_ids

        nodes = set(task_rows)
        indegree = {node: 0 for node in nodes}
        outgoing = {node: set() for node in nodes}
        for task_id, upstream_ids in task_rows.items():
            for upstream_id in upstream_ids & nodes:
                outgoing[upstream_id].add(task_id)
                indegree[task_id] += 1

        queue = [node for node, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for child in outgoing[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        self.assertEqual(len(nodes), visited, "task dependency register contains a cycle")
        self.assertIn('B10 --> B12["BATCH-12 Football"]', graph)
        self.assertIn('B11 --> B12["BATCH-12 Football"]', graph)

    def test_team_context_v2_uses_only_context_confidence(self):
        active = (self.root / "docs/V4_TEAM_CONTEXT_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("team-context@2.0.0", active)
        self.assertIn("context_confidence", active)
        self.assertIn("A bare `confidence` field is forbidden", active)
        self.assertIsNone(re.search(r'"confidence"\s*:', active))
        archived = (self.root / "docs/V4_TEAM_CONTEXT_CONTRACT_1.0.md").read_text(encoding="utf-8")
        self.assertIn("team-context@1.0.0", archived)
        self.assertIn('"confidence"', archived)

    def test_no_production_migration_or_v333_scope_was_added(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))
        self.assertEqual("F:", self.root.drive.upper())


if __name__ == "__main__":
    unittest.main()
