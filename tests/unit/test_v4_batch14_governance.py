from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


class V4Batch14GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.docs = cls.root / "docs"
        cls.fixture = json.loads(
            (cls.root / "tests/fixtures/v4_014/quality_gate_cases.json").read_text(encoding="utf-8")
        )
        cls.config = json.loads((cls.docs / "V4_QUALITY_GATE_CONFIG.json").read_text(encoding="utf-8"))
        cls.matrix = json.loads((cls.docs / "V4_QUALITY_GATE_MATRIX.json").read_text(encoding="utf-8"))
        cls.reasons = json.loads((cls.docs / "V4_QUALITY_GATE_REASON_REGISTRY.json").read_text(encoding="utf-8"))
        cls.decision = (cls.docs / "JCFB_V4_BATCH_14_TACTICAL_QUALITY_PROVENANCE_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")
        cls.tactical = (cls.docs / "V4_TACTICAL_LEAGUE_PROFILE_FEATURE_CONTRACT.md").read_text(encoding="utf-8")
        cls.assessment = (cls.docs / "V4_DATA_QUALITY_ASSESSMENT_CONTRACT.md").read_text(encoding="utf-8")
        cls.gate = (cls.docs / "V4_PROVENANCE_QUALITY_GATE_CONTRACT.md").read_text(encoding="utf-8")
        cls.eligibility = (cls.docs / "V4_FEATURE_ELIGIBILITY_CONTRACT.md").read_text(encoding="utf-8")

    @staticmethod
    def canonical_hash(document):
        value = dict(document)
        value.pop("canonical_hash", None)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def test_all_active_governance_artifacts_are_versioned(self):
        for key, expected in self.fixture["contract_versions"].items():
            if key == "tactical":
                self.assertIn(expected, self.tactical)
            elif key == "assessment":
                self.assertIn(expected, self.assessment)
            elif key == "gate":
                self.assertIn(expected, self.gate)
            elif key == "eligibility":
                self.assertIn(expected, self.eligibility)
            elif key == "config":
                self.assertEqual(expected, self.config["config_version"])
            elif key == "matrix":
                self.assertEqual(expected, self.matrix["matrix_version"])
            elif key == "reason_registry":
                self.assertEqual(expected, self.reasons["registry_version"])

    def test_config_matrix_and_reason_registry_have_recomputable_canonical_hashes(self):
        for document in (self.config, self.matrix, self.reasons):
            self.assertRegex(document["canonical_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["canonical_hash"], self.canonical_hash(document))

    def test_quality_is_multidimensional_and_not_a_scalar_or_confidence(self):
        self.assertEqual(self.fixture["quality_dimensions"], self.config["quality_dimensions"])
        self.assertEqual("TYPED_MULTIDIMENSIONAL_ASSESSMENT", self.config["score_policy"]["representation"])
        self.assertEqual("FORBIDDEN", self.config["score_policy"]["scalar_numeric_quality_score"])
        self.assertEqual("FORBIDDEN", self.config["score_policy"]["prediction_confidence"])
        self.assertEqual("FORBIDDEN", self.config["score_policy"]["cross_domain_weighting"])
        self.assertIn("no global numeric threshold", self.assessment)
        self.assertIn("not scalar numeric fields", self.assessment)
        self.assertNotIn('"confidence": {', self.assessment)

    def test_required_dimension_evidence_and_hash_fields_are_explicit(self):
        for field in ("state", "basis_refs", "evidence_refs", "reason_codes", "counts", "source_input_hashes"):
            self.assertIn(field, self.assessment)
        for field in ("assessment_id", "assessment_inputs", "blockers", "input_hash", "output_hash", "revision"):
            self.assertIn(f"`{field}`", self.assessment)
        for field in ("gate_record_id", "gating_matrix_version / gating_matrix_hash", "reason_registry_version / reason_registry_hash", "feature_eligibility_records", "domain_eligibility_records", "supersedes_gate_record_id"):
            self.assertIn(field, self.gate)

    def test_hard_blocker_matrix_and_stable_reason_registry_agree(self):
        hard_matrix = {item["reason_code"] for item in self.matrix["hard_blockers"]}
        hard_registry = {item["code"] for item in self.reasons["reasons"] if item["class"] == "HARD_BLOCKER"}
        self.assertEqual(hard_matrix, hard_registry)
        for code in self.fixture["hard_reasons"]:
            self.assertIn(code, hard_matrix)
        self.assertEqual("UPPER_SNAKE_CASE", self.reasons["code_policy"]["format"])
        self.assertTrue(self.reasons["code_policy"]["reason_detail_required"])

    def test_eligibility_states_and_levels_do_not_collapse(self):
        self.assertEqual(self.fixture["eligibility_states"], self.config["eligibility_policy"]["states"])
        self.assertEqual(self.fixture["levels"], self.config["eligibility_policy"]["levels"])
        self.assertIn("`INELIGIBLE` is not `BLOCKED`", self.eligibility)
        self.assertIn("optional feature `UNKNOWN`", self.eligibility)
        self.assertEqual(
            {"feature_state", "domain_propagation", "candidate_propagation"},
            set(self.matrix["non_hard_states"]["UNKNOWN"]),
        )

    def matrix_text(self):
        return json.dumps(self.matrix, ensure_ascii=False)

    def test_non_hard_states_are_explicit_and_propagation_is_matrix_defined(self):
        for state in ("UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "STALE", "CONFLICTED", "BLOCKED"):
            self.assertIn(state, self.matrix["non_hard_states"])
        self.assertTrue(self.config["eligibility_policy"]["optional_unknown_can_remain_partial"])
        self.assertEqual("MATRIX_DEFINED", self.config["eligibility_policy"]["hard_blocker_propagation"])
        self.assertIn("unavailable provider", self.eligibility)
        self.assertIn("unresolved conflict", self.eligibility)

    def test_separate_dimensions_only_and_no_three_line_fusion(self):
        self.assertEqual("SEPARATE_DIMENSIONS_ONLY", self.config["interaction_policy"]["default"])
        self.assertEqual([], self.config["interaction_policy"]["approved_rules"])
        self.assertEqual("FORBIDDEN", self.config["interaction_policy"]["statistical_football_market_aggregation"])
        self.assertIn("BATCH-11 and BATCH-13 are not added", self.decision)
        self.assertIn("independent-by-reference", self.decision)

    def test_tactical_boundary_does_not_reimplement_statistical_strength(self):
        self.assertIn("does not replace or modify BATCH-11 Statistical League Strength", self.tactical)
        self.assertIn("tactical advantage score", self.tactical)
        self.assertIn("SEPARATE_DIMENSIONS_ONLY", self.tactical)
        self.assertIn("approved vocabulary/mapping", self.tactical)

    def test_cutoff_future_and_append_only_boundaries_are_frozen(self):
        for text in (self.tactical, self.assessment, self.gate):
            self.assertIn("prediction_cutoff_at", text)
            self.assertIn("kickoff_at", text)
            self.assertIn("append", text.casefold())
            self.assertIn("supersedes", text)
        self.assertIn("input_availability_at <= prediction_cutoff_at < kickoff_at", self.tactical + self.assessment)
        self.assertIn("post-cutoff", self.decision.casefold())

    def test_frozen_input_prediction_and_abstention_remain_downstream(self):
        for text in (self.tactical, self.assessment, self.gate, self.eligibility, self.decision):
            self.assertIn("Frozen Input", text)
            self.assertIn("prediction", text.casefold())
        self.assertIn("does not emit `FROZEN_INPUT_ELIGIBLE=true/false`", self.decision)
        self.assertIn("Prediction Abstention", self.decision)
        self.assertIn("frozen_input_implementation", self.config["production_boundary"])
        self.assertEqual("FORBIDDEN", self.config["production_boundary"]["prediction"])

    def test_dependency_documents_keep_approved_batched_order(self):
        plan = (self.docs / "V4_BATCH_EXECUTION_PLAN.md").read_text(encoding="utf-8")
        register = (self.docs / "V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = (self.docs / "V4_DEPENDENCY_GRAPH_012_100.md").read_text(encoding="utf-8")
        registry = (self.docs / "V4_TASK_REGISTRY_001_100.md").read_text(encoding="utf-8")
        for document in (plan, register, registry):
            self.assertIn("V4-049", document)
            self.assertIn("V4-050", document)
            self.assertIn("V4-051", document)
        self.assertIn("BATCH-14", graph)
        self.assertIn("BATCH-09, BATCH-10, BATCH-12", plan)
        self.assertIn("V4-040 + V4-045 + V4-037", self.decision)
        self.assertIn("V4-049 + V4-050", self.decision)
        self.assertIn("BATCH-14 retains the approved batch-level upstream set", graph)

    def test_batch14_manifest_and_implementation_scope(self):
        paths = [path.as_posix() for path in (self.root / "tools").rglob("*") if path.is_file()]
        self.assertTrue(any(path.endswith("tactical_league_profile.py") for path in paths))
        manifest = json.loads((self.docs / "JCFB_V4_BATCH_14_EXECUTION_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual("FROZEN", manifest["status"])
        self.assertEqual(["V4-049", "V4-050", "V4-051"], manifest["approved_scope"])
        self.assertTrue(manifest["boundaries"]["no_frozen_input"])
        self.assertTrue(manifest["boundaries"]["batch_15_excluded"])
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any(path.startswith("database/migrations/") or path.startswith("migrations/") for path in changed))
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any("supabase" in path.casefold() and not path.startswith("docs/") for path in changed))

    def test_f_drive_and_no_production_migration_boundaries(self):
        self.assertEqual("F:", self.root.drive.upper())
        for value in self.config["production_boundary"].values():
            self.assertIn(value, {"NOT_AUTHORIZED", "FORBIDDEN"})
        self.assertIn("Production/Supabase", self.decision)
        self.assertIn("migration", self.decision.casefold())


if __name__ == "__main__":
    unittest.main()
