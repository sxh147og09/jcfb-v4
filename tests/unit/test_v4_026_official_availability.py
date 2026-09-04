from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    MarketGateStatus,
    OfficialMarketAvailabilityGate,
    OfficialOddsSnapshotStore,
    OfficialScreenshotEvidenceStore,
    AvailabilityGateOutcome,
    resolve_f_drive_output_path,
)


class V4026AvailabilityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        odds_path = cls.repo_root / "tests/fixtures/v4_024/official_odds_cases.json"
        screenshot_path = cls.repo_root / "tests/fixtures/v4_025/official_screenshot_cases.json"
        gate_path = cls.repo_root / "tests/fixtures/v4_026/availability_cases.json"
        cls.identity_fixture = json.loads(identity_path.read_text(encoding="utf-8"))
        cls.odds_fixture = json.loads(odds_path.read_text(encoding="utf-8"))
        cls.screenshot_fixture = json.loads(screenshot_path.read_text(encoding="utf-8"))
        cls.gate_fixture = json.loads(gate_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity.canonical_match_id
        self.assertIsNotNone(self.match_id)
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        odds = copy.deepcopy(self.odds_fixture["base"])
        odds["match_id"] = self.match_id
        snapshot_result = odds_store.ingest(odds)
        self.snapshot = snapshot_result.snapshot
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        screenshot = copy.deepcopy(self.screenshot_fixture["base"])
        screenshot["match_id"] = self.match_id
        screenshot_result = screenshot_store.ingest(screenshot)
        self.screenshot = screenshot_result.evidence
        self.gate = OfficialMarketAvailabilityGate(self.identity_store)

    def test_all_five_markets_pass_when_feed_and_screenshot_agree(self):
        result = self.gate.evaluate(self.snapshot, self.screenshot)
        self.assertTrue(result.accepted)
        self.assertTrue(result.downstream_ready)
        self.assertEqual(AvailabilityGateOutcome.PASSED, result.outcome)
        self.assertTrue(all(item.status == MarketGateStatus.AVAILABLE for item in result.decisions.values()))

    def test_feed_snapshot_can_be_gated_without_screenshot(self):
        result = self.gate.evaluate(self.snapshot)
        self.assertTrue(result.accepted)
        self.assertTrue(result.downstream_ready)

    def test_unavailable_market_is_explicit_and_never_substituted(self):
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        odds = copy.deepcopy(self.odds_fixture["base"])
        odds["match_id"] = self.match_id
        odds["rqspf"] = None
        missing = self.gate_fixture["unavailable_market"]
        odds["market_availability"]["rqspf"] = {"available": False, "status": missing["status"], "reason": missing["reason"]}
        odds["market_unavailable_reason"]["rqspf"] = missing["reason"]
        snapshot = odds_store.ingest(odds).snapshot
        result = self.gate.evaluate(snapshot)
        self.assertTrue(result.accepted)
        self.assertFalse(result.downstream_ready)
        self.assertEqual(AvailabilityGateOutcome.EXPLICIT_MISSINGNESS, result.outcome)
        self.assertEqual(MarketGateStatus.UNAVAILABLE, result.decisions["rqspf"].status)
        self.assertIsNone(result.decisions["rqspf"].payload)

    def test_unverified_screenshot_blocks_market(self):
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        raw = copy.deepcopy(self.screenshot_fixture["base"])
        raw["match_id"] = self.match_id
        raw["market_observations"]["exact_score"] = {"status": "NOT_VERIFIED", "raw_text": "无法辨认", "reason": "OCR_UNREADABLE"}
        raw["verification_state"] = "NOT_VERIFIED"
        raw["verification_reason"] = "EXACT_SCORE_UNREADABLE"
        evidence = screenshot_store.ingest(raw).evidence
        result = self.gate.evaluate(self.snapshot, evidence)
        self.assertFalse(result.accepted)
        self.assertEqual(AvailabilityGateOutcome.BLOCKED, result.outcome)
        self.assertEqual(MarketGateStatus.NOT_VERIFIED, result.decisions["exact_score"].status)
        self.assertIsNone(result.decisions["exact_score"].payload)

    def test_conflicted_screenshot_preserves_competing_evidence(self):
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        raw = copy.deepcopy(self.screenshot_fixture["base"])
        raw["match_id"] = self.match_id
        raw["market_observations"]["spf"] = {
            "status": "CONFLICTED",
            "reason": "OCR_MANUAL_DISAGREE",
            "candidates": [
                {"method": "OCR", "raw_text": "2.10", "payload": {"home": 2.1, "draw": 3.2, "away": 3.15}},
                {"method": "MANUAL_TRANSCRIPTION", "raw_text": "2.01", "payload": {"home": 2.01, "draw": 3.2, "away": 3.15}}
            ]
        }
        raw["verification_state"] = "CONFLICTED"
        raw["verification_reason"] = "OCR_MANUAL_DISAGREE"
        raw["contradiction_state"] = "CONFLICTED"
        evidence = screenshot_store.ingest(raw).evidence
        result = self.gate.evaluate(self.snapshot, evidence)
        self.assertFalse(result.accepted)
        self.assertEqual(MarketGateStatus.BLOCKED, result.decisions["spf"].status)
        self.assertEqual(2, len(result.decisions["spf"].competing_evidence))

    def test_feed_and_screenshot_payload_conflict_is_blocked(self):
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        raw = copy.deepcopy(self.screenshot_fixture["base"])
        raw["match_id"] = self.match_id
        raw["market_observations"]["spf"]["payload"]["home"] = 2.01
        evidence = screenshot_store.ingest(raw).evidence
        result = self.gate.evaluate(self.snapshot, evidence)
        self.assertFalse(result.accepted)
        self.assertEqual("FEED_SCREENSHOT_PAYLOAD_CONFLICT", result.decisions["spf"].reason_code)
        self.assertIsNone(result.decisions["spf"].payload)

    def test_feed_and_screenshot_availability_conflict_is_blocked(self):
        screenshot_store = OfficialScreenshotEvidenceStore(self.identity_store)
        raw = copy.deepcopy(self.screenshot_fixture["base"])
        raw["match_id"] = self.match_id
        raw["market_observations"]["rqspf"] = {"status": "UNAVAILABLE", "reason": "OFFICIAL_MARKET_NOT_ON_SALE"}
        raw["verification_state"] = "VERIFIED"
        evidence = screenshot_store.ingest(raw).evidence
        self.assertIsNotNone(evidence)
        result = self.gate.evaluate(self.snapshot, evidence)
        self.assertFalse(result.accepted)
        self.assertEqual(MarketGateStatus.BLOCKED, result.decisions["rqspf"].status)
        self.assertEqual("FEED_SCREENSHOT_AVAILABILITY_CONFLICT", result.decisions["rqspf"].reason_code)

    def test_unknown_source_market_status_is_blocked_not_coerced(self):
        odds_store = OfficialOddsSnapshotStore(self.identity_store)
        raw = copy.deepcopy(self.odds_fixture["base"])
        raw["match_id"] = self.match_id
        raw["spf"] = None
        raw["market_availability"]["spf"] = {"available": False, "status": "UNKNOWN", "reason": "SOURCE_MARKET_STATE_UNKNOWN"}
        raw["market_unavailable_reason"]["spf"] = "SOURCE_MARKET_STATE_UNKNOWN"
        snapshot = odds_store.ingest(raw).snapshot
        result = self.gate.evaluate(snapshot)
        self.assertFalse(result.accepted)
        self.assertEqual(MarketGateStatus.BLOCKED, result.decisions["spf"].status)
        self.assertEqual("UNKNOWN", result.decisions["spf"].source_status)

    def test_gate_duplicate_is_noop(self):
        first = self.gate.evaluate(self.snapshot, self.screenshot)
        second = self.gate.evaluate(self.snapshot, self.screenshot)
        self.assertEqual(first.gate_id, second.gate_id)
        self.assertEqual(1, len(self.gate.results))
        self.assertEqual("DUPLICATE_NOOP", self.gate.events[-1]["action"])

    def test_missing_snapshot_is_rejected(self):
        with self.assertRaises(Exception):
            self.gate.evaluate(None)

    def test_v333_f_drive_and_no_migration_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.repo_root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-026/evidence.json")
        self.assertEqual("F:", output.drive.upper())


if __name__ == "__main__":
    unittest.main()
