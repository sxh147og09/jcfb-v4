import json
import tempfile
import unittest
from pathlib import Path

from tools.ai_visual_review.protocol import VisualPassObservation, build_review_record, load_contract
from tools.ai_visual_review.runner import run


class AiVisualReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = {
            "queue_item_id": "q1", "artifact_slot": "slot", "artifact_identity": "slot|id=x",
            "raw_image_sha256": "sha256:" + "1" * 64, "market": "EXACT_SCORE", "cell_label": "2:0",
            "outcome_label": "2:0", "selected_profile_identity": "profile@1.1.0", "selected_profile_version": "1.1.0",
            "locator_identity": "locator@1.1.0", "locator_version": "1.1.0", "locator_hash": "sha256:" + "2" * 64,
            "crop_evidence": {"crop_hash": "sha256:" + "3" * 64, "evidence_record_id": "e1", "evidence_record_sha256": "sha256:" + "4" * 64},
            "ocr_evidence": {"normalized_ocr_text": "1.35"}, "prior_trace_record_id": "t1", "prior_trace_record_sha256": "sha256:" + "5" * 64,
            "prior_parser_status": "UNRESOLVED", "source_timestamps": {"source_timestamp": "UNKNOWN"},
        }

    def obs(self, pass_id, method, value="1.35", label="2:0"):
        return VisualPassObservation(pass_id, method, "READABLE", value, label, "sha256:" + ("6" if pass_id == "PASS_A" else "7") * 64, "provider", "1.0", "sha256:" + "8" * 64)

    def test_equal_visual_and_ocr_is_confirmed(self):
        record = build_review_record(self.item, pass_a=self.obs("PASS_A", "AI_VISUAL_FROM_DETERMINISTIC_CROP"), pass_b=self.obs("PASS_B", "AI_VISUAL_FROM_ORIGINAL_IMAGE"), contract=load_contract())
        self.assertEqual("AI_CONFIRMED", record["review_status"])
        self.assertTrue(record["canonical_review_record_hash"].startswith("sha256:"))

    def test_disagreement_is_conflict(self):
        record = build_review_record(self.item, pass_a=self.obs("PASS_A", "AI_VISUAL_FROM_DETERMINISTIC_CROP"), pass_b=self.obs("PASS_B", "AI_VISUAL_FROM_ORIGINAL_IMAGE", value="1.36"), contract=load_contract())
        self.assertEqual("CONFLICT", record["review_status"])
        self.assertIsNone(record["review_value"])

    def test_missing_readable_label_is_rejected(self):
        with self.assertRaises(ValueError):
            build_review_record(self.item, pass_a=self.obs("PASS_A", "AI_VISUAL_FROM_DETERMINISTIC_CROP", label=None), pass_b=self.obs("PASS_B", "AI_VISUAL_FROM_ORIGINAL_IMAGE"), contract=load_contract())

    def test_unavailable_provider_emits_bound_escalations(self):
        queue_file = Path(tempfile.mkdtemp()) / "queue.jsonl"
        queue_file.write_text(json.dumps(self.item) + "\n", encoding="utf-8")
        output = queue_file.parent / "out"
        manifest = run(queue_path=queue_file, output=output)
        self.assertEqual({"HUMAN_ESCALATION_REQUIRED": 1}, manifest["status_counts"])
        record = json.loads((output / "ai_visual_review_records.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual("NOT_EXECUTED", record["pass_a"]["status"])
        self.assertEqual("HUMAN_ESCALATION_REQUIRED", record["review_status"])


if __name__ == "__main__":
    unittest.main()
