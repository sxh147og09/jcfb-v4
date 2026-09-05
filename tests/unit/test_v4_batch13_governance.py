from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class V4Batch13GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.config = json.loads((cls.root / "docs/V4_MARKET_INTELLIGENCE_CONFIG.json").read_text(encoding="utf-8"))
        cls.mapping = json.loads((cls.root / "docs/V4_MARKET_INTELLIGENCE_MAPPING.json").read_text(encoding="utf-8"))
        cls.feature_contract = (cls.root / "docs/V4_MARKET_INTELLIGENCE_FEATURE_CONTRACT.md").read_text(encoding="utf-8")
        cls.movement_contract = (cls.root / "docs/V4_MARKET_MOVEMENT_CONTRACT.md").read_text(encoding="utf-8")
        cls.risk_contract = (cls.root / "docs/V4_MARKET_RISK_INTERPRETATION_CONTRACT.md").read_text(encoding="utf-8")
        cls.decision = (cls.root / "docs/JCFB_V4_BATCH_13_MARKET_INTELLIGENCE_GOVERNANCE_DECISION.md").read_text(encoding="utf-8")

    def test_versioned_governance_artifacts_exist(self):
        self.assertEqual("market-intelligence-config@1.0.0", self.config["config_version"])
        self.assertEqual("market-intelligence-mapping@1.0.0", self.config["mapping_registry_version"])
        self.assertIn("market-intelligence-feature@1.0.0", self.feature_contract)
        self.assertIn("market-movement@1.0.0", self.movement_contract)
        self.assertIn("market-risk-interpretation@1.0.0", self.risk_contract)

    def test_pre_frozen_lifecycle_excludes_formal_prediction_input(self):
        lifecycle = self.config["lifecycle"]
        self.assertEqual("PRE_FROZEN_MARKET_FEATURE_GENERATION", lifecycle["classification"])
        self.assertEqual("NOT_USED", lifecycle["formal_engine_output"])
        self.assertEqual("FORBIDDEN", lifecycle["frozen_input_id"])
        self.assertEqual("FORBIDDEN", lifecycle["frozen_input_hash"])
        self.assertEqual("FORBIDDEN", lifecycle["prediction"])
        self.assertIn("Frozen Input", self.feature_contract)

    def test_snapshot_kinds_and_latest_eligibility_are_explicit(self):
        selection = self.config["snapshot_selection"]
        self.assertEqual("LATEST_ELIGIBLE", selection["eligible_label"])
        self.assertTrue(selection["opening_requires_declared_identity"])
        self.assertTrue(selection["latest_requires_greatest_eligible_source_time"])
        self.assertEqual(["source_timestamp", "captured_at", "snapshot_hash"], selection["ordering_fields"])
        for kind in ("OPENING", "INTERMEDIATE", "CURRENT", "LATEST", "FINAL", "CORRECTION"):
            self.assertIn(kind, self.feature_contract)

    def test_same_source_alignment_and_movement_types_are_separate(self):
        self.assertIn("same canonical `match_id`, provider/source, market, semantic selection, and semantic line", self.movement_contract)
        for movement_type in ("PRICE_MOVEMENT", "LINE_MOVEMENT", "IMPLIED_PROBABILITY_MOVEMENT"):
            self.assertIn(movement_type, self.movement_contract)
        self.assertIn("must not be merged into an opaque single movement", self.movement_contract)

    def test_european_implied_probability_formula_is_not_prediction_probability(self):
        normalization = self.config["normalization_policy"]["european_1x2"]
        self.assertEqual("1_divided_by_decimal_odds", normalization["raw_implied_probability"])
        self.assertEqual("market_implied_probability", normalization["field_name"])
        self.assertEqual("FORBIDDEN", normalization["prediction_probability_alias"])
        mapping = next(item for item in self.mapping["mappings"] if item["mapping_key"] == "EUROPEAN_1X2_MARKET_IMPLIED_PROBABILITY")
        self.assertFalse(mapping["prediction_probability"])

    def test_velocity_and_acceleration_rules_are_deterministic(self):
        policy = self.config["movement_policy"]
        self.assertEqual("value_delta_divided_by_elapsed_hours", policy["velocity_formula"])
        self.assertEqual("BLOCKED", policy["non_positive_elapsed_time"])
        self.assertEqual(3, policy["acceleration_minimum_valid_snapshots"])
        self.assertEqual("UNKNOWN_INSUFFICIENT_SERIES", policy["insufficient_acceleration_series"])
        self.assertEqual("FORBIDDEN", policy["extrapolation"])

    def test_provider_policy_has_no_subjective_weights(self):
        policy = self.config["provider_policy"]
        self.assertEqual("EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION", policy["aggregation_policy"])
        self.assertEqual([], policy["provider_importance_coefficients"])
        self.assertEqual("FORBIDDEN", policy["weighted_bookmaker_consensus"])
        self.assertIn("median", self.movement_contract.casefold())
        self.assertIn("iqr", self.movement_contract.casefold())
        self.assertIn("mad", self.movement_contract.casefold())

    def test_official_external_comparability_is_restricted(self):
        comparable = self.config["comparability_policy"]["official_to_external"]
        self.assertEqual("ALLOWED_IF_SEMANTICALLY_ALIGNED", comparable["official_spf_to_external_european_1x2"])
        self.assertEqual("NOT_COMPARABLE", comparable["official_rqspf_to_external_asian_handicap"])
        self.assertEqual("NOT_COMPARABLE", comparable["official_total_goals_distribution_to_external_over_under"])
        self.assertIn("source_is_official=false", self.feature_contract)
        self.assertIn("official refs/hashes", self.movement_contract)

    def test_missing_stale_conflicted_and_future_states_are_preserved(self):
        for state in ("AVAILABLE", "UNAVAILABLE", "SUSPENDED", "UNKNOWN", "NOT_VERIFIED", "STALE", "CONFLICTED", "FUTURE_DATA", "BLOCKED"):
            self.assertIn(state, self.feature_contract)
        self.assertIn("previous_snapshot", json.dumps(self.config))
        self.assertIn("other_provider", json.dumps(self.config))
        self.assertIn("Post-cutoff snapshots remain `FUTURE_DATA` or `BLOCKED`", self.feature_contract)

    def test_heat_is_multidimensional_and_pressure_is_component_based(self):
        self.assertEqual("MULTIDIMENSIONAL_ACTIVITY_OBJECT", self.config["heat_policy"]["representation"])
        self.assertEqual("COMPONENT_OBJECT", self.config["pressure_policy"]["representation"])
        self.assertEqual("FORBIDDEN_UNLESS_FUTURE_CALIBRATED_CONTRACT", self.config["heat_policy"]["heat_score"])
        self.assertEqual("FORBIDDEN", self.config["pressure_policy"]["pressure_score"])
        for field in ("snapshot_count", "price_change_count", "line_change_count", "provider_breadth", "direction_agreement", "minutes_to_kickoff"):
            self.assertIn(field, self.config["heat_policy"]["components"])

    def test_trap_risk_is_an_evidence_profile_not_intent(self):
        policy = self.config["risk_interpretation_policy"]
        self.assertEqual("FORBIDDEN", policy["trap_risk_score"])
        self.assertEqual("FORBIDDEN", policy["bookmaker_intent"])
        self.assertEqual("FORBIDDEN", policy["certain_trap"])
        self.assertIn("Market Anomaly / Trap-Risk Evidence Profile", self.risk_contract)
        self.assertIn("BOOKMAKER_INTENT_CONFIRMED", self.risk_contract)
        self.assertIn("CERTAIN_TRAP", self.risk_contract)

    def test_threshold_dependent_flags_are_disabled_until_governed(self):
        disabled = self.config["risk_interpretation_policy"]["disabled_until_explicit_threshold"]
        for flag in ("LINE_PRICE_DISLOCATION", "RAPID_MOVEMENT", "MULTI_PROVIDER_DIRECTION_CONCENTRATION", "LATE_MOVEMENT"):
            self.assertIn(flag, disabled)
        self.assertIn("arbitrary thresholds", self.decision.casefold())

    def test_feature_quality_is_not_prediction_confidence(self):
        self.assertEqual(["coverage", "verification", "freshness", "completeness", "conflict", "provenance"], self.config["quality_policy"]["dimensions"])
        self.assertEqual("FORBIDDEN", self.config["quality_policy"]["prediction_confidence"])
        self.assertEqual("FORBIDDEN", self.config["quality_policy"]["betting_confidence"])
        self.assertIn("prediction confidence", self.feature_contract.casefold())

    def test_hash_and_append_only_boundaries_are_explicit(self):
        self.assertIn("input_hash", self.config["hash_policy"]["includes"])
        self.assertIn("output_hash", self.config["hash_policy"]["includes"])
        self.assertIn("provenance_hash", self.config["hash_policy"]["includes"])
        self.assertIn("new artifact identity", self.feature_contract)
        self.assertIn("supersedes_*", self.feature_contract)

    def test_independence_from_batch_11_and_batch_12_is_explicit(self):
        self.assertIn("independent-by-reference", self.decision)
        self.assertIn("BATCH-11 and BATCH-12 are sibling feature lines", self.decision)
        self.assertIn("SEPARATE_DIMENSIONS_ONLY", self.config["interaction_policy"]["default"])
        self.assertEqual([], self.config["interaction_policy"]["approved_rules"])

    def test_dependency_documents_agree_on_task_order(self):
        plan = (self.root / "docs/V4_BATCH_EXECUTION_PLAN.md").read_text(encoding="utf-8")
        register = (self.root / "docs/V4_TASK_DEPENDENCY_REGISTER.md").read_text(encoding="utf-8")
        graph = (self.root / "docs/V4_DEPENDENCY_GRAPH_012_100.md").read_text(encoding="utf-8")
        registry = (self.root / "docs/V4_TASK_REGISTRY_001_100.md").read_text(encoding="utf-8")
        for document in (plan, register, graph, registry):
            self.assertIn("V4-046", document)
            self.assertIn("V4-047", document)
            self.assertIn("V4-048", document)
            self.assertIn("V4-046 -> V4-047 -> V4-048", document)
        self.assertIn("V4-040 + V4-027 + V4-031", register)

    def test_no_v4_046_to_v4_048_implementation_is_present(self):
        paths = [path.as_posix() for path in (self.root / "tools").rglob("*") if path.is_file()]
        self.assertFalse(any(path.casefold().endswith(("v4_046.py", "v4_047.py", "v4_048.py")) for path in paths))
        self.assertIn("NOT IMPLEMENTED", self.decision)

    def test_f_drive_v3_and_no_write_boundaries(self):
        self.assertEqual("F:", self.root.drive.upper())
        self.assertIn("Production/Supabase", self.decision)
        self.assertIn("migration", self.decision.casefold())
        changed = subprocess.run(["git", "diff", "--name-only", "9407350..HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
