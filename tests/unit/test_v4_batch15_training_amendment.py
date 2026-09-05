import hashlib
import json
import subprocess
import unittest
from pathlib import Path


class V4Batch15TrainingAmendmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.config = cls.root / "config" / "prediction_training"
        cls.registry = json.loads((cls.config / "v4_batch15_execution_work_package_registry.json").read_text(encoding="utf-8"))
        cls.archive = json.loads((cls.config / "historical_source_archive_contract.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((cls.config / "execution_work_package_schema.json").read_text(encoding="utf-8"))

    @staticmethod
    def canonical_hash(document):
        value = {key: item for key, item in document.items() if key != "canonical_hash"}
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def test_validator_passes(self):
        result = subprocess.run(
            ["python", str(self.root / "scripts" / "validate_v4_batch15_training_amendment.py")],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("V4 BATCH-15 TRAINING AMENDMENT VALIDATION: PASS", result.stdout)

    def test_all_machine_readable_artifacts_have_recomputable_hashes(self):
        for document in (self.schema, self.registry, self.archive):
            self.assertRegex(document["canonical_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["canonical_hash"], self.canonical_hash(document))

    def test_execution_entity_is_not_a_v4_task(self):
        self.assertEqual("execution-work-package@1.0.0", self.registry["contract_version"])
        self.assertFalse(self.registry["entity_rules"]["is_v4_task"])
        self.assertEqual("V4-001..V4-100", self.registry["task_namespace_boundary"]["reserved_namespace"])
        self.assertEqual([], self.registry["task_namespace_boundary"]["task_ids_created"])

    def test_five_ids_are_deterministic_and_outside_task_namespace(self):
        packages = self.registry["work_packages"]
        self.assertEqual([f"B15-EWP-{index:03d}" for index in range(1, 6)], [item["work_package_id"] for item in packages])
        self.assertEqual(5, len({item["work_package_id"] for item in packages}))
        self.assertTrue(all(item["entity_type"] == "EXECUTION_WORK_PACKAGE" for item in packages))
        self.assertTrue(all(not item["work_package_id"].startswith("V4-") for item in packages))

    def test_parent_scope_and_complete_boundary_are_explicit(self):
        self.assertTrue(all(item["parent_batch"] == "BATCH-15" for item in self.registry["work_packages"]))
        self.assertTrue(all(item["parent_task_scope"] for item in self.registry["work_packages"]))
        self.assertTrue(self.registry["entity_rules"]["work_package_complete_does_not_complete_parent_task"])

    def test_dependency_chain_is_acyclic_and_mandatory(self):
        packages = self.registry["work_packages"]
        self.assertEqual([[], ["B15-EWP-001"], ["B15-EWP-002"], ["B15-EWP-003"], ["B15-EWP-004"]], [item["dependencies"] for item in packages])
        self.assertEqual(4, len(self.registry["dependency_edges"]))
        self.assertTrue(all(edge["edge_type"] in {"MANDATORY_PREREQUISITE", "SEPARATE_FIT_APPROVAL_PREREQUISITE"} for edge in self.registry["dependency_edges"]))

    def test_ewp003_is_authorized_but_formal_fit_remains_unauthorized(self):
        self.assertTrue(self.registry["work_packages"][0]["execution_authorized"])
        self.assertTrue(self.registry["work_packages"][1]["execution_authorized"])
        self.assertTrue(self.registry["work_packages"][2]["execution_authorized"])
        self.assertTrue(all(item["execution_authorized"] is False for item in self.registry["work_packages"][3:]))
        self.assertEqual("SEPARATE_APPROVAL_REQUIRED", self.registry["work_packages"][-1]["status"])
        self.assertFalse(self.registry["entity_rules"]["may_authorize_formal_model_fit"])

    def test_work_packages_require_status_dod_evidence_manifest_and_lineage(self):
        for item in self.registry["work_packages"]:
            self.assertIn(item["status"], {"REGISTERED_NOT_EXECUTABLE", "SEPARATE_APPROVAL_REQUIRED", "COMPLETE"})
            self.assertTrue(item["definition_of_done"])
            self.assertTrue(item["evidence_manifest"])
            self.assertTrue(item["commit_lineage"]["required"])
            if item["work_package_id"] in {"B15-EWP-001", "B15-EWP-002"}:
                self.assertTrue(item["commit_lineage"]["commit_ids"])
                self.assertNotEqual("NOT_GENERATED", item["artifact_hash"])
            elif item["work_package_id"] == "B15-EWP-003":
                self.assertTrue(item["commit_lineage"]["commit_ids"])
                self.assertEqual("NOT_GENERATED", item["artifact_hash"])
            else:
                self.assertEqual([], item["commit_lineage"]["commit_ids"])
                self.assertEqual("NOT_GENERATED", item["artifact_hash"])

    def test_archive_has_both_acquisition_modes(self):
        self.assertEqual({"PROSPECTIVE_CAPTURE", "VERIFIED_HISTORICAL_BACKFILL"}, set(self.archive["acquisition_modes"]))
        self.assertTrue(self.archive["prospective_capture"]["append_only"])
        self.assertEqual("APPROVED_FOR_FUTURE_CAPTURE_GOVERNANCE", self.archive["prospective_capture"]["status"])

    def test_unverifiable_time_is_rejected(self):
        self.assertEqual("REJECT_AS_NOT_ELIGIBLE_FOR_AS_OF_TRAINING", self.archive["unverifiable_time_action"])
        self.assertIn("availability_at", self.archive["record_required_fields"])
        self.assertIn("source_timestamp", self.archive["record_required_fields"])

    def test_raw_fact_reingestion_is_conditional_and_v3_runtime_is_forbidden(self):
        policy = self.archive["raw_fact_reingestion"]
        self.assertEqual("CONDITIONALLY_APPROVED", policy["decision"])
        self.assertTrue(policy["requires_reingestion"])
        self.assertEqual("FORBIDDEN", policy["direct_v3_runtime_reference"])

    def test_required_provenance_fields_are_present(self):
        required = set(self.archive["record_required_fields"])
        self.assertTrue({"source", "source_reference", "source_timestamp", "captured_at", "ingested_at", "original_payload_or_file_hash", "match_identity", "market_or_context_type", "revision_identity", "provenance"}.issubset(required))

    def test_approval_document_records_blocked_readiness(self):
        text = (self.root / "docs" / "JCFB_V4_BATCH_15_MODEL_TRAINING_ARCHITECTURE_AMENDMENT_APPROVAL_DECISION.md").read_text(encoding="utf-8")
        for term in ("MODEL_TRAINING_EXECUTION_IDENTITY RESOLVED", "ACTIVE_GOVERNANCE_ONLY", "NOT_FOUND", "PREDICTION_TRAINING_READINESS_BLOCKED", "UNKNOWN", "NOT_READY_FOR_IMPLEMENTATION"):
            self.assertIn(term, text)

    def test_storage_policy_separates_runtime_and_fixtures(self):
        text = (self.root / "docs" / "JCFB_V4_F_DRIVE_HISTORICAL_ARCHIVE_STORAGE_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("F:\\Projects\\jcfb-v4\\approved_data\\historical_source_archive", text)
        self.assertIn(".runtime", text)
        self.assertIn("tests/fixtures", text)
        self.assertIn("cannot\nbe counted as training data", text)

    def test_source_audit_is_read_only_and_does_not_invent_population(self):
        text = (self.root / "docs" / "JCFB_V4_BATCH_15_HISTORICAL_SOURCE_AUDIT.md").read_text(encoding="utf-8")
        for term in ("VERIFIED_HISTORICAL_BACKFILL: NOT FOUND", "PROSPECTIVE_CAPTURE: GOVERNANCE APPROVED", "HISTORICAL_BACKFILL_INSUFFICIENT", "NOT_AVAILABLE", "UNKNOWN", "read-only audit", "for import"):
            self.assertIn(term, text)
        self.assertIn("0 usable", text)

    def test_no_prohibited_implementation_artifact_is_registered(self):
        names = " ".join(self.registry["work_packages"][-1]["output_artifacts"])
        self.assertIn("formal-fit-report", names)
        self.assertFalse(self.registry["work_packages"][-1]["execution_authorized"])
        self.assertEqual([], self.registry["work_packages"][-1]["commit_lineage"]["commit_ids"])


if __name__ == "__main__":
    unittest.main()
