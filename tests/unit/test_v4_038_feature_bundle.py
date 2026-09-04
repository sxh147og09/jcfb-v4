from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    FeatureBundle,
    FeatureBundleValidationError,
    FeatureBundleStore,
    FeatureSchemaRegistry,
    resolve_f_drive_output_path,
)
import subprocess


class V4038FeatureBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixtures = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture))
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id
        self.registry = FeatureSchemaRegistry()
        self.registry.register(copy.deepcopy(self.fixtures["schema"]))
        self.store = FeatureBundleStore(self.identity_store, self.registry)

    def bundle(self):
        raw = copy.deepcopy(self.fixtures["base"])
        raw["canonical_entity_refs"]["match_id"] = self.match_id
        return raw

    def test_registry_and_typed_bundle_are_versioned(self):
        result = self.store.ingest(self.bundle())
        self.assertTrue(result.accepted, result.error_code)
        self.assertIsNotNone(result.bundle)
        assert result.bundle is not None
        self.assertEqual("feature-bundle@2.0.0", result.bundle.contract_version)
        self.assertEqual("feature-schema@1.0.0", result.bundle.feature_schema_version)
        self.assertEqual("feature-generator@1.0.0", result.bundle.generator_version)
        self.assertEqual(7, len(result.bundle.feature_values))
        self.assertTrue(result.bundle.input_hash.startswith("sha256:"))
        self.assertTrue(result.bundle.feature_hash.startswith("sha256:"))
        self.assertEqual("PRESENT", result.bundle.feature_quality.conflict)

    def test_non_available_states_are_explicit_and_never_defaults(self):
        raw = self.bundle()
        for category in self.fixtures["base"]["feature_values"]:
            record = raw["feature_values"][category][0]
            if record["state"] != "AVAILABLE":
                self.assertIn("reason_code", record)
                self.assertIn("reason_detail", record)
        raw["feature_values"]["football_context_features"][0]["reason_code"] = ""
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("FEATURE_REASON_REQUIRED", result.error_code)

    def test_available_empty_value_and_forbidden_model_fields_fail_closed(self):
        raw = self.bundle()
        raw["feature_values"]["statistical_features"][0]["value"] = {}
        result = self.store.ingest(raw)
        self.assertFalse(result.accepted)
        self.assertEqual("AVAILABLE_VALUE_EMPTY", result.error_code)

        forbidden = self.bundle()
        forbidden["frozen_input_id"] = "mock-frozen-input"
        result = self.store.ingest(forbidden)
        self.assertFalse(result.accepted)
        self.assertEqual("FROZEN_INPUT_UPSTREAM_FORBIDDEN", result.error_code)

        prediction = self.bundle()
        prediction["feature_values"]["quality_features"][0]["prediction"] = "HOME"
        result = self.store.ingest(prediction)
        self.assertFalse(result.accepted)
        self.assertEqual("MODEL_FIELD_FORBIDDEN", result.error_code)

    def test_missing_identity_and_invalid_external_role_fail_closed(self):
        missing_identity = self.bundle()
        missing_identity["canonical_entity_refs"]["match_id"] = "00000000-0000-5000-8000-000000000099"
        result = self.store.ingest(missing_identity)
        self.assertFalse(result.accepted)
        self.assertEqual("MATCH_IDENTITY_NOT_FOUND", result.error_code)

        bad_role = self.bundle()
        bad_role["external_market_refs"][0]["source_is_official"] = True
        result = self.store.ingest(bad_role)
        self.assertFalse(result.accepted)
        self.assertEqual("SOURCE_ROLE_CONFLICT", result.error_code)

    def test_input_hash_is_upstream_only_and_tampering_is_rejected(self):
        raw = self.bundle()
        first = self.store.ingest(raw)
        self.assertTrue(first.accepted)
        assert first.bundle is not None
        self.assertNotIn("frozen_input_id", first.bundle.to_dict())
        tampered = self.bundle()
        tampered["input_hash"] = "sha256:" + "0" * 64
        result = self.store.ingest(tampered)
        self.assertFalse(result.accepted)
        self.assertEqual("INPUT_HASH_MISMATCH", result.error_code)

    def test_append_only_correction_requires_supersedes_and_next_revision(self):
        first = self.store.ingest(self.bundle())
        self.assertTrue(first.accepted)
        assert first.bundle is not None
        correction = self.bundle()
        correction["revision"] = 2
        correction["supersedes_feature_bundle_id"] = first.bundle.feature_bundle_id
        correction["feature_values"]["statistical_features"][0]["value"] = 1.3
        second = self.store.ingest(correction)
        self.assertTrue(second.accepted, second.error_code)
        self.assertEqual(2, len(self.store.bundles))
        self.assertEqual("APPEND", self.store.events[-1]["action"])

    def test_v333_isolation_and_f_drive_boundary(self):
        changed = subprocess.run(["git", "diff", "--name-only", "99e7a23"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertEqual("F:", resolve_f_drive_output_path("F:/Projects/jcfb-v4", "runtime/v4-038/evidence.json").drive.upper())
        with self.assertRaises(ValueError):
            resolve_f_drive_output_path("C:/Projects/jcfb-v4", "runtime/evidence.json")


if __name__ == "__main__":
    unittest.main()
