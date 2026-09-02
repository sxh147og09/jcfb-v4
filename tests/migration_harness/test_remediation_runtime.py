from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.migration_harness.canonical_hash import (
    CanonicalHashError,
    canonical_hash_for_entry,
    canonicalize_sql_text,
    generate_candidate_hashes,
    verify_candidate_hashes,
    write_candidate_hashes,
)
from tools.migration_harness.connection import ConnectionSettings, PostgresConnectionAdapter
from tools.migration_harness.models import ExecutionMode
from tools.migration_harness.runtime_executor import RuntimeExecutor, default_disposable_target
from tools.migration_harness.runtime_tests import validate_runtime_case_wiring


class _FailingAdapter:
    def __init__(self):
        self.connect_calls = 0

    def status(self):
        return {"status": "READY", "driver": "test", "connection_opened": False}

    def connect(self, settings):
        self.connect_calls += 1
        raise AssertionError("plan-only code attempted a database connection")

    def close(self, connection):
        return None


class _ConnectFailureAdapter:
    def __init__(self, error):
        self.error = error
        self.connect_calls = 0

    def status(self):
        return {"status": "READY", "driver": "mock-psycopg", "connection_opened": False}

    def connect(self, settings):
        self.connect_calls += 1
        raise self.error

    def close(self, connection):
        return None


class _MockPsycopg:
    def __init__(self):
        self.kwargs = None
        self.connection = _Connection()

    def connect(self, **kwargs):
        self.kwargs = kwargs
        return self.connection


class _Cursor:
    description = None

    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def close(self):
        return None


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commit_count += 1


class RemediationRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]

    def test_candidate_hashes_are_generated_and_stable(self):
        first = verify_candidate_hashes(self.repo_root)
        second = generate_candidate_hashes(self.repo_root)
        third = generate_candidate_hashes(self.repo_root)
        self.assertEqual("PASS", first["status"])
        self.assertEqual(9, first["matched_count"])
        self.assertEqual(0, first["pending_count"])
        self.assertEqual("PASS", first["dependency_status"])
        self.assertEqual(second, third)

    def test_tampered_candidate_is_detected_without_changing_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                self.repo_root / "database/migrations/v4_runtime_candidate",
                root / "database/migrations/v4_runtime_candidate",
            )
            candidate = root / "database/migrations/v4_runtime_candidate/0001_prerequisites.sql"
            candidate.write_text(candidate.read_text(encoding="utf-8") + "-- tamper fixture\n", encoding="utf-8")
            result = verify_candidate_hashes(root)
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(any(issue["code"] == "BYTE_HASH_MISMATCH" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "CANONICAL_HASH_MISMATCH" for issue in result["issues"]))

    def test_direct_hash_calculation_rejects_candidate_path_escape(self):
        manifest = json.loads(
            (self.repo_root / "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        entry = dict(manifest["candidates"][0])
        entry["candidate_file"] = "database/migrations/v4_runtime_candidate/../v4/0001_prerequisites.sql"
        with self.assertRaises(CanonicalHashError):
            canonical_hash_for_entry(self.repo_root, entry)

    def test_stable_metadata_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                self.repo_root / "database/migrations/v4_runtime_candidate",
                root / "database/migrations/v4_runtime_candidate",
            )
            manifest_path = root / "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["candidates"][0]["name"] = "tampered-stable-name"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = verify_candidate_hashes(root)
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(any(issue["code"] == "CANONICAL_HASH_MISMATCH" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "SQL_HEADER_MISMATCH" for issue in result["issues"]))

    def test_explicit_hash_writer_backfills_deterministic_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(
                self.repo_root / "database/migrations/v4_runtime_candidate",
                root / "database/migrations/v4_runtime_candidate",
            )
            manifest_path = root / "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["candidates"]:
                entry.pop("migration_version", None)
                entry.pop("schema_contract_version", None)
                entry.pop("authored_at", None)
                entry["canonical_migration_hash"] = "PENDING_CANONICAL_HASH"
                entry.pop("content_sha256_noncanonical", None)
            manifest["canonical_hash_status"] = "PENDING_CANONICAL_HASH"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = write_candidate_hashes(root)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(9, result["matched_count"])
            written = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(all(entry.get("migration_version") == entry.get("migration_id") for entry in written["candidates"]))

    def test_sql_canonicalization_is_explicit_and_stable(self):
        source = "\ufeffSELECT 1;  \r\n\r\n"
        self.assertEqual(b"SELECT 1;\n", canonicalize_sql_text(source))

    def test_plan_only_never_invokes_adapter(self):
        adapter = _FailingAdapter()
        report = RuntimeExecutor(self.repo_root, connection_adapter=adapter).execute(
            target=default_disposable_target(),
            mode=ExecutionMode.PLAN_ONLY,
        )
        self.assertEqual("PLANNED", report["status"])
        self.assertEqual(0, adapter.connect_calls)
        self.assertFalse(report["execution_boundary"]["connector_invoked"])
        self.assertFalse(report["execution_boundary"]["database_connected"])
        self.assertFalse(report["execution_boundary"]["sql_executed"])
        self.assertEqual("PASS", report["static_preflight"]["status"])
        self.assertFalse(report["static_preflight"]["connector_invoked"])
        self.assertEqual(20, report["runtime_case_wiring"]["smoke_count"])
        self.assertEqual(15, report["runtime_case_wiring"]["enforcement_count"])

    def test_production_apply_is_hard_blocked_before_adapter(self):
        adapter = _FailingAdapter()
        target = default_disposable_target()
        target.update(
            {
                "target_id": "jcfb-v4-production-review",
                "environment": "PRODUCTION",
                "provider": "PRODUCTION_SUPABASE",
                "disposable": False,
                "connect_permission": "BLOCKED",
            }
        )
        report = RuntimeExecutor(self.repo_root, connection_adapter=adapter).execute(
            target=target,
            mode=ExecutionMode.PRODUCTION_APPLY,
        )
        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("PRODUCTION_TARGET_HARD_BLOCK", report["blocking_reasons"])
        self.assertEqual("BLOCKED", report["static_preflight"]["status"])
        self.assertEqual(0, adapter.connect_calls)

    def test_missing_host_port_fails_closed_with_specific_reason(self):
        adapter = _FailingAdapter()
        incomplete_env = {
            "JCFB_V4_RUNTIME_DB_NAME": "jcfb_v4_runtime",
            "JCFB_V4_RUNTIME_DB_USER": "local_owner",
            "JCFB_V4_RUNTIME_DB_PASSWORD": "test-secret",
            "JCFB_V4_RUNTIME_DB_SSLMODE": "disable",
        }
        with patch.dict(os.environ, incomplete_env, clear=True):
            report = RuntimeExecutor(self.repo_root, connection_adapter=adapter).execute(
                target=default_disposable_target(),
                mode=ExecutionMode.APPLY,
            )
        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("RUNTIME_CONNECTION_CONFIG_INVALID", report["blocking_reasons"])
        self.assertEqual(0, adapter.connect_calls)
        self.assertFalse(report["execution_boundary"]["connector_invoked"])
        self.assertEqual(
            ["JCFB_V4_RUNTIME_DB_HOST", "JCFB_V4_RUNTIME_DB_PORT"],
            report["connection"]["missing_environment_variables"],
        )
        self.assertEqual("CONNECTOR_NOT_INVOKED", report["failure_taxonomy"]["connector_status"])
        self.assertNotIn("test-secret", json.dumps(report))

    def test_connector_connection_failure_is_invoked_and_classified(self):
        adapter = _ConnectFailureAdapter(TimeoutError("local socket timed out"))
        settings = ConnectionSettings("127.0.0.1", 5433, "db", "user", "test-secret", "disable")
        report = RuntimeExecutor(self.repo_root, connection_adapter=adapter).execute(
            target=default_disposable_target(),
            mode=ExecutionMode.APPLY,
            connection_settings=settings,
        )
        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("CONNECTION_REFUSED", report["blocking_reasons"])
        self.assertEqual(1, adapter.connect_calls)
        self.assertTrue(report["execution_boundary"]["connector_invoked"])
        self.assertFalse(report["execution_boundary"]["database_connected"])
        self.assertEqual("CONNECTION_REFUSED", report["error"]["error_code"])
        self.assertEqual("CONNECTOR_INVOKED", report["failure_taxonomy"]["connector_status"])
        self.assertNotIn("local socket timed out", json.dumps(report))

    def test_mocked_psycopg_connector_path_reaches_runtime_pass(self):
        driver = _MockPsycopg()
        adapter = PostgresConnectionAdapter(driver=driver, driver_name="psycopg")
        settings = ConnectionSettings("127.0.0.1", 5433, "db", "user", "test-secret", "disable")
        with patch.object(
            RuntimeExecutor,
            "_runtime_preflight",
            return_value={"status": "PASS", "checks": []},
        ), patch.object(
            RuntimeExecutor,
            "_apply_candidates",
            return_value={"status": "PASS", "applied_count": 0, "records": []},
        ), patch.object(
            RuntimeExecutor,
            "_runtime_postflight",
            return_value={"status": "PASS", "checks": []},
        ), patch(
            "tools.migration_harness.runtime_executor.run_runtime_cases",
            return_value={"status": "PASS", "actually_executed": 35},
        ):
            report = RuntimeExecutor(self.repo_root, connection_adapter=adapter).execute(
                target=default_disposable_target(),
                mode=ExecutionMode.APPLY,
                connection_settings=settings,
            )
        self.assertEqual("RUNTIME_VALIDATION_PASS", report["status"])
        self.assertTrue(report["execution_boundary"]["connector_invoked"])
        self.assertTrue(report["execution_boundary"]["database_connected"])
        self.assertEqual("CONNECTED", report["connection"]["status"])
        self.assertEqual("127.0.0.1", driver.kwargs["host"])
        self.assertEqual(5433, driver.kwargs["port"])
        self.assertNotIn("url", driver.kwargs)
        self.assertNotIn("test-secret", json.dumps(report))

    def test_disposable_host_port_guard_is_localhost_only_and_fail_closed(self):
        compose = (self.repo_root / "docker-compose.runtime-validation.yml").read_text(encoding="utf-8")
        helper = (self.repo_root / "scripts/v4_disposable_runtime.ps1").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:5433:5432"', compose)
        self.assertIn("Test-DisposableHostPort", helper)
        self.assertIn("BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING", helper)
        self.assertIn("BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST", helper)
        self.assertIn("127.0.0.1", helper)

    def test_connection_settings_redact_password(self):
        settings = ConnectionSettings(
            host="127.0.0.1",
            port=5433,
            database="jcfb_v4_runtime",
            user="local_owner",
            password="test-secret",
            sslmode="disable",
        )
        self.assertNotIn("password", settings.safe_dict())
        self.assertNotIn("test-secret", json.dumps(settings.safe_dict()))

    def test_transaction_wrapper_is_not_committed_before_history_insert(self):
        connection = _Connection()
        RuntimeExecutor._execute_sql(connection, "-- fixture\nBEGIN;\nSELECT 1;\nCOMMIT;\n")
        self.assertEqual(0, connection.commit_count)
        executed_sql = connection.cursor_value.executed[0][0]
        self.assertNotIn("BEGIN;", executed_sql)
        self.assertNotIn("COMMIT;", executed_sql)
        self.assertIn("SELECT 1;", executed_sql)

    def test_history_insert_waits_for_caller_commit(self):
        connection = _Connection()
        RuntimeExecutor(Path(self.repo_root))._record_history(
            connection,
            {
                "migration_id": "migration@20260901.001",
                "sequence": 1,
                "name": "fixture",
                "migration_version": "migration@20260901.001",
                "schema_contract_version": "v4-database-schema@1.0.0",
                "canonical_migration_hash": "sha256:" + "a" * 64,
            },
            applied_at="2026-09-01T00:00:00+08:00",
            applied_by="test",
            previous_hash=None,
            chain_hash="sha256:" + "b" * 64,
            status="APPLIED",
            success=True,
            partial_state=False,
            notes="fixture",
        )
        self.assertEqual(0, connection.commit_count)
        self.assertEqual(1, len(connection.cursor_value.executed))

    def test_runtime_case_wiring_is_exactly_twenty_plus_fifteen(self):
        report = validate_runtime_case_wiring(self.repo_root)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(20, report["smoke_count"])
        self.assertEqual(15, report["enforcement_count"])
        self.assertEqual([f"SMOKE-{index:02d}" for index in range(1, 21)], report["smoke_case_ids"])
        self.assertEqual([f"NEG-{index:02d}" for index in range(8, 23)], report["enforcement_case_ids"])

    def test_postgres_adapter_uses_keyword_settings_without_url(self):
        class Driver:
            __name__ = "test_driver"

            def __init__(self):
                self.kwargs = None

            def connect(self, **kwargs):
                self.kwargs = kwargs
                return object()

        driver = Driver()
        settings = ConnectionSettings("127.0.0.1", 5433, "db", "user", "secret", "disable")
        PostgresConnectionAdapter(driver=driver).connect(settings)
        self.assertEqual("127.0.0.1", driver.kwargs["host"])
        self.assertNotIn("url", driver.kwargs)
        self.assertEqual("secret", driver.kwargs["password"])


if __name__ == "__main__":
    unittest.main()
