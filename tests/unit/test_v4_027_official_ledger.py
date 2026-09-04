from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    AvailabilityTimeBasis,
    CanonicalMatchIdentityStore,
    OfficialMarketAvailabilityGate,
    OfficialOddsProvenanceLedger,
    OfficialOddsSnapshotStore,
    OfficialScreenshotEvidenceStore,
    TimeGateStatus,
    resolve_f_drive_output_path,
)


class V4027OfficialOddsLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.repo_root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.odds_fixture = json.loads((cls.repo_root / "tests/fixtures/v4_024/official_odds_cases.json").read_text(encoding="utf-8"))
        cls.screenshot_fixture = json.loads((cls.repo_root / "tests/fixtures/v4_025/official_screenshot_cases.json").read_text(encoding="utf-8"))
        cls.ledger_fixture = json.loads((cls.repo_root / "tests/fixtures/v4_027/official_ledger_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        odds = copy.deepcopy(self.odds_fixture["base"])
        odds["match_id"] = self.match_id
        self.snapshot = odds_store.ingest(odds).snapshot
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        screenshot = copy.deepcopy(self.screenshot_fixture["base"])
        screenshot["match_id"] = self.match_id
        screenshot["source_timestamp"] = "2026-09-04T09:04:00+08:00"
        screenshot["captured_at"] = "2026-09-04T09:04:30+08:00"
        screenshot["observed_at"] = "2026-09-04T09:05:00+08:00"
        screenshot["ingested_at"] = "2026-09-04T09:05:02+08:00"
        self.screenshot = screenshot_store.ingest(screenshot).evidence
        self.gate = OfficialMarketAvailabilityGate(self.identity_store)
        self.gate_result = self.gate.evaluate(self.snapshot, self.screenshot)
        self.ledger = OfficialOddsProvenanceLedger()

    def request(self, name="prematch"):
        return self.ledger_fixture[name]

    def test_prematch_entry_retains_all_source_and_hash_lineage(self):
        result = self.ledger.record(self.snapshot, self.gate_result, **self.request(), screenshot_evidence=self.screenshot)
        self.assertTrue(result.accepted)
        self.assertEqual(TimeGateStatus.PREMATCH_ALLOWED, result.status)
        entry = result.entry
        self.assertEqual(self.match_id, entry.match_id)
        self.assertEqual(self.snapshot.snapshot_id, entry.snapshot_id)
        self.assertEqual(self.snapshot.observation_id, entry.snapshot_observation_id)
        self.assertEqual(self.gate_result.gate_id, entry.gate_id)
        self.assertEqual(self.screenshot.evidence_id, entry.screenshot_evidence_id)
        self.assertEqual("2026-09-04T09:04:00+08:00", entry.availability_at)
        self.assertEqual(self.snapshot.captured_at, entry.captured_at)
        self.assertEqual(self.snapshot.observed_at, entry.observed_at)
        self.assertEqual(self.snapshot.ingested_at, entry.ingested_at)
        self.assertEqual(self.screenshot.source_timestamp, entry.evidence_source_timestamp)
        self.assertEqual(self.screenshot.captured_at, entry.evidence_captured_at)
        self.assertEqual(self.screenshot.observed_at, entry.evidence_observed_at)
        self.assertEqual(self.screenshot.ingested_at, entry.evidence_ingested_at)
        self.assertEqual(self.snapshot.provenance_hash, entry.snapshot_provenance_hash)
        self.assertEqual(self.screenshot.provenance_hash, entry.screenshot_provenance_hash)
        self.assertTrue(entry.provenance_hash.startswith("sha256:"))
        self.assertTrue(entry.ledger_hash.startswith("sha256:"))

    def test_observed_basis_is_explicit_and_ingested_time_is_not_selected(self):
        result = self.ledger.record(self.snapshot, self.gate_result, **self.request("observed_basis"))
        self.assertTrue(result.accepted)
        self.assertEqual(AvailabilityTimeBasis.OBSERVED_AT, result.entry.availability_time_basis)
        self.assertEqual(self.snapshot.observed_at, result.entry.availability_at)
        self.assertNotEqual(self.snapshot.ingested_at, result.entry.availability_at)

    def test_unknown_source_time_is_blocked_without_fallback(self):
        unknown = copy.deepcopy(self.odds_fixture["base"])
        unknown["match_id"] = self.match_id
        unknown["source_timestamp"] = "UNKNOWN"
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        snapshot = odds_store.ingest(unknown).snapshot
        gate_result = self.gate.evaluate(snapshot)
        result = self.ledger.record(snapshot, gate_result, **self.request())
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.BLOCKED, result.status)
        self.assertEqual("UNKNOWN_TIME_BLOCKED", result.entry.reason_code)
        self.assertIsNone(result.entry.availability_at)

    def test_conflicted_source_time_is_blocked(self):
        conflicted = copy.deepcopy(self.odds_fixture["base"])
        conflicted["match_id"] = self.match_id
        conflicted["source_timestamp"] = "CONFLICTED"
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        snapshot = odds_store.ingest(conflicted).snapshot
        result = self.ledger.record(snapshot, self.gate.evaluate(snapshot), **self.request())
        self.assertFalse(result.accepted)
        self.assertEqual("UNKNOWN_TIME_BLOCKED", result.entry.reason_code)

    def test_after_cutoff_is_future_information_leakage(self):
        result = self.ledger.record(self.snapshot, self.gate_result, **self.request("after_cutoff"))
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.FUTURE_INFORMATION_LEAKAGE, result.status)
        self.assertEqual("AFTER_DECLARED_CUTOFF", result.entry.reason_code)
        self.assertTrue(result.entry.future_information_leakage)
        self.assertTrue(result.entry.run_invalid)

    def test_at_or_after_kickoff_is_postmatch_only(self):
        result = self.ledger.record(self.snapshot, self.gate_result, **self.request("postmatch"))
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.POSTMATCH_ONLY, result.status)
        self.assertEqual("AVAILABLE_AT_OR_AFTER_KICKOFF", result.entry.reason_code)
        self.assertTrue(result.entry.future_information_leakage)

    def test_explicit_market_missingness_remains_blocked(self):
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        odds = copy.deepcopy(self.odds_fixture["base"])
        odds["match_id"] = self.match_id
        odds["rqspf"] = None
        odds["market_availability"]["rqspf"] = {"available": False, "status": "UNAVAILABLE", "reason": "OFFICIAL_MARKET_NOT_ON_SALE"}
        odds["market_unavailable_reason"]["rqspf"] = "OFFICIAL_MARKET_NOT_ON_SALE"
        snapshot = odds_store.ingest(odds).snapshot
        gate_result = self.gate.evaluate(snapshot)
        result = self.ledger.record(snapshot, gate_result, **self.request())
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.BLOCKED, result.status)
        self.assertEqual("OFFICIAL_MARKET_MISSINGNESS_NOT_READY", result.entry.reason_code)
        self.assertEqual("UNAVAILABLE", result.entry.market_statuses["rqspf"].value)

    def test_gate_block_and_conflicting_evidence_are_not_promoted(self):
        conflicted = copy.deepcopy(self.screenshot_fixture["base"])
        conflicted["match_id"] = self.match_id
        conflicted["source_timestamp"] = "2026-09-04T09:04:00+08:00"
        conflicted["captured_at"] = "2026-09-04T09:04:30+08:00"
        conflicted["observed_at"] = "2026-09-04T09:05:00+08:00"
        conflicted["ingested_at"] = "2026-09-04T09:05:02+08:00"
        conflicted["market_observations"]["spf"] = {
            "status": "CONFLICTED",
            "reason": "OCR_MANUAL_DISAGREE",
            "candidates": [
                {"method": "OCR", "raw_text": "2.10", "payload": {"home": 2.1, "draw": 3.2, "away": 3.15}},
                {"method": "MANUAL_TRANSCRIPTION", "raw_text": "2.01", "payload": {"home": 2.01, "draw": 3.2, "away": 3.15}},
            ],
        }
        conflicted["verification_state"] = "CONFLICTED"
        conflicted["verification_reason"] = "OCR_MANUAL_DISAGREE"
        conflicted["contradiction_state"] = "CONFLICTED"
        store = OfficialScreenshotEvidenceStore(self.identity_store)
        evidence = store.ingest(conflicted).evidence
        gate_result = self.gate.evaluate(self.snapshot, evidence)
        result = self.ledger.record(self.snapshot, gate_result, **self.request())
        self.assertFalse(result.accepted)
        self.assertEqual("AVAILABILITY_GATE_BLOCKED", result.entry.reason_code)
        self.assertEqual("BLOCKED", result.entry.market_statuses["spf"].value)

    def test_gate_and_snapshot_references_are_required_to_match(self):
        other_gate = OfficialMarketAvailabilityGate(self.identity_store).evaluate(self.snapshot)
        result = self.ledger.record(self.snapshot, other_gate, **self.request())
        self.assertTrue(result.accepted)
        wrong = copy.deepcopy(self.odds_fixture["base"])
        wrong["match_id"] = self.match_id
        wrong["source_reference"] = "ref://official/other"
        other_snapshot = OfficialOddsSnapshotStore(self.identity_store).ingest(wrong).snapshot
        result = self.ledger.record(other_snapshot, self.gate_result, **self.request())
        self.assertFalse(result.accepted)
        self.assertEqual("GATE_REFERENCE_CONFLICT", result.error_code)

    def test_duplicate_is_noop_and_correction_is_append_only(self):
        first = self.ledger.record(self.snapshot, self.gate_result, **self.request())
        duplicate = self.ledger.record(self.snapshot, self.gate_result, **self.request())
        self.assertEqual("DUPLICATE_NOOP", duplicate.action.value)
        self.assertEqual(1, len(self.ledger.entries))
        corrected = self.ledger.record(
            self.snapshot,
            self.gate_result,
            **self.request(),
            supersedes_ledger_id=first.entry.ledger_id,
        )
        self.assertEqual("APPENDED", corrected.action.value)
        self.assertEqual(2, len(self.ledger.entries))
        self.assertEqual(first.entry.ledger_id, corrected.entry.supersedes_ledger_id)
        self.assertEqual(2, corrected.entry.revision)
        self.assertEqual(["APPENDED", "DUPLICATE_NOOP", "APPENDED"], [event["action"] for event in self.ledger.events])

    def test_invalid_cutoff_and_basis_fail_closed(self):
        invalid = self.request()
        result = self.ledger.record(self.snapshot, self.gate_result, invalid["kickoff_at"], invalid["kickoff_at"], invalid["availability_time_basis"])
        self.assertFalse(result.accepted)
        self.assertEqual("CUTOFF_NOT_BEFORE_KICKOFF", result.error_code)
        result = self.ledger.record(self.snapshot, self.gate_result, invalid["prediction_cutoff_at"], invalid["kickoff_at"], "AUTO")
        self.assertFalse(result.accepted)
        self.assertEqual("AVAILABILITY_BASIS_INVALID", result.error_code)

    def test_v333_f_drive_and_no_migration_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.repo_root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-027/evidence.json").drive.upper())


if __name__ == "__main__":
    unittest.main()
