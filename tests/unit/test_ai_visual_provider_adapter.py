import json
import tempfile
import unittest
from pathlib import Path

from tools.ai_visual_review.provider import ProviderNeutralBatchVisionAdapter, StagingImageResolver, VisionAdapterError
from tools.ai_visual_review.protocol import HASH_RE


class StubProvider:
    provider_identity = "stub-vision-provider"
    provider_version = "stub@1.0.0"
    provider_config_hash = "sha256:" + "a" * 64

    def review(self, request):
        return {"status": "READABLE", "value_text": "1.35", "label_text": request.cell_label, "evidence": {"read": request.cell_label + "=1.35", "input": request.review_method}}


class MissingConnectionProvider(StubProvider):
    def review(self, request):
        raise VisionAdapterError("VISION_PROVIDER_CONNECTION_REQUIRED", "test")


class AiVisualProviderAdapterTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "queue_item_id": "q1", "artifact_slot": "slot", "artifact_identity": "slot|id=x", "raw_image_sha256": "sha256:" + "1" * 64,
            "market": "EXACT_SCORE", "cell_label": "2:0", "outcome_label": "2:0", "selected_profile_identity": "profile@1.1.0", "selected_profile_version": "1.1.0",
            "locator_identity": "locator@1.1.0", "locator_version": "1.1.0", "locator_hash": "sha256:" + "2" * 64,
            "crop_evidence": {"crop_hash": "sha256:" + "3" * 64, "evidence_record_id": "e1", "evidence_record_sha256": "sha256:" + "4" * 64, "evidence_region_path": "crop.png"},
            "ocr_evidence": {"normalized_ocr_text": "1.35"}, "prior_trace_record_id": "t1", "prior_trace_record_sha256": "sha256:" + "5" * 64,
            "prior_parser_status": "UNRESOLVED", "source_timestamps": {"source_timestamp": "UNKNOWN"}, "raw_zip_member": "raw/one.png",
        }

    def test_adapter_runs_two_independent_passes_and_records_hashes(self):
        adapter = ProviderNeutralBatchVisionAdapter(StubProvider())
        output = adapter.review_item(self.item)
        self.assertEqual(("AI_VISUAL_FROM_DETERMINISTIC_CROP", "AI_VISUAL_FROM_ORIGINAL_IMAGE"), (output[0].review_method, output[1].review_method))
        for observation in output:
            self.assertEqual("READABLE", observation.status)
            self.assertTrue(HASH_RE.fullmatch(observation.provider_config_hash))
            self.assertTrue(HASH_RE.fullmatch(observation.request_hash))
            self.assertTrue(HASH_RE.fullmatch(observation.response_hash))

    def test_provider_connection_failure_remains_unexecuted(self):
        adapter = ProviderNeutralBatchVisionAdapter(MissingConnectionProvider())
        output = adapter.review_item(self.item)
        self.assertEqual(("NOT_EXECUTED", "NOT_EXECUTED"), (output[0].status, output[1].status))

    def test_provider_metadata_is_recomputed_into_record_hash(self):
        record = ProviderNeutralBatchVisionAdapter(StubProvider()).build_review_record(self.item)
        from tools.ai_visual_review.protocol import canonical_hash
        self.assertEqual(record["canonical_review_record_hash"], canonical_hash(record))

    def test_staging_resolver_verifies_real_crop_and_raw_hashes(self):
        root = Path(__file__).resolve().parents[2] / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001"
        queue = root / "manual_review_workbench_r001_revision_001/review_queue.jsonl"
        if not queue.is_file():
            self.skipTest("R001 staging handoff is not present")
        item = json.loads(queue.read_text(encoding="utf-8").splitlines()[0])
        resolver = StagingImageResolver(root, root / "chatgpt-library-handoff.zip")
        self.assertGreater(len(resolver(item, "PASS_A")), 0)
        self.assertGreater(len(resolver(item, "PASS_B")), 0)

    def test_adapter_builds_a_record_with_provider_lineage(self):
        record = ProviderNeutralBatchVisionAdapter(StubProvider()).build_review_record(self.item)
        self.assertEqual("AI_CONFIRMED", record["review_status"])
        self.assertIn("provider_metadata", record)
        self.assertTrue(HASH_RE.fullmatch(record["provider_metadata"]["request_hashes"]["PASS_A"]))


if __name__ == "__main__":
    unittest.main()
