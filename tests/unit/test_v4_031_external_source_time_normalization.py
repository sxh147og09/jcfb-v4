from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    ExternalAsianHandicapAdapter,
    ExternalEuropean1X2Adapter,
    ExternalOUAdapter,
    ExternalSourceTimeNormalizer,
    resolve_f_drive_output_path,
)


class V4031ExternalSourceTimeNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.root = root
        cls.identity_fixture = json.loads((root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.one_x_two = json.loads((root / "tests/fixtures/v4_028/external_european_1x2_cases.json").read_text(encoding="utf-8"))["base"]
        cls.handicap = json.loads((root / "tests/fixtures/v4_029/external_asian_handicap_cases.json").read_text(encoding="utf-8"))["base"]
        cls.over_under = json.loads((root / "tests/fixtures/v4_030/external_over_under_cases.json").read_text(encoding="utf-8"))["base"]

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)

    def ingest(self, raw, adapter):
        incoming = copy.deepcopy(raw)
        incoming["match_id"] = self.match_id
        result = adapter.ingest(incoming)
        self.assertTrue(result.accepted, result.error_code)
        return result.snapshot

    def test_normalization_preserves_original_refs_times_and_provenance(self):
        snapshots = [
            self.ingest(self.one_x_two, ExternalEuropean1X2Adapter(self.identity_store)),
            self.ingest(self.handicap, ExternalAsianHandicapAdapter(self.identity_store)),
            self.ingest(self.over_under, ExternalOUAdapter(self.identity_store)),
        ]
        result = ExternalSourceTimeNormalizer().normalize(snapshots)
        self.assertTrue(result.accepted)
        normalized = result.normalization
        self.assertIsNotNone(normalized)
        self.assertEqual(3, len(normalized.entries))
        self.assertEqual({item.snapshot_id for item in snapshots}, set(normalized.original_snapshot_ids))
        self.assertEqual({item.snapshot_id for item in snapshots}, {entry.snapshot_id for entry in normalized.entries})
        self.assertEqual(3, len({entry.normalization_key for entry in normalized.entries}))
        for entry in normalized.entries:
            original = next(item for item in snapshots if item.snapshot_id == entry.snapshot_id)
            self.assertEqual(original.snapshot_hash, entry.snapshot_hash)
            self.assertEqual(original.provenance_hash, entry.provenance_hash)
            self.assertEqual(original.source_ref, entry.source_ref)
            self.assertEqual(original.source_timestamp, entry.source_timestamp)
            self.assertEqual(original.captured_at, entry.captured_at)
            self.assertEqual(original.observed_at, entry.observed_at)
            self.assertEqual(original.ingested_at, entry.ingested_at)

    def test_known_source_time_order_is_deterministic(self):
        first = self.ingest(self.one_x_two, ExternalEuropean1X2Adapter(self.identity_store))
        later_raw = copy.deepcopy(self.over_under)
        later_raw["source_timestamp"] = "2026-09-04T09:40:30+08:00"
        later_raw["captured_at"] = "2026-09-04T09:40:30+08:00"
        later_raw["observed_at"] = "2026-09-04T09:40:31+08:00"
        later_raw["ingested_at"] = "2026-09-04T09:40:32+08:00"
        later = self.ingest(later_raw, ExternalOUAdapter(self.identity_store))
        result = ExternalSourceTimeNormalizer().normalize([later, first])
        self.assertTrue(result.accepted)
        self.assertEqual([first.snapshot_id, later.snapshot_id], list(result.normalization.source_time_order))

    def test_unknown_source_time_is_blocked_and_not_coerced(self):
        known = self.ingest(self.one_x_two, ExternalEuropean1X2Adapter(self.identity_store))
        unknown_raw = copy.deepcopy(self.one_x_two)
        unknown_raw.update({
            "source_ref": "ref://external/example/20260904/001/1x2-unknown-time",
            "source_timestamp": "UNKNOWN",
            "availability_status": "UNKNOWN",
            "reason_code": "SOURCE_TIME_UNKNOWN",
        })
        unknown = self.ingest(unknown_raw, ExternalEuropean1X2Adapter(self.identity_store))
        result = ExternalSourceTimeNormalizer().normalize([known, unknown])
        self.assertFalse(result.accepted)
        self.assertEqual("BLOCKED_SOURCE_TIME", result.action)
        self.assertEqual("SOURCE_TIME_UNKNOWN", result.error_code)
        self.assertEqual("UNKNOWN", result.normalization.entries[-1].source_timestamp)
        self.assertEqual("UNKNOWN", result.normalization.entries[-1].source_time_basis)
        self.assertEqual(2, len(result.normalization.original_snapshot_ids))

    def test_non_available_snapshot_is_blocked_for_movement_ready_set(self):
        raw = copy.deepcopy(self.one_x_two)
        raw.update({
            "source_ref": "ref://external/example/20260904/001/1x2-future",
            "availability_status": "FUTURE_DATA",
            "reason_code": "FUTURE_INFORMATION_LEAKAGE",
            "prices": None,
        })
        future = self.ingest(raw, ExternalEuropean1X2Adapter(self.identity_store))
        result = ExternalSourceTimeNormalizer().normalize([future])
        self.assertFalse(result.accepted)
        self.assertEqual("SNAPSHOT_NOT_AVAILABLE", result.error_code)
        self.assertEqual("FUTURE_DATA", result.normalization.entries[0].availability_status)
        self.assertEqual("FUTURE_INFORMATION_LEAKAGE", result.normalization.entries[0].reason_code)

    def test_mixed_match_ids_and_duplicate_refs_fail_closed(self):
        first = self.ingest(self.one_x_two, ExternalEuropean1X2Adapter(self.identity_store))
        duplicate = ExternalSourceTimeNormalizer().normalize([first, first])
        self.assertFalse(duplicate.accepted)
        self.assertEqual("DUPLICATE_SNAPSHOT_REF", duplicate.error_code)

        other_identity = copy.deepcopy(self.identity_fixture["base"])
        other_identity.update({"official_match_no": "002", "source_match_ref": "csl-20260904-002", "home_team_id": "team-home-003", "away_team_id": "team-away-004"})
        other_store = CanonicalMatchIdentityStore()
        other_match = other_store.ingest(other_identity).canonical_match_id
        other_raw = copy.deepcopy(self.handicap)
        other_raw["match_id"] = other_match
        second_result = ExternalAsianHandicapAdapter(other_store).ingest(other_raw)
        self.assertTrue(second_result.accepted)
        mixed = ExternalSourceTimeNormalizer().normalize([first, second_result.snapshot])
        self.assertFalse(mixed.accepted)
        self.assertEqual("MATCH_SCOPE_CONFLICT", mixed.error_code)

    def test_no_synthetic_snapshot_and_v333_f_drive_audit(self):
        snapshot = self.ingest(self.over_under, ExternalOUAdapter(self.identity_store))
        result = ExternalSourceTimeNormalizer().normalize([snapshot])
        self.assertTrue(result.accepted)
        self.assertEqual([snapshot.snapshot_id], list(result.normalization.original_snapshot_ids))
        self.assertEqual(snapshot.snapshot_id, result.normalization.entries[0].snapshot_id)
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-031/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
