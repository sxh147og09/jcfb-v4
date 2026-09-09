import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "config/prediction_training/v4_batch15_verified_historical_backfill_contract_amendment_003.json"


class B15HistoricalBackfillAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.auth = json.loads(AUTH.read_text(encoding="utf-8"))

    def test_revision_is_append_only_and_hash_bound(self):
        self.assertEqual("B15-EWP-001-ADDENDUM-003", self.auth["amendment_id"])
        self.assertEqual("B15-EWP-001-ADDENDUM-002", self.auth["amends"])
        self.assertTrue(self.auth["additive_only"])
        body = {key: value for key, value in self.auth.items() if key != "canonical_hash"}
        expected = "sha256:" + hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(expected, self.auth["canonical_hash"])

    def test_scope_is_conditional_and_training_remains_locked(self):
        scope = self.auth["authorized_scope"]
        for field in (
            "reviewed_extraction_trace_generation",
            "accepted_official_odds_payload_candidate_generation",
            "r002_deterministic_rebuild",
            "no_write_intake_dry_run",
            "historical_archive_append_only_intake",
            "ewp002_real_historical_dataset_rerun",
            "ewp003_real_temporal_readiness_rerun",
        ):
            self.assertIs(scope[field], True)
        gates = self.auth["conditional_gates"]
        self.assertIs(gates["archive_write_requires_no_write_intake_pass"], True)
        self.assertIs(gates["stop_on_any_failure"], True)
        self.assertEqual("NOT_STARTED", self.auth["training_lock"]["formal_model_training"])
        self.assertIs(self.auth["training_lock"]["ewp005_execution_authorized"], False)

    def test_forbidden_boundaries_are_explicit(self):
        forbidden = set(self.auth["not_authorized"])
        for expected in ("EWP-005_FORMAL_MODEL_FIT", "PRODUCTION", "SUPABASE", "PUBLIC_DEPLOYMENT", "V3.3.3_READ_OR_WRITE", "POST_MATCH_LEAKAGE"):
            self.assertIn(expected, forbidden)


if __name__ == "__main__":
    unittest.main()
