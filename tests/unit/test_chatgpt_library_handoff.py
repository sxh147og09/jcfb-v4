import unittest

from src.historical_backfill_intake.library_handoff import (
    build_candidate_dedupe_index,
    validate_handoff,
)


class ChatgptLibraryHandoffTests(unittest.TestCase):
    def test_empty_pending_handoff_is_schema_valid_but_not_materialized(self):
        result = validate_handoff({
            "contract_identity": "chatgpt-library-backfill-handoff@1.0.0",
            "handoff_id": "test-handoff",
            "source_origin": "CHATGPT_LIBRARY_EXPORT_PENDING_LOCAL_MATERIALIZATION",
            "distinct_match_target": 99,
            "source_artifacts": [],
            "candidate_manifest": [],
            "archive_write_allowed": False,
            "training_write_allowed": False,
        })
        self.assertEqual("VALIDATED_INTAKE_SCHEMA_ONLY", result["status"])
        self.assertEqual(0, result["candidate_count"])

    def test_unverified_candidates_dedupe_without_fuzzy_identity(self):
        candidate = {
            "candidate_id": "c-1",
            "file_id_or_external_ref": "library-file-1",
            "filename": "raw.png",
            "sha256": "sha256:" + "a" * 64,
            "timestamp_semantics": "UNKNOWN",
            "match_identity_candidate": {"status": "UNVERIFIED"},
            "market_coverage": ["HTFT"],
            "source_type": "RAW_SCREENSHOT",
            "provenance_confidence": "UNKNOWN",
            "eligible_for_raw_reingestion": True,
            "excluded_reasons": [],
        }
        rows = build_candidate_dedupe_index([candidate, dict(candidate, candidate_id="c-2")])
        self.assertIsNone(rows[0]["duplicate_of_candidate_id"])
        self.assertEqual("c-1", rows[1]["duplicate_of_candidate_id"])
