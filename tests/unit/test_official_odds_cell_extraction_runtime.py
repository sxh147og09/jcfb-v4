from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from src.official_odds_cells import (
    CellLocatorRegistry,
    LayoutProfileRegistry,
    ParserStatus,
    build_full_trace,
    derive_unresolved_trace,
    load_contract,
    trace_record_hash,
    validate_contract,
)


class OfficialOddsCellExtractionRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.contract = load_contract()
        cls.profile = cls.contract["layout_profile_registry"]["supported_profiles"][0]
        cls.regions = cls.profile["market_regions"]

    def build(self, **kwargs):
        defaults = {
            "raw_image": b"synthetic-official-odds-screenshot-v1",
            "artifact_identity": "fixture://official-odds-cell/001",
            "source_width": 1000,
            "source_height": 2000,
            "layout_profile_id": self.profile["layout_profile_id"],
            "layout_regions": self.regions,
        }
        defaults.update(kwargs)
        return build_full_trace(**defaults)

    def test_contract_is_frozen_and_complete(self):
        validate_contract(self.contract)
        self.assertEqual("official-odds-cell-extraction@1.0.0", self.contract["$id"])
        self.assertEqual(["SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HTFT"], self.contract["market_contract"]["market_key_order"])
        self.assertEqual({"SPF": 3, "RQSPF": 4, "TOTAL_GOALS": 8, "EXACT_SCORE": 31, "HTFT": 9}, {market: len(items) for market, items in self.contract["market_contract"]["inventories"].items()})

    def test_locator_is_unique_and_projects_normalized_coordinates(self):
        registry = CellLocatorRegistry(self.contract)
        keys = []
        for market in self.contract["market_contract"]["market_key_order"]:
            for item in registry.inventory(market):
                locator = registry.locate(self.profile["layout_profile_id"], market, item["source_visible_label"], 1000, 2000)
                keys.append(locator["locator_key"])
                self.assertIsNotNone(locator["cell_pixel_coordinates"])
        self.assertEqual(55, len(keys))
        self.assertEqual(55, len(set(keys)))

    def test_unsupported_layout_fails_closed_without_guessing(self):
        result = self.build(layout_profile_id="unknown-profile", layout_regions=self.regions)
        self.assertEqual("UNSUPPORTED_LAYOUT", result.layout_status)
        self.assertEqual(55, len(result.records))
        self.assertTrue(all(item["parser_status"] == ParserStatus.UNSUPPORTED_LAYOUT.value for item in result.records))
        self.assertEqual(55, len(result.unresolved_records))
        self.assertTrue(all(item["cell_coordinates"] is None for item in result.records))

    def test_clean_ocr_value_is_parsed_without_creating_an_odds_payload(self):
        result = self.build(evidence={("SPF", "胜"): {"raw_text": "２．１０", "confidence": 0.99}})
        record = next(item for item in result.records if item["market"] == "SPF" and item["source_visible_label"] == "胜")
        self.assertEqual("PARSED", record["parser_status"])
        self.assertEqual(2.10, record["parsed_value"])
        self.assertEqual("2.10", record["ocr_evidence"]["normalized_text"])
        self.assertNotIn("official_odds_payload", record)

    def test_blur_ambiguous_missing_and_conflict_are_distinct(self):
        evidence = {
            ("TOTAL_GOALS", "0"): {"raw_text": "?"},
            ("TOTAL_GOALS", "1"): {"raw_text": "3.20", "candidate_values": [3.20, 8.20]},
            ("TOTAL_GOALS", "2"): {"raw_text": "3.20", "contradiction_state": "CONFLICTED"},
        }
        result = self.build(evidence=evidence, cell_presence={("TOTAL_GOALS", "3"): False})
        status = {(item["source_visible_label"]): item["parser_status"] for item in result.records if item["market"] == "TOTAL_GOALS"}
        self.assertEqual("UNRESOLVED", status["0"])
        self.assertEqual("AMBIGUOUS", status["1"])
        self.assertEqual("CONFLICT", status["2"])
        self.assertEqual("NOT_PRESENT", status["3"])

    def test_market_unavailable_is_explicit_for_every_cell(self):
        result = self.build(market_availability={"HTFT": "UNAVAILABLE"})
        htft = [item for item in result.records if item["market"] == "HTFT"]
        self.assertEqual(9, len(htft))
        self.assertTrue(all(item["parser_status"] == "MARKET_UNAVAILABLE" for item in htft))
        self.assertTrue(all(item["market_availability_status"] == "UNAVAILABLE" for item in htft))

    def test_full_trace_and_unresolved_trace_are_mechanical(self):
        result = self.build(evidence={("SPF", "胜"): {"raw_text": "2.10"}, ("SPF", "平"): {"raw_text": "?"}})
        unresolved = derive_unresolved_trace(result.records)
        self.assertEqual([item["trace_record_id"] for item in unresolved], [item["trace_record_id"] for item in result.records if item["parser_status"] in {"UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "MARKET_UNAVAILABLE", "CONFLICT", "UNSUPPORTED_LAYOUT"}])
        self.assertEqual(54, len(unresolved))
        self.assertNotIn('"baseline"', json.dumps(unresolved))

    def test_same_input_replays_byte_and_hash_identically(self):
        first = self.build(evidence={("EXACT_SCORE", "1:0"): {"raw_text": "7.50"}})
        second = self.build(evidence={("EXACT_SCORE", "1:0"): {"raw_text": "7.50"}})
        self.assertEqual(first.to_jsonl(), second.to_jsonl())
        self.assertEqual([item["trace_record_sha256"] for item in first.records], [item["trace_record_sha256"] for item in second.records])
        self.assertTrue(all(trace_record_hash(item) == item["trace_record_sha256"] for item in first.records))

    def test_parser_config_change_changes_trace_identity_hash(self):
        changed = copy.deepcopy(self.contract)
        changed["parser_contract"]["config_identity"] = "official-odds-cell-parser-config@1.0.1"
        first = self.build(evidence={("SPF", "胜"): {"raw_text": "2.10"}})
        second = self.build(contract=changed, evidence={("SPF", "胜"): {"raw_text": "2.10"}})
        first_record = next(item for item in first.records if item["market"] == "SPF" and item["source_visible_label"] == "胜")
        second_record = next(item for item in second.records if item["market"] == "SPF" and item["source_visible_label"] == "胜")
        self.assertNotEqual(first_record["parser_config_hash"], second_record["parser_config_hash"])
        self.assertNotEqual(first_record["trace_record_sha256"], second_record["trace_record_sha256"])

    def test_unknown_timestamps_are_not_fabricated(self):
        result = self.build()
        self.assertEqual({"source_timestamp": "UNKNOWN", "captured_at": "UNKNOWN", "observed_at": "UNKNOWN", "ingested_at": "UNKNOWN"}, result.records[0]["source_timestamps"])


if __name__ == "__main__":
    unittest.main()
