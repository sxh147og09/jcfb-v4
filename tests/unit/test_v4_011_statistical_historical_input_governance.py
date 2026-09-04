from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path


class V4011StatisticalHistoricalInputGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.docs = cls.root / "docs"
        cls.contract = (cls.docs / "V4_STATISTICAL_HISTORICAL_INPUT_CONTRACT.md").read_text(encoding="utf-8")
        cls.decision = (cls.docs / "V4_BATCH_11_STATISTICAL_HISTORICAL_INPUT_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")
        cls.config_bytes = (cls.docs / "V4_BATCH_11_STATISTICAL_HISTORICAL_INPUT_CONFIG.json").read_bytes()
        cls.config = json.loads(cls.config_bytes.decode("utf-8"))
        cls.cases = json.loads((cls.root / "tests/fixtures/v4_011/historical_input_cases.json").read_text(encoding="utf-8"))

    @staticmethod
    def eligible(observation, target):
        required = (
            observation.get("source_match_id"),
            observation.get("target_match_id"),
            observation.get("availability_at"),
            observation.get("revision_visible_at_cutoff"),
        )
        if not all(required) or observation["source_match_id"] == target["match_id"]:
            return False
        if observation["target_match_id"] != target["match_id"]:
            return False
        if observation.get("verification_state") != "VERIFIED" or observation.get("quality_state") != "AVAILABLE":
            return False
        availability = datetime.fromisoformat(observation["availability_at"].replace("Z", "+00:00"))
        cutoff = datetime.fromisoformat(target["cutoff_at"].replace("Z", "+00:00"))
        kickoff = datetime.fromisoformat(target["kickoff_at"].replace("Z", "+00:00"))
        if observation.get("correction_published_at"):
            correction_at = datetime.fromisoformat(observation["correction_published_at"].replace("Z", "+00:00"))
            if correction_at > cutoff:
                return False
        return availability <= cutoff < kickoff

    def test_contract_declares_cross_match_boundary_and_target_self_rejection(self):
        for term in (
            "source_match_id != target_match_id",
            "historical-statistical-input@1.0.0",
            "availability_at <= target_prediction_cutoff_at < target_kickoff_at",
            "Official Result",
            "post-match xG",
            "INSUFFICIENT_SAMPLE",
            "half_life_matches=10",
            "competition_id + season_id",
            "EXPLICIT_TRANSLATION_REQUIRED",
            "prediction confidence",
            "Score Engine",
        ):
            self.assertIn(term, self.contract)

    def test_cross_match_eligibility_accepts_only_known_prior_observation(self):
        target = self.cases["target"]
        self.assertTrue(self.eligible(self.cases["eligible_historical_result"], target))
        self.assertFalse(self.eligible(self.cases["future_observation"], target))
        self.assertFalse(self.eligible(self.cases["target_self_result"], target))
        self.assertFalse(self.eligible(self.cases["unknown_time"], target))

    def test_post_cutoff_correction_is_not_admitted_as_visible_revision(self):
        correction = self.cases["post_cutoff_correction"]
        target = self.cases["target"]
        self.assertFalse(self.eligible(correction, target))
        self.assertIn("no post-cutoff correction replaces", self.contract)

    def test_config_is_versioned_and_has_exact_sparse_window_scope(self):
        self.assertEqual(self.config["config_version"], "statistical-strength-config@1.0.0")
        self.assertEqual(self.config["recency_policy"]["max_historical_matches"], 20)
        self.assertEqual(self.config["recency_policy"]["max_historical_days"], 730)
        self.assertEqual(self.config["recency_policy"]["half_life_matches"], 10)
        self.assertEqual(self.config["sparse_data_policy"]["below_minimum"], "NO_NUMERIC_VALUE")

    def test_config_canonical_payload_has_reproducible_hash(self):
        digest = hashlib.sha256(self.config_bytes).hexdigest()
        self.assertEqual(len(digest), 64)
        self.assertIn("sha256:" + digest, self.decision)
        self.assertIn("config version and hash", self.decision)

    def test_feature_output_is_statistical_only(self):
        for forbidden in ("win/draw/loss probability", "handicap or goals probability", "exact score", "betting selection", "Score Engine"):
            self.assertIn(forbidden, self.contract)
        self.assertIn("typed statistical strength features", self.contract)

    def test_append_only_and_v333_production_boundaries_are_explicit(self):
        for term in ("append-only", "supersedes_id", "V3.3.3", "Production/Supabase", "No migration"):
            self.assertIn(term, self.contract + self.decision)

    def test_upstream_dependency_and_scope_remain_batch_11_only(self):
        register = (self.docs / "V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        plan = (self.docs / "V4_BATCH_EXECUTION_PLAN.md").read_text(encoding="utf-8")
        for task in ("V4-041", "V4-042", "V4-043"):
            self.assertIn(task, register)
        self.assertIn("BATCH-11", plan)
        self.assertIn("V4-040", self.decision)
        self.assertNotIn("V4-076 -> V4-041", self.decision)


if __name__ == "__main__":
    unittest.main()
