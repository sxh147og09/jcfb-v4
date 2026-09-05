from __future__ import annotations

import copy
import json
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    ExternalEuropean1X2Adapter,
    MarketIntelligenceEngine,
    MarketMovementEngine,
    MarketRiskInterpretationEngine,
    MarketRiskInterpretationStore,
)


class V4048MarketRiskInterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.external_fixture = json.loads((cls.root / "tests/fixtures/v4_028/external_european_1x2_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_048/market_risk_interpretation_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.market_engine = MarketIntelligenceEngine.from_repo_root(self.root, self.identity_store)
        self.movement_engine = MarketMovementEngine.from_repo_root(self.root)
        self.engine = MarketRiskInterpretationEngine.from_repo_root(self.root)

    def movement(self, timestamp: str, *, price_delta: float = 0.0, provider: str = "Example External Provider"):
        raw = copy.deepcopy(self.external_fixture)
        raw["match_id"] = self.match_id
        raw["source_timestamp"] = timestamp
        raw["captured_at"] = timestamp
        raw["observed_at"] = timestamp
        raw["ingested_at"] = timestamp
        raw["created_at"] = timestamp
        raw["provider"] = provider
        raw["source_ref"] = f"ref://external/{provider.replace(' ', '-').lower()}/{timestamp}"
        raw["prices"]["home"] += price_delta
        snapshot_result = ExternalEuropean1X2Adapter(self.identity_store).ingest(raw)
        self.assertTrue(snapshot_result.accepted, snapshot_result.error_code)
        return self.market_engine.normalize_snapshot(snapshot_result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]

    def price_movements(self, first_delta: float = 0.10, second_delta: float = 0.30):
        first = self.movement("2026-09-04T09:10:00+08:00")
        second = self.movement("2026-09-04T09:20:00+08:00", price_delta=first_delta)
        third = self.movement("2026-09-04T09:30:00+08:00", price_delta=second_delta)
        first_pair = self.movement_engine.compute_pair(first, second, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        second_pair = self.movement_engine.compute_pair(second, third, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        return [next(item for item in first_pair.artifacts if item.selection == "home"), next(item for item in second_pair.artifacts if item.selection == "home")]

    def test_heat_is_multidimensional_and_pressure_is_components(self):
        movements = self.price_movements()
        result = self.engine.interpret(movements, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted, result.error_code)
        raw = result.artifact.to_dict()
        self.assertEqual("PRE_FREEZE_MARKET_RISK_INTERPRETATION_ARTIFACT", raw["artifact_kind"])
        self.assertEqual(3, raw["heat_profile"]["snapshot_count"])
        self.assertIn("movement_velocity", raw["heat_profile"])
        self.assertIn("line_change_presence", raw["pressure_profile"])
        self.assertIn("reversal_presence", raw["pressure_profile"])
        self.assertNotIn("heat_score", json.dumps(raw).casefold())
        self.assertNotIn("pressure_score", json.dumps(raw).casefold())

    def test_direction_reversal_creates_evidence_flag_only(self):
        movements = self.price_movements(first_delta=0.20, second_delta=0.05)
        result = self.engine.interpret(movements, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        flags = result.artifact.anomaly_profile["flags"]
        self.assertTrue(any(item["flag"] == "DIRECTION_REVERSAL" for item in flags))
        reversal = next(item for item in flags if item["flag"] == "DIRECTION_REVERSAL")
        self.assertIn("predicate", reversal)
        self.assertIn("movement_refs", reversal)
        self.assertNotIn("trap_risk_score", json.dumps(result.artifact.to_dict()).casefold())

    def test_provider_dispersion_is_descriptive(self):
        first = self.movement("2026-09-04T09:10:00+08:00", provider="Provider A")
        second = self.movement("2026-09-04T09:10:01+08:00", provider="Provider B", price_delta=0.20)
        aggregate = self.movement_engine.aggregate_providers([first, second], self.fixture["cutoff_at"], self.fixture["kickoff_at"], selection="home")
        result = self.engine.interpret([aggregate.artifacts[0]], self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        self.assertTrue(any(item["flag"] == "PROVIDER_DISPERSION" for item in result.artifact.anomaly_profile["flags"]))

    def test_disabled_threshold_flags_are_not_emitted(self):
        result = self.engine.interpret(self.price_movements(), self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        raw = json.dumps(result.artifact.to_dict()).casefold()
        for flag in ("line_price_dislocation", "rapid_movement", "multi_provider_direction_concentration", "late_movement"):
            self.assertNotIn(f'"flag": "{flag}"', raw)
        self.assertEqual(tuple(sorted(["LINE_PRICE_DISLOCATION", "RAPID_MOVEMENT", "MULTI_PROVIDER_DIRECTION_CONCENTRATION", "LATE_MOVEMENT"])), result.artifact.anomaly_profile["disabled_threshold_flags"])

    def test_stale_and_conflicted_states_are_preserved(self):
        movement = self.price_movements()[0]
        stale = replace(movement, state="STALE")
        conflicted = replace(movement, state="CONFLICTED")
        stale_result = self.engine.interpret([stale], self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(stale_result.accepted)
        self.assertTrue(any(item["flag"] == "STALE_MARKET" for item in stale_result.artifact.anomaly_profile["flags"]))
        conflict_result = self.engine.interpret([conflicted], self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(conflict_result.accepted)
        self.assertEqual("CONFLICTED", conflict_result.artifact.interpretation_state)
        self.assertTrue(any(item["flag"] == "CONFLICTED_MARKET" for item in conflict_result.artifact.anomaly_profile["flags"]))

    def test_cutoff_and_upstream_contract_boundaries_fail_closed(self):
        movement = self.price_movements()[0]
        future = replace(movement, source_time_after="2026-09-04T09:50:00+08:00")
        future_result = self.engine.interpret([future], self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertFalse(future_result.accepted)
        self.assertEqual("POST_CUTOFF_INPUT", future_result.error_code)
        foreign = replace(movement, contract_version="market-movement@9.0.0")
        foreign_result = self.engine.interpret([foreign], self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertFalse(foreign_result.accepted)
        self.assertEqual("MOVEMENT_CONTRACT_INVALID", foreign_result.error_code)

    def test_append_only_profile_store_and_model_boundaries(self):
        result = self.engine.interpret(self.price_movements(), self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        store = MarketRiskInterpretationStore()
        self.assertEqual("APPEND", store.append(result.artifact))
        self.assertEqual("DUPLICATE_NOOP", store.append(result.artifact))
        raw = json.dumps(result.artifact.to_dict()).casefold()
        for forbidden in ("recommendation", "bookmaker_intent_confirmed", "certain_trap", "heat_score", "pressure_score", "trap_risk_score"):
            self.assertNotIn(forbidden, raw)

    def test_f_drive_and_v3_isolation(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
