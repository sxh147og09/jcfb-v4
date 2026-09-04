from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    FeatureBundle,
    FeatureBundleValidationError,
    FeatureSchemaRegistry,
    FeatureSnapshotHasher,
    FeatureSnapshotValidationError,
)


class V4039FeatureSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.fixtures = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))
        cls.rules = json.loads((cls.root / "tests/fixtures/v4_039/feature_snapshot_replay.json").read_text(encoding="utf-8"))["expected_rules"]

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture))
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id
        self.registry = FeatureSchemaRegistry()
        self.registry.register(copy.deepcopy(self.fixtures["schema"]))

    def bundle(self):
        raw = copy.deepcopy(self.fixtures["base"])
        raw["canonical_entity_refs"]["match_id"] = self.match_id
        return FeatureBundle.from_dict(raw, identity_store=self.identity_store, schema_registry=self.registry)

    def test_canonical_serializer_is_stable_and_seals_snapshot_hash(self):
        bundle = self.bundle()
        first = FeatureSnapshotHasher.calculate(bundle)
        second = FeatureSnapshotHasher.calculate(bundle)
        self.assertEqual(first.feature_snapshot_hash, second.feature_snapshot_hash)
        self.assertEqual(first.canonical_payload, second.canonical_payload)
        self.assertTrue(first.feature_snapshot_hash.startswith("sha256:"))
        self.assertEqual(self.rules["same_logical_inputs_same_hash"], True)
        sealed = FeatureSnapshotHasher.seal(bundle)
        self.assertEqual(first.feature_snapshot_hash, sealed.feature_snapshot_hash)
        self.assertTrue(FeatureSnapshotHasher.verify(sealed, first.feature_snapshot_hash))

    def test_volatile_generated_at_does_not_change_snapshot_hash(self):
        first = self.bundle()
        changed = copy.deepcopy(first.to_dict())
        changed["generated_at"] = "2026-09-04T10:12:00+08:00"
        second = FeatureBundle.from_dict(changed, identity_store=self.identity_store, schema_registry=self.registry)
        self.assertEqual(FeatureSnapshotHasher.calculate(first).feature_snapshot_hash, FeatureSnapshotHasher.calculate(second).feature_snapshot_hash)

    def test_logical_feature_changes_change_snapshot_hash(self):
        original = self.bundle()
        original_hash = FeatureSnapshotHasher.calculate(original).feature_snapshot_hash
        for field, value in (
            ("value", 1.75),
            ("state", "UNKNOWN"),
            ("unit", "percent"),
            ("derivation_ref", "derivation-stat-2"),
        ):
            changed = copy.deepcopy(original.to_dict())
            changed["feature_snapshot_hash"] = None
            changed.pop("feature_hash", None)
            changed.pop("payload_hash", None)
            changed["feature_values"]["statistical_features"][0][field] = value
            if field == "state":
                changed["feature_values"]["statistical_features"][0]["value"] = None
                changed["feature_values"]["statistical_features"][0]["reason_code"] = "VALUE_NOT_VERIFIED"
                changed["feature_values"]["statistical_features"][0]["reason_detail"] = "Test state change"
            altered = FeatureBundle.from_dict(changed, identity_store=self.identity_store, schema_registry=self.registry)
            self.assertNotEqual(original_hash, FeatureSnapshotHasher.calculate(altered).feature_snapshot_hash, field)

    def test_upstream_hash_and_config_cutoff_changes_change_snapshot_hash(self):
        original = self.bundle()
        original_hash = FeatureSnapshotHasher.calculate(original).feature_snapshot_hash
        for field, value in (("config_hash", "sha256:" + "9" * 64), ("prediction_cutoff_at", "2026-09-04T09:11:00+08:00")):
            changed = copy.deepcopy(original.to_dict())
            changed["feature_snapshot_hash"] = None
            changed[field] = value
            changed.pop("input_hash", None)
            altered = FeatureBundle.from_dict(changed, identity_store=self.identity_store, schema_registry=self.registry)
            self.assertNotEqual(original_hash, FeatureSnapshotHasher.calculate(altered).feature_snapshot_hash, field)

    def test_frozen_input_and_prediction_cannot_enter_snapshot_boundary(self):
        raw = self.bundle().to_dict()
        raw["frozen_input_id"] = "mock"
        with self.assertRaises(FeatureBundleValidationError):
            FeatureBundle.from_dict(raw, identity_store=self.identity_store, schema_registry=self.registry)
        raw = self.bundle().to_dict()
        raw["prediction"] = {"market": "SPF"}
        with self.assertRaises(FeatureBundleValidationError):
            FeatureBundle.from_dict(raw, identity_store=self.identity_store, schema_registry=self.registry)
        self.assertTrue(self.rules["frozen_input_is_excluded"])
        self.assertFalse(self.rules["prediction_is_excluded"])


if __name__ == "__main__":
    unittest.main()
