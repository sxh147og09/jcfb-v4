from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.migration_harness.common import sha256_json
from tools.migration_harness.runtime_case_handlers import (
    Attempt,
    CaseContext,
    LATEST_BUSINESS_TIMESTAMP,
    RuntimeCaseHandlerRunner,
    _hash,
    _id,
    _official_market_states,
    match_expected_rejection,
)
from tools.migration_harness.runtime_executor import (
    RuntimeExecutor,
    RuntimeEvidenceError,
    capture_git_metadata,
    load_latest_runtime_report,
    render_runtime_report_markdown,
    review_runtime_evidence,
    select_latest_runtime_report,
    write_runtime_report,
)
from tools.migration_harness.runtime_tests import (
    _normalize_adapter_result,
    load_runtime_case_bindings,
    run_runtime_cases,
    validate_runtime_case_wiring,
)


class _Diag:
    def __init__(self, sqlstate: str, constraint_name: str | None = None, message_primary: str | None = None):
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name
        self.message_primary = message_primary


class _DbError(Exception):
    def __init__(self, message: str, sqlstate: str, constraint_name: str | None = None, message_primary: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = _Diag(sqlstate, constraint_name, message_primary)


class _DiagOnlyError(Exception):
    def __init__(self, sqlstate: str, message_primary: str, constraint_name: str | None = None):
        super().__init__("")
        self.diag = _Diag(sqlstate, constraint_name, message_primary)


class _Cursor:
    def __init__(self, connection: "_Connection"):
        self.connection = connection
        self.description = []
        self._rows = []

    def execute(self, sql, params=None):
        values = None if params is None else tuple(params)
        self.connection.executed.append((sql, values))
        if self.connection.fail_sql and self.connection.fail_sql in sql:
            raise _DbError("", "23514", message_primary="fixture failure")
        if "DO $$ DECLARE role_name" in sql:
            for role in ("backend", "executor", "auditor"):
                self.connection.roles.setdefault(
                    role,
                    {"rolinherit": True, "rolbypassrls": True, "service_role_member": False},
                )
        elif "GRANT service_role TO" in sql:
            for role in ("backend", "executor", "auditor"):
                if role in self.connection.roles:
                    self.connection.roles[role]["service_role_member"] = True
        elif "REVOKE service_role FROM" in sql:
            for role in ("backend", "executor", "auditor"):
                if role in self.connection.roles:
                    self.connection.roles[role]["service_role_member"] = False
        elif "DROP ROLE IF EXISTS" in sql:
            match = re.search(r'DROP ROLE IF EXISTS "([a-z_]+)"', sql, flags=re.IGNORECASE)
            if match:
                self.connection.roles.pop(match.group(1), None)
        self.description = []
        self._rows = []
        if "FROM pg_catalog.pg_roles" in sql:
            self.description = [
                ("rolname",),
                ("rolinherit",),
                ("rolbypassrls",),
                ("service_role_member",),
            ]
            self._rows = [
                (
                    role,
                    values["rolinherit"],
                    values["rolbypassrls"],
                    values["service_role_member"],
                )
                for role, values in sorted(self.connection.roles.items())
            ]
        elif "to_regprocedure" in sql:
            self.description = [("object_name",)]
            self._rows = [(None,)]

    def fetchall(self):
        return list(self._rows)

    def close(self):
        return None


class _Connection:
    def __init__(self):
        self.executed = []
        self.commit_count = 0
        self.rollback_count = 0
        self.fail_sql = None
        self.roles = {
            "anon": {"rolinherit": False, "rolbypassrls": False, "service_role_member": False},
            "authenticated": {"rolinherit": False, "rolbypassrls": False, "service_role_member": False},
            "service_role": {"rolinherit": False, "rolbypassrls": True, "service_role_member": False},
            "backend": {"rolinherit": True, "rolbypassrls": True, "service_role_member": True},
            "executor": {"rolinherit": True, "rolbypassrls": True, "service_role_member": True},
            "auditor": {"rolinherit": True, "rolbypassrls": True, "service_role_member": True},
        }

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class _CleanupFailureConnection(_Connection):
    def __init__(self, fail_on_rollback: int):
        super().__init__()
        self.fail_on_rollback = fail_on_rollback

    def rollback(self):
        self.rollback_count += 1
        if self.rollback_count >= self.fail_on_rollback:
            raise RuntimeError("simulated cleanup failure")


class _HandlerProbeContext:
    """Exercise handler SQL construction without opening a database connection."""

    def __init__(self):
        self.executed = []
        self.case_id = "SMOKE-01"

    def set_role(self, role):
        return None

    def execute(self, sql, params=None):
        values = () if params is None else tuple(params)
        placeholders = len(re.findall(r"(?<!%)%(?!%)s", sql))
        if placeholders != len(values):
            raise AssertionError(f"{placeholders} placeholders != {len(values)} params")
        insert_match = re.search(
            r"\bINSERT\s+INTO\s+[A-Za-z_][\w.]*\s*\((?P<columns>[^()]*)\)\s+VALUES\s*\((?P<values>.*)\)\s*$",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if insert_match:
            def split_items(segment):
                items = []
                start = 0
                depth = 0
                quote = None
                index = 0
                while index < len(segment):
                    char = segment[index]
                    if quote:
                        if char == quote and index + 1 < len(segment) and segment[index + 1] == quote:
                            index += 2
                            continue
                        if char == quote:
                            quote = None
                    elif char in {"'", '"'}:
                        quote = char
                    elif char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                    elif char == "," and depth == 0:
                        items.append(segment[start:index].strip())
                        start = index + 1
                    index += 1
                items.append(segment[start:].strip())
                return items

            columns = split_items(insert_match.group("columns"))
            values_sql = split_items(insert_match.group("values"))
            if len(columns) != len(values_sql):
                raise AssertionError(f"{len(columns)} INSERT columns != {len(values_sql)} VALUES expressions")
        self.executed.append((sql, values))

    def attempt(self, sql, params=None, *, role, flush=True):
        self.execute(sql, params)
        return Attempt(True, None, role)

    def flush_constraints(self):
        return None

    def one(self, sql, params=None):
        self.execute(sql, params)
        if "snapshot_row" in sql:
            return {"snapshot_row": True, "unavailable_without_payload": True}
        if "before_state" in sql:
            return {
                "actor": "fixture-actor",
                "actor_role": "auditor",
                "action": "INSERT",
                "entity_type": "core.matches",
                "entity_id": "fixture-entity",
                "before_state": {},
                "after_state": {"fixture": True},
                "happened_at": "2026-01-01T09:00:00+00:00",
                "entry_hash": "sha256:" + "a" * 64,
            }
        if "entity_type = 'evaluation.official_results'" in sql:
            return {"count": 2}
        if "gate_reason" in sql:
            return {"gate_reason": None, "immutable": True, "status": "FROZEN"}
        if "canonical_latest_update_at" in sql:
            return {"canonical_latest_update_at": LATEST_BUSINESS_TIMESTAMP}
        if "projection_id" in sql:
            return {"projection_id": "fixture"}
        return {"count": 1}

    def rows(self, sql, params=None):
        self.execute(sql, params)
        if "result_revision" in sql:
            return [
                {"result_revision": 1, "supersedes_result_id": None},
                {"result_revision": 2, "supersedes_result_id": _id(self.case_id, "result:first")},
            ]
        return []


class _BlockedAdapter:
    role_simulation = None

    def prepare(self):
        return {"status": "BLOCKED", "reason": "unit-test environment"}

    def run_case(self, binding):
        raise AssertionError("blocked preparation must prevent case dispatch")


class RuntimeCaseExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]

    def test_every_registered_case_has_a_concrete_handler(self):
        wiring = validate_runtime_case_wiring(self.repo_root)
        self.assertEqual("PASS", wiring["status"])
        self.assertEqual(20, wiring["smoke_count"])
        self.assertEqual(15, wiring["enforcement_count"])
        self.assertEqual(20, wiring["smoke_executable_handler_count"])
        self.assertEqual(15, wiring["enforcement_executable_handler_count"])
        bindings = load_runtime_case_bindings(self.repo_root)
        for binding in [*bindings["smoke"], *bindings["enforcement"]]:
            self.assertTrue(callable(getattr(RuntimeCaseHandlerRunner, binding.hook_name, None)), binding.case_id)

    def test_all_handlers_build_parameter_safe_sql_without_database(self):
        context = _HandlerProbeContext()
        runner = object.__new__(RuntimeCaseHandlerRunner)
        bindings = load_runtime_case_bindings(self.repo_root)
        all_bindings = [*bindings["smoke"], *bindings["enforcement"]]
        self.assertEqual(35, len(all_bindings))
        for binding in all_bindings:
            with self.subTest(case_id=binding.case_id, handler=binding.hook_name):
                context.case_id = binding.case_id
                getattr(runner, binding.hook_name)(context)

    def test_expected_rejection_requires_sqlstate_and_stable_marker(self):
        expected = {
            "type": "trigger",
            "sqlstates": ["23514"],
            "message_tokens": ["OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD"],
        }
        self.assertTrue(
            match_expected_rejection(
                _DbError("OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD for spf", "23514"),
                expected,
            )
        )
        self.assertFalse(match_expected_rejection(_DbError("unrelated", "23514"), expected))
        self.assertFalse(
            match_expected_rejection(
                _DbError("OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD", "23505"),
                expected,
            )
        )
        self.assertFalse(
            match_expected_rejection(
                _DbError("OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD", "23514"),
                {"message_tokens": ["OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD"]},
            )
        )
        self.assertTrue(
            match_expected_rejection(
                _DbError("duplicate", "23505", "active_production_model_uq"),
                {"sqlstates": ["23505"], "constraints": ["active_production_model_uq"]},
            )
        )

    def test_expected_rejection_reads_psycopg_diagnostic_message_fields(self):
        expected = {
            "type": "trigger",
            "sqlstates": ["23514"],
            "message_tokens": ["OFFICIAL_RQSPF_HANDICAP_REQUIRED"],
        }
        error = _DbError("", "23514", message_primary="OFFICIAL_RQSPF_HANDICAP_REQUIRED")
        self.assertTrue(match_expected_rejection(error, expected))

    def test_outer_normalizer_preserves_diag_only_sqlstate(self):
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["enforcement"] if item.case_id == "NEG-08")
        result = _normalize_adapter_result(
            binding,
            {
                "status": "PASS",
                "actual_outcome": "REJECT",
                "error": _DiagOnlyError("23514", "OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD"),
                "verification": {"no_row": True},
            },
        )
        self.assertEqual("PASS_EXPECTED_REJECT", result["status"])
        self.assertEqual("23514", result["error_sqlstate"])

    def test_unique_constraint_rejection_is_classified_from_driver_diagnostics(self):
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["smoke"] if item.case_id == "SMOKE-02")
        runner = object.__new__(RuntimeCaseHandlerRunner)
        result = runner._evaluate(
            binding,
            {
                "actual_outcome": "REJECT",
                "error": _DbError("", "23505", "matches_data_date_official_match_no_key"),
                "verification": {"original_only": True},
            },
            "REJECT",
        )
        self.assertEqual("PASS_EXPECTED_REJECT", result["status"])
        self.assertTrue(result["expected_rejection_match"])
        self.assertEqual("MATCH", result["expected_rejection_match_reason"])
        self.assertEqual("unique_violation", result["error_class"])

    def test_legacy_generic_reject_is_blocked_and_matched_reject_is_explicit_pass(self):
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["enforcement"] if item.case_id == "NEG-08")
        generic = _normalize_adapter_result(
            binding,
            {
                "status": "PASS",
                "actual_outcome": "REJECT",
                "error": _DbError("unrelated database error", "23514"),
                "verification": {"no_row": True},
            },
        )
        self.assertEqual("BLOCKED_ENVIRONMENT", generic["status"])
        matched = _normalize_adapter_result(
            binding,
            {
                "status": "PASS",
                "actual_outcome": "REJECT",
                "error": _DbError("OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD", "23514"),
                "verification": {"no_row": True},
            },
        )
        self.assertEqual("PASS_EXPECTED_REJECT", matched["status"])
        redacted_result = _normalize_adapter_result(
            binding,
            {
                "status": "PASS",
                "actual_outcome": "REJECT",
                "error": _DbError("driver-detail-should-not-ship", "23514"),
                "verification": {"no_row": True},
            },
        )
        self.assertNotIn("driver-detail-should-not-ship", json.dumps(redacted_result).lower())
        self.assertNotIn("error", redacted_result)

    def test_redacted_governed_rejection_survives_outer_normalization(self):
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["enforcement"] if item.case_id == "NEG-08")
        runner = object.__new__(RuntimeCaseHandlerRunner)
        evaluated = runner._evaluate(
            binding,
            {
                "actual_outcome": "REJECT",
                "error": _DbError("OFFICIAL_AVAILABLE_MARKET_REQUIRES_PAYLOAD", "23514"),
                "verification": {"no_row": True},
            },
            "REJECT",
        )
        self.assertNotIn("error", evaluated)
        normalized = _normalize_adapter_result(binding, evaluated)
        self.assertEqual("PASS_EXPECTED_REJECT", normalized["status"])
        self.assertTrue(normalized["expected_rejection_match"])
        self.assertEqual("23514", normalized["error_sqlstate"])

    def test_redacted_rejection_without_exact_governed_evidence_does_not_pass(self):
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["enforcement"] if item.case_id == "NEG-08")
        result = _normalize_adapter_result(
            binding,
            {
                "status": "PASS_EXPECTED_REJECT",
                "actual_outcome": "REJECT",
                "verification": {"no_row": True},
                "expected_mechanism": dict(binding.execution)["expected_mechanism"],
                "expected_rejection_match": True,
                "expected_rejection_match_reason": "MATCH",
                "error_sqlstate": "23514",
                "result_origin": "INJECTED_ADAPTER",
            },
        )
        self.assertEqual("FAIL_UNEXPECTED_REJECT", result["status"])

    def test_case_context_uses_savepoints_and_rolls_back_complete_case(self):
        connection = _Connection()
        context = CaseContext(connection, "SMOKE-TEST", "unit-test-actor")
        context.begin()
        attempt = context.attempt("SELECT 1", role="executor")
        context.close()
        self.assertTrue(attempt.accepted)
        sql = [item[0] for item in connection.executed]
        self.assertIn("BEGIN", sql)
        self.assertTrue(any(statement.startswith("SAVEPOINT v4_case_action_") for statement in sql))
        self.assertTrue(any(statement.startswith("RELEASE SAVEPOINT") for statement in sql))
        self.assertGreaterEqual(connection.rollback_count, 2)
        self.assertEqual(0, connection.commit_count)

    def test_case_context_restores_failed_savepoint_for_next_action(self):
        connection = _Connection()
        context = CaseContext(connection, "SMOKE-TEST", "unit-test-actor")
        context.begin()
        connection.fail_sql = "SELECT fixture_failure"
        failed = context.attempt("SELECT fixture_failure", role="executor")
        connection.fail_sql = None
        recovered = context.attempt("SELECT 1", role="executor")
        context.close()
        self.assertFalse(failed.accepted)
        self.assertEqual("23514", failed.error.sqlstate)
        self.assertTrue(recovered.accepted)
        sql = [item[0] for item in connection.executed]
        self.assertTrue(any(statement.startswith("ROLLBACK TO SAVEPOINT") for statement in sql))
        self.assertGreaterEqual(connection.rollback_count, 2)

    def test_cleanup_failure_quarantines_connection_before_next_case(self):
        connection = _CleanupFailureConnection(fail_on_rollback=3)
        runner = RuntimeCaseHandlerRunner(connection, actor="unit-test-actor")
        binding = next(item for item in load_runtime_case_bindings(self.repo_root)["smoke"] if item.case_id == "SMOKE-17")
        first = runner.run_case(binding)
        second = runner.run_case(binding)
        self.assertEqual("BLOCKED_ENVIRONMENT", first["status"])
        self.assertEqual("CLEANUP", first["phase"])
        self.assertEqual("FAIL", first["cleanup_phase"])
        self.assertEqual("BLOCKED_ENVIRONMENT", second["status"])
        self.assertFalse(second["actually_executed"])
        self.assertTrue(second["contaminated_by_previous_case"])
        self.assertEqual("CLEANUP", second["execution_phase"])

    def test_accept_postconditions_handle_native_driver_values(self):
        context = _HandlerProbeContext()
        runner = object.__new__(RuntimeCaseHandlerRunner)
        for case_id, hook_name in (
            ("SMOKE-03", "smoke_03_official_market_unavailable"),
            ("SMOKE-09", "smoke_09_official_result_correction"),
            ("SMOKE-19", "smoke_19_lifecycle_audit_coverage"),
        ):
            with self.subTest(case_id=case_id):
                context.case_id = case_id
                result = getattr(runner, hook_name)(context)
                self.assertTrue(all(result["verification"].values()))

    def test_all_enforcement_handlers_reach_action_and_assert_in_probe_context(self):
        context = _HandlerProbeContext()
        runner = object.__new__(RuntimeCaseHandlerRunner)
        bindings = load_runtime_case_bindings(self.repo_root)["enforcement"]
        self.assertEqual(15, len(bindings))
        for binding in bindings:
            with self.subTest(case_id=binding.case_id):
                context.case_id = binding.case_id
                result = getattr(runner, binding.hook_name)(context)
                self.assertEqual("REJECT", result["actual_outcome"])
                self.assertTrue(result["verification"])
                self.assertTrue(all(isinstance(value, bool) for value in result["verification"].values()))

    def test_official_market_fixture_uses_authoritative_unavailable_semantics(self):
        availability_json, reasons_json, payloads = _official_market_states(unavailable="rqspf")
        availability = json.loads(availability_json)
        reasons = json.loads(reasons_json)
        self.assertEqual("UNAVAILABLE", availability["rqspf"]["status"])
        self.assertEqual("OFFICIAL_MARKET_NOT_ON_SALE", availability["rqspf"]["reason"])
        self.assertIsNone(payloads["rqspf"])
        self.assertEqual("OFFICIAL_MARKET_NOT_ON_SALE", reasons["rqspf"])
        for market in ("spf", "total_goals", "exact_score", "half_full"):
            self.assertEqual("AVAILABLE", availability[market]["status"])
            self.assertEqual("NOT_APPLICABLE", availability[market]["reason"])
            self.assertEqual("NOT_APPLICABLE", reasons[market])

    def test_tier_a_mismatch_fixture_reaches_pair_action_after_valid_lineage_setup(self):
        context = _HandlerProbeContext()
        context.case_id = "SMOKE-11"
        runner = object.__new__(RuntimeCaseHandlerRunner)
        result = runner.smoke_11_tier_a_pair_different_frozen_input_hashes(context)
        executed_parameters = [value for _, params in context.executed for value in (params or ())]
        self.assertTrue(any("evaluation.tier_a_samples" in sql for sql, _ in context.executed))
        self.assertIn(_hash("SMOKE-11:declared-different-frozen-input"), executed_parameters)
        self.assertNotIn(_id("SMOKE-11", "prediction:shadow-mismatch"), executed_parameters)
        self.assertEqual("REJECT", result["actual_outcome"])

    def test_disposable_role_simulation_is_explicit_and_no_supabase_auth_is_faked(self):
        connection = _Connection()
        runner = RuntimeCaseHandlerRunner(connection, actor="unit-test-actor")
        preparation = runner.prepare()
        self.assertEqual("PASS", preparation["status"])
        self.assertEqual("DISPOSABLE_ROLE_SIMULATION", preparation["role_simulation"]["mode"])
        self.assertFalse(preparation["role_simulation"]["supabase_auth_runtime"])
        self.assertTrue(any("CREATE ROLE" in sql for sql, _ in connection.executed))
        self.assertTrue(any("GRANT service_role" in sql for sql, _ in connection.executed))
        self.assertEqual(1, connection.commit_count)

    def test_disposable_role_simulation_teardown_drops_only_runner_created_roles(self):
        connection = _Connection()
        for role in ("backend", "executor", "auditor"):
            connection.roles.pop(role)
        runner = RuntimeCaseHandlerRunner(connection, actor="unit-test-actor")
        preparation = runner.prepare()
        self.assertEqual(["backend", "executor", "auditor"], preparation["role_simulation"]["created_roles"])
        self.assertEqual(
            ["backend", "executor", "auditor"],
            preparation["role_simulation"]["granted_service_role_memberships"],
        )
        cleanup = runner.teardown()
        self.assertEqual("PASS", cleanup["status"])
        self.assertEqual({"anon", "authenticated", "service_role"}, set(connection.roles))
        self.assertTrue(any("REVOKE service_role FROM" in sql for sql, _ in connection.executed))
        self.assertTrue(any("DROP ROLE IF EXISTS" in sql for sql, _ in connection.executed))
        self.assertEqual(cleanup, runner.teardown())

    def test_blocked_preparation_produces_closed_result_vocabulary(self):
        report = run_runtime_cases(self.repo_root, _BlockedAdapter())
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual(35, report["defined_count"])
        self.assertEqual(35, report["blocked_environment"])
        self.assertEqual(0, report["pending"])
        self.assertEqual(35, len(report["results"]))
        self.assertTrue(all(item["status"] == "BLOCKED_ENVIRONMENT" for item in report["results"]))

    def test_history_chain_is_validated_and_tampering_blocks_prefix(self):
        from tools.migration_harness.canonical_hash import load_candidate_manifest

        candidates = load_candidate_manifest(self.repo_root)["candidates"]
        entry = candidates[0]
        chain_hash = sha256_json(
            {
                "migration_id": entry["migration_id"],
                "migration_hash": entry["canonical_migration_hash"],
                "prev_migration_hash": None,
            }
        )
        row = {
            "migration_id": entry["migration_id"],
            "sequence": entry["sequence"],
            "name": entry["name"],
            "migration_version": entry["migration_version"],
            "schema_contract_version": entry["schema_contract_version"],
            "migration_hash": entry["canonical_migration_hash"],
            "status": "APPLIED",
            "success": True,
            "partial_state": False,
            "prev_migration_hash": None,
            "chain_hash": chain_hash,
        }
        prefix, issue = RuntimeExecutor._validated_history_prefix([row], candidates)
        self.assertEqual(1, prefix)
        self.assertIsNone(issue)
        row["chain_hash"] = "sha256:" + "0" * 64
        prefix, issue = RuntimeExecutor._validated_history_prefix([row], candidates)
        self.assertEqual(0, prefix)
        self.assertIn("chain_hash", issue)

    def test_runtime_report_contains_case_table_and_advisor_boundary(self):
        report = {
            "status": "RUNTIME_VALIDATION_BLOCKED",
            "contract_version": "v4-runtime-executor@1.0.0",
            "mode": "PLAN_ONLY",
            "target": {"target_id": "jcfb-v4-disposable-runtime", "environment": "DISPOSABLE_LOCAL"},
            "hash_verification": {"status": "PASS", "matched_count": 9, "candidate_count": 9},
            "execution_boundary": {"connector_invoked": False, "database_connected": False, "sql_executed": False},
            "runtime_case_wiring": {"smoke_count": 20, "enforcement_count": 15},
            "runtime_validation": {
                "status": "BLOCKED",
                "actually_executed": 0,
                "expected_reject_matching": "FAIL",
                "results": [
                    {
                        "case_id": "NEG-08",
                        "kind": "ENFORCEMENT",
                        "status": "BLOCKED_ENVIRONMENT",
                        "actual_outcome": "-",
                        "hook_name": "enforcement_08_available_market_missing_payload",
                        "expected_mechanism": {"type": "trigger"},
                    }
                ],
            },
            "schema_checks": {"status": "BLOCKED_ENVIRONMENT", "advisor_status": "NOT_RUN_IN_DISPOSABLE"},
            "staging_readiness": {"status": "BLOCKED_RUNTIME_VALIDATION", "checks": {}},
            "migration_apply_path": {"status": "NOT_RUN", "history_recording": "NOT_RUN"},
        }
        rendered = render_runtime_report_markdown(report)
        self.assertIn("## Runtime cases", rendered)
        self.assertIn("NEG-08", rendered)
        self.assertIn("NOT_RUN_IN_DISPOSABLE", rendered)
        self.assertNotIn("password", rendered.lower())

    def test_runtime_report_writer_persists_unique_runs_and_latest_selection(self):
        report = {
            "status": "RUNTIME_VALIDATION_FAILED",
            "contract_version": "v4-runtime-executor@1.0.0",
            "mode": "APPLY",
            "target": {"target_id": "jcfb-v4-disposable-runtime", "environment": "DISPOSABLE_LOCAL"},
            "hash_verification": {"status": "PASS", "matched_count": 9, "candidate_count": 9},
            "runtime_case_wiring": {
                "smoke_executable_handler_count": 20,
                "enforcement_executable_handler_count": 15,
                "smoke_count": 20,
                "enforcement_count": 15,
            },
            "runtime_validation": {
                "status": "FAIL",
                "passed_smoke": 7,
                "passed_enforcement": 0,
                "smoke_count": 20,
                "enforcement_count": 15,
                "results": [],
            },
            "staging_readiness": {"status": "BLOCKED_RUNTIME_VALIDATION"},
        }
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            report_dir = Path(directory) / "prebatch04"
            git_metadata = lambda head: {
                "git_head": head,
                "git_branch": "main",
                "working_tree_clean": True,
                "repo_root": self.repo_root.resolve().as_posix(),
            }
            with patch(
                "tools.migration_harness.runtime_executor.capture_git_metadata",
                side_effect=[git_metadata("a" * 40), git_metadata("b" * 40)],
            ):
                first = write_runtime_report(
                    report,
                    self.repo_root,
                    report_dir=report_dir,
                    started_at="2026-09-03T10:00:00+00:00",
                    finished_at="2026-09-03T10:00:01+00:00",
                    git_head="a" * 40,
                )
                second = write_runtime_report(
                    report,
                    self.repo_root,
                    report_dir=report_dir,
                    started_at="2026-09-03T10:01:00+00:00",
                    finished_at="2026-09-03T10:01:01+00:00",
                    git_head="b" * 40,
                )
            self.assertNotEqual(first["json"], second["json"])
            self.assertNotEqual(first["run_id"], second["run_id"])
            selected = select_latest_runtime_report(report_dir)
            self.assertEqual(Path(second["json"]).resolve(), selected)
            loaded = load_latest_runtime_report(report_dir)
            self.assertEqual(second["run_id"], loaded["run_id"])
            self.assertEqual("b" * 40, loaded["git_head"])
            self.assertEqual(7, loaded["smoke_passed"])
            self.assertEqual(0, loaded["enforcement_passed"])
            self.assertIn("PRE_BATCH_04_SMOKE_PASSED=7/20", loaded["runtime_summary_lines"])
            self.assertIn("PRE_BATCH_04_ENFORCEMENT_PASSED=0/15", loaded["runtime_summary_lines"])
            pointer = json.loads(Path(second["latest"]).read_text(encoding="utf-8"))
            self.assertEqual(second["run_id"], pointer["run_id"])
            self.assertEqual(second["json"], str(report_dir / pointer["json"]).replace("\\", "/"))
            self.assertEqual(pointer["json"], pointer["report_json"])
            self.assertEqual(pointer["markdown"], pointer["report_markdown"])
            self.assertEqual("RUNTIME_VALIDATION_FAILED", pointer["runtime_status"])
            markdown = Path(second["markdown"]).read_text(encoding="utf-8")
            for field in ("run_id", "started_at", "finished_at", "git_head", "smoke_passed", "enforcement_passed"):
                self.assertIn(f"- {field}: ", markdown)
            self.assertIn("PRE_BATCH_04_SMOKE_PASSED=7/20", markdown)
            self.assertIn("PRE_BATCH_04_ENFORCEMENT_PASSED=0/15", markdown)

    def test_valid_git_metadata_is_populated_from_the_actual_repository(self):
        metadata = capture_git_metadata(self.repo_root)
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(completed.stdout.strip().lower(), metadata["git_head"])
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40,64}", metadata["git_head"]))
        self.assertTrue(metadata["git_branch"])
        self.assertEqual(self.repo_root.resolve().as_posix(), metadata["repo_root"])
        self.assertIsInstance(metadata["working_tree_clean"], bool)

    def test_git_unavailable_fails_closed_before_report_creation(self):
        report = {"status": "RUNTIME_VALIDATION_PASS", "runtime_validation": {"passed_smoke": 20, "passed_enforcement": 15}}
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            report_dir = Path(directory) / "prebatch04"
            with patch("tools.migration_harness.runtime_executor.shutil.which", return_value=None):
                with self.assertRaises(RuntimeEvidenceError) as context:
                    write_runtime_report(report, self.repo_root, report_dir=report_dir)
            self.assertEqual("GIT_EXECUTABLE_NOT_FOUND", context.exception.code)
            self.assertFalse(report_dir.exists())

    def test_report_json_markdown_and_latest_persist_one_git_head(self):
        report = {
            "status": "RUNTIME_VALIDATION_PASS",
            "runtime_validation": {
                "status": "PASS",
                "passed_smoke": 20,
                "passed_enforcement": 15,
                "smoke_count": 20,
                "enforcement_count": 15,
            },
            "staging_readiness": {"status": "READY_FOR_PRODUCTION_REVIEW"},
        }
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            root = Path(directory)
            report_dir = root / "prebatch04"
            first = write_runtime_report(report, self.repo_root, report_dir=report_dir)
            run_json = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
            pointer = json.loads(Path(first["latest"]).read_text(encoding="utf-8"))
            markdown = Path(first["markdown"]).read_text(encoding="utf-8")
            self.assertEqual(run_json["git_head"], pointer["git_head"])
            self.assertIn(f"- git_head: `{run_json['git_head']}`", markdown)
            self.assertEqual("RUNTIME_VALIDATION_PASS", pointer["runtime_status"])
            self.assertEqual(run_json["status"], pointer["runtime_status"])
            self.assertEqual(first["json"], str(report_dir / pointer["report_json"]).replace("\\", "/"))
            self.assertEqual(first["markdown"], str(report_dir / pointer["report_markdown"]).replace("\\", "/"))
            self.assertEqual("PASS", review_runtime_evidence(self.repo_root, report_dir=report_dir)["status"])

    def test_dirty_working_tree_is_captured_accurately(self):
        clean = capture_git_metadata(self.repo_root)
        self.assertIsInstance(clean["working_tree_clean"], bool)
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            root = Path(directory)
            source = root / "tracked.txt"
            source.write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "JCFB Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "jcfb-test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "fixture"], check=True)
            self.assertTrue(capture_git_metadata(root)["working_tree_clean"])
            (root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            self.assertFalse(capture_git_metadata(root)["working_tree_clean"])

    def test_two_successive_runs_keep_their_own_run_id_and_git_head(self):
        report = {
            "status": "RUNTIME_VALIDATION_PASS",
            "runtime_validation": {"status": "PASS", "passed_smoke": 20, "passed_enforcement": 15},
            "staging_readiness": {"status": "READY_FOR_PRODUCTION_REVIEW"},
        }
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            root = Path(directory)
            tracked = root / "tracked.txt"
            tracked.write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            for key, value in (("user.name", "JCFB Test"), ("user.email", "jcfb-test@example.invalid")):
                subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "one"], check=True)
            report_dir = root / "prebatch04"
            first = write_runtime_report(report, root, report_dir=report_dir)
            first_json = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
            tracked.write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "two"], check=True)
            second = write_runtime_report(report, root, report_dir=report_dir)
            second_json = json.loads(Path(second["json"]).read_text(encoding="utf-8"))
            self.assertNotEqual(first_json["run_id"], second_json["run_id"])
            self.assertNotEqual(first_json["git_head"], second_json["git_head"])
            self.assertEqual(second_json["git_head"], json.loads(Path(second["latest"]).read_text(encoding="utf-8"))["git_head"])

    def test_runtime_review_blocks_inconsistent_markdown_git_head(self):
        report = {
            "status": "RUNTIME_VALIDATION_PASS",
            "runtime_validation": {"status": "PASS", "passed_smoke": 20, "passed_enforcement": 15},
            "staging_readiness": {"status": "READY_FOR_PRODUCTION_REVIEW"},
        }
        with tempfile.TemporaryDirectory(dir=str(self.repo_root)) as directory:
            root = Path(directory)
            source = root / "tracked.txt"
            source.write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            for key, value in (("user.name", "JCFB Test"), ("user.email", "jcfb-test@example.invalid")):
                subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "fixture"], check=True)
            report_dir = root / "prebatch04"
            result = write_runtime_report(report, root, report_dir=report_dir)
            markdown_path = Path(result["markdown"])
            markdown_path.write_text(
                markdown_path.read_text(encoding="utf-8").replace(report["git_head"], "0" * 40),
                encoding="utf-8",
            )
            review = review_runtime_evidence(root, report_dir=report_dir)
            self.assertEqual("BLOCKED", review["status"])
            self.assertIn("BLOCKED_RUNTIME_EVIDENCE_GIT_HEAD_MISMATCH", review["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
