from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from src.prediction_training import (
    ENGINE_ROLES,
    PROFILE_ID,
    TRAINING_GATE_ID,
    evaluate_training_eligibility,
    load_ewp004_contract,
    load_training_gate,
    load_training_profile,
    validate_training_gate,
    validate_training_profile,
)


HASH = "sha256:" + "a" * 64
CONFIG = Path("F:/Projects/jcfb-v4/config/prediction_training")


def row(label: str, value: float) -> dict:
    return {"canonical_cell_label": label, "value": value, "resolution_status": "PARSED"}


def source_entry(artifact_type: str, payload: dict, ref: str) -> dict:
    if artifact_type in {"statistical_feature_artifact_ref", "football_intelligence_ref"}:
        payload = dict(payload, reconstruction_rule="AS_OF_TYPED_FEATURE_ARTIFACT", reconstruction_version="typed-feature-artifact@1.0.0", reconstruction_hash=HASH)
    return {"artifact_type": artifact_type, "artifact_domain": "pre_match", "record_ref": ref, "manifest_ref": f"manifests/{ref}.json", "artifact_hash": HASH, "provenance_hash": HASH, "source_availability_at": "2026-09-01T00:00:00+00:00", "payload": payload}


class TrainingEligibilityDecouplingTests(unittest.TestCase):
    def test_active_profile_is_versioned_and_old_ewp004_revision_remains_readable(self):
        profile = load_training_profile(CONFIG)
        gate = load_training_gate(CONFIG)
        self.assertEqual(PROFILE_ID, profile["profile_version"])
        self.assertEqual(TRAINING_GATE_ID, gate["gate_version"])
        self.assertEqual([], validate_training_profile(profile))
        self.assertEqual([], validate_training_gate(gate))
        old = load_ewp004_contract(CONFIG / "v4_batch15_ewp004_training_infrastructure_contract.json")
        self.assertEqual("b15-ewp004-training-infrastructure-contract@1.0.0", old["$id"])
        self.assertNotEqual(old["canonical_hash"], profile["profile_hash"])
        registry = json.loads((CONFIG / "v4_training_eligibility_profile_registry.json").read_text(encoding="utf-8"))
        canonical_hash = registry.pop("canonical_hash")
        from src.prediction_training_contract import sha256_json
        self.assertEqual(canonical_hash, sha256_json(registry))

    def test_required_minimums_have_no_tactical_numeric_requirement(self):
        profile = load_training_profile(CONFIG)
        for role in ENGINE_ROLES:
            required = profile["engine_profiles"][role]["required_features"]
            self.assertTrue(required)
            self.assertFalse(any(item["domain"] == "TACTICAL" for item in required))
            self.assertTrue(any(item["domain"] == "MARKET" for item in required))
        self.assertEqual("TOTAL_GOALS", next(item for item in profile["engine_profiles"]["GOALS"]["required_features"] if item["feature_id"] == "market_official_total_goals_0")["native_market_source"])
        self.assertEqual("HTFT", next(item for item in profile["engine_profiles"]["HTFT"]["required_features"] if item["feature_id"] == "market_official_htft_h_h")["native_market_source"])
        self.assertEqual("categorical_or_relational", profile["engine_profiles"]["OUTCOME"]["optional_features"][0]["type"])

    def test_outcome_uses_official_spf_and_optional_tactical_missing_is_masked(self):
        profile = load_training_profile(CONFIG)
        official = source_entry("official_odds_screenshot", {"SPF": [row("H", 2.1), row("D", 3.2), row("A", 3.4)]}, "official/outcome")
        market = source_entry("market_intelligence_ref", {"official_odds_record_ref": "official/outcome"}, "market/outcome")
        stat = source_entry("statistical_feature_artifact_ref", {"feature_values": {"statistical_strength_home": 1.2, "statistical_strength_away": 0.8}}, "stat/outcome")
        football = source_entry("football_intelligence_ref", {"feature_values": {"football_form_home": 0.6, "football_form_away": 0.4}}, "football/outcome")
        label = {"record_ref": "post/outcome", "manifest_ref": "manifests/post-outcome.json", "artifact_hash": HASH, "source_timestamp": "2026-09-01T03:00:00+00:00"}
        result = evaluate_training_eligibility("OUTCOME", profile, [official, market, stat, football], match_id="m1", cutoff_profile="S1", prediction_cutoff_at="2026-09-01T01:00:00+00:00", kickoff_at="2026-09-01T02:00:00+00:00", label=label)
        self.assertEqual("ELIGIBLE", result["eligibility_state"])
        self.assertEqual(2.1, result["feature_envelope"]["market_official_1x2_home"]["value"])
        self.assertEqual("UNKNOWN", result["availability_mask"]["tactical_context_overlay"])
        self.assertFalse(any("TACTICAL" in reason for reason in result["reasons"]))

    def test_goals_and_htft_use_native_vectors_and_missing_required_feature_fails_closed(self):
        profile = load_training_profile(CONFIG)
        official_payload = {"TOTAL_GOALS": [row(str(i), float(i + 1)) for i in range(7)] + [row("7+", 8.0)], "HTFT": [row(label, 1.0) for label in ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A")]}
        common = [source_entry("official_odds_screenshot", official_payload, "official/native"), source_entry("market_intelligence_ref", {"official_odds_record_ref": "official/native"}, "market/native")]
        stat = source_entry("statistical_feature_artifact_ref", {"feature_values": {"statistical_goals_rate_home": 1.1, "statistical_goals_rate_away": 0.9, "statistical_strength_home": 1.1, "statistical_strength_away": 0.9}}, "stat/native")
        football = source_entry("football_intelligence_ref", {"feature_values": {"football_goals_form_home": 0.7, "football_goals_form_away": 0.5, "football_first_half_form_home": 0.6, "football_first_half_form_away": 0.4}}, "football/native")
        label = {"record_ref": "post/native", "manifest_ref": "manifests/post-native.json", "artifact_hash": HASH, "source_timestamp": "2026-09-01T03:00:00+00:00"}
        goals = evaluate_training_eligibility("GOALS", profile, [*common, stat, football], match_id="m2", cutoff_profile="S1", prediction_cutoff_at="2026-09-01T01:00:00+00:00", kickoff_at="2026-09-01T02:00:00+00:00", label=label)
        self.assertEqual("ELIGIBLE", goals["eligibility_state"])
        self.assertEqual(8.0, goals["feature_envelope"]["market_official_total_goals_7_plus"]["value"])
        htft = evaluate_training_eligibility("HTFT", profile, [*common, stat, football], match_id="m3", cutoff_profile="S1", prediction_cutoff_at="2026-09-01T01:00:00+00:00", kickoff_at="2026-09-01T02:00:00+00:00", label=label)
        self.assertEqual("ELIGIBLE", htft["eligibility_state"])
        self.assertEqual(9, len([key for key in htft["feature_envelope"] if key.startswith("market_official_htft_")]))
        stat_missing = source_entry("statistical_feature_artifact_ref", {"feature_values": {"statistical_goals_rate_home": 1.1}}, "stat/missing")
        blocked = evaluate_training_eligibility("GOALS", profile, [*common, stat_missing, football], match_id="m4", cutoff_profile="S1", prediction_cutoff_at="2026-09-01T01:00:00+00:00", kickoff_at="2026-09-01T02:00:00+00:00", label=label)
        self.assertEqual("INELIGIBLE", blocked["eligibility_state"])
        self.assertIn("MISSING_REQUIRED_MINIMUM_FEATURE:statistical_goals_rate_away", blocked["reasons"])

    def test_future_source_is_rejected_without_imputation(self):
        profile = load_training_profile(CONFIG)
        official = source_entry("official_odds_screenshot", {"SPF": [row("H", 2.1), row("D", 3.2), row("A", 3.4)]}, "official/future")
        official["source_availability_at"] = "2026-09-01T03:00:00+00:00"
        market = source_entry("market_intelligence_ref", {"official_odds_record_ref": "official/future"}, "market/future")
        stat = source_entry("statistical_feature_artifact_ref", {"feature_values": {"statistical_strength_home": 1.2, "statistical_strength_away": 0.8}}, "stat/future")
        football = source_entry("football_intelligence_ref", {"feature_values": {"football_form_home": 0.6, "football_form_away": 0.4}}, "football/future")
        result = evaluate_training_eligibility("OUTCOME", profile, [official, market, stat, football], match_id="m5", cutoff_profile="S1", prediction_cutoff_at="2026-09-01T01:00:00+00:00", kickoff_at="2026-09-01T04:00:00+00:00", label=None)
        self.assertEqual("INELIGIBLE", result["eligibility_state"])
        self.assertIn("MARKET_SOURCE_AS_OF_BOUNDARY_FAILED", result["reasons"])
        self.assertEqual("AVAILABLE", result["availability_mask"]["market_official_1x2_home"])

    def test_static_decoupling_validator_passes(self):
        result = subprocess.run(["python", "scripts/validate_v4_training_eligibility_decoupling.py"], cwd=Path("F:/Projects/jcfb-v4"), capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("prediction_time_full_readiness=UNCHANGED", result.stdout)


if __name__ == "__main__":
    unittest.main()
