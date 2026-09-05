from __future__ import annotations

import copy
import json
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    ExternalEuropean1X2Adapter,
    MarketIntelligenceEngine,
    MarketIntelligenceStore,
    OfficialOddsSnapshotStore,
)


class V4046MarketIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))
        cls.official_fixture = json.loads((cls.root / "tests/fixtures/v4_024/official_odds_cases.json").read_text(encoding="utf-8"))["base"]
        cls.external_fixture = json.loads((cls.root / "tests/fixtures/v4_028/external_european_1x2_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixture = json.loads((cls.root / "tests/fixtures/v4_046/market_intelligence_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity_result = self.identity_store.ingest(copy.deepcopy(self.identity_fixture["base"]))
        self.match_id = identity_result.canonical_match_id
        self.assertIsNotNone(self.match_id)
        self.engine = MarketIntelligenceEngine.from_repo_root(self.root, self.identity_store)

    def official_snapshot(self):
        raw = copy.deepcopy(self.official_fixture)
        raw["match_id"] = self.match_id
        result = OfficialOddsSnapshotStore(self.identity_store).ingest(raw)
        self.assertTrue(result.accepted)
        return result.snapshot

    def external_snapshot(self, *, source_timestamp: str | None = None, status: str | None = None):
        raw = copy.deepcopy(self.external_fixture)
        raw["match_id"] = self.match_id
        if source_timestamp is not None:
            raw["source_timestamp"] = source_timestamp
            if source_timestamp != "UNKNOWN":
                raw["captured_at"] = source_timestamp
                raw["observed_at"] = source_timestamp
                raw["ingested_at"] = source_timestamp
                raw["created_at"] = source_timestamp
        if status is not None:
            raw["availability_status"] = status
            raw["prices"] = None
            raw["reason_code"] = "SOURCE_CONFLICTED" if status == "CONFLICT" else "MARKET_NOT_AVAILABLE"
            raw["reason_detail"] = "The accepted upstream snapshot retained an explicit non-available state."
        result = ExternalEuropean1X2Adapter(self.identity_store).ingest(raw)
        self.assertTrue(result.accepted)
        return result.snapshot

    def test_official_snapshot_normalizes_all_five_markets(self):
        result = self.engine.normalize_snapshot(self.official_snapshot(), self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertTrue(result.accepted)
        self.assertEqual(5, len(result.artifacts))
        self.assertEqual({"SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HALF_FULL"}, {item.market for item in result.artifacts})
        for artifact in result.artifacts:
            self.assertTrue(artifact.source_is_official)
            self.assertEqual("CHINA_SPORTS_LOTTERY", artifact.provider)
            self.assertEqual("AVAILABLE", artifact.state)
            self.assertEqual(self.match_id, artifact.canonical_match_id)
            self.assertTrue(artifact.input_hash.startswith("sha256:"))
            self.assertTrue(artifact.output_hash.startswith("sha256:"))

    def test_external_snapshot_preserves_external_role_and_typed_quote(self):
        result = self.engine.normalize_snapshot(self.external_snapshot(), self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        artifact = result.artifacts[0]
        self.assertTrue(result.accepted)
        self.assertFalse(artifact.source_is_official)
        self.assertEqual("EUROPEAN_1X2", artifact.market)
        self.assertEqual("NOT_APPLICABLE", artifact.semantic_line)
        self.assertEqual("external_market_quote", artifact.unit)
        self.assertEqual({"line", "prices"}, set(artifact.typed_value))
        self.assertNotIn("probability", json.dumps(artifact.to_dict()).casefold())

    def test_latest_eligible_uses_source_time_and_same_scope(self):
        first = self.external_snapshot(source_timestamp="2026-09-04T09:10:30+08:00")
        second = self.external_snapshot(source_timestamp="2026-09-04T09:20:30+08:00")
        first_artifact = self.engine.normalize_snapshot(first, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        second_artifact = self.engine.normalize_snapshot(second, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        store = MarketIntelligenceStore()
        store.append(first_artifact)
        store.append(second_artifact)
        latest = store.latest_eligible(self.match_id, "EUROPEAN_1X2", "Example External Provider", "NOT_APPLICABLE", self.fixture["cutoff_at"])
        self.assertEqual(second_artifact.artifact_id, latest.artifact_id)

    def test_future_and_unresolved_source_time_fail_closed(self):
        future = self.external_snapshot(source_timestamp="2026-09-04T09:50:00+08:00")
        future_result = self.engine.normalize_snapshot(future, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertEqual("FUTURE_DATA", future_result.artifacts[0].state)
        self.assertEqual("POST_CUTOFF_SNAPSHOT", future_result.artifacts[0].reason_code)
        unresolved = self.external_snapshot(source_timestamp="UNKNOWN")
        unresolved_result = self.engine.normalize_snapshot(unresolved, self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertEqual("BLOCKED", unresolved_result.artifacts[0].state)
        self.assertEqual("SOURCE_TIME_UNRESOLVED", unresolved_result.artifacts[0].reason_code)

    def test_conflict_evidence_is_not_dropped(self):
        raw = copy.deepcopy(self.external_fixture)
        raw["match_id"] = self.match_id
        raw["availability_status"] = "CONFLICT"
        raw["prices"] = None
        raw["reason_code"] = "SOURCE_CONFLICTED"
        raw["reason_detail"] = "Two accepted source claims disagree."
        raw["conflict_evidence"] = [
            {
                "provider": "Provider A",
                "source": "Feed A",
                "source_ref": "ref://a",
                "market": "EUROPEAN_1X2",
                "line": "NOT_APPLICABLE",
                "prices": {"home": 2.0, "draw": 3.2, "away": 3.4},
                "source_timestamp": "2026-09-04T09:10:00+08:00",
                "captured_at": "2026-09-04T09:10:01+08:00",
                "provenance_ref": "ref://a/provenance",
                "observation_id": "obs-a"
            },
            {
                "provider": "Provider B",
                "source": "Feed B",
                "source_ref": "ref://b",
                "market": "EUROPEAN_1X2",
                "line": "NOT_APPLICABLE",
                "prices": {"home": 2.2, "draw": 3.1, "away": 3.1},
                "source_timestamp": "2026-09-04T09:10:02+08:00",
                "captured_at": "2026-09-04T09:10:03+08:00",
                "provenance_ref": "ref://b/provenance",
                "observation_id": "obs-b"
            }
        ]
        snapshot_result = ExternalEuropean1X2Adapter(self.identity_store).ingest(raw)
        self.assertTrue(snapshot_result.accepted)
        artifact = self.engine.normalize_snapshot(snapshot_result.snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        self.assertEqual("CONFLICTED", artifact.state)
        self.assertEqual(2, len(artifact.typed_value["conflict_evidence"]))

    def test_identity_and_cutoff_boundaries_block_without_orphan(self):
        foreign_identity_store = CanonicalMatchIdentityStore()
        foreign_engine = MarketIntelligenceEngine.from_repo_root(self.root, foreign_identity_store)
        result = foreign_engine.normalize_snapshot(self.external_snapshot(), self.fixture["cutoff_at"], self.fixture["kickoff_at"])
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)

    def test_append_only_correction_requires_supersedes(self):
        snapshot = self.external_snapshot()
        artifact = self.engine.normalize_snapshot(snapshot, self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        store = MarketIntelligenceStore()
        self.assertEqual("APPEND", store.append(artifact))
        self.assertEqual("DUPLICATE_NOOP", store.append(artifact))
        invalid = replace(artifact, artifact_id="invalid-revision-artifact", revision=2)
        with self.assertRaisesRegex(Exception, "supersedes"):
            store.append(invalid)
        self.assertEqual(1, len(store.artifacts))

    def test_pre_freeze_and_model_boundaries_are_explicit(self):
        artifact = self.engine.normalize_snapshot(self.external_snapshot(), self.fixture["cutoff_at"], self.fixture["kickoff_at"]).artifacts[0]
        raw = json.dumps(artifact.to_dict(), ensure_ascii=False).casefold()
        self.assertEqual("PRE_FREEZE_MARKET_INTELLIGENCE_ARTIFACT", artifact.artifact_kind)
        self.assertEqual("market-intelligence-feature@1.0.0", artifact.contract_version)
        self.assertNotIn("frozen_input_id", raw)
        self.assertNotIn("frozen_input_hash", raw)
        self.assertNotIn("recommendation", raw)
        self.assertNotIn("score_engine", raw)
        self.assertNotIn("trap_risk_score", raw)

    def test_f_drive_and_v3_isolation(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
