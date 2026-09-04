from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    AvailabilityStatus,
    CanonicalFactStore,
    CanonicalMatchIdentityStore,
    TimeGateStatus,
    TimeLineageStore,
    resolve_f_drive_output_path,
)


class V4022TimeLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        fact_path = cls.repo_root / "tests/fixtures/v4_021/fact_cases.json"
        time_path = cls.repo_root / "tests/fixtures/v4_022/time_lineage_cases.json"
        cls.identity_fixture = json.loads(identity_path.read_text(encoding="utf-8"))
        cls.fact_fixture = json.loads(fact_path.read_text(encoding="utf-8"))
        cls.time_fixture = json.loads(time_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(self.identity_fixture["base"])
        self.assertTrue(identity.accepted)
        self.subject = {"match_id": identity.canonical_match_id, "match_identity_key": identity.business_key}
        self.fact_store = CanonicalFactStore(self.identity_store)
        fact = copy.deepcopy(self.fact_fixture["base"])
        fact["subject"] = copy.deepcopy(self.subject)
        fact_result = self.fact_store.ingest(fact)
        self.assertTrue(fact_result.accepted)
        self.fact = fact_result.envelope

    def time_input(self):
        value = copy.deepcopy(self.time_fixture["base"])
        value["fact_object_id"] = self.fact.object_id
        return value

    def gate(self):
        return TimeLineageStore(self.fact_store)

    def test_prematch_allowed_uses_explicit_published_time_basis(self):
        result = self.gate().evaluate(self.time_input())
        self.assertTrue(result.accepted)
        self.assertEqual(TimeGateStatus.PREMATCH_ALLOWED, result.status)
        self.assertEqual("SOURCE_PUBLISHED_AT", result.decision.availability_time_basis.value)
        self.assertEqual("2026-09-04T08:55:00+08:00", result.decision.availability_at)
        self.assertFalse(result.decision.future_information_leakage)
        self.assertTrue(result.decision.tier_a_eligible)

    def test_source_timestamp_basis_is_carried_and_selected(self):
        incoming = self.time_input()
        incoming["availability_time_basis"] = "SOURCE_TIMESTAMP"
        result = self.gate().evaluate(incoming)
        self.assertTrue(result.accepted)
        self.assertEqual("SOURCE_TIMESTAMP", result.decision.availability_time_basis.value)
        self.assertEqual("2026-09-04T08:58:00+08:00", result.decision.availability_at)

    def test_observed_time_basis_is_explicit_and_ingested_time_is_not_used(self):
        incoming = self.time_input()
        incoming["availability_time_basis"] = "OBSERVED_AT"
        incoming["ingested_at"] = "2026-09-04T12:00:00+08:00"
        result = self.gate().evaluate(incoming)
        self.assertTrue(result.accepted)
        self.assertEqual("2026-09-04T09:00:00+08:00", result.decision.availability_at)

    def test_availability_at_equal_to_cutoff_is_allowed(self):
        incoming = self.time_input()
        incoming["availability_time_basis"] = "SOURCE_TIMESTAMP"
        incoming["source_timestamp"] = incoming["prediction_cutoff_at"]
        result = self.gate().evaluate(incoming)
        self.assertTrue(result.accepted)
        self.assertEqual(TimeGateStatus.PREMATCH_ALLOWED, result.status)

    def test_equivalent_timezone_forms_share_deterministic_lineage_identity(self):
        store = self.gate()
        first = store.evaluate(self.time_input())
        equivalent = self.time_input()
        equivalent.update(
            {
                "source_timestamp": "2026-09-04T00:58:00Z",
                "source_published_at": "2026-09-04T00:55:00Z",
                "observed_at": "2026-09-04T01:00:00Z",
                "ingested_at": "2026-09-04T01:01:00Z",
                "prediction_cutoff_at": "2026-09-04T01:00:00Z",
                "kickoff_at": "2026-09-04T11:35:00Z",
            }
        )
        second = store.evaluate(equivalent)
        self.assertEqual(first.decision.decision_id, second.decision.decision_id)
        self.assertEqual("DUPLICATE_NOOP", second.action)
        self.assertEqual(first.decision.lineage_hash, second.decision.lineage_hash)

    def test_missing_basis_fails_closed_without_fallback(self):
        incoming = self.time_input()
        incoming.pop("availability_time_basis")
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("AVAILABILITY_BASIS_REQUIRED", result.error_code)

    def test_missing_selected_source_time_fails_closed(self):
        incoming = self.time_input()
        incoming["availability_time_basis"] = "SOURCE_TIMESTAMP"
        incoming.pop("source_timestamp")
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.BLOCKED, result.status)
        self.assertEqual("AVAILABILITY_TIME_UNKNOWN", result.decision.reason_code)

    def test_after_cutoff_before_kickoff_is_future_information_leakage(self):
        incoming = self.time_input()
        incoming.update(
            {
                "source_published_at": "2026-09-04T09:01:00+08:00",
                "observed_at": "2026-09-04T09:02:00+08:00",
                "ingested_at": "2026-09-04T09:03:00+08:00",
            }
        )
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.FUTURE_INFORMATION_LEAKAGE, result.status)
        self.assertTrue(result.decision.future_information_leakage)
        self.assertTrue(result.decision.run_invalid)
        self.assertFalse(result.decision.tier_a_eligible)
        self.assertFalse(result.decision.promotion_evidence)
        self.assertEqual("AFTER_DECLARED_CUTOFF", result.decision.reason_code)

    def test_at_or_after_kickoff_is_postmatch_only_and_invalid_for_prematch(self):
        incoming = self.time_input()
        incoming.update(
            {
                "source_published_at": "2026-09-04T20:00:00+08:00",
                "observed_at": "2026-09-04T20:01:00+08:00",
                "ingested_at": "2026-09-04T20:02:00+08:00",
            }
        )
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.POSTMATCH_ONLY, result.status)
        self.assertTrue(result.decision.future_information_leakage)
        self.assertEqual("AVAILABLE_AT_OR_AFTER_KICKOFF", result.decision.reason_code)

    def test_cutoff_must_be_strictly_before_kickoff(self):
        incoming = self.time_input()
        incoming["prediction_cutoff_at"] = incoming["kickoff_at"]
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("CUTOFF_NOT_BEFORE_KICKOFF", result.decision.reason_code)

    def test_ingested_before_observed_is_blocked(self):
        incoming = self.time_input()
        incoming["ingested_at"] = "2026-09-04T08:59:00+08:00"
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("INGESTED_BEFORE_OBSERVED", result.decision.reason_code)

    def test_observed_before_published_is_blocked(self):
        incoming = self.time_input()
        incoming["source_published_at"] = "2026-09-04T09:05:00+08:00"
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("OBSERVED_BEFORE_PUBLISHED", result.decision.reason_code)

    def test_observed_before_source_timestamp_is_blocked(self):
        incoming = self.time_input()
        incoming["source_timestamp"] = "2026-09-04T09:05:00+08:00"
        incoming["availability_time_basis"] = "SOURCE_TIMESTAMP"
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("OBSERVED_BEFORE_SOURCE_TIMESTAMP", result.decision.reason_code)

    def test_naive_timestamp_is_blocked(self):
        incoming = self.time_input()
        incoming["prediction_cutoff_at"] = "2026-09-04T09:00:00"
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("TIMESTAMP_TIMEZONE_REQUIRED", result.error_code)

    def test_fact_reference_and_match_reference_are_bound(self):
        incoming = self.time_input()
        incoming["match_id"] = self.subject["match_id"]
        incoming["source_ref"] = self.fact.source_ref
        result = self.gate().evaluate(incoming)
        self.assertTrue(result.accepted)

        incoming["match_id"] = "019a0000-0000-5000-8000-000000000099"
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_REFERENCE_CONFLICT", result.error_code)

    def test_missing_fact_reference_is_blocked(self):
        result = self.gate().evaluate({"fact_object_id": "019a0000-0000-5000-8000-000000000099"})
        self.assertFalse(result.accepted)
        self.assertEqual("FACT_REFERENCE_NOT_FOUND", result.error_code)

    def test_future_data_fact_remains_leakage_evidence(self):
        future_fact = copy.deepcopy(self.fact_fixture["base"])
        future_fact["subject"] = copy.deepcopy(self.subject)
        future_fact.update(
            {
                "source": "Provider B",
                "source_ref": "ref://provider-b/future/001",
                "payload": None,
                "availability_status": "FUTURE_DATA",
                "reason_code": "AFTER_DECLARED_CUTOFF",
            }
        )
        future_result = self.fact_store.ingest(future_fact)
        self.assertTrue(future_result.accepted)
        incoming = self.time_input()
        incoming["fact_object_id"] = future_result.envelope.object_id
        result = self.gate().evaluate(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual(TimeGateStatus.FUTURE_INFORMATION_LEAKAGE, result.status)
        self.assertEqual("FACT_MARKED_FUTURE_DATA", result.decision.reason_code)

    def test_decisions_and_rejections_are_append_only(self):
        store = self.gate()
        first = store.evaluate(self.time_input())
        second = store.evaluate(self.time_input())
        self.assertEqual(first.decision.decision_id, second.decision.decision_id)
        self.assertEqual(["DECISION_APPENDED", "DUPLICATE_NOOP"], [event["action"] for event in store.events])
        changed = self.time_input()
        changed["prediction_cutoff_at"] = "2026-09-04T09:05:00+08:00"
        third = store.evaluate(changed)
        self.assertTrue(third.accepted)
        self.assertEqual(2, len(store.decisions))
        self.assertEqual(3, len(store.events))

    def test_v333_isolation_and_f_drive_policy(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-022/evidence.json")
        self.assertEqual("F:", output.drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "work/evidence.json")


if __name__ == "__main__":
    unittest.main()
