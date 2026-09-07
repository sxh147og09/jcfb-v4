import unittest

from src.historical_backfill_intake import DedupeIndex, build_identity_index, canonical_identity_key


class HistoricalBackfillStagingTests(unittest.TestCase):
    def identity(self, match_id="m-001", kickoff="2026-08-13T12:00:00+08:00"):
        return {"canonical_match_id": match_id, "competition": "League", "home": "Home", "away": "Away", "kickoff_at": kickoff}

    def test_identity_mapping_is_explicit_and_deterministic(self):
        first = canonical_identity_key(self.identity())
        second = canonical_identity_key(self.identity())
        self.assertEqual(first, second)
        rows = build_identity_index([{"manifest_id": "a", "canonical_match_identity": self.identity()}, {"manifest_id": "b", "canonical_match_identity": self.identity()}])
        self.assertIsNone(rows[0]["duplicate_of_manifest_id"])
        self.assertEqual("a", rows[1]["duplicate_of_manifest_id"])

    def test_dedupe_reports_semantics_without_silent_merge(self):
        existing = {"manifest_id": "a", "original_file_sha256": "sha256:" + "1" * 64, "external_source_identity": {"provider": "library", "library_file_id_or_ref": "f1"}, "canonical_match_identity": self.identity(), "extraction": {"extracted_market_payload": {"SPF": 1}}, "chatgpt_upload_timestamp": "2026-08-13T00:00:00+08:00"}
        candidate = dict(existing, manifest_id="b")
        result = DedupeIndex([existing]).compare(candidate)
        self.assertEqual("DUPLICATE_NOOP", result[0]["semantics"])
        self.assertIn("canonical_identity_key", result[0])


if __name__ == "__main__":
    unittest.main()
