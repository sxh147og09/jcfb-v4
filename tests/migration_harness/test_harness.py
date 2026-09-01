from __future__ import annotations

import copy
import unittest
from pathlib import Path

from tools.migration_harness.audits import run_git_diff_check
from tools.migration_harness.common import is_v4_hash
from tools.migration_harness.contracts import (
    validate_canonical_latest,
    validate_function_security,
    validate_immutable_mutation,
    validate_market_payload,
    validate_prematch_run,
    validate_production_uniqueness,
    validate_public_projection,
    validate_review_scope,
    validate_role_write,
    validate_tier_a_pair,
    validate_unknown_not_coerced,
)
from tools.migration_harness.manifest import (
    load_manifest,
    manifest_identity_hash,
    validate_history_integrity,
    validate_manifest,
)
from tools.migration_harness.models import CheckStatus, RunnerStatus
from tools.migration_harness.negative import (
    load_negative_registry,
    run_negative_cases,
    validate_negative_registry,
)
from tools.migration_harness.preflight import PREFLIGHT_IDS, run_preflight
from tools.migration_harness.runner import DryRunRunner, can_transition
from tools.migration_harness.schema_diff import (
    compare_schema_snapshot,
    load_expected_snapshot,
    validate_expected_snapshot_shape,
)
from tools.migration_harness.security import secret_scan
from tools.migration_harness.smoke import (
    load_smoke_catalog,
    runtime_pending_smoke_report,
    validate_smoke_catalog,
)
from tools.migration_harness.target import validate_target_descriptor


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]

    def valid_target(self):
        return {
            "descriptor_version": "v4-migration-target-descriptor@1.0.0",
            "target_id": "local-v4-validation",
            "environment": "DISPOSABLE_LOCAL",
            "provider": "LOCAL_POSTGRES",
            "database_identity": {
                "server_name": "local-disposable",
                "database_name": "jcfb_v4_validation",
                "project_or_cluster_ref": "local-cluster-v4",
            },
            "disposable": True,
            "contains_v333_objects": False,
            "contains_production_data": False,
            "credential_env_name": "JCFB_V4_TEST_DATABASE_URL",
            "allow_network": False,
            "connect_permission": "EXPLICITLY_GRANTED",
            "reset_and_teardown_contract": {
                "reset_before_run": True,
                "destroy_after_evidence": True,
                "operator_owned": True,
            },
        }

    def test_manifest_loads_authoritative_nine_entries(self):
        result = load_manifest(self.repo_root)
        self.assertTrue(result.ok)
        self.assertEqual(9, len(result.entries))
        self.assertEqual("PASS", result.sequence_status)
        self.assertEqual("PASS", result.dependency_status)
        self.assertEqual(9, result.pending_hash_count)

    def test_manifest_identity_hash_is_stable(self):
        first = manifest_identity_hash(load_manifest(self.repo_root))
        second = manifest_identity_hash(load_manifest(self.repo_root))
        self.assertEqual(first, second)
        self.assertTrue(is_v4_hash(first))

    def test_manifest_missing_sequence_is_rejected(self):
        path = self.repo_root / "database/migrations/v4/0000_manifest.md"
        source = path.read_text(encoding="utf-8")
        current = load_manifest(self.repo_root)
        sql = {entry.file: (self.repo_root / entry.file).read_text(encoding="utf-8") for entry in current.entries}
        mutated = "\n".join(line for line in source.splitlines() if not line.startswith("| 0005 |"))
        self.assertFalse(validate_manifest(mutated, sql).ok)

    def test_manifest_duplicate_sequence_is_rejected(self):
        path = self.repo_root / "database/migrations/v4/0000_manifest.md"
        source = path.read_text(encoding="utf-8")
        current = load_manifest(self.repo_root)
        sql = {entry.file: (self.repo_root / entry.file).read_text(encoding="utf-8") for entry in current.entries}
        row = next(line for line in source.splitlines() if line.startswith("| 0005 |"))
        self.assertFalse(validate_manifest(source + "\n" + row, sql).ok)

    def test_runner_default_is_plan_only_and_no_write(self):
        report = DryRunRunner(self.repo_root).plan()
        self.assertEqual(RunnerStatus.PLANNED.value, report["status"])
        self.assertFalse(report["execution_boundary"]["connector_invoked"])
        self.assertFalse(report["execution_boundary"]["database_connected"])
        self.assertFalse(report["execution_boundary"]["sql_executed"])
        self.assertEqual("NO", report["execution_boundary"]["production_db_writes_performed"])
        self.assertEqual(9, len(report["steps"]))

    def test_runner_plan_hash_is_deterministic(self):
        runner = DryRunRunner(self.repo_root)
        self.assertEqual(runner.plan()["plan_hash"], runner.plan()["plan_hash"])

    def test_runner_dry_run_without_target_is_blocked(self):
        report = DryRunRunner(self.repo_root).plan(mode="DRY_RUN")
        self.assertEqual(RunnerStatus.PRECHECK_BLOCKED.value, report["status"])
        self.assertIn("TARGET_REQUIRED_FOR_DRY_RUN", report["blocking_reasons"])

    def test_runner_apply_is_blocked(self):
        report = DryRunRunner(self.repo_root).plan(mode="APPLY")
        self.assertEqual(RunnerStatus.PRECHECK_BLOCKED.value, report["status"])
        self.assertIn("APPLY_FORBIDDEN_IN_BATCH_02", report["blocking_reasons"])

    def test_runner_production_target_is_blocked(self):
        target = self.valid_target()
        target.update({"environment": "PRODUCTION", "provider": "PRODUCTION_SUPABASE", "allow_network": True, "connect_permission": "EXPLICITLY_GRANTED"})
        report = DryRunRunner(self.repo_root).plan(target=target)
        self.assertEqual(RunnerStatus.PRECHECK_BLOCKED.value, report["status"])
        self.assertTrue(any("PRODUCTION" in reason for reason in report["blocking_reasons"]))

    def test_runner_has_no_apply_method(self):
        self.assertFalse(hasattr(DryRunRunner(self.repo_root), "apply"))

    def test_preflight_has_all_eighteen_checks_and_fails_closed(self):
        report = run_preflight(self.repo_root, load_manifest(self.repo_root))
        self.assertEqual(PREFLIGHT_IDS, [check.check_id for check in report.checks])
        self.assertEqual(CheckStatus.BLOCKED, report.status)
        self.assertEqual(CheckStatus.BLOCKED, report.checks[12].status)
        self.assertTrue(any(check.status == CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB for check in report.checks))

    def test_preflight_rejects_missing_secret_env_reference(self):
        target = self.valid_target()
        report = run_preflight(self.repo_root, load_manifest(self.repo_root), target=target, secret_env_names=set())
        pf14 = report.checks[13]
        self.assertEqual(CheckStatus.BLOCKED, pf14.status)

    def test_preflight_rejects_production_object_collision(self):
        target = self.valid_target()
        target["contains_v333_objects"] = True
        report = run_preflight(self.repo_root, load_manifest(self.repo_root), target=target)
        self.assertEqual(CheckStatus.FAIL, report.checks[5].status)

    def test_expected_snapshot_shape_is_valid(self):
        snapshot = load_expected_snapshot(self.repo_root)
        self.assertEqual([], validate_expected_snapshot_shape(snapshot))

    def test_unknown_schema_catalog_is_pending_not_pass(self):
        report = compare_schema_snapshot(load_expected_snapshot(self.repo_root), None)
        self.assertEqual(CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB, report.status)
        self.assertEqual("UNKNOWN_CATALOG", report.classifications[0]["classification"])

    def test_exact_supplied_catalog_has_empty_diff(self):
        snapshot = load_expected_snapshot(self.repo_root)
        actual = {"objects": copy.deepcopy(snapshot["expected_catalog"])}
        report = compare_schema_snapshot(snapshot, actual)
        self.assertEqual(CheckStatus.PASS, report.status)
        self.assertEqual([], report.classifications)

    def test_schema_diff_classifies_missing_and_extra(self):
        snapshot = load_expected_snapshot(self.repo_root)
        actual = {"objects": {kind: list(values) for kind, values in snapshot["expected_catalog"].items()}}
        actual["objects"]["tables"].pop()
        actual["objects"]["tables"].append("extra.unauthorized_table")
        report = compare_schema_snapshot(snapshot, actual)
        classifications = {item["classification"] for item in report.classifications}
        self.assertEqual(CheckStatus.BLOCKED, report.status)
        self.assertEqual({"MISSING", "EXTRA"}, classifications)

    def test_smoke_catalog_has_twenty_cases(self):
        catalog = load_smoke_catalog(self.repo_root)
        self.assertEqual([], validate_smoke_catalog(catalog))
        runtime = runtime_pending_smoke_report(catalog)
        self.assertEqual(20, runtime["pending"])
        self.assertEqual(0, runtime["actually_executed"])
        self.assertEqual(CheckStatus.NOT_EXECUTED_REQUIRES_DISPOSABLE_DB.value, runtime["status"])

    def test_negative_registry_has_all_twenty_two_cases(self):
        registry = load_negative_registry(self.repo_root)
        self.assertEqual([], validate_negative_registry(registry))
        self.assertEqual(22, len(registry["cases"]))

    def test_negative_contracts_execute_and_all_reject(self):
        result = run_negative_cases(self.repo_root)
        self.assertEqual(CheckStatus.PASS.value, result["status"])
        self.assertEqual(22, result["defined_count"])
        self.assertEqual(22, result["actually_executed"])
        self.assertEqual(22, result["pass_count"])
        self.assertEqual(0, result["fail_count"])
        self.assertEqual(15, result["runtime_pending_count"])

    def test_history_hash_mismatch_is_rejected(self):
        manifest = load_manifest(self.repo_root)
        ok, issues = validate_history_integrity([
            {"migration_id": "migration@20260901.001", "migration_hash": "sha256:" + "0" * 64, "status": "APPLIED"}
        ], manifest)
        self.assertFalse(ok)
        self.assertTrue(any(issue.code == "HISTORY_HASH_MISMATCH" for issue in issues))

    def test_valid_target_is_accepted_as_descriptor(self):
        result = validate_target_descriptor(self.valid_target())
        self.assertTrue(result.ok)
        self.assertTrue(result.connect_allowed)

    def test_target_without_reset_contract_is_blocked(self):
        target = self.valid_target()
        target.pop("reset_and_teardown_contract")
        self.assertFalse(validate_target_descriptor(target).ok)

    def test_available_market_without_payload_is_rejected(self):
        self.assertTrue(validate_market_payload({"market": "spf", "status": "AVAILABLE", "payload": None}).rejected)

    def test_unavailable_market_without_reason_is_rejected(self):
        self.assertTrue(validate_market_payload({"market": "spf", "status": "UNAVAILABLE", "payload": None, "unavailable_reason": ""}).rejected)

    def test_rqspf_requires_handicap(self):
        self.assertTrue(validate_market_payload({"market": "rqspf", "status": "AVAILABLE", "payload": {"home": 1}, "handicap_line": None}).rejected)

    def test_post_kickoff_run_is_rejected(self):
        result = validate_prematch_run({"role": "PRODUCTION", "prediction_cutoff_at": "2026-09-01T18:00:00+08:00", "kickoff_at": "2026-09-01T19:00:00+08:00", "run_at": "2026-09-01T19:01:00+08:00"})
        self.assertEqual("POST_KICKOFF_RUN", result.code)
        self.assertTrue(result.rejected)

    def test_immutable_frozen_input_mutation_is_rejected(self):
        self.assertTrue(validate_immutable_mutation({"entity_type": "Frozen Input", "status": "FROZEN", "immutable": True}, "UPDATE").rejected)

    def test_immutable_frozen_prediction_delete_is_rejected(self):
        self.assertTrue(validate_immutable_mutation({"entity_type": "Frozen Prediction", "status": "FROZEN", "immutable": True}, "DELETE").rejected)

    def test_review_cross_match_is_rejected(self):
        self.assertTrue(validate_review_scope({"result_match_id": "a", "frozen_prediction_match_id": "b"}).rejected)

    def test_tier_a_hash_mismatch_is_rejected(self):
        self.assertTrue(validate_tier_a_pair({"production_role": "PRODUCTION", "shadow_role": "SHADOW", "production_frozen_input_hash": "a", "shadow_frozen_input_hash": "b"}).rejected)

    def test_experiment_cannot_be_tier_a(self):
        self.assertTrue(validate_tier_a_pair({"production_role": "PRODUCTION", "shadow_role": "SHADOW", "production_frozen_input_hash": "a", "shadow_frozen_input_hash": "a", "experiment_member": True}).rejected)

    def test_shadow_public_projection_is_rejected(self):
        self.assertTrue(validate_public_projection({"role": "SHADOW", "status": "PUBLISHED"}).rejected)

    def test_two_active_production_revisions_are_rejected(self):
        rows = [{"role": "PRODUCTION", "status": "PRODUCTION", "is_canonical_active": True}] * 2
        self.assertTrue(validate_production_uniqueness(rows).rejected)

    def test_unsafe_security_definer_is_rejected(self):
        self.assertTrue(validate_function_security({"security": "DEFINER", "search_path": ["public"], "actor_check": False, "execute_grants_reviewed": False}).rejected)

    def test_anon_internal_write_is_rejected(self):
        self.assertTrue(validate_role_write("anon", "internal", "INSERT").rejected)
        self.assertTrue(validate_role_write("authenticated", "internal", "UPDATE").rejected)

    def test_canonical_latest_uses_business_time(self):
        self.assertTrue(validate_canonical_latest({"business_times": ["2026-09-01T10:00:00+08:00"], "canonical_latest_update_at": "2026-09-01T11:00:00+08:00", "page_build_at": "2026-09-01T11:00:00+08:00"}).rejected)

    def test_unknown_zero_coercion_is_rejected(self):
        self.assertTrue(validate_unknown_not_coerced({"state": "UNKNOWN", "coerced_value": 0}).rejected)

    def test_runner_state_machine_is_fail_closed(self):
        self.assertTrue(can_transition(RunnerStatus.PLANNED, RunnerStatus.READY_FOR_DISPOSABLE))
        self.assertTrue(can_transition(RunnerStatus.APPLYING, RunnerStatus.FAILED))
        self.assertFalse(can_transition(RunnerStatus.ACCEPTED, RunnerStatus.APPLYING))
        self.assertFalse(can_transition(RunnerStatus.PRECHECK_BLOCKED, RunnerStatus.APPLYING))

    def test_secret_scan_is_clean_without_exposing_values(self):
        result = secret_scan(self.repo_root)
        self.assertEqual(CheckStatus.PASS.value, result["status"])
        self.assertFalse(result["values_logged"])
        self.assertEqual(0, result["hit_count"])

    def test_git_diff_check_has_a_real_result(self):
        result = run_git_diff_check(self.repo_root)
        self.assertIn(result["status"], {CheckStatus.PASS.value, CheckStatus.FAIL.value})


if __name__ == "__main__":
    unittest.main()
