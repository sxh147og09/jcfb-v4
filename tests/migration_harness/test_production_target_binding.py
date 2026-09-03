from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.migration_harness.canonical_hash import verify_candidate_hashes
from tools.migration_harness.production_target import (
    PRODUCTION_PROJECT_REF,
    PRODUCTION_TARGET_IDENTITY_PATH,
    build_production_readiness_review,
    load_production_target_binding,
    production_target_binding_report,
    run_production_target_cross_doc_consistency,
    validate_production_target_binding,
)
from tools.migration_harness.runtime_executor import RuntimeExecutor, default_disposable_target, review_runtime_evidence
from tools.migration_harness.security import secret_scan


class ProductionTargetBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.contract = load_production_target_binding(cls.repo_root)

    def test_checked_in_binding_is_valid_and_records_approved_identity(self):
        result = validate_production_target_binding(self.contract)
        self.assertTrue(result.ok)
        self.assertEqual("PASS", result.status.value)
        self.assertTrue(result.exactly_one_production_target)
        self.assertTrue(result.disposable_production_isolated)
        target = result.production_target
        self.assertIsNotNone(target)
        self.assertEqual("Supabase", target["provider"])
        self.assertEqual(PRODUCTION_PROJECT_REF, target["project_ref"])
        self.assertEqual("us-west-2", target["region"])
        self.assertEqual(17, target["postgres_major"])
        self.assertEqual("PRODUCTION", target["role"])
        self.assertEqual("BOUND_APPROVED", target["binding_state"])
        self.assertEqual("human_approver", target["approved_by"])
        self.assertEqual("explicit user confirmation in ChatGPT", target["approval_basis"])

    def test_contract_declares_all_three_environments_and_exactly_one_production(self):
        environments = [target["environment"] for target in self.contract["targets"]]
        self.assertEqual({"DISPOSABLE_LOCAL", "STAGING", "PRODUCTION"}, set(environments))
        self.assertEqual(1, environments.count("PRODUCTION"))
        self.assertEqual("NOT_BOUND", next(target for target in self.contract["targets"] if target["environment"] == "STAGING")["binding_state"])

    def test_production_identity_fields_are_enforced(self):
        mutations = (
            ("provider", "STAGING_SUPABASE", "PRODUCTION_PROVIDER_INVALID"),
            ("project_ref", "not-a-supabase-ref", "PRODUCTION_PROJECT_REF_INVALID"),
            ("region", "eu-central-1", "PRODUCTION_REGION_INVALID"),
            ("postgres_major", 16, "PRODUCTION_POSTGRES_MAJOR_INVALID"),
            ("role", "STAGING", "TARGET_ROLE_ENVIRONMENT_MISMATCH"),
            ("binding_state", "NOT_BOUND", "PRODUCTION_BINDING_STATE_INVALID"),
        )
        for field, value, expected_code in mutations:
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.contract)
                mutated["targets"][2][field] = value
                codes = {issue.code for issue in validate_production_target_binding(mutated).issues}
                self.assertIn(expected_code, codes)

    def test_exactly_one_production_target_is_required(self):
        duplicated = copy.deepcopy(self.contract)
        duplicated["targets"].append(copy.deepcopy(duplicated["targets"][2]))
        result = validate_production_target_binding(duplicated)
        self.assertFalse(result.ok)
        self.assertIn("EXACTLY_ONE_PRODUCTION_TARGET", {issue.code for issue in result.issues})

    def test_production_cannot_share_disposable_or_staging_identity(self):
        mutated = copy.deepcopy(self.contract)
        mutated["targets"][0]["project_ref"] = PRODUCTION_PROJECT_REF
        result = validate_production_target_binding(mutated)
        self.assertFalse(result.ok)
        self.assertIn("PRODUCTION_TARGET_ISOLATION_INVALID", {issue.code for issue in result.issues})

    def test_secret_fields_are_rejected_and_no_secret_policy_is_recorded(self):
        mutated = copy.deepcopy(self.contract)
        mutated["targets"][2]["service_role_key"] = "fixture-secret-field-must-not-exist"
        result = validate_production_target_binding(mutated)
        self.assertFalse(result.ok)
        self.assertIn("SECRET_FIELD_PRESENT", {issue.code for issue in result.issues})
        self.assertFalse(self.contract["secret_policy"]["secrets_stored"])
        self.assertFalse(self.contract["secret_policy"]["raw_values_allowed"])

    def test_apply_approval_is_required_and_binding_cannot_authorize_apply(self):
        report = production_target_binding_report(self.repo_root)
        self.assertEqual("PASS", report["human_approval_recorded"])
        self.assertEqual("PASS", report["production_hard_block_preserved"])
        self.assertEqual("PASS", report["explicit_apply_approval_required"])
        gate = report["production_apply_gate"]
        self.assertEqual("PASS", gate["status"])
        self.assertTrue(gate["hard_block_preserved"])
        self.assertTrue(gate["explicit_approval_required"])
        self.assertFalse(gate["approval_granted"])
        self.assertFalse(gate["target_binding_authorizes_apply"])
        self.assertFalse(gate["production_apply_allowed"])
        self.assertEqual("PENDING_PRODUCTION_APPLY_APPROVAL", gate["approval_state"])

        target = default_disposable_target()
        target.update({
            "target_id": "jcfb-v4-production-review",
            "environment": "PRODUCTION",
            "provider": "PRODUCTION_SUPABASE",
            "disposable": False,
            "connect_permission": "BLOCKED",
        })
        blocked = RuntimeExecutor(self.repo_root).plan(target=target, mode="PRODUCTION_APPLY")
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertIn("PRODUCTION_TARGET_HARD_BLOCK", blocked["blocking_reasons"])
        self.assertFalse(blocked["execution_boundary"]["connector_invoked"])

    def test_production_readiness_passes_static_preflight_without_authorizing_apply(self):
        review = build_production_readiness_review(self.repo_root)
        self.assertEqual("KNOWN", review["production_target_identity"])
        self.assertEqual("READY_FOR_PRODUCTION_APPLY_APPROVAL", review["status"])
        self.assertEqual("PASS", review["supabase_preflight_plan"]["status"])
        self.assertFalse(review["supabase_preflight_plan"]["automatic_pass"])
        self.assertFalse(review["production_apply_allowed"])
        self.assertEqual("NO", review["supabase_writes_performed"])

    def test_runtime_evidence_review_exposes_known_identity_without_authorizing_apply(self):
        review = review_runtime_evidence(self.repo_root, report_dir=self.repo_root / ".runtime" / "missing-production-review-fixture")
        self.assertEqual("KNOWN", review["production_target_identity"])
        self.assertEqual("PASS", review["supabase_preflight_plan"]["status"])
        self.assertFalse(review["supabase_preflight_plan"]["automatic_pass"])
        self.assertFalse(review["production_apply_allowed"])
        self.assertEqual("PASS", review["checks"]["production_target_identity"]["status"])

    def test_legacy_design_validator_scope_excludes_runtime_candidates(self):
        validator = (self.repo_root / "scripts/validate_v4_migration_harness_design.ps1").read_text(encoding="utf-8")
        self.assertIn("database/schema", validator)
        self.assertIn("database/migrations/v4')", validator)
        self.assertIn("Runtime candidates have a different contract", validator)
        self.assertNotIn("Repo-Path 'database') -Recurse -File -Filter '*.sql'", validator)

    def test_canonical_hash_verifier_remains_nine_of_nine(self):
        report = verify_candidate_hashes(self.repo_root)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(9, report["candidate_count"])
        self.assertEqual(9, report["matched_count"])
        self.assertEqual(0, report["pending_count"])
        self.assertEqual("PASS", report["dependency_status"])

    def test_binding_cross_document_consistency_is_clean(self):
        result = run_production_target_cross_doc_consistency(self.repo_root)
        self.assertEqual("PASS", result["status"])
        self.assertEqual([], result["failures"])

    def test_repository_secret_scan_is_clean(self):
        result = secret_scan(self.repo_root)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(0, result["hit_count"])
        self.assertFalse(result["values_logged"])

    def test_binding_and_schema_are_valid_json_artifacts(self):
        schema = json.loads((self.repo_root / "config/migration_harness/v4_production_target_identity.schema.json").read_text(encoding="utf-8"))
        contract = json.loads((self.repo_root / PRODUCTION_TARGET_IDENTITY_PATH).read_text(encoding="utf-8"))
        self.assertEqual("v4-production-target-identity@1.0.0", schema["$id"])
        self.assertEqual("v4-production-target-identity@1.0.0", contract["$id"])
        self.assertEqual("./v4_production_target_identity.schema.json", contract["$schema"])


if __name__ == "__main__":
    unittest.main()
