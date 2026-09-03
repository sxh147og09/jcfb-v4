from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.migration_harness.view_compatibility import (
    V333_PUBLIC_VIEW_BASELINE,
    V4_PUBLIC_VIEW_NAMES,
    ViewCompatibilityError,
    ViewContract,
    assert_reusable_view,
    choose_view_strategy,
    created_view_names,
    forbidden_view_mutations,
    normalized_contract,
    public_view_collisions,
    view_contracts_equivalent,
)


class ViewForwardFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.candidate_path = cls.repo_root / "database/migrations/v4_runtime_candidate/0008_views_projections.sql"
        cls.candidate_sql = cls.candidate_path.read_text(encoding="utf-8")

    @staticmethod
    def _contract(*, definition: str = "SELECT 1", grants=None, reloptions=("security_invoker=true",)) -> ViewContract:
        return ViewContract(
            definition=definition,
            reloptions=tuple(reloptions),
            grants=frozenset(grants or {("anon", "SELECT"), ("authenticated", "SELECT")}),
        )

    def test_existing_equivalent_v333_view_is_asserted_and_reused_without_replacement(self):
        intended = self._contract(definition="SELECT match_id FROM public.public_read_projections")
        existing = self._contract(definition=" select   match_id FROM public.public_read_projections ")

        self.assertEqual(
            "ASSERT_AND_REUSE",
            choose_view_strategy(
                "public.v_public_predictions",
                existing,
                intended,
                v4_name="public.v4_public_predictions",
            ),
        )
        self.assertEqual(normalized_contract(existing), assert_reusable_view("public.v_public_predictions", existing, intended))
        self.assertEqual((), forbidden_view_mutations(self.candidate_sql))

    def test_existing_incompatible_view_fails_closed_and_requires_v4_rename(self):
        intended = self._contract(definition="SELECT match_id FROM public.public_read_projections")
        existing = self._contract(definition="SELECT match_id FROM public.predictions")

        with self.assertRaises(ViewCompatibilityError):
            assert_reusable_view("public.v_public_predictions", existing, intended)
        self.assertEqual(
            "V4_RENAME",
            choose_view_strategy(
                "public.v_public_predictions",
                existing,
                intended,
                v4_name="public.v4_public_predictions",
            ),
        )

    def test_missing_v4_owned_view_creates_only_approved_object(self):
        intended = self._contract()
        self.assertEqual(
            "CREATE_APPROVED",
            choose_view_strategy(
                "public.v4_public_predictions",
                None,
                intended,
                v4_name="public.v4_public_predictions",
            ),
        )
        self.assertEqual(set(created_view_names(self.candidate_sql)), V4_PUBLIC_VIEW_NAMES)
        self.assertEqual((), public_view_collisions(self.candidate_sql))

    def test_all_eleven_baseline_names_are_scanned_and_no_legacy_view_is_created(self):
        self.assertEqual(11, len(V333_PUBLIC_VIEW_BASELINE))
        expected_collisions = {
            "public.v_public_predictions",
            "public.v_public_latest_odds",
            "public.v_current_frozen_predictions",
            "public.v_canonical_latest_update",
            "public.v_tier_a_progress",
        }
        self.assertTrue(expected_collisions <= V333_PUBLIC_VIEW_BASELINE)
        self.assertEqual((), public_view_collisions(self.candidate_sql, V333_PUBLIC_VIEW_BASELINE))
        self.assertNotRegex(self.candidate_sql, r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+public\.v_(?!4_)")
        self.assertNotRegex(self.candidate_sql, r"(?im)^\s*DROP\s+VIEW\b")

    def test_security_invoker_and_grants_are_part_of_equivalence(self):
        intended = self._contract()
        self.assertTrue(view_contracts_equivalent(self._contract(), intended))
        self.assertFalse(view_contracts_equivalent(self._contract(reloptions=("security_invoker=false",)), intended))
        self.assertFalse(view_contracts_equivalent(self._contract(grants={("service_role", "SELECT")}), intended))

        for qualified_name in sorted(V4_PUBLIC_VIEW_NAMES):
            self.assertRegex(
                self.candidate_sql,
                rf"(?im)^\s*CREATE\s+VIEW\s+{re.escape(qualified_name)}\s*$",
            )
            self.assertRegex(
                self.candidate_sql,
                rf"(?is)CREATE\s+VIEW\s+{re.escape(qualified_name)}\s+WITH\s*\(\s*security_invoker\s*=\s*true\s*\)",
            )
            self.assertRegex(self.candidate_sql, rf"(?is)GRANT\s+SELECT\s+ON\s+[^;]*{re.escape(qualified_name)}")

    def test_applied_prefix_hashes_are_frozen(self):
        manifest_path = self.repo_root / "database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            1: "sha256:1b959f089bc3f46e272ee7edc19b6a9665c78b4067cdad470a3ebc98a513f2bb",
            2: "sha256:7edfc9c4c2c0085f63d0e0860f0d2f74f6a1e85d9b1ac4e602571347e5dd332a",
            3: "sha256:dc493407c012e1296b884ab64eaa251ee6b32fff6c0a9d5cacfe4860098db808",
            4: "sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb",
            5: "sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394",
            6: "sha256:85386b242f6f1ef8fabd1aa09b07f1b4c3082b589b0c6c320bb9705883a5a52d",
            7: "sha256:952ae622fba16f831389b8bfd3b0bfa05b6278f721c41c768532f37d6178a4b0",
        }
        actual = {entry["sequence"]: entry["canonical_migration_hash"] for entry in manifest["candidates"] if entry["sequence"] <= 7}
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
