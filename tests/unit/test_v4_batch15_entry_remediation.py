from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.historical_source_archive import ACTIVATED_AT, ArchiveRuntime, GovernedArchiveReader, select_reconstruction_path
from src.prediction_training_contract import evaluate_engine_eligibility, sha256_json, substantive_hash, validate_training_sample


HASH = "sha256:" + "a" * 64


def valid_sample(role: str = "OUTCOME") -> dict:
    return {
        "training_sample_id": "sample-001",
        "match_id": "match-001",
        "cutoff_profile": "T_MINUS_60M",
        "prediction_cutoff_at": "2026-09-05T02:00:00+00:00",
        "kickoff_at": "2026-09-05T03:00:00+00:00",
        "source_availability_at": "2026-09-05T01:00:00+00:00",
        "feature_bundle_ref": "fb-001",
        "feature_bundle_hash": HASH,
        "feature_snapshot_hash": HASH,
        "statistical_ref": "stat-001",
        "statistical_hash": HASH,
        "football_ref": "football-001",
        "football_hash": HASH,
        "market_ref": "market-001",
        "market_hash": HASH,
        "tactical_ref": "tactical-001",
        "tactical_hash": HASH,
        "gate_record_ref": "gate-001",
        "gate_record_hash": HASH,
        "source_refs": ["source-001"],
        "evidence_refs": ["evidence-001"],
        "provenance_refs": ["provenance-001"],
        "engine_role": role,
        "eligibility_state": "ELIGIBLE",
        "exclusion_or_block_reason": None,
        "label_ref": "label-001",
        "label_hash": HASH,
        "builder_version": "dataset-builder@4.0.0",
        "builder_hash": HASH,
        "dataset_version": "prediction-training-dataset@1.1.0#r001",
        "input_hash": HASH,
        "sample_hash": HASH,
        "provenance_hash": HASH,
        "revision": 1,
        "supersedes": None,
    }


class Batch15EntryRemediationTests(unittest.TestCase):
    def test_alias_rejection_and_four_engine_handicap_separation(self):
        sample = valid_sample()
        sample["sample_id"] = "ambiguous"
        self.assertIn("FIELD_ALIAS_AMBIGUOUS:sample_id", validate_training_sample(sample))
        result = evaluate_engine_eligibility(valid_sample())
        self.assertEqual({"OUTCOME": "ELIGIBLE", "HANDICAP": "INELIGIBLE", "GOALS": "ELIGIBLE", "HTFT": "ELIGIBLE"}, result)
        handicap = valid_sample("HANDICAP")
        handicap.update({
            "official_rqspf_snapshot_ref": "rqspf-001",
            "official_rqspf_snapshot_hash": HASH,
            "official_handicap_value": -0.25,
            "handicap_sign_convention": "home_minus_away",
        })
        self.assertFalse(validate_training_sample(handicap))

    def test_substantive_hash_excludes_volatile_fields(self):
        candidate = {
            "archive_snapshot_identity": "snapshot-001", "archive_snapshot_hash": HASH,
            "cutoff_profile": "T_MINUS_60M", "builder_version": "builder@4.0.0", "builder_hash": HASH,
            "dataset_schema_version": "schema@1.1.0", "dataset_schema_hash": HASH,
            "replay_policy_version": "replay@1.0.0", "replay_policy_hash": HASH,
            "sample_membership": ["sample-001"], "eligibility": {"OUTCOME": "ELIGIBLE"},
            "execution_timestamp": "2026-09-05T09:00:00+00:00", "host_specific_absolute_path": "C:\\secret",
        }
        changed = dict(candidate, execution_timestamp="2026-09-05T09:01:00+00:00", host_specific_absolute_path="F:\\other")
        self.assertEqual(substantive_hash(candidate), substantive_hash(changed))
        changed["sample_membership"] = ["sample-002"]
        self.assertNotEqual(substantive_hash(candidate), substantive_hash(changed))

    def test_replay_prefers_stored_and_rejects_latest_or_incomplete_replay(self):
        stored = select_reconstruction_path({
            "archive_record_id": "asa-001", "artifact_hash": HASH, "revision": 1,
            "capture_state": "CAPTURED", "eligibility_state": "ELIGIBLE_FOR_AS_OF_TRAINING",
        }, {})
        self.assertEqual("STORED_ACCEPTED_ARTIFACT", stored["path"])
        latest = select_reconstruction_path({}, {"used_latest_generator": True, "used_latest_config": False})
        self.assertEqual("INELIGIBLE_FOR_TRAINING", latest["status"])
        incomplete = select_reconstruction_path({}, {"raw_cutoff_visible_inputs_complete": True})
        self.assertEqual("INELIGIBLE_FOR_TRAINING", incomplete["status"])

    def test_read_interface_is_deterministic_cutoff_bound_and_read_only(self):
        with tempfile.TemporaryDirectory(dir="F:/Projects/jcfb-v4/approved_data") as temp:
            project_root = Path(temp)
            runtime = ArchiveRuntime(project_root, persist=True)
            execution = {"work_package_id": "B15-EWP-001", "execution_authorized": True, "execution_id": "test", "execution_started_at": ACTIVATED_AT}
            identity = {"match_id": "match-001", "competition_id": "league-1", "home_team_id": "home", "away_team_id": "away"}
            base = {
                "artifact_type": "feature_bundle_ref", "source": "official", "source_identity": "official",
                "source_reference": "ref://feature/001", "logical_artifact_key": "feature-001",
                "source_timestamp": "2026-09-05T01:00:00+08:00", "observed_at": "2026-09-05T01:00:00+08:00",
                "captured_at": "2026-09-05T01:00:01+08:00", "ingested_at": "2026-09-05T01:00:02+08:00",
                "availability_at": "2026-09-05T01:00:00+08:00", "prediction_cutoff_at": "2026-09-05T02:00:00+08:00",
                "kickoff_at": "2026-09-05T03:00:00+08:00", "payload": {"feature_bundle_ref": "fb-001"},
            }
            first = runtime.capture_pre_match(match_id="match-001", match_identity=identity, cutoff_profile="T_MINUS_60M", artifacts=[base], execution_context=execution).records[0]
            correction = dict(base)
            correction.update({
                "source_timestamp": "2026-09-05T02:30:00+08:00", "observed_at": "2026-09-05T02:30:00+08:00",
                "captured_at": "2026-09-05T02:30:01+08:00", "ingested_at": "2026-09-05T02:30:02+08:00",
                "availability_at": "2026-09-05T02:30:00+08:00", "prediction_cutoff_at": "2026-09-05T03:00:00+08:00",
                "payload": {"feature_bundle_ref": "fb-002"}, "supersedes": first["archive_record_id"], "revision": 2,
            })
            runtime.capture_pre_match(match_id="match-001", match_identity=identity, cutoff_profile="T_MINUS_60M", artifacts=[correction], execution_context=execution)
            runtime.append_post_match_labels(match_id="match-001", match_identity=identity, cutoff_profile="T_MINUS_60M", labels={"final_score": "1:0"}, source="official-result", source_reference="ref://result/001", source_timestamp="2026-09-05T04:00:00+08:00", captured_at="2026-09-05T04:00:01+08:00", ingested_at="2026-09-05T04:00:02+08:00", kickoff_at="2026-09-05T03:00:00+08:00", execution_context=execution)
            reader = GovernedArchiveReader(runtime.archive_root)
            visible = reader.query_by_match_id("match-001", cutoff_profile="T_MINUS_60M", domain="pre_match", prediction_cutoff_at="2026-09-05T02:00:00+00:00")
            self.assertEqual(1, len(visible))
            self.assertEqual(1, visible[0]["revision"])
            snapshot = reader.deterministic_candidate_snapshot(match_id="match-001", cutoff_profile="T_MINUS_60M", prediction_cutoff_at="2026-09-05T02:00:00+00:00")
            self.assertEqual(1, len(snapshot["pre_match"]))
            self.assertEqual(1, len(snapshot["post_match_labels"]))
            self.assertTrue(snapshot["snapshot_hash"].startswith("sha256:"))
            self.assertFalse(hasattr(reader, "records"))
            self.assertFalse(hasattr(reader, "manifests"))
            self.assertEqual(first["archive_record_id"], reader.resolve_supersedes_chain(visible[0]["archive_record_id"])[0]["archive_record_id"])


if __name__ == "__main__":
    unittest.main()
