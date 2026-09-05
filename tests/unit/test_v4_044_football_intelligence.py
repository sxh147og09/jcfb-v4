from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    FeatureBundle,
    FeatureSnapshotHasher,
    FootballIntelligenceEngine,
    FootballIntelligenceStore,
    FootballIntelligenceValidationError,
)


class V4044FootballIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.cases = json.loads((cls.root / "tests/fixtures/v4_044/football_intelligence_engine_cases.json").read_text(encoding="utf-8"))
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))["base"]
        cls.config_engine = FootballIntelligenceEngine.from_repo_root(cls.root)

    def bundle(self) -> FeatureBundle:
        raw = copy.deepcopy(self.bundle_fixture)
        raw["canonical_entity_refs"]["match_id"] = "match-044-001"
        bundle = FeatureBundle.from_dict(raw)
        return FeatureSnapshotHasher.seal(bundle)

    def inputs(self):
        stats = copy.deepcopy(self.cases["statistical_features"])
        for item in stats:
            item["target_match_id"] = "match-044-001"
        contexts = copy.deepcopy(self.cases["context_observations"])
        for item in contexts:
            item["match_id"] = "match-044-001"
        return stats, contexts

    def test_v4044_generates_typed_pre_freeze_artifact(self):
        bundle = self.bundle()
        stats, contexts = self.inputs()
        artifact = self.config_engine.generate(feature_bundle=bundle, statistical_features=stats, context_observations=contexts)
        raw = artifact.to_dict()
        self.assertEqual("PRE_FREEZE_FEATURE_ARTIFACT", raw["artifact_kind"])
        self.assertEqual("football-intelligence-feature@1.0.0", raw["contract_version"])
        self.assertEqual(bundle.feature_snapshot_hash, raw["feature_bundle_ref"]["feature_snapshot_hash"])
        self.assertEqual({"041", "042", "043"}, {item["generator_version"].split("-", 2)[1] for item in raw["statistical_feature_refs"]})
        self.assertNotIn("frozen_input_id", raw)
        self.assertNotIn("frozen_input_hash", raw)
        serialized = json.dumps(raw).casefold()
        self.assertNotIn('"prediction":', serialized)
        self.assertNotIn('"recommendation":', serialized)
        self.assertNotIn('"model_confidence":', serialized)

    def test_type_a_numeric_observation_keeps_mapping_metadata(self):
        artifact = self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=self.inputs()[1])
        rest = next(item for item in artifact.features if item["feature_key"] == "rest_days")
        self.assertEqual("NUMERIC", rest["kind"])
        self.assertEqual(5, rest["value"])
        self.assertEqual("days", rest["unit"])
        self.assertEqual("NATIVE_UNIT", rest["normalization"])
        self.assertEqual("PRESERVE_STATE", self.config_engine.config["numeric_mappings"][0]["missing_behavior"])

    def test_type_b_projected_context_remains_categorical(self):
        artifact = self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=self.inputs()[1])
        lineup = next(item for item in artifact.features if item["feature_key"] == "lineup_state")
        self.assertEqual("CATEGORICAL", lineup["kind"])
        self.assertEqual("PROJECTED", lineup["context_state"])
        self.assertEqual("PROJECTED_LINEUP", lineup["value"])

    def test_missing_and_non_consumable_state_are_preserved(self):
        contexts = self.inputs()[1]
        contexts[0]["state"] = "UNKNOWN"
        contexts[0]["value"] = None
        contexts[0]["reason_code"] = "SOURCE_NOT_VERIFIED"
        contexts[0]["reason_detail"] = "The source did not verify the schedule value."
        artifact = self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=contexts)
        rest = next(item for item in artifact.features if item["feature_key"] == "rest_days")
        self.assertEqual("UNKNOWN", rest["state"])
        self.assertIsNone(rest["value"])
        self.assertEqual("SOURCE_NOT_VERIFIED", rest["reason_code"])

    def test_future_input_fails_closed_as_future_data(self):
        contexts = self.inputs()[1]
        contexts[0]["source_timestamp"] = "2026-09-04T20:00:00+08:00"
        contexts[0]["observed_at"] = "2026-09-04T20:01:00+08:00"
        contexts[0]["effective_at"] = "2026-09-04T20:01:00+08:00"
        artifact = self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=contexts)
        rest = next(item for item in artifact.features if item["feature_key"] == "rest_days")
        self.assertEqual("FUTURE_DATA", rest["state"])
        self.assertIsNone(rest["value"])
        self.assertEqual("POST_CUTOFF_INPUT", rest["reason_code"])

    def test_expired_input_fails_closed_as_stale(self):
        contexts = self.inputs()[1]
        contexts[0]["expires_at"] = "2026-09-04T08:00:00+08:00"
        artifact = self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=contexts)
        rest = next(item for item in artifact.features if item["feature_key"] == "rest_days")
        self.assertEqual("STALE", rest["state"])
        self.assertIsNone(rest["value"])
        self.assertEqual("SOURCE_EXPIRED", rest["reason_code"])

    def test_arbitrary_numeric_context_effect_is_rejected(self):
        contexts = self.inputs()[1]
        contexts[1]["kind"] = "NUMERIC"
        contexts[1]["value"] = 0.7
        with self.assertRaisesRegex(FootballIntelligenceValidationError, "must remain CATEGORICAL"):
            self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=self.inputs()[0], context_observations=contexts)

    def test_missing_statistical_lineage_is_rejected(self):
        stats, contexts = self.inputs()
        with self.assertRaisesRegex(FootballIntelligenceValidationError, "V4-041, V4-042, and V4-043"):
            self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=stats[:2], context_observations=contexts)

    def test_cutoff_and_identity_boundaries_are_rejected(self):
        stats, contexts = self.inputs()
        contexts[0]["team_id"] = "team-not-in-match"
        with self.assertRaisesRegex(FootballIntelligenceValidationError, "not in the canonical match"):
            self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=stats, context_observations=contexts)
        contexts = self.inputs()[1]
        contexts[0]["source_ref"] = {"id": "unlisted-context", "hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        with self.assertRaisesRegex(FootballIntelligenceValidationError, "not declared in the artifact envelope"):
            self.config_engine.generate(feature_bundle=self.bundle(), statistical_features=stats, context_observations=contexts)

    def test_append_only_store_requires_supersedes_for_correction(self):
        bundle = self.bundle()
        stats, contexts = self.inputs()
        artifact = self.config_engine.generate(feature_bundle=bundle, statistical_features=stats, context_observations=contexts)
        store = FootballIntelligenceStore(self.config_engine.config)
        self.assertEqual("APPEND", store.append(artifact))
        self.assertEqual("DUPLICATE_NOOP", store.append(artifact))
        changed_contexts = self.inputs()[1]
        changed_contexts[0]["value"] = 6
        corrected = self.config_engine.generate(
            feature_bundle=bundle,
            statistical_features=stats,
            context_observations=changed_contexts,
            revision=2,
            supersedes_artifact_id=artifact.artifact_id,
        )
        self.assertEqual("APPEND", store.append(corrected))
        invalid_revision = self.config_engine.generate(feature_bundle=bundle, statistical_features=stats, context_observations=changed_contexts, revision=3)
        with self.assertRaisesRegex(FootballIntelligenceValidationError, "supersedes"):
            store.append(invalid_revision)

    def test_f_drive_runtime_and_v3_isolation(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed_paths = subprocess.run(["git", "diff", "--name-only", "HEAD^"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed_paths))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed_paths))


if __name__ == "__main__":
    unittest.main()
