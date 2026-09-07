from __future__ import annotations

import copy
import json
import struct
import unittest
import zlib
from pathlib import Path

from src.official_odds_cells import (
    RemediatedCellLocatorRegistry,
    RemediatedLayoutProfileRegistry,
    build_full_trace,
    extract_structural_features,
    load_remediated_contract,
    resolve_availability_aliases,
)


def synthetic_png(spans: list[list[int]]) -> bytes:
    width, height = 440, 982
    rows = []
    for y in range(height):
        color = bytes((26, 57, 95)) if any(top <= y < bottom for top, bottom in spans) else bytes((255, 255, 255))
        rows.append(b"\x00" + color * width)
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


class OfficialOddsLayoutProfileRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.contract = load_remediated_contract()
        cls.registry = RemediatedLayoutProfileRegistry(cls.contract)
        cls.locator = RemediatedCellLocatorRegistry(cls.contract)
        cls.standard = synthetic_png([[220, 248], [517, 545], [622, 650]])
        cls.shifted = synthetic_png([[203, 231], [500, 528], [605, 633]])

    def test_registry_has_two_additive_profiles_and_full_inventory_geometry(self):
        self.assertEqual(
            {
                "china-sports-lottery-official-standard@1.1.0",
                "china-sports-lottery-official-spf-absent@1.0.0",
            },
            {profile["layout_profile_identity"] for profile in self.registry.profiles},
        )
        self.assertEqual([], self.locator.validate())
        self.assertEqual(55, sum(len(items) for items in self.contract["market_contract"]["inventories"].values()))
        for profile in self.registry.profiles:
            self.assertEqual(55, sum(len(items) for items in profile["cell_geometry_pixels"].values()))

    def test_raw_structural_detection_selects_standard_and_shifted(self):
        standard = self.registry.detect(raw_image=self.standard)
        shifted = self.registry.detect(raw_image=self.shifted)
        self.assertEqual("SELECTED", standard.status)
        self.assertEqual("china-sports-lottery-official-standard", standard.profile_id)
        self.assertEqual("SELECTED", shifted.status)
        self.assertEqual("china-sports-lottery-official-spf-absent", shifted.profile_id)
        self.assertEqual(3, len(extract_structural_features(self.standard)["dark_section_bar_spans"]))

    def test_unsupported_and_ambiguous_detection_fail_closed(self):
        unsupported = self.registry.detect(structural_features={"source_dimensions": {"width": 440, "height": 982}, "dark_section_bar_spans": [[1, 2]]})
        self.assertEqual("UNSUPPORTED_LAYOUT", unsupported.status)
        ambiguous_contract = copy.deepcopy(self.contract)
        duplicate = copy.deepcopy(ambiguous_contract["layout_profile_remediation"]["profiles"][0])
        duplicate["layout_profile_id"] = "test-duplicate-profile"
        duplicate["layout_profile_identity"] = "test-duplicate-profile@1.0.0"
        ambiguous_contract["layout_profile_remediation"]["profiles"].append(duplicate)
        ambiguous = RemediatedLayoutProfileRegistry(ambiguous_contract).detect(raw_image=self.standard)
        self.assertEqual("AMBIGUOUS_LAYOUT", ambiguous.status)

    def test_explicit_geometry_order_and_non_overlap_for_exact_total_and_htft(self):
        for profile in self.registry.profiles:
            for market, count in (("TOTAL_GOALS", 8), ("EXACT_SCORE", 31), ("HTFT", 9)):
                items = self.locator.inventory(market)
                self.assertEqual(list(range(count)), [item["ordering_index"] for item in items])
                locators = [self.locator.locate(profile["layout_profile_id"], market, item["source_visible_label"], 440, 982) for item in items]
                self.assertEqual(list(range(count)), [item["ordering_index"] for item in locators])
                non_null = [item["cell_pixel_coordinates"] for item in locators if item["cell_pixel_coordinates"]]
                self.assertEqual(len(non_null), count)
                for first_index, first in enumerate(non_null):
                    for second in non_null[first_index + 1 :]:
                        self.assertFalse(max(0, min(first[2], second[2]) - max(first[0], second[0])) * max(0, min(first[3], second[3]) - max(first[1], second[1])))

    def test_spf_absent_is_market_unavailable_only_for_spf(self):
        result = build_full_trace(
            self.shifted,
            artifact_identity="fixture://spf-absent",
            source_width=440,
            source_height=982,
            contract=self.contract,
        )
        self.assertEqual("SELECTED", result.layout_status)
        self.assertTrue(all(record["parser_status"] == "MARKET_UNAVAILABLE" for record in result.records if record["market"] == "SPF"))
        self.assertTrue(all(record["parser_status"] == "UNRESOLVED" for record in result.records if record["market"] == "HTFT"))
        self.assertTrue(all(record["market_availability_status"] == "AVAILABLE" for record in result.records if record["market"] == "HTFT"))

    def test_alias_precedence_missing_unknown_and_conflict(self):
        self.assertEqual("AVAILABLE", resolve_availability_aliases({"htft": "AVAILABLE", "half_full": "AVAILABLE"}).state)
        self.assertEqual("htft", resolve_availability_aliases({"htft": "AVAILABLE", "half_full": "AVAILABLE"}).selected_field)
        self.assertEqual("AVAILABLE", resolve_availability_aliases({"half_full": "AVAILABLE"}).state)
        self.assertEqual("UNKNOWN", resolve_availability_aliases({}).state)
        conflict = resolve_availability_aliases({"htft": "AVAILABLE", "half_full": "UNAVAILABLE"})
        self.assertEqual(("BLOCKED", "CONFLICT"), (conflict.state, conflict.status))

    def test_alias_runtime_is_bound_into_trace_config_and_conflict_fails_closed(self):
        first = build_full_trace(
            self.standard,
            artifact_identity="fixture://alias",
            source_width=440,
            source_height=982,
            contract=self.contract,
            market_availability_fields={"htft": "AVAILABLE"},
        )
        second = build_full_trace(
            self.standard,
            artifact_identity="fixture://alias",
            source_width=440,
            source_height=982,
            contract=self.contract,
            market_availability_fields={"half_full": "AVAILABLE"},
        )
        self.assertEqual(first.to_jsonl(), second.to_jsonl())
        conflict = build_full_trace(
            self.standard,
            artifact_identity="fixture://alias-conflict",
            source_width=440,
            source_height=982,
            contract=self.contract,
            market_availability_fields={"htft": "AVAILABLE", "half_full": "UNAVAILABLE"},
        )
        self.assertTrue(all(record["market_availability_status"] == "BLOCKED" for record in conflict.records if record["market"] == "HTFT"))

    def test_same_profile_and_config_are_deterministic_and_profile_change_changes_trace_identity(self):
        raw = self.standard
        first = build_full_trace(raw, artifact_identity="fixture://hash", source_width=440, source_height=982, contract=self.contract)
        second = build_full_trace(raw, artifact_identity="fixture://hash", source_width=440, source_height=982, contract=self.contract)
        self.assertEqual(first.to_jsonl(), second.to_jsonl())
        changed = copy.deepcopy(self.contract)
        changed["layout_profile_remediation"]["profiles"][0]["layout_profile_version"] = "1.1.1"
        changed["layout_profile_remediation"]["profiles"][0]["layout_profile_identity"] = "china-sports-lottery-official-standard@1.1.1"
        changed["layout_profile_registry"]["supported_profiles"][0] = changed["layout_profile_remediation"]["profiles"][0]
        changed["config_hash"] = "changed-for-test"
        third = build_full_trace(raw, artifact_identity="fixture://hash", source_width=440, source_height=982, contract=changed)
        self.assertNotEqual(first.records[0]["layout_profile_identity"], third.records[0]["layout_profile_identity"])
        self.assertNotEqual(first.records[0]["trace_record_sha256"], third.records[0]["trace_record_sha256"])


if __name__ == "__main__":
    unittest.main()
