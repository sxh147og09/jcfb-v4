from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


class PgcryptoSchemaForwardFixTests(unittest.TestCase):
    """Regression coverage for the unapplied 0009 schema-placement repair."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.candidate_dir = cls.repo_root / "database/migrations/v4_runtime_candidate"
        cls.candidate_0009 = (cls.candidate_dir / "0009_seed_and_smoke.sql").read_text(encoding="utf-8")
        cls.bootstrap = (cls.repo_root / "database/runtime/0000_service_role.sql").read_text(encoding="utf-8")
        cls.manifest = json.loads(
            (cls.candidate_dir / "0000_runtime_candidate_manifest.json").read_text(encoding="utf-8")
        )

    def test_0009_replaces_audit_function_before_first_audited_insert(self):
        replace_at = self.candidate_0009.index("CREATE OR REPLACE FUNCTION governance.append_audit_event()")
        seed_at = self.candidate_0009.index("INSERT INTO governance.hash_algorithm_registry")
        self.assertLess(replace_at, seed_at)
        self.assertIn("extensions.digest(", self.candidate_0009)
        self.assertNotRegex(self.candidate_0009, r"(?i)public\.digest\s*\(")
        self.assertIn("PGCRYPTO_SCHEMA_MISMATCH", self.candidate_0009)
        self.assertIn("SQLSTATE 42883", self.candidate_0009)

    def test_forward_fix_does_not_create_public_wrapper_or_move_extension(self):
        self.assertNotRegex(self.candidate_0009, r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.digest")
        self.assertNotRegex(self.candidate_0009, r"(?im)^\s*(?:ALTER|DROP)\s+EXTENSION\s+pgcrypto")
        self.assertNotRegex(self.candidate_0009, r"(?im)^\s*CREATE\s+SCHEMA\s+public")

    def test_disposable_bootstrap_mirrors_extensions_schema_and_uuid_resolution(self):
        self.assertIn("CREATE SCHEMA IF NOT EXISTS extensions", self.bootstrap)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions", self.bootstrap)
        self.assertRegex(
            self.bootstrap,
            r'(?is)ALTER DATABASE %I SET search_path = "\$user", public, extensions',
        )
        self.assertIn("GRANT USAGE ON SCHEMA extensions TO service_role", self.bootstrap)

    def test_disposable_executor_has_only_frozen_prefix_history_trigger_accommodation(self):
        executor = (self.repo_root / "tools/migration_harness/runtime_executor.py").read_text(encoding="utf-8")
        self.assertIn("DISPOSABLE_LOCAL_FROZEN_PREFIX_HISTORY_AUDIT_TRIGGER_BYPASS", executor)
        self.assertIn("DISABLE TRIGGER v4_schema_history_audit_event", executor)
        self.assertIn("ENABLE TRIGGER v4_schema_history_audit_event", executor)
        self.assertNotIn("CREATE FUNCTION public.digest", executor)

    def test_applied_prefix_sql_bytes_remain_frozen(self):
        expected = {
            1: "6ea852a6924082767912a46b8859a7610828835273f0f6fb01fe4893f6c63511",
            2: "c85cfae6c1fe7aba3e1bf05be794ec43d5adb47d055dd7db89c0e1f816257504",
            3: "9b621fd38c6030f9b73e45a944a787bd214e1585e231ce7cbe3e1a79b7642881",
            4: "3339d35a37d92eca4ca76bf0a42ae02deac5fcf8ed8a190a0a5830bf48140751",
            5: "da6658b3e665f085c3968c3010ccfa0e17211824fdd28523faaa49aa750b4e81",
            6: "1ba475b2585f3f25d4984f82e2c7e8a94c815f47ff91a2d4728707adc9ee71b8",
            7: "367c0b4d52d84e60bca6c1bee797a45f5fc7ea769cf21508efacf9cb2a6978c3",
            8: "dc19e7a76839b2b2fd594f3c871d8340b4231fd4d9defb9dc6eb7f592012ca48",
        }
        import hashlib

        for sequence, digest in expected.items():
            path = next(self.candidate_dir.glob(f"{sequence:04d}_*.sql"))
            with self.subTest(sequence=sequence):
                self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_manifest_scope_and_provenance_are_0009_only(self):
        forward_fix = self.manifest["forward_fix"]
        self.assertEqual("JCFB V4 0009 PGCRYPTO SCHEMA FORWARD-FIX 1.0", forward_fix["identity"])
        self.assertEqual("0009_FAILED_ROLLED_BACK", forward_fix["partial_apply_state"])
        self.assertEqual("migration@20260901.009", forward_fix["failed_migration"])
        self.assertEqual("42883", forward_fix["failed_sqlstate"])
        self.assertEqual("PGCRYPTO_SCHEMA_MISMATCH", forward_fix["failure_code"])
        self.assertEqual(["migration@20260901.009"], forward_fix["unapplied_suffix"])
        self.assertEqual(["migration@20260901.009"], forward_fix["resume_scope"])
        self.assertTrue(forward_fix["applied_prefix_hashes_frozen"])
        self.assertTrue(forward_fix["new_explicit_resume_approval_required"])
        self.assertFalse(forward_fix["v333_objects_modified"])


if __name__ == "__main__":
    unittest.main()
