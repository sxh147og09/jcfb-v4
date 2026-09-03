"""Pure role-state contract used by the no-connector regression tests.

The runtime candidate contains the executable PostgreSQL check. This module is
deliberately database-free: it mirrors the fail-closed decision for unit tests
and audit tooling without opening a connection or attempting a role mutation.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


SERVICE_ROLE_MISSING_CODE = "V4_PREREQUISITE_SERVICE_ROLE_MISSING"
SERVICE_ROLE_BYPASSRLS_REQUIRED_CODE = "V4_PREREQUISITE_SERVICE_ROLE_BYPASSRLS_REQUIRED"
PUBLIC_ROLE_BYPASSRLS_FORBIDDEN_CODE = "V4_PREREQUISITE_PUBLIC_ROLE_BYPASSRLS_FORBIDDEN"


def evaluate_service_role_prerequisite(
    role_rows: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Evaluate the candidate's provider-role and public-role invariants.

    Missing ``anon``/``authenticated`` rows are not treated as a service-role
    failure because candidate 0001 may create those local no-login roles with
    ``NOBYPASSRLS``. A present public role with ``rolbypassrls=True`` is always
    rejected. ``service_role`` is different: it must already exist and must
    already have ``rolbypassrls=True``.
    """

    service_role = role_rows.get("service_role")
    if service_role is None:
        return {
            "status": "FAIL",
            "code": SERVICE_ROLE_MISSING_CODE,
            "reason": "service_role must already exist; reserved-role creation is forbidden",
        }
    if service_role.get("rolbypassrls") is not True:
        return {
            "status": "FAIL",
            "code": SERVICE_ROLE_BYPASSRLS_REQUIRED_CODE,
            "reason": "service_role must already have rolbypassrls=true",
        }

    public_role_violations = [
        role
        for role in ("anon", "authenticated")
        if role_rows.get(role, {}).get("rolbypassrls") is True
    ]
    if public_role_violations:
        return {
            "status": "FAIL",
            "code": PUBLIC_ROLE_BYPASSRLS_FORBIDDEN_CODE,
            "reason": "anon/authenticated must retain rolbypassrls=false",
            "violating_roles": public_role_violations,
        }

    return {
        "status": "PASS",
        "code": "V4_PREREQUISITE_SERVICE_ROLE_PASS",
        "service_role_exists": True,
        "service_role_bypass_rls": True,
        "anon_authenticated_bypass_rls_false": True,
    }
