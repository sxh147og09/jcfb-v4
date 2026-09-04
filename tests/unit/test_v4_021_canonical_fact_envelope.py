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
    resolve_f_drive_output_path,
)


class V4021CanonicalFactEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_fixture = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        fact_fixture = cls.repo_root / "tests/fixtures/v4_021/fact_cases.json"
        cls.identity_fixture = json.loads(identity_fixture.read_text(encoding="utf-8"))
        cls.fixtures = json.loads(fact_fixture.read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity_result = self.identity_store.ingest(self.identity_fixture["base"])
        self.assertTrue(identity_result.accepted)
        self.subject = {
            "match_id": identity_result.canonical_match_id,
            "match_identity_key": identity_result.business_key,
        }

    def fact(self):
        value = copy.deepcopy(self.fixtures["base"])
        value["subject"] = copy.deepcopy(self.subject)
        return value

    def store(self):
        return CanonicalFactStore(self.identity_store)

    def test_available_fact_has_typed_envelope_and_hash_lineage(self):
        result = self.store().ingest(self.fact())
        self.assertTrue(result.accepted)
        self.assertEqual(AvailabilityStatus.AVAILABLE, result.status)
        self.assertEqual("fixture_schedule", result.envelope.fact_type)
        self.assertEqual(self.subject, result.envelope.subject.to_dict())
        self.assertTrue(result.envelope.payload)
        self.assertTrue(result.envelope.provenance_hash.startswith("sha256:"))
        self.assertTrue(result.envelope.payload_hash.startswith("sha256:"))
        self.assertEqual(1, result.envelope.revision)

    def test_all_seven_statuses_are_explicit_typed_values(self):
        for status in AvailabilityStatus:
            with self.subTest(status=status):
                incoming = self.fact()
                incoming["availability_status"] = status.value
                if status != AvailabilityStatus.AVAILABLE:
                    incoming["payload"] = None
                    incoming["reason_code"] = f"{status.value}_TEST_REASON"
                if status == AvailabilityStatus.CONFLICT:
                    incoming["conflict_evidence"] = copy.deepcopy(self.fixtures["conflict_evidence"])
                result = self.store().ingest(incoming)
                self.assertTrue(result.accepted)
                self.assertEqual(status, result.status)
                self.assertEqual(status, result.envelope.availability_status)

    def test_unknown_requires_reason_and_can_have_no_payload(self):
        incoming = self.fact()
        incoming.update({"availability_status": "UNKNOWN", "payload": None, "reason_code": "SOURCE_VALUE_UNKNOWN"})
        result = self.store().ingest(incoming)
        self.assertTrue(result.accepted)
        self.assertIsNone(result.envelope.payload)
        self.assertEqual("SOURCE_VALUE_UNKNOWN", result.envelope.reason_code)

    def test_non_available_without_reason_is_blocked(self):
        for status in ("UNKNOWN", "UNAVAILABLE", "STALE", "FUTURE_DATA", "BLOCKED"):
            with self.subTest(status=status):
                incoming = self.fact()
                incoming.update({"availability_status": status, "payload": None})
                result = self.store().ingest(incoming)
                self.assertFalse(result.accepted)
                self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_conflict_retains_both_source_payload_sides(self):
        incoming = self.fact()
        incoming.update(
            {
                "availability_status": "CONFLICT",
                "payload": None,
                "reason_code": "SOURCES_DISAGREE",
                "conflict_evidence": copy.deepcopy(self.fixtures["conflict_evidence"]),
            }
        )
        result = self.store().ingest(incoming)
        self.assertTrue(result.accepted)
        self.assertEqual(AvailabilityStatus.CONFLICT, result.envelope.availability_status)
        self.assertEqual(2, len(result.envelope.conflict_evidence))
        self.assertEqual({"Provider A", "Provider B"}, {item.source for item in result.envelope.conflict_evidence})
        self.assertEqual({"A", "B"}, {item.payload["value"] for item in result.envelope.conflict_evidence})

    def test_conflict_without_two_evidence_sides_is_blocked(self):
        incoming = self.fact()
        incoming.update(
            {
                "availability_status": "CONFLICT",
                "payload": None,
                "reason_code": "SOURCES_DISAGREE",
                "conflict_evidence": [self.fixtures["conflict_evidence"][0]],
            }
        )
        result = self.store().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("CONFLICT_EVIDENCE_REQUIRED", result.error_code)

    def test_available_empty_payload_fails_closed(self):
        incoming = self.fact()
        incoming["payload"] = {}
        result = self.store().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("PAYLOAD_EMPTY", result.error_code)

    def test_available_wrong_payload_type_fails_closed(self):
        incoming = self.fact()
        incoming["payload"] = []
        result = self.store().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("PAYLOAD_TYPE_INVALID", result.error_code)

    def test_missing_source_and_source_ref_fail_closed(self):
        for field in ("source", "source_ref"):
            with self.subTest(field=field):
                incoming = self.fact()
                incoming.pop(field)
                result = self.store().ingest(incoming)
                self.assertFalse(result.accepted)
                self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

    def test_missing_or_invalid_subject_identity_fails_closed(self):
        missing_subject = self.fact()
        missing_subject.pop("subject")
        result = self.store().ingest(missing_subject)
        self.assertFalse(result.accepted)
        self.assertEqual("SUBJECT_INVALID", result.error_code)

        orphan = self.fact()
        orphan["subject"] = {
            "match_id": "019a0000-0000-5000-8000-000000000099",
            "match_identity_key": "2026-09-04:099",
        }
        result = self.store().ingest(orphan)
        self.assertFalse(result.accepted)
        self.assertEqual("SUBJECT_IDENTITY_NOT_FOUND", result.error_code)

    def test_subject_identity_key_mismatch_is_blocked(self):
        incoming = self.fact()
        incoming["subject"]["match_identity_key"] = "2026-09-04:999"
        result = self.store().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("SUBJECT_IDENTITY_KEY_CONFLICT", result.error_code)

    def test_implicit_status_coercion_is_rejected(self):
        for mutation in (
            {"availability_status": "unknown", "reason_code": "SOURCE_VALUE_UNKNOWN"},
            {"status": "UNKNOWN", "payload": None, "reason_code": "SOURCE_VALUE_UNKNOWN"},
            {"available": True},
        ):
            with self.subTest(mutation=mutation):
                incoming = self.fact()
                incoming.pop("availability_status", None)
                incoming.update(mutation)
                result = self.store().ingest(incoming)
                self.assertFalse(result.accepted)
                self.assertEqual("AVAILABILITY_STATUS_REQUIRED" if "availability_status" not in mutation else "AVAILABILITY_STATUS_INVALID", result.error_code)

    def test_prediction_and_model_fields_are_rejected(self):
        for field in ("prediction", "recommendation", "confidence", "model_interpretation", "engine_output"):
            with self.subTest(field=field):
                incoming = self.fact()
                incoming["payload"][field] = "forbidden"
                result = self.store().ingest(incoming)
                self.assertFalse(result.accepted)
                self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_append_only_revision_keeps_predecessor(self):
        store = self.store()
        first = store.ingest(self.fact())
        second_input = self.fact()
        second_input.update(
            {
                "source": "Provider B",
                "source_ref": "ref://provider-b/fact/8842",
                "payload": {"kickoff_confirmed": False, "competition_id": "competition-premier-example"},
                "observed_at": "2026-09-04T09:03:00+08:00",
                "ingested_at": "2026-09-04T09:04:00+08:00",
            }
        )
        second = store.ingest(second_input)
        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual(2, second.envelope.revision)
        self.assertEqual(first.envelope.object_id, second.envelope.supersedes_object_id)
        self.assertIsNotNone(store.get(first.envelope.object_id))
        self.assertEqual("REVISION_APPENDED", store.events[-1]["action"])

    def test_identical_delivery_is_duplicate_noop(self):
        store = self.store()
        first = store.ingest(self.fact())
        second = store.ingest(self.fact())
        self.assertEqual(first.envelope.object_id, second.envelope.object_id)
        self.assertEqual("DUPLICATE_NOOP", second.action)
        self.assertEqual(1, len(store.envelopes))
        self.assertEqual(2, len(store.events))

    def test_future_data_is_explicit_not_available(self):
        incoming = self.fact()
        incoming.update({"availability_status": "FUTURE_DATA", "payload": None, "reason_code": "AFTER_DECLARED_CUTOFF"})
        result = self.store().ingest(incoming)
        self.assertTrue(result.accepted)
        self.assertNotEqual(AvailabilityStatus.AVAILABLE, result.envelope.availability_status)

    def test_v333_isolation_and_f_drive_policy(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))

        incoming = self.fact()
        incoming["payload"]["v333_reference"] = "forbidden"
        result = self.store().ingest(incoming)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-021/evidence.json")
        self.assertEqual("F:", output.drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "work/evidence.json")


if __name__ == "__main__":
    unittest.main()
