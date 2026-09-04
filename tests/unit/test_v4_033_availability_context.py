from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    AvailabilityContextStore,
    CanonicalMatchIdentityStore,
    TeamContextIdentityLinker,
    resolve_f_drive_output_path,
)


class V4033AvailabilityContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.link_fixture = json.loads((cls.root / "tests/fixtures/v4_032/team_context_identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_033/availability_cases.json").read_text(encoding="utf-8"))["base"]

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.link_fixture["match_id"] = self.match_id
        self.fixture["match_id"] = self.match_id
        linker = TeamContextIdentityLinker(self.identity_store)
        self.assertTrue(linker.ingest(copy.deepcopy(self.link_fixture)).accepted)
        self.store = AvailabilityContextStore(linker)

    def test_typed_collections_preserve_available_unknown_and_none_confirmed(self):
        result = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("AVAILABLE", result.record.injuries.state)
        self.assertEqual("NONE_CONFIRMED", result.record.suspensions.state)
        self.assertEqual((), result.record.suspensions.items)
        self.assertEqual("NOT_VERIFIED", result.record.availability.state)
        self.assertIsNone(result.record.availability.items)
        self.assertTrue(result.record.payload_hash.startswith("sha256:"))
        self.assertTrue(result.record.context_hash.startswith("sha256:"))

    def test_unknown_items_empty_array_and_none_confirmed_without_evidence_fail(self):
        unknown = copy.deepcopy(self.fixture)
        unknown["injuries"] = {"state": "UNKNOWN", "items": [], "reason": "No reliable source"}
        result = self.store.ingest(unknown)
        self.assertFalse(result.accepted)
        self.assertEqual("UNKNOWN_ITEMS_FORBIDDEN", result.error_code)

        none_without_evidence = copy.deepcopy(self.fixture)
        none_without_evidence["source_reference"] = "ref://availability/none-without-evidence"
        none_without_evidence["suspensions"] = {"state": "NONE_CONFIRMED", "items": [], "reason": "No report found"}
        result = self.store.ingest(none_without_evidence)
        self.assertFalse(result.accepted)
        self.assertEqual("NONE_CONFIRMED_EVIDENCE_REQUIRED", result.error_code)

    def test_not_verified_stale_future_and_conflict_states_remain_explicit(self):
        for state, reason, refs in [
            ("NOT_VERIFIED", "Report is not verified", ["evidence://report"]),
            ("FUTURE_DATA", "Published after cutoff", ["evidence://future"]),
            ("CONFLICTED", "Two claims disagree", ["evidence://a", "evidence://b"]),
        ]:
            raw = copy.deepcopy(self.fixture)
            raw["source_reference"] = f"ref://availability/state/{state}"
            raw["availability"] = {"state": state, "basis_refs": refs, "reason": reason}
            result = self.store.ingest(raw)
            if state == "FUTURE_DATA":
                self.assertFalse(result.accepted)
            else:
                self.assertTrue(result.accepted, result.error_code)
                self.assertEqual(state, result.record.availability.state)

        stale = copy.deepcopy(self.fixture)
        stale["source_reference"] = "ref://availability/state/STALE"
        stale["availability"] = {"state": "STALE", "basis_refs": ["evidence://stale"], "reason": "Expired", "items": [{"status": "OUT"}]}
        stale["expires_at"] = "2026-09-04T10:00:00+08:00"
        result = self.store.ingest(stale)
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("STALE", result.record.availability.state)

    def test_identity_link_and_cutoff_are_required(self):
        missing_link = AvailabilityContextStore(TeamContextIdentityLinker(self.identity_store))
        result = missing_link.ingest(copy.deepcopy(self.fixture))
        self.assertFalse(result.accepted)
        self.assertEqual("TEAM_CONTEXT_LINK_NOT_FOUND", result.error_code)

        after_cutoff = copy.deepcopy(self.fixture)
        after_cutoff["source_reference"] = "ref://availability/after-cutoff"
        after_cutoff["observed_at"] = "2026-09-04T18:01:00+08:00"
        after_cutoff["ingested_at"] = "2026-09-04T18:02:00+08:00"
        result = self.store.ingest(after_cutoff)
        self.assertFalse(result.accepted)
        self.assertEqual("POST_CUTOFF_CONTEXT", result.error_code)

    def test_append_only_revision_keeps_prior_record(self):
        first = self.store.ingest(copy.deepcopy(self.fixture))
        self.assertTrue(first.accepted)
        revised = copy.deepcopy(self.fixture)
        revised.update({
            "source_reference": "ref://availability/20260904/001/home/002",
            "provenance_ref": "ref://availability/20260904/001/home/002",
            "observed_at": "2026-09-04T09:10:00+08:00",
            "ingested_at": "2026-09-04T09:11:00+08:00",
            "effective_at": "2026-09-04T09:10:00+08:00",
        })
        second = self.store.ingest(revised)
        self.assertTrue(second.accepted, second.error_code)
        self.assertEqual(2, second.record.revision)
        self.assertEqual(first.record.object_id, second.record.supersedes_object_id)
        self.assertEqual(2, len(self.store.records))

    def test_model_fields_v333_and_f_drive_boundary(self):
        forbidden = copy.deepcopy(self.fixture)
        forbidden["injuries"]["items"][0]["prediction"] = "home"
        result = self.store.ingest(forbidden)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.replace("\\", "/").startswith("database/migrations/") for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-033/evidence.json").drive.upper())


if __name__ == "__main__":
    unittest.main()
