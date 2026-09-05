from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    ContextFeatureIntegrationEngine,
    ContextFeatureIntegrationStore,
    ContextFeatureIntegrationValidationError,
    FeatureBundle,
    FeatureSnapshotHasher,
    FootballIntelligenceEngine,
)


class V4045ContextFeatureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.case = json.loads((cls.root / "tests/fixtures/v4_045/context_feature_integration_cases.json").read_text(encoding="utf-8"))
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))["base"]
        cls.v4044_cases = json.loads((cls.root / "tests/fixtures/v4_044/football_intelligence_engine_cases.json").read_text(encoding="utf-8"))
        cls.v4044_engine = FootballIntelligenceEngine.from_repo_root(cls.root)
        cls.engine = ContextFeatureIntegrationEngine.from_repo_root(cls.root)

    def _bundle(self) -> FeatureBundle:
        raw = copy.deepcopy(self.bundle_fixture)
        raw["canonical_entity_refs"]["match_id"] = "match-045-001"
        return FeatureSnapshotHasher.seal(FeatureBundle.from_dict(raw))

    def _inputs(self):
        stats = copy.deepcopy(self.v4044_cases["statistical_features"])
        for item in stats:
            item["target_match_id"] = "match-045-001"
        contexts = copy.deepcopy(self.v4044_cases["context_observations"])
        for item in contexts:
            item["match_id"] = "match-045-001"
        return stats, contexts

    def _v4044(self):
        stats, contexts = self._inputs()
        return self.v4044_engine.generate(
            feature_bundle=self._bundle(),
            statistical_features=stats,
            context_observations=contexts[:1],
        )

    def _extra(self):
        raw = copy.deepcopy(self.case["additional_context"])
        raw["match_id"] = "match-045-001"
        return raw

    def test_generates_typed_integration_bound_to_v4044_and_bundle(self):
        artifact = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()])
        raw = artifact.to_dict()
        self.assertEqual("football-context-integration@1.0.0", raw["contract_version"])
        self.assertEqual("v4-045-context-integration@1.0.0", raw["generator_version"])
        self.assertEqual("match-045-001", raw["canonical_entity_refs"]["match_id"])
        self.assertEqual("PRE_FREEZE_FEATURE_ARTIFACT", self._v4044().to_dict()["artifact_kind"])
        self.assertNotIn("frozen_input_id", raw)
        self.assertNotIn("frozen_input_hash", raw)
        self.assertTrue(raw["input_hash"].startswith("sha256:"))
        self.assertTrue(raw["output_hash"].startswith("sha256:"))
        self.assertTrue(raw["provenance_hash"].startswith("sha256:"))

    def test_existing_and_additional_context_are_merged_without_overwrite(self):
        artifact = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()])
        keys = {(item["feature_key"], item.get("team_id"), item.get("side")) for item in artifact.features}
        self.assertIn(("rest_days", "team-home-001", "HOME"), keys)
        self.assertIn(("lineup_state", "team-away-002", "AWAY"), keys)
        lineup = next(item for item in artifact.features if item["feature_key"] == "lineup_state")
        self.assertEqual("CATEGORICAL", lineup["kind"])
        self.assertEqual("PROJECTED", lineup["context_state"])

    def test_unknown_conflicted_stale_future_and_blocked_remain_non_consumable(self):
        for state, reason in (
            ("UNKNOWN", "SOURCE_NOT_VERIFIED"),
            ("CONFLICTED", "CONFLICTING_CLAIMS"),
            ("STALE", "SOURCE_EXPIRED"),
            ("FUTURE_DATA", "POST_CUTOFF_INPUT"),
            ("BLOCKED", "QUALITY_GATE_BLOCKED"),
        ):
            extra = self._extra()
            extra["state"] = state
            extra["value"] = None
            extra["reason_code"] = reason
            extra["reason_detail"] = f"Explicit {state.lower()} state remains unresolved."
            if state == "STALE":
                extra["expires_at"] = "2026-09-04T08:00:00+08:00"
            if state == "FUTURE_DATA":
                extra["effective_at"] = "2026-09-04T10:00:00+08:00"
            artifact = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])
            feature = next(item for item in artifact.features if item["feature_key"] == "lineup_state")
            self.assertEqual(state, feature["state"])
            self.assertIsNone(feature["value"])
            self.assertEqual(reason, feature["reason_code"])

    def test_missing_reason_or_replacement_value_fails_closed(self):
        extra = self._extra()
        extra["state"] = "UNKNOWN"
        extra["value"] = None
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "reason_code"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])
        extra["reason_code"] = "SOURCE_NOT_VERIFIED"
        extra["reason_detail"] = "The source did not verify this context."
        extra["value"] = "SILENT_DEFAULT"
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "replacement value"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])

    def test_bare_confidence_and_model_fields_are_rejected(self):
        extra = self._extra()
        extra["confidence"] = 0.9
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "confidence"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])
        raw = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()]).to_dict()
        raw["features"][0]["prediction"] = "1X"
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "contains .*prediction"):
            from tools.canonical_intake import load_approved_config
            from tools.canonical_intake.context_feature_integration import ContextFeatureIntegrationArtifact
            ContextFeatureIntegrationArtifact.from_dict(raw, config=load_approved_config(self.root))

    def test_feature_collision_cannot_overwrite_v4044(self):
        extra = self._extra()
        extra["feature_key"] = "rest_days"
        extra["kind"] = "NUMERIC"
        extra["category"] = "schedule"
        extra["value"] = 7
        extra["unit"] = "days"
        extra["team_id"] = "team-home-001"
        extra["side"] = "HOME"
        extra["context_state"] = "CONFIRMED"
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "would overwrite"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])

    def test_identity_and_source_boundaries_are_rejected(self):
        extra = self._extra()
        extra["match_id"] = "orphan-match"
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "canonical match"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])
        extra = self._extra()
        extra["source_ref"] = {"id": "unlisted", "hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "declared in the artifact envelope"):
            self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[extra])

    def test_hashes_and_deterministic_identity_are_recomputed(self):
        first = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()])
        second = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()])
        self.assertEqual(first.integration_id, second.integration_id)
        self.assertEqual(first.input_hash, second.input_hash)
        raw = first.to_dict()
        raw["output_hash"] = "sha256:" + "0" * 64
        from tools.canonical_intake import load_approved_config
        from tools.canonical_intake.context_feature_integration import ContextFeatureIntegrationArtifact
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "not recomputable"):
            ContextFeatureIntegrationArtifact.from_dict(raw, config=load_approved_config(self.root))

    def test_append_only_store_requires_supersedes(self):
        base = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()])
        store = ContextFeatureIntegrationStore(self.engine.config)
        self.assertEqual("APPEND", store.append(base))
        self.assertEqual("DUPLICATE_NOOP", store.append(base))
        changed = self._extra()
        changed["value"] = "PROJECTED_LINEUP_UPDATED"
        corrected = self.engine.generate(
            football_intelligence_artifact=self._v4044(),
            context_observations=[changed],
            revision=2,
            supersedes_integration_id=base.integration_id,
        )
        self.assertEqual("APPEND", store.append(corrected))
        invalid = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[changed], revision=3)
        with self.assertRaisesRegex(ContextFeatureIntegrationValidationError, "supersede"):
            store.append(invalid)

    def test_no_context_confidence_or_frozen_lifecycle_leakage(self):
        raw = self.engine.generate(football_intelligence_artifact=self._v4044(), context_observations=[self._extra()]).to_dict()
        serialized = json.dumps(raw, sort_keys=True).casefold()
        self.assertNotIn('"confidence"', serialized)
        self.assertNotIn('"prediction"', serialized)
        self.assertNotIn("frozen_input", serialized)
        self.assertNotIn("formal_engine_output", serialized)

    def test_f_drive_v3_isolation_and_no_migration_scope(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed_paths = subprocess.run(["git", "diff", "--name-only", "HEAD^"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed_paths))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed_paths))


if __name__ == "__main__":
    unittest.main()
