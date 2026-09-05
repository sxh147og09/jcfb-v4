from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.historical_source_archive import ACTIVATED_AT, ArchiveRuntime, GovernedArchiveReader
from src.prediction_training import DatasetBuildError, HistoricalAsOfDatasetBuilder


HASH = "sha256:" + "b" * 64
CONFIG_ROOT = Path("F:/Projects/jcfb-v4/config/prediction_training")


def execution_manifest() -> dict:
    return {
        "work_package_id": "B15-EWP-002",
        "execution_authorized": True,
        "downstream_execution_authorized": False,
        "forbidden_work_packages": ["B15-EWP-003", "B15-EWP-004", "B15-EWP-005"],
    }


class B15Ewp002DatasetBuilderTests(unittest.TestCase):
    def make_builder(self, project_root: Path) -> HistoricalAsOfDatasetBuilder:
        return HistoricalAsOfDatasetBuilder(
            project_root,
            reader=GovernedArchiveReader(project_root / "approved_data" / "historical_source_archive"),
            execution_manifest=execution_manifest(),
            config_root=CONFIG_ROOT,
            allow_test_root=True,
        )

    def test_empty_archive_produces_formal_zero_candidate_artifacts(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            result = self.make_builder(Path(temp)).build()
            self.assertEqual(0, result.manifest["archived_match_count"])
            self.assertEqual(0, result.manifest["candidate_match_count"])
            self.assertEqual(0, result.manifest["candidate_sample_count"])
            self.assertEqual(0, result.evidence["usable_training_sample_count"])
            self.assertEqual("ZERO_ARCHIVED_CANDIDATES", result.manifest["zero_archive_reason"])
            self.assertTrue(Path(result.formal_paths["dataset_artifact"]).is_file())
            self.assertEqual([], result.dataset_artifact["sample_refs"])
            replayed = self.make_builder(Path(temp)).build()
            self.assertEqual(result.manifest["dataset_id"], replayed.manifest["dataset_id"])
            self.assertEqual(result.manifest["manifest_hash"], replayed.manifest["manifest_hash"])

    def test_complete_match_builds_four_independent_role_samples(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            project_root = Path(temp)
            runtime = ArchiveRuntime(project_root, persist=True)
            identity = {"match_id": "match-001", "competition_id": "league-1", "home_team_id": "home", "away_team_id": "away"}
            execution = {"work_package_id": "B15-EWP-001", "execution_authorized": True, "execution_id": "ewp001-test", "execution_started_at": ACTIVATED_AT}
            times = {
                "source_timestamp": "2026-09-05T01:00:00+08:00", "observed_at": "2026-09-05T01:00:01+08:00",
                "captured_at": "2026-09-05T01:00:02+08:00", "ingested_at": "2026-09-05T01:00:03+08:00",
                "availability_at": "2026-09-05T01:00:00+08:00", "prediction_cutoff_at": "2026-09-05T02:00:00+08:00",
                "kickoff_at": "2026-09-05T03:00:00+08:00",
            }
            payloads = {
                "feature_bundle_ref": {"feature_bundle_ref": {"id": "fb-001", "hash": HASH}, "feature_snapshot_hash": HASH},
                "statistical_feature_artifact_ref": {"ref": "stat-001", "hash": HASH},
                "football_intelligence_ref": {"ref": "football-001", "hash": HASH},
                "market_intelligence_ref": {"ref": "market-001", "hash": HASH},
                "tactical_league_ref": {"ref": "tactical-001", "hash": HASH},
                "batch14_gate_record_ref": {"ref": "gate-001", "hash": HASH},
                "official_odds_snapshot": {"source_is_official": True, "rqspf": {"official_handicap": -0.25}},
            }
            artifacts = []
            for index, (artifact_type, payload) in enumerate(payloads.items()):
                artifacts.append(dict({"artifact_type": artifact_type, "source": "official", "source_identity": "official", "source_reference": f"ref://{artifact_type}/{index}", "payload": payload}, **times))
            captured = runtime.capture_pre_match(match_id="match-001", match_identity=identity, cutoff_profile="T_MINUS_60M", artifacts=artifacts, execution_context=execution)
            self.assertEqual("CAPTURED", captured.state)
            label = runtime.append_post_match_labels(
                match_id="match-001", match_identity=identity, cutoff_profile="T_MINUS_60M",
                labels={"final_score": "2:1", "half_time_score": "1:0", "outcome": "H", "goals": 3, "htft": "H/H"},
                source="official-result", source_reference="ref://result/001", source_timestamp="2026-09-05T05:00:00+08:00",
                captured_at="2026-09-05T05:00:01+08:00", ingested_at="2026-09-05T05:00:02+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=execution,
            )
            self.assertTrue(label.accepted)
            result = self.make_builder(project_root).build()
            self.assertEqual(1, result.manifest["candidate_match_count"])
            self.assertEqual(4, result.manifest["candidate_sample_count"])
            self.assertEqual({role: 1 for role in ("OUTCOME", "HANDICAP", "GOALS", "HTFT")}, result.manifest["eligible_counts_by_engine"])
            self.assertEqual(4, len(result.manifest["sample_records"]))
            self.assertTrue(all(sample["feature_snapshot_hash"] == HASH for sample in result.manifest["sample_records"]))
            self.assertTrue(all("final_score" not in sample for sample in result.manifest["sample_records"]))
            correction = self.make_builder(project_root).build()
            self.assertEqual(2, correction.manifest["revision"])
            self.assertTrue(all(sample["revision"] == 2 for sample in correction.manifest["sample_records"]))
            self.assertIsNotNone(correction.manifest["supersedes"])

    def test_replay_requires_exact_lineage_and_rejects_latest_fallback(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            builder = self.make_builder(Path(temp))
            context = {
                "raw_cutoff_visible_inputs_complete": True,
                "exact_generator_version": "generator@1.0.0",
                "exact_generator_implementation_hash": True,
                "exact_generator_implementation_hash_value": HASH,
                "exact_config_version": "config@1.0.0",
                "exact_config_hash": True,
                "exact_config_hash_value": HASH,
                "exact_mapping_version": "mapping@1.0.0",
                "exact_mapping_hash": True,
                "exact_mapping_hash_value": HASH,
                "source_timestamps_valid": True,
                "no_post_cutoff_revision": True,
            }
            replay, reasons = builder._reconstruction({"capture_state": "INVALID", "eligibility_state": "UNKNOWN" , "replay_context": context})
            self.assertEqual("DETERMINISTIC_HISTORICAL_REPLAY", replay["path"])
            self.assertEqual([], reasons)
            latest, _ = builder._reconstruction({"capture_state": "INVALID", "eligibility_state": "UNKNOWN", "replay_context": dict(context, used_latest_generator=True)})
            self.assertEqual("NONE", latest["path"])

    def test_missing_rqspf_only_blocks_handicap(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            project_root = Path(temp)
            runtime = ArchiveRuntime(project_root, persist=True)
            identity = {"match_id": "match-002", "competition_id": "league-1", "home_team_id": "home", "away_team_id": "away"}
            execution = {"work_package_id": "B15-EWP-001", "execution_authorized": True, "execution_id": "ewp001-test", "execution_started_at": ACTIVATED_AT}
            times = {"source_timestamp": "2026-09-05T01:00:00+08:00", "observed_at": "2026-09-05T01:00:01+08:00", "captured_at": "2026-09-05T01:00:02+08:00", "ingested_at": "2026-09-05T01:00:03+08:00", "availability_at": "2026-09-05T01:00:00+08:00", "prediction_cutoff_at": "2026-09-05T02:00:00+08:00", "kickoff_at": "2026-09-05T03:00:00+08:00"}
            artifacts = []
            payloads = {
                "feature_bundle_ref": {"feature_bundle_ref": {"id": "fb-002", "hash": HASH}, "feature_snapshot_hash": HASH},
                "statistical_feature_artifact_ref": {"ref": "stat-002", "hash": HASH}, "football_intelligence_ref": {"ref": "football-002", "hash": HASH}, "market_intelligence_ref": {"ref": "market-002", "hash": HASH}, "tactical_league_ref": {"ref": "tactical-002", "hash": HASH}, "batch14_gate_record_ref": {"ref": "gate-002", "hash": HASH},
            }
            for artifact_type, payload in payloads.items():
                artifacts.append(dict({"artifact_type": artifact_type, "source": "official", "source_identity": "official", "source_reference": f"ref://{artifact_type}/002", "payload": payload}, **times))
            self.assertEqual("CAPTURED", runtime.capture_pre_match(match_id="match-002", match_identity=identity, cutoff_profile="T_MINUS_60M", artifacts=artifacts, execution_context=execution).state)
            self.assertTrue(runtime.append_post_match_labels(match_id="match-002", match_identity=identity, cutoff_profile="T_MINUS_60M", labels={"final_score": "1:0", "half_time_score": "0:0", "outcome": "H", "goals": 1, "htft": "D/H"}, source="official-result", source_reference="ref://result/002", source_timestamp="2026-09-05T05:00:00+08:00", captured_at="2026-09-05T05:00:01+08:00", ingested_at="2026-09-05T05:00:02+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=execution).accepted)
            result = self.make_builder(project_root).build()
            self.assertEqual(1, result.manifest["eligible_counts_by_engine"]["OUTCOME"])
            self.assertEqual(1, result.manifest["eligible_counts_by_engine"]["GOALS"])
            self.assertEqual("B15-EWP-002-DATASET-MANIFEST", result.manifest["manifest_type"])
            self.assertEqual(1, result.manifest["ineligible_counts_by_engine"]["HANDICAP"])
            self.assertIn("OFFICIAL_RQSPF_MISSING", result.lineage_manifest["candidates"][0]["roles"]["HANDICAP"]["reasons"])

    def test_unauthorized_and_c_drive_execution_fail_closed(self):
        with self.assertRaises(DatasetBuildError):
            HistoricalAsOfDatasetBuilder("C:/jcfb-v4", execution_manifest=execution_manifest(), config_root=CONFIG_ROOT)
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            with self.assertRaises(DatasetBuildError):
                self.make_builder(Path(temp)).__class__(Path(temp), reader=GovernedArchiveReader(Path(temp) / "approved_data" / "historical_source_archive"), execution_manifest={"work_package_id": "B15-EWP-002", "execution_authorized": False}, config_root=CONFIG_ROOT, allow_test_root=True).build()


if __name__ == "__main__":
    unittest.main()
