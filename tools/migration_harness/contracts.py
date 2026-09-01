"""Pure contract guards used by the local negative-test harness.

These functions model the refusal decision without pretending that a
PostgreSQL trigger, RLS policy, or view has run.  The negative registry marks
database-enforcement cases as runtime-pending separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .common import is_non_empty_string


@dataclass(frozen=True)
class ContractDecision:
    accepted: bool
    code: str
    reason: str

    @property
    def rejected(self) -> bool:
        return not self.accepted

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "code": self.code, "reason": self.reason}


def reject(code: str, reason: str) -> ContractDecision:
    return ContractDecision(False, code, reason)


def accept(code: str = "CONTRACT_ACCEPTED", reason: str = "Contract conditions are satisfied") -> ContractDecision:
    return ContractDecision(True, code, reason)


def validate_market_payload(market: Dict[str, Any]) -> ContractDecision:
    market_name = str(market.get("market", "")).lower()
    status = str(market.get("status", "")).upper()
    payload = market.get("payload")
    if status == "AVAILABLE" and payload in (None, "", {}, []):
        return reject("AVAILABLE_PAYLOAD_MISSING", f"Available {market_name or 'market'} cannot omit payload")
    if status == "UNAVAILABLE":
        reason = market.get("unavailable_reason")
        if not is_non_empty_string(reason) and not isinstance(reason, dict):
            return reject("UNAVAILABLE_REASON_MISSING", f"Unavailable {market_name or 'market'} must retain a reason")
        if payload not in (None, "", {}, []):
            return reject("UNAVAILABLE_PAYLOAD_PRESENT", f"Unavailable {market_name or 'market'} cannot carry fabricated payload")
    if market_name == "rqspf" and status == "AVAILABLE":
        handicap = market.get("handicap_line")
        if handicap in (None, "", {}, []):
            return reject("RQSPF_HANDICAP_MISSING", "Available RQSPF requires a handicap line")
    if status not in {"AVAILABLE", "UNAVAILABLE", "UNKNOWN", "BLOCKED", "NOT_VERIFIED", "STALE", "CONFLICT"}:
        return reject("MARKET_STATUS_INVALID", "Market status is not a governed availability state")
    return accept()


def validate_prematch_run(run: Dict[str, Any]) -> ContractDecision:
    try:
        kickoff = datetime.fromisoformat(str(run["kickoff_at"]))
        cutoff = datetime.fromisoformat(str(run["prediction_cutoff_at"]))
        run_at = datetime.fromisoformat(str(run["run_at"]))
    except (KeyError, TypeError, ValueError):
        return reject("PREMATCH_TIME_MISSING", "Kickoff, cutoff, and run time must be parseable")
    if not cutoff < kickoff:
        return reject("CUTOFF_AFTER_KICKOFF", "Prediction cutoff must be before kickoff")
    if not run_at < kickoff:
        return reject("POST_KICKOFF_RUN", "A formal pre-match run cannot complete at or after kickoff")
    if str(run.get("role", "")).upper() not in {"PRODUCTION", "SHADOW", "EXPERIMENT"}:
        return reject("ROLE_INVALID", "Run role must be an explicit V4 role")
    return accept()


def validate_immutable_mutation(record: Dict[str, Any], operation: str) -> ContractDecision:
    if record.get("immutable") is True or str(record.get("status", "")).upper() == "FROZEN":
        code = "FROZEN_PREDICTION_MUTATION" if record.get("entity_type") == "Frozen Prediction" else "FROZEN_INPUT_MUTATION"
        return reject(code, f"{operation.upper()} is forbidden after the record becomes immutable")
    return accept()


def validate_review_scope(review: Dict[str, Any]) -> ContractDecision:
    if review.get("result_match_id") != review.get("frozen_prediction_match_id"):
        return reject("REVIEW_MATCH_SCOPE_MISMATCH", "Review result and Frozen Prediction must share match identity")
    return accept()


def validate_tier_a_pair(pair: Dict[str, Any]) -> ContractDecision:
    if pair.get("production_role") != "PRODUCTION" or pair.get("shadow_role") != "SHADOW":
        return reject("TIER_A_ROLE_VIOLATION", "Tier A requires exactly one Production and one Shadow member")
    if pair.get("production_frozen_input_hash") != pair.get("shadow_frozen_input_hash"):
        return reject("TIER_A_FROZEN_INPUT_HASH_MISMATCH", "Tier A members must use the exact same frozen_input_hash")
    if pair.get("experiment_member") is True or pair.get("member_role") == "EXPERIMENT":
        return reject("EXPERIMENT_NOT_TIER_A", "Experiment output cannot qualify as Forward Tier A evidence")
    if pair.get("production_completed_before_kickoff") is False or pair.get("shadow_completed_before_kickoff") is False:
        return reject("TIER_A_POST_KICKOFF", "Tier A members must complete before kickoff")
    return accept()


def validate_public_projection(projection: Dict[str, Any]) -> ContractDecision:
    if projection.get("role") != "PRODUCTION":
        return reject("PUBLIC_ROLE_LEAK", "Only approved Production output may enter the public projection")
    if projection.get("status") not in {"PUBLISHED", "WITHDRAWN"}:
        return reject("PUBLIC_STATUS_INVALID", "Public projection status must be governed")
    if projection.get("contains_private_payload") is True:
        return reject("PUBLIC_PRIVATE_PAYLOAD", "Private model payload cannot enter a public projection")
    return accept()


def validate_production_uniqueness(revisions: Iterable[Dict[str, Any]]) -> ContractDecision:
    active = [
        row
        for row in revisions
        if row.get("role") == "PRODUCTION"
        and row.get("status") == "PRODUCTION"
        and row.get("is_canonical_active") is True
    ]
    if len(active) > 1:
        return reject("PRODUCTION_UNIQUENESS_FAILURE", "At most one active Production revision may exist per family/channel")
    return accept()


def validate_function_security(function: Dict[str, Any]) -> ContractDecision:
    if function.get("security") != "DEFINER":
        return accept()
    search_path = function.get("search_path")
    if not isinstance(search_path, list) or not search_path or "pg_catalog" not in search_path:
        return reject("SECURITY_DEFINER_SEARCH_PATH_UNSAFE", "SECURITY DEFINER requires a fixed trusted search_path")
    if function.get("actor_check") is not True:
        return reject("SECURITY_DEFINER_ACTOR_CHECK_MISSING", "SECURITY DEFINER requires an explicit actor check")
    if function.get("execute_grants_reviewed") is not True:
        return reject("SECURITY_DEFINER_EXECUTE_UNREVIEWED", "SECURITY DEFINER execute grants must be restricted and reviewed")
    return accept()


def validate_role_write(role: str, target_kind: str, operation: str) -> ContractDecision:
    if role in {"anon", "authenticated"} and target_kind == "internal" and operation.upper() in {"INSERT", "UPDATE", "DELETE"}:
        return reject("PUBLIC_INTERNAL_WRITE_DENIED", "anon and ordinary authenticated roles cannot write internal V4 tables")
    return accept()


def validate_canonical_latest(values: Dict[str, Any]) -> ContractDecision:
    business_times = values.get("business_times")
    canonical = values.get("canonical_latest_update_at")
    if not isinstance(business_times, list) or not business_times or not is_non_empty_string(canonical):
        return reject("CANONICAL_LATEST_TIME_MISSING", "Canonical latest update requires real business timestamps")
    try:
        expected = max(datetime.fromisoformat(str(value)) for value in business_times).isoformat()
        actual = datetime.fromisoformat(str(canonical)).isoformat()
    except (TypeError, ValueError):
        return reject("CANONICAL_LATEST_TIME_INVALID", "Business timestamps must be parseable")
    if actual != expected:
        return reject("CANONICAL_LATEST_USES_NON_BUSINESS_TIME", "Page, deploy, or build time cannot define canonical latest update")
    if values.get("page_build_at") == canonical or values.get("deploy_at") == canonical:
        return reject("CANONICAL_LATEST_USES_NON_BUSINESS_TIME", "Page or deploy time cannot define canonical latest update")
    return accept()


def validate_unknown_not_coerced(value: Dict[str, Any]) -> ContractDecision:
    state = str(value.get("state", "")).upper()
    coerced = value.get("coerced_value")
    if state == "UNKNOWN" and coerced in {False, 0, 0.0, "FALSE", "0", "", None}:
        return reject("UNKNOWN_COERCION", "UNKNOWN must remain explicit and cannot become FALSE, zero, or a default")
    return accept()
