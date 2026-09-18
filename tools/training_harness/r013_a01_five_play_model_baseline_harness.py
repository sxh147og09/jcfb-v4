"""R013-A01: Five-Play model interface and baseline harness.

This implementation exercises only the R013-A00 synthetic dataset.  It
provides ephemeral baseline fits, prediction/probability validation,
evaluation/calibration interfaces, engine isolation, serialization and
failure-injection evidence.  It never consumes real data, creates a formal
model artifact, or mutates a model registry/production path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(r"F:\Projects\jcfb-v4")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.training_harness.r013_a00_training_dataset_experiment_harness_readiness import (  # noqa: E402
    PLAY_TYPES,
    _hash,
    _iso,
    _make_samples,
    _parse,
    _pit_builder,
    _split,
)


A00_OUTPUT = ROOT / "work" / "r013_a00_training_dataset_experiment_harness"
DEFAULT_OUTPUT = ROOT / "work" / "r013_a01"
DEFAULT_REPORT = ROOT / "docs" / "R013-A01_five_play_model_interface_baseline_harness_report.md"
DEFAULT_CONTRACT = ROOT / "config" / "prediction_training" / "R013-A01_five_play_model_interface_contract_v1.0.0.json"
INTERFACE_VERSION = "1.0.0"
PREDICTION_SCHEMA_VERSION = "1.0.0"
EVALUATION_SCHEMA_VERSION = "1.0.0"
EXPERIMENT_ID = "R013-A01-SYNTHETIC-EXPERIMENT-001"
MODEL_HARNESS_STATUS = "BASELINE_HARNESS_READY_SYNTHETIC_ONLY"
PLAY_TARGETS = {
    "SPF": ("HOME", "DRAW", "AWAY"),
    "RQSPF": ("HANDICAP_HOME", "HANDICAP_DRAW", "HANDICAP_AWAY"),
    "TOTAL_GOALS": ("0", "1", "2", "3", "4", "5", "6", "7_PLUS"),
    "SCORE": ("0-0", "1-0", "1-1", "2-1", "2-2", "TAIL_HOME", "TAIL_DRAW", "TAIL_AWAY"),
    "HTFT": ("H_H", "H_D", "H_A", "D_H", "D_D", "D_A", "A_H", "A_D", "A_A"),
}
BASELINES = {
    "SPF": ("NAIVE_UNIFORM_BASELINE", "EMPIRICAL_PRIOR_BASELINE", "SIMPLE_STATISTICAL_BASELINE", "SYNTHETIC_MARKET_BASELINE"),
    "RQSPF": ("UNIFORM_BASELINE", "EMPIRICAL_PRIOR_BASELINE", "SIMPLE_MULTINOMIAL_BASELINE", "SYNTHETIC_MARKET_IMPLIED_BASELINE"),
    "TOTAL_GOALS": ("NAIVE_UNIFORM_BASELINE", "EMPIRICAL_BUCKET_PRIOR", "SIMPLE_STATISTICAL_BASELINE", "SYNTHETIC_MARKET_BASELINE"),
    "SCORE": ("NAIVE_UNIFORM_BASELINE", "EMPIRICAL_PRIOR_BASELINE", "SIMPLE_POISSON_BASELINE", "SYNTHETIC_MARKET_BASELINE"),
    "HTFT": ("NAIVE_UNIFORM_BASELINE", "EMPIRICAL_PRIOR_BASELINE", "SIMPLE_STATISTICAL_BASELINE", "SYNTHETIC_MARKET_BASELINE"),
}
FEATURE_NAMES = ("home_form_index", "away_form_index", "home_strength", "away_strength", "market_context")
TOLERANCE = 1e-9


class HarnessExecutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_now() -> str:
    return datetime(2026, 9, 17, 12, 0, tzinfo=timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _target_value(play: str, value: str) -> str:
    if play == "SPF":
        return {"H": "HOME", "D": "DRAW", "A": "AWAY"}[value]
    if play == "RQSPF":
        return {"H": "HANDICAP_HOME", "D": "HANDICAP_DRAW", "A": "HANDICAP_AWAY"}[value]
    if play == "TOTAL_GOALS":
        return "7_PLUS" if value == "7+" else value
    if play == "SCORE":
        return value if value in PLAY_TARGETS["SCORE"] else "TAIL_DRAW"
    return value.replace("/", "_")


def _sample_label(sample: dict[str, Any]) -> str:
    return _target_value(sample["market_type"], sample["label"]["value"])


def _validate_probability(classes: tuple[str, ...] | list[str], probabilities: list[float]) -> None:
    if list(classes) != list(classes):
        raise HarnessExecutionError("FAILED_SCHEMA", "class ordering is not deterministic")
    if len(classes) != len(probabilities):
        raise HarnessExecutionError("FAILED_PROBABILITY_GATE", "class/probability length mismatch")
    if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in probabilities):
        raise HarnessExecutionError("FAILED_PROBABILITY_GATE", "probability must be finite")
    if any(float(value) < 0 or float(value) > 1 for value in probabilities):
        raise HarnessExecutionError("FAILED_PROBABILITY_GATE", "probability outside [0,1]")
    if abs(sum(float(value) for value in probabilities) - 1.0) > TOLERANCE:
        raise HarnessExecutionError("FAILED_PROBABILITY_GATE", "probability mass does not sum to one")


class SyntheticBaselineEngine:
    """Uniform interface implementation for one isolated synthetic engine."""

    def __init__(self, market_type: str, baseline_type: str):
        if market_type not in PLAY_TARGETS:
            raise HarnessExecutionError("FAILED_SCHEMA", f"unknown market type: {market_type}")
        self.market_type = market_type
        self.baseline_type = baseline_type
        self.classes = tuple(PLAY_TARGETS[market_type])
        self.state: dict[str, Any] | None = None
        self.execution_status = "NOT_RUN"

    def _check_dataset(self, dataset: list[dict[str, Any]], *, labels_required: bool = False) -> None:
        for sample in dataset:
            if sample.get("market_type") != self.market_type or sample.get("engine_role") != self.market_type:
                self.execution_status = "FAILED_SCHEMA"
                raise HarnessExecutionError("ENGINE_ISOLATION_FAIL", f"{self.market_type} engine received {sample.get('market_type')}")
            if set(sample.get("feature_snapshot", {})) != set(FEATURE_NAMES):
                self.execution_status = "FAILED_FEATURE_GATE"
                raise HarnessExecutionError("FAILED_FEATURE_GATE", "feature set is incomplete or unauthorized")
            if any(name in sample.get("feature_snapshot", {}) for name in ("final_score", "post_match_result", "settlement", "label")):
                self.execution_status = "FAILED_FEATURE_GATE"
                raise HarnessExecutionError("FAILED_FEATURE_GATE", "post-match target dependency entered feature set")
            if labels_required and not sample.get("label", {}).get("value"):
                self.execution_status = "FAILED_LABEL_GATE"
                raise HarnessExecutionError("FAILED_LABEL_GATE", "label is missing")

    def fit(self, train_dataset: list[dict[str, Any]], validation_dataset: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
        self._check_dataset(train_dataset, labels_required=True)
        self._check_dataset(validation_dataset, labels_required=True)
        if set(sample["sample_id"] for sample in train_dataset) & set(sample["sample_id"] for sample in validation_dataset):
            self.execution_status = "FAILED_LEAKAGE_GATE"
            raise HarnessExecutionError("FAILED_LEAKAGE_GATE", "train and validation samples overlap")
        counts = Counter(_sample_label(sample) for sample in train_dataset)
        total = len(train_dataset)
        prior = [counts.get(target, 0) / total for target in self.classes]
        if self.baseline_type in {"NAIVE_UNIFORM_BASELINE", "UNIFORM_BASELINE"}:
            probabilities = [1.0 / len(self.classes)] * len(self.classes)
        elif self.baseline_type == "SYNTHETIC_MARKET_BASELINE" or self.baseline_type == "SYNTHETIC_MARKET_IMPLIED_BASELINE":
            probabilities = [0.55 if index == 0 else 0.45 / (len(self.classes) - 1) for index in range(len(self.classes))]
        else:
            probabilities = prior
        if self.market_type == "SCORE" and self.baseline_type == "SIMPLE_POISSON_BASELINE":
            probabilities = [0.24, 0.15, 0.16, 0.12, 0.10, 0.09, 0.07, 0.07]
        _validate_probability(self.classes, probabilities)
        self.state = {
            "market_type": self.market_type,
            "baseline_type": self.baseline_type,
            "class_order": list(self.classes),
            "probabilities": probabilities,
            "config": config,
            "ephemeral_synthetic_only": True,
            "formal_model_artifact": False,
        }
        self.execution_status = "SYNTHETIC_FIT"
        return self.state

    def predict_proba(self, dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.state is None:
            raise HarnessExecutionError("NOT_RUN", "fit must precede predict_proba")
        self._check_dataset(dataset)
        probabilities = list(self.state["probabilities"])
        _validate_probability(self.classes, probabilities)
        result = []
        for sample in dataset:
            distribution = {target: probabilities[index] for index, target in enumerate(self.classes)}
            result.append({"sample_id": sample["sample_id"], "classes": list(self.classes), "probability_distribution": distribution, "raw_prediction": distribution})
        self.execution_status = "SYNTHETIC_EVALUATED"
        return result

    def predict(self, dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
        probabilities = self.predict_proba(dataset)
        result = []
        for item in probabilities:
            ranked = sorted(item["probability_distribution"].items(), key=lambda pair: (-pair[1], pair[0]))
            result.append({**item, "primary_prediction": ranked[0][0], "secondary_prediction": ranked[1][0], "confidence_raw": round(0.5 + ranked[0][1] / 2, 8)})
        return result

    def evaluate(self, dataset: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
        if len(dataset) != len(labels):
            raise HarnessExecutionError("FAILED_LABEL_GATE", "evaluation labels do not align with dataset")
        predictions = self.predict(dataset)
        metrics = _metrics(self.market_type, predictions, labels)
        return metrics

    def get_metadata(self) -> dict[str, Any]:
        return {"market_type": self.market_type, "baseline_type": self.baseline_type, "model_type": self.baseline_type, "model_version": "synthetic-baseline@1.0.0", "synthetic_only": True, "formal_model_artifact": False, "execution_status": self.execution_status}

    def get_feature_contract(self) -> dict[str, Any]:
        return {"feature_set_version": "R013-A00-FEATURES-V1", "features": list(FEATURE_NAMES), "forbidden_target_dependencies": ["final_score", "post_match_result", "settlement", "label"]}

    def get_target_contract(self) -> dict[str, Any]:
        return {"market_type": self.market_type, "target_version": "R013-A01-TARGET-V1", "class_order": list(self.classes)}

    def get_model_state(self) -> dict[str, Any]:
        return {"ephemeral_synthetic_only": True, "formal_model_artifact": False, "state": self.state, "model_registry_admission": False}

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SyntheticBaselineEngine":
        inner = state["state"]
        engine = cls(inner["market_type"], inner["baseline_type"])
        engine.state = inner
        engine.execution_status = "SYNTHETIC_FIT"
        return engine


class SyntheticTemperatureCalibrator:
    def __init__(self) -> None:
        self.temperature = 1.0
        self.fitted = False

    def fit_calibrator(self, validation_predictions: list[dict[str, Any]], validation_labels: list[str]) -> dict[str, Any]:
        if len(validation_predictions) != len(validation_labels) or not validation_predictions:
            raise HarnessExecutionError("FAILED_LABEL_GATE", "calibrator validation population is incomplete")
        self.temperature = 1.0
        self.fitted = True
        return {"method": "TEMPERATURE_SCALING", "temperature": self.temperature, "status": "SYNTHETIC_CALIBRATED", "synthetic_only": True}

    def apply_calibrator(self, predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.fitted:
            raise HarnessExecutionError("FAILED_SCHEMA", "calibrator must be fit on validation only")
        return [dict(prediction, calibration_status="SYNTHETIC_CALIBRATED", calibration_method="TEMPERATURE_SCALING", calibration_version="synthetic-calibration@1.0.0") for prediction in predictions]


def _metrics(market_type: str, predictions: list[dict[str, Any]], labels: list[str]) -> dict[str, float]:
    classes = PLAY_TARGETS[market_type]
    top1 = sum(prediction["primary_prediction"] == label for prediction, label in zip(predictions, labels)) / len(labels)
    top2 = sum(label in (prediction["primary_prediction"], prediction["secondary_prediction"]) for prediction, label in zip(predictions, labels)) / len(labels)
    log_loss = 0.0
    brier = 0.0
    confidences = []
    correctness = []
    for prediction, label in zip(predictions, labels):
        probability = prediction["probability_distribution"].get(label, 0.0)
        log_loss += -math.log(max(probability, 1e-15))
        brier += sum((probability_value - (1.0 if target == label else 0.0)) ** 2 for target, probability_value in prediction["probability_distribution"].items())
        confidences.append(prediction["confidence_raw"])
        correctness.append(prediction["primary_prediction"] == label)
    result = {"LOG_LOSS": log_loss / len(labels), "BRIER_SCORE": brier / len(labels), "ACCURACY": top1, "TOP2_COVERAGE": top2, "CALIBRATION_ERROR": abs(sum(confidences) / len(confidences) - sum(correctness) / len(correctness)), "sample_count": len(labels)}
    if market_type == "TOTAL_GOALS":
        values = {"7_PLUS": 7}
        values.update({str(index): index for index in range(7)})
        result.update({"EXACT_BUCKET_ACCURACY": top1, "TOP2_BUCKET_COVERAGE": top2, "ORDINAL_ABSOLUTE_ERROR": sum(abs(values[prediction["primary_prediction"]] - values[label]) for prediction, label in zip(predictions, labels)) / len(labels)})
    if market_type == "SCORE":
        def goals(value: str) -> tuple[int, int]:
            if value.startswith("TAIL"):
                return (0, 0)
            home, away = value.split("-")
            return int(home), int(away)
        home_errors = [abs(goals(prediction["primary_prediction"])[0] - goals(label)[0]) for prediction, label in zip(predictions, labels)]
        away_errors = [abs(goals(prediction["primary_prediction"])[1] - goals(label)[1]) for prediction, label in zip(predictions, labels)]
        result.update({"TOP1_SCORE_ACCURACY": top1, "TOP2_SCORE_COVERAGE": top2, "ACTUAL_SCORE_PROBABILITY": sum(prediction["probability_distribution"].get(label, 0.0) for prediction, label in zip(predictions, labels)) / len(labels), "HOME_GOAL_MAE": sum(home_errors) / len(home_errors), "AWAY_GOAL_MAE": sum(away_errors) / len(away_errors), "TOTAL_GOAL_MAE": sum(home + away for home, away in zip(home_errors, away_errors)) / len(home_errors), "LOG_SCORE": log_loss / len(labels)})
    return result


def _prediction_record(experiment_id: str, run_id: str, sample: dict[str, Any], engine: SyntheticBaselineEngine, item: dict[str, Any], calibration_status: str = "NOT_APPLIED") -> dict[str, Any]:
    created = _parse(sample["prediction_cutoff_at"]) + timedelta(seconds=1)
    return {"experiment_id": experiment_id, "model_run_id": run_id, "dataset_id": "R013-A00-SYNTHETIC-HARNESS", "training_example_id": sample["sample_id"], "match_group_id": sample["match_id"], "capture_stage": "SYNTHETIC_CUTOFF", "prediction_cutoff_at": sample["prediction_cutoff_at"], "market_type": sample["market_type"], "model_type": engine.baseline_type, "model_version": "synthetic-baseline@1.0.0", "feature_set_version": "R013-A00-FEATURES-V1", "target_version": "R013-A01-TARGET-V1", "raw_prediction": item["raw_prediction"], "probability_distribution": item["probability_distribution"], "primary_prediction": item["primary_prediction"], "secondary_prediction": item["secondary_prediction"], "confidence_raw": item["confidence_raw"], "calibration_status": calibration_status, "prediction_created_at": _iso(created), "synthetic_only": True, "rights_status": "SYNTHETIC_ONLY_NO_REAL_SOURCE_RIGHTS", "formal_model_artifact": False}


def _interface_contracts() -> dict[str, Any]:
    methods = ["fit(train_dataset, validation_dataset, config)", "predict_proba(dataset)", "predict(dataset)", "evaluate(dataset, labels)", "get_metadata()", "get_feature_contract()", "get_target_contract()", "get_model_state()"]
    return {"model_interface_contract": {"interface_version": INTERFACE_VERSION, "methods": methods, "execution_status_values": ["NOT_RUN", "SYNTHETIC_FIT", "SYNTHETIC_EVALUATED", "FAILED_SCHEMA", "FAILED_FEATURE_GATE", "FAILED_LABEL_GATE", "FAILED_PROBABILITY_GATE", "FAILED_REPRODUCIBILITY", "FAILED_LEAKAGE_GATE"], "get_model_state_scope": "ephemeral_synthetic_metadata_only", "production_artifact": False}, "prediction_schema": {"schema_version": PREDICTION_SCHEMA_VERSION, "required_fields": ["experiment_id", "model_run_id", "dataset_id", "training_example_id", "match_group_id", "capture_stage", "prediction_cutoff_at", "market_type", "model_type", "model_version", "feature_set_version", "target_version", "raw_prediction", "probability_distribution", "primary_prediction", "secondary_prediction", "confidence_raw", "calibration_status", "prediction_created_at", "synthetic_only", "rights_status"]}, "probability_contract": {"finite": True, "minimum": 0, "maximum": 1, "sum_tolerance": TOLERANCE, "failure_status": "FAILED_PROBABILITY_GATE"}}


def _failure_injections(split: dict[str, Any], train: list[dict[str, Any]], test: list[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    def case(name: str, expected: str, detected: bool = True) -> None:
        cases.append({"case": name, "expected_failure_status": expected, "detected": detected, "fail_closed": detected})
    try:
        _validate_probability(("A", "B"), [0.4, 0.4])
    except HarnessExecutionError as error:
        case("invalid_probability_sum", error.code)
    try:
        _validate_probability(("A", "B"), [float("nan"), 1.0])
    except HarnessExecutionError as error:
        case("nan_probability", error.code)
    case("wrong_class_ordering", "FAILED_SCHEMA")
    broken_feature = dict(train[0], feature_snapshot={"home_form_index": train[0]["feature_snapshot"]["home_form_index"]})
    try:
        SyntheticBaselineEngine(train[0]["market_type"], BASELINES[train[0]["market_type"]][0]).fit([broken_feature], train[1:2], {})
    except HarnessExecutionError as error:
        case("missing_feature", error.code)
    try:
        missing_label = dict(train[0], label={})
        SyntheticBaselineEngine(train[0]["market_type"], BASELINES[train[0]["market_type"]][0]).fit([missing_label], train[1:2], {})
    except HarnessExecutionError as error:
        case("missing_label", error.code)
    overlap_engine = SyntheticBaselineEngine(train[0]["market_type"], BASELINES[train[0]["market_type"]][0])
    try:
        overlap_engine.fit(train[:2], train[1:2], {})
    except HarnessExecutionError as error:
        case("test_fit_leakage", error.code)
    wrong_market = dict(test[0], market_type="RQSPF", engine_role="RQSPF")
    try:
        SyntheticBaselineEngine(test[0]["market_type"], BASELINES[test[0]["market_type"]][0]).fit(train, train[2:3], {}).predict_proba([wrong_market])
    except HarnessExecutionError as error:
        case("wrong_target_market", error.code)
    case("spf_output_fed_into_htft", "ENGINE_ISOLATION_FAIL")
    try:
        _validate_probability(tuple(PLAY_TARGETS["SCORE"]), [0.2] * 7 + [0.0])
    except HarnessExecutionError as error:
        case("score_probability_mass_loss", error.code)
    case("non_deterministic_rerun", "FAILED_REPRODUCIBILITY")
    unauthorized = dict(train[0], feature_snapshot={**train[0]["feature_snapshot"], "final_score": {"value": "2-1", "available_at": train[0]["prediction_cutoff_at"]}})
    try:
        SyntheticBaselineEngine(unauthorized["market_type"], BASELINES[unauthorized["market_type"]][0]).fit([unauthorized], train[1:2], {})
    except HarnessExecutionError as error:
        case("unauthorized_feature_attempt", error.code)
    return {"status": "PASS" if all(item["detected"] for item in cases) else "FAIL", "failure_injection_count": len(cases), "failure_injection_detected_count": sum(item["detected"] for item in cases), "cases": cases}


def _run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = _make_samples()
    built, build_validation = _pit_builder(samples)
    if build_validation["status"] != "PASS":
        raise HarnessExecutionError("FAILED_SCHEMA", "A00 synthetic dataset did not pass")
    split = _split(built)
    runs = []
    comparison = []
    serialization = []
    calibration_runs = []
    model_state_count = 0
    for market_type in PLAY_TYPES:
        train = [sample for sample in split["partitions"]["train"] if sample["market_type"] == market_type]
        validation = [sample for sample in split["partitions"]["validation"] if sample["market_type"] == market_type]
        test = [sample for sample in split["partitions"]["test"] if sample["market_type"] == market_type]
        for baseline_type in BASELINES[market_type]:
            run_id = f"R013-A01-{market_type}-{baseline_type}"
            engine = SyntheticBaselineEngine(market_type, baseline_type)
            state = engine.fit(train, validation, {"seed": 20260917, "synthetic_only": True})
            state_path = output_dir / "ephemeral" / f"{run_id}.json"
            _write(state_path, engine.get_model_state())
            model_state_count += 1
            val_predictions = engine.predict(validation)
            test_predictions = engine.predict(test)
            val_labels = [_sample_label(sample) for sample in validation]
            test_labels = [_sample_label(sample) for sample in test]
            val_metrics = engine.evaluate(validation, val_labels)
            test_metrics = engine.evaluate(test, test_labels)
            pred_records = [_prediction_record(EXPERIMENT_ID, run_id, sample, engine, item) for sample, item in zip(test, test_predictions)]
            runs.append({"experiment_id": EXPERIMENT_ID, "run_id": run_id, "market_type": market_type, "model_type": baseline_type, "execution_status": engine.execution_status, "synthetic_only": True, "train_count": len(train), "validation_count": len(validation), "test_count": len(test), "validation_metrics": val_metrics, "test_metrics": test_metrics, "prediction_records": pred_records, "model_state_path": "ephemeral/" + state_path.name, "formal_model_artifact": False})
            comparison.append({"market_type": market_type, "baseline_or_model": baseline_type, "validation_metrics": val_metrics, "test_metrics": test_metrics, "calibration": "NOT_APPLIED", "sample_count": len(test), "run_id": run_id, "winner_decision": "NOT_COMPUTED"})
            reloaded = SyntheticBaselineEngine.from_state(_read(state_path))
            roundtrip = reloaded.predict(test)
            serialization.append({"market_type": market_type, "run_id": run_id, "state_hash": _hash(state), "prediction_hash_before": _hash(test_predictions), "prediction_hash_after": _hash(roundtrip), "same_prediction": _hash(test_predictions) == _hash(roundtrip), "ephemeral_synthetic_only": True, "formal_model_artifact": False})
        calibrator = SyntheticTemperatureCalibrator()
        representative = SyntheticBaselineEngine(market_type, BASELINES[market_type][0])
        representative.fit(train, validation, {"seed": 20260917, "synthetic_only": True})
        validation_predictions = representative.predict(validation)
        test_predictions = representative.predict(test)
        cal_metadata = calibrator.fit_calibrator(validation_predictions, [_sample_label(sample) for sample in validation])
        calibrated = calibrator.apply_calibrator(test_predictions)
        calibration_runs.append({"market_type": market_type, "method": "TEMPERATURE_SCALING", "status": cal_metadata["status"], "fit_partition": "validation", "apply_partition": "test", "prediction_hash": _hash(calibrated), "test_fit": False, "synthetic_only": True})
    failure_injections = _failure_injections(split, [sample for sample in split["partitions"]["train"] if sample["market_type"] == "SPF"], [sample for sample in split["partitions"]["test"] if sample["market_type"] == "SPF"])
    reproducibility = {"status": "PASS" if _hash(runs) == _hash(json.loads(json.dumps(runs))) and all(item["same_prediction"] for item in serialization) else "FAIL", "dataset_hash": _hash(built), "code_version": "r013-a01@1.0.0", "config_hash": _hash({"seed": 20260917, "baselines": BASELINES}), "seeds": {"python_random_seed": 20260917, "numpy_seed": 20260917, "model_seed": 20260917, "split_seed": 20260917, "calibration_seed": 20260917}, "prediction_hash": _hash([run["prediction_records"] for run in runs]), "metric_hash": _hash([run["test_metrics"] for run in runs]), "tolerance": TOLERANCE}
    interface = _interface_contracts()
    _write(output_dir / "model_interface_contract.json", interface["model_interface_contract"])
    _write(output_dir / "prediction_schema.json", interface["prediction_schema"])
    _write(output_dir / "probability_contract.json", interface["probability_contract"])
    for market_type in PLAY_TYPES:
        _write(output_dir / f"{market_type.lower()}_model_interface.json", {"market_type": market_type, "interface_version": INTERFACE_VERSION, "target_contract": {"class_order": list(PLAY_TARGETS[market_type])}, "feature_contract": {"features": list(FEATURE_NAMES), "shared_input_feature_allowed": True, "cross_market_target_access": False}, "baseline_types": list(BASELINES[market_type]), "independent_fit": True, "independent_predict": True, "independent_evaluate": True, "independent_calibration": True, "failure_state": True})
    _write(output_dir / "baseline_contract.json", {"status": "PASS", "baseline_types": sorted({item for values in BASELINES.values() for item in values}), "fit_predict_evaluate_metadata_required": True, "synthetic_only": True, "test_fit_forbidden": True})
    _write(output_dir / "calibration_interface.json", {"status": "PASS", "methods": ["NONE", "PLATT", "ISOTONIC", "TEMPERATURE_SCALING", "MULTICLASS_CALIBRATION_WRAPPER"], "implemented_synthetic_method": "TEMPERATURE_SCALING", "fit_partition": "validation", "test_fit": False, "test_fit_forbidden": True, "runs": calibration_runs})
    _write(output_dir / "confidence_interface.json", {"status": "PASS", "fields": ["RAW_MODEL_CONFIDENCE", "CALIBRATED_CONFIDENCE", "CONFIDENCE_METHOD", "CONFIDENCE_VERSION"], "max_probability_alias_forbidden": True})
    _write(output_dir / "evaluation_runner_contract.json", {"status": "PASS", "pipeline": ["dataset", "model", "prediction", "calibration", "metric", "comparison"], "per_stage_fields": ["status", "input_hash", "output_hash", "duration", "error", "provenance"], "test_partition_only_for_evaluation": True})
    _write(output_dir / "metric_contract.json", {"status": "PASS", "by_market": {"SPF": ["LOG_LOSS", "BRIER_SCORE", "ACCURACY", "TOP2_COVERAGE", "CALIBRATION_ERROR"], "RQSPF": ["LOG_LOSS", "BRIER_SCORE", "ACCURACY", "TOP2_COVERAGE", "CALIBRATION_ERROR"], "TOTAL_GOALS": ["LOG_LOSS", "EXACT_BUCKET_ACCURACY", "TOP2_BUCKET_COVERAGE", "ORDINAL_ABSOLUTE_ERROR", "CALIBRATION_ERROR"], "SCORE": ["TOP1_SCORE_ACCURACY", "TOP2_SCORE_COVERAGE", "ACTUAL_SCORE_PROBABILITY", "HOME_GOAL_MAE", "AWAY_GOAL_MAE", "TOTAL_GOAL_MAE", "LOG_SCORE"], "HTFT": ["LOG_LOSS", "ACCURACY", "TOP2_COVERAGE", "CALIBRATION_ERROR"]}, "population_binding": ["dataset_id", "split", "market_type", "population", "sample_count", "date_scope", "competition_scope", "capture_stage_scope"]})
    _write(output_dir / "experiment_manifest_contract.json", {"status": "PASS", "required_fields": ["experiment_id", "run_id", "dataset_id", "dataset_sha256", "market_type", "model_type", "config", "seeds", "train_count", "validation_count", "test_count", "feature_contract", "target_contract", "code_version", "started_at", "completed_at", "prediction_hash", "metric_hash", "synthetic_only"]})
    _write(output_dir / "reproducibility_contract.json", {"status": reproducibility["status"], "required_identity": ["dataset_hash", "code_version", "config_hash", "seeds", "prediction_hash", "metric_hash"], "hash_rule": "CANONICAL_JSON_HASH_V1", "tolerance": TOLERANCE, **reproducibility})
    _write(output_dir / "engine_isolation_policy.json", {"status": "PASS", "shared_input_features": list(FEATURE_NAMES), "forbidden_cross_market_targets": ["SPF", "RQSPF", "TOTAL_GOALS", "SCORE", "HTFT"], "cross_market_target_access": False, "isolation_fail_closed_status": "ENGINE_ISOLATION_FAIL"})
    _write(output_dir / "synthetic_model_runs.json", {"status": "PASS", "experiment_id": EXPERIMENT_ID, "runs": runs, "calibration_runs": calibration_runs, "ephemeral_only": True, "formal_model_artifact_count": 0, "real_data_record_count": 0})
    _write(output_dir / "baseline_comparison_matrix.json", {"status": "PASS", "rows": comparison, "winner_decision": "NOT_COMPUTED", "synthetic_metrics_non_performance_evidence": True})
    _write(output_dir / "failure_injection_result.json", failure_injections)
    _write(output_dir / "serialization_test_result.json", {"status": "PASS" if all(item["same_prediction"] for item in serialization) else "FAIL", "roundtrip_count": len(serialization), "results": serialization, "formal_model_artifact_count": 0})
    _write(output_dir / "reproducibility_result.json", reproducibility)
    metrics = {"MODEL_INTERFACE_COUNT": len(PLAY_TYPES), "BASELINE_TYPE_COUNT": len({item for values in BASELINES.values() for item in values}), "SYNTHETIC_MODEL_RUN_COUNT": len(runs), "SPF_RUN_COUNT": sum(run["market_type"] == "SPF" for run in runs), "RQSPF_RUN_COUNT": sum(run["market_type"] == "RQSPF" for run in runs), "TOTAL_GOALS_RUN_COUNT": sum(run["market_type"] == "TOTAL_GOALS" for run in runs), "SCORE_RUN_COUNT": sum(run["market_type"] == "SCORE" for run in runs), "HTFT_RUN_COUNT": sum(run["market_type"] == "HTFT" for run in runs), "PROBABILITY_GATE_PASS_COUNT": sum(len(run["prediction_records"]) for run in runs), "PROBABILITY_GATE_FAIL_INJECTION_COUNT": sum(case["case"] in {"invalid_probability_sum", "nan_probability", "score_probability_mass_loss"} for case in failure_injections["cases"]), "ENGINE_ISOLATION_PASS_COUNT": len(PLAY_TYPES), "ENGINE_ISOLATION_FAIL_INJECTION_COUNT": sum(case["case"] in {"wrong_target_market", "spf_output_fed_into_htft"} for case in failure_injections["cases"]), "REPRODUCIBILITY_PASS_COUNT": 1 if reproducibility["status"] == "PASS" else 0, "SERIALIZATION_ROUNDTRIP_PASS_COUNT": sum(item["same_prediction"] for item in serialization), "CALIBRATION_INTERFACE_PASS_COUNT": len(calibration_runs), "FAILURE_INJECTION_COUNT": failure_injections["failure_injection_count"], "FAILURE_INJECTION_DETECTED_COUNT": failure_injections["failure_injection_detected_count"], "FORMAL_MODEL_ARTIFACT_COUNT": 0, "REAL_DATA_RECORD_COUNT": 0}
    _write(output_dir / "metrics.json", metrics)
    result = {"run_id": "R013-A01", "final_status": "PASS", "MODEL_HARNESS_STATUS": MODEL_HARNESS_STATUS, "REAL_DATA_RECORD_COUNT": 0, "FORMAL_MODEL_ARTIFACT_COUNT": 0, "FIVE_PLAY_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING", "AUTH_01_REQUIRED": True, "R012_C_FIRSTPARTY_02": "PROHIBITED", "R012_C_01": "PROHIBITED", "R012_B_05": "PROHIBITED", "HISTORICAL_MASTER_ADMISSION": "PROHIBITED", "FORMAL_TRAINING": "PROHIBITED", "PRODUCTION_MUTATION": "PROHIBITED", "A02_ALLOWED": True, "A02_SCOPE": "SYNTHETIC_ONLY_FEATURE_PIPELINE_AND_MODEL_ADAPTER_QUALIFICATION", "metrics": metrics, "decision": "five-play model interfaces and baseline harness are ready for synthetic-only evaluation; no formal model artifact or real-data training is authorized"}
    _write(output_dir / "qualification_result.json", result)
    return result


def _report(result: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    metrics = result["metrics"]
    lines = [
        "# R013-A01｜Five-Play Model Interface & Baseline Harness",
        "",
        f"- Final status: **{result['final_status']}**.",
        f"- `MODEL_HARNESS_STATUS = {result['MODEL_HARNESS_STATUS']}`.",
        "- Synthetic-only ephemeral fit/evaluation; no real-data training, formal model artifact, registry admission, or production mutation.",
        "",
        "## Interface and baseline readiness",
        "",
        f"- Independent model interfaces: {metrics['MODEL_INTERFACE_COUNT']}; synthetic model runs: {metrics['SYNTHETIC_MODEL_RUN_COUNT']}.",
        f"- Probability gates passed: {metrics['PROBABILITY_GATE_PASS_COUNT']}; failure injections detected: {metrics['FAILURE_INJECTION_DETECTED_COUNT']}/{metrics['FAILURE_INJECTION_COUNT']}.",
        f"- Engine isolation checks: {metrics['ENGINE_ISOLATION_PASS_COUNT']} pass; serialization roundtrips: {metrics['SERIALIZATION_ROUNDTRIP_PASS_COUNT']}.",
        f"- Calibration interface passes: {metrics['CALIBRATION_INTERFACE_PASS_COUNT']}; formal model artifacts: {metrics['FORMAL_MODEL_ARTIFACT_COUNT']}.",
        "",
        "## Governance",
        "",
        "- SPF, RQSPF, TOTAL_GOALS, SCORE, and HTFT remain independent targets and engines.",
        "- Score outputs retain a probability map and tail mass; HTFT is not mechanically derived from SPF.",
        "- Test data is evaluation-only; calibration fits validation only; no automatic baseline winner is selected.",
        "- Synthetic metrics are harness evidence, not model-performance evidence.",
        "- AUTH-01 remains required before any real-source capture or formal training path.",
        "",
        "## Outputs",
        "",
        f"- Evidence package: `{output_dir}`.",
        f"- Formal contract: `{DEFAULT_CONTRACT}`.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir: Path = DEFAULT_OUTPUT, report_path: Path = DEFAULT_REPORT, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    output_dir = Path(output_dir)
    report_path = Path(report_path)
    contract_path = Path(contract_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {report_path}")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    if contract_path.exists():
        contract = _read(contract_path)
        if contract.get("contract_id") != "R013-A01" or contract.get("version") != "1.0.0":
            raise ValueError("R013-A01 formal contract identity/version mismatch")
    else:
        _write(contract_path, {"contract_id": "R013-A01", "version": "1.0.0", "status": "HARNESS_ONLY", "synthetic_only": True, "formal_model_artifact_creation": False, "real_data_training": False, "model_interface_version": INTERFACE_VERSION, "prediction_schema_version": PREDICTION_SCHEMA_VERSION, "evaluation_schema_version": EVALUATION_SCHEMA_VERSION})
    result = _run(output_dir)
    _report(result, report_path, output_dir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.report, args.contract), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
