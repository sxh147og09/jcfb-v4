from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    AsianHandicapIntake,
    CanonicalMatchIdentityStore,
    ExternalEuropean1X2Adapter,
    MarketIntelligenceEngine,
    MarketMovementEngine,
    MarketMovementStore,
    OfficialOddsSnapshotStore,
)


class V4047MarketMovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.external_fixture = json.loads((cls.root / "tests/fixtures/v4_028/external_european_1x2_cases.json").read_text(encoding="utf-8"))["base"]
        cls.handicap_fixture = json.loads((cls.root / "tests/fixtures/v4_029/external_asian_handicap_cases.json").read_text(encoding="utf-8"))["base"]
        cls.official_fixture = json.loads((cls.root / "tests/fixtures/v4_024/official_odds_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_047/market_movement_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity_result = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity_result.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.market_engine = MarketIntelligenceEngine.from_repo_root(self.root, self.identity_store)
        self.engine = MarketMovementEngine.from_repo_root(self.root)

    def external_snapshot(self, source_timestamp: str, *, provider: str = "Example External Provider", price_delta: float = 0.0):
        raw = copy.deepcopy(self.external_fixture)
        raw["match_id"] = self.match_id
        raw["source_timestamp"] = source_timestamp
        raw["captured_at"] = source_timestamp
        raw["observed_at"] = source_timestamp
        raw["ingested_at"] = source_timestamp
        raw["created_at"] = source_timestamp
        raw["provider"] = provider
        raw["source_ref"] = f"ref://external/{provider.replace(' ', '-').lower()}/{source_timestamp}"
        raw["prices"]["home"] += price_delta
        result = ExternalEuropean1X2Adapter(self.identity_store).ingest(raw)
        self.assertTrue(result.accepted, result.error_code)
        return self.market_engine.normalize_snapshot(result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]

    def handicap_snapshot(self, source_timestamp: str, line: float):
        raw = copy.deepcopy(self.handicap_fixture)
        raw["match_id"] = self.match_id
        raw["source_timestamp"] = source_timestamp
        raw["captured_at"] = source_timestamp
        raw["observed_at"] = source_timestamp
        raw["ingested_at"] = source_timestamp
        raw["created_at"] = source_timestamp
        raw["line"] = line
        raw["source_ref"] = f"ref://external/handicap/{line}/{source_timestamp}"
        result = AsianHandicapIntake(self.identity_store).ingest(raw)
        self.assertTrue(result.accepted, result.error_code)
        return self.market_engine.normalize_snapshot(result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]

    def official_and_external_spf(self, source_timestamp: str):
        official_raw = copy.deepcopy(self.official_fixture)
        official_raw["match_id"] = self.match_id
        official_raw["source_timestamp"] = source_timestamp
        official_raw["captured_at"] = source_timestamp
        official_raw["observed_at"] = source_timestamp
        official_raw["ingested_at"] = source_timestamp
        official_raw["created_at"] = source_timestamp
        official_result = OfficialOddsSnapshotStore(self.identity_store).ingest(official_raw)
        self.assertTrue(official_result.accepted)
        official = self.market_engine.normalize_snapshot(official_result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        external = self.external_snapshot(source_timestamp)
        return official, external

    def test_price_movement_is_same_line_and_time_normalized(self):
        before = self.external_snapshot("2026-09-04T09:10:00+08:00")
        after = self.external_snapshot("2026-09-04T09:20:00+08:00", price_delta=0.10)
        result = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        home = next(item for item in result.artifacts if item.selection == "home")
        self.assertEqual("PRICE_MOVEMENT", home.movement_type)
        self.assertAlmostEqual(0.10, home.typed_value["value_delta"])
        self.assertAlmostEqual(0.6, home.typed_value["value_delta"] / home.elapsed_hours)
        self.assertEqual(2.11, home.price_before)
        self.assertEqual(2.21, home.price_after)

    def test_line_movement_is_separate_from_price_movement(self):
        before = self.handicap_snapshot("2026-09-04T09:10:00+08:00", -0.5)
        after = self.handicap_snapshot("2026-09-04T09:20:00+08:00", -0.75)
        line = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"], movement_type="LINE_MOVEMENT")
        self.assertTrue(line.accepted)
        self.assertEqual("LINE_MOVEMENT", line.artifacts[0].movement_type)
        self.assertEqual(-0.5, line.artifacts[0].line_before)
        self.assertEqual(-0.75, line.artifacts[0].line_after)
        price = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"], movement_type="PRICE_MOVEMENT")
        self.assertFalse(price.accepted)
        self.assertEqual("SEMANTIC_LINE_CONFLICT", price.error_code)

    def test_implied_probability_is_market_derived_not_prediction_probability(self):
        before = self.external_snapshot("2026-09-04T09:10:00+08:00")
        after = self.external_snapshot("2026-09-04T09:20:00+08:00", price_delta=0.10)
        result = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"], movement_type="IMPLIED_PROBABILITY_MOVEMENT")
        self.assertTrue(result.accepted)
        home = next(item for item in result.artifacts if item.selection == "home")
        self.assertEqual("probability_points", home.unit)
        self.assertNotIn("probability", home.to_dict())
        self.assertNotIn('"prediction":', json.dumps(home.to_dict()).casefold())
        self.assertNotEqual(home.price_before, home.typed_value["value_before"])

    def test_different_provider_cannot_form_one_series(self):
        before = self.external_snapshot("2026-09-04T09:10:00+08:00", provider="Provider A")
        after = self.external_snapshot("2026-09-04T09:20:00+08:00", provider="Provider B")
        result = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertFalse(result.accepted)
        self.assertEqual("SOURCE_SCOPE_CONFLICT", result.error_code)

    def test_future_and_non_consumable_inputs_fail_closed(self):
        future = self.external_snapshot("2026-09-04T09:50:00+08:00")
        current = self.external_snapshot("2026-09-04T09:20:00+08:00")
        result = self.engine.compute_pair(current, future, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertFalse(result.accepted)
        self.assertEqual("NON_CONSUMABLE_INPUT", result.error_code)

    def test_acceleration_requires_three_snapshots_and_is_deterministic(self):
        two = [self.external_snapshot("2026-09-04T09:10:00+08:00"), self.external_snapshot("2026-09-04T09:20:00+08:00", price_delta=0.10)]
        insufficient = self.engine.compute_acceleration(two, self.fixture["cutoff_at"], self.fixture["kickoff_at"], selection="home")
        self.assertTrue(insufficient.accepted)
        self.assertEqual("UNKNOWN", insufficient.artifacts[0].state)
        self.assertEqual("INSUFFICIENT_SERIES", insufficient.artifacts[0].reason_code)
        three = [
            self.external_snapshot("2026-09-04T09:10:00+08:00"),
            self.external_snapshot("2026-09-04T09:20:00+08:00", price_delta=0.10),
            self.external_snapshot("2026-09-04T09:30:00+08:00", price_delta=0.30),
        ]
        result = self.engine.compute_acceleration(three, self.fixture["cutoff_at"], self.fixture["kickoff_at"], selection="home")
        self.assertTrue(result.accepted)
        self.assertEqual("ACCELERATION", result.artifacts[0].movement_type)
        self.assertEqual(3, result.artifacts[0].typed_value["minimum_valid_snapshots"])

    def test_equal_eligible_provider_aggregate_retains_dispersion(self):
        items = [
            self.external_snapshot("2026-09-04T09:10:00+08:00", provider="Provider A"),
            self.external_snapshot("2026-09-04T09:10:01+08:00", provider="Provider B", price_delta=0.10),
        ]
        result = self.engine.aggregate_providers(items, self.fixture["cutoff_at"], self.fixture["kickoff_at"], selection="home")
        self.assertTrue(result.accepted)
        aggregate = result.artifacts[0]
        self.assertEqual("PROVIDER_AGGREGATE", aggregate.movement_type)
        self.assertEqual(2, aggregate.typed_value["eligible_provider_count"])
        self.assertEqual("EQUAL_ELIGIBLE_PROVIDER_CONTRIBUTION", aggregate.typed_value["aggregation_policy"])
        self.assertIn("iqr", aggregate.typed_value)
        self.assertIn("mad", aggregate.typed_value)

    def test_only_approved_official_external_divergence_is_numeric(self):
        official, external = self.official_and_external_spf("2026-09-04T09:10:00+08:00")
        result = self.engine.compare_official_external(official, external, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual(3, len(result.artifacts))
        self.assertTrue(all(item.movement_type == "OFFICIAL_EXTERNAL_DIVERGENCE" for item in result.artifacts))
        self.assertTrue(all(item.source_is_official is None for item in result.artifacts))

    def test_unapproved_cross_market_relation_is_structured_not_numeric(self):
        official_raw = copy.deepcopy(self.official_fixture)
        official_raw["match_id"] = self.match_id
        for field in ("source_timestamp", "captured_at", "observed_at", "ingested_at", "created_at"):
            official_raw[field] = "2026-09-04T09:10:00+08:00"
        official_result = OfficialOddsSnapshotStore(self.identity_store).ingest(official_raw)
        self.assertTrue(official_result.accepted)
        official = next(item for item in self.market_engine.normalize_snapshot(official_result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts if item.market == "RQSPF")
        external = self.handicap_snapshot("2026-09-04T09:10:00+08:00", -0.5)
        result = self.engine.compare_official_external(official, external, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        self.assertEqual("NOT_COMPARABLE", result.artifacts[0].state)
        self.assertIsNone(result.artifacts[0].typed_value.get("numeric_divergence"))

    def test_store_is_append_only(self):
        before = self.external_snapshot("2026-09-04T09:10:00+08:00")
        after = self.external_snapshot("2026-09-04T09:20:00+08:00", price_delta=0.10)
        artifact = self.engine.compute_pair(before, after, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        store = MarketMovementStore()
        self.assertEqual("APPEND", store.append(artifact))
        self.assertEqual("DUPLICATE_NOOP", store.append(artifact))
        self.assertEqual(1, len(store.artifacts))

    def test_f_drive_and_v3_isolation(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
