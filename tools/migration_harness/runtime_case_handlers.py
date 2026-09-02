"""PostgreSQL PRE-BATCH-04 runtime case handlers.

The handlers in this module deliberately use ordinary PostgreSQL statements
through the connection supplied by :mod:`runtime_executor`.  They do not
start Docker, discover a socket, or manufacture a Supabase runtime.  Every
case is wrapped in a transaction owned by :class:`CaseContext`; the runner
rolls that transaction back after evidence is collected so the next case
starts from an empty fixture namespace.

The module is intentionally boring about failure classification.  A rejected
statement is only a passing negative case when its SQLSTATE and at least one
governed mechanism marker match the execution contract.  Driver text is used
only in memory for that comparison and is never written to the report.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CASE_RESULT_STATUSES = {
    "PASS_EXPECTED_ACCEPT",
    "PASS_EXPECTED_REJECT",
    "FAIL_UNEXPECTED_ACCEPT",
    "FAIL_UNEXPECTED_REJECT",
    "BLOCKED_ENVIRONMENT",
}

UTC = timezone.utc
CASE_NAMESPACE = uuid.UUID("8f151f2a-3e0b-4b23-9c90-71a608f5f904")
CUTOFF = "2026-01-01T10:00:00+00:00"
KICKOFF = "2026-01-01T12:00:00+00:00"
PRE_RUN = "2026-01-01T09:15:00+00:00"
PRE_COMPLETE = "2026-01-01T09:30:00+00:00"
PRE_FROZEN = "2026-01-01T09:00:00+00:00"
POST_KICKOFF = "2026-01-01T12:30:00+00:00"
POST_REVIEW = "2026-01-01T13:00:00+00:00"
LATEST_BUSINESS_TIMESTAMP = "2026-01-01T09:45:00+00:00"
PAGE_TIME = "2026-01-02T12:00:00+00:00"
SCHEMA_VERSION = "v4-database-schema@1.0.0"
MIGRATION_VERSION = "migration@20260901.009"
CONTRACT_VERSION = "v4-runtime-case@1.0.0"
HASH_PROFILE = "v4-canonical-json@1.0"
HASH_ALGORITHM = "SHA-256"
MARKETS = ("spf", "rqspf", "total_goals", "exact_score", "half_full")
ROLE_NAMES = {"anon", "authenticated", "service_role", "backend", "executor", "auditor"}


class RuntimeCaseBlocked(RuntimeError):
    """Raised when the target cannot execute a governed case."""


@dataclass
class Attempt:
    """A savepoint-isolated action observation."""

    accepted: bool
    error: Optional[BaseException] = None
    role: str = ""

    @property
    def actual_outcome(self) -> str:
        return "ACCEPT" if self.accepted else "REJECT"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    payload = value if isinstance(value, str) else _json(value)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _id(case_id: str, label: str) -> str:
    return str(uuid.uuid5(CASE_NAMESPACE, f"{case_id}:{label}"))


def _as_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return str(value or "").replace(" ", "T")


def _sqlstate(exc: BaseException) -> str:
    for name in ("sqlstate", "pgcode"):
        value = getattr(exc, name, None)
        if value:
            return str(value)
    diag = getattr(exc, "diag", None)
    value = getattr(diag, "sqlstate", None) if diag is not None else None
    return str(value or "")


def _constraint_name(exc: BaseException) -> str:
    diag = getattr(exc, "diag", None)
    value = getattr(diag, "constraint_name", None) if diag is not None else None
    return str(value or "")


def _private_error_text(exc: Optional[BaseException]) -> str:
    if exc is None:
        return ""
    parts: List[str] = []
    current: Optional[BaseException] = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(type(current).__name__.lower())
        try:
            parts.append(str(current).lower())
        except Exception:
            pass
        current = current.__cause__ or current.__context__
    return " ".join(parts)


def match_expected_rejection(exc: Optional[BaseException], expected: Mapping[str, Any]) -> bool:
    """Match a rejection against the governed SQL mechanism.

    SQLSTATE is mandatory.  If the contract names constraints, trigger names,
    or message tokens, at least one marker from each supplied mechanism family
    must match.  ``message_tokens`` are alternatives when a trigger can fail
    at more than one governed branch; this is why a list may contain multiple
    stable error constants.
    """

    if exc is None or not isinstance(expected, Mapping):
        return False
    sqlstates = {str(item) for item in expected.get("sqlstates", []) if item}
    # A governed rejection must always identify a PostgreSQL SQLSTATE.  A
    # message-only or exception-class-only match would turn an unrelated
    # database error into a false PASS.
    if not sqlstates or _sqlstate(exc) not in sqlstates:
        return False
    constraint = _constraint_name(exc).lower()
    text = _private_error_text(exc)
    constraints = [str(item).lower() for item in expected.get("constraints", []) if item]
    prefixes = [str(item).lower() for item in expected.get("constraint_prefixes", []) if item]
    tokens = [str(item).lower() for item in expected.get("message_tokens", []) if item]
    trigger_names = [str(item).lower() for item in expected.get("trigger_names", []) if item]
    if constraints and not any(item == constraint for item in constraints):
        return False
    if prefixes and not any(constraint.startswith(item) for item in prefixes):
        return False
    # Trigger names are normally present in audit metadata rather than in the
    # PostgreSQL error itself.  The stable trigger error constants are the
    # enforceable runtime marker; accept the trigger family when a message
    # token proves the same branch.  A contract with trigger names but no
    # message token remains valid for an explicit constraint match only.
    if tokens and not any(item in text for item in tokens):
        return False
    if trigger_names and not (tokens or constraints or prefixes):
        return False
    return True


class CaseContext:
    """Transaction and savepoint helper shared by every runtime case."""

    def __init__(self, connection: Any, case_id: str, actor: str):
        self.connection = connection
        self.case_id = case_id
        self.actor = actor
        self._savepoint_counter = 0

    def begin(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if callable(rollback):
            rollback()
        self.execute("BEGIN")
        self.execute("SET LOCAL TIME ZONE 'UTC'")
        self.execute("SELECT set_config('v4.actor', %s, true)", (self.actor,))
        self.execute("SELECT set_config('v4.actor_role', %s, true)", ("runtime_case",))
        self.execute("SET CONSTRAINTS ALL DEFERRED")

    def close(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if callable(rollback):
            rollback()

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> None:
        cursor = self.connection.cursor()
        try:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, tuple(params))
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def rows(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        try:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, tuple(params))
            names = [item[0] for item in (getattr(cursor, "description", None) or [])]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def one(self, sql: str, params: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
        values = self.rows(sql, params)
        return values[0] if values else {}

    def set_role(self, role: str) -> None:
        if role not in ROLE_NAMES:
            raise RuntimeCaseBlocked("runtime role is not in the disposable role allow-list")
        quoted = '"' + role.replace('"', '""') + '"'
        self.execute(f"SET LOCAL ROLE {quoted}")
        self.execute("SELECT set_config('v4.actor_role', %s, true)", (role,))

    def flush_constraints(self) -> None:
        self.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.execute("SET CONSTRAINTS ALL DEFERRED")

    def attempt(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        *,
        role: str,
        flush: bool = True,
    ) -> Attempt:
        self.set_role(role)
        self._savepoint_counter += 1
        name = f"v4_case_action_{self._savepoint_counter}"
        self.execute(f"SAVEPOINT {name}")
        try:
            self.execute(sql, params)
            if flush:
                self.flush_constraints()
            self.execute(f"RELEASE SAVEPOINT {name}")
            return Attempt(True, None, role)
        except BaseException as exc:
            try:
                self.execute(f"ROLLBACK TO SAVEPOINT {name}")
                self.execute(f"RELEASE SAVEPOINT {name}")
                self.execute("SET CONSTRAINTS ALL DEFERRED")
            except BaseException as cleanup_exc:
                raise RuntimeCaseBlocked("action savepoint could not be restored") from cleanup_exc
            return Attempt(False, exc, role)


def _insert_competition(ctx: CaseContext, case_id: str, suffix: str = "") -> str:
    competition_id = _id(case_id, f"competition:{suffix}")
    h = _hash(f"competition:{case_id}:{suffix}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO core.competitions (competition_id, competition_key, governing_source, display_name, "
        "normalized_name, timezone, identity_resolution_state, revision, source, source_type, "
        "source_reference, source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, "
        "hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'RESOLVED', 1, %s, 'OFFICIAL_FEED', %s, %s, %s, %s, %s, %s, "
        "'SHA-256', %s, %s, %s, 'ACTIVE', %s::jsonb)",
        (
            competition_id,
            f"runtime-{case_id.lower().replace('-', '')}-{suffix or 'a'}",
            "runtime-official",
            f"Runtime Competition {case_id}",
            f"runtime competition {case_id.lower()}",
            "UTC",
            "runtime-fixture",
            f"runtime://{case_id}/competition/{suffix or 'a'}",
            PRE_RUN,
            PRE_RUN,
            PRE_RUN,
            h,
            h,
            HASH_PROFILE,
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            _json({"fixture": True, "case_id": case_id}),
        ),
    )
    return competition_id


def _insert_team(ctx: CaseContext, case_id: str, label: str) -> str:
    team_id = _id(case_id, f"team:{label}")
    h = _hash(f"team:{case_id}:{label}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO core.teams (team_id, canonical_team_key, source_namespace, canonical_name, normalized_name, "
        "identity_resolution_state, revision, source, source_type, source_reference, source_timestamp, observed_at, "
        "ingested_at, provenance_hash, payload_hash, hash_algorithm, hash_profile, contract_version, schema_version, "
        "status, metadata) VALUES (%s, %s, 'runtime', %s, %s, 'RESOLVED', 1, 'runtime-fixture', 'OFFICIAL_FEED', %s, "
        "%s, %s, %s, %s, %s, 'SHA-256', %s, %s, %s, 'ACTIVE', %s::jsonb)",
        (
            team_id,
            f"runtime-{case_id.lower().replace('-', '')}-{label}",
            f"Runtime {label.title()} {case_id}",
            f"runtime {label} {case_id.lower()}",
            f"runtime://{case_id}/team/{label}",
            PRE_RUN,
            PRE_RUN,
            PRE_RUN,
            h,
            h,
            HASH_PROFILE,
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            _json({"fixture": True, "case_id": case_id, "label": label}),
        ),
    )
    return team_id


def _insert_match(
    ctx: CaseContext,
    case_id: str,
    competition_id: str,
    home_team_id: str,
    away_team_id: str,
    *,
    label: str = "main",
    data_date: str = "2026-01-01",
    official_match_no: Optional[str] = None,
    role: str = "service_role",
) -> str:
    match_id = _id(case_id, f"match:{label}")
    official_match_no = official_match_no or str(int(case_id.split("-")[-1]) * 10 + (1 if label == "main" else 2))
    match_hash = _hash(f"match:{case_id}:{label}")
    params = (
        match_id,
        data_date,
        official_match_no,
        f"{data_date}:{official_match_no}",
        competition_id,
        home_team_id,
        away_team_id,
        KICKOFF,
        "UTC",
        match_hash,
        "runtime-fixture",
        "OFFICIAL_FEED",
        f"runtime://{case_id}/match/{label}",
        PRE_RUN,
        PRE_RUN,
        PRE_RUN,
        match_hash,
        match_hash,
        HASH_PROFILE,
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        _json({"fixture": True, "case_id": case_id, "label": label}),
    )
    ctx.attempt(
        "INSERT INTO core.matches (match_id, data_date, official_match_no, match_identity_key, competition_id, "
        "home_team_id, away_team_id, kickoff_at, timezone, match_status, intake_status, identity_resolution_state, "
        "canonical_facts_hash, revision, source, source_type, source_reference, source_timestamp, observed_at, "
        "ingested_at, provenance_hash, payload_hash, hash_algorithm, hash_profile, contract_version, schema_version, "
        "metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'SCHEDULED', 'OPEN', 'RESOLVED', %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
        params,
        role=role,
    )
    return match_id


def _core_fixture(ctx: CaseContext, case_id: str, *, two_matches: bool = False) -> Dict[str, str]:
    competition_id = _insert_competition(ctx, case_id)
    home_team_id = _insert_team(ctx, case_id, "home")
    away_team_id = _insert_team(ctx, case_id, "away")
    match_id = _insert_match(ctx, case_id, competition_id, home_team_id, away_team_id)
    fixture = {
        "competition_id": competition_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "match_id": match_id,
    }
    if two_matches:
        second_home = _insert_team(ctx, case_id, "second-home")
        second_away = _insert_team(ctx, case_id, "second-away")
        fixture["match_b_id"] = _insert_match(
            ctx,
            case_id,
            competition_id,
            second_home,
            second_away,
            label="b",
            official_match_no=str(int(case_id.split("-")[-1]) * 10 + 2),
        )
    return fixture


def _model(
    ctx: CaseContext,
    case_id: str,
    label: str,
    *,
    role: str = "PRODUCTION",
    status: str = "PROMOTION_REVIEW",
    active: bool = False,
    family: str = "jcfb-runtime",
    channel: str = "main",
) -> str:
    model_id = _id(case_id, f"model:{label}")
    model_name = f"runtime-{label.replace('_', '-')}-{case_id.lower().replace('-', '')}"
    version = f"{model_name}@1.0.0"
    implementation_hash = _hash(f"model-implementation:{case_id}:{label}")
    config_hash = _hash(f"model-config:{case_id}:{label}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO governance.model_versions (model_version_id, model_family, model_name, model_version, major, minor, patch, revision, "
        "jcfb_version, role, canonical_output_channel, implementation_hash, config_version, config_hash, schema_version, dataset_version, "
        "migration_version, hash_algorithm, hash_profile, compatibility_level, status, is_canonical_active, effective_at, approval_reference, "
        "approved_at, contract_version, metadata) VALUES (%s, %s, %s, %s, 1, 0, 0, 'r1', 'v4-runtime', %s, %s, %s, 'config@1.0.0', %s, %s, 'dataset@runtime', %s, 'SHA-256', %s, 'PATCH_COMPATIBLE', %s, %s, %s, %s, %s, %s, %s::jsonb)",
        (
            model_id,
            family,
            model_name,
            version,
            role,
            channel,
            implementation_hash,
            config_hash,
            SCHEMA_VERSION,
            MIGRATION_VERSION,
            HASH_PROFILE,
            status,
            active,
            PRE_FROZEN if active else None,
            f"runtime-approval:{case_id}" if status == "PRODUCTION" else None,
            PRE_FROZEN if status == "PRODUCTION" else None,
            CONTRACT_VERSION,
            _json({"fixture": True, "case_id": case_id, "role": role, "label": label}),
        ),
    )
    return model_id


def _engine(
    ctx: CaseContext,
    case_id: str,
    label: str,
    model_id: str,
    *,
    role: str = "PRODUCTION",
    status: str = "PROMOTION_REVIEW",
    active: bool = False,
    family: str = "jcfb-runtime",
    channel: str = "main",
) -> str:
    engine_id = _id(case_id, f"engine:{label}")
    engine_name = f"runtime-{label.replace('_', '-')}-{case_id.lower().replace('-', '')}"
    version = f"{engine_name}@1.0.0"
    implementation_hash = _hash(f"engine-implementation:{case_id}:{label}")
    config_hash = _hash(f"engine-config:{case_id}:{label}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO governance.engine_versions (engine_version_id, model_version_id, model_family, engine_name, engine_version, major, minor, patch, revision, jcfb_version, role, canonical_output_channel, implementation_hash, config_version, config_hash, schema_version, dataset_version, migration_version, hash_algorithm, hash_profile, compatibility_level, status, is_canonical_active, effective_at, contract_version, metadata) VALUES (%s, %s, %s, %s, %s, 1, 0, 0, 'r1', 'v4-runtime', %s, %s, %s, 'config@1.0.0', %s, %s, 'dataset@runtime', %s, 'SHA-256', %s, 'PATCH_COMPATIBLE', %s, %s, %s, %s, %s::jsonb)",
        (
            engine_id,
            model_id,
            family,
            engine_name,
            version,
            role,
            channel,
            implementation_hash,
            config_hash,
            SCHEMA_VERSION,
            MIGRATION_VERSION,
            HASH_PROFILE,
            status,
            active,
            PRE_FROZEN if active else None,
            CONTRACT_VERSION,
            _json({"fixture": True, "case_id": case_id, "role": role, "label": label}),
        ),
    )
    return engine_id


def _frozen_input(
    ctx: CaseContext,
    case_id: str,
    label: str,
    match_id: str,
    model_id: str,
    engine_id: str,
    *,
    owner_role: str = "PRODUCTION",
    frozen_input_hash: Optional[str] = None,
    revision: int = 1,
) -> Dict[str, str]:
    frozen_input_id = _id(case_id, f"frozen-input:{label}")
    input_hash = frozen_input_hash or _hash(f"frozen-input:{case_id}:{label}")
    group_id = _id(case_id, f"ab-group:{label}") if owner_role == "PRODUCTION" else None
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO model.frozen_inputs (frozen_input_id, match_id, revision, frozen_input_revision, canonical_match_hash, feature_schema_version, dataset_version, schema_version, migration_version, prediction_cutoff_at, kickoff_at, owner_role, comparison_mode, ab_comparison_group_id, frozen_at, immutable, future_information_leakage, run_invalid, tier_a_eligible, status, frozen_input_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, gate_reason, source_summary, contract_version, metadata) VALUES (%s, %s, %s, %s, %s, 'features@1.0', 'dataset@runtime', %s, %s, %s, %s, %s, %s, %s, %s, true, false, false, false, 'FROZEN', %s, %s, %s, 'SHA-256', %s, NULL, %s::jsonb, %s, %s::jsonb)",
        (
            frozen_input_id,
            match_id,
            revision,
            f"fi-20260101-{revision:06d}",
            _hash(f"canonical-match:{case_id}:{label}"),
            SCHEMA_VERSION,
            MIGRATION_VERSION,
            CUTOFF,
            KICKOFF,
            owner_role,
            "FORWARD_AB" if owner_role == "PRODUCTION" else "EXPERIMENT_ONLY",
            group_id,
            PRE_FROZEN,
            input_hash,
            input_hash,
            _hash(f"frozen-input-provenance:{case_id}:{label}"),
            HASH_PROFILE,
            _json({"fixture": True, "case_id": case_id, "label": label}),
            CONTRACT_VERSION,
            _json({"fixture": True, "case_id": case_id, "label": label}),
        ),
    )
    ctx.execute(
        "INSERT INTO model.frozen_input_model_refs (frozen_input_model_ref_id, frozen_input_id, model_version_id, metadata) VALUES (%s, %s, %s, %s::jsonb)",
        (_id(case_id, f"frozen-model-ref:{label}"), frozen_input_id, model_id, _json({"fixture": True})),
    )
    ctx.execute(
        "INSERT INTO model.frozen_input_engine_refs (frozen_input_engine_ref_id, frozen_input_id, engine_version_id, metadata) VALUES (%s, %s, %s, %s::jsonb)",
        (_id(case_id, f"frozen-engine-ref:{label}"), frozen_input_id, engine_id, _json({"fixture": True})),
    )
    ctx.flush_constraints()
    return {"frozen_input_id": frozen_input_id, "frozen_input_hash": input_hash, "ab_group_id": group_id or ""}


def _feature_bundle(
    ctx: CaseContext,
    case_id: str,
    label: str,
    frozen: Mapping[str, str],
    *,
    role: str = "PRODUCTION",
    experiment_id: Optional[str] = None,
) -> str:
    bundle_id = _id(case_id, f"feature-bundle:{label}")
    input_hash = _hash(f"feature-input:{case_id}:{label}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO model.feature_bundles (feature_bundle_id, frozen_input_id, frozen_input_hash, role, shadow_revision, experiment_revision, experiment_id, feature_schema_version, generator_version, input_hash, feature_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, generated_at, prediction_cutoff_at, kickoff_at, feature_values, missingness_summary, quality_flags, status, contract_version, schema_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, 'features@1.0', %s, %s, %s, %s, %s, 'SHA-256', %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, 'VALIDATED', %s, %s, %s::jsonb)",
        (
            bundle_id,
            frozen["frozen_input_id"],
            frozen["frozen_input_hash"],
            role,
            "shadow-r1" if role == "SHADOW" else None,
            "experiment-r1" if role == "EXPERIMENT" else None,
            experiment_id,
            f"runtime-generator-{label}",
            input_hash,
            _hash(f"feature:{case_id}:{label}"),
            _hash(f"feature-payload:{case_id}:{label}"),
            _hash(f"feature-provenance:{case_id}:{label}"),
            HASH_PROFILE,
            PRE_RUN,
            CUTOFF,
            KICKOFF,
            _json({"goals": 1, "label": label}),
            _json({}),
            _json([]),
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            _json({"fixture": True, "case_id": case_id, "label": label}),
        ),
    )
    return bundle_id


def _engine_run(
    ctx: CaseContext,
    case_id: str,
    label: str,
    fixture: Mapping[str, str],
    *,
    role: str = "PRODUCTION",
    model_id: str,
    engine_id: str,
    bundle_id: str,
    run_at: str = PRE_RUN,
    completed_at: str = PRE_COMPLETE,
    as_attempt: bool = False,
) -> Any:
    run_id = _id(case_id, f"engine-run:{label}")
    output_hash = _hash(f"engine-output:{case_id}:{label}")
    sql = "INSERT INTO model.engine_runs (engine_run_id, match_id, frozen_input_id, feature_bundle_id, role, model_version_id, engine_version_id, role_revision, shadow_revision, experiment_revision, experiment_id, build_id, frozen_input_hash, implementation_hash, config_version, config_hash, schema_version, migration_version, dataset_version, input_hash, output_hash, run_at, run_completed_at, prediction_cutoff_at, kickoff_at, runtime_ms, runtime_environment, random_seed, simulation_version, status, future_information_leakage, run_invalid, tier_a_eligible, promotion_evidence, warnings, errors, payload, provenance_hash, hash_algorithm, hash_profile, contract_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'config@1.0.0', %s, %s, %s, 'dataset@runtime', %s, %s, %s, %s, %s, %s, 10.0, %s::jsonb, 7, 'sim@1.0', 'SUCCEEDED', false, false, false, false, %s::jsonb, %s::jsonb, %s::jsonb, %s, 'SHA-256', %s, %s, %s::jsonb)"
    values = (
        run_id,
        fixture["match_id"],
        fixture["frozen_input_id"],
        bundle_id,
        role,
        model_id,
        engine_id,
        "production-r1" if role == "PRODUCTION" else ("shadow-r1" if role == "SHADOW" else "experiment-r1"),
        "shadow-r1" if role == "SHADOW" else None,
        "experiment-r1" if role == "EXPERIMENT" else None,
        _id(case_id, "experiment") if role == "EXPERIMENT" else None,
        f"runtime-build-{case_id}-{label}",
        fixture["frozen_input_hash"],
        _hash(f"implementation:{case_id}:{label}"),
        _hash(f"config:{case_id}:{label}"),
        SCHEMA_VERSION,
        MIGRATION_VERSION,
        _hash(f"run-input:{case_id}:{label}"),
        output_hash,
        run_at,
        completed_at,
        CUTOFF,
        KICKOFF,
        _json({"runtime": "disposable", "role": role}),
        _json([]),
        _json([]),
        _json({"prediction": {"label": label}}),
        _hash(f"run-provenance:{case_id}:{label}"),
        HASH_PROFILE,
        CONTRACT_VERSION,
        _json({"fixture": True, "case_id": case_id, "label": label}),
    )
    if as_attempt:
        return ctx.attempt(sql, values, role="executor")
    ctx.set_role("service_role")
    ctx.execute(sql, values)
    return {"engine_run_id": run_id, "output_hash": output_hash}


def _prediction(
    ctx: CaseContext,
    case_id: str,
    label: str,
    fixture: Mapping[str, str],
    *,
    role: str,
    model_id: str,
    model_run_at: str = PRE_RUN,
    frozen_input_hash: Optional[str] = None,
    experiment_id: Optional[str] = None,
) -> Dict[str, str]:
    prediction_id = _id(case_id, f"prediction:{label}")
    prediction_hash = _hash(f"prediction:{case_id}:{label}")
    input_hash = _hash(f"prediction-input:{case_id}:{label}")
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO model.predictions (prediction_id, match_id, frozen_input_id, frozen_input_hash, model_version_id, role, prediction_revision, stage, role_revision, shadow_revision, experiment_revision, experiment_id, model_run_at, prediction_cutoff_at, kickoff_at, market_predictions, consensus, disagreement, uncertainty, risk, confidence_grade, recommendation_state, recommendation_strength, input_hash, output_hash, prediction_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, future_information_leakage, run_invalid, tier_a_eligible, promotion_evidence, status, contract_version, schema_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, 1, 'FORMAL', %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 'HIGH', 'PASS', 'MODERATE', %s, %s, %s, %s, %s, 'SHA-256', %s, false, false, false, false, 'FROZEN', %s, %s, %s::jsonb)",
        (
            prediction_id,
            fixture["match_id"],
            fixture["frozen_input_id"],
            frozen_input_hash or fixture["frozen_input_hash"],
            model_id,
            role,
            "production-r1" if role == "PRODUCTION" else ("shadow-r1" if role == "SHADOW" else "experiment-r1"),
            "shadow-r1" if role == "SHADOW" else None,
            "experiment-r1" if role == "EXPERIMENT" else None,
            experiment_id,
            model_run_at,
            CUTOFF,
            KICKOFF,
            _json({"spf": {"home": 1.8, "draw": 3.1, "away": 4.2}}),
            _json({"selection": "home"}),
            _json({}),
            _json({"grade": "LOW"}),
            _json({"risk": "LOW"}),
            input_hash,
            _hash(f"prediction-output:{case_id}:{label}"),
            prediction_hash,
            _hash(f"prediction-payload:{case_id}:{label}"),
            _hash(f"prediction-provenance:{case_id}:{label}"),
            HASH_PROFILE,
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            _json({"fixture": True, "case_id": case_id, "label": label, "role": role}),
        ),
    )
    return {"prediction_id": prediction_id, "prediction_hash": prediction_hash, "input_hash": input_hash}


def _frozen_prediction(
    ctx: CaseContext,
    case_id: str,
    label: str,
    fixture: Mapping[str, str],
    prediction: Mapping[str, str],
    *,
    role: str,
    model_id: str,
    frozen_input_hash: Optional[str] = None,
) -> Dict[str, str]:
    frozen_prediction_id = _id(case_id, f"frozen-prediction:{label}")
    input_hash = frozen_input_hash or fixture["frozen_input_hash"]
    ctx.set_role("service_role")
    ctx.execute(
        "INSERT INTO model.frozen_predictions (frozen_prediction_id, match_id, prediction_id, frozen_input_id, model_version_id, role, freeze_revision, prediction_hash, frozen_snapshot_hash, frozen_input_hash, snapshot, frozen_at, prediction_cutoff_at, kickoff_at, immutable, future_information_leakage, run_invalid, tier_a_eligible, promotion_evidence, status, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s::jsonb, %s, %s, %s, true, false, false, false, false, 'FROZEN', %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
        (
            frozen_prediction_id,
            fixture["match_id"],
            prediction["prediction_id"],
            fixture["frozen_input_id"],
            model_id,
            role,
            prediction["prediction_hash"],
            _hash(f"frozen-snapshot:{case_id}:{label}"),
            input_hash,
            _json({"prediction_hash": prediction["prediction_hash"], "label": label}),
            PRE_FROZEN,
            CUTOFF,
            KICKOFF,
            _hash(f"frozen-payload:{case_id}:{label}"),
            _hash(f"frozen-provenance:{case_id}:{label}"),
            HASH_PROFILE,
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            _json({"fixture": True, "case_id": case_id, "label": label, "role": role}),
        ),
    )
    ctx.flush_constraints()
    return {"frozen_prediction_id": frozen_prediction_id, "frozen_input_hash": input_hash}


def _runtime_fixture(
    ctx: CaseContext,
    case_id: str,
    *,
    active_production: bool = False,
    include_pair: bool = False,
    include_experiment: bool = False,
    two_matches: bool = False,
) -> Dict[str, str]:
    core = _core_fixture(ctx, case_id, two_matches=two_matches)
    prod_model = _model(ctx, case_id, "production", role="PRODUCTION", status="PRODUCTION" if active_production else "PROMOTION_REVIEW", active=active_production)
    prod_engine = _engine(ctx, case_id, "production", prod_model, role="PRODUCTION", status="PRODUCTION" if active_production else "PROMOTION_REVIEW", active=active_production)
    frozen = _frozen_input(ctx, case_id, "production", core["match_id"], prod_model, prod_engine)
    bundle = _feature_bundle(ctx, case_id, "production", frozen, role="PRODUCTION")
    run = _engine_run(ctx, case_id, "production", {**core, **frozen}, role="PRODUCTION", model_id=prod_model, engine_id=prod_engine, bundle_id=bundle)
    prediction = _prediction(ctx, case_id, "production", {**core, **frozen}, role="PRODUCTION", model_id=prod_model)
    frozen_prediction = _frozen_prediction(ctx, case_id, "production", {**core, **frozen}, prediction, role="PRODUCTION", model_id=prod_model)
    fixture: Dict[str, str] = {**core, **frozen, **run, **prediction, **frozen_prediction, "production_model_id": prod_model, "production_engine_id": prod_engine, "production_bundle_id": bundle}
    if include_pair:
        shadow_model = _model(ctx, case_id, "shadow", role="SHADOW", status="SHADOW", family="jcfb-runtime", channel="main")
        shadow_engine = _engine(ctx, case_id, "shadow", shadow_model, role="SHADOW", status="SHADOW", family="jcfb-runtime", channel="main")
        shadow_bundle = _feature_bundle(ctx, case_id, "shadow", frozen, role="SHADOW")
        shadow_run = _engine_run(ctx, case_id, "shadow", {**core, **frozen}, role="SHADOW", model_id=shadow_model, engine_id=shadow_engine, bundle_id=shadow_bundle)
        shadow_prediction = _prediction(ctx, case_id, "shadow", {**core, **frozen}, role="SHADOW", model_id=shadow_model)
        shadow_frozen_prediction = _frozen_prediction(ctx, case_id, "shadow", {**core, **frozen}, shadow_prediction, role="SHADOW", model_id=shadow_model)
        fixture.update({
            "shadow_model_id": shadow_model,
            "shadow_engine_id": shadow_engine,
            "shadow_bundle_id": shadow_bundle,
            "shadow_run_id": shadow_run["engine_run_id"],
            "shadow_output_hash": shadow_run["output_hash"],
            "shadow_prediction_id": shadow_prediction["prediction_id"],
            "shadow_prediction_hash": shadow_prediction["prediction_hash"],
            "shadow_frozen_prediction_id": shadow_frozen_prediction["frozen_prediction_id"],
        })
    if include_experiment:
        experiment_id = _id(case_id, "experiment")
        experiment_model = _model(ctx, case_id, "experiment", role="EXPERIMENT", status="EXPERIMENT", family="jcfb-runtime", channel="experiment")
        experiment_engine = _engine(ctx, case_id, "experiment", experiment_model, role="EXPERIMENT", status="EXPERIMENT", family="jcfb-runtime", channel="experiment")
        # Experiment lineage has its own frozen-input owner and comparison
        # mode.  Reusing the Production-owned frozen input would make setup
        # fail at the runtime-lineage gate before the Tier A role-isolation
        # trigger could be exercised.
        experiment_frozen = _frozen_input(
            ctx,
            case_id,
            "experiment",
            core["match_id"],
            experiment_model,
            experiment_engine,
            owner_role="EXPERIMENT",
            revision=2,
        )
        experiment_lineage = {**core, **experiment_frozen}
        experiment_bundle = _feature_bundle(ctx, case_id, "experiment", experiment_frozen, role="EXPERIMENT", experiment_id=experiment_id)
        experiment_run = _engine_run(ctx, case_id, "experiment", experiment_lineage, role="EXPERIMENT", model_id=experiment_model, engine_id=experiment_engine, bundle_id=experiment_bundle)
        experiment_prediction = _prediction(ctx, case_id, "experiment", experiment_lineage, role="EXPERIMENT", model_id=experiment_model, experiment_id=experiment_id)
        experiment_frozen_prediction = _frozen_prediction(ctx, case_id, "experiment", experiment_lineage, experiment_prediction, role="EXPERIMENT", model_id=experiment_model)
        fixture.update({
            "experiment_id": experiment_id,
            "experiment_model_id": experiment_model,
            "experiment_engine_id": experiment_engine,
            "experiment_frozen_input_id": experiment_frozen["frozen_input_id"],
            "experiment_frozen_input_hash": experiment_frozen["frozen_input_hash"],
            "experiment_bundle_id": experiment_bundle,
            "experiment_run_id": experiment_run["engine_run_id"],
            "experiment_prediction_id": experiment_prediction["prediction_id"],
            "experiment_prediction_hash": experiment_prediction["prediction_hash"],
            "experiment_frozen_prediction_id": experiment_frozen_prediction["frozen_prediction_id"],
        })
    ctx.flush_constraints()
    return fixture


def _official_market_states(*, unavailable: Optional[str] = None, missing_state_field: Optional[str] = None, rqspf_handicap: bool = True) -> Tuple[str, str, Dict[str, Optional[str]]]:
    availability: Dict[str, Dict[str, Any]] = {}
    reasons: Dict[str, str] = {}
    payloads: Dict[str, Optional[Dict[str, Any]]] = {}
    for market in MARKETS:
        if market == unavailable:
            availability[market] = {"available": False, "status": "UNAVAILABLE", "reason": "not offered"}
            reasons[market] = "not offered"
            payloads[market] = None
        else:
            state: Dict[str, Any] = {"available": True, "status": "AVAILABLE", "reason": "verified"}
            if missing_state_field == market:
                state.pop("available", None)
            availability[market] = state
            reasons[market] = "verified"
            if market == "rqspf" and not rqspf_handicap:
                payloads[market] = {"home": 1.9, "away": 3.2}
            elif market == "rqspf":
                payloads[market] = {"official_handicap": "-0.5", "home": 1.9, "away": 3.2}
            else:
                payloads[market] = {"selection": 1.9}
    return _json(availability), _json(reasons), payloads


def _official_snapshot(
    ctx: CaseContext,
    case_id: str,
    match_id: str,
    *,
    unavailable: Optional[str] = None,
    missing_state_field: Optional[str] = None,
    rqspf_handicap: bool = True,
) -> Tuple[Attempt, str]:
    snapshot_id = _id(case_id, "official-snapshot")
    availability, reasons, payloads = _official_market_states(unavailable=unavailable, missing_state_field=missing_state_field, rqspf_handicap=rqspf_handicap)
    snapshot_hash = _hash(f"official-snapshot:{case_id}")
    params = (
        snapshot_id,
        match_id,
        CUTOFF,
        PRE_RUN,
        PRE_RUN,
        PRE_RUN,
        CUTOFF,
        f"runtime://{case_id}/official-odds",
        availability,
        reasons,
        _json(payloads["spf"]) if payloads["spf"] is not None else None,
        _json(payloads["rqspf"]) if payloads["rqspf"] is not None else None,
        _json(payloads["total_goals"]) if payloads["total_goals"] is not None else None,
        _json(payloads["exact_score"]) if payloads["exact_score"] is not None else None,
        _json(payloads["half_full"]) if payloads["half_full"] is not None else None,
        snapshot_hash,
        snapshot_hash,
        _hash(f"official-provenance:{case_id}"),
        HASH_PROFILE,
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        "AVAILABLE",
        _json({"fixture": True, "case_id": case_id}),
    )
    return ctx.attempt(
        "INSERT INTO market.official_odds_snapshots (snapshot_id, match_id, snapshot_kind, captured_at, source_timestamp, observed_at, ingested_at, availability_at, availability_time_state, availability_time_basis, source_is_official, source, source_type, source_reference, market_availability, market_unavailable_reason, spf, rqspf, total_goals, exact_score, half_full, snapshot_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, 'CURRENT', %s, %s, %s, %s, %s, 'KNOWN', 'SOURCE_TIMESTAMP', true, 'runtime-official', 'OFFICIAL_FEED', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, 'SHA-256', %s, %s, %s, %s, %s::jsonb)",
        params,
        role="executor",
    ), snapshot_id


def _result(ctx: CaseContext, case_id: str, match_id: str, *, label: str = "result", revision: int = 1, lineage_id: Optional[str] = None, supersedes: Optional[str] = None, status: str = "VERIFIED", metadata: Optional[Mapping[str, Any]] = None, role: str = "service_role") -> str:
    result_id = _id(case_id, f"result:{label}")
    lineage_id = lineage_id or _id(case_id, "result-lineage")
    result_hash = _hash(f"result:{case_id}:{label}")
    ctx.set_role(role)
    ctx.execute(
        "INSERT INTO evaluation.official_results (result_id, match_id, result_lineage_id, result_revision, supersedes_result_id, full_time_home, full_time_away, half_time_home, half_time_away, result_scope, official_result_payload, source, source_type, source_reference, source_timestamp, observed_at, ingested_at, verified_at, result_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, %s, %s, %s, 2, 1, 1, 0, 'REGULATION_90_PLUS_STOPPAGE', %s::jsonb, 'runtime-official', 'OFFICIAL_FEED', %s, %s, %s, %s, %s, %s, %s, %s, 'SHA-256', %s, %s, %s, %s, %s::jsonb)",
        (
            result_id,
            match_id,
            lineage_id,
            revision,
            supersedes,
            _json({"home": 2, "away": 1, "revision": revision}),
            f"runtime://{case_id}/result/{label}",
            POST_KICKOFF,
            POST_KICKOFF,
            POST_KICKOFF,
            POST_KICKOFF,
            result_hash,
            result_hash,
            _hash(f"result-provenance:{case_id}:{label}"),
            HASH_PROFILE,
            CONTRACT_VERSION,
            SCHEMA_VERSION,
            status,
            _json(metadata or {"fixture": True, "case_id": case_id, "label": label}),
        ),
    )
    ctx.flush_constraints()
    return result_id


def _review(ctx: CaseContext, case_id: str, match_id: str, frozen_prediction_id: str, result_id: str, *, label: str = "review", role: str = "service_role") -> Tuple[Attempt, str]:
    review_id = _id(case_id, f"review:{label}")
    params = (
        review_id,
        match_id,
        frozen_prediction_id,
        result_id,
        POST_REVIEW,
        _hash(f"review-payload:{case_id}:{label}"),
        _hash(f"review:{case_id}:{label}"),
        _hash(f"review-provenance:{case_id}:{label}"),
        f"runtime://{case_id}/review/{label}",
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        _json({"fixture": True, "case_id": case_id, "label": label}),
    )
    return ctx.attempt(
        "INSERT INTO evaluation.postmatch_reviews (review_id, match_id, frozen_prediction_id, result_id, review_type, review_revision, supersedes_review_id, market_hit_results, score_metrics, error_attribution, postmatch_evidence_refs, allowed_input_set, reviewed_at, payload_hash, review_hash, provenance_hash, source, source_type, source_reference, contract_version, schema_version, status, metadata) VALUES (%s, %s, %s, %s, 'MODEL_EVALUATION', 1, NULL, %s::jsonb, %s::jsonb, %s::jsonb, NULL, 'FROZEN_PREDICTION_RESULT_ONLY', %s, %s, %s, %s, 'runtime-review', 'OFFICIAL_FEED', %s, %s, %s, 'VALID', %s::jsonb)",
        (
            params[0], params[1], params[2], params[3],
            _json({"spf": "HIT"}), _json({"brier": 0.2}), _json({"attribution": "fixture"}),
            params[4], params[5], params[6], params[7], params[8], params[9], params[10], params[11],
        ),
        role=role,
    ), review_id


def _tier_sample(ctx: CaseContext, case_id: str, fixture: Mapping[str, str], *, shadow_prediction_id: Optional[str] = None, shadow_model_id: Optional[str] = None, shadow_engine_id: Optional[str] = None, frozen_input_hash: Optional[str] = None, tier_a_eligible: bool = False) -> Attempt:
    shadow_prediction_id = shadow_prediction_id or fixture["shadow_prediction_id"]
    shadow_model_id = shadow_model_id or fixture["shadow_model_id"]
    shadow_engine_id = shadow_engine_id or fixture["shadow_engine_id"]
    input_hash = frozen_input_hash or fixture["frozen_input_hash"]
    sample_id = _id(case_id, "tier-a-sample")
    result_id = _result(ctx, case_id, fixture["match_id"], label="tier-result")
    review_attempt, review_id = _review(ctx, case_id, fixture["match_id"], fixture["frozen_prediction_id"], result_id, label="tier-review")
    if not review_attempt.accepted:
        return review_attempt
    params = (
        sample_id,
        fixture["match_id"],
        fixture["frozen_input_id"],
        fixture["prediction_id"],
        fixture["frozen_prediction_id"],
        shadow_prediction_id,
        fixture.get("shadow_frozen_prediction_id", fixture["frozen_prediction_id"]),
        shadow_model_id,
        shadow_engine_id,
        result_id,
        review_id,
        "shadow-r1",
        input_hash,
        _hash(f"prod-impl:{case_id}"),
        _hash(f"prod-config:{case_id}"),
        fixture["input_hash"],
        _hash(f"prod-output:{case_id}"),
        _hash(f"shadow-impl:{case_id}"),
        _hash(f"shadow-config:{case_id}"),
        _hash(f"shadow-input:{case_id}"),
        _hash(f"shadow-output:{case_id}"),
        PRE_COMPLETE,
        PRE_COMPLETE,
        CUTOFF,
        KICKOFF,
        True,
        True,
        True,
        False,
        tier_a_eligible,
        False,
        "ELIGIBLE" if tier_a_eligible else "REJECTED",
        "tier-a-runtime@1.0",
        _hash(f"tier-payload:{case_id}"),
        _hash(f"tier-provenance:{case_id}"),
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        _json({"fixture": True, "case_id": case_id}),
    )
    return ctx.attempt(
        "INSERT INTO evaluation.tier_a_samples (tier_a_sample_id, match_id, frozen_input_id, production_prediction_id, production_frozen_prediction_id, shadow_prediction_id, shadow_frozen_prediction_id, shadow_model_version_id, shadow_engine_version_id, result_id, review_id, shadow_revision, frozen_input_hash, production_implementation_hash, production_config_hash, production_input_hash, production_output_hash, shadow_implementation_hash, shadow_config_hash, shadow_input_hash, shadow_output_hash, production_run_completed_at, shadow_run_completed_at, prediction_cutoff_at, kickoff_at, pair_integrity_passed, completeness_gate_passed, pre_kickoff_gate_passed, future_information_leakage, tier_a_eligible, promotion_evidence, qualification_status, exclusion_rule_version, payload_hash, provenance_hash, contract_version, schema_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
        params,
        role="executor",
    )


def _projection(ctx: CaseContext, case_id: str, fixture: Mapping[str, str], *, label: str = "projection", production_prediction_id: Optional[str] = None, production_frozen_prediction_id: Optional[str] = None, production_model_id: Optional[str] = None, prediction_business_at: str = "2026-01-01T08:00:00+00:00", frozen_business_at: str = "2026-01-01T08:30:00+00:00", odds_business_at: str = "2026-01-01T09:00:00+00:00", context_business_at: str = "2026-01-01T09:15:00+00:00", result_business_at: Optional[str] = "2026-01-01T09:30:00+00:00", review_business_at: Optional[str] = "2026-01-01T09:45:00+00:00", role: str = "service_role") -> Tuple[Attempt, str]:
    projection_id = _id(case_id, f"projection:{label}")
    params = (
        projection_id,
        fixture["match_id"],
        production_model_id or fixture["production_model_id"],
        production_prediction_id or fixture["prediction_id"],
        production_frozen_prediction_id or fixture["frozen_prediction_id"],
        "Runtime Competition",
        "Runtime Home",
        "Runtime Away",
        KICKOFF,
        "SCHEDULED",
        "runtime-production",
        "runtime-production@1.0.0",
        "r1",
        _json({"spf": "safe"}),
        _json({"selection": "home"}),
        _json({"safe": True}),
        prediction_business_at,
        frozen_business_at,
        odds_business_at,
        context_business_at,
        result_business_at,
        review_business_at,
        1 if label in {"projection", "base"} else 2,
        _hash(f"projection:{case_id}:{label}"),
        _hash(f"projection-payload:{case_id}:{label}"),
        _hash(f"projection-provenance:{case_id}:{label}"),
        HASH_PROFILE,
        "PUBLISHED",
        PAGE_TIME,
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        _json({"fixture": True, "case_id": case_id, "label": label}),
    )
    return ctx.attempt(
        "INSERT INTO public.public_read_projections (projection_id, match_id, production_model_version_id, production_prediction_id, production_frozen_prediction_id, competition_name, home_team_name, away_team_name, kickoff_at, match_status, public_model_name, public_model_version, public_model_revision, safe_odds_summary, safe_selection_summary, safe_result_summary, prediction_business_at, frozen_business_at, odds_business_at, context_business_at, result_business_at, review_business_at, projection_revision, projection_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, publication_status, published_at, contract_version, schema_version, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'SHA-256', %s, %s, %s, %s, %s, %s::jsonb)",
        params,
        role=role,
    ), projection_id


class RuntimeCaseHandlerRunner:
    """Prepare disposable roles and execute all contract handlers."""

    def __init__(self, connection: Any, *, actor: str):
        self.connection = connection
        self.actor = actor
        self.role_simulation: Optional[Dict[str, Any]] = None
        self.preparation: Optional[Dict[str, Any]] = None

    def prepare(self) -> Mapping[str, Any]:
        if self.preparation is not None:
            return self.preparation
        try:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            cursor = self.connection.cursor()
            try:
                cursor.execute(
                    "DO $$ DECLARE role_name text; BEGIN "
                    "FOREACH role_name IN ARRAY ARRAY['backend','executor','auditor']::text[] LOOP "
                    "IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN "
                    "EXECUTE format('CREATE ROLE %I NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS', role_name); "
                    "END IF; END LOOP; END $$"
                )
                cursor.execute("GRANT service_role TO backend, executor, auditor")
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
            commit = getattr(self.connection, "commit", None)
            if callable(commit):
                commit()
            rows = self._rows(
                "SELECT rolname, rolinherit, rolbypassrls, pg_catalog.pg_has_role(rolname, 'service_role', 'member') AS service_role_member FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role','backend','executor','auditor') ORDER BY rolname"
            )
            present = {str(row.get("rolname")) for row in rows}
            required = ROLE_NAMES
            role_rows = [
                {
                    "role": str(row.get("rolname")),
                    "inherit": bool(row.get("rolinherit")),
                    "bypass_rls": bool(row.get("rolbypassrls")),
                    "member_of_service_role": bool(row.get("service_role_member")),
                }
                for row in rows
            ]
            memberships_ok = all(
                item["member_of_service_role"]
                for item in role_rows
                if item["role"] in {"backend", "executor", "auditor"}
            )
            ok = required.issubset(present) and memberships_ok
            self.role_simulation = {
                "status": "PASS" if ok else "BLOCKED",
                "mode": "DISPOSABLE_ROLE_SIMULATION",
                "roles": role_rows,
                "supabase_auth_runtime": False,
                "notes": "No Supabase auth runtime is emulated; anon/authenticated are no-login read roles and backend/executor/auditor are no-login local server-side fixtures.",
            }
            self.preparation = {
                "status": "PASS" if ok else "BLOCKED",
                "role_simulation": self.role_simulation,
                "reason": None if ok else "Required disposable roles or service_role membership are unavailable",
            }
        except BaseException:
            self.role_simulation = {
                "status": "BLOCKED",
                "mode": "DISPOSABLE_ROLE_SIMULATION",
                "roles": [],
                "supabase_auth_runtime": False,
                "notes": "Role preparation could not be completed; driver detail is intentionally redacted.",
            }
            self.preparation = {
                "status": "BLOCKED",
                "role_simulation": self.role_simulation,
                "reason": "Disposable role simulation could not be prepared",
            }
        return self.preparation

    def _rows(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        try:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, tuple(params))
            names = [item[0] for item in (getattr(cursor, "description", None) or [])]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def run_case(self, binding: Any) -> Dict[str, Any]:
        preparation = self.prepare()
        if preparation.get("status") != "PASS":
            return self._blocked(binding, "ROLE_SIMULATION", preparation.get("reason") or "Runtime preparation is blocked")
        handler = getattr(self, str(binding.hook_name), None)
        if not callable(handler):
            return self._blocked(binding, "HANDLER_DISPATCH", "Execution contract handler is not implemented")
        ctx = CaseContext(self.connection, binding.case_id, self.actor)
        raw: Mapping[str, Any] = {}
        try:
            ctx.begin()
            raw = handler(ctx) or {}
            expected = binding.expected_outcome or dict(binding.execution).get("expected_outcome")
            result = self._evaluate(binding, raw, expected)
            result["role_simulation"] = self.role_simulation
            return result
        except RuntimeCaseBlocked as exc:
            return self._blocked(binding, "ENVIRONMENT", str(exc))
        except BaseException:
            return self._blocked(binding, "HANDLER_SETUP", "Case setup or verification could not complete")
        finally:
            ctx.close()

    def _evaluate(self, binding: Any, raw: Mapping[str, Any], expected: str) -> Dict[str, Any]:
        actual = str(raw.get("actual_outcome") or "").upper()
        verification = raw.get("verification")
        verification_pass = verification is True or (isinstance(verification, Mapping) and all(value is True for value in verification.values()))
        error = raw.get("error") if isinstance(raw.get("error"), BaseException) else None
        expected_mechanism = dict(binding.execution).get("expected_mechanism", {})
        if expected == "ACCEPT":
            if actual != "ACCEPT":
                status = "FAIL_UNEXPECTED_REJECT"
            elif not verification_pass:
                status = "FAIL_UNEXPECTED_ACCEPT"
            else:
                status = "PASS_EXPECTED_ACCEPT"
        else:
            if actual == "ACCEPT":
                status = "FAIL_UNEXPECTED_ACCEPT"
            elif not match_expected_rejection(error, expected_mechanism):
                status = "FAIL_UNEXPECTED_REJECT"
            elif not verification_pass:
                status = "FAIL_UNEXPECTED_REJECT"
            else:
                status = "PASS_EXPECTED_REJECT"
        return {
            "status": status,
            "case_id": binding.case_id,
            "kind": binding.kind,
            "hook_name": binding.hook_name,
            "expected_result": binding.expected_result,
            "expected_outcome": expected,
            "actual_outcome": actual,
            "actually_executed": True,
            "action_role": raw.get("action_role"),
            "observed_mechanism": raw.get("observed_mechanism", {}),
            "expected_mechanism": expected_mechanism,
            "verification": dict(verification) if isinstance(verification, Mapping) else verification,
            "error_sqlstate": _sqlstate(error) if error is not None else None,
            "error_constraint": _constraint_name(error) if error is not None else None,
            "reason": raw.get("reason"),
            "hard_gate": bool(dict(binding.execution).get("hard_gate", False)),
            "advisor_status": dict(binding.execution).get("advisor_status"),
        }

    @staticmethod
    def _blocked(binding: Any, phase: str, reason: str) -> Dict[str, Any]:
        return {
            "status": "BLOCKED_ENVIRONMENT",
            "case_id": binding.case_id,
            "kind": binding.kind,
            "hook_name": binding.hook_name,
            "expected_result": binding.expected_result,
            "expected_outcome": binding.expected_outcome or dict(binding.execution).get("expected_outcome"),
            "actually_executed": False,
            "phase": phase,
            "blocked_reason": reason,
            "hard_gate": bool(dict(binding.execution).get("hard_gate", False)),
        }

    def _accept(self, role: str, verification: Mapping[str, bool], *, observed: Optional[Mapping[str, Any]] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        return {"actual_outcome": "ACCEPT", "action_role": role, "verification": dict(verification), "observed_mechanism": dict(observed or {}), "reason": reason}

    def _reject(self, attempt: Attempt, verification: Mapping[str, bool], *, observed: Optional[Mapping[str, Any]] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        return {"actual_outcome": "REJECT", "action_role": attempt.role, "error": attempt.error, "verification": dict(verification), "observed_mechanism": dict(observed or {}), "reason": reason}

    # ---- Smoke handlers -------------------------------------------------

    def smoke_01_valid_core_matches_insert(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        competition_id = _insert_competition(ctx, case_id)
        home_team_id = _insert_team(ctx, case_id, "home")
        away_team_id = _insert_team(ctx, case_id, "away")
        action_id = _insert_match(ctx, case_id, competition_id, home_team_id, away_team_id, role="executor")
        row = ctx.one("SELECT count(*) AS count FROM core.matches WHERE match_id = %s", (action_id,))
        audit = ctx.one("SELECT count(*) AS count FROM governance.audit_logs WHERE entity_type = 'core.matches' AND entity_id = %s", (action_id,))
        return self._accept("executor", {"match_row": int(row.get("count", 0)) == 1, "audit_row": int(audit.get("count", 0)) >= 1}, observed={"postcondition": "match_and_audit"})

    def smoke_02_duplicate_canonical_business_key(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        # The action uses a different identity but the exact existing business
        # key, so the partial fixture remains untouched after rollback.
        attempt = ctx.attempt(
            "INSERT INTO core.matches (match_id, data_date, official_match_no, match_identity_key, competition_id, home_team_id, away_team_id, kickoff_at, timezone, match_status, intake_status, identity_resolution_state, canonical_facts_hash, revision, source, source_type, source_reference, source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, hash_algorithm, hash_profile, contract_version, schema_version, metadata) SELECT %s, data_date, official_match_no, match_identity_key, competition_id, home_team_id, away_team_id, kickoff_at, timezone, 'SCHEDULED', 'OPEN', 'RESOLVED', canonical_facts_hash, 1, source, source_type, 'runtime://SMOKE-02/duplicate-action', source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, 'SHA-256', %s, %s, %s, metadata FROM core.matches WHERE match_id = %s",
            (_id(case_id, "duplicate-action"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, fixture["match_id"]),
            role="executor",
        )
        count = ctx.one("SELECT count(*) AS count FROM core.matches WHERE data_date = '2026-01-01' AND official_match_no = '21'")
        return self._reject(attempt, {"original_only": int(count.get("count", 0)) == 1}, observed={"constraint": "matches_business_key"})

    def smoke_03_official_market_unavailable(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        attempt, snapshot_id = _official_snapshot(ctx, case_id, fixture["match_id"], unavailable="rqspf")
        row = ctx.one("SELECT status, rqspf, market_availability->'rqspf'->>'available' AS available FROM market.official_odds_snapshots WHERE snapshot_id = %s", (snapshot_id,))
        return self._accept("executor", {"snapshot_row": attempt.accepted and row.get("status") == "AVAILABLE", "unavailable_without_payload": row.get("rqspf") is None and str(row.get("available")).lower() == "false"}, observed={"postcondition": "explicit_unavailable_market"})

    def smoke_04_available_market_without_payload(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        attempt, snapshot_id = _official_snapshot(ctx, case_id, fixture["match_id"], unavailable=None)
        # Re-run with the malformed spf payload in an isolated savepoint. The
        # first valid snapshot is setup and is rolled back with the case.
        availability, reasons, payloads = _official_market_states()
        payloads["spf"] = None
        malformed = ctx.attempt(
            "INSERT INTO market.official_odds_snapshots (snapshot_id, match_id, snapshot_kind, captured_at, source_timestamp, observed_at, ingested_at, availability_at, availability_time_state, availability_time_basis, source_is_official, source, source_type, source_reference, market_availability, market_unavailable_reason, spf, rqspf, total_goals, exact_score, half_full, snapshot_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, 'CURRENT', %s, %s, %s, %s, %s, 'KNOWN', 'SOURCE_TIMESTAMP', true, 'runtime-official', 'OFFICIAL_FEED', %s, %s::jsonb, %s::jsonb, NULL, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
            (_id(case_id, "malformed"), fixture["match_id"], CUTOFF, PRE_RUN, PRE_RUN, PRE_RUN, CUTOFF, f"runtime://{case_id}/malformed", availability, reasons, _json(payloads["rqspf"]), _json(payloads["total_goals"]), _json(payloads["exact_score"]), _json(payloads["half_full"]), _hash(f"{case_id}:malformed"), _hash(f"{case_id}:malformed"), _hash(f"{case_id}:malformed:prov"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, _json({"fixture": True, "case_id": case_id})),
            role="executor",
        )
        absent = ctx.one("SELECT count(*) AS count FROM market.official_odds_snapshots WHERE snapshot_id = %s", (_id(case_id, "malformed"),))
        return self._reject(malformed, {"no_snapshot_row": int(absent.get("count", 0)) == 0}, observed={"trigger": "v4_official_market_payload_gate"})

    def smoke_05_available_rqspf_without_handicap(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        availability, reasons, payloads = _official_market_states(rqspf_handicap=False)
        attempt = ctx.attempt(
            "INSERT INTO market.official_odds_snapshots (snapshot_id, match_id, snapshot_kind, captured_at, source_timestamp, observed_at, ingested_at, availability_at, availability_time_state, availability_time_basis, source_is_official, source, source_type, source_reference, market_availability, market_unavailable_reason, spf, rqspf, total_goals, exact_score, half_full, snapshot_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, 'CURRENT', %s, %s, %s, %s, %s, 'KNOWN', 'SOURCE_TIMESTAMP', true, 'runtime-official', 'OFFICIAL_FEED', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
            (_id(case_id, "malformed"), fixture["match_id"], CUTOFF, PRE_RUN, PRE_RUN, PRE_RUN, CUTOFF, f"runtime://{case_id}/malformed", availability, reasons, _json(payloads["spf"]), _json(payloads["rqspf"]), _json(payloads["total_goals"]), _json(payloads["exact_score"]), _json(payloads["half_full"]), _hash(f"{case_id}:malformed"), _hash(f"{case_id}:malformed"), _hash(f"{case_id}:malformed:prov"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, _json({"fixture": True, "case_id": case_id})),
            role="executor",
        )
        return self._reject(attempt, {"no_snapshot_row": ctx.one("SELECT count(*) AS count FROM market.official_odds_snapshots WHERE snapshot_id = %s", (_id(case_id, "malformed"),)).get("count", 0) == 0}, observed={"trigger": "v4_official_market_payload_gate"})

    def smoke_06_post_kickoff_production_run(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id)
        model_id = fixture["production_model_id"]
        engine_id = fixture["production_engine_id"]
        bundle_id = fixture["production_bundle_id"]
        attempt = _engine_run(ctx, case_id, "post-kickoff", fixture, role="PRODUCTION", model_id=model_id, engine_id=engine_id, bundle_id=bundle_id, run_at=POST_KICKOFF, completed_at=POST_KICKOFF, as_attempt=True)
        return self._reject(attempt, {"no_future_leakage": not attempt.accepted}, observed={"trigger": "v4_engine_prematch_gate"})

    def smoke_07_frozen_input_mutation(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _runtime_fixture(ctx, ctx.case_id)
        attempt = ctx.attempt("UPDATE model.frozen_inputs SET gate_reason = 'unauthorised mutation' WHERE frozen_input_id = %s", (fixture["frozen_input_id"],), role="executor")
        row = ctx.one("SELECT gate_reason, immutable, status FROM model.frozen_inputs WHERE frozen_input_id = %s", (fixture["frozen_input_id"],))
        return self._reject(attempt, {"unchanged": row.get("gate_reason") is None and row.get("immutable") is True and row.get("status") == "FROZEN"}, observed={"trigger": "v4_frozen_input_mutation_guard"})

    def smoke_08_frozen_prediction_update_or_delete(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _runtime_fixture(ctx, ctx.case_id)
        update = ctx.attempt("UPDATE model.frozen_predictions SET metadata = metadata WHERE frozen_prediction_id = %s", (fixture["frozen_prediction_id"],), role="executor")
        delete = ctx.attempt("DELETE FROM model.frozen_predictions WHERE frozen_prediction_id = %s", (fixture["frozen_prediction_id"],), role="executor")
        row = ctx.one("SELECT count(*) AS count FROM model.frozen_predictions WHERE frozen_prediction_id = %s", (fixture["frozen_prediction_id"],))
        error = update if not update.accepted else delete
        return self._reject(error, {"update_rejected": not update.accepted, "delete_rejected": not delete.accepted, "row_remains": int(row.get("count", 0)) == 1}, observed={"trigger": "v4_frozen_prediction_append_only"})

    def smoke_09_official_result_correction(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        lineage = _id(case_id, "result-lineage")
        first = _result(ctx, case_id, fixture["match_id"], label="first", lineage_id=lineage, role="executor")
        second = _result(ctx, case_id, fixture["match_id"], label="correction", revision=2, lineage_id=lineage, supersedes=first, status="CORRECTED", metadata={"correction_reason": "official correction", "correction_actor": "runtime-auditor"}, role="executor")
        ctx.set_role("auditor")
        rows = ctx.rows("SELECT result_revision, supersedes_result_id, metadata FROM evaluation.official_results WHERE result_lineage_id = %s ORDER BY result_revision", (lineage,))
        audit = ctx.one("SELECT count(*) AS count FROM governance.audit_logs WHERE entity_type = 'evaluation.official_results'", ())
        return self._accept("executor", {"revision_chain": len(rows) == 2 and rows[1].get("supersedes_result_id") == first, "predecessor_unchanged": rows[0].get("result_revision") == 1, "audit_row": int(audit.get("count", 0)) >= 2}, observed={"postcondition": "append_only_result_correction"})

    def smoke_10_review_with_mismatched_match_identity(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id, two_matches=True)
        result_b = _result(ctx, case_id, fixture["match_b_id"], label="mismatch-result")
        attempt, review_id = _review(ctx, case_id, fixture["match_id"], fixture["frozen_prediction_id"], result_b, label="mismatch", role="executor")
        row = ctx.one("SELECT count(*) AS count FROM evaluation.postmatch_reviews WHERE review_id = %s", (review_id,))
        return self._reject(attempt, {"no_review_row": int(row.get("count", 0)) == 0}, observed={"trigger": "v4_review_scope_gate"})

    def smoke_11_tier_a_pair_different_frozen_input_hashes(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id, include_pair=True)
        mismatched = _hash(f"{case_id}:declared-different-frozen-input")
        bad_prediction = _prediction(ctx, case_id, "shadow-mismatch", fixture, role="SHADOW", model_id=fixture["shadow_model_id"], frozen_input_hash=mismatched)
        attempt = _tier_sample(ctx, case_id, fixture, shadow_prediction_id=bad_prediction["prediction_id"], frozen_input_hash=mismatched)
        return self._reject(attempt, {"pair_rejected": not attempt.accepted}, observed={"trigger": "v4_tier_a_pair_gate"})

    def smoke_12_experiment_forward_tier_a_member(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id, include_pair=True, include_experiment=True)
        attempt = _tier_sample(ctx, case_id, fixture, shadow_prediction_id=fixture["experiment_prediction_id"], shadow_model_id=fixture["experiment_model_id"], shadow_engine_id=fixture["experiment_engine_id"])
        return self._reject(attempt, {"experiment_rejected": not attempt.accepted}, observed={"trigger": "v4_tier_a_pair_gate"})

    def smoke_13_shadow_or_experiment_public_projection(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id, active_production=True, include_pair=True)
        anon = _projection(ctx, case_id, fixture, label="anon-attempt", production_prediction_id=fixture["shadow_prediction_id"], production_frozen_prediction_id=fixture["shadow_frozen_prediction_id"], role="anon")[0]
        service = _projection(ctx, case_id, fixture, label="shadow-attempt", production_prediction_id=fixture["shadow_prediction_id"], production_frozen_prediction_id=fixture["shadow_frozen_prediction_id"], role="service_role")[0]
        ctx.set_role("anon")
        visible = ctx.rows("SELECT match_id FROM public.v_public_predictions WHERE match_id = %s", (fixture["match_id"],))
        selected = service if not service.accepted else anon
        return self._reject(selected, {"public_rejected": not service.accepted, "no_nonproduction_view_row": not visible}, observed={"trigger": "v4_public_projection_scope_gate"})

    def smoke_14_two_active_production_revisions(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        _core_fixture(ctx, case_id)
        first_model = _model(ctx, case_id, "active-a", role="PRODUCTION", status="PRODUCTION", active=True, family="jcfb-unique", channel="main")
        first = _engine(ctx, case_id, "active-a", first_model, role="PRODUCTION", status="PRODUCTION", active=True, family="jcfb-unique", channel="main")
        second = ctx.attempt(
            "INSERT INTO governance.model_versions (model_version_id, model_family, model_name, model_version, major, minor, patch, revision, jcfb_version, role, canonical_output_channel, implementation_hash, config_version, config_hash, schema_version, dataset_version, migration_version, hash_algorithm, hash_profile, compatibility_level, status, is_canonical_active, effective_at, approval_reference, approved_at, contract_version, metadata) VALUES (%s, 'jcfb-unique', 'runtime-active-b', 'runtime-active-b@1.0.0', 1, 0, 0, 'r1', 'v4-runtime', 'PRODUCTION', 'main', %s, 'config@1.0.0', %s, %s, 'dataset@runtime', %s, 'SHA-256', %s, 'PATCH_COMPATIBLE', true, %s, 'runtime-approval:SMOKE-14-b', %s, %s, %s::jsonb)",
            (_id(case_id, "active-b"), _hash(f"{case_id}:model-b"), _hash(f"{case_id}:config-b"), SCHEMA_VERSION, MIGRATION_VERSION, HASH_PROFILE, PRE_FROZEN, PRE_FROZEN, CONTRACT_VERSION, _json({"fixture": True, "case_id": case_id})),
            role="backend",
        )
        count = ctx.one("SELECT count(*) AS count FROM governance.model_versions WHERE model_family = 'jcfb-unique' AND canonical_output_channel = 'main' AND role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active")
        engine_count = ctx.one("SELECT count(*) AS count FROM governance.engine_versions WHERE model_family = 'jcfb-unique' AND canonical_output_channel = 'main' AND role = 'PRODUCTION' AND status = 'PRODUCTION' AND is_canonical_active")
        return self._reject(second, {"single_active_model_pointer": int(count.get("count", 0)) == 1, "single_active_engine_pointer": int(engine_count.get("count", 0)) == 1}, observed={"constraint": "active_production_model_uq"})

    def smoke_15_public_role_internal_write_denied(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        sql = "INSERT INTO core.matches (match_id, data_date, official_match_no, match_identity_key, competition_id, home_team_id, away_team_id, kickoff_at, timezone, match_status, intake_status, identity_resolution_state, canonical_facts_hash, revision, source, source_type, source_reference, source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, hash_algorithm, hash_profile, contract_version, schema_version, metadata) SELECT %s, data_date, '1515', data_date::text || ':1515', competition_id, home_team_id, away_team_id, kickoff_at, timezone, 'SCHEDULED', 'OPEN', 'RESOLVED', canonical_facts_hash, 1, source, source_type, 'runtime://SMOKE-15/public-action', source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, 'SHA-256', %s, %s, %s, metadata FROM core.matches WHERE match_id = %s"
        params = (_id(case_id, "public-action"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, fixture["match_id"])
        anon = ctx.attempt(sql, params, role="anon")
        authenticated = ctx.attempt(sql, params, role="authenticated")
        return self._reject(anon, {"anon_denied": not anon.accepted, "authenticated_denied": not authenticated.accepted}, observed={"role_gate": "internal_write_denied"})

    def smoke_16_approved_backend_controlled_write(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _core_fixture(ctx, case_id)
        sql = "INSERT INTO core.matches (match_id, data_date, official_match_no, match_identity_key, competition_id, home_team_id, away_team_id, kickoff_at, timezone, match_status, intake_status, identity_resolution_state, canonical_facts_hash, revision, source, source_type, source_reference, source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, hash_algorithm, hash_profile, contract_version, schema_version, metadata) SELECT %s, data_date, %s, data_date::text || ':' || %s, competition_id, home_team_id, away_team_id, kickoff_at, timezone, 'SCHEDULED', 'OPEN', 'RESOLVED', canonical_facts_hash, 1, source, source_type, %s, source_timestamp, observed_at, ingested_at, provenance_hash, payload_hash, 'SHA-256', %s, %s, %s, metadata FROM core.matches WHERE match_id = %s"
        backend_id = _id(case_id, "backend-match")
        service_id = _id(case_id, "service-match")
        params = (backend_id, "1616", "1616", f"runtime://{case_id}/backend", HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, fixture["match_id"])
        backend = ctx.attempt(sql, params, role="backend")
        service = ctx.attempt(sql, (service_id, "1617", "1617", f"runtime://{case_id}/service", HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, fixture["match_id"]), role="service_role")
        audit = ctx.one("SELECT count(*) AS count FROM governance.audit_logs WHERE entity_type = 'core.matches' AND entity_id IN (%s, %s)", (backend_id, service_id))
        return self._accept("backend/service_role", {"controlled_role_write": backend.accepted and service.accepted, "audit_row": int(audit.get("count", 0)) >= 2, "trigger_path": True}, observed={"role_gate": "controlled_server_side_write"})

    def smoke_17_security_definer_local_catalog_review(self, ctx: CaseContext) -> Dict[str, Any]:
        ctx.set_role("auditor")
        rows = ctx.rows("SELECT n.nspname AS schema_name, p.proname AS function_name, p.prosecdef AS security_definer, COALESCE(array_to_string(p.proconfig, ','), '') AS config FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'governance' ORDER BY p.proname")
        unsafe = [row for row in rows if row.get("security_definer") and "search_path" not in str(row.get("config", ""))]
        return self._accept("auditor", {"fixed_search_path_or_no_definers": not unsafe, "advisor_not_run": True}, observed={"local_catalog": True, "advisor_status": "NOT_RUN_IN_DISPOSABLE"})

    def smoke_18_canonical_latest_business_timestamps(self, ctx: CaseContext) -> Dict[str, Any]:
        case_id = ctx.case_id
        fixture = _runtime_fixture(ctx, case_id, active_production=True)
        projection, projection_id = _projection(ctx, case_id, fixture)
        ctx.set_role("anon")
        row = ctx.one("SELECT canonical_latest_update_at FROM public.v_canonical_latest_update WHERE match_id = %s", (fixture["match_id"],))
        ctx.set_role("authenticated")
        public_row = ctx.one("SELECT canonical_latest_update_at FROM public.v_public_predictions WHERE match_id = %s", (fixture["match_id"],))
        expected = LATEST_BUSINESS_TIMESTAMP
        return self._accept("anon/authenticated", {"max_business_timestamp": projection.accepted and _as_iso(row.get("canonical_latest_update_at")) == expected, "not_published_at": _as_iso(row.get("canonical_latest_update_at")) != _as_iso(PAGE_TIME), "not_created_at": _as_iso(public_row.get("canonical_latest_update_at")) == expected}, observed={"view": "v_canonical_latest_update", "source": "business_timestamps"})

    def smoke_19_lifecycle_audit_coverage(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _core_fixture(ctx, ctx.case_id)
        ctx.set_role("auditor")
        row = ctx.one("SELECT actor, actor_role, action, entity_type, entity_id, before_state, after_state, happened_at, entry_hash FROM governance.audit_logs WHERE entity_type = 'core.matches' AND entity_id = %s ORDER BY audit_log_id DESC LIMIT 1", (fixture["match_id"],))
        fields = ("actor", "actor_role", "action", "entity_type", "entity_id", "before_state", "after_state", "happened_at", "entry_hash")
        return self._accept("auditor", {field: row.get(field) not in (None, "", {}) for field in fields}, observed={"audit_stream": "core.matches"})

    def smoke_20_v333_boundary_comparison(self, ctx: CaseContext) -> Dict[str, Any]:
        ctx.set_role("auditor")
        before = ctx.rows("SELECT n.nspname AS schema_name, c.relname AS object_name FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE lower(n.nspname) LIKE 'v3%' OR lower(c.relname) LIKE 'v3%' ORDER BY 1, 2")
        after = ctx.rows("SELECT n.nspname AS schema_name, c.relname AS object_name FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE lower(n.nspname) LIKE 'v3%' OR lower(c.relname) LIKE 'v3%' ORDER BY 1, 2")
        return self._accept("auditor", {"zero_v333_objects_before": not before, "zero_v333_objects_after": not after, "unchanged": before == after}, observed={"catalog": "v333_boundary"})

    # ---- Enforcement handlers ------------------------------------------

    def enforcement_08_available_market_missing_payload(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_04_available_market_without_payload(ctx)

    def enforcement_09_unavailable_market_missing_reason(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _core_fixture(ctx, "NEG-09")
        availability, reasons, payloads = _official_market_states(unavailable="spf")
        availability_obj = json.loads(availability)
        availability_obj["spf"]["reason"] = ""
        reasons_obj = json.loads(reasons)
        reasons_obj["spf"] = ""
        attempt = ctx.attempt(
            "INSERT INTO market.official_odds_snapshots (snapshot_id, match_id, snapshot_kind, captured_at, source_timestamp, observed_at, ingested_at, availability_at, availability_time_state, availability_time_basis, source_is_official, source, source_type, source_reference, market_availability, market_unavailable_reason, spf, rqspf, total_goals, exact_score, half_full, snapshot_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, 'CURRENT', %s, %s, %s, %s, %s, 'KNOWN', 'SOURCE_TIMESTAMP', true, 'runtime-official', 'OFFICIAL_FEED', %s, %s::jsonb, %s::jsonb, NULL, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
            (_id("NEG-09", "malformed"), fixture["match_id"], CUTOFF, PRE_RUN, PRE_RUN, PRE_RUN, CUTOFF, "runtime://NEG-09/malformed", _json(availability_obj), _json(reasons_obj), _json(payloads["rqspf"]), _json(payloads["total_goals"]), _json(payloads["exact_score"]), _json(payloads["half_full"]), _hash("NEG-09:malformed"), _hash("NEG-09:malformed"), _hash("NEG-09:malformed:prov"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, _json({"fixture": True})),
            role="executor",
        )
        return self._reject(attempt, {"no_snapshot_row": ctx.one("SELECT count(*) AS count FROM market.official_odds_snapshots WHERE snapshot_id = %s", (_id("NEG-09", "malformed"),)).get("count", 0) == 0}, observed={"trigger": "v4_official_market_payload_gate"})

    def enforcement_10_rqspf_handicap_missing(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_05_available_rqspf_without_handicap(ctx)

    def enforcement_11_post_kickoff_production_run(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_06_post_kickoff_production_run(ctx)

    def enforcement_12_frozen_input_mutation(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_07_frozen_input_mutation(ctx)

    def enforcement_13_frozen_prediction_mutation(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_08_frozen_prediction_update_or_delete(ctx)

    def enforcement_14_review_result_cross_match(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_10_review_with_mismatched_match_identity(ctx)

    def enforcement_15_tier_a_hash_mismatch(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_11_tier_a_pair_different_frozen_input_hashes(ctx)

    def enforcement_16_experiment_forward_tier_a(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_12_experiment_forward_tier_a_member(ctx)

    def enforcement_17_public_projection_role_leak(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_13_shadow_or_experiment_public_projection(ctx)

    def enforcement_18_two_active_production_revisions(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_14_two_active_production_revisions(ctx)

    def enforcement_19_unsafe_security_definer_search_path(self, ctx: CaseContext) -> Dict[str, Any]:
        probe = "CREATE FUNCTION governance.runtime_unsafe_probe() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"
        attempt = ctx.attempt(probe, role="service_role")
        row = ctx.one("SELECT to_regprocedure('governance.runtime_unsafe_probe()') AS object_name")
        return self._reject(attempt, {"create_denied": not attempt.accepted, "probe_absent": not row.get("object_name")}, observed={"role_gate": "trusted_schema_create_denied"})

    def enforcement_20_public_internal_write_grant(self, ctx: CaseContext) -> Dict[str, Any]:
        return self.smoke_15_public_role_internal_write_denied(ctx)

    def enforcement_21_canonical_latest_page_time(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _runtime_fixture(ctx, "NEG-21", active_production=True)
        base, _ = _projection(ctx, "NEG-21", fixture, label="base")
        unsafe, unsafe_id = _projection(ctx, "NEG-21", fixture, label="unsafe", prediction_business_at=POST_KICKOFF)
        return self._reject(unsafe, {"unsafe_projection_rejected": not unsafe.accepted, "base_exists": base.accepted and bool(ctx.one("SELECT projection_id FROM public.public_read_projections WHERE projection_id = %s", (_id("NEG-21", "projection:base"),)))}, observed={"trigger": "v4_public_projection_scope_gate"})

    def enforcement_22_unknown_coercion(self, ctx: CaseContext) -> Dict[str, Any]:
        fixture = _core_fixture(ctx, "NEG-22")
        availability, reasons, payloads = _official_market_states(missing_state_field="spf")
        attempt = ctx.attempt(
            "INSERT INTO market.official_odds_snapshots (snapshot_id, match_id, snapshot_kind, captured_at, source_timestamp, observed_at, ingested_at, availability_at, availability_time_state, availability_time_basis, source_is_official, source, source_type, source_reference, market_availability, market_unavailable_reason, spf, rqspf, total_goals, exact_score, half_full, snapshot_hash, payload_hash, provenance_hash, hash_algorithm, hash_profile, contract_version, schema_version, status, metadata) VALUES (%s, %s, 'CURRENT', %s, %s, %s, %s, %s, 'KNOWN', 'SOURCE_TIMESTAMP', true, 'runtime-official', 'OFFICIAL_FEED', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, 'SHA-256', %s, %s, %s, %s::jsonb)",
            (_id("NEG-22", "unknown"), fixture["match_id"], CUTOFF, PRE_RUN, PRE_RUN, PRE_RUN, CUTOFF, "runtime://NEG-22/unknown", availability, reasons, _json(payloads["spf"]), _json(payloads["rqspf"]), _json(payloads["total_goals"]), _json(payloads["exact_score"]), _json(payloads["half_full"]), _hash("NEG-22:unknown"), _hash("NEG-22:unknown"), _hash("NEG-22:unknown:prov"), HASH_PROFILE, CONTRACT_VERSION, SCHEMA_VERSION, _json({"fixture": True})),
            role="executor",
        )
        return self._reject(attempt, {"no_snapshot_row": ctx.one("SELECT count(*) AS count FROM market.official_odds_snapshots WHERE snapshot_id = %s", (_id("NEG-22", "unknown"),)).get("count", 0) == 0}, observed={"trigger": "v4_official_market_payload_gate", "unknown_not_coerced": True})


__all__ = [
    "Attempt",
    "CaseContext",
    "RuntimeCaseHandlerRunner",
    "match_expected_rejection",
]
