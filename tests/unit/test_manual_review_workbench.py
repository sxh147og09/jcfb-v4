from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.manual_review_workbench import Workbench, build_queue, validate_manual_value
from tools.manual_review_workbench.core import (
    ActionValidationError,
    DuplicateSubmissionError,
    ACTIVE_MARKETS,
    TERMINAL_STATUSES,
    file_hash,
    queue_item_hash,
    record_hash,
)
from tools.manual_review_workbench import core


ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "approved_data" / "historical_backfill_staging" / "CHATGPT-20260901-20260904-R001"


class ManualReviewWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="jcfb-manual-review-")
        self.output = Path(self.tempdir.name) / "manual_review_workbench_r001_revision_test"
        self.workbench = Workbench(staging=STAGING, output=self.output)
        self.trace_before = file_hash(STAGING / "historical_trace_reconstruction_with_ocr_r001_revision_003" / "unresolved_cell_trace.jsonl")
        self.evidence_before = file_hash(STAGING / "ocr_evidence_r001_revision_004" / "ocr_cell_evidence.jsonl")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_queue_count_exclusion_order_and_bindings(self) -> None:
        queue, source = build_queue(STAGING)
        self.assertEqual(432, len(queue))
        self.assertEqual(9, source["market_unavailable_excluded"])
        self.assertEqual({"EXACT_SCORE": 369, "TOTAL_GOALS": 3, "HTFT": 56, "SPF": 2, "RQSPF": 2}, {market: sum(item["market"] == market for item in queue) for market in ACTIVE_MARKETS})
        priority = {market: index for index, market in enumerate(ACTIVE_MARKETS)}
        self.assertEqual(queue, sorted(queue, key=lambda item: (priority[item["market"]], item["artifact_slot"], item["ordering_index"], item["queue_item_id"])))
        self.assertTrue(all(item["queue_item_sha256"] == queue_item_hash(item) for item in queue))
        self.assertTrue(all(item["raw_image_sha256"].startswith("sha256:") for item in queue))
        self.assertTrue(all(item["crop_evidence"]["evidence_region_path"].startswith("evidence_regions/") for item in queue))
        self.assertEqual(0, self.workbench.summary()["confirmed"])
        self.assertEqual(432, self.workbench.summary()["remaining"])

    def test_valid_confirm_ocr_action_is_format_gated(self) -> None:
        item = copy.deepcopy(self.workbench.queue[0])
        item["ocr_evidence"]["normalized_ocr_text"] = "1.35"
        item["ocr_evidence"]["raw_ocr_text"] = " 1.35 "
        parsed, source_text, status = self.workbench._validate_action(item, "CONFIRM_OCR_VALUE", None)
        self.assertEqual(1.35, parsed)
        self.assertEqual(" 1.35 ", source_text)
        self.assertEqual("CONFIRMED", status)

    def test_manual_correction_unknown_conflict_duplicate_and_supersede(self) -> None:
        first = self.workbench.queue[0]
        result = self.workbench.submit(queue_item_id=first["queue_item_id"], action="ENTER_CORRECT_VALUE", value="1.35", reviewer_id="tester")
        self.assertTrue(result["record_created"])
        first_record = result["record"]
        self.assertEqual("CONFIRMED", first_record["manual_review_status"])
        self.assertEqual("1.35", first_record["manual_review_source_text"])
        self.assertEqual(first["source_timestamps"], first_record["source_timestamps"])
        self.assertEqual(first_record["manual_review_record_sha256"], record_hash(first_record))
        with self.assertRaises(DuplicateSubmissionError):
            self.workbench.submit(queue_item_id=first["queue_item_id"], action="ENTER_CORRECT_VALUE", value="1.35", reviewer_id="tester")
        superseding = self.workbench.submit(queue_item_id=first["queue_item_id"], action="ENTER_CORRECT_VALUE", value="1.40", reviewer_id="tester")
        self.assertEqual(2, superseding["record"]["review_revision"])
        self.assertEqual(first_record["manual_review_record_id"], superseding["record"]["supersedes_manual_review_record_id"])
        unknown = self.workbench.queue[1]
        self.workbench.submit(queue_item_id=unknown["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        conflict = self.workbench.queue[2]
        self.workbench.submit(queue_item_id=conflict["queue_item_id"], action="CONFLICT", value="2.10", reviewer_id="tester")
        summary = self.workbench.summary()
        self.assertEqual(1, summary["confirmed"])
        self.assertEqual(1, summary["unknown"])
        self.assertEqual(1, summary["conflict"])
        self.assertEqual(429, summary["remaining"])
        self.assertEqual(4, len(self.workbench.history()))

    def test_invalid_values_and_skip_do_not_write_confirmed_ledger(self) -> None:
        item = self.workbench.queue[0]
        for value in ("", "abc", "-1", "nan", "1,35"):
            with self.assertRaises(ActionValidationError):
                self.workbench.submit(queue_item_id=item["queue_item_id"], action="ENTER_CORRECT_VALUE", value=value, reviewer_id="tester")
        before = len(self.workbench.history())
        self.workbench.submit(queue_item_id=item["queue_item_id"], action="SKIP_FOR_LATER", reviewer_id="tester")
        self.assertEqual(before, len(self.workbench.history()))
        self.assertIn(item["queue_item_id"], self.workbench.session_state()["skipped_queue_item_ids"])
        self.assertEqual(432, self.workbench.summary()["remaining"])

    def test_resume_asset_hash_and_source_no_write_boundary(self) -> None:
        item = self.workbench.queue[0]
        raw, raw_type = self.workbench.asset(item["queue_item_id"], "raw")
        crop, crop_type = self.workbench.asset(item["queue_item_id"], "crop")
        self.assertEqual("image/png", raw_type)
        self.assertEqual("image/png", crop_type)
        self.assertEqual(item["raw_image_sha256"], "sha256:" + __import__("hashlib").sha256(raw).hexdigest())
        self.assertEqual(item["crop_evidence"]["crop_hash"], "sha256:" + __import__("hashlib").sha256(crop).hexdigest())
        self.workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        resumed = Workbench(staging=STAGING, output=self.output)
        self.assertEqual(1, resumed.summary()["unknown"])
        self.assertEqual(self.trace_before, file_hash(STAGING / "historical_trace_reconstruction_with_ocr_r001_revision_003" / "unresolved_cell_trace.jsonl"))
        self.assertEqual(self.evidence_before, file_hash(STAGING / "ocr_evidence_r001_revision_004" / "ocr_cell_evidence.jsonl"))
        self.assertTrue(all(status in TERMINAL_STATUSES for status in resumed.summary()["status_counts"]))

    def test_value_validation_allows_handicap_but_not_negative_odds(self) -> None:
        self.assertEqual(-0.5, validate_manual_value("-0.5", value_kind="HANDICAP_LINE"))
        self.assertEqual(0.0, validate_manual_value("0", value_kind="HANDICAP_LINE"))
        with self.assertRaises(ActionValidationError):
            validate_manual_value("-0.5", value_kind="ODDS")

    def test_git_absent_does_not_fail_submit_and_records_fail_safe_report_metadata(self) -> None:
        output = Path(self.tempdir.name) / "manual_review_workbench_git_absent"
        with patch.object(core.subprocess, "run", side_effect=FileNotFoundError(2, "git")):
            workbench = Workbench(staging=STAGING, output=output)
            item = workbench.queue[0]
            result = workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        self.assertTrue(result["submission_committed"])
        self.assertEqual(1, len(workbench.history()))
        report = (output / "implementation_and_human_review_readiness_report.md").read_text(encoding="utf-8")
        self.assertIn("Final HEAD at report generation: `GIT_NOT_AVAILABLE`", report)
        self.assertIn("Working tree snapshot at report generation: `GIT_NOT_AVAILABLE`", report)

    def test_git_command_failure_uses_fail_safe_metadata(self) -> None:
        item = self.workbench.queue[0]
        failed = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="fatal: not a repository")
        with patch.object(core.subprocess, "run", return_value=failed):
            result = self.workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        self.assertTrue(result["submission_committed"])
        report = (self.output / "implementation_and_human_review_readiness_report.md").read_text(encoding="utf-8")
        self.assertIn("Final HEAD at report generation: `GIT_NOT_AVAILABLE`", report)
        self.assertIn("Working tree snapshot at report generation: `GIT_NOT_AVAILABLE`", report)

    def test_git_available_records_head_and_working_tree(self) -> None:
        item = self.workbench.queue[0]

        def fake_run(command, **kwargs):
            if command[1:3] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="## main\n M tools/manual_review_workbench/core.py\n", stderr="")

        with patch.object(core.subprocess, "run", side_effect=fake_run):
            result = self.workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        self.assertTrue(result["submission_committed"])
        report = (self.output / "implementation_and_human_review_readiness_report.md").read_text(encoding="utf-8")
        self.assertIn("Final HEAD at report generation: `abc123`", report)
        self.assertIn("Working tree snapshot at report generation: `## main |  M tools/manual_review_workbench/core.py`", report)

    def test_post_commit_refresh_failure_returns_committed_warning_and_duplicate_is_rejected(self) -> None:
        item = self.workbench.queue[0]
        with patch.object(core, "_write_report", side_effect=RuntimeError("simulated report failure")):
            result = self.workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")
        self.assertTrue(result["submission_committed"])
        self.assertIn("EXPORT_REFRESH_FAILED", result["warning"])
        self.assertEqual(1, len(self.workbench.history()))
        with self.assertRaises(DuplicateSubmissionError):
            self.workbench.submit(queue_item_id=item["queue_item_id"], action="UNKNOWN", reviewer_id="tester")


if __name__ == "__main__":
    unittest.main()
