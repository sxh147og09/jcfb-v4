"""Unit contracts for the BATCH-03 readiness and evidence package."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.migration_harness.acceptance import (
    ACCEPTANCE_PACKAGE_SCHEMA_PATH,
    EVIDENCE_INDEX_PATH,
    build_roll_forward_drill,
    validate_evidence_index,
)
from tools.migration_harness.readiness import (
    RUNTIME_PENDING_STATUS,
    assess_readiness,
    load_readiness_contract,
    load_staging_target_template,
    target_identity_snapshot,
    validate_readiness_contract_document,
    validate_target_manifest,
)


class Batch03ReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]

    def test_readiness_contract_and_template_are_valid(self):
        contract = load_readiness_contract(self.repo_root)
        template = load_staging_target_template(self.repo_root)
        self.assertEqual([], validate_readiness_contract_document(contract))
        self.assertEqual([], validate_target_manifest(template))
        result = assess_readiness(template)
        self.assertEqual("NOT_READY", result["status"])
        self.assertEqual(RUNTIME_PENDING_STATUS, result["reason"])
        self.assertFalse(result["connect_allowed"])
        self.assertFalse(result["production_apply_allowed"])

    def test_production_is_always_hard_blocked(self):
        target = copy.deepcopy(load_staging_target_template(self.repo_root))
        target.update({
            "environment": "PRODUCTION",
            "provider": "PRODUCTION_SUPABASE",
            "target_state": "BLOCKED",
            "non_production": False,
            "disposable": False,
            "connect_permission": "BLOCKED",
        })
        target["network_security"]["allow_network"] = False
        issues = validate_target_manifest(target)
        self.assertIn("PRODUCTION_TARGET_HARD_BLOCK", {issue.code for issue in issues})
        self.assertEqual("BLOCKED", assess_readiness(target)["status"])
        self.assertFalse(assess_readiness(target)["production_apply_allowed"])

    def test_complete_read_only_runtime_evidence_allows_only_disposable_dry_run(self):
        target = copy.deepcopy(load_staging_target_template(self.repo_root))
        target["connect_permission"] = "EXPLICITLY_GRANTED"
        runtime = {
            "status": "SUPPLIED_READ_ONLY",
            "read_only_catalog_verified": True,
            "target_identity_verified": True,
            "version_compatible": True,
            "extensions_available": True,
            "namespace_isolation_pass": True,
            "history_integrity_pass": True,
            "partial_state_absent": True,
            "permission_boundary_pass": True,
            "backup_decision_recorded": True,
            "secret_presence_verified": True,
            "production_release_reviewed": True,
            "connector_invoked": False,
        }
        result = assess_readiness(target, runtime_evidence=runtime)
        self.assertEqual("READY_FOR_DISPOSABLE_DRY_RUN", result["status"])
        self.assertTrue(result["connect_allowed"])
        self.assertFalse(result["production_apply_allowed"])

    def test_raw_credential_field_is_rejected(self):
        target = copy.deepcopy(load_staging_target_template(self.repo_root))
        target["non_secret_database_identity"]["database_url"] = "redacted-fixture-must-not-be-present"
        codes = {issue.code for issue in validate_target_manifest(target)}
        self.assertIn("RAW_SECRET_FIELD_PRESENT", codes)


class Batch03EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]

    def test_evidence_index_resolves_all_registered_sources(self):
        self.assertEqual([], validate_evidence_index(self.repo_root))
        index = json.loads((self.repo_root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8"))
        self.assertEqual(80, len(index["entries"]))
        self.assertEqual(80, len({entry["ref"] for entry in index["entries"]}))

    def test_acceptance_schema_binds_batch_scope_and_boundary(self):
        schema = json.loads((self.repo_root / ACCEPTANCE_PACKAGE_SCHEMA_PATH).read_text(encoding="utf-8"))
        self.assertEqual("v4-batch-03-acceptance-package@1.0.0", schema["$id"])
        self.assertEqual("BATCH-03", schema["properties"]["batch_id"]["const"])
        self.assertEqual(["V4-016", "V4-017"], schema["properties"]["task_ids"]["const"])
        self.assertTrue(schema["properties"]["no_production_apply_in_this_batch"]["const"])

    def test_roll_forward_drill_is_simulation_only_and_forward_only(self):
        drill = build_roll_forward_drill()
        self.assertEqual("PASS", drill["status"])
        self.assertFalse(drill["executed"])
        self.assertEqual("ROLL_FORWARD_ONLY", drill["decision"])
        self.assertFalse(drill["production_apply_allowed"])
        self.assertTrue(all(step["executed"] is False for step in drill["steps"]))
        self.assertIn("retain_partial_history", {step["action"] for step in drill["steps"]})


if __name__ == "__main__":
    unittest.main()
