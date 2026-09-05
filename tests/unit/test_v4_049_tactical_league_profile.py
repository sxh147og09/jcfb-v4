from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake.context_feature_integration import ContextFeatureIntegrationEngine
from tools.canonical_intake.feature_bundle import FeatureBundle
from tools.canonical_intake.feature_snapshot import FeatureSnapshotHasher
from tools.canonical_intake.football_intelligence import FootballIntelligenceEngine
from tools.canonical_intake.tactical_league_profile import (
    ARTIFACT_KIND,
    CONTRACT_VERSION,
    TacticalLeagueProfileEngine,
    TacticalLeagueProfileStore,
    TacticalLeagueProfileValidationError,
)


class V4049TacticalLeagueProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))["base"]
        cls.football_fixture = json.loads((cls.root / "tests/fixtures/v4_044/football_intelligence_engine_cases.json").read_text(encoding="utf-8"))
        cls.context_fixture = json.loads((cls.root / "tests/fixtures/v4_045/context_feature_integration_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        bundle_raw = copy.deepcopy(self.bundle_fixture)
        bundle_raw["canonical_entity_refs"]["match_id"] = "match-049-001"
        self.bundle = FeatureSnapshotHasher.seal(FeatureBundle.from_dict(bundle_raw))
        stats = copy.deepcopy(self.football_fixture["statistical_features"])
        for item in stats:
            item["target_match_id"] = "match-049-001"
        contexts = copy.deepcopy(self.football_fixture["context_observations"])
        for item in contexts:
            item["match_id"] = "match-049-001"
        v4044 = FootballIntelligenceEngine.from_repo_root(self.root).generate(
            feature_bundle=self.bundle, statistical_features=stats, context_observations=contexts[:1]
        )
        extra = copy.deepcopy(self.context_fixture["additional_context"])
        extra["match_id"] = "match-049-001"
        self.context = ContextFeatureIntegrationEngine.from_repo_root(self.root).generate(
            football_intelligence_artifact=v4044, context_observations=[extra]
        )
        self.engine = TacticalLeagueProfileEngine.from_repo_root(self.root)

    def observations(self):
        return [
            {
                "feature_key": "tactical_matchup",
                "kind": "RELATIONAL",
                "value": {"home": "HIGH_PRESS", "away": "BUILD_UP", "relation": "PRESS_DISRUPTS_BUILD_UP"},
                "unit": "relation",
                "source_refs": ["context-001"],
                "basis_refs": ["evidence-001"],
                "source_timestamp": "2026-09-04T08:40:00+08:00",
                "required": True,
            },
            {
                "feature_key": "league_tactical_context_profile",
                "kind": "CATEGORICAL",
                "value": "TRANSITION_ORIENTED",
                "unit": "profile",
                "source_refs": ["context-001"],
                "basis_refs": ["evidence-001"],
                "source_timestamp": "2026-09-04T08:40:00+08:00",
            },
        ]

    def generate(self, observations=None, **kwargs):
        return self.engine.generate(
            feature_bundle=self.bundle,
            context_feature_artifact=self.context,
            observations=self.observations() if observations is None else observations,
            **kwargs,
        )

    def test_generates_typed_relations_with_lineage_and_no_arbitrary_score(self):
        artifact = self.generate()
        raw = artifact.to_dict()
        self.assertEqual(ARTIFACT_KIND, raw["artifact_kind"])
        self.assertEqual(CONTRACT_VERSION, raw["contract_version"])
        self.assertEqual("PRE_FREEZE_TACTICAL_LEAGUE_PROFILE", raw["artifact_kind"])
        self.assertEqual({"tactical_matchup", "league_tactical_context_profile"}, {item["feature_key"] for item in raw["features"]})
        self.assertEqual("RELATIONAL", raw["features"][0]["kind"])
        self.assertIn("context_feature_artifact_ref", raw)
        self.assertTrue(raw["input_hash"].startswith("sha256:"))
        self.assertTrue(raw["output_hash"].startswith("sha256:"))
        serialized = json.dumps(raw, ensure_ascii=False).casefold()
        self.assertNotIn("tactical_advantage_score", serialized)
        self.assertNotIn("league_adjustment_multiplier", serialized)
        self.assertNotIn('"prediction":', serialized)
        self.assertNotIn("frozen_input", serialized)

    def test_league_strength_and_numeric_tactical_effect_are_rejected(self):
        bad = self.observations()
        bad[0]["feature_key"] = "league_strength"
        with self.assertRaisesRegex(TacticalLeagueProfileValidationError, "approved typed relation|arbitrary"):
            self.generate(bad)
        bad = self.observations()
        bad[0]["feature_key"] = "tactical_advantage_score"
        with self.assertRaises(TacticalLeagueProfileValidationError):
            self.generate(bad)

    def test_unknown_conflict_and_future_states_remain_explicit(self):
        for state, reason in (("UNKNOWN", "FEATURE_NOT_VERIFIED"), ("CONFLICTED", "UNRESOLVED_FEATURE_CONFLICT"), ("FUTURE_DATA", "FUTURE_DATA")):
            item = self.observations()[0]
            item["state"] = state
            item["value"] = None
            item["reason_code"] = reason
            item["reason_detail"] = "The state remains explicit for the quality gate."
            if state == "FUTURE_DATA":
                item["source_timestamp"] = "2026-09-04T09:20:00+08:00"
            feature = next(value for value in self.generate([item]).to_dict()["features"] if value["feature_key"] == "tactical_matchup")
            self.assertEqual(state, feature["state"])
            self.assertIsNone(feature["value"])

    def test_missing_time_is_blocked_and_no_default_is_created(self):
        item = self.observations()[0]
        del item["source_timestamp"]
        artifact = self.generate([item])
        feature = artifact.to_dict()["features"][0]
        self.assertEqual("BLOCKED", feature["state"])
        self.assertEqual("SOURCE_TIMESTAMP_UNKNOWN", feature["reason_code"])
        self.assertIsNone(feature["value"])

    def test_cutoff_and_upstream_identity_are_fail_closed(self):
        item = self.observations()[0]
        item["source_timestamp"] = "2026-09-04T09:11:00+08:00"
        future = self.generate([item]).to_dict()["features"][0]
        self.assertEqual("FUTURE_DATA", future["state"])
        foreign = copy.deepcopy(self.context.to_dict())
        foreign["canonical_entity_refs"]["match_id"] = "another-match"
        with self.assertRaises(TacticalLeagueProfileValidationError):
            self.engine.generate(feature_bundle=self.bundle, context_feature_artifact=foreign, observations=self.observations())

    def test_deterministic_replay_and_hash_tamper_detection(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(first.artifact_id, second.artifact_id)
        self.assertEqual(first.output_hash, second.output_hash)
        raw = first.to_dict()
        raw["output_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(TacticalLeagueProfileValidationError, "recomputable"):
            from tools.canonical_intake.tactical_league_profile import TacticalLeagueProfileArtifact
            TacticalLeagueProfileArtifact.from_dict(raw, config=self.engine.config)

    def test_append_only_correction_requires_supersedes(self):
        base = self.generate()
        store = TacticalLeagueProfileStore(self.engine.config)
        self.assertEqual("APPEND", store.append(base))
        self.assertEqual("DUPLICATE_NOOP", store.append(base))
        corrected = self.generate(revision=2, supersedes_artifact_id=base.artifact_id)
        self.assertEqual("APPEND", store.append(corrected))
        invalid = self.generate(revision=3)
        with self.assertRaisesRegex(TacticalLeagueProfileValidationError, "prior artifact"):
            store.append(invalid)

    def test_f_drive_v3_isolation_and_no_migration_scope(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
