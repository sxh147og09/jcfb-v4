"""Fail-closed compatibility rules for the V4 public-view forward-fix.

The supplied legacy baseline owns several unprefixed ``public.v_*`` identities.
This module keeps the baseline names explicit, compares a view's definition,
reloptions, and grants as one contract, and makes the safe strategy observable
without ever issuing DDL against an existing object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple


V333_PUBLIC_VIEW_BASELINE: FrozenSet[str] = frozenset(
    {
        "public.v_canonical_latest_update",
        "public.v_current_frozen_predictions",
        "public.v_forward_tier_a_progress",
        "public.v_historical_tier_a_recovery_status",
        "public.v_latest_odds_snapshots",
        "public.v_odds_ingestion_gate_status",
        "public.v_public_latest_odds",
        "public.v_public_predictions",
        "public.v_screenshot_intake_status",
        "public.v_shadow_run_latest",
        "public.v_tier_a_progress",
    }
)

V4_PUBLIC_VIEW_NAMES: FrozenSet[str] = frozenset(
    {
        "public.v4_public_predictions",
        "public.v4_public_latest_odds",
        "public.v4_current_frozen_predictions",
        "public.v4_canonical_latest_update",
        "public.v4_tier_a_progress",
        "public.v4_model_registry_public",
    }
)

_CREATE_VIEW_RE = re.compile(
    r"(?im)^\s*CREATE\s+VIEW\s+(?P<qualified>[a-z_][a-z0-9_$]*\.[a-z_][a-z0-9_$]*)\b"
)
_FORBIDDEN_VIEW_MUTATION_RE = re.compile(
    r"(?im)^\s*(?:DROP\s+VIEW|CREATE\s+OR\s+REPLACE\s+VIEW)\b"
)


class ViewCompatibilityError(ValueError):
    """Raised when an existing view cannot be proven reusable."""


@dataclass(frozen=True)
class ViewContract:
    """The catalog properties that must all match for safe reuse."""

    definition: str
    reloptions: Tuple[str, ...] = ()
    grants: FrozenSet[Tuple[str, str]] = frozenset()


def _normalize_sql(value: str) -> str:
    if not isinstance(value, str):
        raise ViewCompatibilityError("view definition must be text")
    return " ".join(value.strip().split()).casefold()


def _normalize_reloptions(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted(_normalize_sql(str(value)) for value in values))


def _normalize_grants(values: Iterable[Sequence[str]]) -> FrozenSet[Tuple[str, str]]:
    normalized = set()
    for value in values:
        if len(value) != 2:
            raise ViewCompatibilityError("view grant entries must contain role and privilege")
        normalized.add((_normalize_sql(str(value[0])), _normalize_sql(str(value[1]))))
    return frozenset(normalized)


def normalized_contract(contract: ViewContract) -> ViewContract:
    """Normalize catalog text before the exact three-part comparison."""

    return ViewContract(
        definition=_normalize_sql(contract.definition),
        reloptions=_normalize_reloptions(contract.reloptions),
        grants=_normalize_grants(contract.grants),
    )


def view_contracts_equivalent(existing: ViewContract, intended: ViewContract) -> bool:
    """Return true only when definition, security options, and grants all match."""

    return normalized_contract(existing) == normalized_contract(intended)


def assert_reusable_view(
    existing_name: str,
    existing: Optional[ViewContract],
    intended: ViewContract,
) -> ViewContract:
    """Prove an existing view is reusable or fail closed.

    This helper is intentionally assertion-only. It does not return replacement
    SQL and it never authorizes ``DROP`` or ``CREATE OR REPLACE``.
    """

    if existing is None:
        raise ViewCompatibilityError(f"required existing view is missing: {existing_name}")
    if not view_contracts_equivalent(existing, intended):
        raise ViewCompatibilityError(f"existing view contract is incompatible: {existing_name}")
    return normalized_contract(existing)


def choose_view_strategy(
    existing_name: str,
    existing: Optional[ViewContract],
    intended: ViewContract,
    *,
    v4_name: str,
) -> str:
    """Return the only safe strategy for an existing or missing identity."""

    if existing is None:
        return "CREATE_APPROVED"
    if view_contracts_equivalent(existing, intended):
        return "ASSERT_AND_REUSE"
    if existing_name in V333_PUBLIC_VIEW_BASELINE and v4_name not in V333_PUBLIC_VIEW_BASELINE:
        return "V4_RENAME"
    return "BLOCKED"


def created_view_names(sql_text: str) -> Tuple[str, ...]:
    """Extract explicit two-part names from ordinary ``CREATE VIEW`` statements."""

    return tuple(match.group("qualified").casefold() for match in _CREATE_VIEW_RE.finditer(sql_text))


def public_view_collisions(
    sql_text: str,
    baseline: Iterable[str] = V333_PUBLIC_VIEW_BASELINE,
) -> Tuple[str, ...]:
    """Return created public view identities that collide with the baseline."""

    baseline_set = {str(value).casefold() for value in baseline}
    return tuple(sorted(set(created_view_names(sql_text)) & baseline_set))


def forbidden_view_mutations(sql_text: str) -> Tuple[str, ...]:
    """Return source lines that could replace or drop an existing view."""

    return tuple(match.group(0).strip() for match in _FORBIDDEN_VIEW_MUTATION_RE.finditer(sql_text))


__all__ = [
    "V333_PUBLIC_VIEW_BASELINE",
    "V4_PUBLIC_VIEW_NAMES",
    "ViewCompatibilityError",
    "ViewContract",
    "assert_reusable_view",
    "choose_view_strategy",
    "created_view_names",
    "forbidden_view_mutations",
    "normalized_contract",
    "public_view_collisions",
    "view_contracts_equivalent",
]
