from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    OfficialScreenshotEvidenceStore,
    resolve_f_drive_output_path,
)


class V4025OfficialScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        screenshot_path = cls.repo_root / "tests/fixtures/v4_025/official_screenshot_cases.json"
        cls.identity_fixture = json.loads(identity_path.read_text(encoding="utf-8"))
        cls.screenshot_fixture = json.loads(screenshot_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.store = OfficialScreenshotEvidenceStore(self.identity_store)

    def base(self):
        raw = copy.deepcopy(self.screenshot_fixture["base"])
        raw["match_id"] = self.match_id
        return raw

    def test_verified_screenshot_retains_image_and_market_evidence(self):
        result = self.store.ingest(self.base())
        self.assertTrue(result.accepted)
        evidence = result.evidence
        self.assertEqual("evidence@1.0.0", evidence.contract_version)
        self.assertEqual("OFFICIAL_SCREENSHOT", evidence.source_type)
        self.assertEqual("OCR_PLUS_MANUAL", evidence.extraction_method)
        self.assertEqual(5, len(evidence.market_observations))
        self.assertTrue(evidence.image_hash.startswith("sha256:"))

    def test_unreadable_market_is_not_verified_and_requires_reason(self):
        raw = self.base()
        item = raw["market_observations"]["exact_score"]
        item.clear()
        item.update({"status": "NOT_VERIFIED", "raw_text": "部分数字无法辨认", "reason": "OCR_UNREADABLE"})
        raw["verification_state"] = "NOT_VERIFIED"
        raw["verification_reason"] = "EXACT_SCORE_UNREADABLE"
        result = self.store.ingest(raw)
        self.assertTrue(result.accepted)
        self.assertEqual("NOT_VERIFIED", result.evidence.market_observations["exact_score"]["status"])
        self.assertIsNone(result.evidence.market_observations["exact_score"]["payload"])

    def test_unreadable_market_without_reason_is_rejected(self):
        raw = self.base()
        raw["market_observations"]["exact_score"] = {"status": "NOT_VERIFIED", "raw_text": "无法辨认"}
        raw["verification_state"] = "NOT_VERIFIED"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_conflicting_ocr_and_manual_candidates_are_retained(self):
        raw = self.base()
        raw["market_observations"]["spf"] = {
            "status": "CONFLICTED",
            "reason": "OCR_MANUAL_DISAGREE",
            "candidates": [
                {"method": "OCR", "raw_text": "胜 2.10 平 3.20 负 3.15", "payload": {"home": 2.1, "draw": 3.2, "away": 3.15}},
                {"method": "MANUAL_TRANSCRIPTION", "raw_text": "胜 2.01 平 3.20 负 3.15", "payload": {"home": 2.01, "draw": 3.2, "away": 3.15}}
            ]
        }
        raw["verification_state"] = "CONFLICTED"
        raw["verification_reason"] = "OCR_MANUAL_DISAGREE"
        raw["contradiction_state"] = "CONFLICTED"
        result = self.store.ingest(raw)
        self.assertTrue(result.accepted)
        candidates = result.evidence.market_observations["spf"]["candidates"]
        self.assertEqual(2, len(candidates))
        self.assertNotEqual(candidates[0]["payload"], candidates[1]["payload"])

    def test_verified_state_cannot_hide_unresolved_market(self):
        raw = self.base()
        raw["market_observations"]["spf"] = {"status": "NOT_VERIFIED", "reason": "OCR_UNREADABLE"}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("VERIFICATION_STATE_CONFLICT", result.error_code)

    def test_verified_empty_payload_is_rejected(self):
        raw = self.base()
        raw["market_observations"]["spf"]["payload"] = {}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("PAYLOAD_EMPTY", result.error_code)

    def test_unverified_payload_is_rejected(self):
        raw = self.base()
        raw["market_observations"]["spf"] = {"status": "NOT_VERIFIED", "reason": "OCR_UNREADABLE", "payload": {"home": 2.1, "draw": 3.2, "away": 3.15}}
        raw["verification_state"] = "NOT_VERIFIED"
        raw["verification_reason"] = "OCR_UNREADABLE"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("UNVERIFIED_PAYLOAD_FORBIDDEN", result.error_code)

    def test_non_official_source_is_rejected(self):
        raw = self.base()
        raw["source_type"] = "EXTERNAL_SCREENSHOT"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("OFFICIAL_SCREENSHOT_REQUIRED", result.error_code)

    def test_image_hash_is_required(self):
        raw = self.base()
        raw.pop("image_hash")
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_model_fields_are_rejected(self):
        raw = self.base()
        raw["market_observations"]["spf"]["prediction"] = 0.5
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_missing_identity_blocks_without_orphan_evidence(self):
        raw = self.base()
        raw["match_id"] = "00000000-0000-5000-8000-000000000999"
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)
        self.assertEqual(0, len(self.store.evidence))

    def test_duplicate_and_correction_are_append_only(self):
        first = self.store.ingest(self.base())
        duplicate = self.store.ingest(self.base())
        self.assertEqual("DUPLICATE_NOOP", duplicate.action)
        correction = self.base()
        correction["source_reference"] = "ref://official/odds/screenshot/20260904-001-correction"
        correction["captured_at"] = "2026-09-04T09:11:30+08:00"
        correction["created_at"] = "2026-09-04T09:12:00+08:00"
        correction["supersedes_evidence_id"] = first.evidence.evidence_id
        correction["revision_reason"] = "OFFICIAL_SCREENSHOT_REPLACED"
        second = self.store.ingest(correction)
        self.assertTrue(second.accepted)
        self.assertEqual(2, second.evidence.revision)
        self.assertIsNotNone(self.store.get(first.evidence.evidence_id))
        self.assertEqual(2, len(self.store.evidence))

    def test_v333_f_drive_and_no_migration_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.repo_root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-025/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
