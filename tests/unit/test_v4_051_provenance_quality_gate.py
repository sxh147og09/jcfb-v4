from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake.context_feature_integration import ContextFeatureIntegrationEngine
from tools.canonical_intake.data_quality_assessment import DataQualityAssessmentEngine
from tools.canonical_intake.feature_bundle import FeatureBundle
from tools.canonical_intake.feature_snapshot import FeatureSnapshotHasher
from tools.canonical_intake.football_intelligence import FootballIntelligenceEngine
from tools.canonical_intake.provenance_quality_gate import (
    ARTIFACT_KIND,
    CONTRACT_VERSION,
    ProvenanceQualityGateEngine,
    ProvenanceQualityGateStore,
    ProvenanceQualityGateValidationError,
)
from tools.canonical_intake.tactical_league_profile import TacticalLeagueProfileEngine


class V4051ProvenanceQualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))["base"]
        cls.football_fixture = json.loads((cls.root / "tests/fixtures/v4_044/football_intelligence_engine_cases.json").read_text(encoding="utf-8"))
        cls.context_fixture = json.loads((cls.root / "tests/fixtures/v4_045/context_feature_integration_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        bundle_raw = copy.deepcopy(self.bundle_fixture)
        bundle_raw["canonical_entity_refs"]["match_id"] = "match-051-001"
        self.bundle = FeatureSnapshotHasher.seal(FeatureBundle.from_dict(bundle_raw))
        stats = copy.deepcopy(self.football_fixture["statistical_features"])
        contexts = copy.deepcopy(self.football_fixture["context_observations"])
        for item in stats:
            item["target_match_id"] = "match-051-001"
        for item in contexts:
            item["match_id"] = "match-051-001"
        v4044 = FootballIntelligenceEngine.from_repo_root(self.root).generate(feature_bundle=self.bundle, statistical_features=stats, context_observations=contexts[:1])
        extra = copy.deepcopy(self.context_fixture["additional_context"])
        extra["match_id"] = "match-051-001"
        self.context = ContextFeatureIntegrationEngine.from_repo_root(self.root).generate(football_intelligence_artifact=v4044, context_observations=[extra])
        self.tactical_engine = TacticalLeagueProfileEngine.from_repo_root(self.root)
        self.assessment_engine = DataQualityAssessmentEngine.from_repo_root(self.root)
        self.gate_engine = ProvenanceQualityGateEngine.from_repo_root(self.root)

    def tactical_observations(self, unknown=False):
        first = {
            "feature_key": "tactical_matchup",
            "kind": "RELATIONAL",
            "value": {"home": "HIGH_PRESS", "away": "BUILD_UP", "relation": "PRESS_DISRUPTS_BUILD_UP"},
            "unit": "relation",
            "source_refs": ["context-001"],
            "basis_refs": ["evidence-001"],
            "source_timestamp": "2026-09-04T08:40:00+08:00",
            "required": True,
        }
        if unknown:
            first.update({"state": "UNKNOWN", "value": None, "reason_code": "FEATURE_NOT_VERIFIED", "reason_detail": "Tactical relation is not verified.", "required": False})
        return [first, {"feature_key": "league_tactical_context_profile", "kind": "CATEGORICAL", "value": "TRANSITION_ORIENTED", "unit": "profile", "source_refs": ["context-001"], "basis_refs": ["evidence-001"], "source_timestamp": "2026-09-04T08:40:00+08:00"}]

    def wave1(self, unknown=False):
        tactical = self.tactical_engine.generate(feature_bundle=self.bundle, context_feature_artifact=self.context, observations=self.tactical_observations(unknown))
        assessment = self.assessment_engine.generate(
            canonical_entity_refs=self.bundle.to_dict()["canonical_entity_refs"],
            prediction_cutoff_at=self.bundle.prediction_cutoff_at,
            kickoff_at=self.bundle.kickoff_at,
            assessment_inputs=[{"id": "context-001", "hash": "sha256:" + "2" * 64, "domain": "CONTEXT", "state": "UNKNOWN" if unknown else "AVAILABLE", "available_at": "2026-09-04T08:40:00+08:00", "basis_refs": ["evidence-001"], "evidence_refs": ["evidence-001"]}],
        )
        return tactical, assessment

    def test_gate_record_contains_provenance_hashes_and_three_gate_levels(self):
        tactical, assessment = self.wave1()
        record = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment)
        raw = record.to_dict()
        self.assertEqual(ARTIFACT_KIND, raw["artifact_kind"])
        self.assertEqual(CONTRACT_VERSION, raw["contract_version"])
        self.assertEqual("ELIGIBLE", raw["overall_gate_state"])
        self.assertEqual(["ELIGIBLE", "ELIGIBLE"], [item["state"] for item in raw["feature_eligibility_records"]])
        self.assertTrue(raw["domain_eligibility_records"])
        self.assertEqual("CANDIDATE_SET", raw["candidate_set_eligibility_records"][0]["level"])
        for field in ("config_hash", "gating_matrix_hash", "reason_registry_hash", "input_hash", "payload_hash", "provenance_hash", "output_hash"):
            self.assertTrue(raw[field].startswith("sha256:"), field)
        serialized = json.dumps(raw, ensure_ascii=False).casefold()
        self.assertNotIn('"prediction":', serialized)
        self.assertNotIn("frozen_input", serialized)
        self.assertNotIn("recommendation", serialized)
        self.assertNotIn("abstention", serialized)

    def test_optional_unknown_is_feature_ineligible_but_candidate_partial(self):
        tactical, assessment = self.wave1(unknown=True)
        record = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment)
        raw = record.to_dict()
        feature = next(item for item in raw["feature_eligibility_records"] if item["subject_ref"] == "tactical_matchup")
        self.assertEqual("INELIGIBLE", feature["state"])
        self.assertEqual("PARTIALLY_ELIGIBLE", raw["overall_gate_state"])
        self.assertEqual("PARTIALLY_ELIGIBLE", raw["candidate_set_eligibility_records"][0]["state"])
        self.assertNotIn("BLOCKED", {item["state"] for item in raw["feature_eligibility_records"]})

    def test_canonical_identity_conflict_blocks_candidate_set(self):
        tactical, assessment = self.wave1()
        bad = assessment.to_dict()
        bad["assessment_inputs"][0]["match_id"] = "foreign-match"
        # Recreate the accepted assessment with the conflict through the engine,
        # preserving its explicit matrix reason rather than editing a hash.
        bad_assessment = self.assessment_engine.generate(
            canonical_entity_refs=self.bundle.to_dict()["canonical_entity_refs"],
            prediction_cutoff_at=self.bundle.prediction_cutoff_at,
            kickoff_at=self.bundle.kickoff_at,
            assessment_inputs=[{"id": "context-001", "hash": "sha256:" + "2" * 64, "domain": "CONTEXT", "state": "AVAILABLE", "match_id": "foreign-match", "available_at": "2026-09-04T08:40:00+08:00"}],
        )
        record = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=bad_assessment)
        self.assertEqual("BLOCKED", record.overall_gate_state)
        self.assertIn("CANONICAL_IDENTITY_MISMATCH", record.to_dict()["candidate_set_eligibility_records"][0]["blocker_reason_codes"])

    def test_future_official_market_blocks_only_matrix_affected_domain(self):
        tactical, _ = self.wave1()
        assessment = self.assessment_engine.generate(
            canonical_entity_refs=self.bundle.to_dict()["canonical_entity_refs"], prediction_cutoff_at=self.bundle.prediction_cutoff_at, kickoff_at=self.bundle.kickoff_at,
            assessment_inputs=[{"id": "official-001", "hash": "sha256:" + "4" * 64, "domain": "ODDS", "source_is_official": True, "state": "AVAILABLE", "available_at": "2026-09-04T09:20:00+08:00"}],
        )
        raw = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment).to_dict()
        odds_domain = next(item for item in raw["domain_eligibility_records"] if item["subject_ref"].endswith(":odds"))
        self.assertEqual("BLOCKED", odds_domain["state"])
        self.assertIn("FUTURE_DATA", odds_domain["blocker_reason_codes"])

    def test_gate_rejects_unaccepted_or_tampered_wave1_outputs(self):
        tactical, assessment = self.wave1()
        with self.assertRaises(ProvenanceQualityGateValidationError):
            self.gate_engine.evaluate(tactical_artifact={"artifact_kind": "PRE_FREEZE_TACTICAL_LEAGUE_PROFILE"}, quality_assessment=assessment)
        raw = assessment.to_dict()
        raw["output_hash"] = "sha256:" + "0" * 64
        with self.assertRaises(ProvenanceQualityGateValidationError):
            self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=raw)

    def test_deterministic_replay_and_append_only_gate_store(self):
        tactical, assessment = self.wave1()
        first = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment)
        second = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment)
        self.assertEqual(first.gate_record_id, second.gate_record_id)
        self.assertEqual(first.output_hash, second.output_hash)
        store = ProvenanceQualityGateStore(self.gate_engine.config, self.gate_engine.matrix, self.gate_engine.reasons)
        self.assertEqual("APPEND", store.append(first))
        self.assertEqual("DUPLICATE_NOOP", store.append(first))
        corrected = self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment, revision=2, supersedes_gate_record_id=first.gate_record_id)
        self.assertEqual("APPEND", store.append(corrected))
        with self.assertRaisesRegex(ProvenanceQualityGateValidationError, "prior gate record"):
            store.append(self.gate_engine.evaluate(tactical_artifact=tactical, quality_assessment=assessment, revision=3))

    def test_f_drive_v3_isolation_and_no_migration_scope(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
