from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


class V4010ArchitectureGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.docs = cls.root / "docs"
        cls.fixture = json.loads(
            (cls.root / "tests/fixtures/v4_010/governance_cases.json").read_text(encoding="utf-8")
        )
        cls.feature = (cls.docs / "V4_FEATURE_BUNDLE_CONTRACT.md").read_text(encoding="utf-8")
        cls.feature_v1 = (cls.docs / "V4_FEATURE_BUNDLE_CONTRACT_1.0.md").read_text(encoding="utf-8")
        cls.frozen = (cls.docs / "V4_FROZEN_INPUT_CONTRACT.md").read_text(encoding="utf-8")
        cls.frozen_v1 = (cls.docs / "V4_FROZEN_INPUT_CONTRACT_1.0.md").read_text(encoding="utf-8")
        cls.adr = (cls.docs / "V4_BATCH_10_ARCHITECTURE_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")

    def test_active_contracts_are_major_versions_and_v1_is_preserved(self):
        self.assertIn("feature-bundle@2.0.0", self.feature)
        self.assertIn("frozen-input@2.0.0", self.frozen)
        self.assertIn("feature-bundle@1.0.0", self.feature_v1)
        self.assertIn("frozen-input@1.0.0", self.frozen_v1)
        self.assertIn("breaking major version", self.adr)

    def test_feature_bundle_uses_upstream_lineage_not_frozen_input(self):
        for field in self.fixture["required_upstream_lineage"]:
            self.assertIn(f"`{field}`", self.feature)
        self.assertIn("`frozen_input_id` and `frozen_input_hash` are not creation-stage inputs", self.feature)
        self.assertNotRegex(self.feature, r"\|\s*`frozen_input_id`\s*\|\s*REQUIRED")
        self.assertNotIn("Frozen Input -> Feature Bundle", self.feature)
        self.assertIn("-> Frozen Input", self.feature)

    def test_frozen_input_consumes_exact_feature_snapshot(self):
        for field in ("feature_bundle_id", "feature_snapshot_hash", "feature_bundle_contract_version"):
            self.assertIn(f"`{field}`", self.frozen)
        self.assertIn("pre-prediction freeze artifact", self.frozen)
        self.assertIn("feature_snapshot_hash", self.frozen)

    def test_feature_quality_has_only_data_quality_dimensions(self):
        for dimension in self.fixture["feature_quality_dimensions"]:
            self.assertIn(f'"{dimension}"', self.feature)
        self.assertIn("unqualified bare `confidence`", self.feature)
        self.assertIn("must not be interpreted as win probability", self.feature)
        self.assertNotIn('"confidence": {', self.feature)

    def test_task_order_and_dependency_direction_remain_approved(self):
        register = (self.docs / "V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = (self.docs / "V4_DEPENDENCY_GRAPH_012_100.md").read_text(encoding="utf-8")
        for task in self.fixture["batch_10_tasks"]:
            self.assertIn(f"| {task} |", register)
        self.assertIn("V4-076", register)
        evidence = (self.docs / "V4_BATCH_15_GOVERNANCE_EVIDENCE.json").read_text(encoding="utf-8")
        self.assertIn("V4-022", evidence)
        self.assertIn("V4-038", evidence)
        self.assertIn("V4-039", evidence)
        self.assertIn("V4-049", evidence)
        self.assertIn("V4-050", evidence)
        self.assertIn("V4-051", evidence)
        self.assertIn("Feature Bundle is upstream", graph)
        self.assertIn("V4-076 Frozen Input", graph)
        self.assertNotIn("V4-076 -> V4-038", self.adr)

    def test_active_architecture_docs_do_not_retain_reverse_edge(self):
        active = [
            "V4_DATA_CONTRACT.md",
            "V4_CANONICAL_DATA_MODEL.md",
            "V4_DATA_LIFECYCLE.md",
            "V4_DATABASE_SCHEMA_BLUEPRINT.md",
            "V4_ENTITY_RELATIONSHIP_MODEL.md",
            "V4_PERSISTENCE_BOUNDARIES.md",
            "V4_FUTURE_SUPABASE_BLUEPRINT.md",
        ]
        reverse_patterns = (
            r"Frozen Input\s*[-→>]\s*Feature Bundle",
            r"Feature Bundle.*one Frozen Input",
            r"Only a passed Frozen Input may generate.*Feature Bundle",
            r"feature_bundles.*has exactly one Frozen Input",
        )
        for name in active:
            text = (self.docs / name).read_text(encoding="utf-8")
            for pattern in reverse_patterns:
                self.assertIsNone(re.search(pattern, text, re.IGNORECASE), f"{name}: {pattern}")

    def test_no_implementation_or_production_boundary_was_crossed(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "29d1455bdee3ff84a46f9b0d26003f26d07a7df2"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertTrue(changed)
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("migrations/") for path in changed))
        self.assertFalse(any("supabase" in path.casefold() and not path.startswith("docs/") for path in changed))
        implementation_markers = ("V4-038", "V4-039", "V4-040")
        self.assertTrue(all(any(marker in path for marker in implementation_markers) is False for path in changed if path.startswith("tools/")))

    def test_f_drive_workspace_boundary(self):
        self.assertEqual("F:", self.root.drive.upper())
        self.assertTrue(str(self.root).casefold().startswith("f:\\projects\\jcfb-v4"))


if __name__ == "__main__":
    unittest.main()
