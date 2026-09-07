import unittest

from src.local_ocr_consensus import (
    STATUS_AMBIGUOUS,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_UNRESOLVED,
    consensus_from_runs,
    normalize_numeric,
)


class LocalOcrConsensusTests(unittest.TestCase):
    def test_numeric_grammar_is_conservative(self):
        self.assertEqual("1.25", normalize_numeric(" 1,25\n"))
        self.assertIsNone(normalize_numeric("1.2.5"))
        self.assertIsNone(normalize_numeric("odds 1.25"))
        self.assertIsNone(normalize_numeric("0"))

    def test_single_engine_agreement_is_not_auto_confirmed(self):
        result = consensus_from_runs(
            [{"engine_identity": "tesseract", "normalized_value": "1.25"}, {"engine_identity": "tesseract", "normalized_value": "1.25"}],
            engine_count=1,
        )
        self.assertEqual(STATUS_AMBIGUOUS, result["status"])

    def test_distinct_engines_can_confirm(self):
        result = consensus_from_runs(
            [{"engine_identity": "tesseract", "normalized_value": "1.25"}, {"engine_identity": "easyocr", "normalized_value": "1.25"}],
            engine_count=2,
        )
        self.assertEqual(STATUS_CONFIRMED, result["status"])

    def test_conflict_and_unresolved_are_distinct(self):
        conflict = consensus_from_runs(
            [{"engine_identity": "tesseract", "normalized_value": "1.25"}, {"engine_identity": "tesseract", "normalized_value": "1.35"}],
            engine_count=1,
        )
        unresolved = consensus_from_runs([{"engine_identity": "tesseract", "normalized_value": None}], engine_count=1)
        self.assertEqual(STATUS_CONFLICT, conflict["status"])
        self.assertEqual(STATUS_UNRESOLVED, unresolved["status"])
