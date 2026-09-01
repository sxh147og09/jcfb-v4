"""Target descriptor validation and the hard production boundary."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import CREDENTIAL_ENV_RE, TARGET_ID_RE, is_non_empty_string
from .models import CheckStatus, Issue, TargetValidation


ALLOWED_ENVIRONMENTS = {"DISPOSABLE_LOCAL", "STAGING"}
ALL_ENVIRONMENTS = ALLOWED_ENVIRONMENTS | {"PRODUCTION"}
ALLOWED_PROVIDERS = {
    "LOCAL_POSTGRES",
    "DOCKER_POSTGRES",
    "STAGING_POSTGRES",
    "STAGING_SUPABASE",
    "PRODUCTION_SUPABASE",
}
REQUIRED_DATABASE_IDENTITY_FIELDS = ("server_name", "database_name", "project_or_cluster_ref")
SECRET_VALUE_KEYS = {
    "url",
    "database_url",
    "password",
    "token",
    "api_key",
    "service_role_key",
    "cookie",
    "secret",
}


def _issue(code: str, message: str, location: Optional[str] = None) -> Issue:
    return Issue(code, message, location)


def validate_target_descriptor(descriptor: Optional[Dict[str, Any]]) -> TargetValidation:
    if descriptor is None:
        return TargetValidation(
            status=CheckStatus.BLOCKED,
            issues=[_issue("TARGET_REQUIRED", "An explicit non-production target descriptor is required")],
        )
    if not isinstance(descriptor, dict):
        return TargetValidation(
            status=CheckStatus.BLOCKED,
            issues=[_issue("TARGET_DESCRIPTOR_INVALID", "Target descriptor must be an object")],
        )

    issues: List[Issue] = []
    target_id = descriptor.get("target_id")
    environment = descriptor.get("environment")
    provider = descriptor.get("provider")

    required = (
        "descriptor_version",
        "target_id",
        "environment",
        "provider",
        "database_identity",
        "disposable",
        "contains_v333_objects",
        "contains_production_data",
        "credential_env_name",
        "allow_network",
        "connect_permission",
    )
    for field in required:
        if field not in descriptor:
            issues.append(_issue("TARGET_FIELD_MISSING", f"Required target descriptor field is missing: {field}", field))

    if descriptor.get("descriptor_version") != "v4-migration-target-descriptor@1.0.0":
        issues.append(_issue("TARGET_DESCRIPTOR_VERSION_INVALID", "Target descriptor version is not the approved contract"))
    if not isinstance(target_id, str) or not TARGET_ID_RE.fullmatch(target_id):
        issues.append(_issue("TARGET_ID_INVALID", "Target identity must be a lowercase opaque identifier"))
    if environment not in ALL_ENVIRONMENTS:
        issues.append(_issue("TARGET_ENVIRONMENT_INVALID", "Target environment is not recognized"))
    if provider not in ALLOWED_PROVIDERS:
        issues.append(_issue("TARGET_PROVIDER_INVALID", "Target provider is not recognized"))

    if environment == "PRODUCTION":
        # This guard is unconditional.  No flag in a BATCH-02 descriptor can
        # authorize a Production connection or write.
        issues.append(_issue("PRODUCTION_TARGET_HARD_BLOCK", "Production targets are hard-blocked in BATCH-02"))
        if descriptor.get("connect_permission") != "BLOCKED":
            issues.append(_issue("PRODUCTION_PERMISSION_INVALID", "Production target permission must be BLOCKED"))
        if descriptor.get("allow_network") is not False:
            issues.append(_issue("PRODUCTION_NETWORK_INVALID", "Production target network access must be false"))

    expected_provider = {
        "DISPOSABLE_LOCAL": {"LOCAL_POSTGRES", "DOCKER_POSTGRES"},
        "STAGING": {"STAGING_POSTGRES", "STAGING_SUPABASE"},
        "PRODUCTION": {"PRODUCTION_SUPABASE"},
    }.get(environment)
    if expected_provider and provider not in expected_provider:
        issues.append(_issue("TARGET_PROVIDER_ENVIRONMENT_MISMATCH", "Provider does not match target environment"))

    database_identity = descriptor.get("database_identity")
    if not isinstance(database_identity, dict):
        issues.append(_issue("DATABASE_IDENTITY_INVALID", "Database identity must be an object"))
    else:
        for field in REQUIRED_DATABASE_IDENTITY_FIELDS:
            if not is_non_empty_string(database_identity.get(field)):
                issues.append(_issue("DATABASE_IDENTITY_FIELD_INVALID", f"Database identity field is missing: {field}", field))
        for key in database_identity:
            if key.lower() in SECRET_VALUE_KEYS:
                issues.append(_issue("SECRET_VALUE_IN_DESCRIPTOR", "Raw credential material is not allowed in a target descriptor", key))

    credential_env_name = descriptor.get("credential_env_name")
    if not isinstance(credential_env_name, str) or not CREDENTIAL_ENV_RE.fullmatch(credential_env_name):
        issues.append(_issue("CREDENTIAL_ENV_REFERENCE_INVALID", "Only an uppercase environment-variable name may identify credentials"))

    if environment in ALLOWED_ENVIRONMENTS:
        if environment == "DISPOSABLE_LOCAL" and descriptor.get("disposable") is not True:
            issues.append(_issue("DISPOSABLE_ASSERTION_REQUIRED", "DISPOSABLE_LOCAL targets must assert disposable=true"))
        if descriptor.get("contains_v333_objects") is not False:
            issues.append(_issue("V333_OBJECT_COLLISION", "Target must contain no V3.3.3 objects"))
        if descriptor.get("contains_production_data") is not False:
            issues.append(_issue("PRODUCTION_DATA_COLLISION", "Target must contain no retained Production data"))
        lifecycle = descriptor.get("reset_and_teardown_contract")
        if not isinstance(lifecycle, dict):
            issues.append(_issue("RESET_TEARDOWN_CONTRACT_MISSING", "Disposable validation needs an operator-owned reset/teardown contract"))
        else:
            for field in ("reset_before_run", "destroy_after_evidence", "operator_owned"):
                if lifecycle.get(field) is not True:
                    issues.append(_issue("RESET_TEARDOWN_CONTRACT_INVALID", f"Reset/teardown field must be true: {field}", field))

    if descriptor.get("connect_permission") not in {"EXPLICITLY_GRANTED", "NOT_GRANTED", "BLOCKED"}:
        issues.append(_issue("CONNECT_PERMISSION_INVALID", "Connection permission is not recognized"))
    elif environment in ALLOWED_ENVIRONMENTS and descriptor.get("connect_permission") != "EXPLICITLY_GRANTED":
        issues.append(_issue("CONNECT_PERMISSION_REQUIRED", "A database connection requires explicit permission"))
    if environment == "PRODUCTION" and descriptor.get("connect_permission") != "BLOCKED":
        issues.append(_issue("PRODUCTION_CONNECT_BLOCKED", "Production connection is always blocked"))

    if not isinstance(descriptor.get("disposable"), bool):
        issues.append(_issue("DISPOSABLE_FLAG_INVALID", "disposable must be boolean"))
    if not isinstance(descriptor.get("contains_v333_objects"), bool):
        issues.append(_issue("V333_FLAG_INVALID", "contains_v333_objects must be boolean"))
    if not isinstance(descriptor.get("contains_production_data"), bool):
        issues.append(_issue("PRODUCTION_DATA_FLAG_INVALID", "contains_production_data must be boolean"))
    if not isinstance(descriptor.get("allow_network"), bool):
        issues.append(_issue("NETWORK_FLAG_INVALID", "allow_network must be boolean"))

    status = CheckStatus.PASS if not issues else CheckStatus.BLOCKED
    return TargetValidation(
        status=status,
        issues=issues,
        target_id=target_id if isinstance(target_id, str) else None,
        environment=environment if isinstance(environment, str) else None,
        provider=provider if isinstance(provider, str) else None,
        connect_allowed=status == CheckStatus.PASS and descriptor.get("connect_permission") == "EXPLICITLY_GRANTED",
    )
