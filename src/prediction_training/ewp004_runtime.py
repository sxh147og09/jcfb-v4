"""Authorized B15-EWP-004 training infrastructure runtime.

This module implements the executable boundaries around model fitting.  It
does not perform formal fitting, persist parameter/model artifacts, mutate the
model registry, calibrate probabilities, or promote a model.  Formal fitting
is an EWP-005 operation and is rejected before an estimator can be invoked.
Synthetic helpers return ephemeral, in-memory integration payloads only.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ewp004_contract import (
    ENGINE_ROLES,
    MODEL_FAMILIES,
    Ewp004ContractError,
    append_parameter_artifact,
    canonical_hash,
    class_support,
    classwise_recall,
    load_contract,
    multiclass_brier_score,
    multiclass_log_loss,
    validate_contract,
    validate_feature_payload,
    validate_model_artifact_package,
    validate_model_family,
    validate_parameter_artifact,
    validate_probability_vector,
    validate_training_config,
)


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIRNAME = "config/prediction_training"
REGISTRY_FILENAME = "v4_batch15_execution_work_package_registry.json"
EXECUTION_MANIFEST_FILENAME = "v4_batch15_ewp004_execution_manifest.json"
READINESS_FILENAME = "v4_batch15_ewp003_readiness_report.json"
DATASET_MANIFEST = Path(
    "approved_data/training_datasets/manifests/"
    "dataset-13c4b050dc50e2de3ec8a961a9c9b029-r001.json"
)
HASH_PREFIX = "sha256:"
PROMOTION_STATES = ("CANDIDATE", "VALIDATED", "APPROVED_FOR_ENGINE", "REJECTED")


class Ewp004RuntimeError(ValueError):
    """A fail-closed runtime rejection with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    """Return the frozen UTF-8 canonical JSON representation of *value*."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_value(value: Any) -> str:
    return HASH_PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _hash_without(document: Mapping[str, Any], *fields: str) -> str:
    return sha256_value({key: value for key, value in document.items() if key not in set(fields)})


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == len(HASH_PREFIX) + 64 and value.startswith(HASH_PREFIX) and all(char in "0123456789abcdef" for char in value[len(HASH_PREFIX):])


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Ewp004RuntimeError("CONFIG_LOAD_FAILED", str(path)) from exc
    if not isinstance(value, dict):
        raise Ewp004RuntimeError("CONFIG_ROOT_INVALID", str(path))
    return value


def _verify_hash(document: Mapping[str, Any], field: str) -> None:
    actual = document.get(field)
    if not _is_hash(actual) or actual != _hash_without(document, field):
        raise Ewp004RuntimeError("HASH_INVALID", field)


@dataclass(frozen=True)
class FormalFitGateResult:
    formal_fit_allowed: bool
    reasons: tuple[str, ...]
    binding_complete: bool
    artifact_generation_allowed: bool = False
    model_registry_write_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "formal_fit_allowed": self.formal_fit_allowed,
            "reasons": list(self.reasons),
            "binding_complete": self.binding_complete,
            "artifact_generation_allowed": self.artifact_generation_allowed,
            "model_registry_write_allowed": self.model_registry_write_allowed,
        }


@dataclass(frozen=True)
class CandidateExecutionPlan:
    engine_role: str
    family_id: str
    family_version: str
    config_id: str
    config_hash: str
    profile_id: str
    profile_hash: str
    probability_contract: Mapping[str, Any]


class CandidateFittingAdapter:
    """Dispatch boundary; no estimator or formal fitting runtime is exposed."""

    def __init__(self, runtime: "Ewp004Runtime"):
        self.runtime = runtime

    def plan(self, engine_role: str, family_id: str) -> CandidateExecutionPlan:
        return self.runtime.dispatch_candidate_family(engine_role, family_id)

    def fit(self, engine_role: str, family_id: str, *, formal_request: Mapping[str, Any] | None = None, synthetic: bool = False, rows: Sequence[Mapping[str, Any]] = ()) -> Mapping[str, Any]:
        if not synthetic:
            return self.runtime.request_formal_fit(formal_request or {})
        if not rows:
            raise Ewp004RuntimeError("SYNTHETIC_FIXTURE_EMPTY", "synthetic adapter execution requires test-local rows")
        plan = self.plan(engine_role, family_id)
        profile = self.runtime.load_training_profile(engine_role)
        return {
            "fixture_label": "SYNTHETIC_CONTRACT_FIXTURE_ONLY",
            "ephemeral": True,
            "fit_executed": False,
            "candidate_adapter_boundary": "DISPATCH_VALIDATED_NO_ESTIMATOR",
            "engine_role": engine_role,
            "family_id": family_id,
            "family_version": plan.family_version,
            "config_id": plan.config_id,
            "config_hash": plan.config_hash,
            "feature_order": [feature["feature_id"] for feature in profile["required_features"]] + [feature["feature_id"] for feature in profile["optional_features"]],
            "label_order": list(profile["output_class_schema"]["order"]),
            "sample_count": len(rows),
        }


class Ewp004Runtime:
    """EWP-004 runtime facade with explicit F-drive and authorization checks."""

    def __init__(self, project_root: str | Path = DEFAULT_PROJECT_ROOT, *, config_root: str | Path | None = None, allow_test_root: bool = False):
        self.project_root = Path(project_root).resolve()
        if not allow_test_root and self.project_root.drive.upper() != "F:":
            raise Ewp004RuntimeError("F_DRIVE_REQUIRED", "formal EWP-004 runtime must remain on F:")
        self.config_root = Path(config_root).resolve() if config_root else self.project_root / CONFIG_DIRNAME
        self.contract = load_contract(self.config_root / "v4_batch15_ewp004_training_infrastructure_contract.json")
        contract_failures = validate_contract(self.contract)
        if contract_failures:
            raise Ewp004RuntimeError("CONTRACT_INVALID", "; ".join(contract_failures))
        _verify_hash(self.contract, "canonical_hash")
        self.execution_manifest = _load_json(self.config_root / EXECUTION_MANIFEST_FILENAME)
        self.registry = _load_json(self.config_root / REGISTRY_FILENAME)
        self._validate_execution_boundary()
        self.adapter = CandidateFittingAdapter(self)

    def _validate_execution_boundary(self) -> None:
        manifest = self.execution_manifest
        _verify_hash(manifest, "canonical_hash")
        if manifest.get("work_package_id") != "B15-EWP-004" or manifest.get("execution_authorized") is not True:
            raise Ewp004RuntimeError("EWP004_NOT_AUTHORIZED", "EWP-004 requires explicit runtime authorization")
        if manifest.get("implementation_executed") is not True:
            raise Ewp004RuntimeError("EWP004_IMPLEMENTATION_NOT_COMPLETE", "execution manifest is not bound to the implementation")
        if manifest.get("formal_model_fit_authorized") is not False:
            raise Ewp004RuntimeError("EWP005_AUTHORIZATION_LEAK", "formal fitting must remain unauthorized")
        if manifest.get("contract_hash") != self.contract.get("canonical_hash"):
            raise Ewp004RuntimeError("CONTRACT_HASH_MISMATCH", "manifest is not bound to the active EWP-004 contract")
        ewp004 = next((item for item in self.registry.get("work_packages", ()) if item.get("work_package_id") == "B15-EWP-004"), {})
        ewp005 = next((item for item in self.registry.get("work_packages", ()) if item.get("work_package_id") == "B15-EWP-005"), {})
        if ewp004.get("execution_authorized") is not True or ewp005.get("execution_authorized") is not False:
            raise Ewp004RuntimeError("EWP005_AUTHORIZATION_LEAK", "registry authorization boundary is invalid")

    def load_training_profile(self, engine_role: str) -> Mapping[str, Any]:
        if engine_role not in ENGINE_ROLES:
            raise Ewp004RuntimeError("UNSUPPORTED_ENGINE_ROLE", engine_role)
        profile = self.contract["engine_training_profiles"].get(engine_role)
        if not isinstance(profile, Mapping) or profile.get("engine_role") != engine_role:
            raise Ewp004RuntimeError("ENGINE_PROFILE_NOT_DECLARED", engine_role)
        if profile.get("profile_hash") != canonical_hash({key: value for key, value in profile.items() if key != "profile_hash"}, exclude=()):
            raise Ewp004RuntimeError("ENGINE_PROFILE_HASH_INVALID", engine_role)
        return profile

    def load_training_config(self, engine_role: str, family_id: str) -> Mapping[str, Any]:
        try:
            config = validate_training_config(self.contract, engine_role, family_id)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc
        return config

    def dispatch_candidate_family(self, engine_role: str, family_id: str) -> CandidateExecutionPlan:
        profile = self.load_training_profile(engine_role)
        try:
            family = validate_model_family(self.contract, family_id, engine_role)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc
        if family_id not in profile.get("allowed_model_families", ()):
            raise Ewp004RuntimeError("UNSUPPORTED_MODEL_FAMILY", f"{family_id}/{engine_role}")
        config = self.load_training_config(engine_role, family_id)
        probability = family.get("probability_output_contract", {})
        if probability.get("kind") != "multiclass_probability_distribution" or probability.get("normalization") != "sum(p) = 1 +/- 1e-6":
            raise Ewp004RuntimeError("PROBABILITY_CONTRACT_INVALID", family_id)
        deterministic = family.get("deterministic_requirements", {})
        if not all(deterministic.get(field) is True for field in ("requires_seed", "requires_fixed_feature_order", "requires_fixed_label_order", "requires_single_declared_thread_count")):
            raise Ewp004RuntimeError("DETERMINISTIC_REQUIREMENTS_INVALID", family_id)
        library = family.get("runtime_library_identity", {})
        if library.get("library_defaults") != "FORBIDDEN_UNDECLARED" or not library.get("library_version"):
            raise Ewp004RuntimeError("RUNTIME_LIBRARY_IDENTITY_INVALID", family_id)
        if family.get("missing_value_compatibility", {}).get("silent_imputation") != "FORBIDDEN":
            raise Ewp004RuntimeError("MISSING_VALUE_POLICY_INVALID", family_id)
        serialization = family.get("parameter_serialization_identity", {})
        if serialization.get("hash_algorithm") != "SHA-256" or serialization.get("format") != "canonical-json":
            raise Ewp004RuntimeError("PARAMETER_SERIALIZATION_IDENTITY_INVALID", family_id)
        return CandidateExecutionPlan(
            engine_role=engine_role,
            family_id=family_id,
            family_version=str(family["family_version"]),
            config_id=str(config["config_id"]),
            config_hash=str(config["config_hash"]),
            profile_id=str(profile["profile_identity"]),
            profile_hash=str(profile["profile_hash"]),
            probability_contract=probability,
        )

    def validate_feature_payload(self, engine_role: str, payload: Mapping[str, Any]) -> None:
        try:
            validate_feature_payload(self.load_training_profile(engine_role), payload)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc

    def consume_training_config(self, engine_role: str, family_id: str, *, seed: int | None = None) -> dict[str, Any]:
        config = dict(self.load_training_config(engine_role, family_id))
        runtime_seed = self.contract["deterministic_runtime_profile"]["random_seed"] if seed is None else seed
        if not isinstance(runtime_seed, int) or isinstance(runtime_seed, bool):
            raise Ewp004RuntimeError("INVALID_RANDOM_SEED", str(runtime_seed))
        fixed = dict(config["fixed_parameters"])
        if fixed.get("random_state") == "BOUND_SEED":
            fixed["random_state"] = runtime_seed
        return {"config_id": config["config_id"], "config_hash": config["config_hash"], "fixed_parameters": fixed, "search_parameters": config["search_parameters"], "search_method": config["search_method"], "search_budget": config["search_budget"], "tie_break": config["tie_break"], "holdout_tuning": config["holdout_tuning"], "seed": runtime_seed}

    def build_deterministic_context(self, engine_role: str, family_id: str, binding: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.dispatch_candidate_family(engine_role, family_id)
        runtime = self.contract["deterministic_runtime_profile"]
        implementation = self.contract["fitting_implementation_identity"]
        required_binding = ("dataset_id", "dataset_revision", "dataset_hash", "split_artifact_id", "split_revision", "split_hash", "readiness_report_id", "readiness_report_revision", "readiness_report_hash")
        if "readiness_report_id" not in binding and "training_readiness_report_id" in binding:
            binding = {**binding, "readiness_report_id": binding["training_readiness_report_id"]}
        missing = [field for field in required_binding if field not in binding or binding[field] in (None, "")]
        if missing:
            raise Ewp004RuntimeError("DETERMINISTIC_CONTEXT_BINDING_INCOMPLETE", ",".join(missing))
        profile = self.load_training_profile(engine_role)
        context = {
            "identity": runtime["identity"],
            "revision": runtime["revision"],
            "python_runtime": runtime["python_runtime"],
            "algorithm_libraries": runtime["algorithm_libraries"],
            "dependency_identity": runtime["dependency_identity"],
            "thread_count": runtime["thread_count"],
            "deterministic_mode": runtime["deterministic_mode"],
            "random_seed": runtime["random_seed"],
            "feature_order": [feature["feature_id"] for feature in profile["required_features"]] + [feature["feature_id"] for feature in profile["optional_features"]],
            "label_order": list(profile["output_class_schema"]["order"]),
            "sample_order": runtime["sample_order"],
            "float_precision": runtime["float_precision"],
            "parameter_serialization_format": runtime["parameter_serialization_format"],
            "canonical_serialization_policy": runtime["canonical_serialization_policy"],
            "engine_role": engine_role,
            "model_family_id": family_id,
            "model_family_version": plan.family_version,
            "engine_training_profile_hash": plan.profile_hash,
            "training_config_hash": plan.config_hash,
            "fitting_implementation_hash": implementation["implementation_hash"],
            "lineage": {field: binding[field] for field in required_binding},
        }
        context["context_hash"] = _hash_without(context)
        return context

    def validate_formal_fit_gate(self, binding: Mapping[str, Any], *, ewp005_authorized: bool = False) -> FormalFitGateResult:
        spec = self.contract["training_readiness_report_binding"]
        binding = dict(binding)
        if "training_readiness_report_id" not in binding and "readiness_report_id" in binding:
            binding["training_readiness_report_id"] = binding["readiness_report_id"]
        if "readiness_report_id" not in binding and "training_readiness_report_id" in binding:
            binding["readiness_report_id"] = binding["training_readiness_report_id"]
        reasons: list[str] = []
        required = tuple(spec["required_fields"])
        missing = [field for field in required if field not in binding or binding[field] in (None, "")]
        if missing:
            reasons.append("READINESS_BINDING_INCOMPLETE")
        if binding.get("split_artifact_id") in (None, "", "NONE"):
            reasons.append("FORMAL_SPLIT_NOT_AVAILABLE")
        for field in ("dataset_hash", "split_hash", "readiness_report_hash"):
            if field in binding and binding.get(field) not in (None, "") and not _is_hash(binding.get(field)):
                reasons.append("READINESS_BINDING_HASH_INVALID")
        state = binding.get("readiness_state")
        if state not in spec["allowed_readiness_states"]:
            reason_codes = binding.get("reason_codes") or [spec.get("current_reason", "READINESS_NOT_APPROVED_FOR_FITTING")]
            for reason in reason_codes:
                if reason not in reasons:
                    reasons.append(str(reason))
            if "READINESS_NOT_APPROVED_FOR_FITTING" not in reasons:
                reasons.append("READINESS_NOT_APPROVED_FOR_FITTING")
        if int(binding.get("usable_samples", 0) or 0) <= 0 and "TRAINING_DATA_INSUFFICIENT" not in reasons:
            reasons.append("TRAINING_DATA_INSUFFICIENT")
        if not ewp005_authorized:
            reasons.append("EWP005_NOT_AUTHORIZED")
        deduped = tuple(dict.fromkeys(reasons))
        return FormalFitGateResult(not deduped, deduped, not missing)

    def request_formal_fit(self, binding: Mapping[str, Any], *, ewp005_authorized: bool = False) -> Mapping[str, Any]:
        result = self.validate_formal_fit_gate(binding, ewp005_authorized=ewp005_authorized)
        if not result.formal_fit_allowed:
            raise Ewp004RuntimeError("FORMAL_FIT_BLOCKED", ",".join(result.reasons))
        raise Ewp004RuntimeError("EWP004_FIT_OUT_OF_SCOPE", "formal fitting belongs to separately authorized EWP-005")

    def current_real_prefit_validation(self) -> dict[str, Any]:
        readiness = _load_json(self.config_root / READINESS_FILENAME)
        manifest_path = self.project_root / DATASET_MANIFEST
        dataset = _load_json(manifest_path)
        binding = {
            "dataset_id": dataset.get("dataset_id"),
            "dataset_revision": f"r{int(dataset.get('revision', 0)):03d}",
            "dataset_hash": dataset.get("dataset_substantive_hash"),
            "split_artifact_id": readiness.get("formal_split_artifact_ref"),
            "split_revision": None,
            "split_hash": None,
            "readiness_report_id": readiness.get("report_identity"),
            "training_readiness_report_id": readiness.get("report_identity"),
            "readiness_report_revision": readiness.get("report_revision"),
            "readiness_report_hash": readiness.get("canonical_hash"),
            "readiness_state": readiness.get("readiness_state"),
            "reason_codes": readiness.get("reason_codes", []),
            "usable_samples": readiness.get("sample_counts", {}).get("usable_samples", 0),
        }
        return {"binding": binding, "gate": self.validate_formal_fit_gate(binding), "parameter_artifacts_generated": False, "model_artifacts_generated": False, "model_registry_inserted": False, "calibration_state": "NOT_CALIBRATED"}

    def evaluate_metrics(self, observed: Sequence[str], probabilities: Sequence[Sequence[float]], class_order: Sequence[str], predicted: Sequence[str] | None = None) -> dict[str, Any]:
        try:
            rows = [validate_probability_vector(row, len(class_order)) for row in probabilities]
            log_loss = multiclass_log_loss(observed, rows, class_order)
            brier = multiclass_brier_score(observed, rows, class_order)
            predictions = list(predicted) if predicted is not None else [class_order[max(range(len(row)), key=row.__getitem__)] for row in rows]
            recall = classwise_recall(observed, predictions, class_order)
            support = class_support(observed, class_order)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc
        body = {"metric_contract_identity": self.contract["evaluation_metric_contract"]["identity"], "metric_contract_revision": self.contract["evaluation_metric_contract"]["revision"], "class_order": list(class_order), "log_loss": log_loss, "brier_score": brier, "classwise_recall": recall, "class_support": support, "probability_normalization_validity": True, "calibration_state": "NOT_CALIBRATED"}
        return {**body, "metric_hash": _hash_without(body)}

    def serialize_parameter_payload(self, payload: Mapping[str, Any] | str) -> dict[str, Any]:
        if not isinstance(payload, (Mapping, str)):
            raise Ewp004RuntimeError("PARAMETER_PAYLOAD_INVALID", "payload must be a mapping or reference")
        serialized = canonical_bytes(payload)
        return {"serialization_identity": "canonical-json@v4-1.0", "serialized_payload": serialized.decode("utf-8"), "parameter_hash": HASH_PREFIX + hashlib.sha256(serialized).hexdigest()}

    def build_ephemeral_parameter_artifact(self, engine_role: str, family_id: str, binding: Mapping[str, Any], payload: Mapping[str, Any] | str, *, revision: int = 1, supersedes: str | None = None) -> dict[str, Any]:
        plan = self.dispatch_candidate_family(engine_role, family_id)
        required = ("dataset_id", "dataset_revision", "dataset_hash", "split_artifact_id", "split_revision", "split_hash", "readiness_report_id", "readiness_report_revision", "readiness_report_hash")
        missing = [field for field in required if binding.get(field) in (None, "")]
        if missing:
            raise Ewp004RuntimeError("PARAMETER_ARTIFACT_BINDING_INCOMPLETE", ",".join(missing))
        serialized = self.serialize_parameter_payload(payload)
        report_id = binding.get("readiness_report_id", binding.get("training_readiness_report_id"))
        if report_id in (None, ""):
            raise Ewp004RuntimeError("PARAMETER_ARTIFACT_BINDING_INCOMPLETE", "readiness_report_id")
        artifact = {
            "parameter_artifact_id": f"synthetic-{engine_role.lower()}-{family_id}",
            "engine_role": engine_role,
            "model_family_id": family_id,
            "model_family_version": plan.family_version,
            "dataset_id": binding["dataset_id"], "dataset_revision": binding["dataset_revision"], "dataset_hash": binding["dataset_hash"],
            "split_artifact_id": binding["split_artifact_id"], "split_revision": binding["split_revision"], "split_hash": binding["split_hash"],
            "readiness_report_id": report_id, "readiness_report_revision": binding["readiness_report_revision"], "readiness_report_hash": binding["readiness_report_hash"],
            "training_config_id": plan.config_id, "training_config_revision": "r001", "training_config_hash": plan.config_hash,
            "fitting_implementation_id": self.contract["fitting_implementation_identity"]["implementation_id"], "fitting_implementation_version": self.contract["fitting_implementation_identity"]["implementation_version"], "fitting_implementation_hash": self.contract["fitting_implementation_identity"]["implementation_hash"],
            "deterministic_runtime_profile_id": self.contract["deterministic_runtime_profile"]["identity"], "deterministic_runtime_profile_revision": self.contract["deterministic_runtime_profile"]["revision"], "deterministic_runtime_profile_hash": self.contract["deterministic_runtime_profile"]["runtime_profile_hash"],
            "random_seed": self.contract["deterministic_runtime_profile"]["random_seed"], "parameter_payload_or_ref": payload, "parameter_hash": serialized["parameter_hash"], "serialization_identity": serialized["serialization_identity"], "created_at": "synthetic-test-only", "revision": revision, "supersedes": supersedes, "ephemeral": True, "fixture_label": "SYNTHETIC_CONTRACT_FIXTURE_ONLY",
        }
        try:
            validate_parameter_artifact(artifact, self.contract)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc
        return artifact

    def append_ephemeral_parameter_artifact(self, existing: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        if artifact.get("ephemeral") is not True:
            raise Ewp004RuntimeError("FORMAL_ARTIFACT_PERSISTENCE_FORBIDDEN", "only synthetic ephemeral artifacts can be handled here")
        try:
            return append_parameter_artifact(existing, artifact, self.contract)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc

    def build_ephemeral_model_package(self, parameter_artifact: Mapping[str, Any], *, extra_bindings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if parameter_artifact.get("ephemeral") is not True:
            raise Ewp004RuntimeError("FORMAL_ARTIFACT_PERSISTENCE_FORBIDDEN", "formal parameter artifacts cannot be packaged by EWP-004")
        validate_parameter_artifact(parameter_artifact, self.contract)
        package = {
            "parameter_artifact_id": parameter_artifact["parameter_artifact_id"], "parameter_artifact_hash": parameter_artifact["parameter_hash"],
            "training_readiness_report_id": parameter_artifact["readiness_report_id"], "training_readiness_report_hash": parameter_artifact["readiness_report_hash"],
            "split_artifact_id": parameter_artifact["split_artifact_id"], "split_artifact_hash": parameter_artifact["split_hash"],
            "dataset_id": parameter_artifact["dataset_id"], "dataset_revision": parameter_artifact["dataset_revision"], "dataset_hash": parameter_artifact["dataset_hash"],
            "engine_training_profile_id": self.load_training_profile(parameter_artifact["engine_role"])["profile_identity"], "engine_training_profile_hash": self.load_training_profile(parameter_artifact["engine_role"])["profile_hash"],
            "model_family_id": parameter_artifact["model_family_id"], "model_family_version": parameter_artifact["model_family_version"], "model_family_registry_hash": self.contract["candidate_model_family_registry"]["registry_hash"],
            "training_config_id": parameter_artifact["training_config_id"], "training_config_hash": parameter_artifact["training_config_hash"],
            "deterministic_runtime_profile_id": parameter_artifact["deterministic_runtime_profile_id"], "deterministic_runtime_profile_hash": parameter_artifact["deterministic_runtime_profile_hash"],
            "fitting_implementation_id": parameter_artifact["fitting_implementation_id"], "fitting_implementation_hash": parameter_artifact["fitting_implementation_hash"],
            "status": "CANDIDATE", "calibration_state": "NOT_CALIBRATED", "ephemeral": True, "fixture_label": "SYNTHETIC_CONTRACT_FIXTURE_ONLY",
        }
        if extra_bindings:
            package.update(extra_bindings)
        try:
            validate_model_artifact_package(package, self.contract)
        except Ewp004ContractError as exc:
            raise Ewp004RuntimeError(exc.code, str(exc)) from exc
        package["artifact_hash"] = _hash_without(package)
        return package

    def selection_key(self, candidate: Mapping[str, Any]) -> tuple[Any, ...]:
        metrics = candidate.get("metrics", candidate)
        family_id = candidate.get("family_id", "")
        try:
            return (float(metrics["mean_out_of_time_log_loss"]), float(metrics["mean_out_of_time_brier_score"]), float(metrics["log_loss_variance"]), float(metrics["complexity"]), str(family_id))
        except (KeyError, TypeError, ValueError) as exc:
            raise Ewp004RuntimeError("SELECTION_METRIC_INPUT_INVALID", str(exc)) from exc

    def select_candidate(self, candidates: Sequence[Mapping[str, Any]], *, evaluation_partition: str = "validation") -> Mapping[str, Any]:
        self.validate_evaluation_partition(evaluation_partition, purpose="candidate_selection")
        if evaluation_partition.casefold() == "holdout":
            raise Ewp004RuntimeError("HOLDOUT_LEAKAGE_REJECTED", "holdout is one-time final independent evaluation only")
        if not candidates:
            raise Ewp004RuntimeError("NO_CANDIDATES", "candidate selection requires candidates")
        return min(candidates, key=self.selection_key)

    def validate_evaluation_partition(self, partition: str, *, purpose: str) -> None:
        if partition not in {"train", "validation", "out_of_time", "holdout"}:
            raise Ewp004RuntimeError("EVALUATION_PARTITION_INVALID", partition)
        if partition == "holdout" and purpose != "final_independent_evaluation":
            raise Ewp004RuntimeError("HOLDOUT_LEAKAGE_REJECTED", "holdout is reserved for one final independent evaluation")
        if partition == "holdout" and purpose == "final_independent_evaluation":
            return
        if purpose in {"tuning", "search", "early_stopping"} and partition == "holdout":
            raise Ewp004RuntimeError("HOLDOUT_LEAKAGE_REJECTED", purpose)

    def validate_promotion_transition(self, current: str, target: str, *, human_gate: bool = False) -> None:
        if current not in PROMOTION_STATES or target not in PROMOTION_STATES:
            raise Ewp004RuntimeError("PROMOTION_STATE_INVALID", f"{current}->{target}")
        allowed = {("CANDIDATE", "VALIDATED"), ("VALIDATED", "APPROVED_FOR_ENGINE"), ("VALIDATED", "REJECTED")}
        if (current, target) not in allowed:
            raise Ewp004RuntimeError("PROMOTION_TRANSITION_INVALID", f"{current}->{target}")
        if target == "APPROVED_FOR_ENGINE" and not human_gate:
            raise Ewp004RuntimeError("PROMOTION_HUMAN_GATE_REQUIRED", "automatic promotion is forbidden")

    def promote_candidate(self, current: str, target: str, *, human_gate: bool = False) -> Mapping[str, Any]:
        self.validate_promotion_transition(current, target, human_gate=human_gate)
        if target == "APPROVED_FOR_ENGINE":
            raise Ewp004RuntimeError("EWP004_PROMOTION_OUT_OF_SCOPE", "EWP-004 cannot approve or insert a model registry artifact")
        return {"from": current, "to": target, "registry_inserted": False, "automatic_promotion": False}

    def scope_boundary(self) -> dict[str, Any]:
        return {"project_root": str(self.project_root), "f_drive_pass": self.project_root.drive.upper() == "F:", "v3_3_3_modified": False, "database_or_supabase_touched": False, "formal_fit_executed": False, "formal_artifacts_generated": False, "model_registry_inserted": False}


__all__ = [
    "CandidateExecutionPlan", "CandidateFittingAdapter", "Ewp004Runtime", "Ewp004RuntimeError", "FormalFitGateResult",
    "PROMOTION_STATES", "canonical_bytes", "sha256_value",
]
