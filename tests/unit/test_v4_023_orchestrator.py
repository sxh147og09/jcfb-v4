from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalIntakeOrchestrator,
    CanonicalMatchIdentityStore,
    IntakeOutcome,
    TimeGateStatus,
    resolve_f_drive_output_path,
)


class V4023OrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        identity_path = cls.repo_root / "tests/fixtures/v4_020/identity_cases.json"
        fact_path = cls.repo_root / "tests/fixtures/v4_021/fact_cases.json"
        orchestrator_path = cls.repo_root / "tests/fixtures/v4_023/orchestrator_cases.json"
        cls.identity_fixture = json.loads(identity_path.read_text(encoding="utf-8"))
        cls.fact_fixture = json.loads(fact_path.read_text(encoding="utf-8"))
        cls.orchestrator_fixture = json.loads(orchestrator_path.read_text(encoding="utf-8"))

    def setUp(self):
        identity_preview = CanonicalMatchIdentityStore().ingest(self.identity_fixture["base"])
        self.subject = {"match_id": identity_preview.canonical_match_id, "match_identity_key": identity_preview.business_key}
        self.orchestrator = CanonicalIntakeOrchestrator()

    def packet(self, *, key: str | None = None):
        fact = copy.deepcopy(self.fact_fixture["base"])
        fact["subject"] = copy.deepcopy(self.subject)
        return {
            "idempotency_key": key or self.orchestrator_fixture["idempotency_key"],
            "identity_observation": copy.deepcopy(self.identity_fixture["base"]),
            "fact_observation": fact,
            "time_lineage": copy.deepcopy(self.orchestrator_fixture["time_lineage"]),
        }

    def test_orchestrator_runs_identity_fact_time_in_order(self):
        result = self.orchestrator.ingest(self.packet())
        self.assertTrue(result.accepted)
        self.assertEqual(IntakeOutcome.ACCEPTED, result.outcome)
        self.assertTrue(result.identity.accepted)
        self.assertTrue(result.fact.accepted)
        self.assertTrue(result.time.accepted)
        self.assertEqual(TimeGateStatus.PREMATCH_ALLOWED, result.time.status)
        self.assertEqual(result.fact.envelope.object_id, result.time.decision.fact_object_id)
        self.assertEqual(1, len(self.orchestrator.deliveries))

    def test_delivery_key_is_required_and_stable(self):
        missing = self.packet()
        missing.pop("idempotency_key")
        result = self.orchestrator.ingest(missing)
        self.assertFalse(result.accepted)
        self.assertEqual("REQUIRED_FIELD_MISSING", result.error_code)

        first = self.orchestrator.ingest(self.packet())
        reordered = {
            "time_lineage": self.packet()["time_lineage"],
            "fact_observation": self.packet()["fact_observation"],
            "identity_observation": self.packet()["identity_observation"],
            "idempotency_key": self.packet()["idempotency_key"],
        }
        second = self.orchestrator.ingest(reordered)
        self.assertTrue(first.accepted)
        self.assertEqual(IntakeOutcome.DUPLICATE_NOOP, second.outcome)
        self.assertEqual(1, len(self.orchestrator.deliveries))

    def test_reused_key_with_changed_payload_fails_closed(self):
        first = self.orchestrator.ingest(self.packet())
        changed = self.packet()
        changed["fact_observation"]["payload"]["kickoff_confirmed"] = False
        second = self.orchestrator.ingest(changed)
        self.assertTrue(first.accepted)
        self.assertFalse(second.accepted)
        self.assertEqual("IDEMPOTENCY_KEY_REUSE_CONFLICT", second.error_code)
        self.assertEqual(1, len(self.orchestrator.fact_store.envelopes))
        self.assertEqual("BLOCKED_IDEMPOTENCY_REUSE", self.orchestrator.events[-1]["action"])

    def test_cross_source_identity_alias_is_coordinated(self):
        first = self.orchestrator.ingest(self.packet())
        second_packet = self.packet(key="fixture:2026-09-04:001:provider-b")
        second_packet["identity_observation"] = copy.deepcopy(self.identity_fixture["second_source"])
        second_packet["fact_observation"]["source"] = "Example schedule provider"
        second_packet["fact_observation"]["source_ref"] = "ref://provider-b/fact/8842"
        second = self.orchestrator.ingest(second_packet)
        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual("CROSS_SOURCE_ALIAS", second.identity.resolution_action)
        self.assertEqual(first.identity.canonical_match_id, second.identity.canonical_match_id)
        self.assertEqual(2, len(self.orchestrator.fact_store.envelopes))

    def test_new_delivery_key_appends_fact_correction_revision(self):
        first = self.orchestrator.ingest(self.packet())
        correction = self.packet(key="fixture:2026-09-04:001:r2")
        correction["fact_observation"]["source"] = "Provider correction"
        correction["fact_observation"]["source_ref"] = "ref://provider/correction/001"
        correction["fact_observation"]["payload"]["kickoff_confirmed"] = False
        correction["time_lineage"]["observed_at"] = "2026-09-04T09:03:00+08:00"
        correction["time_lineage"]["ingested_at"] = "2026-09-04T09:04:00+08:00"
        second = self.orchestrator.ingest(correction)
        self.assertTrue(first.accepted and second.accepted)
        self.assertEqual(2, second.fact.envelope.revision)
        self.assertEqual(first.fact.envelope.object_id, second.fact.envelope.supersedes_object_id)
        self.assertEqual(2, len(self.orchestrator.fact_store.envelopes))

    def test_identity_failure_stops_downstream_stages(self):
        packet = self.packet()
        packet["identity_observation"].pop("official_match_no")
        packet["identity_observation"].pop("source_match_ref")
        result = self.orchestrator.ingest(packet)
        self.assertFalse(result.accepted)
        self.assertEqual(IntakeOutcome.BLOCKED, result.outcome)
        self.assertIsNone(result.fact)
        self.assertIsNone(result.time)
        self.assertEqual(0, len(self.orchestrator.fact_store.envelopes))

    def test_fact_failure_preserves_identity_but_stops_time(self):
        packet = self.packet()
        packet["fact_observation"]["payload"] = {}
        result = self.orchestrator.ingest(packet)
        self.assertFalse(result.accepted)
        self.assertTrue(result.identity.accepted)
        self.assertFalse(result.fact.accepted)
        self.assertIsNone(result.time)
        self.assertEqual(0, len(self.orchestrator.fact_store.envelopes))

    def test_time_failure_is_propagated_and_evidence_retained(self):
        packet = self.packet()
        packet["time_lineage"]["source_published_at"] = "2026-09-04T09:01:00+08:00"
        packet["time_lineage"]["observed_at"] = "2026-09-04T09:02:00+08:00"
        packet["time_lineage"]["ingested_at"] = "2026-09-04T09:03:00+08:00"
        result = self.orchestrator.ingest(packet)
        self.assertFalse(result.accepted)
        self.assertTrue(result.fact.accepted)
        self.assertFalse(result.time.accepted)
        self.assertEqual(TimeGateStatus.FUTURE_INFORMATION_LEAKAGE, result.time.status)
        self.assertEqual(1, len(self.orchestrator.fact_store.envelopes))
        self.assertEqual(1, len(self.orchestrator.time_store.decisions))

    def test_packet_boundary_rejects_unknown_and_model_fields(self):
        unknown = self.packet()
        unknown["metadata"] = {"unexpected": True}
        result = self.orchestrator.ingest(unknown)
        self.assertFalse(result.accepted)
        self.assertEqual("UNEXPECTED_PACKET_FIELD", result.error_code)

        model = self.packet()
        model["fact_observation"]["prediction"] = {"home": 0.8}
        result = self.orchestrator.ingest(model)
        self.assertFalse(result.accepted)
        self.assertEqual("BOUNDARY_FIELD_FORBIDDEN", result.error_code)

    def test_v333_isolation_f_drive_and_no_write_boundary(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        output = resolve_f_drive_output_path("F:/Projects/jcfb-v4", "work/v4-023/evidence.json")
        self.assertEqual("F:", output.drive.upper())
        self.assertFalse(any(path.startswith("database/migrations/") for path in changed))


if __name__ == "__main__":
    unittest.main()
