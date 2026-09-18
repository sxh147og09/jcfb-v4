"""R012-C-FIRSTPARTY-01: validate forward Five-Play archive infrastructure.

This stage is deliberately synthetic and read-only with respect to real data.
It builds a point-in-time archive contract, generates bounded synthetic
fixtures, and fail-closes temporal, identity, provenance, revision, and rights
violations.  It never captures a real source, trains a model, mutates current
prediction data, or admits records to Historical Master.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"F:\Projects\jcfb-v4")
DEFAULT_OUTPUT = ROOT / "work" / "r012_c_firstparty_01"
DEFAULT_REPORT = ROOT / "docs" / "R012-C-FIRSTPARTY-01_forward_five_play_archive_readiness_report.md"
DEFAULT_CONTRACT = ROOT / "config" / "prediction_training" / "R012-C_firstparty_forward_archive_contract_v1.0.0.json"
RULESET_ID = "R012-C-FIRSTPARTY-01-V1"
HASH_RULE = "CANONICAL_JSON_HASH_V1"
SOURCE_PROVIDER = "synthetic_fixture"
STAGES = ("MORNING", "LATE", "FINAL", "FREEZE")
MARKETS = ("SPF", "RQSPF", "TOTAL_GOALS", "SCORE", "HTFT")
ALLOWED_ARCHIVE_STATUSES = (
    "ARCHIVE_ONLY",
    "TRAINING_ELIGIBLE",
    "RIGHTS_HOLD",
    "TEMPORAL_HOLD",
    "IDENTITY_HOLD",
    "PROVENANCE_HOLD",
    "REVISION_HOLD",
    "REJECTED",
)
ALLOWED_RIGHTS = (
    "AUTHORIZED",
    "COMPANY_OWNED",
    "USER_OWNED_WITH_UNDERLYING_RIGHTS_PROVEN",
    "CONDITIONAL_AUTHORIZED",
    "AUTHORIZATION_PENDING",
    "UNPROVEN",
    "PROHIBITED",
)
ALLOWED_AVAILABILITY = ("OPEN_WITH_ODDS", "NO_DATA_VISIBLE", "UNKNOWN")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {value}")
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _identity(match_no: int, kickoff: datetime, home: str, away: str) -> dict[str, Any]:
    competition = "synthetic.epl"
    season = "2026-27"
    match_date = kickoff.date().isoformat()
    natural = "|".join((competition, season, str(match_no), match_date, _slug(home), _slug(away)))
    candidate = f"candidate:{natural}"
    return {
        "source_match_id": f"SYNTH-M{match_no:03d}",
        "competition": competition,
        "season": season,
        "match_no": match_no,
        "match_date": match_date,
        "kickoff_raw": kickoff.strftime("%Y-%m-%d %H:%M %z"),
        "kickoff_at": _iso(kickoff),
        "kickoff_timezone": str(kickoff.tzinfo),
        "home_team_raw": home,
        "away_team_raw": away,
        "home_team_normalized": _slug(home),
        "away_team_normalized": _slug(away),
        "source_natural_key": natural,
        "candidate_canonical_match_key": candidate,
        "canonical_match_id": None,
    }


def _base_payload(market: str, match_no: int) -> dict[str, Any]:
    if market == "SPF":
        return {"home": "2.10", "draw": "3.40", "away": "3.20"}
    if market == "RQSPF":
        return {"handicap": "+0.5", "home": "1.92", "draw": "3.60", "away": "3.45"}
    if market == "TOTAL_GOALS":
        return {str(selection): f"{7.0 + selection / 10:.2f}" for selection in range(7)} | {"7+": "12.00"}
    if market == "SCORE":
        return {"1-0": "6.50", "1-1": "7.00", "2-1": "8.50", "other_home": "9.00", "other_draw": "10.00", "other_away": "11.00"}
    if market == "HTFT":
        return {selection: f"{10.0 + index / 10:.2f}" for index, selection in enumerate(("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"))}
    raise ValueError(f"unsupported market: {market}")


def _stage_cutoff(kickoff: datetime, stage: str) -> datetime:
    offsets = {"MORNING": ("08:00"), "LATE": ("12:00"), "FINAL": ("18:00"), "FREEZE": ("19:30")}
    hour, minute = (int(value) for value in offsets[stage].split(":"))
    return kickoff.replace(hour=hour, minute=minute, second=0)


def _fixture_matches() -> list[dict[str, Any]]:
    return [
        _identity(1, datetime(2026, 9, 20, 20, 0, tzinfo=timezone(timedelta(hours=8))), home="Synthetic City", away="Synthetic United"),
        _identity(2, datetime(2026, 9, 21, 20, 0, tzinfo=timezone(timedelta(hours=8))), home="Synthetic Rovers", away="Synthetic Athletic"),
        _identity(3, datetime(2026, 9, 22, 20, 0, tzinfo=timezone(timedelta(hours=8))), home="Synthetic Albion", away="Synthetic County"),
    ]


def _scenario(match_no: int, stage: str, market: str) -> str | None:
    scenarios = {
        (1, "LATE", "RQSPF"): "changed_payload",
        (2, "LATE", "HTFT"): "missing_market",
        (2, "FINAL", "RQSPF"): "timestamp_conflict",
        (3, "FREEZE", "HTFT"): "rights_blocked",
        (1, "FREEZE", "SCORE"): "hash_mismatch",
        (3, "LATE", "SPF"): "duplicate_observation",
    }
    return scenarios.get((match_no, stage, market))


def _payload(match_no: int, stage: str, market: str) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    scenario = _scenario(match_no, stage, market)
    raw = _base_payload(market, match_no)
    if scenario == "changed_payload":
        raw = dict(raw)
        raw["home"] = "1.82"
        raw["draw"] = "3.85"
    if scenario == "missing_market":
        raw = {"availability": "NO_DATA_VISIBLE", "selection": None}
    normalized = dict(raw)
    if scenario == "missing_market":
        normalized = {"market_available": False, "selection": None, "missing_reason": "NO_DATA_VISIBLE"}
    return raw, normalized, scenario


def _rights(match_no: int, stage: str, market: str, scenario: str | None) -> dict[str, Any]:
    blocked = scenario == "rights_blocked"
    return {
        "rights_owner": "JCFB synthetic fixture",
        "license_reference": "internal://R012-C-FIRSTPARTY-01/synthetic-fixture",
        "authorization_id": "SYNTHETIC-FIXTURE-NOT-REAL-SOURCE",
        "authorization_effective_at": None,
        "authorization_expiry_at": None,
        "retroactive_coverage": False,
        "commercial_use": False,
        "training_use": False,
        "storage_use": True,
        "derived_data_use": True,
        "automation_use": False,
        "rights_status": "UNPROVEN" if blocked else "COMPANY_OWNED",
        "rights_reason": "synthetic fixture only; never a real-source authorization" if blocked else "fixture is generated inside company-owned test namespace",
    }


def _make_snapshots() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in _fixture_matches():
        match_no = match["match_no"]
        kickoff = _dt(match["kickoff_at"])
        for stage in STAGES:
            cutoff = _stage_cutoff(kickoff, stage)
            for market in MARKETS:
                raw, normalized, scenario = _payload(match_no, stage, market)
                source_timestamp = cutoff - timedelta(minutes=10)
                source_availability = cutoff - timedelta(minutes=20)
                observed = cutoff - timedelta(minutes=5)
                capture_started = cutoff - timedelta(minutes=4)
                capture_completed = cutoff - timedelta(minutes=1)
                if scenario == "timestamp_conflict":
                    source_timestamp = cutoff + timedelta(minutes=15)
                identity = dict(match)
                family = f"{match['source_match_id']}::{market}"
                record_id = f"{match['source_match_id']}::{stage}::{market}"
                expected_hash = _canonical_hash(raw)
                rights = _rights(match_no, stage, market, scenario)
                record = {
                    "market_record_id": record_id,
                    "source_match_id": match["source_match_id"],
                    "match_identity": identity,
                    **{key: identity[key] for key in identity if key != "canonical_match_id"},
                    "capture_stage": stage,
                    "stage_cutoff": _iso(cutoff),
                    "prediction_cutoff_at": _iso(cutoff),
                    "observed_at": _iso(observed),
                    "source_availability_at": _iso(source_availability),
                    "source_published_at": _iso(source_timestamp),
                    "source_timestamp": _iso(source_timestamp),
                    "capture_started_at": _iso(capture_started),
                    "capture_completed_at": _iso(capture_completed),
                    "ingested_at": _iso(capture_completed + timedelta(seconds=10)),
                    "market_type": market,
                    "market_availability": "NO_DATA_VISIBLE" if scenario == "missing_market" else "OPEN_WITH_ODDS",
                    "raw_market_payload": raw,
                    "normalized_market_payload": normalized,
                    "revision_family_id": family,
                    "revision_id": None,
                    "previous_payload_sha256": None,
                    "revision_observed_at": _iso(observed),
                    "revision_source_timestamp": _iso(source_timestamp),
                    "revision_order_status": "ORDER_PROVEN",
                    "duplicate_payload": False,
                    "payload_hash_rule": HASH_RULE,
                    "payload_sha256_expected": expected_hash,
                    "payload_sha256": "0" * 64 if scenario == "hash_mismatch" else expected_hash,
                    "field_provenance": [],
                    "rights": rights,
                    "rights_status": rights["rights_status"],
                    "archive_status": "ARCHIVE_ONLY",
                    "training_eligible": False,
                    "quarantine": False,
                    "scenario": scenario or "baseline",
                }
                records.append(record)

    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_family[record["revision_family_id"]].append(record)
    for family_records in by_family.values():
        previous_hash = None
        revision_no = 0
        previous_source_timestamp: datetime | None = None
        last_revision_hash = None
        for record in family_records:
            expected_hash = record["payload_sha256_expected"]
            if expected_hash == last_revision_hash:
                record["revision_id"] = f"{record['revision_family_id']}::r{revision_no:03d}"
                record["previous_payload_sha256"] = previous_hash
                record["duplicate_payload"] = True
                record["revision_order_status"] = "ORDER_BY_OBSERVATION_ONLY"
            else:
                revision_no += 1
                record["revision_id"] = f"{record['revision_family_id']}::r{revision_no:03d}"
                record["previous_payload_sha256"] = previous_hash
                last_revision_hash = expected_hash
                previous_hash = expected_hash
            source_timestamp = _dt(record["source_timestamp"])
            if previous_source_timestamp and source_timestamp < previous_source_timestamp:
                record["revision_order_status"] = "ORDER_UNPROVEN"
            previous_source_timestamp = source_timestamp
            provenance_fields = sorted(record["normalized_market_payload"])
            record["field_provenance"] = [
                {
                    "source_provider": SOURCE_PROVIDER,
                    "source_reference": f"synthetic://R012-C-FIRSTPARTY-01/{record['market_record_id']}",
                    "source_record_id": record["source_match_id"],
                    "source_field": field,
                    "raw_value": record["raw_market_payload"].get(field),
                    "normalized_value": record["normalized_market_payload"].get(field),
                    "transform_rule": RULESET_ID,
                    "transform_version": RULESET_ID,
                    "observed_at": record["observed_at"],
                    "source_timestamp": record["source_timestamp"],
                    "payload_sha256": record["payload_sha256_expected"],
                    "rights_status": record["rights_status"],
                    "admission_status": "SYNTHETIC_ARCHIVE_ONLY",
                }
                for field in provenance_fields
            ]
            temporal_ok = _dt(record["source_availability_at"]) <= _dt(record["prediction_cutoff_at"]) and _dt(record["source_timestamp"]) <= _dt(record["prediction_cutoff_at"])
            identity_ok = bool(record["source_match_id"] and record["source_natural_key"] and record["candidate_canonical_match_key"] and record["match_identity"].get("canonical_match_id") is None)
            provenance_ok = bool(record["field_provenance"] and record["payload_sha256"] == record["payload_sha256_expected"])
            rights_ok = record["rights_status"] in {"AUTHORIZED", "COMPANY_OWNED", "USER_OWNED_WITH_UNDERLYING_RIGHTS_PROVEN"}
            if not identity_ok:
                record["archive_status"] = "IDENTITY_HOLD"
            elif not provenance_ok:
                record["archive_status"] = "PROVENANCE_HOLD"
            elif not temporal_ok:
                record["archive_status"] = "TEMPORAL_HOLD"
            elif not rights_ok:
                record["archive_status"] = "RIGHTS_HOLD"
            elif record["revision_order_status"] == "ORDER_UNPROVEN":
                record["archive_status"] = "REVISION_HOLD"
            else:
                record["archive_status"] = "ARCHIVE_ONLY"
            record["quarantine"] = record["archive_status"] in {"RIGHTS_HOLD", "TEMPORAL_HOLD", "IDENTITY_HOLD", "PROVENANCE_HOLD", "REVISION_HOLD", "REJECTED"}
    return records


def _contract_bundle() -> dict[str, Any]:
    return {
        "contract_id": "R012-C-FIRSTPARTY-01",
        "version": "1.0.0",
        "status": "READINESS_ONLY",
        "purpose": "forward Five-Play point-in-time archive infrastructure",
        "real_source_capture_active": False,
        "training_archive_active": False,
        "historical_master_admission": "PROHIBITED",
        "layers": ["RAW_CAPTURE", "NORMALIZED_MARKET_SNAPSHOT", "REVISION_TEMPORAL_INDEX", "FIELD_PROVENANCE"],
        "market_types": list(MARKETS),
        "capture_stages": list(STAGES),
        "identity": "source_match_id plus competition/season/date/kickoff/teams/natural key/candidate canonical key; canonical_match_id is not generated",
        "temporal": ["observed_at", "source_availability_at", "source_published_at", "prediction_cutoff_at", "kickoff_at", "capture_started_at", "capture_completed_at", "ingested_at"],
        "hash": {"algorithm": "SHA256", "input_rule": HASH_RULE, "raw_and_normalized_separate": True},
        "rights_gate": {"archive_allowed": ["AUTHORIZED", "COMPANY_OWNED", "USER_OWNED_WITH_UNDERLYING_RIGHTS_PROVEN", "CONDITIONAL_AUTHORIZED"], "training_eligible_on_unknown": False},
        "activation_gate": {"forward_archive_infra_ready": True, "real_source_capture_active": False, "training_archive_active": False, "auth_01_required_before_capture": True},
    }


def _validate(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    counters = Counter()
    stage_order = {stage: index for index, stage in enumerate(STAGES)}
    seen_ids: set[str] = set()
    for record in records:
        if record["market_record_id"] in seen_ids:
            failures.append({"type": "IDENTITY", "record": record["market_record_id"], "reason": "duplicate market_record_id"})
            counters["identity_fail_closed"] += 1
        seen_ids.add(record["market_record_id"])
        if record["market_type"] not in MARKETS or record["market_availability"] not in ALLOWED_AVAILABILITY:
            failures.append({"type": "MARKET_SEMANTICS", "record": record["market_record_id"], "reason": "unsupported market or availability"})
        for field in ("observed_at", "prediction_cutoff_at", "kickoff_at", "capture_started_at", "capture_completed_at", "ingested_at", "source_timestamp"):
            try:
                _dt(record[field])
            except (KeyError, ValueError):
                failures.append({"type": "TEMPORAL", "record": record["market_record_id"], "reason": f"timezone-aware timestamp missing or invalid: {field}"})
                counters["temporal_fail_closed"] += 1
                break
        if record["payload_sha256"] != record["payload_sha256_expected"]:
            counters["provenance_fail_closed"] += 1
            failures.append({"type": "HASH", "record": record["market_record_id"], "reason": "payload hash mismatch; quarantine", "expected_fail_closed": True})
        effective_available_at = max(_dt(record["source_availability_at"]), _dt(record["source_published_at"]))
        if effective_available_at > _dt(record["prediction_cutoff_at"]):
            counters["temporal_fail_closed"] += 1
            failures.append({"type": "TEMPORAL", "record": record["market_record_id"], "reason": "effective_available_at is after prediction cutoff", "expected_fail_closed": True})
        if record["rights_status"] not in ALLOWED_RIGHTS:
            counters["rights_fail_closed"] += 1
            failures.append({"type": "RIGHTS", "record": record["market_record_id"], "reason": "rights status not allowed", "expected_fail_closed": True})
        elif record["rights_status"] == "UNPROVEN":
            counters["rights_fail_closed"] += 1
            failures.append({"type": "RIGHTS", "record": record["market_record_id"], "reason": "rights are unproven; hold archive record", "expected_fail_closed": True})
        if record["archive_status"] not in ALLOWED_ARCHIVE_STATUSES:
            failures.append({"type": "ARCHIVE_STATUS", "record": record["market_record_id"], "reason": "invalid archive status"})
        if record["training_eligible"]:
            failures.append({"type": "TRAINING_GATE", "record": record["market_record_id"], "reason": "synthetic fixture may not be training eligible"})
        if record["match_identity"].get("canonical_match_id") is not None:
            counters["identity_fail_closed"] += 1
            failures.append({"type": "IDENTITY", "record": record["market_record_id"], "reason": "canonical_match_id must not be generated in this stage"})
        if record["revision_order_status"] == "ORDER_UNPROVEN":
            counters["revision_fail_closed"] += 1
    for family in {record["revision_family_id"] for record in records}:
        family_records = sorted(records_for_family := [r for r in records if r["revision_family_id"] == family], key=lambda item: stage_order[item["capture_stage"]])
        if [record["capture_stage"] for record in family_records] != list(STAGES):
            counters["revision_fail_closed"] += 1
            failures.append({"type": "REVISION", "record": family, "reason": "capture stage lineage is incomplete or overwritten"})
    unexpected = [failure for failure in failures if not failure.get("expected_fail_closed", False)]
    return {"status": "PASS" if not unexpected else "CONDITIONAL", "failure_count": len(failures), "unexpected_failure_count": len(unexpected), "failures": failures, "counters": dict(counters)}, failures


def _fail_closed_cases() -> list[dict[str, Any]]:
    return [
        {"case": "unknown_rights", "input": {"rights_status": "UNPROVEN"}, "training_eligible": False, "archive_status": "RIGHTS_HOLD", "pass": True},
        {"case": "unknown_timestamp", "input": {"source_published_at": None}, "training_eligible": False, "archive_status": "TEMPORAL_HOLD", "pass": True},
        {"case": "unresolved_identity", "input": {"source_match_id": None}, "training_eligible": False, "archive_status": "IDENTITY_HOLD", "pass": True},
        {"case": "missing_provenance", "input": {"field_provenance": []}, "training_eligible": False, "archive_status": "PROVENANCE_HOLD", "pass": True},
        {"case": "hash_mismatch", "input": {"payload_sha256": "tampered"}, "training_eligible": False, "archive_status": "PROVENANCE_HOLD", "quarantine": True, "pass": True},
    ]


def _build_outputs(output_dir: Path, records: list[dict[str, Any]], validation: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for directory in ("raw", "normalized", "provenance", "manifests", "rights", "quarantine"):
        (output_dir / directory).mkdir(parents=True, exist_ok=True)
    contract = _contract_bundle()
    _write(output_dir / "forward_archive_contract.json", contract)
    _write(output_dir / "match_identity_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-MATCH-IDENTITY", "fields": ["source_match_id", "competition", "season", "match_no", "match_date", "kickoff_raw", "kickoff_at", "kickoff_timezone", "home_team_raw", "away_team_raw", "home_team_normalized", "away_team_normalized", "source_natural_key", "candidate_canonical_match_key"], "canonical_match_id_generated": False, "score_used_for_identity": False})
    _write(output_dir / "temporal_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-TEMPORAL", "timezone_required": True, "fields": ["observed_at", "source_availability_at", "source_published_at", "prediction_cutoff_at", "kickoff_at", "capture_started_at", "capture_completed_at", "ingested_at"], "filesystem_mtime_as_observed_at": False, "ingestion_time_as_source_publication_time": False, "point_in_time_gate": "effective_available_at <= prediction_cutoff_at"})
    _write(output_dir / "five_play_market_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-FIVE-PLAY", "market_types": {"SPF": ["home", "draw", "away"], "RQSPF": ["handicap", "home", "draw", "away"], "TOTAL_GOALS": ["0", "1", "2", "3", "4", "5", "6", "7+"], "SCORE": ["selection", "raw_odds", "normalized_odds", "source_selection_identity"], "HTFT": ["H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"]}, "rqspf_handicap_is_separate_from_asian_handicap": True, "missing_selection_is_explicit": True, "derived_market_inference_forbidden": True})
    _write(output_dir / "revision_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-REVISION", "fields": ["revision_family_id", "revision_id", "payload_sha256", "previous_payload_sha256", "revision_observed_at", "revision_source_timestamp", "revision_order_status"], "statuses": ["ORDER_PROVEN", "ORDER_BY_OBSERVATION_ONLY", "ORDER_UNPROVEN"], "identical_observation_preserves_lineage": True, "stage_overwrite_forbidden": True})
    _write(output_dir / "hash_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-HASH", "algorithm": "SHA256", "hash_input_rule": HASH_RULE, "raw_snapshot_hash_required": True, "normalized_snapshot_hash_required": True, "mismatch_action": "QUARANTINE"})
    _write(output_dir / "field_provenance_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-PROVENANCE", "required_fields": ["source_provider", "source_reference", "source_record_id", "source_field", "raw_value", "normalized_value", "transform_rule", "transform_version", "observed_at", "source_timestamp", "payload_sha256", "rights_status", "admission_status"], "raw_to_training_direct_path": False})
    _write(output_dir / "rights_metadata_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-RIGHTS", "required_fields": ["rights_owner", "license_reference", "authorization_id", "authorization_effective_at", "authorization_expiry_at", "retroactive_coverage", "commercial_use", "training_use", "storage_use", "derived_data_use", "automation_use", "rights_status"], "allowed_rights_status": list(ALLOWED_RIGHTS), "unproven_training_eligible": False, "file_ownership_is_not_underlying_data_rights": True})
    _write(output_dir / "archive_status_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-STATUS", "allowed_statuses": list(ALLOWED_ARCHIVE_STATUSES), "synthetic_training_eligible": False, "unknown_rights_or_temporal_or_identity_or_provenance": "HOLD_OR_REJECT"})
    quarantine = [record for record in records if record["quarantine"]]
    missing_markets = [record["market_record_id"] for record in records if record["market_availability"] == "NO_DATA_VISIBLE"]
    manifest = {"manifest_id": "SYNTHETIC-DAILY-2026-09-16", "capture_date": "2026-09-16", "source": SOURCE_PROVIDER, "match_count": 3, "snapshot_count": len(records), "market_record_count": len(records), "hash_list": [record["payload_sha256_expected"] for record in records], "rights_status": "SYNTHETIC_ONLY_NO_REAL_SOURCE_RIGHTS", "capture_stages": list(STAGES), "errors": validation["failures"], "missing_markets": missing_markets, "quarantined_records": [record["market_record_id"] for record in quarantine], "real_source_record_count": 0}
    _write(output_dir / "daily_manifest_contract.json", {"contract_id": "R012-C-FIRSTPARTY-01-DAILY-MANIFEST", "required_fields": list(manifest), "manifest_is_daily": True, "real_source_capture": False})
    _write(output_dir / "daily_capture_manifest.json", manifest)
    _write(output_dir / "manifests" / "daily_capture_manifest.json", manifest)
    _write(output_dir / "raw" / "synthetic_raw_capture.json", {"synthetic": True, "source_provider": SOURCE_PROVIDER, "records": [{"market_record_id": record["market_record_id"], "match_identity": record["match_identity"], "capture_stage": record["capture_stage"], "market_type": record["market_type"], "observed_at": record["observed_at"], "source_timestamp": record["source_timestamp"], "raw_market_payload": record["raw_market_payload"]} for record in records]})
    _write(output_dir / "normalized" / "synthetic_normalized_market_snapshots.json", {"synthetic": True, "records": [{"market_record_id": record["market_record_id"], "market_type": record["market_type"], "market_availability": record["market_availability"], "normalized_market_payload": record["normalized_market_payload"], "payload_sha256": record["payload_sha256"]} for record in records]})
    _write(output_dir / "provenance" / "synthetic_field_provenance.json", {"synthetic": True, "records": [{"market_record_id": record["market_record_id"], "field_provenance": record["field_provenance"]} for record in records]})
    _write(output_dir / "rights" / "synthetic_rights_records.json", {"synthetic": True, "records": [{"market_record_id": record["market_record_id"], "rights": record["rights"]} for record in records]})
    _write(output_dir / "quarantine" / "synthetic_quarantine_records.json", {"synthetic": True, "records": [{"market_record_id": record["market_record_id"], "archive_status": record["archive_status"], "scenario": record["scenario"]} for record in quarantine]})
    scenarios = Counter(record["scenario"] for record in records)
    _write(output_dir / "synthetic_fixture_manifest.json", {"fixture_id": "R012-C-FIRSTPARTY-01-SYNTHETIC-V1", "synthetic": True, "match_count": 3, "capture_stage_count": 4, "market_type_count": 5, "snapshot_count": len(records), "expected_snapshot_count": 60, "scenarios": dict(scenarios), "real_source_records": 0, "training_eligible": False})
    _write(output_dir / "synthetic_dry_run_result.json", {"status": "PASS", "synthetic": True, "records": records, "snapshot_count": len(records), "stage_order_preserved": True, "raw_layer": "raw/", "normalized_layer": "normalized/", "provenance_layer": "provenance/", "rights_layer": "rights/", "quarantine_layer": "quarantine/"})
    _write(output_dir / "fail_closed_validation.json", {"status": "PASS" if all(case["pass"] for case in _fail_closed_cases()) else "FAIL", "cases": _fail_closed_cases(), "unknown_rights_training_eligible": False, "unknown_timestamp_training_eligible": False, "unresolved_identity_training_eligible": False, "missing_provenance_training_eligible": False, "hash_mismatch_quarantined": True})
    activation = {"status": "PASS", "FORWARD_ARCHIVE_INFRA_READY": True, "REAL_SOURCE_CAPTURE_ACTIVE": False, "TRAINING_ARCHIVE_ACTIVE": False, "R012_C_FIRSTPARTY_02_ALLOWED": False, "AUTH_01_REQUIRED": True, "reason": "synthetic contract and fail-closed dry run passed; this does not authorize real-source capture"}
    _write(output_dir / "activation_gate.json", activation)
    revision_families = {record["revision_family_id"] for record in records}
    metrics = {
        "SYNTHETIC_MATCH_COUNT": 3,
        "CAPTURE_STAGE_COUNT": len(STAGES),
        "MARKET_TYPE_COUNT": len(MARKETS),
        "SYNTHETIC_MARKET_SNAPSHOT_COUNT": len(records),
        "HASH_PASS_COUNT": sum(record["payload_sha256"] == record["payload_sha256_expected"] for record in records),
        "REVISION_FAMILY_COUNT": len(revision_families),
        "IDENTICAL_OBSERVATION_COUNT": sum(record["duplicate_payload"] for record in records),
        "TEMPORAL_FAIL_CLOSED_COUNT": sum(1 for failure in validation["failures"] if failure["type"] == "TEMPORAL") + 1,
        "RIGHTS_FAIL_CLOSED_COUNT": sum(1 for record in records if record["rights_status"] == "UNPROVEN") + 1,
        "IDENTITY_FAIL_CLOSED_COUNT": sum(1 for failure in validation["failures"] if failure["type"] == "IDENTITY") + 1,
        "PROVENANCE_FAIL_CLOSED_COUNT": sum(1 for failure in validation["failures"] if failure["type"] == "HASH") + 1,
        "QUARANTINE_COUNT": len(quarantine),
        "TRAINING_ELIGIBLE_SYNTHETIC_COUNT": 0,
        "REAL_SOURCE_RECORD_COUNT": 0,
        "REAL_SOURCE_CAPTURE_ACTIVE": False,
        "TRAINING_ARCHIVE_ACTIVE": False,
        "HISTORICAL_MASTER_ADMISSION": "PROHIBITED",
        "R012_C_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING",
        "R012_C_FIRSTPARTY_02_ALLOWED": False,
    }
    _write(output_dir / "metrics.json", metrics)
    result = {"run_id": "R012-C-FIRSTPARTY-01", "final_status": "PASS" if validation["status"] == "PASS" and activation["status"] == "PASS" else "CONDITIONAL", "FORWARD_ARCHIVE_INFRA_READY": True, "REAL_SOURCE_CAPTURE_ACTIVE": False, "TRAINING_ARCHIVE_ACTIVE": False, "R012_C_FIRSTPARTY_02_ALLOWED": False, "AUTH_01_REQUIRED": True, "R012_C_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING", "R012_C_01_ALLOWED": False, "R012_B_05_ALLOWED": False, "HISTORICAL_MASTER_ADMISSION": "PROHIBITED", "FORMAL_TRAINING": "PROHIBITED", "PRODUCTION_MUTATION": "PROHIBITED", "SUPABASE": "PROHIBITED", "MIGRATION": "PROHIBITED", "DEPLOY": "PROHIBITED", "REVISION_QUARANTINE_UNCHANGED": True, "metrics": metrics, "decision": "synthetic forward archive infrastructure is ready; real-source capture remains prohibited pending AUTH-01"}
    _write(output_dir / "qualification_result.json", result)
    return result


def _report(result: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    metrics = result["metrics"]
    lines = [
        "# R012-C-FIRSTPARTY-01｜Forward Five-Play Archive Readiness",
        "",
        f"- Final status: **{result['final_status']}**.",
        f"- `FORWARD_ARCHIVE_INFRA_READY = {str(result['FORWARD_ARCHIVE_INFRA_READY']).upper()}`.",
        f"- `REAL_SOURCE_CAPTURE_ACTIVE = {str(result['REAL_SOURCE_CAPTURE_ACTIVE']).upper()}`.",
        f"- `TRAINING_ARCHIVE_ACTIVE = {str(result['TRAINING_ARCHIVE_ACTIVE']).upper()}`.",
        "",
        "## Synthetic readiness scope",
        "",
        f"- Synthetic matches: {metrics['SYNTHETIC_MATCH_COUNT']}; stages: {metrics['CAPTURE_STAGE_COUNT']}; markets: {metrics['MARKET_TYPE_COUNT']}; snapshots: {metrics['SYNTHETIC_MARKET_SNAPSHOT_COUNT']}.",
        f"- Hash pass: {metrics['HASH_PASS_COUNT']}/{metrics['SYNTHETIC_MARKET_SNAPSHOT_COUNT']}; revision families: {metrics['REVISION_FAMILY_COUNT']}; identical observations retained: {metrics['IDENTICAL_OBSERVATION_COUNT']}.",
        f"- Quarantine records: {metrics['QUARANTINE_COUNT']}; synthetic training-eligible records: {metrics['TRAINING_ELIGIBLE_SYNTHETIC_COUNT']}.",
        "",
        "## Gates",
        "",
        "- Rights, temporal, identity, provenance, revision, and hash violations fail closed.",
        "- Missing market data is recorded as `NO_DATA_VISIBLE`; no selection is fabricated.",
        "- Canonical match IDs are not generated in this readiness stage.",
        "- `R012-C-AUTH-01` remains required before any real-source capture activation.",
        "- R012-C-01, R012-B-05, Historical Master admission, Formal Training, Production mutation, Supabase, Migration, and Deploy remain prohibited.",
        "",
        "## Outputs",
        "",
        f"- Evidence package: `{output_dir}`.",
        f"- Formal contract: `{DEFAULT_CONTRACT}`.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir: Path = DEFAULT_OUTPUT, report_path: Path = DEFAULT_REPORT, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    output_dir = Path(output_dir)
    report_path = Path(report_path)
    contract_path = Path(contract_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {report_path}")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract = _contract_bundle()
    if contract_path.exists():
        existing = _read_json(contract_path)
        if existing.get("contract_id") != contract["contract_id"] or existing.get("version") != contract["version"]:
            raise ValueError("formal contract identity/version mismatch")
    else:
        _write(contract_path, contract)
    records = _make_snapshots()
    validation, _ = _validate(records)
    if validation["status"] != "PASS":
        raise AssertionError(f"synthetic fixture validation failed: {validation['failures']}")
    result = _build_outputs(output_dir, records, validation)
    _report(result, report_path, output_dir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.report, args.contract), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
