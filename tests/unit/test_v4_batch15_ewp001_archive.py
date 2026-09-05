from __future__ import annotations

import unittest
import tempfile

from src.historical_source_archive import ArchiveRuntime, ACTIVATED_AT, sha256_bytes, sha256_json


class B15Ewp001ArchiveRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = ArchiveRuntime("F:/Projects/jcfb-v4", persist=False)
        self.match_id = "match-20260905-001"
        self.identity = {"match_id": self.match_id, "competition_id": "league-1", "home_team_id": "home-1", "away_team_id": "away-1"}
        self.execution = {"work_package_id": "B15-EWP-001", "execution_authorized": True, "execution_id": "ewp001-test-execution", "execution_started_at": ACTIVATED_AT}

    def times(self):
        return {
            "source_timestamp": "2026-09-05T01:00:00+08:00",
            "observed_at": "2026-09-05T01:00:02+08:00",
            "captured_at": "2026-09-05T01:00:03+08:00",
            "ingested_at": "2026-09-05T01:00:04+08:00",
            "availability_at": "2026-09-05T01:00:00+08:00",
            "prediction_cutoff_at": "2026-09-05T02:00:00+08:00",
            "kickoff_at": "2026-09-05T03:00:00+08:00",
        }

    def artifact(self, artifact_type="canonical_match_facts", payload=None, **overrides):
        item = {"artifact_type": artifact_type, "source": "official-source", "source_identity": "official-source", "source_reference": "ref://official/2026/001", "payload": payload or {"competition_id": "league-1", "home_team_id": "home-1", "away_team_id": "away-1"}}
        item.update(self.times())
        item.update(overrides)
        return item

    def test_authorized_pre_match_capture_is_captured_and_sample_count_is_not_computed(self):
        result = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact()], execution_context=self.execution)
        self.assertTrue(result.accepted)
        self.assertEqual("CAPTURED", result.state)
        self.assertEqual("CAPTURED", result.session["capture_state"])
        self.assertEqual(1, len(result.records))
        self.assertEqual("ELIGIBLE_FOR_AS_OF_TRAINING", result.records[0]["eligibility_state"])
        self.assertEqual({"archived_match_count": 1, "usable_training_sample_count": "NOT_COMPUTED"}, self.runtime.counts())

    def test_unauthorized_execution_and_wrong_work_package_fail_closed(self):
        unauthorized = dict(self.execution, execution_authorized=False)
        with self.assertRaisesRegex(ValueError, "explicit EWP-001 authorization"):
            self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact()], execution_context=unauthorized)
        with self.assertRaisesRegex(ValueError, "B15-EWP-001"):
            self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact()], execution_context=dict(self.execution, work_package_id="B15-EWP-002"))

    def test_partial_state_records_reason_without_synthetic_placeholder(self):
        invalid = self.artifact(payload={"prediction": 0.5})
        result = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact(), invalid], execution_context=self.execution)
        self.assertTrue(result.accepted)
        self.assertEqual("PARTIAL", result.state)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.failures[0]["code"])
        self.assertEqual(1, len(result.records))

    def test_same_logical_artifact_duplicate_and_correction_are_append_only(self):
        first = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact()], execution_context=self.execution).records[0]
        duplicate = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[self.artifact()], execution_context=self.execution)
        self.assertEqual("CAPTURED", duplicate.state)
        self.assertEqual(first["archive_record_id"], duplicate.records[0]["archive_record_id"])
        correction = self.artifact(payload={"competition_id": "league-1", "home_team_id": "home-1", "away_team_id": "away-1", "venue": "corrected"}, supersedes=first["archive_record_id"], revision=2)
        second = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[correction], execution_context=self.execution).records[0]
        self.assertEqual(2, second["revision"])
        self.assertEqual(first["archive_record_id"], second["supersedes"])
        self.assertIn(first["archive_record_id"], self.runtime.records)
        self.assertNotEqual(first["artifact_hash"], second["artifact_hash"])

    def test_future_information_is_blocked_and_source_capture_ingestion_times_are_distinct(self):
        future = self.artifact(**{"source_timestamp": "2026-09-05T02:30:00+08:00", "availability_at": "2026-09-05T02:30:00+08:00"})
        result = self.runtime.capture_pre_match(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", artifacts=[future], execution_context=self.execution)
        self.assertFalse(result.accepted)
        self.assertEqual("BLOCKED", result.state)
        self.assertEqual("FUTURE_INFORMATION", result.failures[0]["code"])

    def test_official_screenshot_retains_original_root_and_replays(self):
        original = b"real uploaded official screenshot bytes"
        result = self.runtime.ingest_official_screenshot(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", source="china-sports-lottery", source_reference="upload://official/001.png", source_timestamp="2026-09-05T01:10:00+08:00", captured_at="2026-09-05T01:10:01+08:00", ingested_at="2026-09-05T01:10:02+08:00", prediction_cutoff_at="2026-09-05T02:00:00+08:00", kickoff_at="2026-09-05T03:00:00+08:00", captured_snapshot={"spf": {"home": "2.10", "draw": "3.20", "away": "3.15"}}, verification_state="OCR_PLUS_MANUAL", original_artifact_bytes=original, execution_context=self.execution)
        self.assertTrue(result.accepted)
        record = result.record
        self.assertEqual(sha256_bytes(original), record["original_payload_or_file_hash"])
        self.assertTrue(record["payload"]["source_is_official"])
        self.assertEqual("PASS", self.runtime.verify_provenance_replay(record["archive_record_id"])["status"])

    def test_file_backed_archive_reloads_original_provenance_root(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as project_root:
            first_runtime = ArchiveRuntime(project_root, persist=True)
            original = b"persisted original screenshot"
            result = first_runtime.ingest_official_screenshot(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", source="china-sports-lottery", source_reference="upload://official/persisted.png", source_timestamp="2026-09-05T01:10:00+08:00", captured_at="2026-09-05T01:10:01+08:00", ingested_at="2026-09-05T01:10:02+08:00", prediction_cutoff_at="2026-09-05T02:00:00+08:00", kickoff_at="2026-09-05T03:00:00+08:00", captured_snapshot={"spf": {"home": "2.10"}}, verification_state="MANUAL_VERIFIED", original_artifact_bytes=original, execution_context=self.execution)
            reloaded = ArchiveRuntime(project_root, persist=True)
            self.assertEqual("PASS", reloaded.verify_provenance_replay(result.record["archive_record_id"])["status"])
            self.assertTrue((reloaded.archive_root / result.record["original_artifact_path"]).is_file())

    def test_external_snapshots_are_provider_separated_and_consensus_is_rejected(self):
        result = self.runtime.ingest_external_snapshot(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", provider="provider-a", market_type="ASIAN_HANDICAP", line="-0.25", prices={"home": "1.92", "away": "1.94"}, source_reference="ref://provider-a/001", source_timestamp="2026-09-05T01:20:00+08:00", captured_at="2026-09-05T01:20:01+08:00", ingested_at="2026-09-05T01:20:02+08:00", prediction_cutoff_at="2026-09-05T02:00:00+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=self.execution)
        self.assertTrue(result.accepted)
        self.assertFalse(result.record["payload"]["source_is_official"])
        self.assertEqual("provider-a", result.record["payload"]["provider"])
        consensus = self.runtime.ingest_external_snapshot(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", provider="consensus", market_type="ASIAN_HANDICAP", line="-0.25", prices={"home": "1.92", "away": "1.94"}, source_reference="ref://consensus/001", source_timestamp="2026-09-05T01:20:00+08:00", captured_at="2026-09-05T01:20:01+08:00", ingested_at="2026-09-05T01:20:02+08:00", prediction_cutoff_at="2026-09-05T02:00:00+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=self.execution)
        self.assertFalse(consensus.accepted)
        self.assertEqual("PROVIDER_SNAPSHOT_REQUIRED", consensus.error_code)

    def test_post_match_labels_are_separate_and_append_only(self):
        result = self.runtime.append_post_match_labels(match_id=self.match_id, match_identity=self.identity, cutoff_profile="T_MINUS_60M", labels={"final_score": "2:1", "halftime_score": "1:0", "outcome": "H"}, source="official-result", source_reference="ref://result/001", source_timestamp="2026-09-05T05:00:00+08:00", captured_at="2026-09-05T05:00:01+08:00", ingested_at="2026-09-05T05:00:02+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=self.execution)
        self.assertTrue(result.accepted)
        self.assertEqual("final_result", result.record["artifact_type"])
        self.assertEqual("UNKNOWN", result.record["eligibility_state"])
        self.assertEqual("POST_MATCH_ONLY", result.record["label_scope"])
        self.assertNotIn("final_score", self.runtime.records[result.record["archive_record_id"]].get("pre_match_payload", {}))

    def test_backfill_is_evaluation_only_and_rejects_unverifiable_candidate(self):
        decision = self.runtime.evaluate_verified_historical_candidate({"raw_artifact_exists": False, "historical_source_timestamp": None, "original_source_identifiable": False, "match_identity_resolvable": False, "provenance_intact": False})
        self.assertEqual("NOT_ELIGIBLE_FOR_AS_OF_TRAINING", decision["status"])
        self.assertEqual("NOT_PERFORMED", decision["import_action"])
        self.assertEqual({}, self.runtime.records)

    def test_hashes_use_canonical_json_and_f_drive_is_required(self):
        self.assertEqual("sha256:df3581d2e27753dbab1087d0a366f0ce64a7f667ad7366bb35ac74e7d00e74ce", sha256_json({"not": "this"}))
        self.assertEqual("F:", self.runtime.archive_root.drive.upper())
        with self.assertRaises(ValueError):
            ArchiveRuntime("C:/jcfb-v4", persist=False)


if __name__ == "__main__":
    unittest.main()
