from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    LineupCoachTacticalStore,
    TeamContextIdentityLinker,
    resolve_f_drive_output_path,
)


class V4034LineupContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.link = json.loads((cls.root / "tests/fixtures/v4_032/team_context_identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_034/lineup_context_cases.json").read_text(encoding="utf-8"))["base"]

    def setUp(self):
        identity_store = CanonicalMatchIdentityStore()
        identity = identity_store.ingest(copy.deepcopy(self.identity))
        self.match_id = identity.canonical_match_id
        self.link["match_id"] = self.match_id
        self.fixture["match_id"] = self.match_id
        linker = TeamContextIdentityLinker(identity_store)
        self.assertTrue(linker.ingest(copy.deepcopy(self.link)).accepted)
        self.store = LineupCoachTacticalStore(linker)

    def test_projected_lineup_and_attributed_context_are_preserved(self):
        result = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("PROJECTED", result.record.lineup_status.state)
        self.assertEqual("PROJECTED", result.record.starting_xi.state)
        self.assertEqual(("player-001", "player-002"), result.record.starting_xi.players)
        self.assertEqual("AVAILABLE", result.record.coach.state)
        self.assertEqual("NOT_VERIFIED", result.record.motivation.state)
        self.assertTrue(result.record.context_hash.startswith("sha256:"))

    def test_projected_cannot_be_confirmed_and_unknown_xi_has_no_players(self):
        promoted = copy.deepcopy(self.fixture)
        promoted["source_reference"] = "ref://lineup/promoted"
        promoted["lineup_status"] = {"state": "PROJECTED", "value": "CONFIRMED", "basis_refs": ["evidence://bad"]}
        result = self.store.ingest(promoted)
        self.assertFalse(result.accepted)
        self.assertEqual("LINEUP_STATUS_COERCION", result.error_code)

        unknown = copy.deepcopy(self.fixture)
        unknown["source_reference"] = "ref://lineup/unknown"
        unknown["lineup_status"] = {"state": "UNKNOWN", "basis_refs": [], "reason": "No defensible lineup"}
        unknown["starting_xi"] = {"state": "UNKNOWN", "players": [], "basis_refs": [], "reason": "No defensible lineup"}
        result = self.store.ingest(unknown)
        self.assertFalse(result.accepted)
        self.assertEqual("STARTING_XI_PLAYERS_FORBIDDEN", result.error_code)

    def test_confirmed_requires_players_basis_and_state_alignment(self):
        no_players = copy.deepcopy(self.fixture)
        no_players["source_reference"] = "ref://lineup/no-players"
        no_players["lineup_status"] = {"state": "CONFIRMED", "value": "CONFIRMED", "basis_refs": ["evidence://confirmed"]}
        no_players["starting_xi"] = {"state": "CONFIRMED", "basis_refs": ["evidence://confirmed"]}
        result = self.store.ingest(no_players)
        self.assertFalse(result.accepted)
        self.assertEqual("STARTING_XI_PLAYERS_REQUIRED", result.error_code)

        mismatch = copy.deepcopy(self.fixture)
        mismatch["source_reference"] = "ref://lineup/mismatch"
        mismatch["lineup_status"] = {"state": "UNKNOWN", "basis_refs": [], "reason": "Unknown"}
        mismatch["starting_xi"] = {"state": "PROJECTED", "players": ["player-001"], "basis_refs": ["evidence://projected"]}
        result = self.store.ingest(mismatch)
        self.assertFalse(result.accepted)
        self.assertEqual("LINEUP_STATE_CONFLICT", result.error_code)

    def test_rumor_and_post_match_confirmation_fail_closed(self):
        rumor = copy.deepcopy(self.fixture)
        rumor["source_reference"] = "ref://lineup/rumor"
        rumor["lineup_status"] = {"state": "NOT_VERIFIED", "basis_refs": ["evidence://rumor"], "reason": "Rumor only"}
        rumor["starting_xi"] = {"state": "NOT_VERIFIED", "basis_refs": ["evidence://rumor"], "reason": "Rumor only"}
        result = self.store.ingest(rumor)
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("NOT_VERIFIED", result.record.starting_xi.state)

        post = copy.deepcopy(self.fixture)
        post["source_reference"] = "ref://lineup/post-match"
        post["source_timestamp"] = "2026-09-04T20:00:00+08:00"
        post["observed_at"] = "2026-09-04T20:01:00+08:00"
        post["ingested_at"] = "2026-09-04T20:02:00+08:00"
        post["effective_at"] = "2026-09-04T20:00:00+08:00"
        result = self.store.ingest(post)
        self.assertFalse(result.accepted)
        self.assertEqual("POST_CUTOFF_CONTEXT", result.error_code)

    def test_identity_link_is_required_and_append_only(self):
        first = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(first.accepted)
        revised = copy.deepcopy(self.fixture)
        revised.update({"source_reference": "ref://lineup/002", "provenance_ref": "ref://lineup/002", "observed_at": "2026-09-04T09:10:00+08:00", "ingested_at": "2026-09-04T09:11:00+08:00", "effective_at": "2026-09-04T09:10:00+08:00"})
        second = self.store.ingest(revised)
        self.assertTrue(second.accepted, second.error_code)
        self.assertEqual(2, second.record.revision)
        self.assertEqual(first.record.object_id, second.record.supersedes_object_id)

    def test_no_feature_prediction_or_v333_and_f_drive_boundary(self):
        forbidden = copy.deepcopy(self.fixture)
        forbidden["tactical_style"]["value"] = {"feature": "high-press"}
        result = self.store.ingest(forbidden)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-034/evidence.json").drive.upper())


if __name__ == "__main__":
    unittest.main()
