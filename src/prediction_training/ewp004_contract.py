"""Fail-closed governance helpers for the B15-EWP-004 contract.

This module validates executable identities, metric semantics, and artifact
bindings.  It deliberately does not fit a model, write a parameter/model
artifact, modify a registry, or change the real-data readiness state.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "config" / "prediction_training" / "v4_batch15_ewp004_training_infrastructure_contract.json"
ENGINE_ROLES = ("OUTCOME", "HANDICAP", "GOALS", "HTFT")
MODEL_FAMILIES = ("regularized_multinomial_logistic", "gradient_boosted_decision_tree_probabilistic")
HASH_PREFIX = "sha256:"


class Ewp004ContractError(ValueError):
    """A fail-closed contract rejection with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def canonical_hash(value: Mapping[str, Any], *, exclude: str | Sequence[str] = "canonical_hash") -> str:
    excluded = {exclude} if isinstance(exclude, str) else set(exclude)
    body = {key: item for key, item in value.items() if key not in excluded}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def canonical_value_hash(value: Any) -> str:
    """Hash any canonical JSON value, including a scalar/ref payload."""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def load_contract(path: str | Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Ewp004ContractError("CONTRACT_ROOT_INVALID", "contract root must be an object")
    errors = validate_contract(value)
    if errors:
        raise Ewp004ContractError("CONTRACT_INVALID", "; ".join(errors))
    return value


def _required(mapping: Mapping[str, Any], fields: Sequence[str], code: str) -> list[str]:
    return [field for field in fields if field not in mapping or mapping[field] in (None, "")]


def _hash_is_valid(value: Any) -> bool:
    return isinstance(value, str) and len(value) == len(HASH_PREFIX) + 64 and value.startswith(HASH_PREFIX) and all(char in "0123456789abcdef" for char in value[len(HASH_PREFIX):])


def validate_contract(contract: Mapping[str, Any]) -> list[str]:
    """Return all structural/hash failures without performing any fitting."""

    failures: list[str] = []
    if contract.get("$id") != "b15-ewp004-training-infrastructure-contract@1.0.0":
        failures.append("contract identity is not the frozen EWP-004 contract")
    for field, expected in (("work_package_id", "B15-EWP-004"), ("work_package_revision", "r001"), ("contract_revision", "r001")):
        if contract.get(field) != expected:
            failures.append(f"{field} is not {expected}")
    if not isinstance(contract.get("execution_authorized"), bool):
        failures.append("execution_authorized must be boolean")
    if contract.get("execution_authorized") is not True and contract.get("implementation_executed") is not False:
        failures.append("implementation cannot be marked executed before EWP-004 authorization")
    if contract.get("execution_authorized") is True and contract.get("implementation_executed") is not True:
        failures.append("authorized EWP-004 must bind completed infrastructure implementation")
    for field in ("formal_model_fit_authorized", "model_artifacts_generated", "parameter_artifacts_generated"):
        if contract.get(field) is not False:
            failures.append(f"authorization boundary leaked through {field}")
    if contract.get("calibration_state") != "NOT_CALIBRATED":
        failures.append("calibration state is not NOT_CALIBRATED")
    if not _hash_is_valid(contract.get("canonical_hash")) or contract.get("canonical_hash") != canonical_hash(contract):
        failures.append("canonical_hash mismatch")

    registry = contract.get("candidate_model_family_registry", {})
    families = registry.get("families", [])
    actual_families = {item.get("family_id") for item in families if isinstance(item, Mapping)}
    if actual_families != set(MODEL_FAMILIES):
        failures.append("candidate family registry must contain exactly the two governed families")
    if registry.get("automatic_family_admission") is not False or registry.get("unknown_family_action") != "REJECT_UNSUPPORTED_MODEL_FAMILY":
        failures.append("candidate family admission/rejection is not fail-closed")
    registry_body = {key: value for key, value in registry.items() if key != "registry_hash"}
    if not _hash_is_valid(registry.get("registry_hash")) or registry.get("registry_hash") != canonical_hash(registry_body, exclude=()):
        failures.append("candidate family registry hash mismatch")
    for family in families:
        if not isinstance(family, Mapping):
            failures.append("candidate family entry is not an object")
            continue
        required = ("family_id", "family_version", "supported_engine_roles", "probability_output_contract", "deterministic_requirements", "runtime_library_identity", "parameter_serialization_identity", "missing_value_compatibility", "unsupported_family_rejection")
        failures.extend(f"family {family.get('family_id')}: missing {field}" for field in _required(family, required, "family"))
        if family.get("supported_engine_roles") != list(ENGINE_ROLES):
            failures.append(f"family {family.get('family_id')}: supported engine roles are incomplete")
        if family.get("runtime_library_identity", {}).get("library_defaults") != "FORBIDDEN_UNDECLARED":
            failures.append(f"family {family.get('family_id')}: library defaults are not forbidden")
        if family.get("unsupported_family_rejection", {}).get("no_dynamic_registration") is not True:
            failures.append(f"family {family.get('family_id')}: dynamic registration is not forbidden")

    profiles = contract.get("engine_training_profiles", {})
    if set(profiles) != set(ENGINE_ROLES):
        failures.append("four engine training profiles are not independently declared")
    for role in ENGINE_ROLES:
        profile = profiles.get(role, {})
        required = ("profile_identity", "profile_revision", "profile_hash", "engine_role", "target_contract_identity", "target_contract_hash", "feature_profile_identity", "feature_profile_hash", "allowed_model_families", "required_features", "optional_features", "typed_missing_state_handling", "output_class_schema", "primary_selection_metric", "evaluation_metrics", "calibration_state_expectation")
        failures.extend(f"profile {role}: missing {field}" for field in _required(profile, required, "profile"))
        if profile.get("engine_role") != role:
            failures.append(f"profile {role}: engine_role mismatch")
        if profile.get("allowed_model_families") != list(MODEL_FAMILIES):
            failures.append(f"profile {role}: allowed family set is incomplete")
        if not _hash_is_valid(profile.get("target_contract_hash")) or profile.get("target_contract_hash") != HASH_PREFIX + hashlib.sha256(str(profile.get("target_contract_identity")).encode()).hexdigest():
            failures.append(f"profile {role}: target contract hash mismatch")
        feature_body = {key: profile.get(key) for key in ("feature_profile_identity", "required_features", "optional_features")}
        if not _hash_is_valid(profile.get("feature_profile_hash")) or profile.get("feature_profile_hash") != canonical_hash(feature_body, exclude=()):
            failures.append(f"profile {role}: feature profile hash mismatch")
        profile_body = {key: value for key, value in profile.items() if key != "profile_hash"}
        if not _hash_is_valid(profile.get("profile_hash")) or profile.get("profile_hash") != canonical_hash(profile_body, exclude=()):
            failures.append(f"profile {role}: profile hash mismatch")
        classes = profile.get("output_class_schema", {}).get("classes")
        order = profile.get("output_class_schema", {}).get("order")
        if classes != order or not isinstance(classes, list) or profile.get("output_class_schema", {}).get("probability_vector_length") != len(classes or ()):
            failures.append(f"profile {role}: output class schema/order is invalid")
        if profile.get("primary_selection_metric") != "mean_out_of_time_log_loss" or profile.get("calibration_state_expectation") != "NOT_CALIBRATED":
            failures.append(f"profile {role}: selection/calibration semantics are invalid")
        if not profile.get("required_features"):
            failures.append(f"profile {role}: exact required feature list is empty")

    config_contract = contract.get("training_config_contract", {})
    configs = config_contract.get("configs", {})
    if config_contract.get("library_default_fallback") != "REJECT_TRAINING_CONFIG_NOT_DECLARED":
        failures.append("training config library-default fallback is not fail-closed")
    if set(configs) != set(ENGINE_ROLES):
        failures.append("training configs are not independently bound per engine role")
    for role in ENGINE_ROLES:
        if set(configs.get(role, {})) != set(MODEL_FAMILIES):
            failures.append(f"training config bindings incomplete for {role}")
        for family in MODEL_FAMILIES:
            cfg = configs.get(role, {}).get(family, {})
            body = {key: value for key, value in cfg.items() if key != "config_hash"}
            if not _hash_is_valid(cfg.get("config_hash")) or cfg.get("config_hash") != canonical_hash(body, exclude=()):
                failures.append(f"training config hash mismatch for {role}/{family}")
            for field in ("config_id", "config_revision", "fixed_parameters", "search_parameters", "search_method", "search_budget", "tie_break", "early_stopping", "seed_binding", "holdout_tuning"):
                if field not in cfg:
                    failures.append(f"training config {role}/{family}: missing {field}")
            if cfg.get("search_budget", 0) <= 0 or cfg.get("holdout_tuning") != "FORBIDDEN":
                failures.append(f"training config {role}/{family}: budget or holdout policy invalid")

    runtime = contract.get("deterministic_runtime_profile", {})
    runtime_body = {key: value for key, value in runtime.items() if key != "runtime_profile_hash"}
    if not _hash_is_valid(runtime.get("runtime_profile_hash")) or runtime.get("runtime_profile_hash") != canonical_hash(runtime_body, exclude=()):
        failures.append("deterministic runtime profile hash mismatch")
    for field in ("python_runtime", "algorithm_libraries", "dependency_identity", "thread_count", "deterministic_mode", "random_seed", "feature_order", "label_order", "sample_order", "float_precision", "parameter_serialization_format", "canonical_serialization_policy"):
        if field not in runtime:
            failures.append(f"deterministic runtime profile missing {field}")
    if runtime.get("thread_count") != 1 or runtime.get("deterministic_mode") is not True:
        failures.append("deterministic thread/mode boundary is not frozen")

    implementation = contract.get("fitting_implementation_identity", {})
    implementation_body = {key: value for key, value in implementation.items() if key != "implementation_hash"}
    if not _hash_is_valid(implementation.get("implementation_hash")) or implementation.get("implementation_hash") != canonical_hash(implementation_body, exclude=()):
        failures.append("fitting implementation identity hash mismatch")
    if implementation.get("status") != "IDENTITY_FROZEN_NO_RUNTIME" or implementation.get("source_code_hash") != "NOT_GENERATED_IMPLEMENTATION_NOT_AUTHORIZED":
        failures.append("fitting implementation runtime boundary leaked")

    readiness = contract.get("training_readiness_report_binding", {})
    required_bindings = ("dataset_id", "dataset_revision", "dataset_hash", "split_artifact_id", "split_revision", "split_hash", "training_readiness_report_id", "readiness_report_revision", "readiness_report_hash")
    if readiness.get("allowed_readiness_states") != ["READY"] or readiness.get("current_state") != "BLOCKED" or readiness.get("current_reason") != "TRAINING_DATA_INSUFFICIENT":
        failures.append("readiness report binding does not preserve the blocked real-data boundary")
    if readiness.get("required_fields") != list(required_bindings):
        failures.append("readiness binding field set is incomplete")

    parameter = contract.get("parameter_artifact_contract", {})
    if parameter.get("append_only") is not True or parameter.get("overwrite_policy") != "REJECT_PARAMETER_ARTIFACT_OVERWRITE":
        failures.append("parameter artifact append-only boundary is invalid")
    parameter_readiness_fields = ("dataset_id", "dataset_revision", "dataset_hash", "split_artifact_id", "split_revision", "split_hash", "readiness_report_id", "readiness_report_revision", "readiness_report_hash")
    if not set(parameter_readiness_fields).issubset(set(parameter.get("required_fields", []))):
        failures.append("parameter artifact does not carry readiness bindings")

    evaluation = contract.get("evaluation_metric_contract", {})
    if evaluation.get("log_loss", {}).get("epsilon") != 1e-15 or evaluation.get("brier_score", {}).get("formula") != "B = (1/N) * sum_i sum_k (p_i,k - 1[y_i=k])^2":
        failures.append("metric formula/epsilon semantics are not frozen")
    if evaluation.get("classwise_recall", {}).get("zero_support_behavior") != "NULL_AND_EXCLUDED_FROM_MACRO":
        failures.append("zero-support recall behavior is not frozen")
    if evaluation.get("probability_normalization", {}).get("sum_tolerance") != 0.000001:
        failures.append("probability normalization tolerance is not 1e-6")
    if evaluation.get("full_precision_policy", "").find("full precision") < 0 or evaluation.get("persistence", {}).get("display_rounding") != "separate_non_hashing_representation":
        failures.append("metric precision/display persistence boundary is invalid")

    packaging = contract.get("model_artifact_packaging_contract", {})
    if packaging.get("missing_binding_action") != "BLOCKED_MODEL_ARTIFACT_PACKAGING_BINDING_INCOMPLETE" or packaging.get("append_only") is not True:
        failures.append("model artifact packaging fail-closed/append-only policy is invalid")
    for field in ("parameter_artifact_id", "parameter_artifact_hash", "training_readiness_report_id", "training_readiness_report_hash", "split_artifact_id", "split_artifact_hash", "dataset_id", "dataset_revision", "dataset_hash", "engine_training_profile_id", "engine_training_profile_hash", "model_family_id", "model_family_version", "model_family_registry_hash", "training_config_id", "training_config_hash", "deterministic_runtime_profile_id", "deterministic_runtime_profile_hash", "fitting_implementation_id", "fitting_implementation_hash"):
        if field not in packaging.get("required_bindings", []):
            failures.append(f"packaging required binding missing {field}")
    if contract.get("promotion_boundary", {}).get("human_gate_required") is not True or contract.get("promotion_boundary", {}).get("automatic_promotion") is not False:
        failures.append("promotion boundary is not explicit human-gated")
    bound_configs = contract.get("model_selection_protocol", {}).get("bound_config_bindings", {})
    for role in ENGINE_ROLES:
        for family in MODEL_FAMILIES:
            expected = configs.get(role, {}).get(family, {})
            bound = bound_configs.get(role, {}).get(family, {})
            if bound.get("config_id") != expected.get("config_id") or bound.get("config_hash") != expected.get("config_hash"):
                failures.append(f"selection config binding mismatch for {role}/{family}")
    return failures


def validate_model_family(contract: Mapping[str, Any], family_id: str, engine_role: str) -> Mapping[str, Any]:
    if engine_role not in ENGINE_ROLES:
        raise Ewp004ContractError("UNSUPPORTED_ENGINE_ROLE", engine_role)
    family = next((item for item in contract["candidate_model_family_registry"]["families"] if item.get("family_id") == family_id), None)
    if family is None or engine_role not in family.get("supported_engine_roles", ()):
        raise Ewp004ContractError("UNSUPPORTED_MODEL_FAMILY", f"{family_id}/{engine_role}")
    return family


def validate_training_config(contract: Mapping[str, Any], engine_role: str, family_id: str) -> Mapping[str, Any]:
    validate_model_family(contract, family_id, engine_role)
    config = contract.get("training_config_contract", {}).get("configs", {}).get(engine_role, {}).get(family_id)
    if config is None:
        raise Ewp004ContractError("TRAINING_CONFIG_NOT_DECLARED", f"{engine_role}/{family_id}")
    expected = canonical_hash({key: value for key, value in config.items() if key != "config_hash"}, exclude=())
    if config.get("config_hash") != expected:
        raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}")
    if config.get("holdout_tuning") != "FORBIDDEN" or not config.get("fixed_parameters") or not config.get("search_parameters"):
        raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}")
    if config.get("search_method") != "GRID_EXHAUSTIVE" or not isinstance(config.get("search_budget"), int) or config["search_budget"] <= 0:
        raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}")
    if any(value == "LIBRARY_DEFAULT" for value in config.get("fixed_parameters", {}).values()):
        raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}")
    combinations = 1
    for name, spec in config.get("search_parameters", {}).items():
        if not isinstance(spec, Mapping) or not isinstance(spec.get("values"), list) or not spec["values"]:
            raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}")
        if spec.get("type") not in {"float", "integer", "categorical"}:
            raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}")
        if spec["type"] == "float" and any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in spec["values"]):
            raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}")
        if spec["type"] == "integer" and any(not isinstance(value, int) or isinstance(value, bool) for value in spec["values"]):
            raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}")
        if "range" in spec:
            bounds = spec["range"]
            if not isinstance(bounds, list) or len(bounds) != 2 or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in bounds) or any(value < bounds[0] or value > bounds[1] for value in spec["values"]):
                raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}/range")
        if "choices" in spec:
            choices = spec["choices"]
            if not isinstance(choices, list) or not all(value in choices for value in spec["values"]):
                raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/{name}/choices")
        combinations *= len(spec["values"])
    if combinations != config.get("search_budget"):
        raise Ewp004ContractError("INVALID_TRAINING_CONFIG", f"{engine_role}/{family_id}/search_budget")
    return config


def validate_feature_payload(profile: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    for feature in profile.get("required_features", ()):
        feature_id = feature["feature_id"]
        if feature_id not in payload or not isinstance(payload[feature_id], (int, float)) or isinstance(payload[feature_id], bool) or not math.isfinite(float(payload[feature_id])):
            raise Ewp004ContractError("REQUIRED_FEATURE_MISSING", feature_id)
    optional = {item["feature_id"]: item for item in profile.get("optional_features", ())}
    for feature_id, value in payload.items():
        if feature_id in optional and isinstance(value, Mapping):
            if value.get("state") not in optional[feature_id].get("allowed_missing_states", ()):
                raise Ewp004ContractError("INVALID_TYPED_MISSING_STATE", feature_id)
        elif feature_id not in {item["feature_id"] for item in profile.get("required_features", ())} and feature_id not in optional:
            raise Ewp004ContractError("UNDECLARED_FEATURE", feature_id)


def validate_readiness_binding(binding: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    spec = contract["training_readiness_report_binding"]
    normalized = dict(binding)
    if "training_readiness_report_id" not in normalized and "readiness_report_id" in normalized:
        normalized["training_readiness_report_id"] = normalized["readiness_report_id"]
    missing = _required(normalized, spec["required_fields"], "readiness")
    if missing:
        raise Ewp004ContractError("READINESS_BINDING_INCOMPLETE", ",".join(missing))
    if normalized.get("readiness_state") not in spec["allowed_readiness_states"]:
        raise Ewp004ContractError(spec["formal_fit_action_when_not_allowed"], str(normalized.get("readiness_state")))
    if any(not _hash_is_valid(normalized.get(field)) for field in ("dataset_hash", "split_hash", "readiness_report_hash")):
        raise Ewp004ContractError("READINESS_BINDING_HASH_INVALID", "dataset/split/report hash")


def validate_probability_vector(probabilities: Sequence[float], expected_length: int, tolerance: float = 1e-6) -> tuple[float, ...]:
    if len(probabilities) != expected_length:
        raise Ewp004ContractError("INVALID_PROBABILITY_VECTOR", "class count does not match profile")
    values = tuple(float(value) for value in probabilities)
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        raise Ewp004ContractError("INVALID_PROBABILITY_VECTOR", "probability outside [0,1] or non-finite")
    if abs(sum(values) - 1.0) > tolerance:
        raise Ewp004ContractError("PROBABILITY_NOT_NORMALIZED", "sum is outside 1 +/- 1e-6")
    return values


def _probability_rows(probabilities: Sequence[Sequence[float]], class_order: Sequence[str]) -> tuple[tuple[float, ...], ...]:
    return tuple(validate_probability_vector(row, len(class_order)) for row in probabilities)


def multiclass_log_loss(observed: Sequence[str], probabilities: Sequence[Sequence[float]], class_order: Sequence[str], epsilon: float = 1e-15) -> float:
    if len(observed) != len(probabilities) or not observed:
        raise Ewp004ContractError("METRIC_INPUT_INVALID", "observed/probability rows must be non-empty and aligned")
    rows = _probability_rows(probabilities, class_order)
    index = {label: position for position, label in enumerate(class_order)}
    try:
        return -sum(math.log(max(row[index[label]], epsilon)) for row, label in zip(rows, observed)) / len(rows)
    except KeyError as exc:
        raise Ewp004ContractError("METRIC_LABEL_INVALID", str(exc)) from exc


def multiclass_brier_score(observed: Sequence[str], probabilities: Sequence[Sequence[float]], class_order: Sequence[str]) -> float:
    if len(observed) != len(probabilities) or not observed:
        raise Ewp004ContractError("METRIC_INPUT_INVALID", "observed/probability rows must be non-empty and aligned")
    rows = _probability_rows(probabilities, class_order)
    index = {label: position for position, label in enumerate(class_order)}
    if any(label not in index for label in observed):
        raise Ewp004ContractError("METRIC_LABEL_INVALID", "observed label is outside class order")
    return sum(sum((value - (1.0 if position == index[label] else 0.0)) ** 2 for position, value in enumerate(row)) for label, row in zip(observed, rows)) / len(rows)


def class_support(observed: Sequence[str], class_order: Sequence[str]) -> dict[str, int]:
    if any(label not in class_order for label in observed):
        raise Ewp004ContractError("METRIC_LABEL_INVALID", "observed label is outside class order")
    return {label: sum(1 for value in observed if value == label) for label in class_order}


def classwise_recall(observed: Sequence[str], predicted: Sequence[str], class_order: Sequence[str]) -> dict[str, Any]:
    if len(observed) != len(predicted) or not observed:
        raise Ewp004ContractError("METRIC_INPUT_INVALID", "observed/predicted rows must be non-empty and aligned")
    support = class_support(observed, class_order)
    if any(label not in class_order for label in predicted):
        raise Ewp004ContractError("METRIC_LABEL_INVALID", "predicted label is outside class order")
    recalls: dict[str, float | None] = {}
    for label in class_order:
        true_positive = sum(1 for actual, prediction in zip(observed, predicted) if actual == label and prediction == label)
        false_negative = sum(1 for actual, prediction in zip(observed, predicted) if actual == label and prediction != label)
        recalls[label] = None if true_positive + false_negative == 0 else true_positive / (true_positive + false_negative)
    defined = [value for value in recalls.values() if value is not None]
    return {"by_class": recalls, "support": support, "macro": (sum(defined) / len(defined) if defined else None), "zero_support_behavior": "NULL_AND_EXCLUDED_FROM_MACRO"}


def validate_parameter_artifact(artifact: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    spec = contract["parameter_artifact_contract"]
    missing = [field for field in spec["required_fields"] if field not in artifact or (artifact[field] in ("",) or (artifact[field] is None and field != "supersedes"))]
    if missing:
        raise Ewp004ContractError("PARAMETER_ARTIFACT_BINDING_INCOMPLETE", ",".join(missing))
    if artifact.get("engine_role") not in ENGINE_ROLES:
        raise Ewp004ContractError("UNSUPPORTED_ENGINE_ROLE", str(artifact.get("engine_role")))
    validate_model_family(contract, artifact["model_family_id"], artifact["engine_role"])
    family = next(item for item in contract["candidate_model_family_registry"]["families"] if item.get("family_id") == artifact["model_family_id"])
    if artifact.get("model_family_version") != family.get("family_version"):
        raise Ewp004ContractError("PARAMETER_ARTIFACT_FAMILY_VERSION_INVALID", str(artifact.get("model_family_version")))
    if any(not _hash_is_valid(artifact.get(field)) for field in ("dataset_hash", "split_hash", "readiness_report_hash", "training_config_hash", "fitting_implementation_hash", "deterministic_runtime_profile_hash", "parameter_hash")):
        raise Ewp004ContractError("PARAMETER_ARTIFACT_HASH_INVALID", "required artifact hash is invalid")
    if artifact.get("supersedes") is not None and not isinstance(artifact.get("supersedes"), str):
        raise Ewp004ContractError("PARAMETER_ARTIFACT_SUPERSESSION_INVALID", "supersedes must be an artifact id or null")
    payload = artifact.get("parameter_payload_or_ref")
    if not isinstance(payload, (Mapping, str)):
        raise Ewp004ContractError("PARAMETER_ARTIFACT_PAYLOAD_INVALID", "payload_or_ref must be one canonical payload or reference")
    if artifact.get("serialization_identity") not in {
        contract.get("canonicalization", {}).get("profile"),
        "canonical-json@v4-1.0",
    }:
        raise Ewp004ContractError("PARAMETER_ARTIFACT_SERIALIZATION_INVALID", str(artifact.get("serialization_identity")))
    if artifact.get("parameter_hash") != canonical_value_hash(payload):
        raise Ewp004ContractError("PARAMETER_ARTIFACT_HASH_MISMATCH", str(artifact.get("parameter_artifact_id")))


def append_parameter_artifact(existing: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Validate an append-only candidate list in memory; never persists it."""

    validate_parameter_artifact(artifact, contract)
    same_id = [item for item in existing if item.get("parameter_artifact_id") == artifact.get("parameter_artifact_id")]
    if same_id:
        latest = max(int(item.get("revision", 0)) for item in same_id)
        if int(artifact["revision"]) <= latest or artifact.get("supersedes") != artifact.get("parameter_artifact_id"):
            raise Ewp004ContractError("REJECT_PARAMETER_ARTIFACT_OVERWRITE", str(artifact.get("parameter_artifact_id")))
    return tuple(existing) + (artifact,)


def validate_model_artifact_package(package: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    spec = contract["model_artifact_packaging_contract"]
    missing = _required(package, spec["required_bindings"], "packaging")
    if missing:
        raise Ewp004ContractError("BLOCKED_MODEL_ARTIFACT_PACKAGING_BINDING_INCOMPLETE", ",".join(missing))
    for field in ("parameter_artifact_hash", "training_readiness_report_hash", "split_artifact_hash", "dataset_hash", "engine_training_profile_hash", "model_family_registry_hash", "training_config_hash", "deterministic_runtime_profile_hash", "fitting_implementation_hash"):
        if not _hash_is_valid(package.get(field)):
            raise Ewp004ContractError("BLOCKED_MODEL_ARTIFACT_PACKAGING_BINDING_INCOMPLETE", field)


__all__ = [
    "ENGINE_ROLES", "MODEL_FAMILIES", "Ewp004ContractError", "append_parameter_artifact",
    "canonical_hash", "canonical_value_hash", "class_support", "classwise_recall", "load_contract",
    "multiclass_brier_score", "multiclass_log_loss", "validate_contract",
    "validate_feature_payload", "validate_model_artifact_package", "validate_model_family",
    "validate_parameter_artifact", "validate_probability_vector", "validate_readiness_binding",
    "validate_training_config",
]
