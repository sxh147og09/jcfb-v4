from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import CanonicalMatchIdentityStore, resolve_f_drive_output_path


class V4020CanonicalMatchIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        fixture_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        cls.fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))

    def base(self):
        return copy.deepcopy(self.fixtures["base"])

    def test_normal_identity_is_resolved(self):
        result = CanonicalMatchIdentityStore().ingest(self.base())
        self.assertTrue(result.accepted)
        self.assertEqual("ROOT_CREATED", result.resolution_action)
        self.assertEqual("AVAILABLE", result.status)
        self.assertRegex(result.canonical_match_id or "", r"^[0-9a-f-]{36}$")
        self.assertEqual("2026-09-04:001", result.business_key)
        self.assertEqual("RESOLVED", result.envelope.identity_resolution_state)

    def test_same_source_duplicate_is_stable_and_append_only(self):
        store = CanonicalMatchIdentityStore()
        first = store.ingest(self.base())
        second = store.ingest(self.base())
        self.assertEqual(first.canonical_match_id, second.canonical_match_id)
        self.assertEqual("DUPLICATE_NOOP", second.resolution_action)
        self.assertEqual(1, len(store.observations))
        self.assertEqual(["ROOT_CREATED", "DUPLICATE_NOOP"], [event["action"] for event in store.events])

    def test_cross_source_same_match_maps_to_existing_identity(self):
        store = CanonicalMatchIdentityStore()
        first = store.ingest(self.base())
        second = store.ingest(self.fixtures["second_source"])
        self.assertTrue(second.accepted)
        self.assertEqual("CROSS_SOURCE_ALIAS", second.resolution_action)
        self.assertEqual(first.canonical_match_id, second.canonical_match_id)
        self.assertEqual(first.business_key, second.business_key)
        self.assertEqual(2, len(store.observations))

    def test_identity_uuid_is_stable_across_independent_importers(self):
        first = CanonicalMatchIdentityStore().ingest(self.base())
        second = CanonicalMatchIdentityStore().ingest(self.base())
        self.assertEqual(first.canonical_match_id, second.canonical_match_id)

    def test_home_away_reversal_fails_closed_and_keeps_both_sources(self):
        store = CanonicalMatchIdentityStore()
        store.ingest(self.base())
        incoming = self.base()
        incoming.update({"source_reference": "ref://official/fixture/20260904/001-revised", "home_team_id": "team-away-002", "away_team_id": "team-home-001"})
        result = store.ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("BLOCKED", result.status)
        self.assertTrue(any(conflict.code == "HOME_AWAY_ORIENTATION_CONFLICT" for conflict in result.conflicts))
        self.assertEqual(2, len(store.observations))
        self.assertEqual("BLOCKED_CONFLICT", store.events[-1]["action"])

    def test_kickoff_conflict_fails_closed(self):
        store = CanonicalMatchIdentityStore()
        store.ingest(self.base())
        incoming = self.base()
        incoming.update({"source": "Provider B", "source_type": "EXTERNAL_FEED", "source_reference": "ref://provider-b/fixture/8842", "kickoff_at": "2026-09-04T20:05:00+08:00"})
        result = store.ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertTrue(any(conflict.code == "KICKOFF_CONFLICT" for conflict in result.conflicts))

    def test_timezone_identity_conflict_fails_closed(self):
        store = CanonicalMatchIdentityStore()
        store.ingest(self.base())
        incoming = self.base()
        incoming.update({"source": "Provider B", "source_type": "EXTERNAL_FEED", "source_reference": "ref://provider-b/fixture/8842", "timezone": "UTC", "kickoff_at": "2026-09-04T11:35:00Z"})
        result = store.ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertTrue(any(conflict.code == "TIMEZONE_CONFLICT" for conflict in result.conflicts))

    def test_cross_source_timezone_conflict_fails_closed(self):
        store = CanonicalMatchIdentityStore()
        store.ingest(self.base())
        incoming = copy.deepcopy(self.fixtures["second_source"])
        incoming["timezone"] = "UTC"
        incoming["kickoff_at"] = "2026-09-04T11:35:00Z"
        result = store.ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertTrue(any(conflict.code == "TIMEZONE_CONFLICT" for conflict in result.conflicts))

    def test_competition_conflict_fails_closed(self):
        store = CanonicalMatchIdentityStore()
        store.ingest(self.base())
        incoming = self.base()
        incoming.update({"source": "Provider B", "source_type": "EXTERNAL_FEED", "source_reference": "ref://provider-b/fixture/8842", "competition_id": "competition-other"})
        result = store.ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertTrue(any(conflict.code == "COMPETITION_ID_CONFLICT" for conflict in result.conflicts))

    def test_timezone_alias_is_normalized_and_offset_checked(self):
        incoming = self.base()
        incoming["timezone"] = "PRC"
        result = CanonicalMatchIdentityStore().ingest(incoming)
        self.assertTrue(result.accepted)
        self.assertEqual("Asia/Shanghai", result.envelope.timezone)

    def test_missing_official_and_source_match_ref_is_blocked(self):
        incoming = self.base()
        incoming.pop("official_match_no")
        incoming.pop("source_match_ref")
        result = CanonicalMatchIdentityStore().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_REFERENCE_REQUIRED", result.resolution_action)
        self.assertEqual("BLOCKED", result.status)

    def test_missing_source_reference_is_blocked(self):
        incoming = self.base()
        incoming.pop("source_reference")
        result = CanonicalMatchIdentityStore().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("SOURCE_REFERENCE_REQUIRED", result.resolution_action)

    def test_model_interpretation_fields_are_rejected(self):
        incoming = self.base()
        incoming["metadata"]["confidence"] = {"score": 0.99}
        result = CanonicalMatchIdentityStore().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.resolution_action)

    def test_v333_isolation(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.repo_root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        incoming = self.base()
        incoming["metadata"]["v333_reference"] = "forbidden"
        result = CanonicalMatchIdentityStore().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.resolution_action)

    def test_f_drive_runtime_and_output_path(self):
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-020/evidence.json")
        self.assertEqual("F:", output.drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "work/evidence.json")
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("F:/Projects/jcfb-v4", "../outside.json")


if __name__ == "__main__":
    unittest.main()
