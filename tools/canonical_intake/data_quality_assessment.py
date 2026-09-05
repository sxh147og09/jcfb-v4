"""V4-050 typed multidimensional data-quality assessment."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .batch14_common import (
    Batch14ValidationError,
    QUALITY_DIMENSIONS,
    STATES,
    canonical_entity,
    dimension,
    find_forbidden,
    freeze,
    hash_value,
    iso,
    load_batch14_governance,
    reference,
    text,
    timestamp,
    thaw,
    typed_dimensions,
    validate_boundary,
)
from .feature_bundle import FeatureBundle, FeatureBundleValidationError
from .feature_snapshot import FeatureSnapshotHasher, FeatureSnapshotValidationError


CONTRACT_VERSION = "data-quality-assessment@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_DATA_QUALITY_ASSESSMENT"
GENERATOR_VERSION = "v4-050-data-quality-assessment@1.0.0"
ARTIFACT_NAMESPACE = uuid.UUID("5c58f7da-409c-5b36-9d3d-1f758d39a688")


class DataQualityAssessmentValidationError(Batch14ValidationError):
    """A V4-050 assessment cannot be safely admitted."""


def _hash(value: Any, field: str) -> str:
    return hash_value(value, field, DataQualityAssessmentValidationError)


def _ref(raw: Any, field: str, *, allow_missing_hash: bool = False) -> Dict[str, Any]:
    try:
        return reference(raw, field, allow_missing_hash=allow_missing_hash)
    except Batch14ValidationError as exc:
        raise DataQualityAssessmentValidationError(exc.code, str(exc)) from exc


def _implementation_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _domain(raw: Mapping[str, Any]) -> str:
    explicit = raw.get("domain")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().upper()
    source_kind = str(raw.get("source_kind", "")).casefold()
    if raw.get("source_is_official") is True or "odds" in source_kind or "market" in source_kind:
        return "ODDS"
    if "context" in source_kind or "tactical" in source_kind or "league" in source_kind:
        return "CONTEXT"
    return "DATA"


def _availability(raw: Mapping[str, Any]) -> Optional[datetime]:
    for field in ("input_availability_at", "available_at", "source_timestamp", "observed_at", "effective_at"):
        if raw.get(field) is not None:
            return timestamp(raw[field], f"assessment_inputs.{field}", DataQualityAssessmentValidationError)
    return None


def _feature_reason(state: str) -> str:
    return {
        "UNKNOWN": "OPTIONAL_FEATURE_UNKNOWN",
        "UNAVAILABLE": "OPTIONAL_FEATURE_UNAVAILABLE",
        "NOT_VERIFIED": "FEATURE_NOT_VERIFIED",
        "CONFLICTED": "UNRESOLVED_FEATURE_CONFLICT",
        "STALE": "STALE_REQUIRES_UPSTREAM_POLICY",
        "BLOCKED": "UPSTREAM_BLOCKED",
        "FUTURE_DATA": "FUTURE_DATA",
    }.get(state, "FEATURE_NOT_VERIFIED")


def _reason(code: str, detail: str, *, scope: str, domain: str, input_ids: Iterable[str] = ()) -> Dict[str, Any]:
    return {
        "reason_code": code,
        "reason_detail": detail,
        "scope": scope,
        "domain": domain,
        "input_ids": sorted(set(input_ids)),
    }


def _assessment_states(items: Sequence[Mapping[str, Any]], blockers: Sequence[Mapping[str, Any]], warnings: Sequence[Mapping[str, Any]]) -> Dict[str, str]:
    states = {str(item.get("state", "UNKNOWN")) for item in items}
    hard = bool(blockers)
    has_stale = "STALE" in states
    has_conflict = "CONFLICTED" in states
    has_nonavailable = bool(states - {"AVAILABLE"})
    return {
        "identity": "BLOCKED" if any(item.get("reason_code") in {"CANONICAL_IDENTITY_MISSING", "CANONICAL_IDENTITY_MISMATCH"} for item in blockers) else "PASS",
        "availability": "BLOCKED" if any(item.get("reason_code") in {"SOURCE_TIMESTAMP_UNKNOWN", "TIMEZONE_AMBIGUOUS"} for item in blockers) else ("PARTIAL" if has_nonavailable else "PASS"),
        "coverage": "UNKNOWN" if not items else ("PARTIAL" if has_nonavailable else "PASS"),
        "verification": "BLOCKED" if hard else ("PARTIAL" if has_nonavailable else "PASS"),
        "freshness": "BLOCKED" if any(item.get("reason_code") in {"FUTURE_DATA", "POST_CUTOFF_DATA", "POST_MATCH_DATA"} for item in blockers) else ("STALE" if has_stale else ("PARTIAL" if has_nonavailable else "PASS")),
        "completeness": "UNKNOWN" if not items else ("PARTIAL" if has_nonavailable else "PASS"),
        "conflict": "BLOCKED" if any(item.get("reason_code") in {"UNRESOLVED_INTEGRITY_CONFLICT", "REVISION_HASH_CONFLICT"} for item in blockers) else ("CONFLICTED" if has_conflict else "PASS"),
        "provenance": "BLOCKED" if any(item.get("reason_code") in {"REQUIRED_HASH_MISSING", "HASH_VERIFICATION_FAILED", "PROVENANCE_LINEAGE_MISSING"} for item in blockers) else ("PARTIAL" if any(not item.get("hash") for item in items) else ("PASS" if items else "UNKNOWN")),
        "timestamp_validity": "BLOCKED" if any(item.get("reason_code") in {"SOURCE_TIMESTAMP_UNKNOWN", "TIMEZONE_AMBIGUOUS", "POST_CUTOFF_DATA", "POST_MATCH_DATA"} for item in blockers) else ("PASS" if items else "UNKNOWN"),
        "cutoff_eligibility": "BLOCKED" if any(item.get("reason_code") in {"FUTURE_DATA", "POST_CUTOFF_DATA", "POST_MATCH_DATA"} for item in blockers) else ("PARTIAL" if has_nonavailable else ("PASS" if items else "UNKNOWN")),
        "duplication_integrity": "BLOCKED" if any(item.get("reason_code") in {"UNRESOLVED_INTEGRITY_CONFLICT", "REVISION_HASH_CONFLICT", "HASH_VERIFICATION_FAILED"} for item in blockers) else "PASS",
        "future_data_risk": "BLOCKED" if any(item.get("reason_code") in {"FUTURE_DATA", "POST_CUTOFF_DATA", "POST_MATCH_DATA"} for item in blockers) else "PASS",
    }


def _make_quality(items: Sequence[Mapping[str, Any]], blockers: Sequence[Mapping[str, Any]], warnings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    basis = sorted({ref for item in items for ref in item.get("basis_refs", [])})
    evidence = sorted({ref for item in items for ref in item.get("evidence_refs", [])})
    hashes = sorted({item["hash"] for item in items if item.get("hash")})
    codes = sorted({str(item["reason_code"]) for item in blockers + warnings if item.get("reason_code")})
    counts: Dict[str, int] = {}
    for item in items:
        state = str(item.get("state", "UNKNOWN"))
        counts[state] = counts.get(state, 0) + 1
    return typed_dimensions(_assessment_states(items, blockers, warnings), basis_refs=basis, evidence_refs=evidence, reason_codes=codes, counts=counts, source_input_hashes=hashes)


def _hashes(raw: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    input_hash = sha256_json({
        "contract_version": raw["contract_version"],
        "artifact_kind": raw["artifact_kind"],
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "match_id": raw["match_id"],
        "prediction_cutoff_at": raw["prediction_cutoff_at"],
        "kickoff_at": raw["kickoff_at"],
        "assessment_inputs": raw["assessment_inputs"],
        "generator_version": raw["generator_version"],
        "implementation_hash": raw["implementation_hash"],
        "config_version": raw["config_version"],
        "config_hash": raw["config_hash"],
        "gating_matrix_version": raw["gating_matrix_version"],
        "gating_matrix_hash": raw["gating_matrix_hash"],
        "reason_registry_version": raw["reason_registry_version"],
        "reason_registry_hash": raw["reason_registry_hash"],
    })
    payload_hash = sha256_json({
        "data_quality_assessment": raw["data_quality_assessment"],
        "odds_quality_assessment": raw["odds_quality_assessment"],
        "context_quality_assessment": raw["context_quality_assessment"],
        "source_quality_assessment": raw["source_quality_assessment"],
        "blockers": raw["blockers"],
        "warnings": raw["warnings"],
    })
    provenance_hash = sha256_json({
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "assessment_inputs": [{"id": item["id"], "hash": item.get("hash"), "basis_refs": item.get("basis_refs", []), "evidence_refs": item.get("evidence_refs", []), "source_timestamp": item.get("source_timestamp"), "available_at": item.get("available_at")} for item in raw["assessment_inputs"]],
    })
    output_hash = sha256_json({"input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash, "blockers": raw["blockers"], "warnings": raw["warnings"]})
    return input_hash, payload_hash, provenance_hash, output_hash


def _validate_dimensions(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(QUALITY_DIMENSIONS):
        raise DataQualityAssessmentValidationError("QUALITY_DIMENSIONS_INVALID", f"{field} must contain all approved dimensions")
    result = {}
    for name in QUALITY_DIMENSIONS:
        item = value[name]
        if not isinstance(item, Mapping):
            raise DataQualityAssessmentValidationError("QUALITY_DIMENSION_INVALID", f"{field}.{name} must be an object")
        if not isinstance(item.get("state"), str) or not item["state"].strip():
            raise DataQualityAssessmentValidationError("QUALITY_DIMENSION_STATE_MISSING", f"{field}.{name}.state is required")
        for required in ("basis_refs", "evidence_refs", "reason_codes", "counts", "source_input_hashes"):
            if required not in item:
                raise DataQualityAssessmentValidationError("QUALITY_DIMENSION_FIELD_MISSING", f"{field}.{name}.{required} is required")
        result[name] = freeze(dict(item))
    return freeze(result)


@dataclass(frozen=True)
class DataQualityAssessmentArtifact:
    assessment_id: str
    artifact_kind: str
    contract_version: str
    match_id: str
    canonical_entity_refs: Mapping[str, Any]
    prediction_cutoff_at: str
    kickoff_at: str
    assessment_inputs: Tuple[Mapping[str, Any], ...]
    data_quality_assessment: Mapping[str, Any]
    odds_quality_assessment: Mapping[str, Any]
    context_quality_assessment: Mapping[str, Any]
    source_quality_assessment: Mapping[str, Any]
    blockers: Tuple[Mapping[str, Any], ...]
    warnings: Tuple[Mapping[str, Any], ...]
    generator_version: str
    implementation_hash: str
    config_version: str
    config_hash: str
    gating_matrix_version: str
    gating_matrix_hash: str
    reason_registry_version: str
    reason_registry_hash: str
    input_hash: str
    payload_hash: str
    provenance_hash: str
    output_hash: str
    revision: int
    supersedes_assessment_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "artifact_kind": self.artifact_kind,
            "contract_version": self.contract_version,
            "match_id": self.match_id,
            "canonical_entity_refs": thaw(self.canonical_entity_refs),
            "prediction_cutoff_at": self.prediction_cutoff_at,
            "kickoff_at": self.kickoff_at,
            "assessment_inputs": [thaw(item) for item in self.assessment_inputs],
            "data_quality_assessment": thaw(self.data_quality_assessment),
            "odds_quality_assessment": thaw(self.odds_quality_assessment),
            "context_quality_assessment": thaw(self.context_quality_assessment),
            "source_quality_assessment": thaw(self.source_quality_assessment),
            "blockers": [thaw(item) for item in self.blockers],
            "warnings": [thaw(item) for item in self.warnings],
            "generator_version": self.generator_version,
            "implementation_hash": self.implementation_hash,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "gating_matrix_version": self.gating_matrix_version,
            "gating_matrix_hash": self.gating_matrix_hash,
            "reason_registry_version": self.reason_registry_version,
            "reason_registry_hash": self.reason_registry_hash,
            "input_hash": self.input_hash,
            "payload_hash": self.payload_hash,
            "provenance_hash": self.provenance_hash,
            "output_hash": self.output_hash,
            "revision": self.revision,
            "supersedes_assessment_id": self.supersedes_assessment_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any]) -> "DataQualityAssessmentArtifact":
        if not isinstance(raw, Mapping):
            raise DataQualityAssessmentValidationError("ARTIFACT_INVALID", "assessment must be an object")
        forbidden = find_forbidden(raw)
        if forbidden:
            raise DataQualityAssessmentValidationError("FORBIDDEN_FIELD", f"assessment contains {forbidden}")
        if raw.get("artifact_kind") != ARTIFACT_KIND or raw.get("contract_version") != CONTRACT_VERSION:
            raise DataQualityAssessmentValidationError("CONTRACT_VERSION_INVALID", "assessment kind or contract version is not approved")
        entity = canonical_entity(raw.get("canonical_entity_refs"), DataQualityAssessmentValidationError)
        match_id = text(raw.get("match_id"), "match_id", DataQualityAssessmentValidationError)
        if entity["match_id"] != match_id:
            raise DataQualityAssessmentValidationError("CANONICAL_IDENTITY_MISMATCH", "match_id must equal canonical_entity_refs.match_id")
        cutoff_text, kickoff_text, _, _ = validate_boundary(raw.get("prediction_cutoff_at"), raw.get("kickoff_at"), DataQualityAssessmentValidationError)
        if raw.get("generator_version") != GENERATOR_VERSION:
            raise DataQualityAssessmentValidationError("GENERATOR_VERSION_INVALID", f"expected {GENERATOR_VERSION}")
        identities = (("config_version", config.get("config_version"), "config_hash", config.get("canonical_hash")), ("gating_matrix_version", matrix.get("matrix_version"), "gating_matrix_hash", matrix.get("canonical_hash")), ("reason_registry_version", reasons.get("registry_version"), "reason_registry_hash", reasons.get("canonical_hash")))
        for version_field, expected_version, hash_field, expected_hash in identities:
            if raw.get(version_field) != expected_version or raw.get(hash_field) != expected_hash:
                raise DataQualityAssessmentValidationError("GOVERNANCE_IDENTITY_MISMATCH", f"{version_field}/{hash_field} does not identify the approved artifact")
        inputs_raw = raw.get("assessment_inputs")
        if not isinstance(inputs_raw, list) or not inputs_raw:
            raise DataQualityAssessmentValidationError("ASSESSMENT_INPUTS_REQUIRED", "assessment_inputs must be a non-empty list")
        inputs = []
        for index, item in enumerate(inputs_raw):
            if not isinstance(item, Mapping):
                raise DataQualityAssessmentValidationError("ASSESSMENT_INPUT_INVALID", f"assessment_inputs[{index}] must be an object")
            normalized = dict(item)
            normalized["id"] = text(normalized.get("id"), f"assessment_inputs[{index}].id", DataQualityAssessmentValidationError)
            if normalized.get("hash") is not None:
                normalized["hash"] = _hash(normalized["hash"], f"assessment_inputs[{index}].hash")
            for field in ("basis_refs", "evidence_refs"):
                if not isinstance(normalized.get(field, []), list):
                    raise DataQualityAssessmentValidationError("ASSESSMENT_INPUT_REFS_INVALID", f"assessment_inputs[{index}].{field} must be a list")
            state = text(normalized.get("state", "UNKNOWN"), f"assessment_inputs[{index}].state", DataQualityAssessmentValidationError).upper()
            if state not in STATES:
                raise DataQualityAssessmentValidationError("ASSESSMENT_INPUT_STATE_INVALID", f"assessment_inputs[{index}].state is not governed")
            normalized["state"] = state
            inputs.append(freeze(normalized))
        dimensions = tuple(_validate_dimensions(raw.get(field), field) for field in ("data_quality_assessment", "odds_quality_assessment", "context_quality_assessment", "source_quality_assessment"))
        blockers = raw.get("blockers", [])
        warnings = raw.get("warnings", [])
        if not isinstance(blockers, list) or not isinstance(warnings, list):
            raise DataQualityAssessmentValidationError("REASON_COLLECTION_INVALID", "blockers and warnings must be lists")
        normalized = dict(raw)
        normalized.update({"canonical_entity_refs": entity, "match_id": match_id, "prediction_cutoff_at": cutoff_text, "kickoff_at": kickoff_text, "assessment_inputs": [thaw(item) for item in inputs], "data_quality_assessment": thaw(dimensions[0]), "odds_quality_assessment": thaw(dimensions[1]), "context_quality_assessment": thaw(dimensions[2]), "source_quality_assessment": thaw(dimensions[3]), "blockers": list(blockers), "warnings": list(warnings)})
        calculated = _hashes(normalized)
        for field, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), calculated):
            if raw.get(field) != value:
                raise DataQualityAssessmentValidationError(f"{field.upper()}_MISMATCH", f"{field} is not recomputable")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise DataQualityAssessmentValidationError("REVISION_INVALID", "revision must be a positive integer")
        supersedes = raw.get("supersedes_assessment_id")
        if revision == 1 and supersedes is not None:
            raise DataQualityAssessmentValidationError("ROOT_SUPERSEDES_INVALID", "revision 1 cannot supersede an assessment")
        expected_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"assessment|{calculated[0]}|{calculated[1]}|{revision}"))
        if raw.get("assessment_id") != expected_id:
            raise DataQualityAssessmentValidationError("ASSESSMENT_ID_MISMATCH", "assessment_id is not deterministic")
        if raw.get("implementation_hash") != _implementation_hash():
            raise DataQualityAssessmentValidationError("IMPLEMENTATION_HASH_MISMATCH", "implementation_hash is not current")
        return cls(
            assessment_id=expected_id, artifact_kind=ARTIFACT_KIND, contract_version=CONTRACT_VERSION, match_id=match_id, canonical_entity_refs=freeze(entity), prediction_cutoff_at=cutoff_text, kickoff_at=kickoff_text,
            assessment_inputs=tuple(inputs), data_quality_assessment=dimensions[0], odds_quality_assessment=dimensions[1], context_quality_assessment=dimensions[2], source_quality_assessment=dimensions[3], blockers=tuple(freeze(dict(item)) for item in blockers), warnings=tuple(freeze(dict(item)) for item in warnings), generator_version=GENERATOR_VERSION, implementation_hash=_hash(raw["implementation_hash"], "implementation_hash"), config_version=text(raw["config_version"], "config_version", DataQualityAssessmentValidationError), config_hash=_hash(raw["config_hash"], "config_hash"), gating_matrix_version=text(raw["gating_matrix_version"], "gating_matrix_version", DataQualityAssessmentValidationError), gating_matrix_hash=_hash(raw["gating_matrix_hash"], "gating_matrix_hash"), reason_registry_version=text(raw["reason_registry_version"], "reason_registry_version", DataQualityAssessmentValidationError), reason_registry_hash=_hash(raw["reason_registry_hash"], "reason_registry_hash"), input_hash=calculated[0], payload_hash=calculated[1], provenance_hash=calculated[2], output_hash=calculated[3], revision=revision, supersedes_assessment_id=text(supersedes, "supersedes_assessment_id", DataQualityAssessmentValidationError) if supersedes is not None else None,
        )


class DataQualityAssessmentEngine:
    """Assess exact accepted inputs by typed dimensions only."""

    def __init__(self, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any], repo_root: Path):
        self.config, self.matrix, self.reasons, self.repo_root = config, matrix, reasons, Path(repo_root).resolve()
        self.implementation_hash = _implementation_hash()

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "DataQualityAssessmentEngine":
        root = Path(repo_root).resolve()
        if root.drive.upper() != "F:":
            raise DataQualityAssessmentValidationError("F_DRIVE_REQUIRED", "V4-050 runtime must use the F: drive")
        return cls(*load_batch14_governance(root), root)

    @staticmethod
    def _bundle(raw: Optional[Union[FeatureBundle, Mapping[str, Any]]]) -> Optional[FeatureBundle]:
        if raw is None:
            return None
        try:
            bundle = raw if isinstance(raw, FeatureBundle) else FeatureBundle.from_dict(raw)
            if not bundle.feature_snapshot_hash:
                raise DataQualityAssessmentValidationError("FEATURE_SNAPSHOT_REQUIRED", "V4-050 requires an accepted Feature Snapshot hash")
            FeatureSnapshotHasher.verify(bundle, bundle.feature_snapshot_hash)
            return bundle
        except (FeatureBundleValidationError, FeatureSnapshotValidationError) as exc:
            raise DataQualityAssessmentValidationError(exc.code, str(exc)) from exc

    def generate(
        self,
        *,
        feature_bundle: Optional[Union[FeatureBundle, Mapping[str, Any]]] = None,
        canonical_entity_refs: Optional[Mapping[str, Any]] = None,
        prediction_cutoff_at: Optional[str] = None,
        kickoff_at: Optional[str] = None,
        assessment_inputs: Optional[Sequence[Mapping[str, Any]]] = None,
        inputs: Optional[Sequence[Mapping[str, Any]]] = None,
        revision: int = 1,
        supersedes_assessment_id: Optional[str] = None,
    ) -> DataQualityAssessmentArtifact:
        bundle = self._bundle(feature_bundle)
        if bundle is not None:
            entity = bundle.to_dict()["canonical_entity_refs"]
            cutoff_value, kickoff_value = bundle.prediction_cutoff_at, bundle.kickoff_at
        else:
            entity = canonical_entity(canonical_entity_refs, DataQualityAssessmentValidationError)
            cutoff_value, kickoff_value = prediction_cutoff_at, kickoff_at
        entity = canonical_entity(entity, DataQualityAssessmentValidationError)
        cutoff_text, kickoff_text, cutoff, kickoff = validate_boundary(cutoff_value, kickoff_value, DataQualityAssessmentValidationError)
        raw_items = assessment_inputs if assessment_inputs is not None else inputs
        if not isinstance(raw_items, (list, tuple)) or not raw_items:
            raise DataQualityAssessmentValidationError("ASSESSMENT_INPUTS_REQUIRED", "assessment_inputs must be a non-empty list")
        normalized_items: List[Dict[str, Any]] = []
        blockers: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        seen: Dict[str, Tuple[Any, Any]] = {}
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, Mapping):
                raise DataQualityAssessmentValidationError("ASSESSMENT_INPUT_INVALID", f"assessment_inputs[{index}] must be an object")
            forbidden = find_forbidden(raw, f"assessment_inputs[{index}]")
            if forbidden:
                raise DataQualityAssessmentValidationError("FORBIDDEN_FIELD", f"assessment input contains {forbidden}")
            item = dict(raw)
            ref = _ref(item, f"assessment_inputs[{index}]", allow_missing_hash=True)
            item.update(ref)
            item["domain"] = _domain(item)
            item["state"] = text(item.get("state", "AVAILABLE"), f"assessment_inputs[{index}].state", DataQualityAssessmentValidationError).upper()
            if item["state"] not in STATES:
                raise DataQualityAssessmentValidationError("ASSESSMENT_INPUT_STATE_INVALID", f"assessment_inputs[{index}].state is not governed")
            item["required"] = bool(item.get("required", True))
            item["basis_refs"] = list(item.get("basis_refs", [])) if isinstance(item.get("basis_refs", []), (list, tuple)) else []
            item["evidence_refs"] = list(item.get("evidence_refs", [])) if isinstance(item.get("evidence_refs", []), (list, tuple)) else []
            domain = item["domain"]
            if item["hash"] is None:
                blockers.append(_reason("REQUIRED_HASH_MISSING", "The assessment input has no exact accepted hash.", scope="AFFECTED_LINEAGE", domain=domain, input_ids=[item["id"]]))
            match = item.get("match_id")
            if match is not None and match != entity["match_id"]:
                blockers.append(_reason("CANONICAL_IDENTITY_MISMATCH", "The assessment input is bound to another canonical match.", scope="CANDIDATE_SET", domain=domain, input_ids=[item["id"]]))
            if item["id"] in seen and seen[item["id"]] != (item.get("hash"), item.get("revision")):
                blockers.append(_reason("REVISION_HASH_CONFLICT", "The same input identity has conflicting revision/hash identity.", scope="AFFECTED_LINEAGE", domain=domain, input_ids=[item["id"]]))
            seen[item["id"]] = (item.get("hash"), item.get("revision"))
            try:
                available = _availability(item)
            except DataQualityAssessmentValidationError:
                available = None
                blockers.append(_reason("TIMEZONE_AMBIGUOUS", "Input availability time is invalid or lacks an explicit timezone.", scope="AFFECTED_DOMAIN", domain=domain, input_ids=[item["id"]]))
            if available is None:
                blockers.append(_reason("SOURCE_TIMESTAMP_UNKNOWN", "No timezone-aware input availability timestamp was supplied.", scope="AFFECTED_DOMAIN", domain=domain, input_ids=[item["id"]]))
            else:
                item["input_availability_at"] = iso(available)
                if available >= kickoff:
                    item["state"] = "BLOCKED"
                    blockers.append(_reason("POST_MATCH_DATA", "Input availability is at or after kickoff_at.", scope="AFFECTED_DOMAIN", domain=domain, input_ids=[item["id"]]))
                elif available > cutoff:
                    item["state"] = "FUTURE_DATA"
                    blockers.append(_reason("FUTURE_DATA", "Input availability is after prediction_cutoff_at.", scope="AFFECTED_DOMAIN", domain=domain, input_ids=[item["id"]]))
            if item["state"] in {"UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "STALE", "CONFLICTED", "BLOCKED"}:
                warnings.append(_reason(_feature_reason(item["state"]), f"Input state remains {item['state']} and is not coerced to AVAILABLE.", scope="FEATURE", domain=domain, input_ids=[item["id"]]))
            normalized_items.append(item)
        # A conflict is hard only when the exact identity/hash lineage cannot be audited;
        # a typed source state remains a non-hard warning for the matrix consumer.
        domains = {str(item["domain"]) for item in normalized_items}
        def by_domain(domain: str) -> List[Mapping[str, Any]]:
            return [item for item in normalized_items if item["domain"] == domain]
        data_items = normalized_items
        odds_items = by_domain("ODDS")
        context_items = by_domain("CONTEXT")
        raw = {
            "assessment_id": "pending", "artifact_kind": ARTIFACT_KIND, "contract_version": CONTRACT_VERSION, "match_id": entity["match_id"], "canonical_entity_refs": entity, "prediction_cutoff_at": cutoff_text, "kickoff_at": kickoff_text,
            "assessment_inputs": normalized_items,
            "data_quality_assessment": _make_quality(data_items, blockers, warnings),
            "odds_quality_assessment": _make_quality(odds_items, blockers, warnings),
            "context_quality_assessment": _make_quality(context_items, blockers, warnings),
            "source_quality_assessment": _make_quality(normalized_items, blockers, warnings),
            "blockers": blockers, "warnings": warnings,
            "generator_version": GENERATOR_VERSION, "implementation_hash": self.implementation_hash, "config_version": self.config["config_version"], "config_hash": self.config["canonical_hash"], "gating_matrix_version": self.matrix["matrix_version"], "gating_matrix_hash": self.matrix["canonical_hash"], "reason_registry_version": self.reasons["registry_version"], "reason_registry_hash": self.reasons["canonical_hash"], "revision": revision, "supersedes_assessment_id": supersedes_assessment_id,
        }
        calculated = _hashes(raw)
        raw.update({name: value for name, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), calculated)})
        raw["assessment_id"] = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"assessment|{calculated[0]}|{calculated[1]}|{revision}"))
        return DataQualityAssessmentArtifact.from_dict(raw, config=self.config, matrix=self.matrix, reasons=self.reasons)

    assess = generate


class DataQualityAssessmentStore:
    """Append-only local store for V4-050 assessments."""

    def __init__(self, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any]):
        self.config, self.matrix, self.reasons = config, matrix, reasons
        self._items: Dict[str, DataQualityAssessmentArtifact] = {}

    @property
    def assessments(self) -> Tuple[DataQualityAssessmentArtifact, ...]:
        return tuple(self._items.values())

    def append(self, assessment: Union[DataQualityAssessmentArtifact, Mapping[str, Any]]) -> str:
        item = assessment if isinstance(assessment, DataQualityAssessmentArtifact) else DataQualityAssessmentArtifact.from_dict(assessment, config=self.config, matrix=self.matrix, reasons=self.reasons)
        existing = self._items.get(item.assessment_id)
        if existing is not None:
            if existing.to_dict() == item.to_dict():
                return "DUPLICATE_NOOP"
            raise DataQualityAssessmentValidationError("ASSESSMENT_ID_REUSE", "assessment identity cannot be reused")
        if item.supersedes_assessment_id is not None:
            predecessor = self._items.get(item.supersedes_assessment_id)
            if predecessor is None or predecessor.revision + 1 != item.revision:
                raise DataQualityAssessmentValidationError("SUPERSEDES_INVALID", "corrections require the immediate predecessor and next revision")
            if predecessor.match_id != item.match_id:
                raise DataQualityAssessmentValidationError("SUPERSEDES_FAMILY_CONFLICT", "correction must remain in the same match family")
        elif item.revision != 1:
            raise DataQualityAssessmentValidationError("SUPERSEDES_REQUIRED", "a non-root revision must explicitly supersede the prior assessment")
        self._items[item.assessment_id] = item
        return "APPEND"


__all__ = [
    "ARTIFACT_KIND", "CONTRACT_VERSION", "GENERATOR_VERSION", "DataQualityAssessmentArtifact", "DataQualityAssessmentEngine", "DataQualityAssessmentStore", "DataQualityAssessmentValidationError",
]
