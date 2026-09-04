from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    ExternalEuropean1X2Adapter,
    ExternalMarketStatus,
    resolve_f_drive_output_path,
)


class V4028ExternalEuropean1X2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.fixture = json.loads((root / "tests/fixtures/v4_028/external_european_1x2_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.store = ExternalEuropean1X2Adapter(self.identity_store)

    def base(self):
        raw = copy.deepcopy(self.fixture["base"])
        raw["match_id"] = self.match_id
        return raw

    def test_available_european_1x2_is_typed_external_snapshot(self):
        result = self.store.ingest(self.base())
        self.assertTrue(result.accepted)
        self.assertEqual("APPENDED", result.action)
        snapshot = result.snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual("external-market-snapshot@1.0.0", snapshot.contract_version)
        self.assertEqual("EUROPEAN_1X2", snapshot.market.value)
        self.assertEqual("NOT_APPLICABLE", snapshot.line)
        self.assertFalse(snapshot.source_is_official)
        self.assertEqual(ExternalMarketStatus.AVAILABLE, snapshot.availability_status)
        self.assertTrue(snapshot.payload_hash.startswith("sha256:"))
        self.assertTrue(snapshot.provenance_hash.startswith("sha256:"))

    def test_duplicate_is_append_only_noop(self):
        first = self.store.ingest(self.base())
        second = self.store.ingest(self.base())
        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual("DUPLICATE_NOOP", second.action)
        self.assertEqual(1, len(self.store.snapshots))

    def test_missing_canonical_match_identity_blocks_without_orphan(self):
        raw = self.base()
        raw["match_id"] = "00000000-0000-5000-8000-000000000999"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)
        self.assertEqual(0, len(self.store.snapshots))

    def test_official_source_cannot_enter_external_adapter(self):
        raw = self.base()
        raw["source_is_official"] = True
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("EXTERNAL_SOURCE_REQUIRED", result.error_code)

    def test_empty_or_malformed_prices_fail_closed(self):
        raw = self.base()
        raw["prices"] = {}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PRICES_EMPTY", result.error_code)

        raw = self.base()
        raw["prices"]["home"] = "2.11"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PRICE_VALUE_INVALID", result.error_code)

    def test_external_official_and_model_fields_are_rejected(self):
        raw = self.base()
        raw["rqspf"] = {"home": 2.0}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("OFFICIAL_FIELD_FORBIDDEN", result.error_code)

        raw = self.base()
        raw["metadata"]["prediction"] = "home"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_v333_migration_and_f_drive_boundaries_pass(self):
        root = Path(__file__).resolve().parents[2]
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-028/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
