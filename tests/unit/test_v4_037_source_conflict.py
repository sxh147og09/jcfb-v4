from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    ContradictionState,
    EvidenceGraphStore,
    EvidenceGraphValidationError,
    FreshnessState,
    SourceConflictResolver,
    SourceQualityBand,
)
from tools.canonical_intake.match_identity import resolve_f_drive_output_path


class V4037SourceConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixtures = json.loads((cls.root / "tests/fixtures/v4_037/source_conflict_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        identity_store = CanonicalMatchIdentityStore()
        identity = identity_store.ingest(copy.deepcopy(self.identity_fixture))
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id
        self.graph = EvidenceGraphStore(identity_store)
        self.resolver = SourceConflictResolver(self.graph)

    def evidence(self, name="base"):
        raw = copy.deepcopy(self.fixtures[name])
        raw["entity_refs"]["match_id"] = self.match_id
        return raw

    def add(self, name="base"):
        result = self.graph.ingest(self.evidence(name))
        self.assertTrue(result.accepted, result.error_code)
        return result.item

    def test_source_quality_is_explicit_and_append_only(self):
        item = self.add()
        assert item is not None
        with self.assertRaises(EvidenceGraphValidationError) as context:
            self.resolver.assess_source({"assessment_id": "quality-001", "evidence_id": item.evidence_id, "quality_band": "HIGH", "quality_basis": [], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:15:00+08:00"})
        self.assertEqual("QUALITY_BASIS_REQUIRED", context.exception.code)

        first = self.resolver.assess_source({"assessment_id": "quality-001", "evidence_id": item.evidence_id, "quality_band": "HIGH", "quality_basis": ["attributable official club record"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:15:00+08:00"})
        second = self.resolver.assess_source({"assessment_id": "quality-002", "evidence_id": item.evidence_id, "quality_band": "MEDIUM", "quality_basis": ["source freshness downgraded by review"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:20:00+08:00", "revision": 2, "supersedes_assessment_id": first.assessment_id})
        self.assertEqual(SourceQualityBand.MEDIUM, second.quality_band)
        self.assertEqual(2, len(self.resolver.quality_assessments))

    def test_expiry_unknown_time_and_future_cutoff_fail_closed(self):
        item = self.add("stale")
        assert item is not None
        self.resolver.assess_source({"assessment_id": "quality-stale", "evidence_id": item.evidence_id, "quality_band": "MEDIUM", "quality_basis": ["source record retained"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:15:00+08:00"})
        stale = self.resolver.evaluate(item.evidence_id, as_of="2026-09-04T13:00:00+08:00")
        self.assertEqual(FreshnessState.STALE, stale.freshness_state)
        self.assertFalse(stale.eligible)
        self.assertIn("EXPIRED", stale.blockers)

        unknown = self.evidence()
        unknown["evidence_id"] = "evidence-20260904-013"
        unknown.pop("valid_from")
        unknown["valid_from_state"] = "UNKNOWN_TIME"
        unknown_item = self.graph.ingest(unknown).item
        assert unknown_item is not None
        self.resolver.assess_source({"assessment_id": "quality-unknown", "evidence_id": unknown_item.evidence_id, "quality_band": "HIGH", "quality_basis": ["source identity only"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:15:00+08:00"})
        unknown_result = self.resolver.evaluate(unknown_item.evidence_id, as_of="2026-09-04T10:00:00+08:00")
        self.assertEqual(FreshnessState.UNKNOWN_TIME, unknown_result.freshness_state)
        self.assertFalse(unknown_result.eligible)

        future = self.evidence()
        future["evidence_id"] = "evidence-20260904-014"
        future["valid_from"] = "2026-09-04T12:00:00+08:00"
        future["retrieved_at"] = "2026-09-04T12:01:00+08:00"
        future_item = self.graph.ingest(future).item
        assert future_item is not None
        self.resolver.assess_source({"assessment_id": "quality-future", "evidence_id": future_item.evidence_id, "quality_band": "HIGH", "quality_basis": ["source is attributable"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T12:02:00+08:00"})
        future_result = self.resolver.evaluate(future_item.evidence_id, as_of="2026-09-04T12:30:00+08:00", cutoff_at="2026-09-04T11:00:00+08:00", kickoff_at="2026-09-04T19:35:00+08:00")
        self.assertEqual(FreshnessState.FUTURE_DATA, future_result.freshness_state)
        self.assertFalse(future_result.eligible)
        self.assertIn("NOT_ELIGIBLE_AT_CUTOFF", future_result.blockers)

    def test_conflict_retains_all_claims_and_never_silently_selects(self):
        first = self.add()
        second_raw = self.evidence("contradicting")
        second = self.graph.ingest(second_raw)
        self.assertTrue(second.accepted, second.error_code)
        assert first is not None and second.item is not None
        self.assertEqual(ContradictionState.CONFLICTED, self.resolver.conflict_state(first.claim_id))
        self.assertEqual({first.evidence_id, second.item.evidence_id}, {item.evidence_id for item in self.resolver.conflict_set(first.claim_id)})

        self.resolver.assess_source({"assessment_id": "quality-conflict-a", "evidence_id": first.evidence_id, "quality_band": "HIGH", "quality_basis": ["source identity and direct record"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:20:00+08:00"})
        self.resolver.assess_source({"assessment_id": "quality-conflict-b", "evidence_id": second.item.evidence_id, "quality_band": "MEDIUM", "quality_basis": ["source identity and direct record"], "assessed_by": "reviewer", "assessed_at": "2026-09-04T09:20:00+08:00"})
        blocked = self.resolver.evaluate(first.evidence_id, as_of="2026-09-04T10:00:00+08:00")
        self.assertFalse(blocked.eligible)
        self.assertIn("UNRESOLVED_CONFLICT", blocked.blockers)

        with self.assertRaises(EvidenceGraphValidationError) as context:
            self.resolver.resolve_conflict({"resolution_id": "resolution-001", "claim_id": first.claim_id, "evidence_ids": [first.evidence_id], "basis_evidence_ids": [first.evidence_id], "resolution_reason": "incomplete set", "actor": "reviewer", "resolved_at": "2026-09-04T10:10:00+08:00", "policy_reference": "review://conflict/001"})
        self.assertEqual("RESOLUTION_REFERENCE_INVALID", context.exception.code)

        resolution = self.resolver.resolve_conflict({"resolution_id": "resolution-001", "claim_id": first.claim_id, "evidence_ids": [first.evidence_id, second.item.evidence_id], "basis_evidence_ids": [first.evidence_id, second.item.evidence_id], "resolution_reason": "documented independent review retained both source sides", "actor": "reviewer", "resolved_at": "2026-09-04T10:10:00+08:00", "policy_reference": "review://conflict/001", "selected_evidence_id": first.evidence_id})
        self.assertEqual(ContradictionState.RESOLVED, self.resolver.conflict_state(first.claim_id))
        self.assertEqual({first.evidence_id, second.item.evidence_id}, set(resolution.evidence_ids))
        self.assertEqual(1, len(self.resolver.resolutions))

    def test_missing_quality_is_not_implicitly_trusted_and_resolution_is_explicit(self):
        item = self.add()
        assert item is not None
        result = self.resolver.evaluate(item.evidence_id, as_of="2026-09-04T10:00:00+08:00")
        self.assertFalse(result.eligible)
        self.assertIn("SOURCE_QUALITY_UNKNOWN", result.blockers)
        self.assertIsNone(result.to_dict().get("prediction_confidence"))

    def test_f_drive_and_v333_isolation(self):
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-037/evidence.json").drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "work/evidence.json")


if __name__ == "__main__":
    unittest.main()
