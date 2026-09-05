"""Fail-closed temporal splitting and training-readiness runtime for B15-EWP-003.

This module deliberately stops at split/readiness evidence.  It never fits a
model, writes a model artifact, or calls a downstream engine.  Production
execution consumes only an approved EWP-002 manifest and its dataset artifact;
synthetic records are accepted by the pure builder/evaluator APIs only so
tests can prove the contract without changing the approved dataset.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.prediction_training_contract import ENGINE_ROLES, sha256_json


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CURRENT_DATASET_ID = "dataset-13c4b050dc50e2de3ec8a961a9c9b029"
DEFAULT_PROJECT_ROOT = Path("F:/Projects/jcfb-v4")
DEFAULT_DATASET_MANIFEST = (
    "approved_data/training_datasets/manifests/"
    "dataset-13c4b050dc50e2de3ec8a961a9c9b029-r001.json"
)
DEFAULT_REPORT_PATH = Path("config/prediction_training/v4_batch15_ewp003_readiness_report.json")

DECLARED_CLASSES = {
    "OUTCOME": ("H", "D", "A"),
    "HANDICAP": ("H", "D", "A"),
    "GOALS": ("0", "1", "2", "3", "4", "5", "6", "7+"),
    "HTFT": ("H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"),
}


class Ewp003RuntimeError(ValueError):
    """A fail-closed EWP-003 contract violation."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise Ewp003RuntimeError("TIMESTAMP_NOT_DECLARED", "timestamp must be a timezone-aware ISO string")
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise Ewp003RuntimeError("TIMESTAMP_INVALID", str(value)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Ewp003RuntimeError("TIMESTAMP_TIMEZONE_REQUIRED", str(value))
    return parsed.astimezone(timezone.utc)


def _duration(value: Any, field: str) -> timedelta:
    if not isinstance(value, str) or not value.strip():
        raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", field)
    text = value.strip().upper()
    match = re.fullmatch(
        r"P(?:(?P<days>\d+(?:\.\d+)?)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?",
        text,
    )
    if not match or text == "P":
        raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", f"{field} must be an ISO-8601 duration")
    result = timedelta(
        days=float(match.group("days") or 0),
        hours=float(match.group("hours") or 0),
        minutes=float(match.group("minutes") or 0),
        seconds=float(match.group("seconds") or 0),
    )
    if result <= timedelta(0):
        raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", f"{field} must be positive")
    return result


def _hash_body(document: Mapping[str, Any], self_fields: Sequence[str] = ()) -> str:
    body = {key: value for key, value in document.items() if key not in set(self_fields)}
    return sha256_json(body)


def _stable_sample_id(sample: Mapping[str, Any]) -> str:
    return str(sample.get("training_sample_id", sample.get("sample_id", "")))


def _sample_sort_key(sample: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _parse_timestamp(sample["prediction_cutoff_at"]),
        str(sample.get("match_id", "")),
        _stable_sample_id(sample),
    )


def _stable_ref(sample: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "training_sample_id": _stable_sample_id(sample),
        "match_id": str(sample.get("match_id", "")),
        "cutoff_profile": str(sample.get("cutoff_profile", "")),
        "engine_role": str(sample.get("engine_role", "")),
        "revision": sample.get("revision"),
        "sample_hash": sample.get("sample_hash"),
    }


def _sample_class(sample: Mapping[str, Any], role: str) -> Optional[str]:
    for key in ("target_class", "class_label", "label_class"):
        if sample.get(key) is not None:
            return str(sample[key])
    labels = sample.get("labels")
    if isinstance(labels, Mapping) and labels.get(role) is not None:
        return str(labels[role])
    classes = sample.get("class_labels")
    if isinstance(classes, Mapping) and classes.get(role) is not None:
        return str(classes[role])
    return None


def _declared_feature_available(sample: Mapping[str, Any], feature: str) -> Optional[bool]:
    for key in ("feature_availability", "required_features", "features"):
        value = sample.get(key)
        if isinstance(value, Mapping) and feature in value:
            item = value[feature]
            if isinstance(item, bool):
                return item
            if isinstance(item, Mapping) and isinstance(item.get("available"), bool):
                return item["available"]
    if feature in sample:
        return sample[feature] is not None
    return None


@dataclass(frozen=True)
class DatasetBinding:
    dataset_id: str
    dataset_revision: str
    dataset_manifest_hash: str
    dataset_substantive_hash: str
    dataset_version: str
    active_revision: bool = True
    supersedes: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_revision": self.dataset_revision,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "dataset_substantive_hash": self.dataset_substantive_hash,
            "dataset_version": self.dataset_version,
            "active_revision": self.active_revision,
            "supersedes": self.supersedes,
        }


@dataclass(frozen=True)
class SplitResult:
    strategy: str
    partitions: Mapping[str, tuple[Mapping[str, Any], ...]]
    folds: tuple[Mapping[str, Any], ...]
    boundaries: Mapping[str, Any]
    config_identity: str
    config_hash: str
    grouping_identity: Mapping[str, Any]
    ordering_identity: Mapping[str, Any]
    split_substantive_hash: str


def validate_league_scope(scope: Any, samples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate the manifest-declared league scope; never infer one from rows."""

    if not isinstance(scope, Mapping):
        raise Ewp003RuntimeError("LEAGUE_SCOPE_NOT_DECLARED", "league scope must be declared by the dataset manifest")
    scope_type = scope.get("scope_type")
    scope_hash = scope.get("scope_declaration_hash")
    if scope_type not in {"SINGLE_LEAGUE", "DECLARED_MULTI_LEAGUE"} or not isinstance(scope_hash, str) or not HASH_RE.fullmatch(scope_hash):
        raise Ewp003RuntimeError("LEAGUE_SCOPE_NOT_DECLARED", "league scope declaration is incomplete")
    if scope_type == "SINGLE_LEAGUE":
        league_ids = [scope.get("league_id")]
        if not league_ids[0]:
            raise Ewp003RuntimeError("LEAGUE_SCOPE_NOT_DECLARED", "single league_id is required")
    else:
        raw_ids = scope.get("league_ids")
        if not isinstance(raw_ids, list) or not raw_ids or any(not item for item in raw_ids):
            raise Ewp003RuntimeError("LEAGUE_SCOPE_NOT_DECLARED", "explicit league_ids are required")
        if "partition_coverage_requirements" not in scope or "fold_coverage_requirements" not in scope:
            raise Ewp003RuntimeError("LEAGUE_SCOPE_NOT_DECLARED", "multi-league coverage requirements are required")
        league_ids = list(dict.fromkeys(str(item) for item in raw_ids))
    for sample in samples:
        league_id = sample.get("league_id", sample.get("competition_id"))
        if league_id not in league_ids:
            raise Ewp003RuntimeError("LEAGUE_SCOPE_OUT_OF_DECLARED_SCOPE", str(league_id))
    return {"scope_type": scope_type, "league_ids": sorted(str(item) for item in league_ids), "scope_declaration_hash": scope_hash}


class TemporalSplitBuilder:
    """Build only explicitly configured, match-grouped temporal splits."""

    def __init__(self, contract: Mapping[str, Any], split_config: Optional[Mapping[str, Any]] = None):
        self.contract = contract
        self.split_config = dict(split_config) if split_config is not None else None
        self.strategy_contract = contract.get("strategy_contract", {})

    def _require_config(self) -> Mapping[str, Any]:
        if not isinstance(self.split_config, Mapping) or not self.split_config.get("strategy"):
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", "strategy and all split parameters are required")
        strategy = self.split_config.get("strategy")
        if strategy not in self.strategy_contract.get("allowed_strategies", ()):
            if str(strategy).upper() in {"RANDOM", "RANDOM_SPLIT"}:
                raise Ewp003RuntimeError("RANDOM_SPLIT_FORBIDDEN", "random split is forbidden")
            raise Ewp003RuntimeError("SPLIT_STRATEGY_INVALID", str(strategy))
        return self.split_config

    def build(self, samples: Sequence[Mapping[str, Any]], binding: DatasetBinding, league_scope: Mapping[str, Any]) -> SplitResult:
        config = self._require_config()
        if not samples:
            raise Ewp003RuntimeError("TRAINING_DATA_INSUFFICIENT", "no samples can be split")
        for sample in samples:
            if sample.get("engine_role") not in ENGINE_ROLES:
                raise Ewp003RuntimeError("ENGINE_ROLE_INVALID", str(sample.get("engine_role")))
            self._validate_sample_for_runtime(sample, binding)
        if config["strategy"] == "EXPLICIT_TEMPORAL_BOUNDARIES":
            return self._explicit(samples, binding, league_scope, config)
        return self._walk_forward(samples, binding, league_scope, config)

    @staticmethod
    def _validate_sample_for_runtime(sample: Mapping[str, Any], binding: DatasetBinding) -> None:
        required = ("match_id", "prediction_cutoff_at", "kickoff_at", "source_availability_at")
        if any(not sample.get(field) for field in required):
            raise Ewp003RuntimeError("SAMPLE_TIME_BINDING_MISSING", "match_id and cutoff/kickoff are required")
        cutoff = _parse_timestamp(sample["prediction_cutoff_at"])
        kickoff = _parse_timestamp(sample["kickoff_at"])
        if not cutoff < kickoff:
            raise Ewp003RuntimeError("FUTURE_LEAKAGE_DETECTED", "cutoff must precede kickoff")
        if _parse_timestamp(sample["source_availability_at"]) > cutoff:
            raise Ewp003RuntimeError("FUTURE_LEAKAGE_DETECTED", "source became available after cutoff")
        for field in ("dataset_id", "dataset_revision", "dataset_manifest_hash", "dataset_substantive_hash"):
            if field in sample and sample[field] != getattr(binding, field):
                raise Ewp003RuntimeError("MIXED_DATASET_REVISION", field)
        if "dataset_version" in sample and sample["dataset_version"] != binding.dataset_version:
            raise Ewp003RuntimeError("MIXED_DATASET_REVISION", "dataset_version")

    @staticmethod
    def _grouped(samples: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for sample in samples:
            groups[str(sample["match_id"])].append(sample)
        for group in groups.values():
            group.sort(key=_sample_sort_key)
        return dict(sorted(groups.items()))

    @staticmethod
    def _group_times(group: Sequence[Mapping[str, Any]]) -> tuple[datetime, datetime]:
        times = [_parse_timestamp(item["prediction_cutoff_at"]) for item in group]
        return min(times), max(times)

    @staticmethod
    def _check_partition_order(partitions: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        present = [name for name in ("train", "validation", "holdout") if partitions.get(name)]
        for left, right in zip(present, present[1:]):
            left_max = max(_parse_timestamp(item["prediction_cutoff_at"]) for item in partitions[left])
            right_min = min(_parse_timestamp(item["prediction_cutoff_at"]) for item in partitions[right])
            if not left_max < right_min:
                raise Ewp003RuntimeError("TEMPORAL_LEAKAGE_DETECTED", f"{left} is not strictly before {right}")

    def _explicit(self, samples: Sequence[Mapping[str, Any]], binding: DatasetBinding, league_scope: Mapping[str, Any], config: Mapping[str, Any]) -> SplitResult:
        required = self.strategy_contract.get("explicit_temporal_boundaries", {}).get("required_config_fields", ())
        missing = [field for field in required if field not in config]
        if missing:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", ",".join(missing))
        separation = _duration(config.get("minimum_chronological_separation"), "minimum_chronological_separation")
        if config.get("ordering_field") != "prediction_cutoff_at":
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "ordering_field must be prediction_cutoff_at")
        if config.get("identical_timestamp_tie_break") != ["match_id_group_key", "sample_id_within_group"]:
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "identical timestamp tie-break is not frozen")
        if config.get("partition_inclusivity_exclusivity") != self.strategy_contract.get("explicit_temporal_boundaries", {}).get("partition_inclusivity_exclusivity"):
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "partition inclusivity/exclusivity is not frozen")
        train_end = _parse_timestamp(config["train_end"])
        validation_start = _parse_timestamp(config["validation_start"])
        validation_end = _parse_timestamp(config["validation_end"])
        holdout_start = _parse_timestamp(config["holdout_start"])
        holdout_end = _parse_timestamp(config["holdout_end"])
        if not train_end + separation <= validation_start or not validation_end + separation <= holdout_start:
            raise Ewp003RuntimeError("SPLIT_CONFIG_OVERLAP", "declared boundaries violate separation")
        if validation_start > validation_end or holdout_start > holdout_end:
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "partition start must not follow end")
        grouped = self._grouped(samples)
        partitions: dict[str, list[Mapping[str, Any]]] = {"train": [], "validation": [], "holdout": []}
        for match_id, group in grouped.items():
            low, high = self._group_times(group)
            candidates = []
            if high <= train_end:
                candidates.append("train")
            if validation_start <= low and high <= validation_end:
                candidates.append("validation")
            if holdout_start <= low and high <= holdout_end:
                candidates.append("holdout")
            if len(candidates) != 1:
                raise Ewp003RuntimeError("SAME_MATCH_CROSSES_BOUNDARY", match_id)
            partitions[candidates[0]].extend(group)
        for group in partitions.values():
            group.sort(key=_sample_sort_key)
        if any(not partitions[name] for name in ("train", "validation", "holdout")):
            raise Ewp003RuntimeError("PARTITION_EMPTY", "all train, validation, and holdout partitions are required")
        self._check_partition_order(partitions)
        stable_boundaries = {
            "train_end": config["train_end"], "validation_start": config["validation_start"],
            "validation_end": config["validation_end"], "holdout_start": config["holdout_start"],
            "holdout_end": config["holdout_end"], "minimum_chronological_separation": config["minimum_chronological_separation"],
        }
        return self._result("EXPLICIT_TEMPORAL_BOUNDARIES", partitions, (), stable_boundaries, config, binding, league_scope)

    def _walk_forward(self, samples: Sequence[Mapping[str, Any]], binding: DatasetBinding, league_scope: Mapping[str, Any], config: Mapping[str, Any]) -> SplitResult:
        spec = self.strategy_contract.get("walk_forward_rolling_origin", {})
        required = spec.get("required_config_fields", ())
        missing = [field for field in required if field not in config]
        if missing:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", ",".join(missing))
        mode = config.get("mode")
        if mode not in {"expanding", "sliding"}:
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "mode must be expanding or sliding")
        if mode == "sliding" and "sliding_window_width" not in config:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", "sliding_window_width")
        if config.get("incomplete_final_fold_policy") not in {"REJECT", "DROP_INCOMPLETE_FINAL_FOLD"}:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", "incomplete_final_fold_policy")
        if config.get("same_match_grouping_policy") != "GROUP_BY_MATCH_ID_BEFORE_FOLD_ASSIGNMENT":
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "same-match grouping policy is required")
        if config.get("fold_level_minimum_readiness_policy") != "EACH_REQUIRED_FOLD_MUST_PASS_DECLARED_READINESS_RULE":
            raise Ewp003RuntimeError("SPLIT_CONFIG_INVALID", "fold-level readiness policy is required")
        train_period = _duration(config["initial_train_period"], "initial_train_period")
        origin_step = _duration(config["origin_step"], "origin_step")
        validation_horizon = _duration(config["validation_horizon"], "validation_horizon")
        holdout_horizon = _duration(config["holdout_horizon"], "holdout_horizon")
        window_width = _duration(config["sliding_window_width"], "sliding_window_width") if mode == "sliding" else None
        if mode == "sliding" and window_width is None:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", "sliding_window_width")
        grouped = self._grouped(samples)
        all_times = [_parse_timestamp(item["prediction_cutoff_at"]) for item in samples]
        first_origin = _parse_timestamp(config["first_origin_at"]) if config.get("first_origin_at") else min(all_times) + train_period
        latest = max(all_times)
        folds: list[dict[str, Any]] = []
        origin = first_origin
        while origin <= latest:
            validation_end = origin + validation_horizon
            holdout_start = validation_end
            holdout_end = holdout_start + holdout_horizon
            partition_groups: dict[str, list[Mapping[str, Any]]] = {"train": [], "validation": [], "holdout": []}
            for match_id, group in grouped.items():
                low, high = self._group_times(group)
                train_start = origin - window_width if mode == "sliding" and window_width else min(all_times)
                candidates = []
                if train_start <= low and high <= origin:
                    candidates.append("train")
                if origin < low and high <= validation_end:
                    candidates.append("validation")
                if holdout_start < low and high <= holdout_end:
                    candidates.append("holdout")
                if len(candidates) == 1:
                    partition_groups[candidates[0]].extend(group)
                elif len(candidates) > 1:
                    raise Ewp003RuntimeError("SAME_MATCH_CROSSES_FOLD", match_id)
            complete = all(partition_groups[name] for name in ("train", "validation", "holdout"))
            if complete:
                for group in partition_groups.values():
                    group.sort(key=_sample_sort_key)
                self._check_partition_order(partition_groups)
                folds.append({
                    "fold_index": len(folds) + 1,
                    "origin_at": origin.isoformat(),
                    "boundaries": {"train_start": train_start.isoformat(), "train_end": origin.isoformat(), "validation_start": (origin + timedelta(microseconds=1)).isoformat(), "validation_end": validation_end.isoformat(), "holdout_start": (holdout_start + timedelta(microseconds=1)).isoformat(), "holdout_end": holdout_end.isoformat()},
                    "partitions": {key: tuple(value) for key, value in partition_groups.items()},
                })
            elif config["incomplete_final_fold_policy"] == "REJECT" and origin + validation_horizon <= latest:
                raise Ewp003RuntimeError("INCOMPLETE_FINAL_FOLD", str(len(folds) + 1))
            origin += origin_step
        minimum_folds = config.get("minimum_folds")
        if not isinstance(minimum_folds, int) or isinstance(minimum_folds, bool) or minimum_folds <= 0:
            raise Ewp003RuntimeError("SPLIT_CONFIG_NOT_DECLARED", "minimum_folds")
        if len(folds) < minimum_folds:
            raise Ewp003RuntimeError("MINIMUM_FOLDS_NOT_MET", f"{len(folds)}<{minimum_folds}")
        first = folds[0]["partitions"]
        boundaries = {"walk_forward": {key: value for key, value in config.items() if key in required or key == "sliding_window_width" or key == "first_origin_at"}}
        return self._result("WALK_FORWARD_ROLLING_ORIGIN", first, tuple(folds), boundaries, config, binding, league_scope)

    def _result(self, strategy: str, partitions: Mapping[str, Sequence[Mapping[str, Any]]], folds: Sequence[Mapping[str, Any]], boundaries: Mapping[str, Any], config: Mapping[str, Any], binding: DatasetBinding, league_scope: Mapping[str, Any]) -> SplitResult:
        ordered = {key: tuple(sorted(value, key=_sample_sort_key)) for key, value in partitions.items()}
        config_hash = sha256_json(config)
        membership = {key: [_stable_ref(sample) for sample in ordered[key]] for key in ("train", "validation", "holdout")}
        substantive = {
            "dataset_identity_and_hashes": binding.as_dict(), "strategy": strategy, "boundaries": boundaries,
            "walk_forward_parameters": config if strategy == "WALK_FORWARD_ROLLING_ORIGIN" else {},
            "league_scope": league_scope, "grouping_rules": self.strategy_contract.get("grouping_contract", {}),
            "readiness_rule_version_and_hash": {"version": "prediction-training-readiness-rule@1.1.0"},
            "sample_membership_by_partition": membership,
        }
        return SplitResult(
            strategy=strategy, partitions=ordered, folds=tuple(folds), boundaries=boundaries,
            config_identity=f"{self.contract.get('$id')}#config", config_hash=config_hash,
            grouping_identity={"assignment_unit": "match_id", "grouping_root": "match_id", "cross_partition_action": "REJECT_SPLIT"},
            ordering_identity={"ordering_field": "prediction_cutoff_at", "tie_break": ["match_id_group_key", "sample_id_within_group"], "array_order": "PRESERVE_SEMANTIC_ORDER"},
            split_substantive_hash=sha256_json(substantive),
        )

    @staticmethod
    def formal_artifact(split: SplitResult, binding: DatasetBinding, readiness_rule_hash: str, *, revision: int = 1, supersedes: Optional[str] = None) -> dict[str, Any]:
        """Materialize the governed split schema only after a split is performable."""
        body: dict[str, Any] = {
            "split_artifact_id": "split-" + split.split_substantive_hash[7:39],
            "artifact_identity": "temporal-split-artifact@1.0.0",
            "dataset_id": binding.dataset_id,
            "dataset_revision": binding.dataset_revision,
            "dataset_manifest_hash": binding.dataset_manifest_hash,
            "dataset_substantive_hash": binding.dataset_substantive_hash,
            "strategy": split.strategy,
            "config_version": "prediction-training-temporal-split@1.1.0",
            "config_identity": split.config_identity,
            "config_hash": split.config_hash,
            "readiness_rule_hash": readiness_rule_hash,
            "holdout_usage_policy": {"fitting": "FORBIDDEN", "candidate_selection": "FORBIDDEN", "early_stopping": "FORBIDDEN"},
            "train_match_refs": sorted({str(item["match_id"]) for item in split.partitions["train"]}),
            "train_sample_refs": [_stable_ref(item) for item in split.partitions["train"]],
            "validation_match_refs": sorted({str(item["match_id"]) for item in split.partitions["validation"]}),
            "validation_sample_refs": [_stable_ref(item) for item in split.partitions["validation"]],
            "holdout_match_refs": sorted({str(item["match_id"]) for item in split.partitions["holdout"]}),
            "holdout_sample_refs": [_stable_ref(item) for item in split.partitions["holdout"]],
            "folds": [
                {
                    "fold_index": fold["fold_index"],
                    "origin_at": fold["origin_at"],
                    "boundaries": fold["boundaries"],
                    "train_sample_refs": [_stable_ref(item) for item in fold["partitions"]["train"]],
                    "validation_sample_refs": [_stable_ref(item) for item in fold["partitions"]["validation"]],
                    "holdout_sample_refs": [_stable_ref(item) for item in fold["partitions"]["holdout"]],
                }
                for fold in split.folds
            ],
            "boundaries": split.boundaries,
            "grouping_identity": split.grouping_identity,
            "ordering_identity": split.ordering_identity,
            "revision": revision,
            "supersedes": supersedes,
        }
        body["artifact_hash"] = sha256_json(body)
        return body


class TrainingReadinessEvaluator:
    """Evaluate evidence gates independently for each engine; never accuracy."""

    def __init__(self, contract: Mapping[str, Any], required_features: Sequence[str] = ()):
        self.contract = contract
        self.required_features = tuple(str(item) for item in required_features)
        self.rule = contract.get("minimum_sample_readiness_contract", {})
        self.minimums = dict(self.rule.get("class_minimums", {"train": 5, "validation": 3, "holdout": 3}))

    def evaluate(
        self,
        samples: Sequence[Mapping[str, Any]],
        binding: DatasetBinding,
        split: Optional[SplitResult],
        *,
        league_scope: Optional[Mapping[str, Any]],
        zero_data_reason: Optional[str] = None,
        dataset_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        counts = {role: {"total": 0, "eligible": 0, "partial": 0, "ineligible": 0, "blocked": 0, "usable": 0} for role in ENGINE_ROLES}
        for sample in samples:
            role = sample.get("engine_role")
            if role not in counts:
                continue
            counts[role]["total"] += 1
            state = sample.get("eligibility_state")
            if state == "ELIGIBLE":
                counts[role]["eligible"] += 1
            elif state == "PARTIALLY_ELIGIBLE":
                counts[role]["partial"] += 1
            elif state == "INELIGIBLE":
                counts[role]["ineligible"] += 1
            else:
                counts[role]["blocked"] += 1
        if split:
            for role in ENGINE_ROLES:
                counts[role]["usable"] = sum(1 for sample in samples if sample.get("engine_role") == role and sample.get("eligibility_state") == "ELIGIBLE" and any(_stable_sample_id(sample) == _stable_sample_id(item) for part in split.partitions.values() for item in part))
        if zero_data_reason or not samples:
            return self._zero_report(binding, counts, zero_data_reason or "TRAINING_DATA_INSUFFICIENT", league_scope, dataset_reason=dataset_reason)
        if split is None:
            raise Ewp003RuntimeError("SPLIT_NOT_AVAILABLE", "non-empty readiness evaluation requires a split")
        normalized_scope = validate_league_scope(league_scope, samples)
        per_class = {role: self._class_support(role, samples, split) for role in ENGINE_ROLES}
        temporal = self._temporal_coverage(split)
        league = self._league_coverage(samples, split, normalized_scope)
        feature = self._feature_coverage(samples, split)
        stability = self._stability(per_class, feature)
        same_match = self._same_match_check(split)
        future = self._future_check(samples, binding)
        reasons: set[str] = set()
        for state in (temporal["state"], league["state"], stability["state"], same_match["state"], future["state"]):
            if state != "PASS":
                reasons.add({"UNKNOWN": "READINESS_DIAGNOSTIC_UNKNOWN", "UNSTABLE": "STATISTICAL_STABILITY_UNSTABLE", "FAIL": "LEAKAGE_DETECTED"}.get(state, "TRAINING_DATA_INSUFFICIENT"))
        for role in ENGINE_ROLES:
            if counts[role]["usable"] == 0:
                reasons.add("TRAINING_DATA_INSUFFICIENT")
        readiness = "READY" if not reasons else "BLOCKED"
        per_engine_readiness = {}
        for role in ENGINE_ROLES:
            role_reasons = set()
            for window in per_class[role].values():
                if window["state"] != "PASS":
                    role_reasons.add("TRAINING_DATA_INSUFFICIENT" if window["state"] == "UNSTABLE" else "READINESS_DIAGNOSTIC_UNKNOWN")
            if feature["state"] != "PASS":
                role_reasons.add("REQUIRED_FEATURE_COVERAGE_INCOMPLETE" if feature["state"] == "UNSTABLE" else "READINESS_DIAGNOSTIC_UNKNOWN")
            if counts[role]["usable"] == 0:
                role_reasons.add("TRAINING_DATA_INSUFFICIENT")
            per_engine_readiness[role] = {"readiness_state": "READY" if not role_reasons else "BLOCKED", "reason_codes": sorted(role_reasons), "usable_samples": counts[role]["usable"]}
        stable = {
            "dataset_identity_and_hashes": binding.as_dict(),
            "split_strategy_and_config_identity_hash": {"strategy": split.strategy, "config_identity": split.config_identity, "config_hash": split.config_hash},
            "split_status": "PERFORMABLE", "readiness_state": readiness, "reason_codes": sorted(reasons),
            "per_engine_counts": counts, "per_engine_readiness": per_engine_readiness, "per_class_support_by_partition": per_class,
            "temporal_coverage": temporal, "league_coverage": league, "required_feature_coverage": feature,
            "statistical_stability_diagnostic_state": stability, "same_match_leakage_check": same_match,
            "future_leakage_check": future, "split_artifact_generated": False,
            "holdout_usage_policy": {"fitting": "FORBIDDEN", "candidate_selection": "FORBIDDEN", "early_stopping": "FORBIDDEN"},
        }
        report = dict(stable, report_identity="training-readiness-report@1.0.0", report_revision="r002", model_accuracy=None)
        report["deterministic_report_hash"] = sha256_json(stable)
        report["canonical_hash"] = _hash_body(report, ("canonical_hash",))
        return report

    def _zero_report(self, binding: DatasetBinding, counts: Mapping[str, Any], reason: str, league_scope: Optional[Mapping[str, Any]], *, dataset_reason: Optional[str] = None) -> dict[str, Any]:
        stable = {
            "dataset_identity_and_hashes": binding.as_dict(),
            "split_strategy_and_config_identity_hash": {"strategy": "NOT_SELECTED", "config_identity": self.contract.get("$id"), "config_hash": self.contract.get("canonical_hash"), "explicit_config_required": True},
            "split_status": "NOT_PERFORMABLE", "readiness_state": "BLOCKED", "reason_codes": [reason],
            "per_engine_counts": counts,
            "per_engine_readiness": {role: {"readiness_state": "BLOCKED", "reason_codes": [reason], "usable_samples": 0} for role in ENGINE_ROLES},
            "per_class_support_by_partition": {role: "NOT_AVAILABLE_NO_PARTITIONS" for role in ENGINE_ROLES},
            "temporal_coverage": "UNKNOWN_NO_PARTITIONS", "league_coverage": "LEAGUE_SCOPE_NOT_DECLARED" if league_scope is None else "UNKNOWN_NO_SAMPLES",
            "required_feature_coverage": "UNKNOWN_NO_SAMPLES", "statistical_stability_diagnostic_state": "UNKNOWN",
            "same_match_leakage_check": "PASS_EMPTY_DATASET", "future_leakage_check": "PASS_EMPTY_DATASET",
            "split_artifact_generated": False, "formal_split_artifact_ref": None,
        }
        report = dict(stable, report_identity="training-readiness-report@1.0.0", report_revision="r002", model_accuracy=None)
        report["sample_counts"] = {"candidate_samples": 0, "usable_samples": 0, "per_engine_samples": {role: 0 for role in ENGINE_ROLES}, "reason": dataset_reason or reason}
        report["deterministic_report_hash"] = sha256_json(stable)
        report["canonical_hash"] = _hash_body(report, ("canonical_hash",))
        return report

    def _class_support(self, role: str, samples: Sequence[Mapping[str, Any]], split: SplitResult) -> dict[str, Any]:
        declared = list(DECLARED_CLASSES[role])
        output: dict[str, Any] = {}
        for partition, members in split.partitions.items():
            eligible = [sample for sample in members if sample.get("engine_role") == role and sample.get("eligibility_state") == "ELIGIBLE"]
            support = Counter(_sample_class(sample, role) for sample in eligible)
            unknown = sum(1 for sample in eligible if _sample_class(sample, role) is None)
            output[partition] = {"eligible_samples": len(eligible), "declared_classes": declared, "support": {item: int(support.get(item, 0)) for item in declared}, "unknown_class_samples": unknown, "class_rates": {item: (support.get(item, 0) / len(eligible) if eligible else None) for item in declared}, "state": "UNKNOWN" if not eligible or unknown else ("PASS" if all(support.get(item, 0) >= self.minimums[partition] for item in declared) else "UNSTABLE")}
        return output

    @staticmethod
    def _temporal_coverage(split: SplitResult) -> dict[str, Any]:
        if split.strategy == "WALK_FORWARD_ROLLING_ORIGIN":
            return {"state": "PASS" if split.folds else "UNKNOWN", "fold_count": len(split.folds), "folds": [{"fold_index": fold["fold_index"], "train_samples": len(fold["partitions"]["train"]), "validation_samples": len(fold["partitions"]["validation"]), "holdout_samples": len(fold["partitions"]["holdout"])} for fold in split.folds]}
        return {"state": "PASS", "partitions": {key: {"sample_count": len(value), "min_cutoff": min((_parse_timestamp(item["prediction_cutoff_at"]) for item in value), default=None).isoformat() if value else None, "max_cutoff": max((_parse_timestamp(item["prediction_cutoff_at"]) for item in value), default=None).isoformat() if value else None} for key, value in split.partitions.items()}}

    @staticmethod
    def _league_coverage(samples: Sequence[Mapping[str, Any]], split: SplitResult, scope: Mapping[str, Any]) -> dict[str, Any]:
        expected = set(scope["league_ids"])
        partitions: dict[str, Any] = {}
        for name, members in split.partitions.items():
            observed = {str(item.get("league_id", item.get("competition_id"))) for item in members}
            partitions[name] = {"observed": sorted(observed), "missing": sorted(expected - observed), "state": "PASS" if expected <= observed else "UNSTABLE"}
        return {"scope_type": scope["scope_type"], "declared_league_ids": sorted(expected), "partitions": partitions, "state": "PASS" if all(item["state"] == "PASS" for item in partitions.values()) else "UNSTABLE"}

    def _feature_coverage(self, samples: Sequence[Mapping[str, Any]], split: SplitResult) -> dict[str, Any]:
        if not self.required_features:
            return {"state": "UNKNOWN", "reason": "REQUIRED_FEATURE_SCOPE_NOT_DECLARED"}
        partitions: dict[str, Any] = {}
        for name, members in split.partitions.items():
            eligible = [item for item in members if item.get("eligibility_state") == "ELIGIBLE"]
            availability = {feature: sum(1 for item in eligible if _declared_feature_available(item, feature) is True) / len(eligible) if eligible else None for feature in self.required_features}
            all_available = [item for item in eligible if all(_declared_feature_available(item, feature) is True for feature in self.required_features)]
            partitions[name] = {"eligible_samples": len(eligible), "required_features": list(self.required_features), "availability_by_feature": availability, "all_required_features_availability": len(all_available) / len(eligible) if eligible else None, "state": "UNKNOWN" if not eligible or any(value is None for value in availability.values()) else ("PASS" if len(all_available) == len(eligible) else "UNSTABLE")}
        return {"state": "PASS" if all(item["state"] == "PASS" for item in partitions.values()) else ("UNKNOWN" if any(item["state"] == "UNKNOWN" for item in partitions.values()) else "UNSTABLE"), "partitions": partitions}

    def _stability(self, per_class: Mapping[str, Any], feature: Mapping[str, Any]) -> dict[str, Any]:
        states = [window["state"] for role in per_class.values() for window in role.values()]
        states.append(feature["state"])
        if all(state == "PASS" for state in states):
            return {"state": "PASS", "rule": "STRUCTURAL_ONLY_UNTIL_NUMERIC_THRESHOLD_APPROVED"}
        return {"state": "UNKNOWN" if "UNKNOWN" in states else "UNSTABLE", "rule": "STRUCTURAL_ONLY_UNTIL_NUMERIC_THRESHOLD_APPROVED", "blocking_windows": states.count("UNKNOWN") + states.count("UNSTABLE")}

    @staticmethod
    def _same_match_check(split: SplitResult) -> dict[str, Any]:
        for name, members in split.partitions.items():
            matches = [str(item["match_id"]) for item in members]
            if len(matches) != len(set(matches)) and len({(str(item["match_id"]), name) for item in members}) != len(set((str(item["match_id"]), name) for item in members)):
                return {"state": "FAIL", "reason": "SAME_MATCH_CROSS_PARTITION"}
        seen: dict[str, str] = {}
        for name, members in split.partitions.items():
            for item in members:
                match_id = str(item["match_id"])
                if match_id in seen and seen[match_id] != name:
                    return {"state": "FAIL", "reason": "SAME_MATCH_CROSS_PARTITION"}
                seen[match_id] = name
        return {"state": "PASS", "grouping_root": "match_id"}

    @staticmethod
    def _future_check(samples: Sequence[Mapping[str, Any]], binding: DatasetBinding) -> dict[str, Any]:
        for sample in samples:
            if sample.get("source_availability_at") is not None and _parse_timestamp(sample["source_availability_at"]) > _parse_timestamp(sample["prediction_cutoff_at"]):
                return {"state": "FAIL", "reason": "FUTURE_DATA_AT_CUTOFF"}
            if sample.get("dataset_revision") is not None and sample.get("dataset_revision") != binding.dataset_revision:
                return {"state": "FAIL", "reason": "MIXED_DATASET_REVISION"}
        return {"state": "PASS", "as_of_predicate": "source_availability_at <= prediction_cutoff_at < kickoff_at"}


class Ewp003Runtime:
    """Authorized EWP-003 façade for current approved data and report output."""

    def __init__(self, project_root: str | Path = DEFAULT_PROJECT_ROOT, *, execution_manifest: Optional[Mapping[str, Any]] = None, config_root: Optional[str | Path] = None, allow_test_root: bool = False):
        self.project_root = Path(project_root).resolve()
        if not allow_test_root and self.project_root.drive.upper() != "F:":
            raise Ewp003RuntimeError("F_DRIVE_REQUIRED", "formal EWP-003 runtime must remain on F:")
        self.config_root = Path(config_root).resolve() if config_root else self.project_root / "config" / "prediction_training"
        self.contract = self._load_json(self.config_root / "v4_batch15_ewp003_temporal_split_contract.json")
        self._verify_document_hash(self.contract, "canonical_hash")
        self.execution_manifest = dict(execution_manifest) if execution_manifest is not None else self._load_json(self.config_root / "v4_batch15_ewp003_execution_manifest.json")
        self._validate_execution()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _verify_document_hash(document: Mapping[str, Any], field: str) -> None:
        value = document.get(field)
        if not isinstance(value, str) or not HASH_RE.fullmatch(value) or value != _hash_body(document, (field,)):
            raise Ewp003RuntimeError("HASH_INVALID", field)

    def _validate_execution(self) -> None:
        manifest = self.execution_manifest
        if manifest.get("work_package_id") != "B15-EWP-003" or manifest.get("execution_authorized") is not True:
            raise Ewp003RuntimeError("EWP003_NOT_AUTHORIZED", "EWP-003 execution must be explicitly authorized")
        if manifest.get("downstream_execution_authorized") is not False:
            raise Ewp003RuntimeError("DOWNSTREAM_AUTHORIZATION_LEAK", "downstream work packages must remain unauthorized")
        forbidden = set(manifest.get("forbidden_work_packages", ()))
        if not {"B15-EWP-004", "B15-EWP-005"}.issubset(forbidden):
            raise Ewp003RuntimeError("DEPENDENCY_BOUNDARY_INVALID", "EWP-004 and EWP-005 must be forbidden")
        if manifest.get("contract_hash") != self.contract.get("canonical_hash"):
            raise Ewp003RuntimeError("CONTRACT_HASH_MISMATCH", "execution manifest is not bound to the frozen contract")

    def _approved_path(self, relative: str) -> Path:
        root = (self.project_root / "approved_data" / "training_datasets").resolve()
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise Ewp003RuntimeError("APPROVED_PATH_ESCAPE", relative) from exc
        return path

    def load_dataset(self, manifest_path: str | Path = DEFAULT_DATASET_MANIFEST, *, replay_mode: str = "CURRENT_ACTIVE", expected_binding: Optional[Mapping[str, Any]] = None) -> tuple[DatasetBinding, list[Mapping[str, Any]], Mapping[str, Any]]:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = (self.project_root / path).resolve()
        root = (self.project_root / "approved_data" / "training_datasets").resolve()
        try:
            path.relative_to(root / "manifests")
        except ValueError as exc:
            raise Ewp003RuntimeError("APPROVED_PATH_REQUIRED", str(path)) from exc
        manifest = self._load_json(path)
        self._verify_document_hash(manifest, "manifest_hash")
        if manifest.get("manifest_type") != "B15-EWP-002-DATASET-MANIFEST":
            raise Ewp003RuntimeError("DATASET_MANIFEST_INVALID", "wrong dataset manifest type")
        artifact_path = self._approved_path(str(manifest.get("dataset_artifact_ref", "")))
        artifact = self._load_json(artifact_path)
        artifact_hash = artifact.get("artifact_hash")
        if artifact_hash != manifest.get("dataset_artifact_hash") or artifact_hash != _hash_body(artifact, ("artifact_hash",)):
            raise Ewp003RuntimeError("DATASET_ARTIFACT_HASH_MISMATCH", str(artifact_path))
        dataset_id = str(manifest.get("dataset_id"))
        revision = f"r{int(manifest.get('revision', 0)):03d}"
        siblings = []
        for candidate in (path.parent).glob(f"{dataset_id}-r*.json"):
            try:
                siblings.append(self._load_json(candidate))
            except (OSError, json.JSONDecodeError):
                continue
        max_revision = max((int(item.get("revision", 0)) for item in siblings), default=int(manifest.get("revision", 0)))
        active = manifest.get("supersedes") in (None, "") and int(manifest.get("revision", 0)) == max_revision
        if replay_mode == "CURRENT_ACTIVE" and not active:
            raise Ewp003RuntimeError("SUPERSEDED_DATASET_REVISION", revision)
        if replay_mode != "CURRENT_ACTIVE":
            if replay_mode != "HISTORICAL_REPLAY" or not isinstance(expected_binding, Mapping):
                raise Ewp003RuntimeError("EXPLICIT_REPLAY_IDENTITY_REQUIRED", "historical replay requires exact identity")
            for field in ("dataset_id", "dataset_revision", "dataset_manifest_hash", "dataset_substantive_hash"):
                if expected_binding.get(field) != (dataset_id if field == "dataset_id" else revision if field == "dataset_revision" else manifest.get(field)):
                    raise Ewp003RuntimeError("REPLAY_IDENTITY_MISMATCH", field)
        binding = DatasetBinding(dataset_id, revision, str(manifest["manifest_hash"]), str(manifest["dataset_substantive_hash"]), str(manifest["dataset_version"]), active, manifest.get("supersedes"))
        if dataset_id != CURRENT_DATASET_ID and not self.execution_manifest.get("test_fixture_mode", False):
            raise Ewp003RuntimeError("DATASET_NOT_APPROVED", dataset_id)
        samples = list(manifest.get("sample_records", ()))
        if artifact.get("sample_count") != len(artifact.get("sample_refs", ())):
            raise Ewp003RuntimeError("DATASET_ARTIFACT_SAMPLE_COUNT_INVALID", dataset_id)
        return binding, samples, manifest

    def run(self, *, manifest_path: str | Path = DEFAULT_DATASET_MANIFEST, split_config: Optional[Mapping[str, Any]] = None, required_features: Sequence[str] = (), replay_mode: str = "CURRENT_ACTIVE", expected_binding: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        return self.run_detailed(manifest_path=manifest_path, split_config=split_config, required_features=required_features, replay_mode=replay_mode, expected_binding=expected_binding)["report"]

    def run_detailed(self, *, manifest_path: str | Path = DEFAULT_DATASET_MANIFEST, split_config: Optional[Mapping[str, Any]] = None, required_features: Sequence[str] = (), replay_mode: str = "CURRENT_ACTIVE", expected_binding: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        binding, samples, manifest = self.load_dataset(manifest_path, replay_mode=replay_mode, expected_binding=expected_binding)
        scope = manifest.get("league_scope", manifest.get("league_scope_declaration"))
        if not samples:
            return {"report": TrainingReadinessEvaluator(self.contract, required_features).evaluate(samples, binding, None, league_scope=scope, zero_data_reason="TRAINING_DATA_INSUFFICIENT", dataset_reason=manifest.get("zero_archive_reason")), "split_artifact": None}
        normalized_scope = validate_league_scope(scope, samples)
        split = TemporalSplitBuilder(self.contract, split_config).build(samples, binding, normalized_scope)
        report = TrainingReadinessEvaluator(self.contract, required_features).evaluate(samples, binding, split, league_scope=normalized_scope)
        artifact = TemporalSplitBuilder.formal_artifact(split, binding, sha256_json(self.contract.get("minimum_sample_readiness_contract", {})))
        report["split_artifact_generated"] = True
        report["formal_split_artifact_ref"] = f"splits/{binding.dataset_id}-{binding.dataset_revision}-{artifact['split_artifact_id']}.json"
        stable_report = {key: value for key, value in report.items() if key not in {"canonical_hash", "deterministic_report_hash"}}
        report["deterministic_report_hash"] = sha256_json(stable_report)
        report["canonical_hash"] = _hash_body(report, ("canonical_hash",))
        return {"report": report, "split_artifact": artifact}


__all__ = [
    "CURRENT_DATASET_ID", "DatasetBinding", "Ewp003Runtime", "Ewp003RuntimeError", "SplitResult",
    "TemporalSplitBuilder", "TrainingReadinessEvaluator", "validate_league_scope",
]
