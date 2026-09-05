"""Historical as-of dataset construction for B15-EWP-002.

The builder has one data boundary: :class:`GovernedArchiveReader`.  It never
walks fixtures, source-data directories, runtime caches, a database, or the
V3.3.3 runtime.  Missing evidence is represented in the lineage audit and
cannot become a synthetic sample.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.historical_source_archive import (
    ArchiveReadError,
    GovernedArchiveReader,
    POST_MATCH_TYPES,
    PRE_MATCH_TYPES,
    select_reconstruction_path,
)
from src.prediction_training_contract import (
    ENGINE_ROLES,
    sha256_json,
    substantive_hash,
    validate_training_sample,
)


BUILD_STATUS = "B15-EWP-002"
DATASET_CONTRACT_ID = "prediction-training-dataset@1.1.0"
DATASET_SCHEMA_ID = "prediction-training-dataset-schema@1.1.0"
REPLAY_POLICY_ID = "historical-artifact-replay-lineage-policy@1.0.0"
STORAGE_POLICY_ID = "v4-training-dataset-storage-policy@1.0.0"
ARCHIVE_CONTRACT_ID = "historical-source-archive@1.0.0"
BUILDER_VERSION = "historical-as-of-dataset-builder@1.0.0"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FEATURE_TYPES = {
    "feature_bundle": "feature_bundle_ref",
    "statistical": "statistical_feature_artifact_ref",
    "football": "football_intelligence_ref",
    "market": "market_intelligence_ref",
    "tactical": "tactical_league_ref",
    "gate": "batch14_gate_record_ref",
}
ROLE_LABEL_TYPES = {
    "OUTCOME": {"outcome_label", "final_result"},
    "HANDICAP": {"handicap_label_basis", "final_result"},
    "GOALS": {"goals_label", "final_result"},
    "HTFT": {"htft_label", "halftime_result", "final_result"},
}
FORBIDDEN_SOURCE_TERMS = ("v3.3.3", "v333", "src/data", "tests/fixtures", ".runtime/data")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _required_timestamp(value: Any, field: str) -> datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise DatasetBuildError("MISSING_OR_INVALID_TIMESTAMP", field)
    return parsed


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HASH_RE.fullmatch(value))


def _safe_component(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise DatasetBuildError("PATH_COMPONENT_INVALID", field)
    return value


def _load_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract_hash(path: Path, expected_id: str) -> str:
    document = _load_json(path)
    if document.get("$id") != expected_id:
        raise DatasetBuildError("CONTRACT_ID_MISMATCH", expected_id)
    value = document.get("canonical_hash")
    if not _is_hash(value):
        raise DatasetBuildError("CONTRACT_HASH_MISSING", expected_id)
    body = dict(document)
    body.pop("canonical_hash", None)
    if value != sha256_json(body):
        raise DatasetBuildError("CONTRACT_HASH_INVALID", expected_id)
    return value


class DatasetBuildError(ValueError):
    """A fail-closed dataset builder violation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DatasetBuildResult:
    manifest: Mapping[str, Any]
    dataset_artifact: Mapping[str, Any]
    lineage_manifest: Mapping[str, Any]
    evidence: Mapping[str, Any]
    formal_paths: Mapping[str, str]


class HistoricalAsOfDatasetBuilder:
    """Build append-only, as-of samples from the governed archive reader."""

    def __init__(
        self,
        project_root: str | Path = "F:/Projects/jcfb-v4",
        *,
        reader: Optional[GovernedArchiveReader] = None,
        execution_manifest: Optional[Mapping[str, Any]] = None,
        builder_version: str = BUILDER_VERSION,
        config_root: Optional[str | Path] = None,
        allow_test_root: bool = False,
    ):
        self.project_root = Path(project_root).resolve()
        if self.project_root.drive.upper() != "F:" or (self.project_root.name != "jcfb-v4" and not allow_test_root):
            raise DatasetBuildError("F_DRIVE_REQUIRED", "dataset builder must bind to F:/Projects/jcfb-v4")
        self.archive_root = (self.project_root / "approved_data" / "historical_source_archive").resolve()
        self.approved_root = (self.project_root / "approved_data" / "training_datasets").resolve()
        self.staging_root = (self.project_root / ".runtime" / "training_dataset_staging").resolve()
        self.reader = reader or GovernedArchiveReader(self.archive_root)
        if self.reader.archive_root != self.archive_root:
            raise DatasetBuildError("ARCHIVE_READER_SCOPE_INVALID", "reader must bind to the approved archive root")
        self.execution_manifest = dict(execution_manifest or {})
        self.builder_version = builder_version
        self.config_root = Path(config_root).resolve() if config_root else self.project_root / "config" / "prediction_training"
        if not self.config_root.is_dir():
            raise DatasetBuildError("CONFIG_ROOT_MISSING", str(self.config_root))
        self.builder_hash = _sha256_bytes(Path(__file__).read_bytes())
        self.contract_hash = _contract_hash(self.config_root / "v4_prediction_training_dataset_contract.json", DATASET_CONTRACT_ID)
        self.schema_hash = _contract_hash(self.config_root / "v4_prediction_training_dataset_schema.json", DATASET_SCHEMA_ID)
        self.replay_policy_hash = _contract_hash(self.config_root / "v4_historical_artifact_replay_lineage_policy.json", REPLAY_POLICY_ID)
        self.storage_policy_hash = _contract_hash(self.config_root / "v4_training_dataset_storage_policy.json", STORAGE_POLICY_ID)
        self.archive_contract_hash = _contract_hash(self.config_root / "historical_source_archive_contract.json", ARCHIVE_CONTRACT_ID)

    def _validate_execution(self) -> None:
        if self.execution_manifest.get("work_package_id") != BUILD_STATUS:
            raise DatasetBuildError("WORK_PACKAGE_SCOPE_INVALID", "builder requires B15-EWP-002")
        if self.execution_manifest.get("execution_authorized") is not True:
            raise DatasetBuildError("EXECUTION_NOT_AUTHORIZED", "B15-EWP-002 requires explicit authorization")
        if self.execution_manifest.get("downstream_execution_authorized") not in (None, False):
            raise DatasetBuildError("DOWNSTREAM_AUTHORIZATION_LEAK", "downstream EWP execution must remain false")
        forbidden = self.execution_manifest.get("forbidden_work_packages", [])
        if not forbidden and isinstance(self.execution_manifest.get("dependency_boundary"), Mapping):
            forbidden = self.execution_manifest["dependency_boundary"].get("forbidden_work_packages", [])
        if set(forbidden) and not {"B15-EWP-003", "B15-EWP-004", "B15-EWP-005"}.issubset(set(forbidden)):
            raise DatasetBuildError("DOWNSTREAM_BOUNDARY_INCOMPLETE", "EWP-003 through EWP-005 must be forbidden")

    def _assert_target(self, path: Path, *, approved: bool = False) -> None:
        if path.drive.upper() != "F:":
            raise DatasetBuildError("C_DRIVE_REJECTED", str(path))
        root = self.approved_root if approved else self.staging_root
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise DatasetBuildError("STORAGE_PATH_FORBIDDEN", str(path)) from exc
        for term in FORBIDDEN_SOURCE_TERMS:
            if term.casefold() in str(path).casefold():
                raise DatasetBuildError("SOURCE_BOUNDARY_FORBIDDEN", str(path))

    def _write_append_only(self, relative: str, document: Mapping[str, Any]) -> str:
        staging = (self.staging_root / relative).resolve()
        target = (self.approved_root / relative).resolve()
        self._assert_target(staging)
        self._assert_target(target, approved=True)
        staging.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical_bytes(document) + b"\n"
        if staging.exists() and staging.read_bytes() != payload:
            raise DatasetBuildError("STAGING_COLLISION", str(staging))
        staging.write_bytes(payload)
        if target.exists():
            if target.read_bytes() != payload:
                raise DatasetBuildError("APPEND_ONLY_PATH_COLLISION", str(target))
        else:
            shutil.copyfile(staging, target)
        return str(target)

    @staticmethod
    def _entry_stable(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "archive_record_id": entry.get("archive_record_id"),
            "record_ref": entry.get("record_ref"),
            "manifest_ref": entry.get("manifest_ref"),
            "artifact_hash": entry.get("artifact_hash"),
            "provenance_hash": entry.get("provenance_hash"),
            "revision": entry.get("revision"),
            "supersedes": entry.get("supersedes"),
            "match_id": entry.get("match_id"),
            "cutoff_profile": entry.get("cutoff_profile"),
            "artifact_type": entry.get("artifact_type"),
            "artifact_domain": entry.get("artifact_domain"),
            "source_availability_at": entry.get("source_availability_at"),
        }

    def _archive_snapshot(self, entries: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
        stable = [self._entry_stable(item) for item in entries]
        body = {
            "archive_contract": ARCHIVE_CONTRACT_ID,
            "archive_contract_hash": self.archive_contract_hash,
            "records": stable,
        }
        return "archive-snapshot-" + sha256_json(body)[7:25], sha256_json(body)

    @staticmethod
    def _group_candidates(entries: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in entries:
            key = (
                entry.get("match_id"), entry.get("cutoff_profile"),
                entry.get("prediction_cutoff_at"), entry.get("kickoff_at"),
            )
            grouped.setdefault(key, {"match_id": key[0], "cutoff_profile": key[1], "prediction_cutoff_at": key[2], "kickoff_at": key[3]})
        return tuple(sorted(grouped.values(), key=lambda item: tuple(str(item.get(field) or "") for field in ("match_id", "cutoff_profile", "prediction_cutoff_at", "kickoff_at"))))

    @staticmethod
    def _payload(entry: Mapping[str, Any]) -> Mapping[str, Any]:
        value = entry.get("payload")
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _nested(value: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in value:
                return value[key]
        return None

    @classmethod
    def _ref_hash(cls, entry: Mapping[str, Any], *, snapshot: bool = False) -> tuple[str, str, Optional[str]]:
        payload = cls._payload(entry)
        raw = payload.get("feature_bundle_ref") if "feature_bundle_ref" in payload else payload
        ref: Any = None
        value_hash: Any = None
        if isinstance(raw, Mapping):
            ref = cls._nested(raw, "id", "ref", "artifact_ref", "reference")
            value_hash = cls._nested(raw, "hash", "artifact_hash", "feature_bundle_hash", "feature_snapshot_hash")
        elif isinstance(raw, str):
            ref = raw
        ref = ref or cls._nested(payload, "ref", "id", "artifact_ref", "reference")
        value_hash = value_hash or cls._nested(payload, "hash", "artifact_hash", "feature_bundle_hash", "feature_snapshot_hash")
        if snapshot:
            value_hash = value_hash or cls._nested(payload, "feature_snapshot_hash")
        if not ref:
            ref = entry.get("record_ref")
        if not value_hash:
            value_hash = entry.get("artifact_hash")
        return str(ref or ""), str(value_hash or ""), str(payload.get("feature_snapshot_hash")) if payload.get("feature_snapshot_hash") else None

    @classmethod
    def _domain_ref_hash(cls, entry: Mapping[str, Any]) -> tuple[str, str]:
        payload = cls._payload(entry)
        raw = cls._nested(payload, "ref", "id", "artifact_ref", "reference")
        value_hash = cls._nested(payload, "hash", "artifact_hash", "feature_hash")
        if isinstance(raw, Mapping):
            raw_map = raw
            raw = cls._nested(raw_map, "id", "ref", "artifact_ref", "reference")
            value_hash = value_hash or cls._nested(raw_map, "hash", "artifact_hash", "feature_hash")
        return str(raw or entry.get("record_ref") or ""), str(value_hash or entry.get("artifact_hash") or "")

    def _record_integrity(self, entry: Mapping[str, Any], cutoff: datetime, kickoff: datetime) -> list[str]:
        reasons: list[str] = []
        availability = _parse_timestamp(entry.get("source_availability_at", entry.get("availability_at")))
        if availability is None:
            reasons.append("MISSING_SOURCE_AVAILABILITY_TIMESTAMP")
        elif not availability <= cutoff < kickoff:
            reasons.append("AS_OF_TIME_PREDICATE_FAILED")
        provenance = entry.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance:
            reasons.append("MISSING_PROVENANCE")
        elif not _is_hash(entry.get("provenance_hash")) or entry.get("provenance_hash") != sha256_json(provenance):
            reasons.append("BROKEN_PROVENANCE_HASH")
        if not _is_hash(entry.get("artifact_hash")):
            reasons.append("BROKEN_ARTIFACT_HASH")
        if not entry.get("record_ref") or not entry.get("manifest_ref"):
            reasons.append("EXACT_ARCHIVE_REF_MISSING")
        if any(term in str(entry).casefold() for term in ("v3.3.3", "v333", "frozen_prediction", "model_output")):
            reasons.append("V3_OR_MODEL_CONTENT_FORBIDDEN")
        return reasons

    def _reconstruction(self, entry: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        payload = self._payload(entry)
        context = entry.get("replay_context")
        if not isinstance(context, Mapping):
            context = payload.get("replay_context") if isinstance(payload.get("replay_context"), Mapping) else {}
        selection = select_reconstruction_path(entry, context)
        if selection.get("path") == "DETERMINISTIC_HISTORICAL_REPLAY":
            exact_fields = {
                "exact_generator_version", "exact_config_version", "exact_mapping_version",
                "exact_generator_implementation_hash_value", "exact_config_hash_value", "exact_mapping_hash_value",
            }
            missing = [field for field in exact_fields if not context.get(field)]
            bad_hash = [field for field in ("exact_generator_implementation_hash_value", "exact_config_hash_value", "exact_mapping_hash_value") if not _is_hash(context.get(field))]
            if missing or bad_hash:
                return {"path": "NONE", "status": "INELIGIBLE_FOR_TRAINING", "reasons": ["REPLAY_EXACT_LINEAGE_INCOMPLETE"]}, ["REPLAY_EXACT_LINEAGE_INCOMPLETE"]
        if selection.get("status") != "ELIGIBLE_FOR_AS_OF_TRAINING":
            return selection, list(selection.get("reasons", [])) or ["RECONSTRUCTION_PATH_UNAVAILABLE"]
        return selection, []

    def _resolve_chain(self, entry: Mapping[str, Any], all_entries: Mapping[str, Mapping[str, Any]]) -> list[str]:
        chain: list[str] = []
        current = entry
        visited: set[str] = set()
        while current:
            record_id = str(current.get("archive_record_id"))
            if not record_id or record_id in visited:
                raise DatasetBuildError("UNRESOLVABLE_SUPERSEDES_CHAIN", record_id)
            visited.add(record_id)
            chain.append(record_id)
            predecessor = current.get("supersedes")
            if not predecessor:
                break
            current = all_entries.get(str(predecessor))
            if current is None:
                raise DatasetBuildError("UNRESOLVABLE_SUPERSEDES_CHAIN", str(predecessor))
        return chain

    def _feature_domains(self, pre: Sequence[Mapping[str, Any]], cutoff: datetime, kickoff: datetime, all_entries: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Mapping[str, Any]], list[str], dict[str, Any]]:
        selected: dict[str, Mapping[str, Any]] = {}
        reasons: list[str] = []
        paths: dict[str, Any] = {}
        for domain, artifact_type in FEATURE_TYPES.items():
            candidates = [item for item in pre if item.get("artifact_type") == artifact_type]
            if not candidates:
                reasons.append(f"MISSING_REQUIRED_DOMAIN_ARTIFACT:{domain.upper()}")
                continue
            candidates.sort(key=lambda item: (int(item.get("revision", 0)), str(item.get("archive_record_id"))), reverse=True)
            item = candidates[0]
            try:
                self._resolve_chain(item, all_entries)
            except DatasetBuildError as exc:
                reasons.append(exc.code)
                continue
            integrity = self._record_integrity(item, cutoff, kickoff)
            reconstruction, reconstruction_reasons = self._reconstruction(item)
            if integrity or reconstruction_reasons:
                reasons.extend(integrity or reconstruction_reasons)
                continue
            selected[domain] = item
            paths[domain] = reconstruction
        return selected, sorted(set(reasons)), paths

    def _labels(self, post: Sequence[Mapping[str, Any]], kickoff: datetime, all_entries: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Mapping[str, Any]], dict[str, list[str]]]:
        selected: dict[str, Mapping[str, Any]] = {}
        reasons: dict[str, list[str]] = defaultdict(list)
        by_type: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for entry in post:
            by_type[str(entry.get("artifact_type"))].append(entry)
        for role in ENGINE_ROLES:
            candidates: list[Mapping[str, Any]] = []
            for artifact_type in ROLE_LABEL_TYPES[role]:
                candidates.extend(by_type.get(artifact_type, []))
            candidates.sort(key=lambda item: (int(item.get("revision", 0)), str(item.get("archive_record_id"))), reverse=True)
            if not candidates:
                reasons[role].append("MISSING_POST_MATCH_LABEL")
                continue
            item = candidates[0]
            try:
                self._resolve_chain(item, all_entries)
            except DatasetBuildError as exc:
                reasons[role].append(exc.code)
                continue
            if _parse_timestamp(item.get("source_timestamp")) is None or _parse_timestamp(item.get("source_timestamp")) < kickoff:
                reasons[role].append("POST_MATCH_LABEL_TIME_INVALID")
            if not _is_hash(item.get("artifact_hash")):
                reasons[role].append("LABEL_HASH_INVALID")
            if not isinstance(item.get("provenance"), Mapping) or not item.get("provenance"):
                reasons[role].append("MISSING_LABEL_PROVENANCE")
            if not reasons[role]:
                selected[role] = item
        return selected, reasons

    @staticmethod
    def _rqspf(pre: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
        for entry in pre:
            if entry.get("artifact_type") not in {"official_odds_snapshot", "official_odds_screenshot"}:
                continue
            payload = entry.get("payload") if isinstance(entry.get("payload"), Mapping) else {}
            if payload.get("source_is_official") is False:
                continue
            stack: list[Any] = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, Mapping):
                    for key, child in value.items():
                        if str(key).casefold() in {"rqspf", "official_rqspf", "rqspf_snapshot"} and isinstance(child, Mapping):
                            handicap = child.get("official_handicap", child.get("handicap"))
                            if handicap is not None:
                                return {"entry": entry, "value": handicap}
                        stack.append(child)
                elif isinstance(value, list):
                    stack.extend(value)
        return None

    def _sample(
        self,
        candidate: Mapping[str, Any],
        role: str,
        domains: Mapping[str, Mapping[str, Any]],
        label: Mapping[str, Any],
        pre: Sequence[Mapping[str, Any]],
        reconstruction_paths: Mapping[str, Any],
        archive_snapshot_hash: str,
        prior: Optional[Mapping[str, Any]],
        dataset_version: str,
    ) -> dict[str, Any]:
        match_id = str(candidate["match_id"])
        cutoff_profile = str(candidate["cutoff_profile"])
        logical = {"match_id": match_id, "cutoff_profile": cutoff_profile, "engine_role": role}
        training_sample_id = "ts-" + sha256_json(logical)[7:39]
        bundle = domains["feature_bundle"]
        bundle_ref, bundle_hash, snapshot_hash = self._ref_hash(bundle, snapshot=True)
        domain_values: dict[str, str] = {}
        domain_hashes: dict[str, str] = {}
        for domain in ("statistical", "football", "market", "tactical", "gate"):
            domain_values[domain], domain_hashes[domain] = self._domain_ref_hash(domains[domain])
        source_refs = sorted(str(item.get("record_ref")) for item in pre)
        evidence_refs = sorted(str(item.get("record_ref")) for item in pre if item.get("artifact_type") == "evidence_graph_ref")
        provenance_refs = sorted(str(item.get("manifest_ref")) for item in pre if item.get("manifest_ref"))
        label_ref = str(label.get("record_ref"))
        label_hash = str(label.get("artifact_hash"))
        pre_input = {
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "prediction_cutoff_at": candidate["prediction_cutoff_at"],
            "kickoff_at": candidate["kickoff_at"],
            "feature_refs_and_hashes": {
                "feature_bundle": [bundle_ref, bundle_hash, snapshot_hash],
                "statistical": [domain_values["statistical"], domain_hashes["statistical"]],
                "football": [domain_values["football"], domain_hashes["football"]],
                "market": [domain_values["market"], domain_hashes["market"]],
                "tactical": [domain_values["tactical"], domain_hashes["tactical"]],
                "gate": [domain_values["gate"], domain_hashes["gate"]],
            },
            "source_refs": source_refs,
        }
        input_hash = sha256_json(pre_input)
        provenance_hash = sha256_json({"source_refs": source_refs, "evidence_refs": evidence_refs, "provenance_refs": provenance_refs, "reconstruction": reconstruction_paths})
        revision = int(prior.get("revision", 0)) + 1 if prior else 1
        supersedes = prior.get("sample_hash") if prior else None
        sample: dict[str, Any] = {
            "training_sample_id": training_sample_id,
            "match_id": match_id,
            "cutoff_profile": cutoff_profile,
            "prediction_cutoff_at": candidate["prediction_cutoff_at"],
            "kickoff_at": candidate["kickoff_at"],
            "source_availability_at": min(str(item.get("source_availability_at")) for item in pre),
            "feature_bundle_ref": bundle_ref,
            "feature_bundle_hash": bundle_hash,
            "feature_snapshot_hash": snapshot_hash or "",
            "statistical_ref": domain_values["statistical"],
            "statistical_hash": domain_hashes["statistical"],
            "football_ref": domain_values["football"],
            "football_hash": domain_hashes["football"],
            "market_ref": domain_values["market"],
            "market_hash": domain_hashes["market"],
            "tactical_ref": domain_values["tactical"],
            "tactical_hash": domain_hashes["tactical"],
            "gate_record_ref": domain_values["gate"],
            "gate_record_hash": domain_hashes["gate"],
            "source_refs": source_refs,
            "evidence_refs": evidence_refs,
            "provenance_refs": provenance_refs,
            "engine_role": role,
            "eligibility_state": "ELIGIBLE",
            "exclusion_or_block_reason": None,
            "label_ref": label_ref,
            "label_hash": label_hash,
            "builder_version": self.builder_version,
            "builder_hash": self.builder_hash,
            "dataset_version": dataset_version,
            "input_hash": input_hash,
            "provenance_hash": provenance_hash,
            "revision": revision,
            "supersedes": supersedes,
        }
        if role == "HANDICAP":
            rqspf = self._rqspf(pre)
            if rqspf is None:
                raise DatasetBuildError("RQSPF_REQUIRED", "HANDICAP sample requires official RQSPF")
            rqspf_entry = rqspf["entry"]
            sample.update({
                "official_rqspf_snapshot_ref": rqspf_entry["record_ref"],
                "official_rqspf_snapshot_hash": rqspf_entry["artifact_hash"],
                "official_handicap_value": rqspf["value"],
                "handicap_sign_convention": "home_minus_away",
            })
        sample["sample_hash"] = sha256_json(sample)
        failures = validate_training_sample(sample)
        if failures:
            raise DatasetBuildError("DATASET_SAMPLE_CONTRACT_INVALID", ";".join(failures))
        return sample

    @staticmethod
    def _prior_sample(approved_root: Path, dataset_id: str, logical: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        manifests = approved_root / "manifests"
        if not manifests.is_dir():
            return None
        found: list[Mapping[str, Any]] = []
        for path in manifests.glob("*.json"):
            try:
                document = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if document.get("manifest_type") != "B15-EWP-002-DATASET-MANIFEST" or document.get("dataset_id") != dataset_id:
                continue
            for sample in document.get("sample_records", []):
                if all(sample.get(key) == value for key, value in logical.items()):
                    found.append(sample)
        return max(found, key=lambda item: int(item.get("revision", 0))) if found else None

    def build(self, *, cutoff_profile: Optional[str] = None) -> DatasetBuildResult:
        self._validate_execution()
        try:
            all_entries = self.reader.enumerate_approved_archive_records()
        except (ArchiveReadError, OSError, json.JSONDecodeError) as exc:
            raise DatasetBuildError("ARCHIVE_READ_BLOCKED", str(exc)) from exc
        all_entry_map = {str(item.get("archive_record_id")): item for item in all_entries if item.get("archive_record_id")}
        archive_snapshot_identity, archive_snapshot_hash = self._archive_snapshot(all_entries)
        pre_entries = [item for item in all_entries if item.get("artifact_domain") == "pre_match" and (cutoff_profile is None or item.get("cutoff_profile") == cutoff_profile)]
        post_by_candidate: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for item in all_entries:
            if item.get("artifact_domain") == "post_match":
                post_by_candidate[(str(item.get("match_id")), str(item.get("cutoff_profile")))].append(item)
        candidates = self._group_candidates(pre_entries)
        dataset_id = "dataset-" + sha256_json({"archive_snapshot_hash": archive_snapshot_hash, "cutoff_profile": cutoff_profile, "builder_version": self.builder_version, "builder_hash": self.builder_hash, "contract_hash": self.contract_hash})[7:39]
        existing_manifests = sorted((self.approved_root / "manifests").glob(f"{dataset_id}-r*.json")) if (self.approved_root / "manifests").is_dir() else []
        existing_manifest = _load_json(existing_manifests[-1]) if existing_manifests else None
        dataset_revision = int(existing_manifest.get("revision", 0)) + 1 if existing_manifest and candidates else 1
        dataset_version = DATASET_CONTRACT_ID + f"#r{dataset_revision:03d}"
        sample_records: list[dict[str, Any]] = []
        sample_refs: list[dict[str, Any]] = []
        lineage_candidates: list[dict[str, Any]] = []
        counts: dict[str, Counter[str]] = {role: Counter() for role in ENGINE_ROLES}
        for candidate in candidates:
            candidate_key = (str(candidate.get("match_id")), str(candidate.get("cutoff_profile")))
            cutoff = _parse_timestamp(candidate.get("prediction_cutoff_at"))
            kickoff = _parse_timestamp(candidate.get("kickoff_at"))
            role_audit: dict[str, Any] = {"match_id": candidate.get("match_id"), "cutoff_profile": candidate.get("cutoff_profile"), "roles": {}}
            if cutoff is None or kickoff is None:
                for role in ENGINE_ROLES:
                    counts[role]["BLOCKED"] += 1
                    role_audit["roles"][role] = {"eligibility_state": "BLOCKED", "reasons": ["MISSING_CUTOFF_OR_KICKOFF_TIMESTAMP"]}
                lineage_candidates.append(role_audit)
                continue
            visible_pre = self.reader.enumerate_approved_archive_records(match_id=candidate_key[0], cutoff_profile=candidate_key[1], domain="pre_match", prediction_cutoff_at=str(candidate["prediction_cutoff_at"]))
            domains, common_reasons, reconstruction_paths = self._feature_domains(visible_pre, cutoff, kickoff, all_entry_map)
            labels, label_reasons = self._labels(post_by_candidate[candidate_key], kickoff, all_entry_map)
            rqspf = self._rqspf(visible_pre)
            if rqspf is None:
                label_reasons["HANDICAP"].append("OFFICIAL_RQSPF_MISSING")
            for role in ENGINE_ROLES:
                reasons = list(common_reasons) + list(label_reasons.get(role, []))
                if role == "HANDICAP" and rqspf is None:
                    reasons.append("OFFICIAL_RQSPF_MISSING")
                status = "ELIGIBLE" if not reasons else "INELIGIBLE"
                role_audit["roles"][role] = {"eligibility_state": status, "reasons": sorted(set(reasons)), "feature_refs": [domains[key].get("record_ref") for key in sorted(domains)]}
                counts[role][status] += 1
                if status != "ELIGIBLE":
                    continue
                try:
                    logical = {"match_id": candidate_key[0], "cutoff_profile": candidate_key[1], "engine_role": role}
                    prior = self._prior_sample(self.approved_root, dataset_id, logical)
                    sample = self._sample(candidate, role, domains, labels[role], visible_pre, reconstruction_paths, archive_snapshot_hash, prior, dataset_version)
                except DatasetBuildError as exc:
                    role_audit["roles"][role]["eligibility_state"] = "BLOCKED"
                    role_audit["roles"][role]["reasons"] = sorted(set(role_audit["roles"][role]["reasons"] + [exc.code]))
                    counts[role]["ELIGIBLE"] -= 1
                    counts[role]["BLOCKED"] += 1
                    continue
                sample_records.append(sample)
                relative = f"artifacts/{archive_snapshot_identity}/{_safe_component(candidate_key[0], 'match_id')}/{_safe_component(candidate_key[1], 'cutoff_profile')}/{role}/r{int(sample['revision']):03d}-{sample['training_sample_id']}.json"
                sample_ref = {"training_sample_id": sample["training_sample_id"], "match_id": sample["match_id"], "cutoff_profile": sample["cutoff_profile"], "engine_role": role, "revision": sample["revision"], "sample_hash": sample["sample_hash"], "artifact_ref": relative}
                self._write_append_only(relative, sample)
                sample_refs.append(sample_ref)
            lineage_candidates.append(role_audit)
        membership = sorted(sample["training_sample_id"] + f"#r{sample['revision']:03d}" for sample in sample_records)
        role_counts = {role: {state: int(counts[role].get(state, 0)) for state in ("ELIGIBLE", "PARTIALLY_ELIGIBLE", "INELIGIBLE", "BLOCKED")} for role in ENGINE_ROLES}
        stable_manifest = {
            "archive_snapshot_identity": archive_snapshot_identity,
            "archive_snapshot_hash": archive_snapshot_hash,
            "cutoff_profile": cutoff_profile or "ALL_ARCHIVED_CUTOFF_PROFILES",
            "builder_version": self.builder_version,
            "builder_hash": self.builder_hash,
            "dataset_schema_version": DATASET_SCHEMA_ID,
            "dataset_schema_hash": self.schema_hash,
            "replay_policy_version": REPLAY_POLICY_ID,
            "replay_policy_hash": self.replay_policy_hash,
            "sample_membership": membership,
            "feature_refs_and_hashes": sorted(sample_refs, key=lambda item: (item["training_sample_id"], item["revision"])),
            "eligibility": role_counts,
            "label_refs_and_hashes": sorted([{"training_sample_id": item["training_sample_id"], "label_ref": item["label_ref"], "label_hash": item["label_hash"]} for item in sample_records], key=lambda item: item["training_sample_id"]),
        }
        manifest_hash = substantive_hash(stable_manifest)
        substantive_manifest = dict(stable_manifest, dataset_substantive_hash=manifest_hash)
        dataset_artifact = {
            "artifact_type": "HISTORICAL_AS_OF_TRAINING_DATASET",
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "contract_identity": DATASET_CONTRACT_ID,
            "contract_hash": self.contract_hash,
            "builder_identity": "HistoricalAsOfDatasetBuilder",
            "builder_version": self.builder_version,
            "builder_hash": self.builder_hash,
            "archive_snapshot_identity": archive_snapshot_identity,
            "archive_snapshot_hash": archive_snapshot_hash,
            "sample_refs": sample_refs,
            "sample_count": len(sample_records),
            "role_eligibility_counts": role_counts,
            "dataset_substantive_hash": manifest_hash,
            "revision": dataset_revision,
            "supersedes": existing_manifest.get("dataset_artifact_hash") if existing_manifest and dataset_revision > 1 else None,
        }
        dataset_artifact_hash = sha256_json(dataset_artifact)
        dataset_artifact["artifact_hash"] = dataset_artifact_hash
        artifact_relative = f"artifacts/{dataset_id}/dataset.json" if dataset_revision == 1 else f"artifacts/{dataset_id}/revisions/r{dataset_revision:03d}/dataset.json"
        artifact_path = self._write_append_only(artifact_relative, dataset_artifact)
        lineage_manifest = {
            "manifest_type": "B15-EWP-002-LINEAGE-MANIFEST",
            "dataset_id": dataset_id,
            "dataset_substantive_hash": manifest_hash,
            "archive_snapshot_identity": archive_snapshot_identity,
            "archive_snapshot_hash": archive_snapshot_hash,
            "candidate_match_count": len(candidates),
            "candidate_sample_count": len(candidates) * len(ENGINE_ROLES),
            "candidates": lineage_candidates,
        }
        lineage_hash = sha256_json(lineage_manifest)
        lineage_manifest["lineage_manifest_hash"] = lineage_hash
        lineage_relative = f"lineage_manifests/{dataset_id}.json" if dataset_revision == 1 else f"lineage_manifests/{dataset_id}-r{dataset_revision:03d}.json"
        lineage_path = self._write_append_only(lineage_relative, lineage_manifest)
        manifest = {
            "manifest_type": "B15-EWP-002-DATASET-MANIFEST",
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "builder_identity": "HistoricalAsOfDatasetBuilder",
            "builder_version": self.builder_version,
            "builder_hash": self.builder_hash,
            "contract_identity": DATASET_CONTRACT_ID,
            "contract_hash": self.contract_hash,
            "dataset_schema_version": DATASET_SCHEMA_ID,
            "dataset_schema_hash": self.schema_hash,
            "replay_policy_identity": REPLAY_POLICY_ID,
            "replay_policy_hash": self.replay_policy_hash,
            "replay_policy_version": REPLAY_POLICY_ID,
            "archive_snapshot_identity": archive_snapshot_identity,
            "archive_snapshot_hash": archive_snapshot_hash,
            "storage_policy_identity": STORAGE_POLICY_ID,
            "storage_policy_hash": self.storage_policy_hash,
            "cutoff_profile": cutoff_profile or "ALL_ARCHIVED_CUTOFF_PROFILES",
            "archived_match_count": len({str(item.get("match_id")) for item in all_entries if item.get("match_id")}),
            "candidate_match_count": len(candidates),
            "candidate_sample_count": len(candidates) * len(ENGINE_ROLES),
            "eligible_counts_by_engine": {role: role_counts[role]["ELIGIBLE"] for role in ENGINE_ROLES},
            "partially_eligible_counts_by_engine": {role: role_counts[role]["PARTIALLY_ELIGIBLE"] for role in ENGINE_ROLES},
            "ineligible_counts_by_engine": {role: role_counts[role]["INELIGIBLE"] for role in ENGINE_ROLES},
            "blocked_counts_by_engine": {role: role_counts[role]["BLOCKED"] for role in ENGINE_ROLES},
            "sample_records": sample_records,
            "sample_refs": sample_refs,
            "sample_membership": membership,
            "feature_refs_and_hashes": stable_manifest["feature_refs_and_hashes"],
            "eligibility": stable_manifest["eligibility"],
            "label_refs_and_hashes": stable_manifest["label_refs_and_hashes"],
            "dataset_artifact_ref": artifact_relative,
            "dataset_artifact_hash": dataset_artifact_hash,
            "lineage_manifest_ref": lineage_relative,
            "lineage_manifest_hash": lineage_hash,
            "dataset_substantive_hash": manifest_hash,
            "revision": dataset_revision,
            "supersedes": existing_manifest.get("manifest_hash") if existing_manifest and dataset_revision > 1 else None,
            "zero_archive_reason": "ZERO_ARCHIVED_CANDIDATES" if not candidates else None,
        }
        manifest_hash_value = sha256_json(manifest)
        manifest["manifest_hash"] = manifest_hash_value
        manifest_relative = f"manifests/{dataset_id}-r{dataset_revision:03d}.json"
        manifest_path = self._write_append_only(manifest_relative, manifest)
        evidence = {
            "evidence_type": "B15-EWP-002-ACCEPTANCE-EVIDENCE",
            "dataset_id": dataset_id,
            "dataset_manifest_ref": manifest_relative,
            "dataset_manifest_hash": manifest_hash_value,
            "dataset_substantive_hash": manifest_hash,
            "archived_match_count": manifest["archived_match_count"],
            "candidate_match_count": manifest["candidate_match_count"],
            "candidate_sample_count": manifest["candidate_sample_count"],
            "role_counts": role_counts,
            "usable_training_sample_count": len(sample_records),
            "usable_training_sample_reason": "ZERO_ARCHIVED_CANDIDATES" if not candidates else "COMPUTED_FROM_ELIGIBLE_ROLE_SAMPLES",
            "no_temporal_split": True,
            "no_model_fitting": True,
            "no_v4_076": True,
            "no_v3_3_3": True,
        }
        evidence_hash = sha256_json(evidence)
        evidence["evidence_hash"] = evidence_hash
        evidence_relative = f"evidence/{dataset_id}-acceptance.json" if dataset_revision == 1 else f"evidence/{dataset_id}-r{dataset_revision:03d}-acceptance.json"
        evidence_path = self._write_append_only(evidence_relative, evidence)
        return DatasetBuildResult(
            manifest=manifest,
            dataset_artifact=dataset_artifact,
            lineage_manifest=lineage_manifest,
            evidence=evidence,
            formal_paths={"dataset_artifact": artifact_path, "manifest": manifest_path, "lineage_manifest": lineage_path, "evidence": evidence_path},
        )


__all__ = ["BUILD_STATUS", "DatasetBuildError", "DatasetBuildResult", "HistoricalAsOfDatasetBuilder"]
