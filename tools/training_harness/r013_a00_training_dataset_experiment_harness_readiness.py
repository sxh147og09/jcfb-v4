"""R013-A00: synthetic-only training dataset and experiment harness readiness.

The harness validates contracts, point-in-time construction, independent
Five-Play dataset bindings, temporal/rights/revision gates, chronological
splitting, leakage detection, experiment reproducibility, evaluation,
calibration, and baseline interfaces.  It deliberately never consumes real
training data, fits a model, or writes a model artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(r"F:\Projects\jcfb-v4")
DEFAULT_OUTPUT = ROOT / "work" / "r013_a00_training_dataset_experiment_harness"
DEFAULT_REPORT = ROOT / "docs" / "R013-A00_training_dataset_experiment_harness_readiness_report.md"
DEFAULT_CONTRACT = ROOT / "config" / "prediction_training" / "R013-A00_training_dataset_experiment_harness_contract_v1.0.0.json"
HARNESS_ID = "R013-A00"
HARNESS_STATUS = "HARNESS_READY_NO_REAL_DATA"
BUILDER_VERSION = "r013-a00-pit-dataset-builder@1.0.0"
HASH_RULE = "CANONICAL_JSON_HASH_V1"
SEED = 20260917
PLAY_TYPES = ("SPF", "RQSPF", "TOTAL_GOALS", "SCORE", "HTFT")
PARTITIONS = ("train", "validation", "test")
FEATURE_NAMES = ("home_form_index", "away_form_index", "home_strength", "away_strength", "market_context")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone-aware timestamp required: {value}")
    return parsed


def _label(play: str, index: int) -> str:
    if play in {"SPF", "RQSPF"}:
        return ("H", "D", "A")[index % 3]
    if play == "TOTAL_GOALS":
        return ("0", "1", "2", "3", "4", "5", "6", "7+")[index % 8]
    if play == "SCORE":
        return ("0-0", "1-0", "1-1", "2-1", "2-2")[index % 5]
    return ("H/H", "H/D", "D/H", "D/D", "A/H", "A/A")[index % 6]


def _match_groups() -> list[dict[str, Any]]:
    tz = timezone(timedelta(hours=8))
    groups = []
    for index in range(15):
        kickoff = datetime(2026, 10, 1, 20, 0, tzinfo=tz) + timedelta(days=index)
        groups.append({
            "match_id": f"SYN-R013-M{index + 1:03d}",
            "competition": "synthetic.epl",
            "season": "2026-27",
            "match_date": kickoff.date().isoformat(),
            "kickoff_at": _iso(kickoff),
            "home_team": f"Synthetic Home {index + 1:02d}",
            "away_team": f"Synthetic Away {index + 1:02d}",
            "match_identity_key": f"synthetic.epl|2026-27|{kickoff.date().isoformat()}|synthetic-home-{index + 1:02d}|synthetic-away-{index + 1:02d}",
        })
    return groups


def _make_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for index, match in enumerate(_match_groups()):
        kickoff = _parse(match["kickoff_at"])
        cutoff = kickoff - timedelta(minutes=60)
        available = cutoff - timedelta(minutes=30)
        observed_label = kickoff + timedelta(minutes=120)
        feature_snapshot = {
            "home_form_index": {"value": round(0.50 + index * 0.01, 4), "available_at": _iso(available)},
            "away_form_index": {"value": round(0.45 + index * 0.008, 4), "available_at": _iso(available)},
            "home_strength": {"value": 100 + index, "available_at": _iso(available)},
            "away_strength": {"value": 98 + index, "available_at": _iso(available)},
            "market_context": {"value": "SYNTHETIC_PREMATCH_CONTEXT", "available_at": _iso(available)},
        }
        for play in PLAY_TYPES:
            body = {
                "sample_id": f"{match['match_id']}::{play}",
                "match_id": match["match_id"],
                "market_type": play,
                "engine_role": play,
                "competition": match["competition"],
                "season": match["season"],
                "match_date": match["match_date"],
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "match_identity_key": match["match_identity_key"],
                "prediction_cutoff_at": _iso(cutoff),
                "kickoff_at": match["kickoff_at"],
                "source_availability_at": _iso(available),
                "feature_snapshot": feature_snapshot,
                "feature_names": list(FEATURE_NAMES),
                "label": {"value": _label(play, index), "observed_at": _iso(observed_label)},
                "rights": {"rights_status": "COMPANY_OWNED", "synthetic": True, "real_source": False, "formal_training_allowed": False},
                "revision": {"revision_id": "r001", "revision_order_status": "ORDER_PROVEN", "supersedes": None},
                "source": {"provider": "synthetic_fixture", "source_reference": f"synthetic://R013-A00/{match['match_id']}/{play}"},
            }
            body["feature_snapshot_hash"] = _hash(feature_snapshot)
            body["sample_hash"] = _hash(body)
            samples.append(body)
    return samples


def _training_contract() -> dict[str, Any]:
    return {
        "contract_id": "R013-A00-TRAINING-DATASET",
        "version": "1.0.0",
        "status": "HARNESS_ONLY",
        "synthetic_only": True,
        "real_training_data_allowed": False,
        "formal_model_training_allowed": False,
        "model_artifact_creation_allowed": False,
        "required_identity": ["sample_id", "match_id", "market_type", "engine_role", "match_identity_key"],
        "required_temporal": ["source_availability_at", "prediction_cutoff_at", "kickoff_at", "label.observed_at"],
        "feature_label_separation": True,
        "raw_to_training_direct_path": False,
    }


def _play_contracts() -> dict[str, Any]:
    classes = {
        "SPF": ["H", "D", "A"],
        "RQSPF": ["H", "D", "A"],
        "TOTAL_GOALS": ["0", "1", "2", "3", "4", "5", "6", "7+"],
        "SCORE": ["selection", "raw_odds", "normalized_odds", "source_selection_identity"],
        "HTFT": ["H/H", "H/D", "H/A", "D/H", "D/D", "D/A", "A/H", "A/D", "A/A"],
    }
    return {play: {"dataset_contract_id": f"R013-A00-{play}", "market_type": play, "engine_role": play, "classes_or_fields": values, "independent_dataset": True, "cross_play_feature_join": False, "target_leakage_forbidden": True} for play, values in classes.items()}


def _pit_builder(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    built = []
    failures = []
    for sample in samples:
        cutoff = _parse(sample["prediction_cutoff_at"])
        kickoff = _parse(sample["kickoff_at"])
        available = _parse(sample["source_availability_at"])
        label_observed = _parse(sample["label"]["observed_at"])
        temporal_pass = available <= cutoff < kickoff and label_observed > kickoff
        features_pass = all(_parse(field["available_at"]) <= cutoff for field in sample["feature_snapshot"].values())
        identity_pass = all(sample.get(field) for field in ("sample_id", "match_id", "market_type", "engine_role", "match_identity_key"))
        rights_pass = sample["rights"]["synthetic"] is True and sample["rights"]["real_source"] is False and sample["rights"]["formal_training_allowed"] is False
        revision_pass = sample["revision"]["revision_id"] == "r001" and sample["revision"]["revision_order_status"] == "ORDER_PROVEN" and sample["revision"]["supersedes"] is None
        hash_pass = sample["sample_hash"] == _hash({key: value for key, value in sample.items() if key != "sample_hash"})
        if not temporal_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "TEMPORAL", "reason": "feature or label violates point-in-time boundary"})
        if not features_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "FEATURE_AVAILABILITY", "reason": "feature observed after cutoff"})
        if not identity_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "IDENTITY", "reason": "required identity missing"})
        if not rights_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "RIGHTS", "reason": "synthetic rights boundary violated"})
        if not revision_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "REVISION", "reason": "revision lineage unresolved"})
        if not hash_pass:
            failures.append({"sample_id": sample["sample_id"], "gate": "HASH", "reason": "sample hash mismatch"})
        built.append({
            "sample_id": sample["sample_id"],
            "match_id": sample["match_id"],
            "market_type": sample["market_type"],
            "engine_role": sample["engine_role"],
            "prediction_cutoff_at": sample["prediction_cutoff_at"],
            "kickoff_at": sample["kickoff_at"],
            "feature_snapshot": sample["feature_snapshot"],
            "feature_snapshot_hash": sample["feature_snapshot_hash"],
            "label": sample["label"],
            "sample_hash": sample["sample_hash"],
            "gates": {"temporal": temporal_pass and features_pass, "rights": rights_pass, "revision": revision_pass, "identity": identity_pass, "hash": hash_pass},
            "harness_eligible": temporal_pass and features_pass and rights_pass and revision_pass and identity_pass and hash_pass,
            "formal_training_eligible": False,
        })
    return built, {"status": "PASS" if not failures else "FAIL", "failures": failures, "failure_count": len(failures)}


def _split_policy() -> dict[str, Any]:
    return {
        "contract_id": "R013-A00-SPLIT-POLICY",
        "strategy": "GROUPED_CHRONOLOGICAL_SPLIT",
        "random_split": "FORBIDDEN",
        "group_key": "match_id",
        "ordering": ["prediction_cutoff_at", "match_id", "sample_id"],
        "partition_ratios": {"train": 1 / 3, "validation": 1 / 3, "test": 1 / 3},
        "partition_count_by_group": {"train": 5, "validation": 5, "test": 5},
        "strict_temporal_relations": ["max(train.prediction_cutoff_at) < min(validation.prediction_cutoff_at)", "max(validation.prediction_cutoff_at) < min(test.prediction_cutoff_at)"],
        "same_match_cross_partition": "FORBIDDEN",
        "default_strategy": None,
        "missing_config_action": "FAIL_CLOSED",
    }


def _split(samples: list[dict[str, Any]]) -> dict[str, Any]:
    groups = sorted({sample["match_id"] for sample in samples}, key=lambda match_id: min(sample["prediction_cutoff_at"] for sample in samples if sample["match_id"] == match_id))
    group_partitions = {match_id: PARTITIONS[index // 5] for index, match_id in enumerate(groups)}
    partitions: dict[str, list[dict[str, Any]]] = {partition: [] for partition in PARTITIONS}
    for sample in samples:
        partitions[group_partitions[sample["match_id"]]].append(sample)
    result = {"strategy": "GROUPED_CHRONOLOGICAL_SPLIT", "group_key": "match_id", "group_partitions": group_partitions, "partitions": {key: sorted(value, key=lambda sample: (sample["prediction_cutoff_at"], sample["sample_id"])) for key, value in partitions.items()}, "random_split_used": False}
    result["split_hash"] = _hash(result)
    return result


def _leakage_scan(split: dict[str, Any]) -> dict[str, Any]:
    findings = []
    all_samples = [sample for partition in split["partitions"].values() for sample in partition]
    sample_ids = [sample["sample_id"] for sample in all_samples]
    if len(sample_ids) != len(set(sample_ids)):
        findings.append({"code": "DUPLICATE_SAMPLE_ID", "severity": "ERROR"})
    for sample in all_samples:
        cutoff = _parse(sample["prediction_cutoff_at"])
        if any(_parse(field["available_at"]) > cutoff for field in sample["feature_snapshot"].values()):
            findings.append({"code": "FUTURE_FEATURE", "sample_id": sample["sample_id"], "severity": "ERROR"})
        if _parse(sample["label"]["observed_at"]) <= cutoff:
            findings.append({"code": "LABEL_BEFORE_CUTOFF", "sample_id": sample["sample_id"], "severity": "ERROR"})
        if any(key in {"label", "final_score", "post_match_result", "settlement"} for key in sample["feature_snapshot"]):
            findings.append({"code": "TARGET_FIELD_IN_FEATURES", "sample_id": sample["sample_id"], "severity": "ERROR"})
    for left_index, left in enumerate(PARTITIONS):
        left_matches = {sample["match_id"] for sample in split["partitions"][left]}
        for right in PARTITIONS[left_index + 1:]:
            overlap = left_matches & {sample["match_id"] for sample in split["partitions"][right]}
            if overlap:
                findings.append({"code": "MATCH_GROUP_CROSS_PARTITION", "partitions": [left, right], "match_ids": sorted(overlap), "severity": "ERROR"})
    return {"status": "PASS" if not findings else "FAIL", "leakage_count": len(findings), "findings": findings, "scanner_version": "r013-a00-leakage-scanner@1.0.0"}


def _evaluation_contracts() -> dict[str, Any]:
    return {
        "evaluation_contract": {"status": "CONTRACT_ONLY", "metrics": ["accuracy", "log_loss", "brier_score", "macro_f1", "top_k_accuracy"], "evaluation_partition": "test", "model_artifact_required": True, "synthetic_results_formal": False},
        "calibration_contract": {"status": "CONTRACT_ONLY", "methods": ["identity", "temperature_scaling", "isotonic"], "metrics": ["expected_calibration_error", "maximum_calibration_error", "reliability_bins"], "fit_partition": "validation", "test_calibration_evaluation": True, "model_artifact_creation": False},
        "baseline_contract": {"status": "READY_FOR_HARNESS_ONLY", "baselines": ["majority_class", "empirical_prior", "uniform_reference"], "metrics": ["accuracy", "log_loss", "brier_score", "expected_calibration_error"], "baseline_results_written": False, "formal_training": False},
    }


def _build(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = _make_samples()
    built, build_validation = _pit_builder(samples)
    if build_validation["status"] != "PASS":
        raise AssertionError(build_validation)
    split = _split(built)
    leakage = _leakage_scan(split)
    if leakage["status"] != "PASS":
        raise AssertionError(leakage)
    split_repeat = _split(built)
    reproducibility = {"status": "PASS" if split["split_hash"] == split_repeat["split_hash"] and _hash(built) == _hash(_pit_builder(samples)[0]) else "FAIL", "seed": SEED, "hash_rule": HASH_RULE, "builder_version": BUILDER_VERSION, "ordering": ["prediction_cutoff_at", "match_id", "sample_id"], "volatile_fields_excluded": ["execution_started_at", "execution_completed_at", "host", "pid", "duration"], "dataset_substantive_hash": _hash(built), "split_hash": split["split_hash"]}
    contracts = _training_contract()
    _write(output_dir / "training_dataset_contract.json", contracts)
    _write(output_dir / "point_in_time_dataset_builder.json", {"builder_id": BUILDER_VERSION, "status": "PASS", "source_boundary": "synthetic_fixture_only", "raw_to_training_direct_path": False, "gates": ["temporal", "rights", "revision", "identity", "hash"], "formal_training": False})
    _write(output_dir / "five_play_independent_dataset_contracts.json", _play_contracts())
    _write(output_dir / "rights_gate_report.json", {"status": "PASS", "synthetic_only": True, "real_source_rights_proven": False, "formal_training_allowed": False, "fail_closed_unknown_rights": True, "checked_count": len(built), "passed_count": len(built)})
    _write(output_dir / "temporal_gate_report.json", {"status": "PASS", "checked_count": len(built), "passed_count": sum(sample["gates"]["temporal"] for sample in built), "point_in_time_rule": "all feature availability <= prediction cutoff < kickoff < label observation"})
    _write(output_dir / "revision_gate_report.json", {"status": "PASS", "checked_count": len(built), "passed_count": sum(sample["gates"]["revision"] for sample in built), "superseded_revision_consumption": "FORBIDDEN"})
    _write(output_dir / "synthetic_dataset_manifest.json", {"manifest_type": "R013-A00-SYNTHETIC-HARNESS", "synthetic_only": True, "sample_count": len(built), "match_group_count": len({sample["match_id"] for sample in built}), "play_types": list(PLAY_TYPES), "real_data_record_count": 0, "formal_training_allowed": False, "dataset_substantive_hash": reproducibility["dataset_substantive_hash"]})
    _write(output_dir / "synthetic_dataset.json", {"synthetic_only": True, "records": samples, "formal_training_allowed": False, "model_artifact_creation": False})
    _write(output_dir / "dataset_build_result.json", {"status": "PASS", "builder_version": BUILDER_VERSION, "sample_count": len(built), "harness_eligible_count": sum(sample["harness_eligible"] for sample in built), "formal_training_eligible_count": 0, "dataset": built, "validation": build_validation})
    _write(output_dir / "split_policy.json", _split_policy())
    _write(output_dir / "split_result.json", split)
    _write(output_dir / "leakage_scan_report.json", leakage)
    _write(output_dir / "experiment_manifest.json", {"experiment_id": "R013-A00-SYNTHETIC-EXPERIMENT-001", "status": HARNESS_STATUS, "dataset_manifest_hash": _hash(_read_json(output_dir / "synthetic_dataset_manifest.json")), "dataset_substantive_hash": reproducibility["dataset_substantive_hash"], "split_hash": split["split_hash"], "seed": SEED, "engine_roles": list(PLAY_TYPES), "model_artifact_creation": False, "real_training_data": False})
    _write(output_dir / "reproducibility_contract.json", reproducibility)
    evaluation = _evaluation_contracts()
    _write(output_dir / "evaluation_contract.json", evaluation["evaluation_contract"])
    _write(output_dir / "calibration_contract.json", evaluation["calibration_contract"])
    _write(output_dir / "baseline_contract.json", evaluation["baseline_contract"])
    metrics = {"SYNTHETIC_ONLY": True, "REAL_DATA_RECORD_COUNT": 0, "SYNTHETIC_SAMPLE_COUNT": len(built), "PLAY_CONTRACT_COUNT": len(PLAY_TYPES), "PIT_BUILT_COUNT": len(built), "PIT_TEMPORAL_PASS_COUNT": sum(sample["gates"]["temporal"] for sample in built), "RIGHTS_GATE_PASS_COUNT": len(built), "REVISION_GATE_PASS_COUNT": sum(sample["gates"]["revision"] for sample in built), "IDENTITY_GATE_PASS_COUNT": sum(sample["gates"]["identity"] for sample in built), "HASH_GATE_PASS_COUNT": sum(sample["gates"]["hash"] for sample in built), "LEAKAGE_COUNT": leakage["leakage_count"], "TRAIN_SAMPLE_COUNT": len(split["partitions"]["train"]), "VALIDATION_SAMPLE_COUNT": len(split["partitions"]["validation"]), "TEST_SAMPLE_COUNT": len(split["partitions"]["test"]), "MODEL_ARTIFACT_COUNT": 0, "FORMAL_MODEL_TRAINING": False, "TRAINING_HARNESS_STATUS": HARNESS_STATUS}
    _write(output_dir / "metrics.json", metrics)
    result = {"run_id": HARNESS_ID, "final_status": "PASS", "TRAINING_HARNESS_STATUS": HARNESS_STATUS, "SYNTHETIC_ONLY": True, "REAL_TRAINING_DATA": "PROHIBITED", "FORMAL_MODEL_TRAINING": "PROHIBITED", "MODEL_ARTIFACT_CREATION": "PROHIBITED", "R012_C_FIRSTPARTY_02": "PROHIBITED", "R012_C_01": "PROHIBITED", "R012_B_05": "PROHIBITED", "HISTORICAL_MASTER_ADMISSION": "PROHIBITED", "PRODUCTION_MUTATION": "PROHIBITED", "SUPABASE": "PROHIBITED", "MIGRATION": "PROHIBITED", "DEPLOY": "PROHIBITED", "AUTH_01_REQUIRED": True, "FIVE_PLAY_AUTHORIZATION_STATUS": "AUTHORIZATION_PENDING", "metrics": metrics, "decision": "training dataset and experiment harness is ready for synthetic contract testing only; no real data or model artifact is authorized"}
    _write(output_dir / "qualification_result.json", result)
    return result


def _report(result: dict[str, Any], report_path: Path, output_dir: Path) -> None:
    m = result["metrics"]
    lines = [
        "# R013-A00｜Training Dataset & Experiment Harness Readiness",
        "",
        f"- Final status: **{result['final_status']}**.",
        f"- `TRAINING_HARNESS_STATUS = {result['TRAINING_HARNESS_STATUS']}`.",
        "- Synthetic-only harness; no real training data, formal model training, or model artifact was created.",
        "",
        "## Harness scope",
        "",
        f"- Synthetic samples: {m['SYNTHETIC_SAMPLE_COUNT']}; independent Five-Play contracts: {m['PLAY_CONTRACT_COUNT']}.",
        f"- Point-in-time build: {m['PIT_BUILT_COUNT']}/{m['SYNTHETIC_SAMPLE_COUNT']} passed.",
        f"- Chronological grouped split: train {m['TRAIN_SAMPLE_COUNT']}, validation {m['VALIDATION_SAMPLE_COUNT']}, test {m['TEST_SAMPLE_COUNT']}.",
        f"- Leakage findings: {m['LEAKAGE_COUNT']}; model artifacts: {m['MODEL_ARTIFACT_COUNT']}.",
        "",
        "## Governance gates",
        "",
        "- Features must be available no later than prediction cutoff; labels are observed after kickoff.",
        "- Random split and cross-partition match groups are forbidden.",
        "- Rights, revision, temporal, identity, and hash failures fail closed.",
        "- Evaluation, calibration, and baseline contracts are readiness interfaces only; no model fitting occurred.",
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
    expected = {"contract_id": "R013-A00", "version": "1.0.0"}
    if contract_path.exists():
        existing = _read_json(contract_path)
        if existing.get("contract_id") != expected["contract_id"] or existing.get("version") != expected["version"]:
            raise ValueError("formal R013-A00 contract identity/version mismatch")
    else:
        _write(contract_path, {**expected, **_training_contract(), "status": "HARNESS_ONLY"})
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
