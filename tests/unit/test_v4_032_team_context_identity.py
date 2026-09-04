from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    TeamContextIdentityLinker,
    TeamSide,
    resolve_f_drive_output_path,
)


class V4032TeamContextIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads(
            (cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8")
        )
        cls.fixture = json.loads(
            (cls.root / "tests/fixtures/v4_032/team_context_identity_cases.json").read_text(encoding="utf-8")
        )

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity_raw = copy.deepcopy(self.identity_fixture["base"])
        identity_raw["official_match_no"] = "001"
        identity = self.identity_store.ingest(identity_raw)
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.fixture["base"]["match_id"] = self.match_id
        self.fixture["away"]["match_id"] = self.match_id
        self.linker = TeamContextIdentityLinker(self.identity_store)

    def test_resolves_canonical_match_team_and_side(self):
        result = self.linker.ingest(copy.deepcopy(self.fixture["base"]))
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("AVAILABLE", result.status)
        self.assertEqual(self.match_id, result.link.match_id)
        self.assertEqual("team-home-001", result.link.team_id)
        self.assertEqual(TeamSide.HOME, result.link.side)
        self.assertEqual("AVAILABLE", result.link.status)
        self.assertNotEqual(result.link.mapping_hash, result.link.provenance_hash)

    def test_alias_without_stable_identity_can_resolve_only_to_canonical_name(self):
        raw = copy.deepcopy(self.fixture["base"])
        raw.pop("team_id")
        raw["team_alias"] = "Example Home"
        result = self.linker.ingest(raw)
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("team-home-001", result.link.team_id)

    def test_unresolved_alias_and_side_conflict_fail_closed(self):
        unresolved = copy.deepcopy(self.fixture["base"])
        unresolved.pop("team_id")
        unresolved["team_alias"] = "Unknown Home Alias"
        result = self.linker.ingest(unresolved)
        self.assertFalse(result.accepted)
        self.assertEqual("ALIAS_UNRESOLVED", result.error_code)

        wrong_side = copy.deepcopy(self.fixture["base"])
        wrong_side["side"] = "AWAY"
        result = self.linker.ingest(wrong_side)
        self.assertFalse(result.accepted)
        self.assertEqual("TEAM_ID_SIDE_CONFLICT", result.error_code)

    def test_missing_match_identity_and_source_time_fail_closed(self):
        missing_match = copy.deepcopy(self.fixture["base"])
        missing_match["match_id"] = "00000000-0000-5000-8000-000000000099"
        result = self.linker.ingest(missing_match)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)

        missing_time = copy.deepcopy(self.fixture["base"])
        missing_time.pop("source_timestamp")
        result = self.linker.ingest(missing_time)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_source_reference_conflict_is_retained_and_blocked(self):
        first = self.linker.ingest(copy.deepcopy(self.fixture["base"]))
        self.assertTrue(first.accepted)
        conflicting = copy.deepcopy(self.fixture["base"])
        conflicting.update({"team_id": "team-away-002", "side": "AWAY"})
        result = self.linker.ingest(conflicting)
        self.assertFalse(result.accepted)
        self.assertEqual("SOURCE_REFERENCE_IDENTITY_CONFLICT", result.error_code)
        self.assertEqual("team-home-001", result.conflicts[0].existing_value["team_id"])
        self.assertEqual("team-away-002", result.conflicts[0].incoming_value["team_id"])

    def test_revision_is_append_only_and_display_name_is_not_join_key(self):
        first = self.linker.ingest(copy.deepcopy(self.fixture["base"]))
        self.assertTrue(first.accepted)
        revised = copy.deepcopy(self.fixture["base"])
        revised.update(
            {
                "source_reference": "ref://context/20260904/001/home/identity-002",
                "provenance_ref": "ref://context/20260904/001/home/identity-002",
                "team_display_name": "A Different Display Label",
                "observed_at": "2026-09-04T09:10:00+08:00",
                "ingested_at": "2026-09-04T09:11:00+08:00",
                "effective_at": "2026-09-04T09:10:00+08:00",
            }
        )
        second = self.linker.ingest(revised)
        self.assertTrue(second.accepted, second.error_code)
        self.assertEqual(2, second.link.revision)
        self.assertEqual(first.link.object_id, second.link.supersedes_object_id)
        self.assertEqual(2, len(self.linker.links))
        self.assertEqual("team-home-001", second.link.team_id)
        self.assertFalse(second.link.metadata["display_name_join_key"])

    def test_model_fields_v333_and_non_f_drive_changes_are_rejected_or_absent(self):
        model_field = copy.deepcopy(self.fixture["base"])
        model_field["metadata"] = {"feature_bundle": "forbidden"}
        result = self.linker.ingest(model_field)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-032/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
