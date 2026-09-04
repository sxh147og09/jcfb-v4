from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    OperationalContextStore,
    TeamContextIdentityLinker,
    resolve_f_drive_output_path,
)


class V4035OperationalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.link = json.loads((cls.root / "tests/fixtures/v4_032/team_context_identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_035/operational_context_cases.json").read_text(encoding="utf-8"))["base"]

    def setUp(self):
        identity_store = CanonicalMatchIdentityStore()
        identity = identity_store.ingest(copy.deepcopy(self.identity))
        self.match_id = identity.canonical_match_id
        self.link["match_id"] = self.match_id
        self.fixture["match_id"] = self.match_id
        linker = TeamContextIdentityLinker(identity_store)
        self.assertTrue(linker.ingest(copy.deepcopy(self.link)).accepted)
        self.store = OperationalContextStore(linker)

    def test_each_operational_field_retains_source_time_expiry_and_hash(self):
        result = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(result.accepted, result.error_code)
        record = result.record
        self.assertEqual("AVAILABLE", record.schedule_pressure.state)
        self.assertEqual("UNKNOWN", record.fatigue.state)
        self.assertEqual("UNAVAILABLE", record.weather.state)
        self.assertEqual("NOT_VERIFIED", record.pitch.state)
        for name in ("schedule_pressure", "fatigue", "travel", "weather", "pitch"):
            item = getattr(record, name)
            self.assertTrue(item.source)
            self.assertTrue(item.source_reference)
            self.assertTrue(item.source_timestamp)
            self.assertTrue(item.retrieved_at)
            self.assertTrue(item.effective_at)
            self.assertTrue(item.expires_at)
            self.assertTrue(item.provenance_ref)
            self.assertTrue(item.payload_hash.startswith("sha256:"))
        self.assertTrue(record.payload_hash.startswith("sha256:"))
        self.assertTrue(record.context_hash.startswith("sha256:"))

    def test_available_empty_and_missing_source_or_expiry_fail_closed(self):
        empty = copy.deepcopy(self.fixture)
        empty["schedule_pressure"]["payload"] = {}
        result = self.store.ingest(empty)
        self.assertFalse(result.accepted)
        self.assertEqual("AVAILABLE_PAYLOAD_REQUIRED", result.error_code)

        missing_source = copy.deepcopy(self.fixture)
        missing_source["weather"].pop("source")
        result = self.store.ingest(missing_source)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

        missing_expiry = copy.deepcopy(self.fixture)
        missing_expiry["pitch"].pop("expires_at")
        result = self.store.ingest(missing_expiry)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_unknown_unavailable_are_not_filled_and_future_or_post_cutoff_blocks(self):
        unknown = copy.deepcopy(self.fixture)
        unknown["travel"]["state"] = "UNKNOWN"
        unknown["travel"].pop("payload", None)
        unknown["travel"]["basis_refs"] = []
        unknown["travel"]["reason"] = "No travel source"
        result = self.store.ingest(unknown)
        self.assertTrue(result.accepted, result.error_code)
        self.assertIsNone(result.record.travel.payload)

        future = copy.deepcopy(self.fixture)
        future["pitch"]["state"] = "FUTURE_DATA"
        future["pitch"]["reason"] = "Published after cutoff"
        future["pitch"]["source_reference"] = "ref://pitch/future"
        result = self.store.ingest(future)
        self.assertFalse(result.accepted)
        self.assertEqual("FUTURE_DATA_NOT_ELIGIBLE", result.error_code)

        post = copy.deepcopy(self.fixture)
        post["weather"]["source_reference"] = "ref://weather/post-cutoff"
        post["weather"]["retrieved_at"] = "2026-09-04T18:01:00+08:00"
        result = self.store.ingest(post)
        self.assertFalse(result.accepted)
        self.assertEqual("POST_CUTOFF_CONTEXT", result.error_code)

    def test_identity_link_required_and_corrections_are_append_only(self):
        first = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(first.accepted)
        revised = copy.deepcopy(self.fixture)
        revised["provenance_ref"] = "ref://operational/002"
        revised["ingested_at"] = "2026-09-04T09:11:00+08:00"
        revised["schedule_pressure"]["source_reference"] = "ref://schedule/002"
        second = self.store.ingest(revised)
        self.assertTrue(second.accepted, second.error_code)
        self.assertEqual(2, second.record.revision)
        self.assertEqual(first.record.object_id, second.record.supersedes_object_id)
        self.assertEqual(2, len(self.store.records))

    def test_no_feature_market_intelligence_v333_and_f_drive_boundary(self):
        forbidden = copy.deepcopy(self.fixture)
        forbidden["travel"]["payload"]["feature"] = "long-haul"
        result = self.store.ingest(forbidden)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-035/evidence.json").drive.upper())


if __name__ == "__main__":
    unittest.main()
