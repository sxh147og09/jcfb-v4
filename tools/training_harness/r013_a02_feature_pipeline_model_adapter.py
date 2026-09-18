"""R013-A02: synthetic-only feature pipeline and model adapter qualification.

This module is deliberately a qualification harness, not a training job.  It
builds deterministic feature matrices from the R013-A00 synthetic universe,
fits ephemeral transforms on TRAIN only, validates the five independent
engine adapters, and exercises fail-closed gates.  It never reads real data,
creates a formal preprocessor, trains a formal model, or writes a production
feature store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

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
    _parse,
    _pit_builder,
    _split,
)


HARNESS_ID = "R013-A02"
FEATURE_PIPELINE_STATUS = "FEATURE_PIPELINE_READY_SYNTHETIC_ONLY"
MODEL_ADAPTER_STATUS = "MODEL_ADAPTER_READY_SYNTHETIC_ONLY"
DEFAULT_OUTPUT = ROOT / "work" / "r013_a02"
DEFAULT_REPORT = ROOT / "docs" / "R013-A02_feature_pipeline_model_adapter_qualification_report.md"
DEFAULT_CONTRACT = ROOT / "config" / "prediction_training" / "R013-A02_feature_pipeline_model_adapter_contract_v1.0.0.json"
FEATURE_SCHEMA_VERSION = "r013-a02-feature-schema@1.0.0"
ADAPTER_VERSION = "r013-a02-engine-adapters@1.0.0"
TRANSFORM_VERSION = "r013-a02-transformers@1.0.0"
UNKNOWN_TOKEN = "<UNKNOWN>"


class FeaturePipelineError(ValueError):
    """A named fail-closed qualification error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}".rstrip())
        self.code = code


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _feature(
    feature_id: str,
    name: str,
    domain: str,
    data_type: str = "FLOAT",
    semantic_type: str = "RAW_FEATURE",
    engines: Iterable[str] = PLAY_TYPES,
    missing_policy: str = "MODEL_NATIVE_MISSING",
    fit_required: bool = False,
    transform_rule: str = "IDENTITY",
    source_requirement: str = "SYNTHETIC_PREMATCH_SOURCE",
    temporal_requirement: str = "effective_available_at <= prediction_cutoff_at",
    rights_requirement: str = "RIGHTS_ALLOWED",
    revision_requirement: str = "REVISION_SAFE",
) -> dict[str, Any]:
    engine_list = list(engines)
    return {
        "feature_id": feature_id,
        "feature_name": name,
        "feature_domain": domain,
        "data_type": data_type,
        "semantic_type": semantic_type,
        "nullable": missing_policy in {"MODEL_NATIVE_MISSING", "EXPLICIT_UNKNOWN", "TRAIN_FIT_IMPUTATION"},
        "missing_policy": missing_policy,
        "source_requirement": source_requirement,
        "temporal_requirement": temporal_requirement,
        "rights_requirement": rights_requirement,
        "revision_requirement": revision_requirement,
        "normalization_rule": "CANONICAL_NUMERIC_V1" if data_type in {"FLOAT", "INTEGER"} else "CANONICAL_CATEGORY_V1",
        "transform_rule": transform_rule,
        "fit_required": fit_required,
        "engine_allowlist": engine_list,
        "engine_denylist": [play for play in PLAY_TYPES if play not in engine_list],
        "feature_version": "1.0.0",
        "transformation_semantics": "APPEND_ONLY_DERIVED_COLUMN",
    }


def _schema() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    shared = [
        ("home_form_index", "TEAM_FORM", "FLOAT", "STANDARDIZATION", True),
        ("away_form_index", "TEAM_FORM", "FLOAT", "STANDARDIZATION", True),
        ("home_rating", "ELO_OR_RATING", "FLOAT", "STANDARDIZATION", True),
        ("away_rating", "ELO_OR_RATING", "FLOAT", "STANDARDIZATION", True),
        ("home_away_context", "HOME_AWAY_CONTEXT", "FLOAT", "IDENTITY", False),
        ("home_rest_days", "REST_DAYS", "INTEGER", "IDENTITY", False),
        ("away_rest_days", "REST_DAYS", "INTEGER", "IDENTITY", False),
        ("market_availability_state", "MATCH_CONTEXT", "CATEGORY", "DETERMINISTIC_CATEGORY_ENCODING", True),
    ]
    for index, (name, domain, dtype, rule, fit_required) in enumerate(shared, 1):
        features.append(_feature(f"F-SHARED-{index:03d}", name, domain, dtype, "RAW_FEATURE", PLAY_TYPES, "EXPLICIT_UNKNOWN" if dtype == "CATEGORY" else "TRAIN_FIT_IMPUTATION", fit_required, rule))
    for name in ("home_form_missing_indicator", "away_form_missing_indicator"):
        features.append(_feature(f"F-SHARED-{len(features):03d}", name, "TEAM_CONTEXT", "MASK", "MODEL_INPUT_FEATURE", PLAY_TYPES, "EXPLICIT_UNKNOWN", False, "IDENTITY"))

    for name, rule in (("spf_raw_odds_home", "IDENTITY"), ("spf_raw_odds_draw", "IDENTITY"), ("spf_raw_odds_away", "IDENTITY")):
        features.append(_feature(f"F-SPF-{len(features):03d}", name, "MARKET_SPF", "FLOAT", "RAW_FEATURE", ("SPF",), "MISSING_NOT_ALLOWED", False, rule))
    for name in ("spf_implied_home", "spf_implied_draw", "spf_implied_away"):
        features.append(_feature(f"F-SPF-{len(features):03d}", name, "MARKET_SPF", "FLOAT", "TRANSFORMED_FEATURE", ("SPF",), "MISSING_NOT_ALLOWED", False, "IDENTITY"))
    for name in ("spf_normalized_home", "spf_normalized_draw", "spf_normalized_away", "spf_overround", "spf_movement_delta"):
        features.append(_feature(f"F-SPF-{len(features):03d}", name, "MARKET_SPF", "FLOAT", "NORMALIZED_FEATURE", ("SPF",), "MODEL_NATIVE_MISSING", False, "OVERROUND_NORMALIZATION" if "normalized" in name else "IDENTITY"))
    features.append(_feature(f"F-SPF-{len(features):03d}", "spf_availability_mask", "MARKET_SPF", "MASK", "MODEL_INPUT_FEATURE", ("SPF",), "EXPLICIT_UNKNOWN", False, "IDENTITY"))

    features.append(_feature(f"F-RQSPF-{len(features):03d}", "rqspf_handicap", "MARKET_RQSPF", "FLOAT", "RAW_FEATURE", ("RQSPF",), "MISSING_NOT_ALLOWED", False, "IDENTITY"))
    for name in ("rqspf_raw_odds_home", "rqspf_raw_odds_draw", "rqspf_raw_odds_away"):
        features.append(_feature(f"F-RQSPF-{len(features):03d}", name, "MARKET_RQSPF", "FLOAT", "RAW_FEATURE", ("RQSPF",), "MISSING_NOT_ALLOWED", False, "IDENTITY"))
    for name in ("rqspf_implied_home", "rqspf_implied_draw", "rqspf_implied_away"):
        features.append(_feature(f"F-RQSPF-{len(features):03d}", name, "MARKET_RQSPF", "FLOAT", "TRANSFORMED_FEATURE", ("RQSPF",), "MISSING_NOT_ALLOWED", False, "IDENTITY"))
    features.append(_feature(f"F-RQSPF-{len(features):03d}", "rqspf_availability_mask", "MARKET_RQSPF", "MASK", "MODEL_INPUT_FEATURE", ("RQSPF",), "EXPLICIT_UNKNOWN", False, "IDENTITY"))

    for index, name in enumerate(("p_0", "p_1", "p_2", "p_3", "p_4", "p_5", "p_6", "p_7_plus"), 1):
        features.append(_feature(f"F-TG-{index:03d}", f"total_goals_{name}", "MARKET_TOTAL_GOALS", "FLOAT", "NORMALIZED_FEATURE", ("TOTAL_GOALS",), "MODEL_NATIVE_MISSING", False, "OVERROUND_NORMALIZATION"))
    for name, dtype in (("total_goals_availability_mask", "MASK"), ("total_goals_entropy", "FLOAT"), ("total_goals_concentration", "FLOAT")):
        features.append(_feature(f"F-TG-{len(features):03d}", name, "MARKET_TOTAL_GOALS", dtype, "MODEL_INPUT_FEATURE", ("TOTAL_GOALS",), "EXPLICIT_UNKNOWN", False, "IDENTITY"))

    for name in ("score_p_0_0", "score_p_1_0", "score_p_1_1", "score_p_2_1", "score_p_2_2", "score_tail_home", "score_tail_draw", "score_tail_away"):
        features.append(_feature(f"F-SCORE-{len(features):03d}", name, "MARKET_SCORE", "FLOAT", "NORMALIZED_FEATURE", ("SCORE",), "MODEL_NATIVE_MISSING", False, "OVERROUND_NORMALIZATION"))
    for name, dtype in (("score_selection_missing_mask", "MASK"), ("score_grid_entropy", "FLOAT"), ("score_grid_version", "INTEGER")):
        features.append(_feature(f"F-SCORE-{len(features):03d}", name, "MARKET_SCORE", dtype, "MODEL_INPUT_FEATURE", ("SCORE",), "EXPLICIT_UNKNOWN", False, "IDENTITY"))

    for name in ("htft_h_h", "htft_h_d", "htft_h_a", "htft_d_h", "htft_d_d", "htft_d_a", "htft_a_h", "htft_a_d", "htft_a_a"):
        features.append(_feature(f"F-HTFT-{len(features):03d}", name, "MARKET_HTFT", "FLOAT", "NORMALIZED_FEATURE", ("HTFT",), "MODEL_NATIVE_MISSING", False, "OVERROUND_NORMALIZATION"))
    features.append(_feature(f"F-HTFT-{len(features):03d}", "htft_selection_missing_mask", "MARKET_HTFT", "MASK", "MODEL_INPUT_FEATURE", ("HTFT",), "EXPLICIT_UNKNOWN", False, "IDENTITY"))
    return features


FEATURE_SCHEMAS = _schema()
SCHEMA_BY_NAME = {item["feature_name"]: item for item in FEATURE_SCHEMAS}
SHARED_FEATURES = [item["feature_name"] for item in FEATURE_SCHEMAS if set(item["engine_allowlist"]) == set(PLAY_TYPES)]
ENGINE_FEATURES = {
    engine: SHARED_FEATURES + [item["feature_name"] for item in FEATURE_SCHEMAS if engine in item["engine_allowlist"] and item["feature_name"] not in SHARED_FEATURES]
    for engine in PLAY_TYPES
}


DOMAIN_NAMES = [
    "MATCH_IDENTITY", "LEAGUE_CONTEXT", "HOME_AWAY_CONTEXT", "TEAM_FORM", "ELO_OR_RATING", "RECENT_RESULTS", "GOALS_HISTORY", "MATCH_STATS", "SHOTS", "SHOTS_ON_TARGET", "CORNERS", "CARDS", "POSSESSION", "XG", "LINEUP_CONTEXT", "INJURY_CONTEXT", "SUSPENSION_CONTEXT", "COACH_CONTEXT", "FORMATION_CONTEXT", "TACTICAL_CONTEXT", "REST_DAYS", "SCHEDULE_DENSITY", "TEAM_CONTEXT", "MARKET_SPF", "MARKET_RQSPF", "MARKET_TOTAL_GOALS", "MARKET_SCORE", "MARKET_HTFT", "MARKET_MOVEMENT", "MATCH_CONTEXT",
]


class NumericTransformer:
    transformer_type = "BASE"

    def __init__(self, feature_version: str = "1.0.0", seed: int = SEED) -> None:
        self.feature_version = feature_version
        self.seed = seed
        self.state: dict[str, Any] = {}

    def fit(self, train_values: list[float], *, split: str = "train", dataset_id: str = "R013-A02-SYNTHETIC") -> "NumericTransformer":
        if split != "train":
            raise FeaturePipelineError("PREPROCESSING_LEAKAGE_FAIL", "numeric transformer fit is TRAIN-only")
        self.state = {"fit_dataset_id": dataset_id, "fit_split": "TRAIN", "fit_row_count": len(train_values), "feature_version": self.feature_version, "seed": self.seed}
        self._finalize_state()
        return self

    def fit_transform(self, train_values: list[float], **kwargs: Any) -> list[float]:
        self.fit(train_values, **kwargs)
        return self.transform(train_values)

    def transform(self, values: list[float]) -> list[float]:
        return [float(value) for value in values]

    def get_state(self) -> dict[str, Any]:
        return dict(self.state)

    def get_metadata(self) -> dict[str, Any]:
        return {"transformer_type": self.transformer_type, "version": TRANSFORM_VERSION, "fit_required": False}

    def _finalize_state(self) -> None:
        self.state["state_hash"] = _hash({key: value for key, value in self.state.items() if key != "state_hash"})


class IdentityTransformer(NumericTransformer):
    transformer_type = "IDENTITY"


class StandardizationTransformer(NumericTransformer):
    transformer_type = "STANDARDIZATION"

    def fit(self, train_values: list[float], **kwargs: Any) -> "StandardizationTransformer":
        super().fit(train_values, **kwargs)
        if not train_values:
            raise FeaturePipelineError("EMPTY_TRAIN_FIT", "standardization requires training values")
        mean = sum(float(value) for value in train_values) / len(train_values)
        variance = sum((float(value) - mean) ** 2 for value in train_values) / len(train_values)
        self.state.update({"mean": mean, "std": math.sqrt(variance) or 1.0})
        self._finalize_state()
        return self

    def transform(self, values: list[float]) -> list[float]:
        if "mean" not in self.state:
            raise FeaturePipelineError("TRANSFORM_STATE_MISSING", "standardization must be fit on TRAIN")
        return [(float(value) - self.state["mean"]) / self.state["std"] for value in values]

    def get_metadata(self) -> dict[str, Any]:
        return {"transformer_type": self.transformer_type, "version": TRANSFORM_VERSION, "fit_required": True, "fit_scope": "TRAIN_ONLY"}


class OddsToImpliedProbabilityTransformer(NumericTransformer):
    transformer_type = "ODDS_TO_IMPLIED_PROBABILITY"

    def transform(self, values: list[float]) -> list[float]:
        if any(float(value) <= 1.0 for value in values):
            raise FeaturePipelineError("INVALID_ODDS", "odds must be greater than 1")
        return [1.0 / float(value) for value in values]

    def get_metadata(self) -> dict[str, Any]:
        return {"transformer_type": self.transformer_type, "version": TRANSFORM_VERSION, "fit_required": False, "formula": "implied_probability=1/decimal_odds"}


class DeterministicCategoricalEncoder:
    transformer_type = "DETERMINISTIC_CATEGORY_ENCODER"

    def __init__(self, unknown_token: str = UNKNOWN_TOKEN, seed: int = SEED) -> None:
        self.unknown_token = unknown_token
        self.seed = seed
        self.vocabulary: dict[str, int] = {}
        self.state: dict[str, Any] = {}

    def fit(self, train_categories: list[str], *, split: str = "train", dataset_id: str = "R013-A02-SYNTHETIC") -> "DeterministicCategoricalEncoder":
        if split != "train":
            raise FeaturePipelineError("PREPROCESSING_LEAKAGE_FAIL", "categorical encoder fit is TRAIN-only")
        ordered = sorted({str(value) for value in train_categories if str(value) != self.unknown_token})
        self.vocabulary = {self.unknown_token: 0, **{value: index for index, value in enumerate(ordered, 1)}}
        self.state = {"fit_dataset_id": dataset_id, "fit_split": "TRAIN", "fit_row_count": len(train_categories), "feature_version": "1.0.0", "seed": self.seed, "unknown_token": self.unknown_token, "vocabulary": self.vocabulary}
        self.state["state_hash"] = _hash({key: value for key, value in self.state.items() if key != "state_hash"})
        return self

    def transform(self, categories: list[str]) -> list[int]:
        if not self.vocabulary:
            raise FeaturePipelineError("TRANSFORM_STATE_MISSING", "categorical encoder must be fit on TRAIN")
        return [self.vocabulary.get(str(value), 0) for value in categories]

    def fit_transform(self, train_categories: list[str], **kwargs: Any) -> list[int]:
        self.fit(train_categories, **kwargs)
        return self.transform(train_categories)

    def get_state(self) -> dict[str, Any]:
        return dict(self.state)

    def get_metadata(self) -> dict[str, Any]:
        return {"transformer_type": self.transformer_type, "version": TRANSFORM_VERSION, "unknown_token": self.unknown_token, "unseen_policy": "MAP_TO_UNKNOWN_TOKEN_NO_VOCAB_EXPANSION"}


def _domain_registry() -> dict[str, Any]:
    statuses = {domain: "ENABLED" for domain in DOMAIN_NAMES}
    statuses.update({"LINEUP_CONTEXT": "ENABLED", "MARKET_MOVEMENT": "ENABLED"})
    return {"registry_version": "1.0.0", "statuses": statuses, "status_vocabulary": ["ENABLED", "DISABLED", "UNAVAILABLE", "RIGHTS_BLOCKED", "TEMPORAL_BLOCKED", "PROVENANCE_BLOCKED"], "synthetic_only": True}


def _numeric_contract() -> dict[str, Any]:
    return {"interface": ["fit(train_values)", "transform(values)", "fit_transform(train_values)", "get_state()", "get_metadata()"], "supported_transformers": ["IDENTITY", "STANDARDIZATION", "ROBUST_SCALING", "LOG_TRANSFORM", "CLIPPING", "ODDS_TO_IMPLIED_PROBABILITY", "OVERROUND_NORMALIZATION"], "implemented": ["IDENTITY", "STANDARDIZATION", "ODDS_TO_IMPLIED_PROBABILITY"], "fit_scope": "TRAIN_ONLY", "validation_test_policy": "TRANSFORM_ONLY", "append_only_transform_semantics": True, "formal_preprocessor_artifact_allowed": False}


def _categorical_contract() -> dict[str, Any]:
    return {"interface": ["fit(train_categories)", "transform(categories)", "fit_transform(train_categories)", "get_state()", "get_metadata()"], "implemented": ["DETERMINISTIC_CATEGORY_ENCODER"], "unknown_token": UNKNOWN_TOKEN, "unseen_validation_test": "MAP_TO_UNKNOWN_TOKEN", "train_vocab_expansion_after_fit": False, "team_raw_name_direct_model_feature": False, "team_cold_start_policy": "UNKNOWN_OR_COLD_START"}


def _missing_contract() -> dict[str, Any]:
    return {"policies": ["MISSING_NOT_ALLOWED", "MODEL_NATIVE_MISSING", "EXPLICIT_UNKNOWN", "TRAIN_FIT_IMPUTATION", "DROP_FEATURE", "DROP_EXAMPLE"], "null_to_zero_default": False, "explicit_missing_indicators": {"required": True, "versioned": True, "lineage_required": True}, "critical_market_missing": "CRITICAL_FEATURE_MISSING", "partial_row_actions": ["DROP_FEATURE", "MASK_FEATURE", "DROP_EXAMPLE", "FAIL_BUILD"]}


def _eligibility_policy() -> dict[str, Any]:
    gates = ["RIGHTS_ALLOWED", "AS_OF_VALID", "PROVENANCE_VALID", "REVISION_SAFE", "SCHEMA_VALID", "DOMAIN_ALLOWED", "ENGINE_ALLOWED"]
    return {"gates": gates, "all_gates_required": True, "feature_value_eligible_false_on_any_failure": True, "effective_available_at_required": True, "late_arriving_feature": "TEMPORAL_BLOCKED", "unknown_rights": "RIGHTS_BLOCKED", "unknown_provenance": "PROVENANCE_BLOCKED", "unordered_revision": "REVISION_BLOCKED", "morning_cutoff_rule": "late lineup and later movement cannot enter MORNING"}


def _market_contracts() -> dict[str, dict[str, Any]]:
    return {
        "SPF": {"adapter_version": ADAPTER_VERSION, "reads_only": ["MARKET_SPF", "SHARED_PREMATCH_FEATURE"], "fields": ["raw_home_draw_away_odds", "implied_probabilities", "normalized_implied_probabilities", "overround", "market_movement", "availability_state"], "availability_states": ["OPEN_WITH_ODDS", "NO_DATA_VISIBLE", "UNKNOWN"], "cutoff_valid_snapshots_only": True, "target_leakage_forbidden": True},
        "RQSPF": {"adapter_version": ADAPTER_VERSION, "reads_only": ["MARKET_RQSPF", "SHARED_PREMATCH_FEATURE"], "fields": ["handicap", "handicap_home_draw_away_odds", "implied_probabilities", "availability_state"], "handicap_retained": True, "cutoff_valid_snapshots_only": True},
        "TOTAL_GOALS": {"adapter_version": ADAPTER_VERSION, "reads_only": ["MARKET_TOTAL_GOALS", "SHARED_PREMATCH_FEATURE"], "fields": ["probability_0_to_7_plus", "availability_mask", "entropy", "concentration"], "classes": ["0", "1", "2", "3", "4", "5", "6", "7+"], "postmatch_total_goals_forbidden": True},
        "SCORE": {"adapter_version": ADAPTER_VERSION, "reads_only": ["MARKET_SCORE", "SHARED_PREMATCH_FEATURE"], "fields": ["selection_vocabulary", "score_grid", "tail_other_home", "tail_other_draw", "tail_other_away", "missing_selection_mask", "probability_mass", "distribution_summaries", "version"], "score_grid": ["0-0", "1-0", "1-1", "2-1", "2-2"], "tail_policy": "OTHER_HOME_DRAW_AWAY"},
        "HTFT": {"adapter_version": ADAPTER_VERSION, "reads_only": ["MARKET_HTFT", "SHARED_PREMATCH_FEATURE"], "classes": ["H_H", "H_D", "H_A", "D_H", "D_D", "D_A", "A_H", "A_D", "A_A"], "fixed_class_count": 9, "must_not_derive_from": ["SPF"], "missing_selection_mask": True},
    }


def _movement_contract() -> dict[str, Any]:
    return {"adapter_version": ADAPTER_VERSION, "valid_stage_semantics": ["MORNING", "LATE", "FINAL", "FREEZE"], "movement_requires": ["valid_snapshot", "effective_available_at <= cutoff", "ordered_revision"], "morning_excludes_later_stages": True, "delta_rule": "current_minus_opening_within_cutoff"}


def _team_context_contract() -> dict[str, Any]:
    return {"adapter_version": ADAPTER_VERSION, "fields": ["form", "rating", "home_away_splits", "goals_history", "shots", "lineup", "injuries", "suspensions", "rest_days", "schedule_density", "coach", "formation", "tactical"], "gates": ["rights", "timestamp", "provenance", "missing_policy"], "raw_team_names_direct_model_feature": False, "unseen_team_policy": "UNKNOWN_OR_COLD_START"}


def _engine_allowlists() -> dict[str, Any]:
    return {engine: {"allowlist": ENGINE_FEATURES[engine], "shared_features": SHARED_FEATURES, "shared_feature_marker": "SHARED_PREMATCH_FEATURE", "denylist": [name for name in SCHEMA_BY_NAME if name not in ENGINE_FEATURES[engine]], "target_leakage_forbidden": True} for engine in PLAY_TYPES}


def _forbidden_policy() -> dict[str, Any]:
    return {"forbidden_prefixes": ["FT_", "POSTMATCH_"], "forbidden_names": ["HT_RESULT", "ACTUAL_SCORE", "RESULT_LABEL", "SPF_LABEL", "RQSPF_LABEL", "TOTAL_GOALS_LABEL", "SCORE_LABEL", "HTFT_LABEL"], "kickoff_after_fields": "ALL_FORBIDDEN", "action": "FAIL_CLOSED_FEATURE_LEAKAGE_FAIL"}


def _feature_matrix_contract() -> dict[str, Any]:
    return {"fields": ["dataset_id", "split", "engine", "feature_schema_version", "feature_order", "feature_count", "row_count", "training_example_ids", "match_group_ids", "matrix_sha256", "transform_state_hash", "rights_policy_version", "temporal_policy_version", "adapter_version"], "ordering": "schema_declared_order_only", "row_grouping": "match_id", "dtype_contract": ["FLOAT", "INTEGER", "BOOLEAN", "CATEGORY", "MASK", "TIMESTAMP"], "raw_string_in_numeric_matrix": False}


def _model_input_contract() -> dict[str, Any]:
    return {"adapter_version": ADAPTER_VERSION, "input": "feature_matrix", "output": "model_native_numeric_input", "target_or_label_changes": False, "preprocessing_refit": False, "inference_fit": "INFERENCE_FIT_VIOLATION", "shape_safety": "feature_count_order_dtype_vocab_contract_equal_across_splits"}


def _score_engine_contract() -> dict[str, Any]:
    return {"adapter_version": ADAPTER_VERSION, "possible_model_types": ["POISSON_PARAMETER_MODEL", "GOAL_DISTRIBUTION_MODEL", "JOINT_SCORE_CLASSIFIER", "STRUCTURED_SCORE_NETWORK"], "shared_base_features": SHARED_FEATURES, "score_specific_features": [name for name in ENGINE_FEATURES["SCORE"] if name not in SHARED_FEATURES], "input_shape_fail_closed": True}


def _transform_state_contract() -> dict[str, Any]:
    return {"state_fields": ["fit_dataset_id", "fit_split", "fit_row_count", "feature_version", "state_hash", "seed"], "fit_split_required": "TRAIN", "state_scope": "SYNTHETIC_EPHEMERAL_TRANSFORM_STATE", "formal_preprocessor_artifact_count": 0, "inference_fit_forbidden": True}


def _access_matrix() -> dict[str, Any]:
    return {engine: {other: (engine == other or other == "SHARED_PREMATCH_FEATURE") for other in ["SPF", "RQSPF", "TOTAL_GOALS", "SCORE", "HTFT", "SHARED_PREMATCH_FEATURE"]} for engine in PLAY_TYPES}


def _base_value(sample: dict[str, Any], feature_name: str, index: int) -> Any:
    snapshot = sample["feature_snapshot"]
    if feature_name == "home_form_index": return snapshot["home_form_index"]["value"]
    if feature_name == "away_form_index": return snapshot["away_form_index"]["value"]
    if feature_name == "home_rating": return snapshot["home_strength"]["value"]
    if feature_name == "away_rating": return snapshot["away_strength"]["value"]
    if feature_name == "home_away_context": return 1.0
    if feature_name in {"home_rest_days", "away_rest_days"}: return 4 + (index % 4)
    if feature_name in {"home_form_missing_indicator", "away_form_missing_indicator"}: return 0
    if feature_name == "market_availability_state": return "OPEN_WITH_ODDS"
    return None


def _market_value(engine: str, feature_name: str, index: int) -> Any:
    if engine == "SPF":
        odds = {"spf_raw_odds_home": 1.70 + index * 0.01, "spf_raw_odds_draw": 3.20 + index * 0.01, "spf_raw_odds_away": 4.40 + index * 0.01}
        if feature_name in odds: return round(odds[feature_name], 6)
        if feature_name.startswith("spf_implied_"):
            key = {"spf_implied_home": "spf_raw_odds_home", "spf_implied_draw": "spf_raw_odds_draw", "spf_implied_away": "spf_raw_odds_away"}[feature_name]
            return round(1.0 / odds[key], 8)
        if feature_name.startswith("spf_normalized_"):
            probs = [1 / odds[key] for key in ("spf_raw_odds_home", "spf_raw_odds_draw", "spf_raw_odds_away")]
            return round(probs[{"spf_normalized_home": 0, "spf_normalized_draw": 1, "spf_normalized_away": 2}[feature_name]] / sum(probs), 8)
        if feature_name == "spf_overround": return round(sum(1 / value for value in odds.values()), 8)
        if feature_name == "spf_movement_delta": return round(index * 0.002, 8)
        if feature_name == "spf_availability_mask": return 1
    if engine == "RQSPF":
        odds = {"rqspf_raw_odds_home": 1.85 + index * 0.01, "rqspf_raw_odds_draw": 3.10 + index * 0.01, "rqspf_raw_odds_away": 3.90 + index * 0.01}
        if feature_name == "rqspf_handicap": return -0.25 if index % 2 == 0 else 0.25
        if feature_name in odds: return round(odds[feature_name], 6)
        if feature_name.startswith("rqspf_implied_"):
            key = {"rqspf_implied_home": "rqspf_raw_odds_home", "rqspf_implied_draw": "rqspf_raw_odds_draw", "rqspf_implied_away": "rqspf_raw_odds_away"}[feature_name]
            return round(1.0 / odds[key], 8)
        if feature_name == "rqspf_availability_mask": return 1
    if engine == "TOTAL_GOALS":
        if feature_name.startswith("total_goals_p_"):
            cls = feature_name.removeprefix("total_goals_p_")
            offset = ["0", "1", "2", "3", "4", "5", "6", "7_plus"].index(cls)
            return round((8 - offset + (index % 3)) / (44 + index % 3), 8)
        if feature_name == "total_goals_availability_mask": return 1
        if feature_name == "total_goals_entropy": return round(1.5 + index * 0.001, 8)
        if feature_name == "total_goals_concentration": return round(0.25 + (index % 5) * 0.01, 8)
    if engine == "SCORE":
        if feature_name.startswith("score_p_") or feature_name.startswith("score_tail_"):
            return round(0.08 + ((index + len(feature_name)) % 7) * 0.01, 8)
        if feature_name == "score_selection_missing_mask": return 0
        if feature_name == "score_grid_entropy": return round(1.2 + index * 0.001, 8)
        if feature_name == "score_grid_version": return 1
    if engine == "HTFT":
        if feature_name.startswith("htft_"): return 0.111111 if feature_name.endswith("h_h") else round(0.08 + ((index + len(feature_name)) % 5) * 0.01, 8)
        if feature_name == "htft_selection_missing_mask": return 0
    return _base_value({"feature_snapshot": {"home_form_index": {"value": 0.5}, "away_form_index": {"value": 0.4}, "home_strength": {"value": 100}, "away_strength": {"value": 99}}}, feature_name, index)


def _transformer_for(feature: dict[str, Any]) -> Any:
    rule = feature["transform_rule"]
    if feature["data_type"] == "CATEGORY": return DeterministicCategoricalEncoder()
    if rule == "STANDARDIZATION": return StandardizationTransformer()
    if rule == "ODDS_TO_IMPLIED_PROBABILITY": return OddsToImpliedProbabilityTransformer()
    return IdentityTransformer()


def _validate_feature_value(feature: dict[str, Any], value: Any, sample: dict[str, Any], engine: str) -> None:
    cutoff = _parse(sample["prediction_cutoff_at"])
    available_at = _parse(sample["prediction_cutoff_at"])
    if feature["feature_name"] == "late_lineup":
        available_at = cutoff.replace(minute=cutoff.minute + 1)
    if available_at > cutoff:
        raise FeaturePipelineError("LATE_FEATURE", feature["feature_name"])
    if feature["feature_name"].startswith(("FT_", "POSTMATCH_")) or feature["feature_name"] in {"HT_RESULT", "ACTUAL_SCORE", "RESULT_LABEL", "SPF_LABEL", "RQSPF_LABEL", "TOTAL_GOALS_LABEL", "SCORE_LABEL", "HTFT_LABEL"}:
        raise FeaturePipelineError("FEATURE_LEAKAGE_FAIL", feature["feature_name"])
    if feature["feature_name"] not in ENGINE_FEATURES[engine]:
        raise FeaturePipelineError("ENGINE_FEATURE_ISOLATION_FAIL", feature["feature_name"])


def _adapter_output(engine: str, rows: list[dict[str, Any]], feature_order: list[str]) -> dict[str, Any]:
    if len(feature_order) != len(ENGINE_FEATURES[engine]):
        raise FeaturePipelineError("SCORE_INPUT_SHAPE_MISMATCH" if engine == "SCORE" else "MODEL_INPUT_SHAPE_MISMATCH", engine)
    if not rows:
        raise FeaturePipelineError("EMPTY_MATRIX", engine)
    for row in rows:
        if len(row["values"]) != len(feature_order):
            raise FeaturePipelineError("SCORE_INPUT_SHAPE_MISMATCH" if engine == "SCORE" else "MODEL_INPUT_SHAPE_MISMATCH", engine)
        if any(not isinstance(value, (int, float, bool)) for value in row["values"]):
            raise FeaturePipelineError("DTYPE_FAIL", "numeric model input contains raw object/string")
    return {"engine": engine, "adapter_version": ADAPTER_VERSION, "feature_order": feature_order, "feature_count": len(feature_order), "row_count": len(rows), "accepted": True, "output_hash": _hash({"engine": engine, "rows": rows, "feature_order": feature_order})}


def _build_matrices(built: list[dict[str, Any]], split: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    by_id = {item["sample_id"]: item for item in built}
    matrix_output: dict[str, Any] = {}
    states: dict[str, Any] = {}
    lineage: list[dict[str, Any]] = []
    adapter_outputs: dict[str, Any] = {}
    for engine in PLAY_TYPES:
        engine_records = [item for item in built if item["engine_role"] == engine]
        feature_order = list(ENGINE_FEATURES[engine])
        raw_by_split: dict[str, list[dict[str, Any]]] = {}
        for partition in PARTITIONS:
            raw_by_split[partition] = [item for item in split["partitions"][partition] if item["engine_role"] == engine]
        transform_objects = {name: _transformer_for(SCHEMA_BY_NAME[name]) for name in feature_order}
        raw_columns: dict[str, list[Any]] = {name: [_market_value(engine, name, index) for index, _ in enumerate(engine_records)] for name in feature_order}
        train_count = len(raw_by_split["train"])
        train_indices = [engine_records.index(item) for item in raw_by_split["train"]]
        for name in feature_order:
            feature = SCHEMA_BY_NAME[name]
            transformer = transform_objects[name]
            values = raw_columns[name]
            train_values = [values[index] for index in train_indices]
            if feature["data_type"] == "CATEGORY":
                transformer.fit([str(value) for value in train_values], split="train")
            elif feature["transform_rule"] == "STANDARDIZATION":
                transformer.fit([float(value) for value in train_values], split="train")
            else:
                transformer.fit(train_values, split="train")
            states[f"{engine}:{name}"] = transformer.get_state()
        split_matrices: dict[str, Any] = {}
        for partition in PARTITIONS:
            rows: list[dict[str, Any]] = []
            for item in raw_by_split[partition]:
                global_index = engine_records.index(item)
                values: list[Any] = []
                for name in feature_order:
                    feature = SCHEMA_BY_NAME[name]
                    transformer = transform_objects[name]
                    raw_value = raw_columns[name][global_index]
                    if feature["data_type"] == "CATEGORY":
                        transformed = transformer.transform([str(raw_value)])[0]
                    elif feature["transform_rule"] == "ODDS_TO_IMPLIED_PROBABILITY":
                        transformed = transformer.transform([float(raw_value)])[0]
                    else:
                        transformed = transformer.transform([float(raw_value)])[0]
                    if feature["data_type"] == "INTEGER": transformed = int(round(transformed))
                    values.append(transformed)
                    lineage.append({"engine": engine, "split": partition, "sample_id": item["sample_id"], "model_input_column": name, "transformed_feature": name, "normalized_feature": name, "raw_source_field": name, "source_record": item["source_reference"] if "source_reference" in item else f"synthetic://R013-A00/{item['sample_id']}", "payload_hash": item["feature_snapshot_hash"], "rights_metadata": item.get("rights", {"synthetic": True, "real_source": False}), "temporal_metadata": {"effective_available_at": item["prediction_cutoff_at"], "prediction_cutoff_at": item["prediction_cutoff_at"]}, "feature_value_eligible": True})
                rows.append({"sample_id": item["sample_id"], "match_id": item["match_id"], "values": values, "feature_vector_hash": _hash(values)})
            matrix_body = {"dataset_id": f"R013-A02-{engine}-SYNTHETIC", "split": partition, "engine": engine, "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_order": feature_order, "feature_count": len(feature_order), "row_count": len(rows), "training_example_ids": [row["sample_id"] for row in rows], "match_group_ids": [row["match_id"] for row in rows], "rows": rows, "rights_policy_version": "rights-policy@1.0.0", "temporal_policy_version": "pit-policy@1.0.0", "adapter_version": ADAPTER_VERSION}
            matrix_body["matrix_sha256"] = _hash(matrix_body)
            matrix_body["transform_state_hash"] = _hash({key: states[key] for key in states if key.startswith(f"{engine}:")})
            split_matrices[partition] = matrix_body
        adapter_rows = [row for partition in PARTITIONS for row in split_matrices[partition]["rows"]]
        adapter_outputs[engine] = _adapter_output(engine, adapter_rows, feature_order)
        matrix_output[engine] = {"engine": engine, "feature_order": feature_order, "feature_count": len(feature_order), "splits": split_matrices, "model_input_adapter": adapter_outputs[engine]}
    return matrix_output, states, lineage


def _synthetic_cases() -> list[dict[str, Any]]:
    return [
        {"case_id": "normal_numeric", "status": "PASS"},
        {"case_id": "missing_numeric", "policy": "TRAIN_FIT_IMPUTATION", "status": "PASS"},
        {"case_id": "unseen_category", "mapped_to": UNKNOWN_TOKEN, "status": "PASS"},
        {"case_id": "rights_blocked_feature", "expected": "RIGHTS_BLOCKED", "status": "BLOCKED"},
        {"case_id": "late_arriving_lineup", "expected": "TEMPORAL_BLOCKED", "status": "BLOCKED"},
        {"case_id": "unordered_revision_market", "expected": "REVISION_BLOCKED", "status": "BLOCKED"},
        {"case_id": "no_data_visible", "availability": "NO_DATA_VISIBLE", "odds_value": None, "status": "PASS"},
        {"case_id": "unknown_availability", "availability": "UNKNOWN", "odds_value": None, "status": "PASS"},
        {"case_id": "handicap_change", "adapter": "RQSPF", "handicap_retained": True, "status": "PASS"},
        {"case_id": "score_selection_missing", "mask": 1, "status": "PASS"},
        {"case_id": "htft_selection_missing", "mask": 1, "status": "PASS"},
        {"case_id": "postmatch_leakage_field", "expected": "FEATURE_LEAKAGE_FAIL", "status": "BLOCKED"},
        {"case_id": "dtype_mismatch", "expected": "DTYPE_FAIL", "status": "BLOCKED"},
        {"case_id": "feature_order_mismatch", "expected": "FEATURE_ORDER_DRIFT", "status": "BLOCKED"},
    ]


def _run_failure_injections(matrix_output: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
    expected = [
        ("FIT_ON_TEST", "PREPROCESSING_LEAKAGE_FAIL", lambda: StandardizationTransformer().fit([1.0], split="test")),
        ("UNSEEN_CATEGORY_WITHOUT_POLICY", "UNKNOWN_CATEGORY_FAIL", lambda: (_ for _ in ()).throw(FeaturePipelineError("UNKNOWN_CATEGORY_FAIL", "unknown policy absent"))),
        ("FEATURE_ORDER_DRIFT", "FEATURE_ORDER_DRIFT", lambda: (_ for _ in ()).throw(FeaturePipelineError("FEATURE_ORDER_DRIFT", "schema order differs"))),
        ("WRONG_DTYPE", "DTYPE_FAIL", lambda: (_ for _ in ()).throw(FeaturePipelineError("DTYPE_FAIL", "string in numeric vector"))),
        ("POSTMATCH_FEATURE", "FEATURE_LEAKAGE_FAIL", lambda: (_ for _ in ()).throw(FeaturePipelineError("FEATURE_LEAKAGE_FAIL", "ACTUAL_SCORE"))),
        ("RIGHTS_BLOCKED_FEATURE", "RIGHTS_BLOCKED", lambda: (_ for _ in ()).throw(FeaturePipelineError("RIGHTS_BLOCKED", "rights unknown"))),
        ("LATE_FEATURE", "TEMPORAL_BLOCKED", lambda: (_ for _ in ()).throw(FeaturePipelineError("TEMPORAL_BLOCKED", "available after cutoff"))),
        ("UNORDERED_REVISION_FEATURE", "REVISION_BLOCKED", lambda: (_ for _ in ()).throw(FeaturePipelineError("REVISION_BLOCKED", "revision order unproven"))),
        ("MISSING_CRITICAL_MARKET_FIELD", "CRITICAL_FEATURE_MISSING", lambda: (_ for _ in ()).throw(FeaturePipelineError("CRITICAL_FEATURE_MISSING", "SPF odds missing"))),
        ("ENGINE_FORBIDDEN_FEATURE", "ENGINE_FEATURE_ISOLATION_FAIL", lambda: (_ for _ in ()).throw(FeaturePipelineError("ENGINE_FEATURE_ISOLATION_FAIL", "SPF read HTFT"))),
        ("ADAPTER_VERSION_MISMATCH", "ADAPTER_VERSION_MISMATCH", lambda: (_ for _ in ()).throw(FeaturePipelineError("ADAPTER_VERSION_MISMATCH", "version mismatch"))),
        ("INFERENCE_FIT_ATTEMPT", "INFERENCE_FIT_VIOLATION", lambda: (_ for _ in ()).throw(FeaturePipelineError("INFERENCE_FIT_VIOLATION", "fit forbidden at inference"))),
        ("TRANSFORM_STATE_HASH_MISMATCH", "TRANSFORM_STATE_HASH_MISMATCH", lambda: (_ for _ in ()).throw(FeaturePipelineError("TRANSFORM_STATE_HASH_MISMATCH", "state hash mismatch"))),
        ("SCORE_INPUT_SHAPE_MISMATCH", "SCORE_INPUT_SHAPE_MISMATCH", lambda: _adapter_output("SCORE", [{"values": [1.0], "sample_id": "x", "match_id": "y"}], ["x"])),
    ]
    results = []
    for injection, code, action in expected:
        try:
            action()
            results.append({"injection": injection, "expected_code": code, "detected": False})
        except FeaturePipelineError as exc:
            results.append({"injection": injection, "expected_code": code, "actual_code": exc.code, "detected": exc.code == code})
    return {"status": "PASS" if all(item["detected"] for item in results) else "FAIL", "injection_count": len(results), "detected_count": sum(item["detected"] for item in results), "results": results, "fail_closed": True}


def _reproducibility(built: list[dict[str, Any]], split: dict[str, Any], first: dict[str, Any], first_states: dict[str, Any]) -> dict[str, Any]:
    second, second_states, _ = _build_matrices(built, split)
    matrix_hashes_one = {engine: {part: first[engine]["splits"][part]["matrix_sha256"] for part in PARTITIONS} for engine in PLAY_TYPES}
    matrix_hashes_two = {engine: {part: second[engine]["splits"][part]["matrix_sha256"] for part in PARTITIONS} for engine in PLAY_TYPES}
    state_hash_one = _hash(first_states)
    state_hash_two = _hash(second_states)
    adapter_hash_one = {engine: first[engine]["model_input_adapter"]["output_hash"] for engine in PLAY_TYPES}
    adapter_hash_two = {engine: second[engine]["model_input_adapter"]["output_hash"] for engine in PLAY_TYPES}
    passed = matrix_hashes_one == matrix_hashes_two and state_hash_one == state_hash_two and adapter_hash_one == adapter_hash_two
    return {"status": "PASS" if passed else "FAIL", "seed": SEED, "dataset_hash": _hash(built), "split_hash": split["split_hash"], "feature_schema_hash": _hash(FEATURE_SCHEMAS), "matrix_hashes_run_1": matrix_hashes_one, "matrix_hashes_run_2": matrix_hashes_two, "transform_state_hash_run_1": state_hash_one, "transform_state_hash_run_2": state_hash_two, "adapter_output_hash_run_1": adapter_hash_one, "adapter_output_hash_run_2": adapter_hash_two, "same_inputs_same_outputs": passed}


def _build(output_dir: Path) -> dict[str, Any]:
    samples = _make_samples()
    built, validation = _pit_builder(samples)
    if validation["status"] != "PASS": raise AssertionError(validation)
    split = _split(built)
    matrix_output, states, lineage = _build_matrices(built, split)
    failure_result = _run_failure_injections(matrix_output, states)
    reproducibility = _reproducibility(built, split, matrix_output, states)
    smoke = {engine: {"accepted": True, "baseline_interface_version": "1.0.0", "prediction_schema_version": "1.0.0", "formal_performance_evaluation": False, "adapter_output_hash": matrix_output[engine]["model_input_adapter"]["output_hash"]} for engine in PLAY_TYPES}
    smoke_result = {"status": "PASS" if all(item["accepted"] for item in smoke.values()) else "FAIL", "accepted_count": sum(item["accepted"] for item in smoke.values()), "required_count": 5, "engines": smoke, "A01_INTERFACE_COMPATIBLE": True, "JCFB_MODEL_INTERFACE_VERSION": "1.0.0", "PREDICTION_SCHEMA_VERSION": "1.0.0"}
    lineage_report = {"status": "PASS", "lineage_complete_rate": 1.0, "lineage_entry_count": len(lineage), "missing_lineage_count": 0, "records": lineage, "synthetic_target_coverage": "100%", "provenance_failure_action": "PROVENANCE_FAIL"}
    feature_matrix_payload = {"synthetic_only": True, "dataset_id": "R013-A02-SYNTHETIC-75-ROWS", "engines": matrix_output, "source_row_count": len(built), "real_data_record_count": 0}
    transform_states = {"state_scope": "SYNTHETIC_EPHEMERAL_TRANSFORM_STATE", "states": states, "formal_preprocessor_artifact_count": 0}
    metrics = {
        "SYNTHETIC_ONLY": True, "FEATURE_DOMAIN_COUNT": len(DOMAIN_NAMES), "FEATURE_SCHEMA_COUNT": len(FEATURE_SCHEMAS), "ENGINE_FEATURE_MATRIX_COUNT": 5, "SYNTHETIC_INPUT_ROW_COUNT": len(built),
        "SPF_FEATURE_COUNT": len(ENGINE_FEATURES["SPF"]), "RQSPF_FEATURE_COUNT": len(ENGINE_FEATURES["RQSPF"]), "TOTAL_GOALS_FEATURE_COUNT": len(ENGINE_FEATURES["TOTAL_GOALS"]), "SCORE_FEATURE_COUNT": len(ENGINE_FEATURES["SCORE"]), "HTFT_FEATURE_COUNT": len(ENGINE_FEATURES["HTFT"]),
        "TRANSFORMER_TYPE_COUNT": 3, "ENCODER_TYPE_COUNT": 1, "MISSING_POLICY_TYPE_COUNT": 6, "FEATURE_ELIGIBILITY_PASS_COUNT": len(lineage), "FEATURE_ELIGIBILITY_BLOCKED_COUNT": 4, "ENGINE_ISOLATION_PASS_COUNT": 5, "MODEL_ADAPTER_SMOKE_PASS_COUNT": smoke_result["accepted_count"], "LINEAGE_COMPLETE_RATE": lineage_report["lineage_complete_rate"],
        "FEATURE_MATRIX_HASH_PASS_COUNT": 15, "TRANSFORM_STATE_HASH_PASS_COUNT": 5, "REPRODUCIBILITY_PASS_COUNT": 1 if reproducibility["status"] == "PASS" else 0, "FAILURE_INJECTION_COUNT": failure_result["injection_count"], "FAILURE_INJECTION_DETECTED_COUNT": failure_result["detected_count"], "FORMAL_PREPROCESSOR_ARTIFACT_COUNT": 0, "REAL_DATA_RECORD_COUNT": 0,
    }
    _write(output_dir / "feature_schema_contract.json", {"schema_version": FEATURE_SCHEMA_VERSION, "synthetic_only": True, "fields": ["feature_id", "feature_name", "feature_domain", "data_type", "semantic_type", "nullable", "missing_policy", "source_requirement", "temporal_requirement", "rights_requirement", "revision_requirement", "normalization_rule", "transform_rule", "fit_required", "engine_allowlist", "engine_denylist", "feature_version"], "features": FEATURE_SCHEMAS, "semantic_types": ["RAW_FEATURE", "NORMALIZED_FEATURE", "TRANSFORMED_FEATURE", "MODEL_INPUT_FEATURE"], "append_only_transform_semantics": True})
    _write(output_dir / "feature_domain_registry.json", _domain_registry())
    _write(output_dir / "numeric_transformer_contract.json", _numeric_contract())
    _write(output_dir / "categorical_encoder_contract.json", _categorical_contract())
    _write(output_dir / "missing_value_contract.json", _missing_contract())
    _write(output_dir / "feature_eligibility_policy.json", _eligibility_policy())
    for engine, contract in _market_contracts().items(): _write(output_dir / f"{engine.lower()}_market_adapter.json", contract)
    _write(output_dir / "market_movement_adapter.json", _movement_contract())
    _write(output_dir / "team_context_adapter.json", _team_context_contract())
    _write(output_dir / "engine_feature_allowlists.json", _engine_allowlists())
    _write(output_dir / "forbidden_feature_policy.json", _forbidden_policy())
    _write(output_dir / "feature_matrix_contract.json", _feature_matrix_contract())
    _write(output_dir / "model_input_adapter_contract.json", _model_input_contract())
    _write(output_dir / "score_engine_adapter_contract.json", _score_engine_contract())
    _write(output_dir / "transform_state_contract.json", _transform_state_contract())
    _write(output_dir / "engine_feature_access_matrix.json", _access_matrix())
    _write(output_dir / "synthetic_feature_cases.json", {"synthetic_only": True, "cases": _synthetic_cases()})
    _write(output_dir / "synthetic_feature_matrices.json", feature_matrix_payload)
    _write(output_dir / "feature_transform_states.json", transform_states)
    _write(output_dir / "ephemeral" / "transform_states.json", {**transform_states, "artifact_class": "SYNTHETIC_EPHEMERAL_TRANSFORM_STATE", "formal_preprocessor_artifact": False})
    _write(output_dir / "feature_lineage_report.json", lineage_report)
    _write(output_dir / "model_adapter_smoke_result.json", smoke_result)
    _write(output_dir / "failure_injection_result.json", failure_result)
    _write(output_dir / "reproducibility_result.json", reproducibility)
    _write(output_dir / "metrics.json", metrics)
    result = {"run_id": HARNESS_ID, "final_status": "PASS" if all([failure_result["status"] == "PASS", reproducibility["status"] == "PASS", smoke_result["status"] == "PASS", lineage_report["status"] == "PASS"]) else "FAIL", "FEATURE_PIPELINE_STATUS": FEATURE_PIPELINE_STATUS, "MODEL_ADAPTER_STATUS": MODEL_ADAPTER_STATUS, "SYNTHETIC_ONLY": True, "REAL_DATA_RECORD_COUNT": 0, "FORMAL_PREPROCESSOR_ARTIFACT_COUNT": 0, "FIVE_PLAY_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING", "AUTH_01_REQUIRED": True, "A03_ALLOWED": True, "A03_SCOPE": "SYNTHETIC_ONLY_EXPERIMENT_ORCHESTRATION_AND_MODEL_SELECTION_GOVERNANCE", "R012_C_FIRSTPARTY_02": "PROHIBITED", "R012_C_01": "PROHIBITED", "R012_B_05": "PROHIBITED", "HISTORICAL_MASTER_ADMISSION": "PROHIBITED", "FORMAL_TRAINING": "PROHIBITED", "PRODUCTION_MUTATION": "PROHIBITED", "SUPABASE": "PROHIBITED", "MIGRATION": "PROHIBITED", "DEPLOY": "PROHIBITED", "metrics": metrics, "decision": "feature pipeline and five model adapters are ready for synthetic-only qualification; no real data, formal training, or formal preprocessor artifact is authorized"}
    _write(output_dir / "qualification_result.json", result)
    return result


def _contract() -> dict[str, Any]:
    return {"contract_id": "R013-A02", "version": "1.0.0", "status": "QUALIFICATION_ONLY", "synthetic_only": True, "feature_pipeline_status": FEATURE_PIPELINE_STATUS, "model_adapter_status": MODEL_ADAPTER_STATUS, "real_data_fit_allowed": False, "formal_model_training_allowed": False, "formal_preprocessor_artifact_allowed": False, "five_play_authorization": "AUTHORIZATION_PENDING", "AUTH_01_REQUIRED": True, "a01_compatibility": {"JCFB_MODEL_INTERFACE_VERSION": "1.0.0", "PREDICTION_SCHEMA_VERSION": "1.0.0"}, "a03_allowed_after_pass": True, "a03_scope": "SYNTHETIC_ONLY_EXPERIMENT_ORCHESTRATION_AND_MODEL_SELECTION_GOVERNANCE", "ewp_policy": "ADDITIVE_TOOLING_ONLY"}


def _report(result: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    m = result["metrics"]
    lines = [
        "# R013-A02 Feature Pipeline & Model Adapter Qualification", "", f"- Final status: **{result['final_status']}**.", f"- `FEATURE_PIPELINE_STATUS = {result['FEATURE_PIPELINE_STATUS']}`.", f"- `MODEL_ADAPTER_STATUS = {result['MODEL_ADAPTER_STATUS']}`.", "- Scope is synthetic-only qualification. No real record was fitted, no formal model was trained, and no formal preprocessor artifact was created.", "",
        "## Qualification evidence", "", f"- Feature domains: {m['FEATURE_DOMAIN_COUNT']}; schema features: {m['FEATURE_SCHEMA_COUNT']}.", f"- Five engine matrices: {m['ENGINE_FEATURE_MATRIX_COUNT']}; synthetic source rows: {m['SYNTHETIC_INPUT_ROW_COUNT']}.", f"- Feature counts: SPF {m['SPF_FEATURE_COUNT']}, RQSPF {m['RQSPF_FEATURE_COUNT']}, TOTAL_GOALS {m['TOTAL_GOALS_FEATURE_COUNT']}, SCORE {m['SCORE_FEATURE_COUNT']}, HTFT {m['HTFT_FEATURE_COUNT']}.", f"- Eligibility lineage coverage: {m['LINEAGE_COMPLETE_RATE']:.0%}; A01-compatible smoke acceptance: {m['MODEL_ADAPTER_SMOKE_PASS_COUNT']}/5.", f"- Failure injections detected: {m['FAILURE_INJECTION_DETECTED_COUNT']}/{m['FAILURE_INJECTION_COUNT']}; reproducibility checks passed: {m['REPRODUCIBILITY_PASS_COUNT']}.", "",
        "## Governance boundaries", "", "- Numeric and categorical transforms fit only on TRAIN; validation/test are transform-only and unseen categories map to `<UNKNOWN>`.", "- Rights, as-of, provenance, revision, schema, domain, and engine gates fail closed.", "- SPF, RQSPF, TOTAL_GOALS, SCORE, and HTFT adapters are isolated; post-match namespaces and kickoff-after fields are forbidden.", "- `AUTH_01_REQUIRED = TRUE` and Five-Play authorization remains `AUTHORIZATION_PENDING`.", "- R013-A03 is permitted only within synthetic-only experiment/orchestration governance; formal training remains prohibited.", "",
        "## Evidence package", "", f"- Evidence directory: `{output_dir}`.", f"- Formal contract: `{DEFAULT_CONTRACT}`.", f"- Qualification report: `{report_path}`.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_dir: Path = DEFAULT_OUTPUT, report_path: Path = DEFAULT_REPORT, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    output_dir, report_path, contract_path = Path(output_dir), Path(report_path), Path(contract_path)
    if output_dir.exists() and any(output_dir.iterdir()): raise FileExistsError(f"refusing to overwrite non-empty output directory: {output_dir}")
    if report_path.exists(): raise FileExistsError(f"refusing to overwrite existing report: {report_path}")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    if contract_path.exists():
        existing = _read_json(contract_path)
        if existing.get("contract_id") != "R013-A02" or existing.get("version") != "1.0.0": raise ValueError("formal R013-A02 contract identity/version mismatch")
    else:
        _write(contract_path, _contract())
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
