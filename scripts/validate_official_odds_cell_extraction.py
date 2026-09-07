"""Focused validator for B15-EWP-006 official screenshot cell extraction."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "official_odds_cell_extraction"
TRAINING_CONFIG = ROOT / "config" / "prediction_training"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MARKETS = ("SPF", "RQSPF", "TOTAL_GOALS", "EXACT_SCORE", "HTFT")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def self_hash(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("canonical_hash", None)
    return "sha256:" + hashlib.sha256(canonical(payload)).hexdigest()


def validate() -> list[str]:
    failures: list[str] = []
    contract = load(CONFIG / "official_odds_cell_extraction_contract.json")
    schema = load(CONFIG / "official_odds_cell_trace_schema.json")
    amendment = load(TRAINING_CONFIG / "v4_batch15_architecture_amendment_registry.json")
    base = load(TRAINING_CONFIG / "v4_batch15_execution_work_package_registry.json")
    if contract.get("$id") != "official-odds-cell-extraction@1.0.0" or contract.get("status") != "FROZEN":
        failures.append("contract identity/status is not frozen")
    if contract.get("config_hash") != self_config_hash(contract):
        failures.append("contract config_hash does not match effective layout/parser configuration")
    if contract.get("canonical_hash") != self_hash(contract):
        failures.append("contract canonical_hash mismatch")
    if schema.get("$id") != contract.get("schema_version") or schema.get("additionalProperties") is not False:
        failures.append("trace schema identity or strictness is invalid")
    inventories = contract.get("market_contract", {}).get("inventories", {})
    expected_counts = {"SPF": 3, "RQSPF": 4, "TOTAL_GOALS": 8, "EXACT_SCORE": 31, "HTFT": 9}
    if set(inventories) != set(MARKETS) or {market: len(inventories.get(market, [])) for market in MARKETS} != expected_counts:
        failures.append("complete market cell inventories are not frozen")
    for market in MARKETS:
        items = inventories.get(market, [])
        if [item.get("ordering_index") for item in items] != list(range(len(items))):
            failures.append(f"inventory ordering invalid: {market}")
        if len({item.get("source_visible_label") for item in items}) != len(items):
            failures.append(f"inventory uniqueness invalid: {market}")
    parser = contract.get("parser_contract", {})
    if set(parser.get("status_vocabulary", [])) != {"PARSED", "UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "MARKET_UNAVAILABLE", "CONFLICT", "UNSUPPORTED_LAYOUT"}:
        failures.append("parser status vocabulary is incomplete")
    if set(parser.get("unresolved_statuses", [])) != {"UNRESOLVED", "AMBIGUOUS", "NOT_PRESENT", "MARKET_UNAVAILABLE", "CONFLICT", "UNSUPPORTED_LAYOUT"}:
        failures.append("unresolved derivation status set is not deterministic")
    included = set(contract.get("trace_hash_contract", {}).get("included_fields", []))
    required = set(contract.get("trace_record_contract", {}).get("required_fields", []))
    if "trace_record_sha256" in included or required - {"trace_record_sha256"} != included:
        failures.append("trace hash canonical boundary is incomplete")
    if amendment.get("base_registry_unchanged") is not True or amendment.get("base_registry_hash") != base.get("canonical_hash"):
        failures.append("architecture amendment is not bound to immutable active registry")
    if amendment.get("canonical_hash") != self_hash(amendment):
        failures.append("architecture amendment canonical_hash mismatch")
    package = amendment.get("work_package", {})
    if package.get("work_package_id") != "B15-EWP-006" or package.get("sequence") != 6 or package.get("dependencies") != ["B15-EWP-001"]:
        failures.append("EWP-006 identity/dependency is not deterministic")
    if package.get("execution_authorized") is not True or package.get("status") != "COMPLETE":
        failures.append("EWP-006 is not authorized/completed for its declared implementation scope")
    if package.get("canonical_hash") and package.get("canonical_hash") != self_hash(package):
        failures.append("embedded package canonical hash mismatch")
    boundary = package.get("authorization_boundary", {})
    for key in ("historical_replay", "accepted_odds_payload_write", "archive_write", "r002_generation", "ewp002_rerun", "ewp003_rerun", "ewp005_execution_authorized", "v333_modification"):
        if boundary.get(key) is not False:
            failures.append(f"EWP-006 authorization leaked: {key}")
    archive_root = ROOT / "approved_data" / "historical_source_archive"
    if archive_root.exists() and any(path.is_file() for path in archive_root.rglob("*")):
        failures.append("historical source archive contains files")
    if any(path.is_file() and path.suffix.lower() == ".zip" and "r002" in path.name.casefold() for path in (ROOT / "approved_data").rglob("*")):
        failures.append("r002 ZIP detected")
    if ROOT.drive.upper() != "F:":
        failures.append("F-drive boundary is not active")
    try:
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        failures.append(f"git boundary audit unavailable: {exc}")
        changed = []
    if any("v333" in path.casefold() or "v3.3.3" in path.casefold() for path in changed):
        failures.append("V3.3.3 path changed")
    if any(path.startswith("database/migrations/") for path in changed):
        failures.append("migration path changed")
    return failures


def self_config_hash(contract: dict[str, Any]) -> str:
    payload = {"layout_profile_registry": contract["layout_profile_registry"], "parser_contract": contract["parser_contract"]}
    return "sha256:" + hashlib.sha256(canonical(payload)).hexdigest()


if __name__ == "__main__":
    errors = validate()
    if errors:
        print("OFFICIAL ODDS CELL EXTRACTION VALIDATION: FAIL")
        print("\n".join(errors))
        sys.exit(1)
    print("OFFICIAL ODDS CELL EXTRACTION VALIDATION: PASS")
    print("EWP-006 implementation scope: COMPLETE")
    print("Historical full replay: NOT_EXECUTED")
    print("Accepted odds/archive/r002/model/V3 actions: NOT_AUTHORIZED")
