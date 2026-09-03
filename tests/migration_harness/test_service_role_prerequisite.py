from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.migration_harness.service_role_prerequisite import (
    PUBLIC_ROLE_BYPASSRLS_FORBIDDEN_CODE,
    SERVICE_ROLE_BYPASSRLS_REQUIRED_CODE,
    SERVICE_ROLE_MISSING_CODE,
    evaluate_service_role_prerequisite,
)


class ServiceRolePrerequisiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.candidate_path = cls.repo_root / "database" / "migrations" / "v4_runtime_candidate" / "0001_prerequisites.sql"
        cls.candidate_sql = cls.candidate_path.read_text(encoding="utf-8")
        cls.generator_sql = (cls.repo_root / "tools" / "migration_harness" / "promote_runtime_candidates.py").read_text(encoding="utf-8")

    @staticmethod
    def _roles(*, service_role: bool | None = True, anon: bool = False, authenticated: bool = False):
        rows = {
            "anon": {"rolbypassrls": anon},
            "authenticated": {"rolbypassrls": authenticated},
        }
        if service_role is not None:
            rows["service_role"] = {"rolbypassrls": service_role}
        return rows

    def test_service_role_exists_with_bypass_true_passes(self):
        result = evaluate_service_role_prerequisite(self._roles(service_role=True))
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["service_role_exists"])
        self.assertTrue(result["service_role_bypass_rls"])
        self.assertTrue(result["anon_authenticated_bypass_rls_false"])

    def test_service_role_exists_with_bypass_false_fails_closed(self):
        result = evaluate_service_role_prerequisite(self._roles(service_role=False))
        self.assertEqual("FAIL", result["status"])
        self.assertEqual(SERVICE_ROLE_BYPASSRLS_REQUIRED_CODE, result["code"])

    def test_missing_service_role_fails_closed(self):
        result = evaluate_service_role_prerequisite(self._roles(service_role=None))
        self.assertEqual("FAIL", result["status"])
        self.assertEqual(SERVICE_ROLE_MISSING_CODE, result["code"])

    def test_anon_and_authenticated_bypass_invariant_is_enforced(self):
        for role in ("anon", "authenticated"):
            values = {"service_role": {"rolbypassrls": True}, "anon": {"rolbypassrls": False}, "authenticated": {"rolbypassrls": False}}
            values[role]["rolbypassrls"] = True
            with self.subTest(role=role):
                result = evaluate_service_role_prerequisite(values)
                self.assertEqual("FAIL", result["status"])
                self.assertEqual(PUBLIC_ROLE_BYPASSRLS_FORBIDDEN_CODE, result["code"])

    def test_0001_uses_verification_only_reserved_role_prerequisite(self):
        self.assertRegex(self.candidate_sql, r"(?is)SELECT\s+rolbypassrls.*?FROM\s+pg_catalog\.pg_roles")
        self.assertIn("IF NOT FOUND", self.candidate_sql)
        self.assertIn(SERVICE_ROLE_MISSING_CODE, self.candidate_sql)
        self.assertIn(SERVICE_ROLE_BYPASSRLS_REQUIRED_CODE, self.candidate_sql)
        self.assertIn(PUBLIC_ROLE_BYPASSRLS_FORBIDDEN_CODE, self.candidate_sql)
        for pattern in (
            r"(?i)\bALTER\s+ROLE\s+service_role\b",
            r"(?i)\bCREATE\s+ROLE\s+service_role\b",
            r"(?i)\bSET\s+ROLE\s+service_role\b",
        ):
            self.assertNotRegex(self.candidate_sql, pattern)

    def test_no_reserved_role_mutation_remains_in_any_runtime_candidate_sql(self):
        candidate_dir = self.repo_root / "database" / "migrations" / "v4_runtime_candidate"
        mutation = re.compile(r"(?i)\b(?:ALTER|CREATE|SET)\s+ROLE\s+service_role\b")
        for path in sorted(candidate_dir.glob("*.sql")):
            with self.subTest(path=path.name):
                self.assertIsNone(mutation.search(path.read_text(encoding="utf-8")))

    def test_generator_forbids_provider_reserved_role_mutation(self):
        mutation = re.compile(r"(?i)\b(?:ALTER|CREATE|SET)\s+ROLE\s+service_role\b")
        self.assertIsNone(mutation.search(self.generator_sql))
        self.assertIn("service_role is intentionally absent from this list", self.generator_sql)

    def test_disposable_compatibility_bootstrap_is_separate_from_candidate(self):
        bootstrap_path = self.repo_root / "database" / "runtime" / "0000_service_role.sql"
        bootstrap_sql = bootstrap_path.read_text(encoding="utf-8")
        self.assertIn("JCFB V4 DISPOSABLE LOCAL ROLE BOOTSTRAP", bootstrap_sql)
        self.assertIn("not a Supabase/Production patch", bootstrap_sql)
        self.assertRegex(bootstrap_sql, r"(?is)CREATE\s+ROLE\s+service_role.*?BYPASSRLS")
        self.assertNotRegex(bootstrap_sql, r"(?i)\bALTER\s+ROLE\s+service_role\b")


if __name__ == "__main__":
    unittest.main()
