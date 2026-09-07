"""Engine output contract and common envelope validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Mapping, Sequence


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ROLES = frozenset({"PRODUCTION", "SHADOW", "EXPERIMENT"})
STATUSES = frozenset({"SUCCEEDED", "FAILED", "BLOCKED", "INVALID", "SYNTHETIC_TEST_ONLY"})
ENGINE_PAYLOADS = {
    "OUTCOME": ("outcome_probability", ("H", "D", "A")),
    "HANDICAP": ("handicap_outcome_probability", ("H", "D", "A")),
    "GOALS": ("goal_distribution", ("0", "1", "2", "3", "4", "5", "6", "7+")),
    "HTFT": ("half_full_probability", ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A")),
}
VOLATILE_FIELDS = frozenset({"created_at", "ingested_at", "observed_at", "run_at", "run_completed_at", "runtime_ms", "output_hash"})
_SECRET_TERMS = ("password", "secret", "token", "cookie", "api_key", "authorization")


class EngineRuntimeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _hash_body(envelope: Mapping[str, Any]) -> str:
    return sha256_json({key: value for key, value in envelope.items() if key not in VOLATILE_FIELDS})


def _require_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise EngineRuntimeError("HASH_INVALID", field)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise EngineRuntimeError("TIMESTAMP_INVALID", field)
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EngineRuntimeError("TIMESTAMP_INVALID", field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EngineRuntimeError("TIMEZONE_REQUIRED", field)
    return parsed


def _contains_secret(value: Any, path: str = "") -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if any(term in str(key).casefold() for term in _SECRET_TERMS):
                return True
            if _contains_secret(child, f"{path}.{key}"):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_secret(item, path) for item in value)
    return False


def _validate_distribution(value: Any, labels: Sequence[str], field: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(labels):
        raise EngineRuntimeError("DISTRIBUTION_KEYS_INVALID", field)
    numbers = []
    for label in labels:
        number = value[label]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(float(number)) or not 0 <= float(number) <= 1:
            raise EngineRuntimeError("PROBABILITY_INVALID", f"{field}.{label}")
        numbers.append(float(number))
    if abs(sum(numbers) - 1.0) > 1e-6:
        raise EngineRuntimeError("PROBABILITY_NOT_NORMALIZED", field)


def validate_engine_output(envelope: Mapping[str, Any]) -> dict[str, Any]:
    required = ("object_id", "engine_run_id", "contract_version", "role", "model_name", "model_version", "engine_name", "engine_version", "revision", "implementation_hash", "config_version", "config_hash", "schema_version", "input_hash", "frozen_input_id", "frozen_input_hash", "run_at", "run_completed_at", "runtime_ms", "runtime_environment", "status", "warnings", "errors", "payload", "output_hash")
    missing = [field for field in required if field not in envelope]
    if missing:
        raise EngineRuntimeError("ENGINE_ENVELOPE_FIELD_MISSING", ",".join(missing))
    for field in ("implementation_hash", "config_hash", "input_hash", "frozen_input_hash", "output_hash"):
        _require_hash(envelope[field], field)
    if envelope["role"] not in ROLES or envelope["status"] not in STATUSES:
        raise EngineRuntimeError("ENGINE_ENUM_INVALID", "role/status")
    if not isinstance(envelope["warnings"], list) or not isinstance(envelope["errors"], list) or not isinstance(envelope["runtime_environment"], Mapping):
        raise EngineRuntimeError("ENGINE_METADATA_INVALID", "warnings/errors/runtime_environment")
    if isinstance(envelope["runtime_ms"], bool) or not isinstance(envelope["runtime_ms"], (int, float)) or not math.isfinite(float(envelope["runtime_ms"])) or envelope["runtime_ms"] < 0:
        raise EngineRuntimeError("RUNTIME_MS_INVALID", "runtime_ms")
    start = _timestamp(envelope["run_at"], "run_at")
    end = _timestamp(envelope["run_completed_at"], "run_completed_at")
    if end < start:
        raise EngineRuntimeError("RUN_TIME_ORDER_INVALID", "run_completed_at before run_at")
    if _contains_secret(envelope["runtime_environment"]):
        raise EngineRuntimeError("SECRET_IN_RUNTIME_ENVIRONMENT", "secrets must not enter runtime_environment")
    if envelope["status"] == "SUCCEEDED" or envelope["status"] == "SYNTHETIC_TEST_ONLY":
        role = str(envelope["engine_name"]).upper().replace("_ENGINE", "")
        if role not in ENGINE_PAYLOADS:
            raise EngineRuntimeError("ENGINE_NAME_INVALID", str(envelope["engine_name"]))
        probability_field, labels = ENGINE_PAYLOADS[role]
        payload = envelope["payload"]
        if not isinstance(payload, Mapping) or probability_field not in payload:
            raise EngineRuntimeError("ENGINE_PAYLOAD_INVALID", probability_field)
        _validate_distribution(payload[probability_field], labels, probability_field)
        if envelope["errors"]:
            raise EngineRuntimeError("SUCCESS_WITH_ERRORS", "successful output must have empty errors")
    elif not envelope["errors"]:
        raise EngineRuntimeError("NON_SUCCESS_ERROR_REQUIRED", "blocked/failed/invalid output requires errors")
    if envelope["output_hash"] != _hash_body(envelope):
        raise EngineRuntimeError("OUTPUT_HASH_MISMATCH", "output_hash does not match logical envelope")
    return {"status": "PASS", "engine_name": envelope["engine_name"], "role": envelope["role"], "output_hash": envelope["output_hash"]}


def build_engine_output(*, role: str, engine_role: str, model_name: str, model_version: str, engine_version: str, revision: str, implementation_hash: str, config_version: str, config_hash: str, input_hash: str, frozen_input_id: str, frozen_input_hash: str, run_at: str, run_completed_at: str, runtime_ms: float, payload: Mapping[str, Any], status: str = "SUCCEEDED", warnings: Sequence[Mapping[str, Any]] = (), errors: Sequence[Mapping[str, Any]] = (), synthetic_test_only: bool = False) -> dict[str, Any]:
    if role not in ROLES:
        raise EngineRuntimeError("ROLE_INVALID", role)
    envelope = {
        "object_id": sha256_json({"engine_role": engine_role, "input_hash": input_hash, "revision": revision})[7:39],
        "engine_run_id": sha256_json({"engine_role": engine_role, "input_hash": input_hash, "revision": revision})[7:39],
        "contract_version": "engine-output@1.0.0",
        "role": role,
        "model_name": model_name,
        "model_version": model_version,
        "engine_name": f"{engine_role.lower()}_engine",
        "engine_version": engine_version,
        "revision": revision,
        "shadow_revision": "NOT_APPLICABLE" if role != "SHADOW" else revision,
        "experiment_revision": "NOT_APPLICABLE" if role != "EXPERIMENT" else revision,
        "implementation_hash": implementation_hash,
        "config_version": config_version,
        "config_hash": config_hash,
        "schema_version": "engine-output-schema@1.0.0",
        "input_hash": input_hash,
        "frozen_input_id": frozen_input_id,
        "frozen_input_hash": frozen_input_hash,
        "run_at": run_at,
        "run_completed_at": run_completed_at,
        "runtime_ms": runtime_ms,
        "runtime_environment": {"runtime": "jcfb-v4-prediction-runtime@1.0.0", "dependency_lock_hash": sha256_json({"runtime": "jcfb-v4-prediction-runtime@1.0.0"})},
        "status": "SYNTHETIC_TEST_ONLY" if synthetic_test_only else status,
        "warnings": list(warnings),
        "errors": list(errors),
        "payload": dict(payload),
    }
    envelope["output_hash"] = _hash_body(envelope)
    validate_engine_output(envelope)
    return envelope


__all__ = ["ENGINE_PAYLOADS", "EngineRuntimeError", "build_engine_output", "canonical_bytes", "sha256_json", "validate_engine_output"]
