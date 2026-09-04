from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    EvidenceGraphStore,
    EvidenceGraphValidationError,
    VerificationState,
    resolve_f_drive_output_path,
)


class V4036EvidenceGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        identity = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        fixture = json.loads((cls.root / "tests/fixtures/v4_036/evidence_cases.json").read_text(encoding="utf-8"))
        cls.identity_fixture = identity
        cls.fixture = fixture

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture))
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id

    def evidence(self, name="base"):
        raw = copy.deepcopy(self.fixture[name])
        raw["entity_refs"]["match_id"] = self.match_id
        return raw

    def test_trusted_evidence_is_addressable_and_hashable(self):
        graph = EvidenceGraphStore(self.identity_store)
        result = graph.ingest(self.evidence())
        self.assertTrue(result.accepted, result.error_code)
        self.assertEqual("ROOT_CREATED", result.action)
        item = result.item
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual("evidence@1.0.0", item.to_dict()["contract_version"])
        self.assertEqual(VerificationState.VERIFIED, item.verification_state)
        self.assertTrue(item.evidence_hash.startswith("sha256:"))
        self.assertTrue(item.payload_hash.startswith("sha256:"))
        self.assertTrue(item.provenance_hash.startswith("sha256:"))
        self.assertEqual(item, graph.get(item.evidence_id))

    def test_claim_source_basis_and_time_relationships_are_retained(self):
        raw = self.evidence()
        raw["basis_refs"] = ["evidence-previous-001"]
        result = EvidenceGraphStore(self.identity_store).ingest(raw)
        self.assertTrue(result.accepted, result.error_code)
        assert result.item is not None
        output = result.item.to_dict()
        self.assertEqual(["evidence-previous-001"], output["basis_refs"])
        self.assertEqual("ref://club/availability/001", output["source_reference"])
        self.assertEqual("2026-09-04T08:00:00+08:00", output["published_at"])
        self.assertEqual("2026-09-04T09:00:00+08:00", output["retrieved_at"])
        self.assertEqual("2026-09-04T08:00:00+08:00", output["valid_from"])

    def test_identity_is_required_and_display_name_cannot_replace_match_id(self):
        graph = EvidenceGraphStore(self.identity_store)
        missing = self.evidence()
        missing["entity_refs"].pop("match_id")
        result = graph.ingest(missing)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_ID_REQUIRED", result.error_code)

        orphan = self.evidence()
        orphan["entity_refs"]["match_id"] = "019a0000-0000-5000-8000-000000000099"
        result = graph.ingest(orphan)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)

        display_only = self.evidence()
        display_only["entity_refs"] = {"team_display_name": "Example Home"}
        result = graph.ingest(display_only)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_ID_REQUIRED", result.error_code)

    def test_missing_source_or_unresolved_source_time_fails_closed(self):
        graph = EvidenceGraphStore(self.identity_store)
        missing_source = self.evidence()
        missing_source.pop("source")
        result = graph.ingest(missing_source)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

        unknown_valid_from = self.evidence()
        unknown_valid_from.pop("valid_from")
        unknown_valid_from["valid_from_state"] = "UNKNOWN_TIME"
        result = graph.ingest(unknown_valid_from)
        self.assertTrue(result.accepted, result.error_code)
        assert result.item is not None
        self.assertIsNone(result.item.valid_from)
        self.assertEqual("UNKNOWN_TIME", result.item.valid_from_state)

    def test_model_fields_and_prediction_confidence_are_rejected(self):
        for field in ("prediction", "recommendation", "model_interpretation", "engine_output", "feature_bundle"):
            with self.subTest(field=field):
                raw = self.evidence()
                raw["claim"][field] = "forbidden"
                result = EvidenceGraphStore(self.identity_store).ingest(raw)
                self.assertFalse(result.accepted)
                self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

        raw = self.evidence()
        raw["confidence"] = {"prediction_confidence": "HIGH"}
        result = EvidenceGraphStore(self.identity_store).ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_hash_mismatch_and_invalid_states_fail_closed(self):
        graph = EvidenceGraphStore(self.identity_store)
        bad_hash = self.evidence()
        bad_hash["evidence_hash"] = "sha256:" + "0" * 64
        result = graph.ingest(bad_hash)
        self.assertFalse(result.accepted)
        self.assertEqual("EVIDENCE_HASH_MISMATCH", result.error_code)

        bad_state = self.evidence()
        bad_state["verification_state"] = "GUESS"
        result = graph.ingest(bad_state)
        self.assertFalse(result.accepted)
        self.assertEqual("STATE_INVALID", result.error_code)

    def test_append_only_revision_duplicate_and_id_reuse(self):
        graph = EvidenceGraphStore(self.identity_store)
        first = graph.ingest(self.evidence())
        self.assertTrue(first.accepted)
        second_raw = self.evidence()
        second_raw.update(
            {
                "evidence_id": "evidence-20260904-003",
                "revision": 2,
                "supersedes_evidence_id": "evidence-20260904-001",
                "source_reference": "ref://club/availability/003",
                "retrieved_at": "2026-09-04T09:20:00+08:00",
            }
        )
        second = graph.ingest(second_raw)
        self.assertTrue(second.accepted, second.error_code)
        assert first.item is not None and second.item is not None
        self.assertEqual("REVISION_APPENDED", second.action)
        self.assertEqual(first.item.evidence_id, second.item.supersedes_evidence_id)
        self.assertIsNotNone(graph.get(first.item.evidence_id))

        duplicate = graph.ingest(self.evidence())
        self.assertTrue(duplicate.accepted)
        self.assertEqual("DUPLICATE_NOOP", duplicate.action)

        reused = self.evidence()
        reused["claim"]["availability"] = "UNKNOWN"
        result = graph.ingest(reused)
        self.assertFalse(result.accepted)
        self.assertEqual("EVIDENCE_ID_REUSE", result.error_code)

    def test_f_drive_and_v333_isolation_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-036/evidence.json").drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "work/evidence.json")


if __name__ == "__main__":
    unittest.main()
