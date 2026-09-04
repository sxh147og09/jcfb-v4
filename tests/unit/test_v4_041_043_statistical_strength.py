from __future__ import annotations

import copy
import json
import subprocess
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.canonical_intake import (
    AttackDefenceHomeAdvantageEngine,
    CanonicalMatchIdentityStore,
    DynamicTeamRatingEngine,
    FeatureBundle,
    HistoricalInputManifest,
    OpponentFormLeagueStrengthEngine,
    StatisticalFeatureState,
    StatisticalFeatureStore,
    StatisticalStrengthConfig,
    StatisticalStrengthValidationError,
    verify_feature_hash,
    resolve_f_drive_output_path,
)


class V4041ToV4043StatisticalStrengthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.cases = json.loads((cls.root / "tests/fixtures/v4_041_043/statistical_strength_cases.json").read_text(encoding="utf-8"))
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))["base"]

    def setUp(self):
        self.identities = CanonicalMatchIdentityStore()
        target_raw = copy.deepcopy(self.identity_fixture)
        target_raw["official_match_no"] = "TARGET-011"
        target_raw["data_date"] = "2026-09-04"
        target_raw["source_match_ref"] = "target-v4-011"
        target = self.identities.ingest(target_raw)
        self.assertTrue(target.accepted, target.to_dict())
        self.target_id = target.canonical_match_id
        assert target.envelope is not None
        self.target_hash = target.envelope.payload_hash
        self.source_ids = {}
        self.source_hashes = {}
        for index, source in enumerate(self.cases["source_matches"], start=1):
            raw = copy.deepcopy(self.identity_fixture)
            raw["official_match_no"] = f"SRC-{index:03d}"
            raw["data_date"] = "2026-08-01"
            raw["source_match_ref"] = source["source_match_id"]
            raw["kickoff_at"] = source["source_event_at"].replace("12:00:00+00:00", "12:05:00+00:00")
            raw["timezone"] = "UTC"
            result = self.identities.ingest(raw)
            self.assertTrue(result.accepted, result.to_dict())
            self.source_ids[source["source_match_id"]] = result.canonical_match_id
            assert result.envelope is not None
            self.source_hashes[source["source_match_id"]] = result.envelope.payload_hash
        self.config = StatisticalStrengthConfig.load_approved(self.root)
        self.feature_bundle = copy.deepcopy(self.bundle_fixture)
        self.feature_bundle["canonical_entity_refs"]["match_id"] = self.target_id
        self.feature_bundle["feature_snapshot_hash"] = "sha256:" + "1" * 64
        self.feature_bundle["input_hash"] = "sha256:" + "2" * 64

    def observation(self, source, *, team_id, side, kind, value, status="AVAILABLE", venue_status=None, index=0, opponent=None):
        event = source["source_event_at"]
        return {
            "historical_input_id": f"hist-{source['source_match_id']}-{team_id}-{kind}",
            "contract_version": "historical-statistical-input@1.0.0",
            "source_match_id": self.source_ids[source["source_match_id"]],
            "target_match_id": self.target_id,
            "source_match_identity_hash": self.source_hashes[source["source_match_id"]],
            "target_match_identity_hash": self.target_hash,
            "team_id": team_id,
            "competition_id": self.cases["target"]["competition_id"],
            "season_id": self.cases["target"]["season_id"],
            "competition_type": "LEAGUE",
            "side": side,
            "venue_status": venue_status or side,
            "observation_type": kind,
            "value": value,
            "unit": "points" if kind == "POINTS" else "goals",
            "source": "official-result-feed",
            "source_reference": f"ref://official/result/{index}",
            "evidence_refs": [{"evidence_id": f"evidence-{index}-{team_id}-{kind}", "evidence_hash": "sha256:" + str(index % 10) * 64}],
            "source_event_at": event,
            "result_known_at": event,
            "stat_available_at": event,
            "published_at": event,
            "observed_at": event,
            "retrieved_at": event,
            "ingested_at": event,
            "availability_at": event,
            "revision": 1,
            "revision_visible_at_cutoff": 1,
            "availability_status": status,
            "verification_state": "VERIFIED" if status == "AVAILABLE" else "NOT_VERIFIED",
            "quality_state": "AVAILABLE" if status == "AVAILABLE" else "UNKNOWN",
            "payload_hash": "sha256:" + str((index + 1) % 10) * 64,
            "provenance_hash": "sha256:" + str((index + 2) % 10) * 64,
            "content_hash": "sha256:" + str((index + 3) % 10) * 64,
            "opponent_team_id": opponent,
            "reason_code": "NOT_VERIFIED" if status != "AVAILABLE" else None,
            "reason_detail": "fixture unavailable" if status != "AVAILABLE" else None,
        }

    def observations(self, count=20):
        output = []
        for index, source in enumerate(self.cases["source_matches"][:count], start=1):
            output.extend(
                [
                    self.observation(source, team_id="team-home-001", side="HOME", kind="POINTS", value=source["home_points"], index=index, opponent="team-away-002"),
                    self.observation(source, team_id="team-home-001", side="HOME", kind="GOALS_FOR", value=source["home_goals_for"], index=index, opponent="team-away-002"),
                    self.observation(source, team_id="team-home-001", side="HOME", kind="GOALS_AGAINST", value=source["home_goals_against"], index=index, opponent="team-away-002"),
                    self.observation(source, team_id="team-away-002", side="AWAY", kind="POINTS", value=source["away_points"], index=index, opponent="team-home-001"),
                    self.observation(source, team_id="team-away-002", side="AWAY", kind="GOALS_FOR", value=source["away_goals_for"], index=index, opponent="team-home-001"),
                    self.observation(source, team_id="team-away-002", side="AWAY", kind="GOALS_AGAINST", value=source["away_goals_against"], index=index, opponent="team-home-001"),
                ]
            )
        return output

    def manifest(self, observations=None):
        return HistoricalInputManifest.build(
            target_match_id=self.target_id,
            target_match_identity_hash=self.target_hash,
            target_prediction_cutoff_at=self.cases["target"]["cutoff_at"],
            target_kickoff_at=self.cases["target"]["kickoff_at"],
            observations=self.observations() if observations is None else observations,
            config=self.config,
            identity_store=self.identities,
        )

    def test_manifest_is_target_scoped_and_windowed_by_source_match(self):
        manifest = self.manifest()
        self.assertEqual(20, len({item.source_match_id for item in manifest.for_team("team-home-001")}))
        self.assertEqual(20, len({item.source_match_id for item in manifest.for_team("team-away-002")}))
        self.assertEqual(self.target_id, manifest.target_match_id)
        self.assertEqual(self.config.config_hash, manifest.config_hash)
        self.assertTrue(manifest.input_hash.startswith("sha256:"))

    def test_v4041_dynamic_rating_is_available_and_replayable(self):
        manifest = self.manifest()
        engine = DynamicTeamRatingEngine(self.config)
        first = engine.generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        second = engine.generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, first.state)
        self.assertEqual(first.value, second.value)
        self.assertEqual(first.output_hash, second.output_hash)
        self.assertEqual(first.generator_version, "v4-041-dynamic-team-rating@1.0.0")
        self.assertTrue(verify_feature_hash(first))
        self.assertNotIn("prediction", json.dumps(first.to_dict()).casefold())

    def test_sparse_dynamic_rating_has_no_default_numeric_value(self):
        manifest = self.manifest(self.observations(count=4))
        feature = DynamicTeamRatingEngine(self.config).generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        self.assertEqual(StatisticalFeatureState.UNKNOWN, feature.state)
        self.assertIsNone(feature.value)
        self.assertEqual("INSUFFICIENT_SAMPLE", feature.reason_code)
        self.assertEqual("PARTIAL", feature.feature_quality.coverage)

    def test_v4042_attack_defence_and_home_advantage_are_typed(self):
        result = AttackDefenceHomeAdvantageEngine(self.config).generate(manifest=self.manifest(), team_id="team-home-001", feature_bundle=self.feature_bundle)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.attack.state)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.defence.state)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.home_advantage.state)
        self.assertEqual(20, result.home_advantage.usable_sample_count)
        self.assertEqual("goals_per_eligible_home_match", result.home_advantage.unit)
        self.assertTrue(all(verify_feature_hash(item) for item in result.features))

    def test_unknown_venue_blocks_home_advantage_without_fallback(self):
        observations = self.observations()
        observations[1]["venue_status"] = "UNKNOWN"
        manifest = self.manifest(observations)
        result = AttackDefenceHomeAdvantageEngine(self.config).generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        self.assertEqual(StatisticalFeatureState.BLOCKED, result.home_advantage.state)
        self.assertEqual("VENUE_UNKNOWN", result.home_advantage.reason_code)
        self.assertIsNone(result.home_advantage.value)

    def test_v4043_requires_v4041_v4042_lineage_and_preserves_typed_outputs(self):
        manifest = self.manifest()
        rating_engine = DynamicTeamRatingEngine(self.config)
        rating_home = rating_engine.generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        rating_away = rating_engine.generate(manifest=manifest, team_id="team-away-002", feature_bundle=self.feature_bundle)
        context = AttackDefenceHomeAdvantageEngine(self.config).generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        result = OpponentFormLeagueStrengthEngine(self.config).generate(
            manifest=manifest,
            team_id="team-home-001",
            feature_bundle=self.feature_bundle,
            upstream_features=(rating_home, rating_away, context.attack, context.defence),
        )
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.opponent_adjusted.state)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.form_decay.state)
        self.assertEqual(StatisticalFeatureState.AVAILABLE, result.league_strength.state)
        self.assertEqual(StatisticalFeatureState.NOT_APPLICABLE, result.transition.state)
        self.assertTrue(all(verify_feature_hash(item) for item in result.features))

    def test_transition_without_explicit_mapping_is_blocked(self):
        manifest = self.manifest()
        rating_engine = DynamicTeamRatingEngine(self.config)
        rating_home = rating_engine.generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        rating_away = rating_engine.generate(manifest=manifest, team_id="team-away-002", feature_bundle=self.feature_bundle)
        context = AttackDefenceHomeAdvantageEngine(self.config).generate(manifest=manifest, team_id="team-home-001", feature_bundle=self.feature_bundle)
        result = OpponentFormLeagueStrengthEngine(self.config).generate(
            manifest=manifest,
            team_id="team-home-001",
            feature_bundle=self.feature_bundle,
            upstream_features=(rating_home, rating_away, context.attack, context.defence),
            transition_required=True,
        )
        self.assertEqual(StatisticalFeatureState.BLOCKED, result.transition.state)
        self.assertEqual("TRANSITION_MAPPING_REQUIRED", result.transition.reason_code)

    def test_invalid_status_self_result_future_and_model_field_fail_closed(self):
        observations = self.observations(count=5)
        self_observation = copy.deepcopy(observations[0])
        self_observation["source_match_id"] = self.target_id
        future = copy.deepcopy(observations[1])
        future["availability_at"] = "2026-09-04T12:00:00+00:00"
        future["source_event_at"] = "2026-09-04T12:00:00+00:00"
        future["historical_input_id"] = "future-observation"
        forbidden = copy.deepcopy(observations[2])
        forbidden["historical_input_id"] = "forbidden-observation"
        forbidden["prediction"] = "HOME"
        invalid = copy.deepcopy(observations[3])
        invalid["historical_input_id"] = "invalid-status"
        invalid["availability_status"] = "MISSING"
        manifest = self.manifest(observations + [self_observation, future, forbidden, invalid])
        self.assertGreaterEqual(manifest.excluded_sample_counts["TARGET_SELF_RESULT_FORBIDDEN"], 1)
        self.assertGreaterEqual(manifest.excluded_sample_counts["FUTURE_DATA"], 1)
        self.assertGreaterEqual(manifest.excluded_sample_counts["MODEL_FIELD_FORBIDDEN"], 1)
        self.assertGreaterEqual(manifest.excluded_sample_counts["AVAILABILITY_STATUS_INVALID"], 1)

    def test_append_only_feature_store_and_f_drive_boundary(self):
        feature = DynamicTeamRatingEngine(self.config).generate(manifest=self.manifest(), team_id="team-home-001", feature_bundle=self.feature_bundle)
        store = StatisticalFeatureStore()
        self.assertEqual("APPEND", store.append(feature))
        self.assertEqual("DUPLICATE_NOOP", store.append(feature))
        changed = replace(feature, feature_id="corrected-feature-id", revision=2, supersedes_feature_id=feature.feature_id, value=(feature.value or 0) + 0.1)
        with self.assertRaises(StatisticalStrengthValidationError):
            store.append(changed)
        self.assertEqual("F:", resolve_f_drive_output_path(self.root, "runtime/v4-041/evidence.json").drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path(Path("C:/Projects/jcfb-v4"), "runtime/evidence.json")
        changed_paths = subprocess.run(["git", "diff", "--name-only", "0db7214"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed_paths))


if __name__ == "__main__":
    unittest.main()
