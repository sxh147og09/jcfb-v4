from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import CanonicalMatchIdentityStore, ExternalAsianHandicapAdapter, ExternalMarketStatus, resolve_f_drive_output_path


class V4029ExternalAsianHandicapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.root = root
        cls.identity_fixture = json.loads((root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.fixture = json.loads((root / "tests/fixtures/v4_029/external_asian_handicap_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.store = ExternalAsianHandicapAdapter(self.identity_store)

    def base(self):
        raw = copy.deepcopy(self.fixture["base"])
        raw["match_id"] = self.match_id
        return raw

    def test_available_handicap_preserves_exact_line_and_prices(self):
        result = self.store.ingest(self.base())
        self.assertTrue(result.accepted)
        self.assertEqual("ASIAN_HANDICAP", result.snapshot.market.value)
        self.assertEqual(-1.0, result.snapshot.line)
        self.assertEqual({"home": 1.92, "away": 1.94}, dict(result.snapshot.prices))
        self.assertFalse(result.snapshot.source_is_official)

    def test_line_is_typed_and_default_line_is_rejected(self):
        raw = self.base()
        raw["line"] = "-1.0"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("LINE_REQUIRED", result.error_code)

        raw = self.base()
        raw.pop("line")
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("LINE_REQUIRED", result.error_code)

    def test_all_non_available_states_require_explicit_reason(self):
        for status in ("UNKNOWN", "UNAVAILABLE", "STALE", "FUTURE_DATA", "BLOCKED"):
            raw = self.base()
            raw["availability_status"] = status
            raw["reason_code"] = f"{status}_EXPLICIT"
            raw["line"] = "UNKNOWN"
            raw["prices"] = None
            result = self.store.ingest(raw)
            self.assertTrue(result.accepted, (status, result.error_code))
            self.assertEqual(ExternalMarketStatus(status), result.snapshot.availability_status)
            self.assertEqual(f"{status}_EXPLICIT", result.snapshot.reason_code)

    def test_missing_reason_is_not_inferred_from_empty_prices(self):
        raw = self.base()
        raw.update({"availability_status": "UNAVAILABLE", "line": "UNKNOWN", "prices": None})
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_external_handicap_never_becomes_official_rqspf(self):
        raw = self.base()
        raw["rqspf"] = {"official_handicap": -1.0, "home": 1.9, "draw": 3.2, "away": 1.9}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("OFFICIAL_FIELD_FORBIDDEN", result.error_code)

    def test_correction_appends_and_preserves_predecessor(self):
        first = self.store.ingest(self.base())
        correction = self.base()
        correction.update({
            "snapshot_kind": "CORRECTION",
            "source_ref": "ref://external/asian/20260904/001/ah-correction",
            "captured_at": "2026-09-04T09:30:30+08:00",
            "observed_at": "2026-09-04T09:30:31+08:00",
            "ingested_at": "2026-09-04T09:30:32+08:00",
            "supersedes_snapshot_id": first.snapshot.snapshot_id,
            "revision_reason": "PROVIDER_CORRECTION"
        })
        correction["prices"]["home"] = 1.90
        second = self.store.ingest(correction)
        self.assertTrue(second.accepted)
        self.assertEqual(2, second.snapshot.revision)
        self.assertEqual(first.snapshot.snapshot_id, second.snapshot.supersedes_snapshot_id)
        self.assertIsNotNone(self.store.get(first.snapshot.snapshot_id))
        self.assertEqual(2, len(self.store.snapshots))

    def test_v333_migration_and_f_drive_boundaries_pass(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-029/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
