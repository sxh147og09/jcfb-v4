"""Additive 1.1.0 multi-layout detection, geometry, and availability aliases.

This module is deliberately separate from the frozen 1.0.0 contract.  It can
load the additive profile registry, derive observable PNG section-bar
features, and feed the existing in-memory trace runtime without writing OCR
evidence or accepted odds values.
"""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from tools.migration_harness.common import sha256_json

from .contract import MARKETS, load_contract
from .layout import LayoutDetection, NormalizedRect, PixelRect


PROFILE_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "official_odds_cell_extraction" / "layout_profile_remediation_1_1_0.json"
REMEDIATION_IDENTITY = "official-odds-layout-profiles@1.1.0"
REMEDIATED_EXTRACTION_CONTRACT_IDENTITY = "official-odds-cell-extraction@1.1.0"


@dataclass(frozen=True)
class AvailabilityResolution:
    state: str
    status: str
    selected_field: Optional[str]
    observed_fields: tuple[str, ...]
    reason: str


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "canonical_hash"}
    return "sha256:" + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_profile_config(path: str | Path = PROFILE_CONFIG_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("$id") != REMEDIATION_IDENTITY or config.get("status") != "FROZEN_ADDITIVE":
        raise ValueError("layout remediation registry identity/status is invalid")
    if config.get("canonical_hash") not in {None, "PENDING_RUNTIME_CANONICAL_HASH"} and config["canonical_hash"] != _canonical_hash(config):
        raise ValueError("layout remediation registry canonical hash mismatch")
    if len(config.get("profiles", [])) != 2:
        raise ValueError("exactly two additive layout profiles are required")
    return config


def load_remediated_contract(path: str | Path = PROFILE_CONFIG_PATH) -> dict[str, Any]:
    """Return a 1.1.0 in-memory contract while leaving the frozen 1.0.0 file untouched."""

    base = load_contract()
    profile_config = load_profile_config(path)
    contract = copy.deepcopy(base)
    contract["$id"] = REMEDIATED_EXTRACTION_CONTRACT_IDENTITY
    contract["contract_version"] = REMEDIATED_EXTRACTION_CONTRACT_IDENTITY
    contract["status"] = "FROZEN_ADDITIVE"
    contract["schema_version"] = base["schema_version"]
    contract["layout_profile_registry"] = {
        "registry_identity": profile_config["$id"],
        "supported_profiles": profile_config["profiles"],
        "detector_contract": profile_config["detector_contract"],
        "locator": profile_config["locator"],
    }
    contract["layout_profile_remediation"] = profile_config
    contract["market_contract"]["source_field_mapping"]["HTFT"] = "htft"
    contract["market_contract"]["source_field_aliases"] = profile_config["schema_aliases"]
    contract["compatibility"] = {
        "base_extraction_contract": base["$id"],
        "base_trace_schema": base["schema_version"],
        "profile_registry_compatibility": profile_config["compatibility"],
        "supersedes": profile_config["supersedes"],
    }
    contract["config_hash"] = sha256_json({"layout_profile_registry": contract["layout_profile_registry"], "parser_contract": contract["parser_contract"], "source_field_aliases": contract["market_contract"]["source_field_aliases"]})
    contract["canonical_hash"] = _canonical_hash(contract)
    return contract


def _normalise_state(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("state", value.get("status"))
    if not isinstance(value, str):
        return "UNKNOWN"
    state = value.strip().upper()
    return state if state in {"AVAILABLE", "UNAVAILABLE", "UNKNOWN", "BLOCKED"} else "UNKNOWN"


def resolve_availability_aliases(
    fields: Optional[Mapping[str, Any]],
    *,
    canonical_field: str = "htft",
    legacy_aliases: tuple[str, ...] = ("half_full",),
) -> AvailabilityResolution:
    """Resolve HTFT coverage without collapsing missing, unknown, and unavailable."""

    if not isinstance(fields, Mapping):
        return AvailabilityResolution("UNKNOWN", "UNKNOWN", None, (), "COVERAGE_FIELDS_MISSING")
    observed = tuple(field for field in (canonical_field, *legacy_aliases) if field in fields)
    if not observed:
        return AvailabilityResolution("UNKNOWN", "UNKNOWN", None, (), "COVERAGE_FIELD_MISSING")
    states = {field: _normalise_state(fields[field]) for field in observed}
    if len(set(states.values())) > 1:
        return AvailabilityResolution("BLOCKED", "CONFLICT", None, observed, "CANONICAL_AND_LEGACY_ALIAS_CONFLICT")
    selected = canonical_field if canonical_field in states else observed[0]
    state = states[selected]
    return AvailabilityResolution(state, state, selected, observed, "CANONICAL_FIELD" if selected == canonical_field else "LEGACY_ALIAS_COMPATIBILITY")


def _png_rows(raw_png: bytes) -> tuple[int, int, list[bytes]]:
    if not isinstance(raw_png, bytes) or raw_png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("raw_image must be a PNG byte sequence")
    offset = 8
    idat = bytearray()
    width = height = bit_depth = color_type = None
    while offset < len(raw_png):
        length = struct.unpack(">I", raw_png[offset : offset + 4])[0]
        kind = raw_png[offset + 4 : offset + 8]
        chunk = raw_png[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8 or interlace != 0 or color_type not in {2, 6} or compression != 0 or filtering != 0:
                raise ValueError("only non-interlaced 8-bit RGB/RGBA PNGs are supported")
        elif kind == b"IDAT":
            idat.extend(chunk)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise ValueError("PNG IHDR is missing")
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    decoded = zlib.decompress(bytes(idat))
    rows: list[bytes] = []
    prior = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = decoded[cursor]
        cursor += 1
        current = bytearray(decoded[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = current[index - channels] if index >= channels else 0
            up = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 1:
                current[index] = (current[index] + left) & 255
            elif filter_type == 2:
                current[index] = (current[index] + up) & 255
            elif filter_type == 3:
                current[index] = (current[index] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
                current[index] = (current[index] + predictor) & 255
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter type: {filter_type}")
        rows.append(bytes(current))
        prior = current
    return width, height, rows


def extract_structural_features(raw_png: bytes) -> dict[str, Any]:
    """Extract only section-bar geometry; no OCR text or values are read."""

    width, height, rows = _png_rows(raw_png)
    channels = 3 if len(rows[0]) == width * 3 else 4
    spans: list[list[int]] = []
    in_run: Optional[int] = None
    for y, row in enumerate(rows):
        hits = 0
        for x in range(max(0, min(15, width)), min(425, width)):
            offset = x * channels
            r, g, b = row[offset : offset + 3]
            if r < 60 and g < 100 and b < 150 and b >= g >= r:
                hits += 1
        ratio = hits / max(1, min(425, width) - min(15, width))
        is_bar = ratio >= 0.80
        if is_bar and in_run is None:
            in_run = y
        if not is_bar and in_run is not None:
            if y - in_run >= 10:
                spans.append([in_run, y])
            in_run = None
    if in_run is not None and height - in_run >= 10:
        spans.append([in_run, height])
    return {
        "source_dimensions": {"width": width, "height": height},
        "dark_section_bar_spans": spans,
        "feature_hash": sha256_json({"source_dimensions": {"width": width, "height": height}, "dark_section_bar_spans": spans}),
    }


class RemediatedLayoutProfileRegistry:
    """Deterministic structural detector for the additive profile registry."""

    def __init__(self, contract: Optional[Mapping[str, Any]] = None):
        self.contract = dict(contract or load_remediated_contract())
        remediation = self.contract.get("layout_profile_remediation") or load_profile_config()
        self.config = remediation
        self.profiles = tuple(remediation["profiles"])
        self._profiles = {profile["layout_profile_id"]: profile for profile in self.profiles}

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def profile(self, profile_id: str) -> Mapping[str, Any]:
        if profile_id not in self._profiles:
            raise KeyError(profile_id)
        return self._profiles[profile_id]

    def detect(self, raw_image: Optional[bytes] = None, structural_features: Optional[Mapping[str, Any]] = None) -> LayoutDetection:
        features = dict(structural_features or (extract_structural_features(raw_image) if raw_image is not None else {}))
        dimensions = features.get("source_dimensions", {})
        candidates: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
        tolerance = int(self.config["detector_contract"].get("anchor_tolerance_pixels", 0))
        observed = features.get("dark_section_bar_spans", [])
        for profile in self.profiles:
            rules = profile["detector_rules"]
            expected_dimensions = rules["source_dimensions"]
            if dimensions.get("width") != expected_dimensions["width"] or dimensions.get("height") != expected_dimensions["height"]:
                continue
            expected_spans = list(rules["dark_section_bar_spans"].values())
            if len(observed) != len(expected_spans):
                continue
            if not all(
                abs(actual[0] - expected[0]) <= tolerance and abs(actual[1] - expected[1]) <= tolerance
                for actual, expected in zip(sorted(observed), sorted(expected_spans))
            ):
                continue
            evidence = {
                "feature_hash": features.get("feature_hash", sha256_json(features)),
                "source_dimensions": dimensions,
                "observed_dark_section_bar_spans": observed,
                "expected_dark_section_bar_spans": expected_spans,
                "market_presence": profile["market_presence"],
            }
            candidates.append((profile, evidence))
        if len(candidates) == 1:
            profile, evidence = candidates[0]
            regions = {market: profile["market_regions"][market] for market in MARKETS}
            return LayoutDetection("SELECTED", profile["layout_profile_id"], profile["layout_profile_version"], "UNIQUE_STRUCTURAL_PROFILE_MATCH", regions, evidence)
        if not candidates:
            return LayoutDetection("UNSUPPORTED_LAYOUT", "UNKNOWN", "UNKNOWN", "NO_PROFILE_MATCHED_STRUCTURAL_ANCHORS", {}, {"features": features})
        return LayoutDetection("AMBIGUOUS_LAYOUT", "AMBIGUOUS", "UNKNOWN", "MULTIPLE_PROFILES_MATCH_STRUCTURAL_ANCHORS", {}, {"matched_profile_ids": [item[0]["layout_profile_id"] for item in candidates], "features": features})


class RemediatedCellLocatorRegistry:
    """Projects explicit profile rectangles while reusing the frozen inventory order."""

    def __init__(self, contract: Optional[Mapping[str, Any]] = None):
        self.contract = dict(contract or load_remediated_contract())
        self.layout_registry = RemediatedLayoutProfileRegistry(self.contract)
        self._inventories = self.contract["market_contract"]["inventories"]

    def inventory(self, market: str) -> tuple[Mapping[str, Any], ...]:
        if market not in MARKETS:
            raise KeyError(market)
        return tuple(self._inventories[market])

    def locate(self, profile_id: str, market: str, source_visible_label: str, width: int, height: int) -> dict[str, Any]:
        profile = self.layout_registry.profile(profile_id)
        expected_dimensions = profile["detector_rules"]["source_dimensions"]
        if (width, height) != (expected_dimensions["width"], expected_dimensions["height"]):
            raise ValueError("source dimensions do not match the frozen profile dimension policy")
        item = next((candidate for candidate in self.inventory(market) if candidate["source_visible_label"] == source_visible_label), None)
        if item is None:
            raise KeyError(f"unknown cell: {market}/{source_visible_label}")
        index = item["ordering_index"]
        pixel_geometry = profile["cell_geometry_pixels"][market][index]
        region = profile["market_regions"][market]
        region_rect = NormalizedRect(region["left"] / width, region["top"] / height, region["right"] / width, region["bottom"] / height)
        cell_rect = None if pixel_geometry is None else NormalizedRect(pixel_geometry[0] / width, pixel_geometry[1] / height, pixel_geometry[2] / width, pixel_geometry[3] / height)
        return {
            "locator_version": profile["locator_version"],
            "locator_key": f"{profile['layout_profile_identity']}|{market}|{item['source_visible_label']}|{profile['locator_version']}",
            "layout_profile_id": profile["layout_profile_id"],
            "layout_profile_version": profile["layout_profile_version"],
            "market": market,
            "source_visible_label": source_visible_label,
            "canonical_outcome_label": item["canonical_outcome_label"],
            "ordering_index": index,
            "row": item["row"],
            "column": item["column"],
            "region_coordinates": region_rect.to_dict(),
            "cell_coordinates": cell_rect.to_dict() if cell_rect else None,
            "region_pixel_coordinates": region_rect.project(width, height).to_dict(),
            "cell_pixel_coordinates": pixel_geometry,
            "geometry_status": "READY" if pixel_geometry else "MARKET_UNAVAILABLE",
        }

    @staticmethod
    def unsupported_locator(profile_id: str, market: str, item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "locator_version": "official-odds-grid-locator@1.1.0",
            "locator_key": f"{profile_id}|{market}|{item['source_visible_label']}|official-odds-grid-locator@1.1.0",
            "layout_profile_id": profile_id,
            "layout_profile_version": "UNKNOWN",
            "market": market,
            "source_visible_label": item["source_visible_label"],
            "canonical_outcome_label": item["canonical_outcome_label"],
            "ordering_index": item["ordering_index"],
            "row": item["row"],
            "column": item["column"],
            "region_coordinates": None,
            "cell_coordinates": None,
            "region_pixel_coordinates": None,
            "cell_pixel_coordinates": None,
            "geometry_status": "UNSUPPORTED_LAYOUT",
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        for profile in self.layout_registry.profiles:
            for market in MARKETS:
                cells = profile["cell_geometry_pixels"].get(market, [])
                if len(cells) != len(self.inventory(market)):
                    errors.append(f"{profile['layout_profile_id']}/{market}: inventory geometry count mismatch")
                region = profile["market_regions"][market]
                if not region.get("geometry_supported", True):
                    if any(cell is not None for cell in cells):
                        errors.append(f"{profile['layout_profile_id']}/{market}: unavailable market has geometry")
                    continue
                bounds = (region["left"], region["top"], region["right"], region["bottom"])
                rectangles = [tuple(cell) for cell in cells if cell is not None]
                for left, top, right, bottom in rectangles:
                    if not (bounds[0] <= left < right <= bounds[2] and bounds[1] <= top < bottom <= bounds[3]):
                        errors.append(f"{profile['layout_profile_id']}/{market}: cell outside market region")
                for first_index, first in enumerate(rectangles):
                    for second in rectangles[first_index + 1 :]:
                        overlap_width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
                        overlap_height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
                        if overlap_width > 0 and overlap_height > 0:
                            errors.append(f"{profile['layout_profile_id']}/{market}: cell rectangles overlap")
        return errors
