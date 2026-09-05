from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake.data_quality_assessment import (
    ARTIFACT_KIND,
    CONTRACT_VERSION,
    DataQualityAssessmentArtifact,
    DataQualityAssessmentEngine,
    DataQualityAssessmentStore,
    DataQualityAssessmentValidationError,
)


class V4050DataQualityAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.engine = DataQualityAssessmentEngine.from_repo_root(cls.root)

    def inputs(self):
        return [
            {
                "id": "official-odds-001",
                "hash": "sha256:" + "1" * 64,
                "domain": "ODDS",
                "source_kind": "official_odds_snapshot",
                "source_is_official": True,
                "state": "AVAILABLE",
                "required": True,
                "available_at": "2026-09-04T08:30:00+08:00",
                "basis_refs": ["fact-001"],
                "evidence_refs": ["evidence-001"],
                "revision": 1,
            },
            {
                "id": "context-001",
                "hash": "sha256:" + "2" * 64,
                "domain": "CONTEXT",
                "source_kind": "team_context",
                "state": "UNKNOWN",
                "required": False,
                "available_at": "2026-09-04T08:40:00+08:00",
                "basis_refs": ["fact-001"],
                "evidence_refs": ["evidence-001"],
                "revision": 1,
            },
        ]

    def generate(self, inputs=None, **kwargs):
        return self.engine.generate(
            canonical_entity_refs={"match_id": "match-050-001", "home_team_id": "team-home", "away_team_id": "team-away"},
            prediction_cutoff_at="2026-09-04T09:10:00+08:00",
            kickoff_at="2026-09-04T11:35:00+08:00",
            assessment_inputs=self.inputs() if inputs is None else inputs,
            **kwargs,
        )

    def test_outputs_four_typed_quality_assessments_and_all_dimensions(self):
        raw = self.generate().to_dict()
        self.assertEqual(ARTIFACT_KIND, raw["artifact_kind"])
        self.assertEqual(CONTRACT_VERSION, raw["contract_version"])
        for field in ("data_quality_assessment", "odds_quality_assessment", "context_quality_assessment", "source_quality_assessment"):
            self.assertEqual(
                set(self.engine.config["quality_dimensions"]),
                set(raw[field]),
            )
            for dimension in raw[field].values():
                self.assertEqual({"state", "basis_refs", "evidence_refs", "reason_codes", "counts", "source_input_hashes"}, set(dimension))
        self.assertTrue(raw["input_hash"].startswith("sha256:"))
        self.assertTrue(raw["provenance_hash"].startswith("sha256:"))
        self.assertIn("gating_matrix_hash", raw)
        self.assertIn("reason_registry_hash", raw)

    def test_quality_is_not_scalar_confidence_or_cross_domain_aggregation(self):
        raw = json.dumps(self.generate().to_dict(), ensure_ascii=False).casefold()
        for forbidden in ('"score"', '"confidence"', '"weight"', '"penalty"', '"probability"', "composite"):
            self.assertNotIn(forbidden, raw)
        self.assertNotIn('"prediction":', raw)
        self.assertNotIn("frozen_input", raw)

    def test_non_hard_unknown_remains_warning_while_official_future_is_hard_blocked(self):
        items = self.inputs()
        items[0]["available_at"] = "2026-09-04T09:20:00+08:00"
        artifact = self.generate(items).to_dict()
        codes = {item["reason_code"] for item in artifact["blockers"]}
        self.assertIn("FUTURE_DATA", codes)
        self.assertTrue(any(item["reason_code"] == "OPTIONAL_FEATURE_UNKNOWN" for item in artifact["warnings"]))
        self.assertEqual("BLOCKED", artifact["odds_quality_assessment"]["future_data_risk"]["state"])

    def test_missing_hash_and_unknown_time_fail_closed_as_blockers(self):
        items = self.inputs()
        del items[0]["hash"]
        del items[0]["available_at"]
        artifact = self.generate(items).to_dict()
        codes = {item["reason_code"] for item in artifact["blockers"]}
        self.assertIn("REQUIRED_HASH_MISSING", codes)
        self.assertIn("SOURCE_TIMESTAMP_UNKNOWN", codes)
        self.assertEqual("BLOCKED", artifact["odds_quality_assessment"]["provenance"]["state"])

    def test_duplicate_identity_with_conflicting_hash_is_not_silently_selected(self):
        items = self.inputs()
        duplicate = copy.deepcopy(items[0])
        duplicate["hash"] = "sha256:" + "3" * 64
        duplicate["revision"] = 2
        items.append(duplicate)
        artifact = self.generate(items).to_dict()
        self.assertTrue(any(item["reason_code"] == "REVISION_HASH_CONFLICT" for item in artifact["blockers"]))
        self.assertEqual("BLOCKED", artifact["data_quality_assessment"]["duplication_integrity"]["state"])

    def test_deterministic_replay_and_hash_tamper_detection(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(first.assessment_id, second.assessment_id)
        self.assertEqual(first.output_hash, second.output_hash)
        raw = first.to_dict()
        raw["output_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(DataQualityAssessmentValidationError, "recomputable"):
            DataQualityAssessmentArtifact.from_dict(raw, config=self.engine.config, matrix=self.engine.matrix, reasons=self.engine.reasons)

    def test_append_only_correction_requires_supersedes(self):
        base = self.generate()
        store = DataQualityAssessmentStore(self.engine.config, self.engine.matrix, self.engine.reasons)
        self.assertEqual("APPEND", store.append(base))
        self.assertEqual("DUPLICATE_NOOP", store.append(base))
        corrected = self.generate(revision=2, supersedes_assessment_id=base.assessment_id)
        self.assertEqual("APPEND", store.append(corrected))
        invalid = self.generate(revision=3)
        with self.assertRaisesRegex(DataQualityAssessmentValidationError, "prior assessment"):
            store.append(invalid)

    def test_f_drive_v3_isolation_and_no_migration_scope(self):
        self.assertEqual("F:", self.root.drive.upper())
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
