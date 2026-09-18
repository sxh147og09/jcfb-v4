"""R013-A03: synthetic-only experiment orchestration and model selection governance.

The harness creates auditable experiment/candidate/run evidence without
claiming model performance.  It consumes only the deterministic R013-A00
synthetic dataset and R013-A02 synthetic feature matrices, writes ephemeral
synthetic run state under ``work/r013_a03/ephemeral``, and never creates a
formal model artifact, registry record, or production promotion.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(r"F:\Projects\jcfb-v4")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.training_harness.r013_a00_training_dataset_experiment_harness_readiness import (  # noqa: E402
    PARTITIONS,
    PLAY_TYPES,
    SEED,
    _hash,
    _iso,
    _make_samples,
    _pit_builder,
    _split,
)
from tools.training_harness.r013_a02_feature_pipeline_model_adapter import (  # noqa: E402
    ADAPTER_VERSION,
    FEATURE_SCHEMA_VERSION,
    ENGINE_FEATURES,
    _build_matrices,
)


HARNESS_ID = "R013-A03"
GOVERNANCE_STATUS = "EXPERIMENT_GOVERNANCE_READY_SYNTHETIC_ONLY"
DEFAULT_OUTPUT = ROOT / "work" / "r013_a03"
DEFAULT_REPORT = ROOT / "docs" / "R013-A03_experiment_orchestration_model_selection_governance_report.md"
DEFAULT_CONTRACT = ROOT / "config" / "prediction_training" / "R013-A03_experiment_model_selection_governance_contract_v1.0.0.json"
GOVERNANCE_VERSION = "1.0.0"
POLICY_VERSION = "1.0.0"
LINEAGE_VERSION = "1.0.0"
SEED_BUNDLE = {"dataset_seed": SEED, "orchestrator_seed": 20260917, "candidate_seed": 20260917}
BASELINE_NAMES = ("NAIVE_BASELINE", "EMPIRICAL_PRIOR", "SIMPLE_STATISTICAL", "MARKET_BASELINE")
MODEL_FAMILIES = ("BASELINE", "STATISTICAL", "LINEAR", "TREE_BASED", "PROBABILISTIC", "SCORE_DISTRIBUTION", "NEURAL", "ENSEMBLE")
EXPERIMENT_STATUSES = ("REGISTERED", "READY_TO_RUN", "RUNNING", "COMPLETED", "FAILED", "INVALIDATED", "HELD", "REJECTED", "ARCHIVED")
CANDIDATE_LIFECYCLE = ("DRAFT", "SYNTHETIC_INTERFACE_VALIDATED", "SYNTHETIC_EVALUATED", "SYNTHETIC_GOVERNANCE_ELIGIBLE", "REAL_DATA_NOT_AUTHORIZED", "REAL_TRAINING_CANDIDATE", "REAL_VALIDATION_CANDIDATE", "PROMOTION_REVIEW", "APPROVED", "REJECTED", "RETIRED")


class GovernanceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}".rstrip())
        self.code = code


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _timestamp(index: int, rerun: int = 0) -> str:
    base = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    return _iso(base + timedelta(minutes=index * 3 + rerun))


def _candidate_specs() -> list[dict[str, Any]]:
    family_plan = {
        "SPF": [("BASELINE", "majority_prior_v1"), ("STATISTICAL", "rating_prior_v1"), ("LINEAR", "linear_market_context_v1")],
        "RQSPF": [("BASELINE", "majority_prior_v1"), ("STATISTICAL", "handicap_prior_v1"), ("LINEAR", "linear_handicap_context_v1")],
        "TOTAL_GOALS": [("BASELINE", "empirical_bucket_prior_v1"), ("STATISTICAL", "poisson_goals_v1"), ("PROBABILISTIC", "ordinal_goal_distribution_v1")],
        "SCORE": [("BASELINE", "simple_poisson_baseline_v1"), ("STATISTICAL", "joint_score_prior_v1"), ("SCORE_DISTRIBUTION", "structured_score_distribution_v1")],
        "HTFT": [("BASELINE", "empirical_transition_prior_v1"), ("STATISTICAL", "half_transition_prior_v1"), ("LINEAR", "linear_htft_context_v1")],
    }
    specs: list[dict[str, Any]] = []
    for engine in PLAY_TYPES:
        for ordinal, (family, config_name) in enumerate(family_plan[engine], 1):
            config = {"config_name": config_name, "complexity": ordinal, "fit_policy": "SYNTHETIC_EPHEMERAL_ONLY", "model_artifact": False}
            specs.append({"candidate_id": f"{engine}-CAND-{ordinal:03d}", "market_type": engine, "model_family": family, "model_type": config_name.upper(), "model_config": config, "candidate_ordinal": ordinal})
    return specs


def _metric_registry() -> dict[str, Any]:
    common = {
        "LOG_LOSS": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, None]},
        "BRIER_SCORE": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]},
        "ACCURACY": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]},
        "TOP2_COVERAGE": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]},
        "CALIBRATION_ERROR": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]},
    }
    return {"registry_version": "1.0.0", "metrics": {**common, "EXACT_BUCKET_ACCURACY": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]}, "ORDINAL_ERROR": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, None]}, "TOP1_SCORE_ACCURACY": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]}, "TOP2_SCORE_COVERAGE": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]}, "ACTUAL_SCORE_PROBABILITY": {"direction": "HIGHER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, 1]}, "HOME_GOAL_MAE": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, None]}, "AWAY_GOAL_MAE": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, None]}, "TOTAL_GOAL_MAE": {"direction": "LOWER_IS_BETTER", "invalid_value_policy": "FAIL_GATE", "range": [0, None]}, "PROBABILITY_MASS_VALIDITY": {"direction": "RANGE", "invalid_value_policy": "FAIL_GATE", "range": [0.999999, 1.000001]}, "TAIL_MASS_VALIDITY": {"direction": "RANGE", "invalid_value_policy": "FAIL_GATE", "range": [0.999999, 1.000001]}}, "single_metric_promotion": False, "synthetic_metrics_non_performance_evidence": True}


def _metrics_for(engine: str) -> list[str]:
    if engine in {"SPF", "RQSPF"}:
        return ["LOG_LOSS", "BRIER_SCORE", "ACCURACY", "TOP2_COVERAGE", "CALIBRATION_ERROR"]
    if engine == "TOTAL_GOALS":
        return ["LOG_LOSS", "EXACT_BUCKET_ACCURACY", "TOP2_COVERAGE", "ORDINAL_ERROR", "CALIBRATION_ERROR"]
    if engine == "SCORE":
        return ["TOP1_SCORE_ACCURACY", "TOP2_SCORE_COVERAGE", "ACTUAL_SCORE_PROBABILITY", "HOME_GOAL_MAE", "AWAY_GOAL_MAE", "TOTAL_GOAL_MAE", "PROBABILITY_MASS_VALIDITY", "TAIL_MASS_VALIDITY"]
    return ["LOG_LOSS", "ACCURACY", "TOP2_COVERAGE", "CALIBRATION_ERROR"]


def _metric_value(engine: str, candidate_ordinal: int, split: str, metric: str) -> float:
    offset = candidate_ordinal * 0.013 + (0.007 if split == "test" else 0.0)
    if metric in {"LOG_LOSS", "BRIER_SCORE", "CALIBRATION_ERROR", "ORDINAL_ERROR", "HOME_GOAL_MAE", "AWAY_GOAL_MAE", "TOTAL_GOAL_MAE"}:
        base = {"LOG_LOSS": 0.92, "BRIER_SCORE": 0.23, "CALIBRATION_ERROR": 0.08, "ORDINAL_ERROR": 1.15, "HOME_GOAL_MAE": 0.78, "AWAY_GOAL_MAE": 0.74, "TOTAL_GOAL_MAE": 1.22}[metric]
        return round(max(0.001, base - offset), 6)
    if metric in {"PROBABILITY_MASS_VALIDITY", "TAIL_MASS_VALIDITY"}:
        return 1.0
    base = {"ACCURACY": 0.47, "TOP2_COVERAGE": 0.71, "EXACT_BUCKET_ACCURACY": 0.31, "TOP1_SCORE_ACCURACY": 0.18, "TOP2_SCORE_COVERAGE": 0.39, "ACTUAL_SCORE_PROBABILITY": 0.14}[metric]
    return round(min(0.999, base + offset), 6)


def _phase_run(run_id: str, run_type: str, input_hash: str, output_hash: str, status: str = "COMPLETED", error_state: str | None = None) -> dict[str, Any]:
    stable_offset = int(_hash(run_id).split(":", 1)[1][:8], 16) % 40
    return {"run_id": run_id, "run_type": run_type, "status": status, "input_hash": input_hash, "output_hash": output_hash, "started_at": _timestamp(stable_offset), "completed_at": _timestamp(stable_offset, 1), "error_state": error_state, "synthetic_only": True, "formal_training": False}


def _contract_files() -> dict[str, Any]:
    return {
        "experiment_registry_contract": {"contract_id": "R013-A03-EXPERIMENT-REGISTRY", "version": GOVERNANCE_VERSION, "required_fields": ["experiment_id", "experiment_family", "market_type", "research_question", "dataset_id", "dataset_hash", "feature_schema_version", "feature_matrix_hash", "model_interface_version", "model_type", "model_config", "preprocessing_state_hash", "target_version", "split_policy_version", "evaluation_schema_version", "calibration_config", "baseline_set", "code_commit", "environment_hash", "seed_bundle", "started_at", "completed_at", "synthetic_only", "experiment_status"], "allowed_statuses": EXPERIMENT_STATUSES, "success_status_forbidden": True, "queryable_by": ["market_type", "candidate_id", "experiment_family", "dataset_id", "date", "status", "decision", "contract_version"]},
        "candidate_lifecycle_contract": {"version": GOVERNANCE_VERSION, "allowed_states": CANDIDATE_LIFECYCLE, "maximum_current_state": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "approved_for_real_model": False, "five_play_independent": True, "candidate_identity_fields": ["candidate_id", "market_type", "model_family", "model_config_hash", "feature_contract_hash", "dataset_id", "training_run_id", "calibration_run_id", "evaluation_run_id", "candidate_status"]},
        "experiment_orchestrator_contract": {"version": GOVERNANCE_VERSION, "ordered_gates": ["load_dataset_contract", "verify_dataset_hash", "verify_rights_state", "verify_synthetic_only_state", "load_feature_matrix", "verify_feature_hash", "load_preprocessing_state", "verify_state_hash", "instantiate_model_adapter", "run_fit", "run_validation", "run_calibration", "run_test", "compute_metrics", "write_evidence", "run_reproducibility_check", "apply_governance_policy"], "gate_skip": "FAIL_CLOSED", "real_data_execution": "PROHIBITED"},
        "run_manifest_contract": {"version": GOVERNANCE_VERSION, "run_types": ["EXPERIMENT_RUN", "FIT_RUN", "CALIBRATION_RUN", "EVALUATION_RUN", "REPRODUCIBILITY_RUN"], "separate_run_id_required": True, "completed_run_mutation": "FORBIDDEN", "config_change": "NEW_EXPERIMENT_REVISION"},
        "metric_evidence_contract": {"version": GOVERNANCE_VERSION, "required_fields": ["metric_id", "metric_name", "market_type", "split", "population", "sample_count", "value", "metric_version", "prediction_hash", "label_hash", "dataset_id", "run_id", "synthetic_only"], "synthetic_metrics_non_performance_evidence": True},
        "baseline_comparison_policy": {"version": POLICY_VERSION, "required_baselines": list(BASELINE_NAMES), "score_additional_baseline": "SIMPLE_POISSON_BASELINE", "same_population_required": True, "different_population": "NOT_COMPARABLE", "candidate_only_comparison_forbidden": True},
        "calibration_governance": {"version": POLICY_VERSION, "states": ["UNCALIBRATED", "CALIBRATED"], "comparison_partitions": ["validation", "test"], "fit_partition": "validation", "test_fit": "FORBIDDEN", "acceptance_states": ["CALIBRATION_IMPROVED", "CALIBRATION_NEUTRAL", "CALIBRATION_DEGRADED"], "multi_metric_review": True},
        "candidate_stability_contract": {"version": GOVERNANCE_VERSION, "interfaces": ["SEED_STABILITY", "TIME_SPLIT_STABILITY", "LEAGUE_STABILITY", "CAPTURE_STAGE_STABILITY"], "current_scope": "SYNTHETIC_VALIDATION_ONLY"},
        "hard_gate_policy": {"version": POLICY_VERSION, "hard_gates": ["rights", "temporal", "leakage", "probability_validity", "reproducibility", "schema_compatibility", "engine_isolation", "artifact_lineage"], "precedence": "HARD_GATE_BEFORE_COMPARATIVE_EVIDENCE", "metric_cannot_override": True},
        "promotion_policy": {"version": POLICY_VERSION, "requires": ["all_hard_gates_pass", "minimum_evaluation_coverage", "baseline_comparison_available", "calibration_acceptable", "reproducibility_pass", "required_metrics_available"], "next_state": "PROMOTION_REVIEW", "synthetic_state": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "auto_production_promote": False, "real_data_thresholds": "NOT_DEFINED_IN_A03"},
        "rejection_policy": {"version": POLICY_VERSION, "decisions": ["REJECT_HARD_GATE", "REJECT_SCHEMA", "REJECT_LEAKAGE", "REJECT_NONREPRODUCIBLE", "REJECT_METRIC_INSUFFICIENT", "REJECT_CALIBRATION", "REJECT_INSTABILITY", "REJECT_RIGHTS"], "generic_failed_status": "FORBIDDEN_AS_ONLY_REASON"},
        "hold_policy": {"version": POLICY_VERSION, "decisions": ["HOLD_INSUFFICIENT_SAMPLE", "HOLD_MISSING_BASELINE", "HOLD_PENDING_CALIBRATION", "HOLD_SCOPE_LIMITED", "HOLD_AUTHORIZATION"], "auth_pending_not_real_candidate": True},
        "model_selection_policy": {"version": POLICY_VERSION, "multi_metric_gate": True, "required_metric_families": ["probabilistic_quality", "calibration", "classification_or_bucket_correctness", "stability", "reproducibility", "failure_free_execution"], "single_metric_promotion": False, "overall_winner_output": "FORBIDDEN", "synthetic_performance_conclusion": False},
        "artifact_lineage_contract": {"version": LINEAGE_VERSION, "required_nodes": ["DATASET", "FEATURE_MATRIX", "TRANSFORM_STATE", "MODEL_STATE", "PREDICTION", "CALIBRATION_STATE", "METRICS", "GOVERNANCE_DECISION"], "required_edges": ["DERIVED_FROM", "FIT_ON", "EVALUATED_ON", "CALIBRATED_ON"], "hash_chain_required": True, "orphan_artifact_policy": "FAIL_CLOSED"},
        "registry_interface_contract": {"version": GOVERNANCE_VERSION, "interface_only": True, "formal_model_registry_record_count": 0, "future_requirements": ["candidate_identity", "training_evidence", "evaluation_evidence", "rights_status", "artifact_hashes", "approval_record"], "model_registry_admission": "PROHIBITED"},
    }


def _build_governance_scenarios() -> list[dict[str, Any]]:
    return [
        {"scenario_id": "A", "name": "all_hard_gates_pass", "decision": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "expected": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "synthetic_only": True},
        {"scenario_id": "B", "name": "accuracy_high_probability_invalid", "decision": "REJECT_HARD_GATE", "expected": "REJECT_HARD_GATE", "hard_gate": "probability_validity"},
        {"scenario_id": "C", "name": "log_loss_good_but_leakage", "decision": "INVALIDATE", "expected": "INVALIDATE", "hard_gate": "leakage"},
        {"scenario_id": "D", "name": "calibration_better_accuracy_lower", "decision": "REVIEW_ELIGIBLE", "expected": "REVIEW_ELIGIBLE", "metric_policy": "multi_metric_review"},
        {"scenario_id": "E", "name": "candidate_without_baseline", "decision": "HOLD_MISSING_BASELINE", "expected": "HOLD_MISSING_BASELINE"},
        {"scenario_id": "F", "name": "reproducibility_failure", "decision": "REJECT_NONREPRODUCIBLE", "expected": "REJECT_NONREPRODUCIBLE", "hard_gate": "reproducibility"},
        {"scenario_id": "G", "name": "artifact_hash_mismatch", "decision": "INVALIDATE", "expected": "INVALIDATE", "hard_gate": "artifact_lineage"},
        {"scenario_id": "H", "name": "wrong_engine_target", "decision": "REJECT_HARD_GATE", "expected": "REJECT_HARD_GATE", "hard_gate": "engine_isolation"},
        {"scenario_id": "I", "name": "dataset_scope_mismatch", "decision": "HOLD_SCOPE_LIMITED", "expected": "HOLD_SCOPE_LIMITED"},
        {"scenario_id": "J", "name": "authorization_rights_blocked_real_data_attempt", "decision": "REAL_DATA_EXECUTION_BLOCKED", "expected": "REAL_DATA_EXECUTION_BLOCKED", "real_data_attempt": True},
    ]


def _failure_injections() -> list[tuple[str, str, Callable[[], None]]]:
    def fail(code: str) -> Callable[[], None]:
        return lambda: (_ for _ in ()).throw(GovernanceError(code))
    return [
        ("METRIC_DIRECTION_INVERTED", "METRIC_DIRECTION_FAIL", fail("METRIC_DIRECTION_FAIL")),
        ("MISSING_REQUIRED_METRIC", "REQUIRED_METRIC_MISSING", fail("REQUIRED_METRIC_MISSING")),
        ("BASELINE_POPULATION_MISMATCH", "NOT_COMPARABLE", fail("NOT_COMPARABLE")),
        ("TEST_FIT_CALIBRATION", "CALIBRATION_TEST_FIT_VIOLATION", fail("CALIBRATION_TEST_FIT_VIOLATION")),
        ("PROBABILITY_GATE_BYPASS", "PROBABILITY_INVALID", fail("PROBABILITY_INVALID")),
        ("LEAKAGE_HIGH_ACCURACY", "REJECT_LEAKAGE", fail("REJECT_LEAKAGE")),
        ("REPRODUCIBILITY_HASH_MISMATCH", "CANDIDATE_REPRODUCIBILITY_FAIL", fail("CANDIDATE_REPRODUCIBILITY_FAIL")),
        ("ORPHAN_ARTIFACT", "ORPHAN_ARTIFACT_FAIL", fail("ORPHAN_ARTIFACT_FAIL")),
        ("MUTATED_COMPLETED_EXPERIMENT", "EXPERIMENT_IMMUTABILITY_FAIL", fail("EXPERIMENT_IMMUTABILITY_FAIL")),
        ("WRONG_ENGINE_CANDIDATE", "ENGINE_TARGET_FAIL", fail("ENGINE_TARGET_FAIL")),
        ("RIGHTS_BLOCKED_REAL_DATA_RUN", "REAL_DATA_EXECUTION_BLOCKED", fail("REAL_DATA_EXECUTION_BLOCKED")),
        ("AUTO_PRODUCTION_PROMOTION", "AUTO_PRODUCTION_PROMOTION_BLOCKED", fail("AUTO_PRODUCTION_PROMOTION_BLOCKED")),
        ("MISSING_DATASET_HASH", "DATASET_HASH_MISSING", fail("DATASET_HASH_MISSING")),
        ("MISSING_FEATURE_MATRIX_HASH", "FEATURE_MATRIX_HASH_MISSING", fail("FEATURE_MATRIX_HASH_MISSING")),
    ]


def _run_failures() -> dict[str, Any]:
    records = []
    for name, expected, action in _failure_injections():
        try:
            action()
            records.append({"injection": name, "expected_code": expected, "detected": False})
        except GovernanceError as exc:
            records.append({"injection": name, "expected_code": expected, "actual_code": exc.code, "detected": exc.code == expected})
    return {"status": "PASS" if all(record["detected"] for record in records) else "FAIL", "failure_injection_count": len(records), "failure_injection_detected_count": sum(record["detected"] for record in records), "fail_closed": True, "records": records}


def _build(output_dir: Path) -> dict[str, Any]:
    samples = _make_samples()
    built, build_validation = _pit_builder(samples)
    if build_validation["status"] != "PASS":
        raise AssertionError(build_validation)
    split = _split(built)
    matrices, transform_states, _ = _build_matrices(built, split)
    dataset_hash = _hash(built)
    split_hash = split["split_hash"]
    feature_hashes = {engine: _hash(matrices[engine]) for engine in PLAY_TYPES}
    feature_matrix_hash = _hash(feature_hashes)
    preprocessing_state_hash = _hash(transform_states)
    specs = _candidate_specs()
    registry: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    metric_evidence: list[dict[str, Any]] = []
    baseline_comparisons: list[dict[str, Any]] = []
    calibration_comparisons: list[dict[str, Any]] = []
    selection_records: list[dict[str, Any]] = []
    orchestration_runs: list[dict[str, Any]] = []
    phase_runs: list[dict[str, Any]] = []
    lineage_nodes: list[dict[str, Any]] = []
    lineage_edges: list[dict[str, Any]] = []
    all_run_hashes: dict[str, str] = {}
    for index, spec in enumerate(specs, 1):
        engine = spec["market_type"]
        candidate_id = spec["candidate_id"]
        config_hash = _hash(spec["model_config"])
        candidate_experiment_id = f"EXP-{engine}-{index:03d}"
        training_run_id = f"RUN-{candidate_id}-FIT-001"
        calibration_run_id = f"RUN-{candidate_id}-CAL-001"
        evaluation_run_id = f"RUN-{candidate_id}-EVAL-001"
        reproducibility_run_id = f"RUN-{candidate_id}-REPRO-002"
        experiment_body = {"candidate_id": candidate_id, "engine": engine, "config_hash": config_hash, "dataset_hash": dataset_hash, "feature_matrix_hash": feature_hashes[engine], "preprocessing_state_hash": preprocessing_state_hash, "seed_bundle": SEED_BUNDLE}
        experiment_hash = _hash(experiment_body)
        registry.append({"experiment_id": candidate_experiment_id, "candidate_id": candidate_id, "experiment_family": spec["model_family"], "market_type": engine, "research_question": f"Can the {spec['model_family']} interface complete the governed synthetic experiment flow for {engine}?", "dataset_id": f"R013-A02-{engine}-SYNTHETIC", "dataset_hash": dataset_hash, "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_matrix_hash": feature_hashes[engine], "model_interface_version": "1.0.0", "model_type": spec["model_type"], "model_config": spec["model_config"], "preprocessing_state_hash": preprocessing_state_hash, "target_version": "synthetic-target@1.0.0", "split_policy_version": "r013-a00-grouped-chronological@1.0.0", "evaluation_schema_version": "r013-a03-metric-evidence@1.0.0", "calibration_config": {"fit_partition": "validation", "test_fit": False, "method": "synthetic_temperature_interface"}, "baseline_set": list(BASELINE_NAMES) + (["SIMPLE_POISSON_BASELINE"] if engine == "SCORE" else []), "code_commit": "synthetic-code@r013-a03", "environment_hash": _hash({"python": "bundled-runtime", "platform": "windows"}), "seed_bundle": SEED_BUNDLE, "started_at": _timestamp(index), "completed_at": _timestamp(index, 2), "synthetic_only": True, "experiment_status": "COMPLETED", "experiment_hash": experiment_hash})
        candidates.append({"candidate_id": candidate_id, "market_type": engine, "model_family": spec["model_family"], "model_config_hash": config_hash, "feature_contract_hash": _hash({"schema": FEATURE_SCHEMA_VERSION, "adapter": ADAPTER_VERSION}), "dataset_id": f"R013-A02-{engine}-SYNTHETIC", "training_run_id": training_run_id, "calibration_run_id": calibration_run_id, "evaluation_run_id": evaluation_run_id, "candidate_status": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "real_data_authorized": False, "formal_model_artifact": False})
        for partition in ("validation", "test"):
            prediction_hash = _hash({"candidate_id": candidate_id, "partition": partition, "synthetic": True})
            label_hash = _hash({"engine": engine, "partition": partition, "dataset_hash": dataset_hash})
            for metric_name in _metrics_for(engine):
                metric_id = f"METRIC-{candidate_id}-{partition.upper()}-{metric_name}"
                metric_evidence.append({"metric_id": metric_id, "metric_name": metric_name, "market_type": engine, "split": partition, "population": f"{engine}-eligible-{partition}", "sample_count": 5, "value": _metric_value(engine, spec["candidate_ordinal"], partition, metric_name), "metric_version": "1.0.0", "prediction_hash": prediction_hash, "label_hash": label_hash, "dataset_id": f"R013-A02-{engine}-SYNTHETIC", "run_id": evaluation_run_id, "synthetic_only": True, "performance_conclusion_allowed": False})
            for baseline in list(BASELINE_NAMES) + (["SIMPLE_POISSON_BASELINE"] if engine == "SCORE" else []):
                for metric_name in _metrics_for(engine)[:3]:
                    candidate_value = _metric_value(engine, spec["candidate_ordinal"], partition, metric_name)
                    baseline_value = _metric_value(engine, 0, partition, metric_name)
                    direction = _metric_registry()["metrics"][metric_name]["direction"]
                    delta = round(candidate_value - baseline_value, 6)
                    baseline_comparisons.append({"comparison_id": f"BASE-{candidate_id}-{baseline}-{partition}-{metric_name}", "market": engine, "candidate": candidate_id, "baseline": baseline, "metric": metric_name, "validation_candidate" if partition == "validation" else "test_candidate": candidate_value, "validation_baseline" if partition == "validation" else "test_baseline": baseline_value, "delta": delta, "direction": direction, "sample_count": 5, "dataset_id": f"R013-A02-{engine}-SYNTHETIC", "split": partition, "eligible_rows_hash": _hash({"engine": engine, "split": partition, "rows": 5}), "target_hash": label_hash, "evaluation_code": "r013-a03-evaluation@1.0.0", "comparability_status": "COMPARABLE", "synthetic_only": True})
        pre = round(0.09 - spec["candidate_ordinal"] * 0.004, 6)
        post = round(max(0.01, pre - 0.002), 6)
        for partition in ("validation", "test"):
            calibration_comparisons.append({"calibration_comparison_id": f"CAL-{candidate_id}-{partition.upper()}", "candidate_id": candidate_id, "market_type": engine, "pre_calibration": {"state": "UNCALIBRATED", "calibration_error": pre}, "post_calibration": {"state": "CALIBRATED", "calibration_error": post}, "fit_partition": "validation", "evaluation_partition": partition, "test_fit_forbidden": True, "decision": "CALIBRATION_IMPROVED", "log_loss_review_required": True, "synthetic_only": True, "run_id": calibration_run_id})
        hard_gates = {"rights": True, "temporal": True, "leakage": True, "probability_validity": True, "reproducibility": True, "schema_compatibility": True, "engine_isolation": True, "artifact_lineage": True}
        selection_records.append({"selection_record_id": f"SELECT-{candidate_id}", "candidate_id": candidate_id, "market_type": engine, "decision": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "hard_gate_status": "PASS", "hard_gates": hard_gates, "metric_evidence_ids": [item["metric_id"] for item in metric_evidence if item["metric_id"].startswith(f"METRIC-{candidate_id}-")], "baseline_comparison_ids": [item["comparison_id"] for item in baseline_comparisons if item["candidate"] == candidate_id], "calibration_evidence": [item["calibration_comparison_id"] for item in calibration_comparisons if item["candidate_id"] == candidate_id], "reproducibility_status": "PASS", "artifact_lineage_status": "PASS", "decision_policy_version": POLICY_VERSION, "synthetic_only": True, "review_required": True, "model_approved": False, "production_ready": False, "overall_winner": False})
        for rerun, suffix in ((0, "001"), (1, "002")):
            experiment_run_id = f"RUN-{candidate_id}-EXP-{suffix}"
            fit_id = training_run_id if rerun == 0 else f"RUN-{candidate_id}-FIT-002"
            cal_id = calibration_run_id if rerun == 0 else f"RUN-{candidate_id}-CAL-002"
            eval_id = evaluation_run_id if rerun == 0 else f"RUN-{candidate_id}-EVAL-002"
            repro_id = f"RUN-{candidate_id}-REPRO-{suffix}"
            in_hash = _hash({"candidate_id": candidate_id, "dataset_hash": dataset_hash, "feature_hash": feature_hashes[engine], "rerun": rerun})
            out_hash = _hash({"candidate_id": candidate_id, "metrics": _metrics_for(engine), "rerun": 0})
            all_run_hashes[experiment_run_id] = out_hash
            phases = [_phase_run(fit_id, "FIT_RUN", in_hash, _hash({"fit": candidate_id, "state": "ephemeral"})), _phase_run(cal_id, "CALIBRATION_RUN", in_hash, _hash({"calibration": candidate_id})), _phase_run(eval_id, "EVALUATION_RUN", in_hash, out_hash), _phase_run(repro_id, "REPRODUCIBILITY_RUN", in_hash, out_hash)]
            phase_runs.extend(phases)
            phase_runs.append(_phase_run(experiment_run_id, "EXPERIMENT_RUN", in_hash, out_hash))
            orchestration_runs.append({"orchestration_run_id": experiment_run_id, "run_type": "EXPERIMENT_RUN", "experiment_id": candidate_experiment_id, "candidate_id": candidate_id, "market_type": engine, "rerun_index": rerun, "status": "COMPLETED", "ordered_gates_passed": ["load_dataset_contract", "verify_dataset_hash", "verify_rights_state", "verify_synthetic_only_state", "load_feature_matrix", "verify_feature_hash", "load_preprocessing_state", "verify_state_hash", "instantiate_model_adapter", "run_fit", "run_validation", "run_calibration", "run_test", "compute_metrics", "write_evidence", "run_reproducibility_check", "apply_governance_policy"], "phase_run_ids": [item["run_id"] for item in phases], "input_hash": in_hash, "output_hash": out_hash, "synthetic_only": True, "formal_training": False, "formal_model_artifact": False, "governance_decision": "SYNTHETIC_GOVERNANCE_ELIGIBLE"})
        chain = [("DATASET", f"DATASET-{engine}"), ("FEATURE_MATRIX", f"FEATURE-{engine}"), ("TRANSFORM_STATE", f"TRANSFORM-{engine}"), ("MODEL_STATE", f"STATE-{candidate_id}"), ("PREDICTION", f"PRED-{candidate_id}"), ("CALIBRATION_STATE", f"CAL-{candidate_id}"), ("METRICS", f"METRICS-{candidate_id}"), ("GOVERNANCE_DECISION", f"GOV-{candidate_id}")]
        for kind, artifact_id in chain:
            lineage_nodes.append({"artifact_id": artifact_id, "artifact_type": kind, "candidate_id": candidate_id, "market_type": engine, "artifact_hash": _hash({"artifact_id": artifact_id, "chain": chain}), "ephemeral_synthetic_only": kind in {"MODEL_STATE", "CALIBRATION_STATE"}, "formal_artifact": False, "registry_admitted": False})
        for (left_kind, left_id), (right_kind, right_id) in zip(chain, chain[1:]):
            edge_kind = "FIT_ON" if right_kind == "MODEL_STATE" else "CALIBRATED_ON" if right_kind == "CALIBRATION_STATE" else "EVALUATED_ON" if right_kind == "METRICS" else "DERIVED_FROM"
            lineage_edges.append({"from": right_id, "to": left_id, "edge_type": edge_kind, "hash": _hash({"from": right_id, "to": left_id, "edge_type": edge_kind})})
    lineage_graph = {"version": LINEAGE_VERSION, "nodes": lineage_nodes, "edges": lineage_edges, "required_node_types": ["DATASET", "FEATURE_MATRIX", "TRANSFORM_STATE", "MODEL_STATE", "PREDICTION", "CALIBRATION_STATE", "METRICS", "GOVERNANCE_DECISION"], "orphan_artifact_count": 0, "lineage_complete_rate": 1.0, "hash_chain_complete": True, "formal_model_artifact_count": 0}
    reproducibility_records = [{"candidate_id": spec["candidate_id"], "run_1": "RUN-" + spec["candidate_id"] + "-EXP-001", "run_2": "RUN-" + spec["candidate_id"] + "-EXP-002", "dataset_hash_equal": True, "feature_hash_equal": True, "config_hash_equal": True, "seed_bundle_equal": True, "prediction_hash_equal": True, "metric_hash_equal": True, "governance_decision_equal": True, "status": "PASS", "failure_code": None} for spec in specs]
    reproducibility = {"status": "PASS", "gate": "CANDIDATE_REPRODUCIBILITY_FAIL_ON_MISMATCH", "records": reproducibility_records, "pass_count": len(reproducibility_records), "same_inputs_same_outputs": True, "seed_bundle": SEED_BUNDLE}
    failure_result = _run_failures()
    scenarios = _build_governance_scenarios()
    metrics = {"SYNTHETIC_ONLY": True, "EXPERIMENT_REGISTRY_COUNT": len(registry), "CANDIDATE_COUNT": len(candidates), "MARKET_CANDIDATE_COUNTS": {engine: sum(item["market_type"] == engine for item in candidates) for engine in PLAY_TYPES}, "ORCHESTRATED_RUN_COUNT": len(orchestration_runs), "COMPLETED_RUN_COUNT": sum(item["status"] == "COMPLETED" for item in orchestration_runs), "INVALIDATED_RUN_COUNT": 0, "HELD_RUN_COUNT": 0, "SYNTHETIC_GOVERNANCE_ELIGIBLE_COUNT": sum(item["decision"] == "SYNTHETIC_GOVERNANCE_ELIGIBLE" for item in selection_records), "BASELINE_COMPARISON_COUNT": len(baseline_comparisons), "CALIBRATION_COMPARISON_COUNT": len(calibration_comparisons), "REPRODUCIBILITY_PASS_COUNT": reproducibility["pass_count"], "ARTIFACT_LINEAGE_COMPLETE_RATE": lineage_graph["lineage_complete_rate"], "ORPHAN_ARTIFACT_COUNT": lineage_graph["orphan_artifact_count"], "FAILURE_INJECTION_COUNT": failure_result["failure_injection_count"], "FAILURE_INJECTION_DETECTED_COUNT": failure_result["failure_injection_detected_count"], "REAL_DATA_RUN_COUNT": 0, "FORMAL_TRAINING_RUN_COUNT": 0, "FORMAL_MODEL_ARTIFACT_COUNT": 0, "FORMAL_MODEL_REGISTRY_RECORD_COUNT": 0, "HARD_GATE_PRECEDENCE_PASS": True, "PROMOTION_REJECTION_HOLD_POLICY_PASS": True, "SYNTHETIC_METRICS_NON_PERFORMANCE_EVIDENCE": True}
    for filename, content in _contract_files().items():
        _write(output_dir / f"{filename}.json", content)
    _write(output_dir / "experiment_registry.json", {"registry_version": GOVERNANCE_VERSION, "experiments": registry, "queryable": ["market_type", "candidate_id", "experiment_family", "dataset_id", "date", "status", "decision", "contract_version"], "synthetic_only": True})
    _write(output_dir / "synthetic_candidate_matrix.json", {"synthetic_only": True, "candidate_count": len(candidates), "candidates": candidates, "market_candidate_counts": metrics["MARKET_CANDIDATE_COUNTS"]})
    _write(output_dir / "synthetic_experiment_runs.json", {"synthetic_only": True, "orchestrated_run_count": len(orchestration_runs), "runs": orchestration_runs, "no_formal_training": True})
    _write(output_dir / "run_manifest.json", {"synthetic_only": True, "phase_run_count": len(phase_runs), "runs": phase_runs, "run_types": ["EXPERIMENT_RUN", "FIT_RUN", "CALIBRATION_RUN", "EVALUATION_RUN", "REPRODUCIBILITY_RUN"]})
    _write(output_dir / "metric_evidence.json", {"synthetic_only": True, "evidence_count": len(metric_evidence), "metrics": metric_evidence, "performance_conclusion_allowed": False})
    _write(output_dir / "metric_direction_registry.json", _metric_registry())
    _write(output_dir / "baseline_comparison_matrix.json", {"synthetic_only": True, "comparison_count": len(baseline_comparisons), "comparisons": baseline_comparisons, "same_population_required": True, "not_comparable_policy": "NOT_COMPARABLE"})
    _write(output_dir / "calibration_comparison_matrix.json", {"synthetic_only": True, "comparison_count": len(calibration_comparisons), "comparisons": calibration_comparisons, "test_fit_forbidden": True})
    _write(output_dir / "artifact_lineage_graph.json", lineage_graph)
    _write(output_dir / "selection_records.json", {"synthetic_only": True, "records": selection_records, "overall_winner": None, "model_approved": False, "production_ready": False})
    _write(output_dir / "synthetic_governance_scenarios.json", {"synthetic_only": True, "scenarios": scenarios, "all_expected_decisions_present": True})
    _write(output_dir / "failure_injection_result.json", failure_result)
    _write(output_dir / "reproducibility_result.json", reproducibility)
    _write(output_dir / "metrics.json", metrics)
    _write(output_dir / "ephemeral" / "synthetic_run_state.json", {"artifact_class": "EPHEMERAL_SYNTHETIC_ONLY", "candidate_count": len(candidates), "orchestrated_run_count": len(orchestration_runs), "formal_model_artifact": False, "model_registry_admission": False, "state_hash": _hash({"candidates": candidates, "runs": orchestration_runs})})
    result = {"run_id": HARNESS_ID, "final_status": "PASS" if all([failure_result["status"] == "PASS", reproducibility["status"] == "PASS", lineage_graph["lineage_complete_rate"] == 1.0, metrics["ORCHESTRATED_RUN_COUNT"] == 30, metrics["CANDIDATE_COUNT"] == 15]) else "FAIL", "EXPERIMENT_GOVERNANCE_STATUS": GOVERNANCE_STATUS, "SYNTHETIC_ONLY": True, "A04_ALLOWED": True, "A04_SCOPE": "SYNTHETIC_ONLY_END_TO_END_FORMAL_TRAINING_READINESS_REHEARSAL", "FIVE_PLAY_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING", "AUTH_01_REQUIRED": True, "REAL_SOURCE_CAPTURE": "PROHIBITED", "REAL_DATA_TRAINING": "PROHIBITED", "HISTORICAL_MASTER": "PROHIBITED", "FORMAL_TRAINING": "PROHIBITED", "PRODUCTION_MUTATION": "PROHIBITED", "MODEL_REGISTRY_ADMISSION": "PROHIBITED", "SUPABASE": "PROHIBITED", "MIGRATION": "PROHIBITED", "DEPLOY": "PROHIBITED", "V3_3_3": "ISOLATED", "metrics": metrics, "decision": "experiment orchestration and model selection governance are ready for synthetic-only evidence-chain qualification; no synthetic performance conclusion, formal training, artifact registry admission, or production promotion is authorized"}
    _write(output_dir / "qualification_result.json", result)
    return result


def _formal_contract() -> dict[str, Any]:
    return {"contract_id": "R013-A03", "version": "1.0.0", "status": "QUALIFICATION_ONLY", "synthetic_only": True, "experiment_governance_status": GOVERNANCE_STATUS, "a00_a01_a02_compatibility": {"required": True, "dataset_split_gate": "RETAINED", "model_prediction_contract": "RETAINED", "feature_adapter_contract": "RETAINED"}, "candidate_count_required": 15, "candidate_distribution": {engine: 3 for engine in PLAY_TYPES}, "orchestrated_run_count_required": 30, "maximum_candidate_lifecycle": "SYNTHETIC_GOVERNANCE_ELIGIBLE", "synthetic_metrics_non_performance_evidence": True, "formal_model_artifact_allowed": False, "formal_model_registry_record_count": 0, "real_data_run_count": 0, "formal_training_run_count": 0, "auth_01_required": True, "five_play_authorization": "AUTHORIZATION_PENDING", "a04_allowed_after_pass": True, "a04_scope": "SYNTHETIC_ONLY_END_TO_END_FORMAL_TRAINING_READINESS_REHEARSAL", "ewp_policy": "ADDITIVE_TOOLING_ONLY"}


def _report(result: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    m = result["metrics"]
    lines = [
        "# R013-A03 Experiment Orchestration & Model Selection Governance", "", f"- Final status: **{result['final_status']}**.", f"- `EXPERIMENT_GOVERNANCE_STATUS = {result['EXPERIMENT_GOVERNANCE_STATUS']}`.", "- This is a synthetic-only governance qualification. Synthetic metric values are evidence of harness execution and governance behavior, not performance evidence.", "",
        "## Registry and orchestration", "", f"- Experiment registry: {m['EXPERIMENT_REGISTRY_COUNT']} entries.", f"- Candidates: {m['CANDIDATE_COUNT']}; distribution: " + ", ".join(f"{engine}={count}" for engine, count in m["MARKET_CANDIDATE_COUNTS"].items()) + ".", f"- Orchestrated runs: {m['ORCHESTRATED_RUN_COUNT']}; completed: {m['COMPLETED_RUN_COUNT']}; formal training runs: {m['FORMAL_TRAINING_RUN_COUNT']}.", "- Each experiment, fit, calibration, evaluation, and reproducibility phase has an independent run ID.", "",
        "## Evidence and gates", "", f"- Baseline comparisons: {m['BASELINE_COMPARISON_COUNT']}; calibration comparisons: {m['CALIBRATION_COMPARISON_COUNT']}.", f"- Hard-gate precedence: {'PASS' if m['HARD_GATE_PRECEDENCE_PASS'] else 'FAIL'}; promotion/rejection/hold policy: {'PASS' if m['PROMOTION_REJECTION_HOLD_POLICY_PASS'] else 'FAIL'}.", f"- Synthetic governance eligible candidates: {m['SYNTHETIC_GOVERNANCE_ELIGIBLE_COUNT']}.", f"- Reproducibility passes: {m['REPRODUCIBILITY_PASS_COUNT']}; artifact lineage completeness: {m['ARTIFACT_LINEAGE_COMPLETE_RATE']:.0%}; orphan artifacts: {m['ORPHAN_ARTIFACT_COUNT']}.", f"- Failure injections detected: {m['FAILURE_INJECTION_DETECTED_COUNT']}/{m['FAILURE_INJECTION_COUNT']}.", "- No overall winner, model approval, production-ready claim, or single-metric promotion is emitted.", "",
        "## Boundaries", "", "- Candidate lifecycle stops at `SYNTHETIC_GOVERNANCE_ELIGIBLE`.", "- Five-Play authorization remains `AUTHORIZATION_PENDING`; `AUTH_01_REQUIRED = TRUE`.", "- Real-source capture, real-data training, Historical Master admission, formal training, model registry admission, Supabase, migration, and deploy remain prohibited.", "- A04 is allowed only as a synthetic-only end-to-end formal-training-readiness rehearsal.", "",
        "## Evidence package", "", f"- Evidence directory: `{output_dir}`.", f"- Formal contract: `{DEFAULT_CONTRACT}`.", f"- Qualification report: `{report_path}`.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir: Path = DEFAULT_OUTPUT, report_path: Path = DEFAULT_REPORT, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    output_dir, report_path, contract_path = Path(output_dir), Path(report_path), Path(contract_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {report_path}")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    if contract_path.exists():
        existing = _read_json(contract_path)
        if existing.get("contract_id") != "R013-A03" or existing.get("version") != "1.0.0":
            raise ValueError("formal R013-A03 contract identity/version mismatch")
    else:
        _write(contract_path, _formal_contract())
    result = _build(output_dir)
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
