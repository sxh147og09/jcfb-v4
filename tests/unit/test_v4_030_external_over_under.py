from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import CanonicalMatchIdentityStore, ExternalMarketStatus, ExternalOUAdapter, resolve_f_drive_output_path


class V4030ExternalOverUnderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.root = root
        cls.identity_fixture = json.loads((root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.fixture = json.loads((root / "tests/fixtures/v4_030/external_over_under_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.store = ExternalOUAdapter(self.identity_store)

    def base(self):
        raw = copy.deepcopy(self.fixture["base"])
        raw["match_id"] = self.match_id
        return raw

    def test_available_over_under_preserves_goal_line_and_sides(self):
        result = self.store.ingest(self.base())
        self.assertTrue(result.accepted)
        self.assertEqual("OVER_UNDER", result.snapshot.market.value)
        self.assertEqual(2.5, result.snapshot.line)
        self.assertEqual({"over": 1.88, "under": 1.96}, dict(result.snapshot.prices))
        self.assertFalse(result.snapshot.source_is_official)

    def test_missing_or_default_goal_line_fails_closed(self):
        raw = self.base()
        raw.pop("line")
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("LINE_REQUIRED", result.error_code)

        raw = self.base()
        raw["line"] = "2.5"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("LINE_REQUIRED", result.error_code)

    def test_non_available_ou_is_explicit_and_not_available(self):
        raw = self.base()
        raw.update({"availability_status": "UNAVAILABLE", "reason_code": "MARKET_NOT_OFFERED", "line": "UNKNOWN", "prices": None})
        result = self.store.ingest(raw)
        self.assertTrue(result.accepted)
        self.assertEqual(ExternalMarketStatus.UNAVAILABLE, result.snapshot.availability_status)
        self.assertIsNone(result.snapshot.prices)
        self.assertEqual("MARKET_NOT_OFFERED", result.snapshot.reason_code)

    def test_available_empty_or_wrong_price_shape_is_rejected(self):
        raw = self.base()
        raw["prices"] = {}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PRICES_EMPTY", result.error_code)

        raw = self.base()
        raw["prices"] = {"home": 1.9, "away": 1.9}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PRICE_SHAPE_INVALID", result.error_code)

    def test_external_ou_cannot_populate_official_total_goals(self):
        raw = self.base()
        raw["total_goals"] = {"2": 3.0}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("OFFICIAL_FIELD_FORBIDDEN", result.error_code)

    def test_source_time_state_is_preserved_not_coerced_to_available(self):
        raw = self.base()
        raw.update({"source_timestamp": "UNKNOWN", "availability_status": "FUTURE_DATA", "reason_code": "SOURCE_TIME_NOT_ELIGIBLE"})
        result = self.store.ingest(raw)
        self.assertTrue(result.accepted)
        self.assertEqual("UNKNOWN", result.snapshot.source_timestamp)
        self.assertEqual(ExternalMarketStatus.FUTURE_DATA, result.snapshot.availability_status)

    def test_v333_migration_and_f_drive_boundaries_pass(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-030/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
