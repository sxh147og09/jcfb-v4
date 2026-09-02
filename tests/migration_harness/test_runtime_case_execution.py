from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.migration_harness.common import sha256_json
from tools.migration_harness.runtime_case_handlers import (
    Attempt,
    CaseContext,
    LATEST_BUSINESS_TIMESTAMP,
    RuntimeCaseHandlerRunner,
    match_expected_rejection,
)
from tools.migration_harness.runtime_executor import RuntimeExecutor, render_runtime_report_markdown
from tools.migration_harness.runtime_tests import (
    _normalize_adapter_result,
    load_runtime_case_bindings,
    run_runtime_cases,
    validate_runtime_case_wiring,
)


class _Diag:
    def __init__(self, sqlstate: str, constraint_name: str | None = None):
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name


class _DbError(Exception):
    def __init__(self, message: str, sqlstate: str, constraint_name: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = _Diag(sqlstate, constraint_name)


class _Cursor:
    def __init__(self, connection: "_Connection"):
        self.connection = connection
        self.description = []
        self._rows = []

    def execute(self, sql, params=None):
        values = None if params is None else tuple(params)
        self.connection.executed.append((sql, values))
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
                ("anon", False, False, False),
                ("authenticated", False, False, False),
                ("service_role", False, True, False),
                ("backend", True, True, True),
                ("executor", True, True, True),
                ("auditor", True, True, True),
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

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


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
        self.executed.append((sql, values))

    def attempt(self, sql, params=None, *, role, flush=True):
        self.execute(sql, params)
        return Attempt(True, None, role)

    def flush_constraints(self):
        return None

    def one(self, sql, params=None):
        self.execute(sql, params)
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
                {"result_revision": 2, "supersedes_result_id": "fixture"},
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


if __name__ == "__main__":
    unittest.main()
