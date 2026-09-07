"""Versioned layout profiles and deterministic normalized-to-pixel locators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .contract import MARKETS, load_contract


LOCATOR_VERSION = "official-odds-grid-locator@1.0.0"


@dataclass(frozen=True)
class NormalizedRect:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
            raise ValueError("normalized coordinates must be finite and within [0, 1]")
        if not self.left < self.right or not self.top < self.bottom:
            raise ValueError("rectangle must have positive area")

    def to_dict(self) -> dict[str, float]:
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom}

    def project(self, width: int, height: int) -> "PixelRect":
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ValueError("source dimensions must be positive integers")
        return PixelRect(
            left=math.floor(self.left * width),
            top=math.floor(self.top * height),
            right=math.ceil(self.right * width),
            bottom=math.ceil(self.bottom * height),
        )


@dataclass(frozen=True)
class PixelRect:
    left: int
    top: int
    right: int
    bottom: int

    def to_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom}


@dataclass(frozen=True)
class LayoutDetection:
    status: str
    profile_id: str
    profile_version: str
    reason: str
    region_rects: Mapping[str, NormalizedRect]


def _rect(raw: Mapping[str, Any]) -> NormalizedRect:
    return NormalizedRect(float(raw["left"]), float(raw["top"]), float(raw["right"]), float(raw["bottom"]))


class LayoutProfileRegistry:
    """Exact-match layout registry; it intentionally contains no heuristic fallback."""

    def __init__(self, contract: Optional[Mapping[str, Any]] = None):
        self.contract = dict(contract or load_contract())
        self._profiles = {item["layout_profile_id"]: item for item in self.contract["layout_profile_registry"]["supported_profiles"]}

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def detect(self, profile_id: Optional[str], regions: Optional[Mapping[str, Mapping[str, Any]]]) -> LayoutDetection:
        if profile_id not in self._profiles:
            return LayoutDetection("UNSUPPORTED_LAYOUT", profile_id or "UNKNOWN", "UNKNOWN", "PROFILE_ID_NOT_REGISTERED", {})
        profile = self._profiles[profile_id]
        expected_raw = profile["market_regions"]
        if not isinstance(regions, Mapping) or set(regions) != set(MARKETS):
            return LayoutDetection("UNSUPPORTED_LAYOUT", profile_id, profile["layout_profile_version"], "MARKET_REGION_ANCHORS_INCOMPLETE", {})
        expected = {market: _rect(expected_raw[market]) for market in MARKETS}
        try:
            actual = {market: _rect(regions[market]) for market in MARKETS}
        except (KeyError, TypeError, ValueError):
            return LayoutDetection("UNSUPPORTED_LAYOUT", profile_id, profile["layout_profile_version"], "MARKET_REGION_ANCHORS_INVALID", {})
        if any(actual[market] != expected[market] for market in MARKETS):
            return LayoutDetection("UNSUPPORTED_LAYOUT", profile_id, profile["layout_profile_version"], "MARKET_REGION_ANCHORS_MISMATCH", {})
        return LayoutDetection("MATCHED", profile_id, profile["layout_profile_version"], "EXACT_PROFILE_MATCH", actual)

    def profile(self, profile_id: str) -> Mapping[str, Any]:
        if profile_id not in self._profiles:
            raise KeyError(profile_id)
        return self._profiles[profile_id]


class CellLocatorRegistry:
    """Derives every cell rectangle from profile, market, row, and column only."""

    def __init__(self, contract: Optional[Mapping[str, Any]] = None):
        self.contract = dict(contract or load_contract())
        self.layout_registry = LayoutProfileRegistry(self.contract)
        self._inventories = self.contract["market_contract"]["inventories"]

    def inventory(self, market: str) -> tuple[Mapping[str, Any], ...]:
        if market not in MARKETS:
            raise KeyError(market)
        return tuple(self._inventories[market])

    def locate(self, profile_id: str, market: str, source_visible_label: str, width: int, height: int) -> dict[str, Any]:
        profile = self.layout_registry.profile(profile_id)
        item = next((candidate for candidate in self.inventory(market) if candidate["source_visible_label"] == source_visible_label), None)
        if item is None:
            raise KeyError(f"unknown cell: {market}/{source_visible_label}")
        region = _rect(profile["market_regions"][market])
        rows = int(profile["market_regions"][market]["grid_rows"])
        columns = int(profile["market_regions"][market]["grid_columns"])
        if item["row"] >= rows or item["column"] >= columns:
            raise ValueError(f"cell exceeds profile grid: {market}/{source_visible_label}")
        cell_width = (region.right - region.left) / columns
        cell_height = (region.bottom - region.top) / rows
        cell = NormalizedRect(
            round(region.left + item["column"] * cell_width, 6),
            round(region.top + item["row"] * cell_height, 6),
            round(region.left + (item["column"] + 1) * cell_width, 6),
            round(region.top + (item["row"] + 1) * cell_height, 6),
        )
        return {
            "locator_version": LOCATOR_VERSION,
            "locator_key": f"{profile_id}|{market}|{source_visible_label}|{LOCATOR_VERSION}",
            "layout_profile_id": profile_id,
            "layout_profile_version": profile["layout_profile_version"],
            "market": market,
            "source_visible_label": source_visible_label,
            "ordering_index": item["ordering_index"],
            "row": item["row"],
            "column": item["column"],
            "region_coordinates": region.to_dict(),
            "cell_coordinates": cell.to_dict(),
            "region_pixel_coordinates": region.project(width, height).to_dict(),
            "cell_pixel_coordinates": cell.project(width, height).to_dict(),
        }

    @staticmethod
    def unsupported_locator(profile_id: str, market: str, item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "locator_version": LOCATOR_VERSION,
            "locator_key": f"{profile_id}|{market}|{item['source_visible_label']}|{LOCATOR_VERSION}",
            "layout_profile_id": profile_id,
            "layout_profile_version": "UNKNOWN",
            "market": market,
            "source_visible_label": item["source_visible_label"],
            "ordering_index": item["ordering_index"],
            "row": item["row"],
            "column": item["column"],
            "region_coordinates": None,
            "cell_coordinates": None,
            "region_pixel_coordinates": None,
            "cell_pixel_coordinates": None,
        }
