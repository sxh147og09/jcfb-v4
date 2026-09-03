from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.migration_harness.canonical_hash import verify_candidate_hashes
from tools.migration_harness.production_target import (
    build_production_readiness_review,
    load_production_target_binding,
    production_target_binding_report,
    run_production_target_cross_doc_consistency,
)
from tools.migration_harness.supabase_preflight import (
    APPLY_BEFORE_IDS,
    EXPECTED_BASELINE_HISTORY,
    EXPECTED_BASELINE_COUNTS,
    EXPECTED_V4_SEQUENCE,
    POST_APPLY_IDS,
    PREFLIGHT_PLAN_ID,
    advisor_fingerprint,
    build_forward_fix_recovery,
    build_supabase_preflight_report,
    classify_post_apply_schema,
    compare_advisor_findings,
    compare_schema_object_identities,
    detect_baseline_migration_drift,
    detect_partial_apply,
    load_supabase_preflight_plan,
    load_supabase_preflight_schema,
    validate_advisor_baseline,
    validate_baseline_migration_history,
    validate_supabase_preflight_plan_document,
    verify_git_head_match,
)


class SupabasePreflightPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.plan = load_supabase_preflight_plan(cls.repo_root)
        cls.schema = load_supabase_preflight_schema(cls.repo_root)
        cls.binding = load_production_target_binding(cls.repo_root)

    def test_checked_in_contract_is_complete_and_bound_to_approved_target(self):
        self.assertEqual(PREFLIGHT_PLAN_ID, self.plan["$id"])
        self.assertEqual(PREFLIGHT_PLAN_ID, self.plan["contract_version"])
        self.assertEqual([], validate_supabase_preflight_plan_document(self.plan, self.binding))
        report = build_supabase_preflight_report(self.repo_root, self.binding)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("KNOWN", report["production_target_identity"])
        self.assertEqual("PASS", report["supabase_preflight_plan"])
        self.assertEqual("READY_FOR_PRODUCTION_APPLY_APPROVAL", report["final_readiness_decision"])
        self.assertEqual("BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3", report["next_stage"])

    def test_plan_and_schema_are_valid_json_artifacts(self):
        self.assertIsInstance(self.plan, dict)
        self.assertIsInstance(self.schema, dict)
        self.assertEqual(PREFLIGHT_PLAN_ID, self.schema["$id"])
        self.assertEqual("./v4_supabase_preflight_plan.schema.json", self.plan["$schema"])

    def test_baseline_identity_counts_history_and_checklist_are_exact(self):
        baseline = self.plan["production_baseline"]
        self.assertEqual(EXPECTED_BASELINE_COUNTS, baseline["schema_counts"])
        self.assertEqual(9, baseline["migration_history"]["count"])
        self.assertEqual([], validate_baseline_migration_history(baseline["migration_history"]["entries"]))
        self.assertEqual(
            list(EXPECTED_BASELINE_HISTORY),
            [(row["version"], row["name"]) for row in baseline["migration_history"]["entries"]],
        )
        self.assertEqual(list(APPLY_BEFORE_IDS), [item["id"] for item in self.plan["apply_before_checklist"]])
        self.assertEqual(list(POST_APPLY_IDS), [item["id"] for item in self.plan["post_apply_verification_plan"]])
        self.assertGreater(len(baseline["schema_object_identities"]["known_identity_samples"]), 0)

    def test_target_database_counts_and_history_drift_are_blocked(self):
        mutated = copy.deepcopy(self.plan)
        mutated["production_baseline"]["target"]["project_ref"] = "wrong-project-ref"
        mutated["production_baseline"]["schema_counts"]["public_tables"] = 19
        mutated["production_baseline"]["migration_history"]["entries"][0]["name"] = "unexpected"
        codes = {issue.code for issue in validate_supabase_preflight_plan_document(mutated, self.binding)}
        self.assertIn("PREFLIGHT_BINDING_MISMATCH", codes)
        self.assertIn("PREFLIGHT_BASELINE_SCHEMA_COUNTS", codes)
        self.assertIn("PREFLIGHT_BASELINE_HISTORY_MISMATCH", codes)

        expected = self.plan["production_baseline"]["migration_history"]["entries"]
        observed = copy.deepcopy(expected)
        observed[1]["name"] = "drifted-name"
        drift = detect_baseline_migration_drift(expected, observed)
        self.assertEqual("BLOCKED_UNEXPECTED_PRE_EXISTING_DRIFT", drift["status"])
        self.assertEqual([list(EXPECTED_BASELINE_HISTORY[1])], drift["missing"])
        self.assertEqual([[EXPECTED_BASELINE_HISTORY[1][0], "drifted-name"]], drift["unexpected"])

    def test_capture_metadata_and_no_secret_fields_are_required(self):
        baseline = self.plan["production_baseline"]
        self.assertEqual("connected Supabase read-only inspection", baseline["capture"]["capture_source"])
        self.assertTrue(baseline["capture"]["read_only"])
        self.assertEqual("NO", baseline["capture"]["production_writes_performed"])
        mutated = copy.deepcopy(self.plan)
        mutated["production_baseline"]["secret_value"] = "must-be-rejected"
        codes = {issue.code for issue in validate_supabase_preflight_plan_document(mutated, self.binding)}
        self.assertIn("PREFLIGHT_SECRET_FIELD_PRESENT", codes)

    def test_advisor_baselines_have_stable_fingerprints_and_v333_attribution(self):
        self.assertEqual([], validate_advisor_baseline(self.plan))
        for advisor_key in ("security_advisor", "performance_advisor"):
            for finding in self.plan["production_baseline"][advisor_key]["findings"]:
                self.assertEqual(finding["fingerprint"], advisor_fingerprint(finding))
                self.assertEqual("PRE_EXISTING_V3_3_3_DEBT", finding["attribution"])

    def test_advisor_before_after_contract_blocks_new_security_regressions(self):
        baseline = self.plan["production_baseline"]["security_advisor"]
        unchanged = compare_advisor_findings(baseline, copy.deepcopy(baseline))
        self.assertEqual("PASS", unchanged["status"])
        self.assertEqual(4, unchanged["baseline_count"])

        after = copy.deepcopy(baseline)
        after["findings"].append({
            "advisor": "supabase_security",
            "code": "new_v4_security_issue",
            "severity": "WARN",
            "scope": "public",
            "object_identity": "public.v4_example",
            "attribution": "V4_DECLARED",
        })
        blocked = compare_advisor_findings(baseline, after)
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual(1, len(blocked["new_security_error_warn"]))

    def test_advisor_info_and_baseline_debt_changes_are_not_silent(self):
        baseline = self.plan["production_baseline"]["performance_advisor"]
        after = copy.deepcopy(baseline)
        after["findings"].append({
            "advisor": "supabase_performance",
            "code": "new_info",
            "severity": "INFO",
            "scope": "public",
            "object_identity": "public.v4_example",
            "attribution": "V4_DECLARED",
        })
        review = compare_advisor_findings(baseline, after)
        self.assertEqual("REVIEW_REQUIRED", review["status"])
        self.assertEqual(1, len(review["new_info_review_required"]))

        missing = copy.deepcopy(baseline)
        missing["findings"].pop()
        blocked = compare_advisor_findings(baseline, missing)
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertTrue(blocked["baseline_debt_change_requires_review"])

    def test_schema_diff_compares_identity_and_definition_signature(self):
        baseline = {"objects": [{"object_kind": "table", "schema": "public", "name": "legacy", "signature_hash": "sha256:one"}]}
        self.assertEqual("PASS", compare_schema_object_identities(baseline, copy.deepcopy(baseline))["status"])

        changed = copy.deepcopy(baseline)
        changed["objects"][0]["signature_hash"] = "sha256:two"
        self.assertEqual("BLOCKED", compare_schema_object_identities(baseline, changed)["status"])
        missing = {"objects": []}
        self.assertEqual("BLOCKED", compare_schema_object_identities(baseline, missing)["status"])
        extra = {"objects": baseline["objects"] + [{"object_kind": "view", "schema": "public", "name": "unexpected"}]}
        self.assertEqual("BLOCKED", compare_schema_object_identities(baseline, extra)["status"])

    def test_post_apply_schema_classification_separates_v333_and_v4(self):
        baseline = {"objects": [{"object_kind": "table", "schema": "public", "name": "legacy", "signature_hash": "sha256:legacy", "attribution": "PRE_EXISTING_V3_3_3_BASELINE"}]}
        v4 = {"objects": [{"object_kind": "table", "schema": "public", "name": "v4_new", "signature_hash": "sha256:v4", "attribution": "V4_DECLARED"}]}
        after = {"objects": baseline["objects"] + v4["objects"]}
        result = classify_post_apply_schema(baseline, after, v4)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(["table.public.legacy"], result["preserved_v3_3_3"])
        self.assertEqual(["table.public.v4_new"], result["v4_added"])

        unexpected = {"objects": after["objects"] + [{"object_kind": "view", "schema": "public", "name": "not_declared"}]}
        result = classify_post_apply_schema(baseline, unexpected, v4)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(["view.public.not_declared"], result["unexpected_added"])

        changed_preexisting = copy.deepcopy(after)
        changed_preexisting["objects"][0]["signature_hash"] = "sha256:changed"
        result = classify_post_apply_schema(baseline, changed_preexisting, v4)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(["table.public.legacy"], result["changed_preexisting"])

    def test_partial_apply_stops_and_requires_forward_fix_without_history_repair(self):
        not_started = detect_partial_apply([])
        self.assertEqual("NOT_STARTED", not_started["state"])
        self.assertEqual("PASS", not_started["status"])
        self.assertFalse(not_started["stop_further_execution"])

        partial = detect_partial_apply([{"sequence": "0001", "status": "COMMITTED"}])
        self.assertEqual("PARTIAL_APPLY_STOP_REQUIRED", partial["state"])
        self.assertEqual("BLOCKED", partial["status"])
        self.assertTrue(partial["stop_further_execution"])
        self.assertTrue(partial["do_not_repair_history_manually"])

        failed = detect_partial_apply([
            {"sequence": "0001", "status": "COMMITTED"},
            {"sequence": "0002", "status": "FAILED"},
        ])
        self.assertEqual("FORWARD_FIX_REQUIRED", failed["state"])
        self.assertTrue(build_forward_fix_recovery(failed["state"])["retain_history"])
        self.assertFalse(build_forward_fix_recovery(failed["state"])["rewrite_history"])

        complete = detect_partial_apply([{"sequence": sequence, "status": "COMMITTED"} for sequence in EXPECTED_V4_SEQUENCE])
        self.assertEqual("COMPLETE", complete["state"])
        self.assertEqual("PASS", complete["status"])

    def test_git_head_match_is_a_hard_apply_before_gate(self):
        head = "a" * 40
        self.assertEqual("PASS", verify_git_head_match(head, head)["status"])
        mismatch = verify_git_head_match(head, "b" * 40)
        self.assertEqual("BLOCKED", mismatch["status"])
        self.assertFalse(mismatch["matches"])
        self.assertEqual("BLOCK", mismatch["failure_action"])

    def test_binding_readiness_and_hard_block_remain_separate_from_preflight_pass(self):
        binding_report = production_target_binding_report(self.repo_root)
        self.assertEqual("PASS", binding_report["supabase_preflight_plan"]["status"])
        self.assertEqual("PASS", binding_report["production_hard_block_preserved"])
        self.assertFalse(binding_report["production_apply_gate"]["approval_granted"])
        self.assertFalse(binding_report["production_apply_gate"]["production_apply_allowed"])

        review = build_production_readiness_review(self.repo_root)
        self.assertEqual("PASS", review["final_readiness_review"]["status"])
        self.assertEqual("READY_FOR_PRODUCTION_APPLY_APPROVAL", review["final_readiness_review"]["decision"])
        self.assertTrue(review["final_readiness_review"]["explicit_apply_approval_required"])
        self.assertFalse(review["production_apply_allowed"])

    def test_canonical_hashes_remain_nine_of_nine_without_write(self):
        report = verify_candidate_hashes(self.repo_root)
        self.assertEqual("PASS", report["status"])
        self.assertEqual((9, 9, 0), (report["candidate_count"], report["matched_count"], report["pending_count"]))

    def test_self_audit_and_cross_document_consistency_include_preflight(self):
        consistency = run_production_target_cross_doc_consistency(self.repo_root)
        self.assertEqual("PASS", consistency["status"])
        self.assertEqual([], consistency["failures"])

    def test_report_execution_boundary_is_read_only(self):
        report = build_supabase_preflight_report(self.repo_root, self.binding)
        boundary = report["execution_boundary"]
        self.assertFalse(boundary["database_connected"])
        self.assertFalse(boundary["sql_executed"])
        self.assertEqual("NO", boundary["production_db_writes_performed"])
        self.assertEqual("NO", boundary["supabase_writes_performed"])
        self.assertEqual("NO", boundary["batch_04_executed"])
        self.assertEqual("NO", boundary["v4_018_v4_019_changed"])
        self.assertEqual("NO", boundary["v333_mutated"])


if __name__ == "__main__":
    unittest.main()
