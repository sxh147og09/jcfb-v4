"""Production target identity binding and read-only readiness evidence.

The binding contract records only non-secret identity metadata.  It proves
which Supabase project is the named Production target; it never grants an
apply permission and never opens a database connection.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .common import TARGET_ID_RE, read_json
from .models import CheckStatus, Issue


PRODUCTION_TARGET_IDENTITY_PATH = "config/migration_harness/v4_production_target_identity.json"
PRODUCTION_TARGET_IDENTITY_SCHEMA_PATH = "config/migration_harness/v4_production_target_identity.schema.json"
PRODUCTION_TARGET_IDENTITY_CONTRACT_VERSION = "v4-production-target-identity@1.0.0"
PRODUCTION_TARGET_IDENTITY_SCOPE = "JCFB_V4_PRODUCTION_TARGET_BINDING"
PRODUCTION_PROJECT_REF = "icndieflfvydixtehgzu"
PRODUCTION_REGION = "us-west-2"
PRODUCTION_POSTGRES_MAJOR = 17
PRODUCTION_PROVIDER = "Supabase"
PRODUCTION_BINDING_STATE = "BOUND_APPROVED"
PRODUCTION_APPROVED_BY = "human_approver"
PRODUCTION_APPROVAL_BASIS = "explicit user confirmation in ChatGPT"
PRODUCTION_APPLY_APPROVAL_STATE = "PENDING_PRODUCTION_APPLY_APPROVAL"
PRODUCTION_APPLY_APPROVAL_SCOPE = "EXPLICIT_PRODUCTION_APPLY_APPROVAL"

ENVIRONMENTS = ("DISPOSABLE_LOCAL", "STAGING", "PRODUCTION")
NON_PRODUCTION_ENVIRONMENTS = {"DISPOSABLE_LOCAL", "STAGING"}
PROVIDERS_BY_ENVIRONMENT = {
    "DISPOSABLE_LOCAL": {"LOCAL_POSTGRES", "DOCKER_POSTGRES"},
    "STAGING": {"STAGING_POSTGRES", "STAGING_SUPABASE"},
    "PRODUCTION": {PRODUCTION_PROVIDER},
}
TARGET_FIELDS = {
    "environment",
    "target_id",
    "provider",
    "project_ref",
    "region",
    "postgres_major",
    "role",
    "binding_state",
    "approved_by",
    "approval_basis",
    "display_name",
}
ROOT_FIELDS = {
    "$schema",
    "$id",
    "contract_version",
    "contract_state",
    "scope",
    "identity_primary_key",
    "targets",
    "production_apply_gate",
    "secret_policy",
}
SENSITIVE_FIELD_NAMES = {
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
SENSITIVE_FIELD_SUFFIXES = tuple(
    f"_{name}"
    for name in (
        "url",
        "password",
        "token",
        "api_key",
        "service_role_key",
        "private_key",
        "cookie",
        "secret",
        "secret_value",
        "connection_string",
        "connection_uri",
    )
)
SUPABASE_PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
REGION_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


@dataclass(frozen=True)
class ProductionTargetBindingValidation:
    """Redacted result of validating the checked-in binding contract."""

    status: CheckStatus
    issues: Sequence[Issue]
    production_target: Optional[Dict[str, Any]] = None
    exactly_one_production_target: bool = False
    disposable_production_isolated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == CheckStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "production_target": dict(self.production_target) if self.production_target else None,
            "exactly_one_production_target": self.exactly_one_production_target,
            "disposable_production_isolated": self.disposable_production_isolated,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(code: str, message: str, location: Optional[str] = None) -> Issue:
    return Issue(code, message, location)


def load_production_target_binding(repo_root: Path) -> Dict[str, Any]:
    """Load the non-secret Production target binding contract."""

    return read_json(Path(repo_root) / PRODUCTION_TARGET_IDENTITY_PATH)


def _looks_sensitive_key(key: Any) -> bool:
    key_text = str(key).lower()
    return key_text in SENSITIVE_FIELD_NAMES or any(key_text.endswith(suffix) for suffix in SENSITIVE_FIELD_SUFFIXES)


def _walk_sensitive_fields(value: Any, path: str = "") -> Iterable[Issue]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            location = f"{path}.{key_text}" if path else key_text
            if _looks_sensitive_key(key_text):
                yield _issue("SECRET_FIELD_PRESENT", "Secret or connection material is not allowed in a binding contract", location)
            yield from _walk_sensitive_fields(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_sensitive_fields(child, f"{path}[{index}]")


def _safe_target(target: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(target, Mapping):
        return None
    safe = {
        key: target.get(key)
        for key in (
            "target_id",
            "environment",
            "provider",
            "project_ref",
            "region",
            "postgres_major",
            "role",
            "binding_state",
            "approved_by",
            "approval_basis",
            "display_name",
        )
        if key in target
    }
    return safe


def _target_rows(contract: Mapping[str, Any]) -> List[Dict[str, Any]]:
    targets = contract.get("targets")
    return [dict(item) for item in targets if isinstance(item, Mapping)] if isinstance(targets, list) else []


def validate_production_target_binding(contract: Optional[Mapping[str, Any]]) -> ProductionTargetBindingValidation:
    """Validate exact-one Production identity, isolation, and apply separation."""

    if not isinstance(contract, Mapping):
        return ProductionTargetBindingValidation(
            status=CheckStatus.FAIL,
            issues=[_issue("PRODUCTION_BINDING_INVALID", "Production target binding must be an object")],
        )

    issues: List[Issue] = list(_walk_sensitive_fields(contract))
    unknown_root = sorted(set(contract) - ROOT_FIELDS)
    issues.extend(
        _issue("BINDING_FIELD_UNKNOWN", "Binding contract contains an unknown root field", key)
        for key in unknown_root
    )
    required_root = (
        "$schema",
        "$id",
        "contract_version",
        "contract_state",
        "scope",
        "identity_primary_key",
        "targets",
        "production_apply_gate",
        "secret_policy",
    )
    issues.extend(
        _issue("BINDING_FIELD_MISSING", "Required binding contract field is missing", field)
        for field in required_root
        if field not in contract
    )
    if contract.get("$id") != PRODUCTION_TARGET_IDENTITY_CONTRACT_VERSION:
        issues.append(_issue("BINDING_ID_INVALID", "Binding contract id is not the approved contract"))
    if contract.get("contract_version") != PRODUCTION_TARGET_IDENTITY_CONTRACT_VERSION:
        issues.append(_issue("BINDING_VERSION_INVALID", "Binding contract version is not approved"))
    if contract.get("contract_state") != "ACTIVE":
        issues.append(_issue("BINDING_STATE_INVALID", "Binding contract must be active"))
    if contract.get("scope") != PRODUCTION_TARGET_IDENTITY_SCOPE:
        issues.append(_issue("BINDING_SCOPE_INVALID", "Binding contract scope is not Production target binding"))
    if contract.get("identity_primary_key") != "project_ref":
        issues.append(_issue("IDENTITY_PRIMARY_KEY_INVALID", "project_ref must remain the unique target identity key"))

    targets_value = contract.get("targets")
    if not isinstance(targets_value, list):
        issues.append(_issue("TARGET_LIST_INVALID", "Binding contract targets must be a list", "targets"))
        targets: List[Dict[str, Any]] = []
    else:
        targets = _target_rows(contract)
        if len(targets) != len(targets_value):
            issues.append(_issue("TARGET_ENTRY_INVALID", "Every binding target must be an object", "targets"))
        if len(targets_value) != 3:
            issues.append(_issue("TARGET_ENVIRONMENT_COUNT_INVALID", "Binding contract must declare the three V4 environments", "targets"))

    seen_target_ids: List[str] = []
    seen_environments: List[str] = []
    for index, target in enumerate(targets):
        location = f"targets[{index}]"
        unknown_fields = sorted(set(target) - TARGET_FIELDS)
        issues.extend(
            _issue("TARGET_FIELD_UNKNOWN", "Binding target contains an unknown field", f"{location}.{field}")
            for field in unknown_fields
        )
        for field in ("environment", "target_id", "provider", "project_ref", "region", "postgres_major", "role", "binding_state"):
            if field not in target:
                issues.append(_issue("TARGET_FIELD_MISSING", "Required binding target field is missing", f"{location}.{field}"))

        environment = target.get("environment")
        if environment not in ENVIRONMENTS:
            issues.append(_issue("TARGET_ENVIRONMENT_INVALID", "Binding target environment is not recognized", f"{location}.environment"))
        else:
            seen_environments.append(environment)
        target_id = target.get("target_id")
        if not isinstance(target_id, str) or not TARGET_ID_RE.fullmatch(target_id):
            issues.append(_issue("TARGET_ID_INVALID", "Binding target id must be lowercase and path-safe", f"{location}.target_id"))
        elif target_id in seen_target_ids:
            issues.append(_issue("TARGET_ID_DUPLICATE", "Binding target ids must be unique", f"{location}.target_id"))
        else:
            seen_target_ids.append(target_id)

        provider = target.get("provider")
        if provider not in PROVIDERS_BY_ENVIRONMENT.get(environment, set()):
            issues.append(_issue("TARGET_PROVIDER_INVALID", "Provider does not match binding environment", f"{location}.provider"))
        if target.get("role") != environment:
            issues.append(_issue("TARGET_ROLE_ENVIRONMENT_MISMATCH", "Target role must match its environment", f"{location}.role"))

        binding_state = target.get("binding_state")
        if environment == "PRODUCTION":
            if binding_state != PRODUCTION_BINDING_STATE:
                issues.append(_issue("PRODUCTION_BINDING_STATE_INVALID", "Production target must be BOUND_APPROVED", f"{location}.binding_state"))
            project_ref = target.get("project_ref")
            if not isinstance(project_ref, str) or not project_ref.strip():
                issues.append(_issue("PRODUCTION_PROJECT_REF_MISSING", "Production project_ref must be non-empty", f"{location}.project_ref"))
            elif not SUPABASE_PROJECT_REF_RE.fullmatch(project_ref):
                issues.append(_issue("PRODUCTION_PROJECT_REF_INVALID", "Production project_ref is not a basic Supabase ref", f"{location}.project_ref"))
            if project_ref != PRODUCTION_PROJECT_REF:
                issues.append(_issue("PRODUCTION_PROJECT_REF_UNEXPECTED", "Production project_ref does not match the approved binding", f"{location}.project_ref"))
            if provider != PRODUCTION_PROVIDER:
                issues.append(_issue("PRODUCTION_PROVIDER_INVALID", "Production provider must be Supabase", f"{location}.provider"))
            if target.get("region") != PRODUCTION_REGION or not isinstance(target.get("region"), str) or not REGION_RE.fullmatch(target.get("region", "")):
                issues.append(_issue("PRODUCTION_REGION_INVALID", "Production region does not match the approved binding", f"{location}.region"))
            postgres_major = target.get("postgres_major")
            if isinstance(postgres_major, bool) or not isinstance(postgres_major, int) or postgres_major != PRODUCTION_POSTGRES_MAJOR:
                issues.append(_issue("PRODUCTION_POSTGRES_MAJOR_INVALID", "Production postgres_major does not match the approved binding", f"{location}.postgres_major"))
            if target.get("approved_by") != PRODUCTION_APPROVED_BY:
                issues.append(_issue("HUMAN_APPROVAL_RECORD_INVALID", "Production binding must record approved_by=human_approver", f"{location}.approved_by"))
            if target.get("approval_basis") != PRODUCTION_APPROVAL_BASIS:
                issues.append(_issue("APPROVAL_BASIS_INVALID", "Production binding must record the explicit ChatGPT confirmation basis", f"{location}.approval_basis"))
        elif environment in NON_PRODUCTION_ENVIRONMENTS:
            if binding_state != "NOT_BOUND":
                issues.append(_issue("NON_PRODUCTION_BINDING_STATE_INVALID", "Disposable and staging targets must remain NOT_BOUND in this contract", f"{location}.binding_state"))
            if target.get("approved_by") is not None or target.get("approval_basis") is not None:
                issues.append(_issue("NON_PRODUCTION_APPROVAL_INVALID", "Non-production targets cannot carry Production approval metadata", location))

    exactly_one_production = seen_environments.count("PRODUCTION") == 1
    if not exactly_one_production:
        issues.append(_issue("EXACTLY_ONE_PRODUCTION_TARGET", "Binding contract must contain exactly one Production target"))
    if set(seen_environments) != set(ENVIRONMENTS):
        issues.append(_issue("TARGET_ENVIRONMENT_SET_INVALID", "Binding contract must distinguish DISPOSABLE_LOCAL, STAGING, and PRODUCTION"))

    production_targets = [target for target in targets if target.get("environment") == "PRODUCTION"]
    production_target = _safe_target(production_targets[0]) if len(production_targets) == 1 else None
    production_project_ref = production_targets[0].get("project_ref") if len(production_targets) == 1 else None
    production_target_id = production_targets[0].get("target_id") if len(production_targets) == 1 else None
    isolated = bool(production_target) and all(
        target.get("target_id") != production_target_id
        and (
            production_project_ref is None
            or target.get("project_ref") is None
            or target.get("project_ref") != production_project_ref
        )
        for target in targets
        if target.get("environment") != "PRODUCTION"
    )
    if not isolated:
        issues.append(_issue("PRODUCTION_TARGET_ISOLATION_INVALID", "Production target must differ from disposable and staging identities"))

    gate = contract.get("production_apply_gate")
    if not isinstance(gate, Mapping):
        issues.append(_issue("PRODUCTION_APPLY_GATE_MISSING", "Production apply gate must be an object", "production_apply_gate"))
    else:
        if gate.get("hard_block_preserved") is not True:
            issues.append(_issue("PRODUCTION_HARD_BLOCK_NOT_PRESERVED", "Production hard block must remain true", "production_apply_gate.hard_block_preserved"))
        if gate.get("explicit_approval_required") is not True:
            issues.append(_issue("EXPLICIT_APPLY_APPROVAL_REQUIRED", "Production apply must require explicit approval", "production_apply_gate.explicit_approval_required"))
        if gate.get("target_binding_authorizes_apply") is not False:
            issues.append(_issue("BINDING_MUST_NOT_AUTHORIZE_APPLY", "Target binding must not authorize Production apply", "production_apply_gate.target_binding_authorizes_apply"))
        if gate.get("approval_state") != PRODUCTION_APPLY_APPROVAL_STATE:
            issues.append(_issue("PRODUCTION_APPLY_APPROVAL_STATE_INVALID", "Production apply approval must remain pending", "production_apply_gate.approval_state"))
        if gate.get("approval_scope") != PRODUCTION_APPLY_APPROVAL_SCOPE:
            issues.append(_issue("PRODUCTION_APPLY_APPROVAL_SCOPE_INVALID", "Production apply approval scope is not explicit", "production_apply_gate.approval_scope"))

    secret_policy = contract.get("secret_policy")
    if not isinstance(secret_policy, Mapping):
        issues.append(_issue("SECRET_POLICY_MISSING", "Binding contract must declare its no-secret policy", "secret_policy"))
    else:
        if secret_policy.get("secrets_stored") is not False:
            issues.append(_issue("SECRETS_STORED_IN_BINDING", "Binding contract must not store secrets", "secret_policy.secrets_stored"))
        if secret_policy.get("raw_values_allowed") is not False:
            issues.append(_issue("RAW_SECRET_VALUES_ALLOWED", "Raw credential values must not be allowed", "secret_policy.raw_values_allowed"))
        if secret_policy.get("credential_source") != "PROCESS_ENVIRONMENT_ONLY":
            issues.append(_issue("CREDENTIAL_SOURCE_INVALID", "Credentials must remain process-environment-only", "secret_policy.credential_source"))

    return ProductionTargetBindingValidation(
        status=CheckStatus.PASS if not issues else CheckStatus.FAIL,
        issues=issues,
        production_target=production_target,
        exactly_one_production_target=exactly_one_production,
        disposable_production_isolated=isolated,
    )


def _apply_gate_snapshot(contract: Mapping[str, Any], validation: ProductionTargetBindingValidation) -> Dict[str, Any]:
    gate = contract.get("production_apply_gate") if isinstance(contract.get("production_apply_gate"), Mapping) else {}
    hard_block = gate.get("hard_block_preserved") is True
    explicit_required = gate.get("explicit_approval_required") is True
    binding_authorizes_apply = gate.get("target_binding_authorizes_apply") is True
    approval_pending = gate.get("approval_state") == PRODUCTION_APPLY_APPROVAL_STATE
    return {
        "status": "PASS" if validation.ok and hard_block and explicit_required and not binding_authorizes_apply and approval_pending else "FAIL",
        "hard_block_preserved": hard_block,
        "explicit_approval_required": explicit_required,
        "approval_granted": False,
        "approval_state": gate.get("approval_state"),
        "target_binding_authorizes_apply": binding_authorizes_apply,
        "production_apply_allowed": False,
    }


def production_target_binding_report(repo_root: Path) -> Dict[str, Any]:
    """Return a redacted, read-only binding report for human review."""

    root = Path(repo_root).resolve()
    try:
        contract = load_production_target_binding(root)
    except (OSError, ValueError, TypeError):
        contract = None
    validation = validate_production_target_binding(contract)
    contract_value = contract if isinstance(contract, Mapping) else {}
    production_target = validation.production_target
    identity_known = validation.ok and validation.exactly_one_production_target and bool(production_target)
    gate = _apply_gate_snapshot(contract_value, validation)
    secret_policy = contract_value.get("secret_policy") if isinstance(contract_value.get("secret_policy"), Mapping) else {}
    human_approval_recorded = bool(
        production_target
        and production_target.get("approved_by") == PRODUCTION_APPROVED_BY
        and production_target.get("approval_basis") == PRODUCTION_APPROVAL_BASIS
    )
    return {
        "status": "PASS" if validation.ok else "FAIL",
        "contract_version": contract_value.get("contract_version"),
        "source": PRODUCTION_TARGET_IDENTITY_PATH,
        "identity_primary_key": contract_value.get("identity_primary_key"),
        "production_target_identity": "KNOWN" if identity_known else "FAIL",
        "production_target": production_target,
        "human_approval_recorded": "PASS" if human_approval_recorded else "FAIL",
        "exactly_one_production_target": "PASS" if validation.exactly_one_production_target else "FAIL",
        "disposable_production_isolation": "PASS" if validation.disposable_production_isolated else "FAIL",
        "secrets_stored": "NO" if secret_policy.get("secrets_stored") is False else "YES",
        "secret_values_present": False,
        "production_hard_block_preserved": "PASS" if gate["hard_block_preserved"] else "FAIL",
        "explicit_apply_approval_required": "PASS" if gate["explicit_approval_required"] else "FAIL",
        "production_apply_gate": gate,
        "supabase_preflight_plan": {
            "status": "INCOMPLETE",
            "automatic_pass": False,
            "reason": "Target binding records identity only; Supabase security/advisor and schema baseline evidence remain separate",
            "next_stage": "SUPABASE_PREFLIGHT_PLAN_COMPLETION",
        },
        "issues": [issue.to_dict() for issue in validation.issues],
        "database_connected": False,
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
    }


def build_production_readiness_review(repo_root: Path) -> Dict[str, Any]:
    """Build the identity-only Production Readiness review input."""

    binding = production_target_binding_report(repo_root)
    return {
        "status": "IDENTITY_KNOWN_PREFLIGHT_INCOMPLETE" if binding["production_target_identity"] == "KNOWN" else "BLOCKED_PRODUCTION_TARGET_BINDING",
        "production_target_identity": binding["production_target_identity"],
        "production_target_binding": binding,
        "supabase_preflight_plan": binding["supabase_preflight_plan"],
        "production_apply_gate": binding["production_apply_gate"],
        "production_apply_approval_required": True,
        "production_apply_allowed": False,
        "database_connected": False,
        "production_db_writes_performed": "NO",
        "supabase_writes_performed": "NO",
        "batch_04_executed": "NO",
    }


def run_production_target_cross_doc_consistency(repo_root: Path) -> Dict[str, Any]:
    """Check that the binding, policy, readiness, and operator docs agree."""

    root = Path(repo_root).resolve()
    checks: List[str] = []
    failures: List[str] = []

    requirements = {
        "docs/V4_PRODUCTION_TARGET_BINDING.md": (
            PRODUCTION_TARGET_IDENTITY_PATH,
            "target binding does not authorize Production apply",
            "SUPABASE_PREFLIGHT_PLAN_COMPLETION",
        ),
        "docs/V4_PRODUCTION_POLICY.md": (
            "docs/V4_PRODUCTION_TARGET_BINDING.md",
            "Target binding does not equal Production apply approval",
        ),
        "docs/V4_RUNTIME_ROLE_BOUNDARY.md": ("project_ref", "BOUND_APPROVED", "PRODUCTION"),
        "docs/V4_MIGRATION_PREFLIGHT.md": (PRODUCTION_TARGET_IDENTITY_PATH, "target identity is known", "preflight"),
        "README.md": ("docs/V4_PRODUCTION_TARGET_BINDING.md", "V4-018 NEXT", "Production apply approval"),
    }
    for relative, needles in requirements.items():
        path = root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        content = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle.lower() in content.lower():
                checks.append(f"{relative}:{needle}")
            else:
                failures.append(f"missing-text:{relative}:{needle}")

    schema_path = root / PRODUCTION_TARGET_IDENTITY_SCHEMA_PATH
    contract_path = root / PRODUCTION_TARGET_IDENTITY_PATH
    if schema_path.is_file() and contract_path.is_file():
        checks.append("binding-contract-and-schema:present")
    else:
        failures.append("binding-contract-and-schema:missing")
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "source": PRODUCTION_TARGET_IDENTITY_PATH,
    }
