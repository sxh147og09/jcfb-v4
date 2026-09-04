from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from tools.canonical_intake import (
    CanonicalMatchIdentityStore,
    FeatureAssemblyStore,
    FeatureAssemblyValidationError,
    FeatureBundle,
    FeatureSchemaRegistry,
    FeatureSnapshotHasher,
    SchemaAdapterRegistry,
)


class V4040FeatureAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.identity_fixture = json.loads((cls.root / "tests/fixtures/v4_020/identity_cases.json").read_text(encoding="utf-8"))["base"]
        cls.bundle_fixture = json.loads((cls.root / "tests/fixtures/v4_038/feature_bundle_cases.json").read_text(encoding="utf-8"))
        cls.assembly_fixture = json.loads((cls.root / "tests/fixtures/v4_040/assembly_cases.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.identity_store = CanonicalMatchIdentityStore()
        identity = self.identity_store.ingest(copy.deepcopy(self.identity_fixture))
        self.assertTrue(identity.accepted)
        self.match_id = identity.canonical_match_id
        self.schema_registry = FeatureSchemaRegistry()
        self.schema_registry.register(copy.deepcopy(self.bundle_fixture["schema"]))
        raw_bundle = copy.deepcopy(self.bundle_fixture["base"])
        raw_bundle["canonical_entity_refs"]["match_id"] = self.match_id
        bundle = FeatureBundle.from_dict(raw_bundle, identity_store=self.identity_store, schema_registry=self.schema_registry)
        self.bundle = FeatureSnapshotHasher.seal(bundle)
        self.adapter_registry = SchemaAdapterRegistry()
        self.source_objects = []
        for index, kind in enumerate(("canonical_fact", "official_odds_snapshot", "external_market_snapshot", "team_context", "evidence_graph")):
            item = {
                "source_kind": kind,
                "schema_version": self.assembly_fixture["source_schema_version"],
                "object_id": f"{kind}-001",
                "object_hash": "sha256:" + str(index + 1) * 64,
                "match_id": self.match_id,
                "source": f"{kind}-source",
                "source_reference": f"ref://{kind}/001",
                "status": "AVAILABLE",
                "available_at": self.assembly_fixture["available_at"],
                "provenance_hash": "sha256:" + "a" * 64,
                "payload": {"state": "AVAILABLE", "observed": True}
            }
            if kind == "official_odds_snapshot":
                item["source_is_official"] = True
            if kind == "external_market_snapshot":
                item["source_is_official"] = False
            self.source_objects.append(item)
            self.adapter_registry.register({"source_kind": kind, "source_schema_version": self.assembly_fixture["source_schema_version"], "target_feature_schema_version": self.assembly_fixture["target_feature_schema_version"], "adapter_version": self.assembly_fixture["adapter_version"]})

    def request(self):
        return {
            "target_feature_schema_version": self.assembly_fixture["target_feature_schema_version"],
            "generator_version": self.bundle.generator_version,
            "role": self.bundle.role,
            "config_version": self.bundle.config_version,
            "config_hash": self.bundle.config_hash,
            "canonical_entity_refs": self.bundle.to_dict()["canonical_entity_refs"],
            "source_objects": copy.deepcopy(self.source_objects),
            "schema_adapters": [{"source_kind": adapter.source_kind, "source_schema_version": adapter.source_schema_version, "target_feature_schema_version": adapter.target_feature_schema_version, "adapter_version": adapter.adapter_version} for adapter in self.adapter_registry.adapters],
            "prediction_cutoff_at": self.assembly_fixture["prediction_cutoff_at"],
            "kickoff_at": self.assembly_fixture["kickoff_at"],
            "feature_bundle": self.bundle.to_dict(),
        }

    def test_assembly_consumes_versioned_inputs_and_preserves_handoff(self):
        store = FeatureAssemblyStore(self.adapter_registry)
        result = store.assemble(self.request())
        self.assertTrue(result.accepted, result.error_code)
        self.assertIsNotNone(result.handoff)
        assert result.handoff is not None
        self.assertEqual(self.bundle.feature_bundle_id, result.handoff["feature_bundle_id"])
        self.assertEqual(self.bundle.feature_snapshot_hash, result.handoff["feature_snapshot_hash"])
        self.assertEqual(self.bundle.input_hash, result.handoff["input_hash"])
        self.assertEqual("APPEND", result.action)

    def test_missingness_and_states_are_preserved_without_defaults(self):
        request = self.request()
        request["feature_bundle"]["missingness_summary"]["AVAILABLE"] = 99
        request["feature_bundle"].pop("payload_hash", None)
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("MISSINGNESS_MISMATCH", result.error_code)

        request = self.request()
        request["feature_bundle"]["feature_snapshot_hash"] = None
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("FEATURE_SNAPSHOT_REQUIRED", result.error_code)

    def test_incompatible_schema_match_and_future_data_fail_closed(self):
        request = self.request()
        request["schema_adapters"][0]["source_schema_version"] = "source-envelope@9.0.0"
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("SCHEMA_ADAPTER_DECLARATION_MISMATCH", result.error_code)

        request = self.request()
        request["source_objects"][0]["match_id"] = "other-match"
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("SOURCE_MATCH_CONFLICT", result.error_code)

        request = self.request()
        request["source_objects"][0]["available_at"] = "2026-09-04T09:11:00+08:00"
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("FUTURE_DATA", result.error_code)

    def test_raw_source_display_join_and_synthetic_boundaries_fail(self):
        for field in ("raw_screenshot", "ocr_raw_text", "provider_raw_response", "free_form_news", "unversioned_json", "join_key"):
            request = self.request()
            request[field] = "forbidden"
            result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
            self.assertFalse(result.accepted, field)
            self.assertEqual("RAW_SOURCE_BYPASS", result.error_code, field)

        request = self.request()
        request["display_name"] = "Display Name Join"
        result = FeatureAssemblyStore(self.adapter_registry).assemble(request)
        self.assertFalse(result.accepted)
        self.assertEqual("DISPLAY_NAME_JOIN_FORBIDDEN", result.error_code)

    def test_append_only_assembly_and_f_drive_v333_audit(self):
        store = FeatureAssemblyStore(self.adapter_registry)
        first = store.assemble(self.request())
        second = store.assemble(self.request())
        self.assertTrue(first.accepted)
        self.assertEqual("DUPLICATE_NOOP", second.action)
        self.assertEqual(1, len(store.handoffs))
        changed = subprocess.run(["git", "diff", "--name-only", "6fbbddf"], cwd=self.root, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any("v3.3.3" in path.casefold() or "v333" in path.casefold() for path in changed))
        self.assertEqual("F:", self.root.drive.upper())


if __name__ == "__main__":
    unittest.main()
