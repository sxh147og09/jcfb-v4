from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    OfficialOddsSnapshotStore,
    resolve_f_drive_output_path,
)


class V4024OfficialOddsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        odds_path = cls.repo_root / "tests/fixtures/v4_024/official_odds_cases.json"
        cls.identity_fixture = json.loads(identity_path.read_text(encoding="utf-8"))
        cls.odds_fixture = json.loads(odds_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.store = OfficialOddsSnapshotStore(self.identity_store)

    def base(self):
        raw = copy.deepcopy(self.odds_fixture["base"])
        raw["match_id"] = self.match_id
        return raw

    def test_valid_five_market_feed_snapshot_is_typed_and_hashed(self):
        result = self.store.ingest(self.base())
        self.assertTrue(result.accepted)
        self.assertEqual("APPENDED", result.action)
        snapshot = result.snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual("official-odds-snapshot@1.0.0", snapshot.contract_version)
        self.assertEqual(("spf", "rqspf", "total_goals", "exact_score", "half_full"), tuple(snapshot.payloads))
        self.assertTrue(snapshot.source_is_official)
        self.assertEqual(snapshot.snapshot_hash, snapshot.payload_hash)
        self.assertTrue(snapshot.provenance_hash.startswith("sha256:"))

    def test_duplicate_observation_is_noop(self):
        first = self.store.ingest(self.base())
        second = self.store.ingest(self.base())
        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual("DUPLICATE_NOOP", second.action)
        self.assertEqual(1, len(self.store.snapshots))

    def test_explicit_unavailable_market_has_reason_and_no_payload(self):
        raw = self.base()
        raw["rqspf"] = None
        raw["market_availability"]["rqspf"] = {"available": False, "status": "UNAVAILABLE", "reason": "OFFICIAL_MARKET_NOT_ON_SALE"}
        raw["market_unavailable_reason"]["rqspf"] = "OFFICIAL_MARKET_NOT_ON_SALE"
        result = self.store.ingest(raw)
        self.assertTrue(result.accepted)
        self.assertIsNone(result.snapshot.payloads["rqspf"])
        self.assertEqual("UNAVAILABLE", result.snapshot.market_availability["rqspf"]["status"])

    def test_external_source_is_rejected(self):
        raw = self.base()
        raw["source_type"] = "EXTERNAL_FEED"
        raw["source_is_official"] = False
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("OFFICIAL_SOURCE_TYPE_REQUIRED", result.error_code)

    def test_available_empty_payload_is_rejected(self):
        raw = self.base()
        raw["spf"] = {}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PAYLOAD_EMPTY", result.error_code)

    def test_non_available_payload_is_rejected(self):
        raw = self.base()
        raw["market_availability"]["spf"] = {"available": False, "status": "UNAVAILABLE", "reason": "OFFICIAL_MARKET_NOT_ON_SALE"}
        raw["market_unavailable_reason"]["spf"] = "OFFICIAL_MARKET_NOT_ON_SALE"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("UNAVAILABLE_PAYLOAD_FORBIDDEN", result.error_code)

    def test_exact_five_market_keys_are_required(self):
        raw = self.base()
        raw["market_availability"].pop("half_full")
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MARKET_SET_INVALID", result.error_code)

    def test_model_fields_are_rejected(self):
        raw = self.base()
        raw["spf"]["prediction"] = 0.5
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_hash_mismatch_fails_closed(self):
        raw = self.base()
        raw["snapshot_hash"] = "sha256:" + "0" * 64
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("HASH_MISMATCH", result.error_code)

    def test_missing_canonical_match_identity_blocks_without_orphan(self):
        raw = self.base()
        raw["match_id"] = "00000000-0000-5000-8000-000000000999"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)
        self.assertEqual(0, len(self.store.snapshots))

    def test_correction_appends_new_snapshot_and_preserves_predecessor(self):
        first = self.store.ingest(self.base())
        correction = self.base()
        correction["snapshot_kind"] = "CORRECTION"
        correction["source_reference"] = "ref://official/odds/20260904/001/correction-0905"
        correction["captured_at"] = "2026-09-04T09:05:30+08:00"
        correction["created_at"] = "2026-09-04T09:06:00+08:00"
        correction["supersedes_snapshot_id"] = first.snapshot.snapshot_id
        correction["revision_reason"] = "OFFICIAL_SOURCE_CORRECTION"
        correction["spf"]["home"] = 2.05
        second = self.store.ingest(correction)
        self.assertTrue(second.accepted)
        self.assertEqual(2, second.snapshot.revision)
        self.assertEqual(first.snapshot.snapshot_id, second.snapshot.supersedes_snapshot_id)
        self.assertIsNotNone(self.store.get(first.snapshot.snapshot_id))
        self.assertEqual(2, len(self.store.snapshots))

    def test_v333_f_drive_and_no_migration_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.repo_root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-024/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
