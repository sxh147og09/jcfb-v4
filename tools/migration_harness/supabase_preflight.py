"""Static Supabase Production preflight-plan and evidence contracts.

This module translates a previously supplied, read-only Production baseline
into repository governance artifacts.  It never opens a connection, executes
SQL, calls a Supabase API, or changes migration history.  Live recapture is an
apply-before gate and is represented as a required check rather than inferred
from this checked-in plan.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .canonical_hash import verify_candidate_hashes
from .common import is_v4_hash, read_json, sha256_json
from .models import CheckStatus, Issue
from .schema_diff import CATALOG_KINDS


PREFLIGHT_PLAN_PATH = "config/migration_harness/v4_supabase_preflight_plan.json"
PREFLIGHT_PLAN_SCHEMA_PATH = "config/migration_harness/v4_supabase_preflight_plan.schema.json"
PREFLIGHT_PLAN_ID = "v4-supabase-preflight-plan@1.0.0"
PREFLIGHT_PLAN_SCOPE = "JCFB_V4_SUPABASE_PREFLIGHT_PLAN_COMPLETION"
PRODUCTION_PROJECT_REF = "icndieflfvydixtehgzu"
PRODUCTION_PROVIDER = "Supabase"
PRODUCTION_REGION = "us-west-2"
PRODUCTION_POSTGRES_MAJOR = 17
PRODUCTION_DATABASE_NAME = "postgres"
PRODUCTION_SERVER_VERSION = "17.6"
CAPTURE_SOURCE = "connected Supabase read-only inspection"
BASELINE_ATTRIBUTION = "PRE_EXISTING_V3_3_3_DEBT"
BASELINE_OBJECT_ATTRIBUTION = "PRE_EXISTING_V3_3_3_BASELINE"
EXPECTED_BASELINE_COUNTS = {
    "public_tables": 20,
    "public_views": 11,
    "public_functions": 18,
    "public_rls_tables": 20,
    "public_non_internal_triggers": 38,
}
EXPECTED_V4_SEQUENCE = tuple(f"{index:04d}" for index in range(1, 10))
EXPECTED_BASELINE_HISTORY = (
    ("20260831064909", "jcfb_v3_3_3_central_data_schema_1_0"),
    ("20260831064938", "jcfb_v3_3_3_schema_1_0_security_hardening"),
    ("20260831064955", "jcfb_v3_3_3_schema_1_0_fk_indexes"),
    ("20260831065135", "jcfb_v3_3_3_central_data_schema_1_1"),
    ("20260831065552", "jcfb_v3_3_3_official_odds_ingestion_gate_1_0"),
    ("20260831070156", "jcfb_v3_3_3_official_screenshot_intake_1_0"),
    ("20260831073246", "jcfb_v3_3_3_shadow_execution_provenance_guard_1_0"),
    ("20260831074714", "historical_tier_a_recovery_quarantine_1_0"),
    ("20260831080846", "jcfb_v3_3_3_forward_tier_a_collection_1_0"),
)
APPLY_BEFORE_IDS = (
    "APPLY-01",
    "APPLY-02",
    "APPLY-03",
    "APPLY-04",
    "APPLY-05",
    "APPLY-06",
    "APPLY-07",
    "APPLY-08",
    "APPLY-09",
)
POST_APPLY_IDS = tuple(f"POST-{index:02d}" for index in range(1, 15))
SENSITIVE_KEYS = {
    "url",
    "database_url",
    "connection_string",
    "connection_uri",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "service_role_key",
    "private_key",
    "cookie",
    "secret",
    "secret_value",
}
GIT_HEAD_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
ADVISOR_FINGERPRINT_FIELDS = (
    "advisor",
    "code",
    "severity",
    "scope",
    "object_identity",
    "role",
    "attribution",
)


def _issue(code: str, message: str, location: Optional[str] = None) -> Issue:
    return Issue(code, message, location)


def load_supabase_preflight_plan(repo_root: Path) -> Dict[str, Any]:
    return read_json(Path(repo_root) / PREFLIGHT_PLAN_PATH)


def load_supabase_preflight_schema(repo_root: Path) -> Dict[str, Any]:
    return read_json(Path(repo_root) / PREFLIGHT_PLAN_SCHEMA_PATH)


def _walk_sensitive_keys(value: Any, path: str = "") -> Iterable[Issue]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            location = f"{path}.{key_text}" if path else key_text
            if key_text in SENSITIVE_KEYS:
                yield _issue("PREFLIGHT_SECRET_FIELD_PRESENT", "Preflight contract contains a forbidden secret field", location)
            yield from _walk_sensitive_keys(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_sensitive_keys(child, f"{path}[{index}]")


def _binding_target(binding: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if not isinstance(binding, Mapping):
        return None
    targets = binding.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if isinstance(target, Mapping) and target.get("environment") == "PRODUCTION":
                return target
    if binding.get("environment") == "PRODUCTION":
        return binding
    return None


def _validate_baseline_target(baseline: Mapping[str, Any], binding: Optional[Mapping[str, Any]], issues: List[Issue]) -> None:
    target = baseline.get("target")
    if not isinstance(target, Mapping):
        issues.append(_issue("PREFLIGHT_BASELINE_TARGET_INVALID", "Production baseline target is missing", "production_baseline.target"))
        return
    expected = {
        "provider": PRODUCTION_PROVIDER,
        "project_ref": PRODUCTION_PROJECT_REF,
        "region": PRODUCTION_REGION,
        "environment": "PRODUCTION",
    }
    for field, value in expected.items():
        if target.get(field) != value:
            issues.append(_issue("PREFLIGHT_BASELINE_TARGET_MISMATCH", f"Baseline {field} does not match the approved Production binding", f"production_baseline.target.{field}"))
    bound = _binding_target(binding)
    if bound is not None:
        for field in ("provider", "project_ref", "region", "environment"):
            if target.get(field) != bound.get(field):
                issues.append(_issue("PREFLIGHT_BINDING_MISMATCH", f"Baseline {field} differs from target binding", f"production_baseline.target.{field}"))
        if bound.get("postgres_major") != PRODUCTION_POSTGRES_MAJOR:
            issues.append(_issue("PREFLIGHT_BINDING_POSTGRES_MISMATCH", "Bound Production postgres major is not 17", "targets[PRODUCTION].postgres_major"))


def _validate_database_identity(baseline: Mapping[str, Any], issues: List[Issue]) -> None:
    identity = baseline.get("database_identity")
    if not isinstance(identity, Mapping):
        issues.append(_issue("PREFLIGHT_DATABASE_IDENTITY_MISSING", "Database identity/version baseline is missing", "production_baseline.database_identity"))
        return
    if identity.get("database_name") != PRODUCTION_DATABASE_NAME:
        issues.append(_issue("PREFLIGHT_DATABASE_NAME_MISMATCH", "Production database identity must be postgres", "production_baseline.database_identity.database_name"))
    if identity.get("server_version") != PRODUCTION_SERVER_VERSION:
        issues.append(_issue("PREFLIGHT_SERVER_VERSION_MISMATCH", "Production server version baseline must be 17.6", "production_baseline.database_identity.server_version"))
    if identity.get("postgres_major") != PRODUCTION_POSTGRES_MAJOR:
        issues.append(_issue("PREFLIGHT_POSTGRES_MAJOR_MISMATCH", "Production postgres major baseline must be 17", "production_baseline.database_identity.postgres_major"))


def _history_pair(row: Any) -> Optional[Tuple[str, str]]:
    if not isinstance(row, Mapping):
        return None
    version = row.get("version", row.get("migration_version"))
    name = row.get("name", row.get("migration_name"))
    if not isinstance(version, str) or not isinstance(name, str):
        return None
    return version, name


def validate_baseline_migration_history(entries: Any) -> List[Issue]:
    issues: List[Issue] = []
    if not isinstance(entries, list):
        return [_issue("PREFLIGHT_BASELINE_HISTORY_INVALID", "Baseline migration history must be a list")]
    if len(entries) != len(EXPECTED_BASELINE_HISTORY):
        issues.append(_issue("PREFLIGHT_BASELINE_HISTORY_COUNT", "Baseline migration history must contain exactly nine entries"))
    pairs: List[Tuple[str, str]] = []
    for index, row in enumerate(entries):
        pair = _history_pair(row)
        if pair is None:
            issues.append(_issue("PREFLIGHT_BASELINE_HISTORY_ROW_INVALID", "Baseline history row must contain version and name", f"entries[{index}]"))
            continue
        pairs.append(pair)
        if isinstance(row, Mapping) and row.get("ordinal") != index + 1:
            issues.append(_issue("PREFLIGHT_BASELINE_HISTORY_ORDER", "Baseline history ordinal is not contiguous", f"entries[{index}].ordinal"))
    if pairs != list(EXPECTED_BASELINE_HISTORY):
        issues.append(_issue("PREFLIGHT_BASELINE_HISTORY_MISMATCH", "Baseline migration history does not exactly match the supplied nine-row evidence"))
    return issues


def detect_baseline_migration_drift(expected: Sequence[Mapping[str, Any]], observed: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    expected_pairs = [_history_pair(item) for item in expected]
    observed_pairs = [_history_pair(item) for item in observed]
    expected_clean = [pair for pair in expected_pairs if pair is not None]
    observed_clean = [pair for pair in observed_pairs if pair is not None]
    missing = [pair for pair in expected_clean if pair not in observed_clean]
    unexpected = [pair for pair in observed_clean if pair not in expected_clean]
    order_changed = not missing and not unexpected and expected_clean != observed_clean
    status = "PASS" if not missing and not unexpected and not order_changed and len(observed_clean) == len(expected_clean) else "BLOCKED_UNEXPECTED_PRE_EXISTING_DRIFT"
    return {
        "status": status,
        "compared_by": ["version", "name"],
        "missing": [list(pair) for pair in missing],
        "unexpected": [list(pair) for pair in unexpected],
        "order_changed": order_changed,
    }


def advisor_fingerprint(finding: Mapping[str, Any]) -> str:
    payload = {field: finding[field] for field in ADVISOR_FINGERPRINT_FIELDS if field in finding}
    return sha256_json(payload)


def _advisor_findings(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        findings = value.get("findings")
        if isinstance(findings, list):
            return [item for item in findings if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def validate_advisor_baseline(plan: Mapping[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    baseline = plan.get("production_baseline")
    if not isinstance(baseline, Mapping):
        return [_issue("PREFLIGHT_ADVISOR_BASELINE_MISSING", "Production baseline is missing")]
    for advisor_key, required_codes in (
        ("security_advisor", {"rls_enabled_no_policy", "security_definer_view", "anon_security_definer_function_executable", "authenticated_security_definer_function_executable"}),
        ("performance_advisor", {"unindexed_foreign_key", "unused_index"}),
    ):
        advisor = baseline.get(advisor_key)
        if not isinstance(advisor, Mapping) or advisor.get("captured") is not True:
            issues.append(_issue("PREFLIGHT_ADVISOR_NOT_CAPTURED", f"{advisor_key} must be marked captured", f"production_baseline.{advisor_key}"))
            continue
        findings = _advisor_findings(advisor)
        if not findings:
            issues.append(_issue("PREFLIGHT_ADVISOR_FINDINGS_EMPTY", f"{advisor_key} must contain baseline findings", f"production_baseline.{advisor_key}.findings"))
        found_codes = {str(item.get("code")) for item in findings}
        if not required_codes.issubset(found_codes):
            issues.append(_issue("PREFLIGHT_ADVISOR_CODES_MISSING", f"{advisor_key} is missing one or more supplied baseline finding codes"))
        for index, finding in enumerate(findings):
            if finding.get("attribution") != BASELINE_ATTRIBUTION:
                issues.append(_issue("PREFLIGHT_ADVISOR_ATTRIBUTION_INVALID", "Every baseline advisor finding must be attributed to pre-existing V3.3.3 debt", f"{advisor_key}.findings[{index}].attribution"))
            fingerprint = finding.get("fingerprint")
            if not is_v4_hash(fingerprint) or fingerprint != advisor_fingerprint(finding):
                issues.append(_issue("PREFLIGHT_ADVISOR_FINGERPRINT_INVALID", "Advisor baseline fingerprint is missing or unstable", f"{advisor_key}.findings[{index}].fingerprint"))
    return issues


def _finding_key(finding: Mapping[str, Any]) -> str:
    fingerprint = finding.get("fingerprint")
    return str(fingerprint) if is_v4_hash(fingerprint) else advisor_fingerprint(finding)


def compare_advisor_findings(baseline: Any, after: Any) -> Dict[str, Any]:
    """Compare read-only advisor outputs without treating V3 debt as V4 debt."""

    before_findings = _advisor_findings(baseline)
    after_findings = _advisor_findings(after)
    before_by_key = {_finding_key(item): item for item in before_findings}
    after_by_key = {_finding_key(item): item for item in after_findings}
    new_findings = [dict(after_by_key[key]) for key in sorted(set(after_by_key) - set(before_by_key))]
    missing_baseline = [dict(before_by_key[key]) for key in sorted(set(before_by_key) - set(after_by_key))]
    preserved = [dict(after_by_key[key]) for key in sorted(set(before_by_key) & set(after_by_key))]
    new_security_error_warn = [
        item for item in new_findings
        if item.get("advisor") == "supabase_security"
        and item.get("attribution") != BASELINE_ATTRIBUTION
        and item.get("severity") in {"ERROR", "WARN"}
    ]
    new_performance_high_impact = [
        item for item in new_findings
        if item.get("advisor") == "supabase_performance" and item.get("severity") != "INFO"
    ]
    new_info = [item for item in new_findings if item.get("severity") == "INFO"]
    if new_security_error_warn or new_performance_high_impact or missing_baseline:
        status = "BLOCKED"
    elif new_info:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"
    return {
        "status": status,
        "compared_by": "stable_baseline_fingerprint",
        "baseline_count": len(before_findings),
        "after_count": len(after_findings),
        "preserved_baseline": preserved,
        "new_findings": new_findings,
        "missing_baseline": missing_baseline,
        "new_security_error_warn": new_security_error_warn,
        "new_performance_high_impact": new_performance_high_impact,
        "new_info_review_required": new_info,
        "baseline_debt_change_requires_review": bool(missing_baseline),
    }


def _schema_key(value: Any) -> Optional[Tuple[str, str, str]]:
    if not isinstance(value, Mapping):
        return None
    kind = value.get("object_kind", value.get("kind"))
    schema = value.get("schema")
    name = value.get("name")
    if not all(isinstance(item, str) and item for item in (kind, schema, name)):
        return None
    return str(kind), str(schema), str(name)


def _schema_items(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        items = value.get("objects")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def compare_schema_object_identities(expected: Any, observed: Any) -> Dict[str, Any]:
    """Compare a full recapture by kind/schema/name and optional signature."""

    expected_items = _schema_items(expected)
    observed_items = _schema_items(observed)
    expected_map = {_schema_key(item): item for item in expected_items if _schema_key(item) is not None}
    observed_map = {_schema_key(item): item for item in observed_items if _schema_key(item) is not None}
    missing = sorted(set(expected_map) - set(observed_map))
    extra = sorted(set(observed_map) - set(expected_map))
    changed: List[Tuple[str, str, str]] = []
    for key in sorted(set(expected_map) & set(observed_map)):
        left = expected_map[key]
        right = observed_map[key]
        for signature_field in ("signature_hash", "definition_hash", "properties_hash"):
            if signature_field in left and signature_field in right and left.get(signature_field) != right.get(signature_field):
                changed.append(key)
                break
    malformed = len(expected_items) != len(expected_map) or len(observed_items) != len(observed_map)
    status = "PASS" if not missing and not extra and not changed and not malformed else "BLOCKED"
    return {
        "status": status,
        "compared_by": ["object_kind", "schema", "name"],
        "missing": [".".join(key) for key in missing],
        "extra": [".".join(key) for key in extra],
        "changed": [".".join(key) for key in changed],
        "malformed_identity_count": (len(expected_items) - len(expected_map)) + (len(observed_items) - len(observed_map)),
        "counts_compared": False,
    }


def classify_post_apply_schema(
    baseline: Any,
    after: Any,
    v4_expected: Any,
) -> Dict[str, Any]:
    """Separate preserved V3.3.3 objects from declared V4 additions/changes."""

    baseline_items = _schema_items(baseline)
    after_items = _schema_items(after)
    expected_v4_items = _schema_items(v4_expected)
    baseline_map = {_schema_key(item): item for item in baseline_items if _schema_key(item) is not None}
    after_map = {_schema_key(item): item for item in after_items if _schema_key(item) is not None}
    v4_map = {_schema_key(item): item for item in expected_v4_items if _schema_key(item) is not None}
    missing = sorted(set(baseline_map) - set(after_map))
    added = sorted(set(after_map) - set(baseline_map))
    v4_added = [key for key in added if key in v4_map or after_map[key].get("attribution") == "V4_DECLARED"]
    unexpected_added = [key for key in added if key not in v4_added]
    changed_preexisting: List[Tuple[str, str, str]] = []
    preserved: List[Tuple[str, str, str]] = []
    for key in sorted(set(baseline_map) & set(after_map)):
        left = baseline_map[key]
        right = after_map[key]
        changed = any(
            field in left and field in right and left.get(field) != right.get(field)
            for field in ("signature_hash", "definition_hash", "properties_hash")
        )
        if changed:
            changed_preexisting.append(key)
        else:
            preserved.append(key)
    status = "PASS" if not missing and not changed_preexisting and not unexpected_added else "BLOCKED"
    return {
        "status": status,
        "compared_by": ["object_kind", "schema", "name"],
        "preserved_v3_3_3": [".".join(key) for key in preserved],
        "v4_added": [".".join(key) for key in v4_added],
        "v4_changed": [".".join(key) for key in added if key in v4_map and key in baseline_map],
        "missing_preexisting": [".".join(key) for key in missing],
        "changed_preexisting": [".".join(key) for key in changed_preexisting],
        "unexpected_added": [".".join(key) for key in unexpected_added],
        "v3_compatibility_change_manifest": [],
    }


def detect_partial_apply(history_rows: Any, expected_sequence: Sequence[str] = EXPECTED_V4_SEQUENCE) -> Dict[str, Any]:
    """Classify V4 history and stop on any non-complete partial state."""

    rows = [row for row in history_rows if isinstance(row, Mapping)] if isinstance(history_rows, list) else []
    seen: List[str] = []
    duplicate: List[str] = []
    invalid: List[str] = []
    failure_rows: List[Mapping[str, Any]] = []
    for row in rows:
        sequence = str(row.get("sequence", ""))
        if sequence in seen:
            duplicate.append(sequence)
        seen.append(sequence)
        if sequence not in expected_sequence:
            invalid.append(sequence)
        if row.get("status") in {"APPLYING", "FAILED", "PARTIAL", "BLOCKED", "PARTIAL_FAIL"} or row.get("partial_state") is True:
            failure_rows.append(row)
    ordered_unique = [sequence for sequence in seen if sequence not in duplicate]
    if not rows:
        state = "NOT_STARTED"
    elif duplicate or invalid or failure_rows:
        state = "FORWARD_FIX_REQUIRED"
    elif ordered_unique == list(expected_sequence):
        state = "COMPLETE"
    elif ordered_unique == list(expected_sequence[: len(ordered_unique)]):
        state = "PARTIAL_APPLY_STOP_REQUIRED"
    else:
        state = "FORWARD_FIX_REQUIRED"
    return {
        "status": "PASS" if state in {"NOT_STARTED", "COMPLETE"} else "BLOCKED",
        "state": state,
        "stop_further_execution": state not in {"NOT_STARTED", "COMPLETE"},
        "do_not_repair_history_manually": True,
        "seen_sequence": ordered_unique,
        "duplicate_sequence": duplicate,
        "invalid_sequence": invalid,
        "failure_rows": [dict(row) for row in failure_rows],
    }


def build_forward_fix_recovery(state: str) -> Dict[str, Any]:
    blocked_state = state in {"FORWARD_FIX_REQUIRED", "PARTIAL_APPLY_STOP_REQUIRED"}
    return {
        "status": "FORWARD_FIX_REQUIRED" if blocked_state else "NO_FORWARD_FIX_REQUIRED",
        "input_state": state,
        "stop_further_execution": blocked_state,
        "retain_history": True,
        "rewrite_history": False,
        "new_forward_identity_required": blocked_state,
        "production_apply_allowed": False,
    }


def verify_git_head_match(current_head: Any, approved_runtime_evidence_head: Any) -> Dict[str, Any]:
    valid_current = isinstance(current_head, str) and GIT_HEAD_RE.fullmatch(current_head) is not None
    valid_approved = isinstance(approved_runtime_evidence_head, str) and GIT_HEAD_RE.fullmatch(approved_runtime_evidence_head) is not None
    matches = valid_current and valid_approved and current_head.lower() == approved_runtime_evidence_head.lower()
    return {
        "status": "PASS" if matches else "BLOCKED",
        "current_git_head": current_head if valid_current else None,
        "approved_runtime_evidence_head": approved_runtime_evidence_head if valid_approved else None,
        "matches": matches,
        "failure_action": "BLOCK",
    }


def _validate_checklist(plan: Mapping[str, Any], issues: List[Issue]) -> None:
    checklist = plan.get("apply_before_checklist")
    if not isinstance(checklist, list):
        issues.append(_issue("PREFLIGHT_CHECKLIST_MISSING", "Apply-before checklist must be a list"))
        return
    ids = [item.get("id") for item in checklist if isinstance(item, Mapping)]
    if ids != list(APPLY_BEFORE_IDS):
        issues.append(_issue("PREFLIGHT_CHECKLIST_COVERAGE", "Apply-before checklist must contain APPLY-01 through APPLY-09 in order"))
    for index, item in enumerate(checklist):
        if not isinstance(item, Mapping):
            issues.append(_issue("PREFLIGHT_CHECKLIST_ITEM_INVALID", "Apply-before checklist item must be an object", f"apply_before_checklist[{index}]"))
            continue
        if item.get("required") is not True or item.get("gate") != "MANDATORY_BEFORE_PRODUCTION_APPLY" or item.get("failure_action") != "BLOCK" or not isinstance(item.get("evidence_ref"), str) or not item.get("evidence_ref"):
            issues.append(_issue("PREFLIGHT_CHECKLIST_ITEM_POLICY", "Every apply-before checklist item must be required, evidence-linked, and blocking", f"apply_before_checklist[{index}]"))
    git_item = next((item for item in checklist if isinstance(item, Mapping) and item.get("id") == "APPLY-06"), None)
    if not git_item or git_item.get("current_head_must_equal_approved_runtime_evidence_head") is not True:
        issues.append(_issue("PREFLIGHT_GIT_HEAD_CHECK_MISSING", "Apply-before checklist must require current Git HEAD equality"))
    hash_item = next((item for item in checklist if isinstance(item, Mapping) and item.get("id") == "APPLY-07"), None)
    if not hash_item or hash_item.get("expected_count") != 9:
        issues.append(_issue("PREFLIGHT_CANONICAL_HASH_CHECK_MISSING", "Apply-before checklist must require nine canonical hashes"))


def _validate_schema_contract(plan: Mapping[str, Any], issues: List[Issue]) -> None:
    value = plan.get("schema_baseline_diff_contract")
    if not isinstance(value, Mapping):
        issues.append(_issue("PREFLIGHT_SCHEMA_CONTRACT_MISSING", "Schema baseline/diff contract is missing"))
        return
    if value.get("compare_by_object_identity") is not True or value.get("counts_are_not_identity_evidence") is not True:
        issues.append(_issue("PREFLIGHT_SCHEMA_IDENTITY_POLICY", "Schema comparison must use object identity and cannot rely on counts"))
    identity_fields = value.get("identity_fields")
    if not isinstance(identity_fields, list) or not {"object_kind", "schema", "name"}.issubset(identity_fields):
        issues.append(_issue("PREFLIGHT_SCHEMA_IDENTITY_FIELDS", "Schema identity fields must include object_kind, schema, and name"))
    if value.get("v3_compatibility_change_manifest") != [] or value.get("unknown_identity_action") != "BLOCK" or value.get("never_auto_repair") is not True:
        issues.append(_issue("PREFLIGHT_SCHEMA_SAFETY_POLICY", "V3.3.3 compatibility and unknown identity policy is unsafe"))


def _validate_partial_and_recovery(plan: Mapping[str, Any], issues: List[Issue]) -> None:
    partial = plan.get("partial_apply_contract")
    if not isinstance(partial, Mapping):
        issues.append(_issue("PREFLIGHT_PARTIAL_CONTRACT_MISSING", "Partial apply contract is missing"))
    else:
        if tuple(partial.get("expected_v4_sequence", [])) != EXPECTED_V4_SEQUENCE:
            issues.append(_issue("PREFLIGHT_PARTIAL_SEQUENCE", "Partial apply contract must declare V4 sequence 0001 through 0009"))
        if partial.get("history_registry") != "governance.schema_migrations" or partial.get("atomic_step_recording") is not True:
            issues.append(_issue("PREFLIGHT_PARTIAL_HISTORY_POLICY", "Partial apply contract must record each step atomically in governance.schema_migrations"))
        on_partial = partial.get("on_partial")
        if not isinstance(on_partial, Mapping) or on_partial.get("stop_further_execution") is not True or on_partial.get("state") != "FORWARD_FIX_REQUIRED" or on_partial.get("do_not_repair_or_fake_history_manually", on_partial.get("do_not_fake_or_repair_history_manually")) is not True:
            issues.append(_issue("PREFLIGHT_PARTIAL_STOP_POLICY", "Partial apply must stop and require forward fix without manual history repair"))
    recovery = plan.get("forward_fix_recovery_contract")
    if not isinstance(recovery, Mapping) or recovery.get("historical_rollback_rewrite") is not False or recovery.get("recovery_path") != "FORWARD_FIX_REQUIRED" or recovery.get("transaction_per_safe_migration") is not True or recovery.get("irreversible_ddl_review_required") is not True or recovery.get("no_history_repair_by_hand") is not True:
        issues.append(_issue("PREFLIGHT_FORWARD_FIX_POLICY", "Forward-fix/recovery contract is incomplete or unsafe"))


def _validate_post_apply(plan: Mapping[str, Any], issues: List[Issue]) -> None:
    value = plan.get("post_apply_verification_plan")
    if not isinstance(value, list) or [item.get("id") for item in value if isinstance(item, Mapping)] != list(POST_APPLY_IDS):
        issues.append(_issue("PREFLIGHT_POST_APPLY_COVERAGE", "Post-apply verification plan must contain POST-01 through POST-14 in order"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or item.get("required") is not True or item.get("failure_action") != "BLOCK_ACCEPTANCE" or not isinstance(item.get("evidence_ref"), str) or not item.get("evidence_ref"):
            issues.append(_issue("PREFLIGHT_POST_APPLY_ITEM_POLICY", "Every post-apply verification must be required, evidence-linked, and acceptance-blocking", f"post_apply_verification_plan[{index}]"))


def _validate_approval_and_boundary(plan: Mapping[str, Any], issues: List[Issue]) -> None:
    approval = plan.get("approval_separation")
    if not isinstance(approval, Mapping):
        issues.append(_issue("PREFLIGHT_APPROVAL_SEPARATION_MISSING", "Approval separation contract is missing"))
    else:
        binding = approval.get("target_binding_approval")
        preflight = approval.get("preflight_plan")
        final_review = approval.get("final_review")
        if not isinstance(binding, Mapping) or binding.get("state") != "BOUND_APPROVED" or binding.get("authorizes_apply") is not False:
            issues.append(_issue("PREFLIGHT_BINDING_APPROVAL_MIXED", "Target binding approval must not authorize apply"))
        if not isinstance(preflight, Mapping) or preflight.get("state") != "PASS" or preflight.get("authorizes_apply") is not False:
            issues.append(_issue("PREFLIGHT_PASS_APPROVAL_MIXED", "Preflight PASS must not authorize apply"))
        if not isinstance(final_review, Mapping) or final_review.get("required") is not True or final_review.get("decision") != "READY_FOR_PRODUCTION_APPLY_APPROVAL" or final_review.get("approval_state") != "PENDING_PRODUCTION_APPLY_APPROVAL":
            issues.append(_issue("PREFLIGHT_FINAL_REVIEW_POLICY", "Final Review must precede explicit Production Apply Approval"))
        if approval.get("explicit_apply_approval_required") is not True or approval.get("production_apply_allowed") is not False or approval.get("same_agent_may_not_approve_and_execute") is not True:
            issues.append(_issue("PREFLIGHT_APPLY_GATE_POLICY", "Production apply gate must remain explicit and closed"))
    boundary = plan.get("execution_boundary")
    required_boundary = {
        "production_apply_invoked": False,
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
        "ddl_executed": False,
        "dml_executed": False,
        "batch_04_executed": "NO",
        "v4_018_v4_019_changed": "NO",
        "v333_mutated": "NO",
        "automatic_apply": False,
    }
    if not isinstance(boundary, Mapping) or any(boundary.get(key) != value for key, value in required_boundary.items()):
        issues.append(_issue("PREFLIGHT_EXECUTION_BOUNDARY", "Preflight plan execution boundary reports a forbidden operation"))


def validate_supabase_preflight_plan_document(plan: Any, binding: Optional[Mapping[str, Any]] = None) -> List[Issue]:
    """Validate the checked-in plan and its supplied Production baseline."""

    if not isinstance(plan, Mapping):
        return [_issue("PREFLIGHT_PLAN_INVALID", "Supabase preflight plan must be an object")]
    issues: List[Issue] = list(_walk_sensitive_keys(plan))
    if plan.get("$id") != PREFLIGHT_PLAN_ID or plan.get("contract_version") != PREFLIGHT_PLAN_ID:
        issues.append(_issue("PREFLIGHT_PLAN_VERSION", "Supabase preflight plan version is not approved"))
    if plan.get("contract_state") != "ACTIVE" or plan.get("scope") != PREFLIGHT_PLAN_SCOPE or plan.get("plan_status") != "PASS":
        issues.append(_issue("PREFLIGHT_PLAN_STATE", "Supabase preflight plan must be ACTIVE and PASS"))
    if plan.get("target_binding_source") != "config/migration_harness/v4_production_target_identity.json":
        issues.append(_issue("PREFLIGHT_BINDING_SOURCE", "Preflight plan must point to the Production target binding contract"))
    baseline = plan.get("production_baseline")
    if not isinstance(baseline, Mapping):
        issues.append(_issue("PREFLIGHT_BASELINE_MISSING", "Production baseline snapshot is missing"))
    else:
        _validate_baseline_target(baseline, binding, issues)
        _validate_database_identity(baseline, issues)
        capture = baseline.get("capture")
        if not isinstance(capture, Mapping) or capture.get("capture_source") != CAPTURE_SOURCE or capture.get("read_only") is not True or capture.get("production_writes_performed") != "NO" or not isinstance(capture.get("captured_at"), str) or not capture.get("captured_at"):
            issues.append(_issue("PREFLIGHT_CAPTURE_METADATA", "Baseline capture source/time/read-only metadata is incomplete"))
        history = baseline.get("migration_history")
        if not isinstance(history, Mapping) or history.get("count") != 9 or history.get("exact_baseline_required") is not True or history.get("drift_action") != "BLOCK_UNLESS_EXPLICITLY_REVIEWED":
            issues.append(_issue("PREFLIGHT_BASELINE_HISTORY_POLICY", "Baseline history must require exact nine-entry recapture with reviewed drift"))
        else:
            issues.extend(validate_baseline_migration_history(history.get("entries")))
        counts = baseline.get("schema_counts")
        if counts != EXPECTED_BASELINE_COUNTS:
            issues.append(_issue("PREFLIGHT_BASELINE_SCHEMA_COUNTS", "Baseline public schema counts do not match the supplied Production evidence"))
        identities = baseline.get("schema_object_identities")
        if not isinstance(identities, Mapping) or not isinstance(identities.get("known_identity_samples"), list) or not identities.get("known_identity_samples") or identities.get("comparison_by") != "OBJECT_IDENTITY" or identities.get("full_identity_recapture_required_before_apply") is not True:
            issues.append(_issue("PREFLIGHT_BASELINE_IDENTITIES", "Baseline object identity samples and full recapture requirement are missing"))
        else:
            for index, item in enumerate(identities["known_identity_samples"]):
                if not isinstance(item, Mapping) or not _schema_key(item) or item.get("attribution") != BASELINE_OBJECT_ATTRIBUTION:
                    issues.append(_issue("PREFLIGHT_BASELINE_IDENTITY_INVALID", "Baseline identity sample is malformed or not attributed to V3.3.3", f"known_identity_samples[{index}]"))
        v333 = baseline.get("v333_isolation")
        if not isinstance(v333, Mapping) or v333.get("compatibility_change_manifest") != [] or v333.get("v4_must_not_modify") is not True:
            issues.append(_issue("PREFLIGHT_V333_ISOLATION", "V3.3.3 isolation baseline is incomplete"))
        issues.extend(validate_advisor_baseline(plan))
    _validate_checklist(plan, issues)
    _validate_schema_contract(plan, issues)
    advisor_contract = plan.get("advisor_before_after_contract")
    if not isinstance(advisor_contract, Mapping) or advisor_contract.get("baseline_attribution") != BASELINE_ATTRIBUTION or advisor_contract.get("new_security_error_warn_action") != "BLOCK" or advisor_contract.get("comparison_requires_before_and_after") is not True:
        issues.append(_issue("PREFLIGHT_ADVISOR_POLICY", "Advisor before/after policy is incomplete"))
    _validate_partial_and_recovery(plan, issues)
    _validate_post_apply(plan, issues)
    _validate_approval_and_boundary(plan, issues)
    hashes = plan.get("canonical_hash_contract")
    if not isinstance(hashes, Mapping) or hashes.get("expected_count") != 9 or hashes.get("verification_mode") != "VERIFY_ONLY_NO_WRITE" or hashes.get("expected_status") != "PASS" or hashes.get("pending_count") != 0:
        issues.append(_issue("PREFLIGHT_CANONICAL_HASH_POLICY", "Canonical hash policy must require a 9/9 verify-only result"))
    secret_policy = plan.get("secret_policy")
    if not isinstance(secret_policy, Mapping) or secret_policy.get("secret_fields_present") is not False or secret_policy.get("raw_secret_values_present") is not False or secret_policy.get("credential_source") != "PROCESS_ENVIRONMENT_ONLY" or any(secret_policy.get(key) is not False for key in ("persist_values", "log_values", "report_values")):
        issues.append(_issue("PREFLIGHT_SECRET_POLICY", "Preflight secret policy is unsafe or incomplete"))
    projection = plan.get("final_readiness_projection")
    if not isinstance(projection, Mapping) or projection.get("production_target_identity") != "KNOWN" or projection.get("supabase_preflight_plan") != "PASS" or projection.get("decision") != "READY_FOR_PRODUCTION_APPLY_APPROVAL" or projection.get("apply_gate") != "CLOSED_PENDING_EXPLICIT_APPROVAL":
        issues.append(_issue("PREFLIGHT_READINESS_PROJECTION", "Final readiness projection does not preserve the closed apply gate"))
    return issues


def build_supabase_preflight_report(repo_root: Path, binding: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a redacted static completion report; no target is contacted."""

    root = Path(repo_root).resolve()
    if binding is None:
        try:
            loaded_binding = read_json(root / "config/migration_harness/v4_production_target_identity.json")
        except (OSError, ValueError, TypeError):
            loaded_binding = None
        binding = loaded_binding if isinstance(loaded_binding, Mapping) else None
    try:
        plan = load_supabase_preflight_plan(root)
    except (OSError, ValueError, TypeError):
        plan = None
    issues = validate_supabase_preflight_plan_document(plan, binding=binding)
    hash_report = verify_candidate_hashes(root)
    hash_pass = hash_report.get("status") == "PASS" and hash_report.get("candidate_count") == 9 and hash_report.get("matched_count") == 9 and hash_report.get("pending_count") == 0
    checks = {
        "contract_completeness": {"status": "PASS" if not issues else "FAIL", "issue_count": len(issues)},
        "baseline_project_binding": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_BASELINE_TARGET") or issue.code.startswith("PREFLIGHT_BINDING") for issue in issues) else "FAIL"},
        "baseline_database_identity": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_DATABASE") or issue.code.startswith("PREFLIGHT_SERVER") or issue.code.startswith("PREFLIGHT_POSTGRES") for issue in issues) else "FAIL"},
        "baseline_migration_history": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_BASELINE_HISTORY") for issue in issues) else "FAIL", "captured_count": 9},
        "baseline_schema_counts": {"status": "PASS" if not any(issue.code == "PREFLIGHT_BASELINE_SCHEMA_COUNTS" for issue in issues) else "FAIL", "counts": dict(EXPECTED_BASELINE_COUNTS)},
        "baseline_schema_object_identities": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_BASELINE_IDENTIT") for issue in issues) else "FAIL", "comparison": "OBJECT_IDENTITY", "full_recapture_required_before_apply": True},
        "schema_baseline_diff_contract": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_SCHEMA_") for issue in issues) else "FAIL", "comparison": "OBJECT_IDENTITY"},
        "security_advisor_baseline": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_ADVISOR") for issue in issues) else "FAIL", "pre_existing_debt_isolated": True},
        "performance_advisor_baseline": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_ADVISOR") for issue in issues) else "FAIL", "new_regressions_policy": "BLOCK"},
        "pre_existing_security_debt_isolated": {"status": "PASS" if not any(issue.code in {"PREFLIGHT_ADVISOR_ATTRIBUTION_INVALID", "PREFLIGHT_V333_ISOLATION"} for issue in issues) else "FAIL"},
        "advisor_before_after_contract": {"status": "PASS" if not any(issue.code == "PREFLIGHT_ADVISOR_POLICY" for issue in issues) else "FAIL", "new_security_error_warn": "BLOCK"},
        "v333_isolation": {"status": "PASS" if not any(issue.code == "PREFLIGHT_V333_ISOLATION" for issue in issues) else "FAIL"},
        "partial_apply_detection": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_PARTIAL") for issue in issues) else "FAIL", "expected_sequence": list(EXPECTED_V4_SEQUENCE)},
        "forward_fix_recovery": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_FORWARD_FIX") for issue in issues) else "FAIL"},
        "post_apply_verification": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_POST_APPLY") for issue in issues) else "FAIL", "count": len(POST_APPLY_IDS)},
        "approval_separation": {"status": "PASS" if not any(issue.code.startswith(prefix) for issue in issues for prefix in ("PREFLIGHT_APPROVAL", "PREFLIGHT_BINDING_APPROVAL", "PREFLIGHT_PASS_APPROVAL", "PREFLIGHT_FINAL_REVIEW", "PREFLIGHT_APPLY_GATE")) else "FAIL", "apply_allowed": False},
        "production_hard_block": {"status": "PASS" if not any(issue.code == "PREFLIGHT_EXECUTION_BOUNDARY" for issue in issues) else "FAIL", "apply_allowed": False},
        "canonical_hashes": {"status": "PASS" if hash_pass else "FAIL", "candidate_count": hash_report.get("candidate_count", 0), "matched_count": hash_report.get("matched_count", 0), "pending_count": hash_report.get("pending_count", 0)},
        "secret_policy": {"status": "PASS" if not any(issue.code.startswith("PREFLIGHT_SECRET") for issue in issues) else "FAIL"},
    }
    static_pass = not issues and hash_pass
    return {
        "status": "PASS" if static_pass else "FAIL",
        "source": PREFLIGHT_PLAN_PATH,
        "production_project_ref": PRODUCTION_PROJECT_REF,
        "production_target_identity": "KNOWN" if _binding_target(binding) is not None else "FAIL",
        "supabase_preflight_plan": "PASS" if static_pass else "FAIL",
        "final_readiness_decision": "READY_FOR_PRODUCTION_APPLY_APPROVAL" if static_pass else "BLOCKED",
        "production_apply_allowed": False,
        "explicit_apply_approval_required": True,
        "checks": checks,
        "baseline": plan.get("production_baseline") if isinstance(plan, Mapping) else None,
        "apply_before_checklist": plan.get("apply_before_checklist") if isinstance(plan, Mapping) else [],
        "issues": [issue.to_dict() for issue in issues],
        "canonical_hash_report": hash_report,
        "execution_boundary": {
            "database_connected": False,
            "sql_executed": False,
            "ddl_executed": False,
            "dml_executed": False,
            "production_db_writes_performed": "NO",
            "supabase_writes_performed": "NO",
            "batch_04_executed": "NO",
            "v4_018_v4_019_changed": "NO",
            "v333_mutated": "NO",
        },
        "next_stage": "BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3",
    }
