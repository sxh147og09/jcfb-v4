"""Load and validate the frozen official odds cell extraction contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tools.migration_harness.common import sha256_json


CONTRACT_IDENTITY = "official-odds-cell-extraction@1.0.0"
TRACE_SCHEMA_IDENTITY = "official-odds-cell-trace@1.0.0"
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "official_odds_cell_extraction" / "official_odds_cell_extraction_contract.json"
MARKETS = ("SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HTFT")
STATUSES = frozenset({"PARSED", "UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "MARKET_UNAVAILABLE", "CONFLICT", "UNSUPPORTED_LAYOUT"})
UNRESOLVED_STATUSES = frozenset({"UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "MARKET_UNAVAILABLE", "CONFLICT", "UNSUPPORTED_LAYOUT"})


class ContractValidationError(ValueError):
    """The frozen contract cannot safely drive the runtime."""


def load_contract(path: str | Path = CONTRACT_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        contract = json.load(handle)
    validate_contract(contract)
    return contract


def _required(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ContractValidationError(f"contract field missing: {key}")
    return mapping[key]


def validate_contract(contract: Mapping[str, Any]) -> None:
    if not isinstance(contract, Mapping):
        raise ContractValidationError("contract must be an object")
    if contract.get("$id") != CONTRACT_IDENTITY or contract.get("contract_version") != CONTRACT_IDENTITY:
        raise ContractValidationError("contract identity/version mismatch")
    if contract.get("schema_version") != TRACE_SCHEMA_IDENTITY or contract.get("status") != "FROZEN":
        raise ContractValidationError("contract schema or lifecycle is not frozen")
    source = _required(contract, "source")
    if source.get("source_type") != "OFFICIAL_SCREENSHOT" or source.get("raw_bytes_are_immutable") is not True:
        raise ContractValidationError("source boundary is not official and immutable")
    coordinates = _required(contract, "coordinate_contract")
    if coordinates.get("system") != "NORMALIZED_SOURCE_PIXEL_PROJECTION":
        raise ContractValidationError("coordinate system is not governed")
    layout_registry = _required(contract, "layout_profile_registry")
    profiles = layout_registry.get("supported_profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ContractValidationError("at least one supported layout profile is required")
    profile_ids = {item.get("layout_profile_id") for item in profiles}
    if len(profile_ids) != len(profiles) or None in profile_ids:
        raise ContractValidationError("layout profile identities must be unique")
    market_contract = _required(contract, "market_contract")
    if tuple(market_contract.get("market_key_order", ())) != MARKETS:
        raise ContractValidationError("market order must cover the five official markets")
    inventories = _required(market_contract, "inventories")
    for market in MARKETS:
        items = inventories.get(market)
        if not isinstance(items, list) or not items:
            raise ContractValidationError(f"inventory missing: {market}")
        if [item.get("ordering_index") for item in items] != list(range(len(items))):
            raise ContractValidationError(f"inventory order is not contiguous: {market}")
        if len({item.get("source_visible_label") for item in items}) != len(items):
            raise ContractValidationError(f"inventory labels are not unique: {market}")
        for item in items:
            if not isinstance(item.get("canonical_outcome_label"), str) or not isinstance(item.get("value_kind"), str):
                raise ContractValidationError(f"inventory identity is incomplete: {market}")
    parser = _required(contract, "parser_contract")
    if parser.get("implementation_identity") != "official-odds-cell-parser" or parser.get("implementation_version") != "1.0.0":
        raise ContractValidationError("parser implementation identity/version mismatch")
    if set(parser.get("status_vocabulary", ())) != STATUSES or not set(parser.get("unresolved_statuses", ())).issubset(STATUSES):
        raise ContractValidationError("parser status vocabulary is incomplete")
    trace = _required(contract, "trace_record_contract")
    required_fields = trace.get("required_fields")
    if not isinstance(required_fields, list) or "trace_record_sha256" not in required_fields:
        raise ContractValidationError("trace record required fields are incomplete")
    hashing = _required(contract, "trace_hash_contract")
    if hashing.get("algorithm") != "SHA-256" or hashing.get("profile") != "v4-canonical-json@1.0":
        raise ContractValidationError("trace hash profile is not governed")
    included = set(hashing.get("included_fields", ()))
    if "trace_record_sha256" in included or set(required_fields) - {"trace_record_sha256"} != included:
        raise ContractValidationError("trace hash boundary does not cover required fields exactly")
    derivation = _required(contract, "unresolved_derivation")
    if derivation.get("post_hoc_baseline_fitting") is not False or derivation.get("input") != "full_cell_trace_in_contract_order":
        raise ContractValidationError("unresolved derivation is not mechanical")
    safety = _required(contract, "safety_boundary")
    for key in ("accepted_official_odds_payload_write", "historical_source_archive_write", "archive_record_or_revision_write", "r002_package_generation", "ewp002_rerun", "ewp003_rerun", "ewp005_execution_authorized", "model_fit_or_promotion", "v333_modification"):
        if safety.get(key) is not False:
            raise ContractValidationError(f"safety boundary leaked: {key}")


def parser_config_hash(contract: Mapping[str, Any]) -> str:
    """Hash only the effective layout/parser configuration, never volatile metadata."""

    return sha256_json({"layout_profile_registry": contract["layout_profile_registry"], "parser_contract": contract["parser_contract"]})
