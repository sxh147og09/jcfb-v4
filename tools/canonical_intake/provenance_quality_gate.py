"""V4-051 matrix-driven provenance and pre-Freeze quality gate."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from tools.migration_harness.common import sha256_json

from .batch14_common import (
    Batch14ValidationError,
    ELIGIBILITY_LEVELS,
    ELIGIBILITY_STATES,
    canonical_entity,
    find_forbidden,
    freeze,
    hash_value,
    load_batch14_governance,
    reference,
    text,
    thaw,
    timestamp,
    validate_boundary,
)
from .data_quality_assessment import (
    DataQualityAssessmentArtifact,
    DataQualityAssessmentValidationError,
)
from .tactical_league_profile import (
    TacticalLeagueProfileArtifact,
    TacticalLeagueProfileValidationError,
)


CONTRACT_VERSION = "provenance-quality-gate@1.0.0"
ARTIFACT_KIND = "PRE_FREEZE_QUALITY_GATE_RECORD"
GENERATOR_VERSION = "v4-051-provenance-quality-gate@1.0.0"
ARTIFACT_NAMESPACE = uuid.UUID("4c79255a-2995-5cae-b9f4-68059f91fe90")


class ProvenanceQualityGateValidationError(Batch14ValidationError):
    """A V4-051 gate record cannot be safely admitted."""


def _hash(value: Any, field: str) -> str:
    return hash_value(value, field, ProvenanceQualityGateValidationError)


def _implementation_hash() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _ref(value: Any, field: str) -> Dict[str, Any]:
    try:
        return reference(value, field)
    except Batch14ValidationError as exc:
        raise ProvenanceQualityGateValidationError(exc.code, str(exc)) from exc


def _hard_rules(matrix: Mapping[str, Any]) -> Dict[str, str]:
    return {str(item["reason_code"]): str(item["propagation"]) for item in matrix.get("hard_blockers", []) if isinstance(item, Mapping) and item.get("reason_code") and item.get("propagation")}


def _non_hard(matrix: Mapping[str, Any], state: str) -> Mapping[str, Any]:
    value = matrix.get("non_hard_states", {}).get(state)
    return value if isinstance(value, Mapping) else {"feature_state": "INELIGIBLE", "domain_propagation": "ONLY_IF_REQUIRED", "candidate_propagation": "PARTIALLY_ELIGIBLE"}


def _reason_record(raw: Mapping[str, Any], *, default_scope: str, default_domain: str) -> Dict[str, Any]:
    code = text(raw.get("reason_code"), "reason_code", ProvenanceQualityGateValidationError).upper()
    detail = text(raw.get("reason_detail"), "reason_detail", ProvenanceQualityGateValidationError)
    return {
        "reason_code": code,
        "reason_detail": detail,
        "scope": str(raw.get("scope", default_scope)),
        "domain": str(raw.get("domain", default_domain)),
        "input_ids": sorted({str(item) for item in raw.get("input_ids", [])}),
    }


def _eligibility_id(level: str, subject_id: str, state: str, input_hash: str) -> str:
    return str(uuid.uuid5(ARTIFACT_NAMESPACE, f"eligibility|{level}|{subject_id}|{state}|{input_hash}"))


def _hashes(raw: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    input_hash = sha256_json({
        "contract_version": raw["contract_version"],
        "artifact_kind": raw["artifact_kind"],
        "match_id": raw["match_id"],
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "prediction_cutoff_at": raw["prediction_cutoff_at"],
        "kickoff_at": raw["kickoff_at"],
        "assessment_input_refs": raw["assessment_input_refs"],
        "assessment_input_hashes": raw["assessment_input_hashes"],
        "v4_049_refs": raw["v4_049_refs"],
        "v4_049_hashes": raw["v4_049_hashes"],
        "v4_050_refs": raw["v4_050_refs"],
        "v4_050_hashes": raw["v4_050_hashes"],
        "config_version": raw["config_version"],
        "config_hash": raw["config_hash"],
        "gating_matrix_version": raw["gating_matrix_version"],
        "gating_matrix_hash": raw["gating_matrix_hash"],
        "reason_registry_version": raw["reason_registry_version"],
        "reason_registry_hash": raw["reason_registry_hash"],
        "generator_version": raw["generator_version"],
        "implementation_hash": raw["implementation_hash"],
    })
    payload_hash = sha256_json({
        "candidate_set_ref": raw["candidate_set_ref"],
        "feature_eligibility_records": raw["feature_eligibility_records"],
        "domain_eligibility_records": raw["domain_eligibility_records"],
        "candidate_set_eligibility_records": raw["candidate_set_eligibility_records"],
        "overall_gate_state": raw["overall_gate_state"],
        "blockers": raw["blockers"],
        "warning_nonblocking_reasons": raw["warning_nonblocking_reasons"],
    })
    provenance_hash = sha256_json({
        "canonical_entity_refs": raw["canonical_entity_refs"],
        "assessment_input_refs": raw["assessment_input_refs"],
        "assessment_input_hashes": raw["assessment_input_hashes"],
        "v4_049_refs": raw["v4_049_refs"],
        "v4_049_hashes": raw["v4_049_hashes"],
        "v4_050_refs": raw["v4_050_refs"],
        "v4_050_hashes": raw["v4_050_hashes"],
        "evidence_refs": raw["evidence_refs"],
        "provenance_refs": raw["provenance_refs"],
    })
    output_hash = sha256_json({"input_hash": input_hash, "payload_hash": payload_hash, "provenance_hash": provenance_hash, "overall_gate_state": raw["overall_gate_state"], "blockers": raw["blockers"], "warning_nonblocking_reasons": raw["warning_nonblocking_reasons"]})
    return input_hash, payload_hash, provenance_hash, output_hash


def _validate_eligibility_records(value: Any, field: str) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise ProvenanceQualityGateValidationError("ELIGIBILITY_COLLECTION_INVALID", f"{field} must be a list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ProvenanceQualityGateValidationError("ELIGIBILITY_RECORD_INVALID", f"{field}[{index}] must be an object")
        level = text(item.get("level"), f"{field}[{index}].level", ProvenanceQualityGateValidationError).upper()
        state = text(item.get("state"), f"{field}[{index}].state", ProvenanceQualityGateValidationError).upper()
        if level not in ELIGIBILITY_LEVELS or state not in ELIGIBILITY_STATES:
            raise ProvenanceQualityGateValidationError("ELIGIBILITY_VALUE_INVALID", f"{field}[{index}] has an unapproved level/state")
        for required in ("eligibility_id", "subject_ref", "subject_hash", "blocker_reason_codes", "warning_reason_codes", "required"):
            if required not in item:
                raise ProvenanceQualityGateValidationError("ELIGIBILITY_FIELD_MISSING", f"{field}[{index}].{required} is required")
        _hash(item["subject_hash"], f"{field}[{index}].subject_hash")
        result.append(freeze(dict(item)))
    return tuple(result)


@dataclass(frozen=True)
class ProvenanceQualityGateRecord:
    gate_record_id: str
    artifact_kind: str
    contract_version: str
    match_id: str
    canonical_entity_refs: Mapping[str, Any]
    prediction_cutoff_at: str
    kickoff_at: str
    assessment_input_refs: Tuple[Mapping[str, Any], ...]
    assessment_input_hashes: Tuple[str, ...]
    v4_049_refs: Tuple[Mapping[str, Any], ...]
    v4_049_hashes: Tuple[str, ...]
    v4_050_refs: Tuple[Mapping[str, Any], ...]
    v4_050_hashes: Tuple[str, ...]
    candidate_set_ref: Mapping[str, Any]
    feature_eligibility_records: Tuple[Mapping[str, Any], ...]
    domain_eligibility_records: Tuple[Mapping[str, Any], ...]
    candidate_set_eligibility_records: Tuple[Mapping[str, Any], ...]
    overall_gate_state: str
    blockers: Tuple[Mapping[str, Any], ...]
    warning_nonblocking_reasons: Tuple[Mapping[str, Any], ...]
    evidence_refs: Tuple[Mapping[str, Any], ...]
    provenance_refs: Tuple[Mapping[str, Any], ...]
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
    supersedes_gate_record_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_record_id": self.gate_record_id, "artifact_kind": self.artifact_kind, "contract_version": self.contract_version, "match_id": self.match_id, "canonical_entity_refs": thaw(self.canonical_entity_refs), "prediction_cutoff_at": self.prediction_cutoff_at, "kickoff_at": self.kickoff_at,
            "assessment_input_refs": [thaw(item) for item in self.assessment_input_refs], "assessment_input_hashes": list(self.assessment_input_hashes), "v4_049_refs": [thaw(item) for item in self.v4_049_refs], "v4_049_hashes": list(self.v4_049_hashes), "v4_050_refs": [thaw(item) for item in self.v4_050_refs], "v4_050_hashes": list(self.v4_050_hashes), "candidate_set_ref": thaw(self.candidate_set_ref),
            "feature_eligibility_records": [thaw(item) for item in self.feature_eligibility_records], "domain_eligibility_records": [thaw(item) for item in self.domain_eligibility_records], "candidate_set_eligibility_records": [thaw(item) for item in self.candidate_set_eligibility_records], "overall_gate_state": self.overall_gate_state, "blockers": [thaw(item) for item in self.blockers], "warning_nonblocking_reasons": [thaw(item) for item in self.warning_nonblocking_reasons], "evidence_refs": [thaw(item) for item in self.evidence_refs], "provenance_refs": [thaw(item) for item in self.provenance_refs],
            "generator_version": self.generator_version, "implementation_hash": self.implementation_hash, "config_version": self.config_version, "config_hash": self.config_hash, "gating_matrix_version": self.gating_matrix_version, "gating_matrix_hash": self.gating_matrix_hash, "reason_registry_version": self.reason_registry_version, "reason_registry_hash": self.reason_registry_hash,
            "input_hash": self.input_hash, "payload_hash": self.payload_hash, "provenance_hash": self.provenance_hash, "output_hash": self.output_hash, "revision": self.revision, "supersedes_gate_record_id": self.supersedes_gate_record_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any]) -> "ProvenanceQualityGateRecord":
        if not isinstance(raw, Mapping):
            raise ProvenanceQualityGateValidationError("ARTIFACT_INVALID", "gate record must be an object")
        forbidden = find_forbidden(raw)
        if forbidden:
            raise ProvenanceQualityGateValidationError("FORBIDDEN_FIELD", f"gate record contains {forbidden}")
        if raw.get("artifact_kind") != ARTIFACT_KIND or raw.get("contract_version") != CONTRACT_VERSION:
            raise ProvenanceQualityGateValidationError("CONTRACT_VERSION_INVALID", "gate record kind or contract version is not approved")
        entity = canonical_entity(raw.get("canonical_entity_refs"), ProvenanceQualityGateValidationError)
        match_id = text(raw.get("match_id"), "match_id", ProvenanceQualityGateValidationError)
        if match_id != entity["match_id"]:
            raise ProvenanceQualityGateValidationError("CANONICAL_IDENTITY_MISMATCH", "match_id must equal canonical_entity_refs.match_id")
        cutoff_text, kickoff_text, _, _ = validate_boundary(raw.get("prediction_cutoff_at"), raw.get("kickoff_at"), ProvenanceQualityGateValidationError)
        if raw.get("generator_version") != GENERATOR_VERSION or raw.get("config_version") != config.get("config_version") or raw.get("config_hash") != config.get("canonical_hash"):
            raise ProvenanceQualityGateValidationError("GOVERNANCE_IDENTITY_MISMATCH", "gate generator/config identity is not approved")
        for version_field, hash_field, expected_version, expected_hash in (("gating_matrix_version", "gating_matrix_hash", matrix.get("matrix_version"), matrix.get("canonical_hash")), ("reason_registry_version", "reason_registry_hash", reasons.get("registry_version"), reasons.get("canonical_hash"))):
            if raw.get(version_field) != expected_version or raw.get(hash_field) != expected_hash:
                raise ProvenanceQualityGateValidationError("GOVERNANCE_IDENTITY_MISMATCH", f"{version_field}/{hash_field} is not approved")
        for field in ("assessment_input_refs", "v4_049_refs", "v4_050_refs", "evidence_refs", "provenance_refs"):
            if not isinstance(raw.get(field), list):
                raise ProvenanceQualityGateValidationError("REFERENCE_COLLECTION_INVALID", f"{field} must be a list")
        refs = []
        for field in ("assessment_input_refs", "v4_049_refs", "v4_050_refs", "evidence_refs", "provenance_refs"):
            for index, item in enumerate(raw[field]):
                refs.append(_ref(item, f"{field}[{index}]"))
        candidate_ref = _ref(raw.get("candidate_set_ref"), "candidate_set_ref")
        for field in ("assessment_input_hashes", "v4_049_hashes", "v4_050_hashes"):
            values = raw.get(field)
            if not isinstance(values, list) or any(not isinstance(item, str) or not item.startswith("sha256:") for item in values):
                raise ProvenanceQualityGateValidationError("HASH_COLLECTION_INVALID", f"{field} must contain SHA-256 hashes")
            for index, item in enumerate(values):
                _hash(item, f"{field}[{index}]")
        feature_records = _validate_eligibility_records(raw.get("feature_eligibility_records"), "feature_eligibility_records")
        domain_records = _validate_eligibility_records(raw.get("domain_eligibility_records"), "domain_eligibility_records")
        candidate_records = _validate_eligibility_records(raw.get("candidate_set_eligibility_records"), "candidate_set_eligibility_records")
        overall = text(raw.get("overall_gate_state"), "overall_gate_state", ProvenanceQualityGateValidationError).upper()
        if overall not in ELIGIBILITY_STATES:
            raise ProvenanceQualityGateValidationError("ELIGIBILITY_VALUE_INVALID", "overall_gate_state is not approved")
        blockers = raw.get("blockers", [])
        warnings = raw.get("warning_nonblocking_reasons", [])
        if not isinstance(blockers, list) or not isinstance(warnings, list):
            raise ProvenanceQualityGateValidationError("REASON_COLLECTION_INVALID", "blockers and warnings must be lists")
        known_reason_codes = {str(item.get("code")) for item in reasons.get("reasons", []) if isinstance(item, Mapping)}
        for collection, field in ((blockers, "blockers"), (warnings, "warning_nonblocking_reasons")):
            for index, item in enumerate(collection):
                code = text(item.get("reason_code"), f"{field}[{index}].reason_code", ProvenanceQualityGateValidationError).upper()
                if code not in known_reason_codes:
                    raise ProvenanceQualityGateValidationError("UNKNOWN_REASON_CODE", f"{field}[{index}] uses an unregistered reason code")
        n_assessment = len(raw["assessment_input_refs"])
        n_v049 = len(raw["v4_049_refs"])
        n_v050 = len(raw["v4_050_refs"])
        n_evidence = len(raw["evidence_refs"])
        n_provenance = len(raw["provenance_refs"])
        assessment_refs = refs[:n_assessment]
        v049_refs = refs[n_assessment:n_assessment + n_v049]
        v050_refs = refs[n_assessment + n_v049:n_assessment + n_v049 + n_v050]
        evidence_refs = refs[n_assessment + n_v049 + n_v050:n_assessment + n_v049 + n_v050 + n_evidence]
        provenance_refs = refs[-n_provenance:] if n_provenance else []
        normalized = dict(raw)
        normalized.update({
            "canonical_entity_refs": entity,
            "match_id": match_id,
            "prediction_cutoff_at": cutoff_text,
            "kickoff_at": kickoff_text,
            "assessment_input_refs": [thaw(item) for item in assessment_refs],
            "v4_049_refs": [thaw(item) for item in v049_refs],
            "v4_050_refs": [thaw(item) for item in v050_refs],
            "evidence_refs": [thaw(item) for item in evidence_refs],
            "provenance_refs": [thaw(item) for item in provenance_refs],
            "candidate_set_ref": thaw(candidate_ref),
            "feature_eligibility_records": [thaw(item) for item in feature_records],
            "domain_eligibility_records": [thaw(item) for item in domain_records],
            "candidate_set_eligibility_records": [thaw(item) for item in candidate_records],
            "overall_gate_state": overall,
            "blockers": list(blockers),
            "warning_nonblocking_reasons": list(warnings),
        })
        calculated = _hashes(normalized)
        for field, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), calculated):
            if raw.get(field) != value:
                raise ProvenanceQualityGateValidationError(f"{field.upper()}_MISMATCH", f"{field} is not recomputable")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ProvenanceQualityGateValidationError("REVISION_INVALID", "revision must be a positive integer")
        supersedes = raw.get("supersedes_gate_record_id")
        if revision == 1 and supersedes is not None:
            raise ProvenanceQualityGateValidationError("ROOT_SUPERSEDES_INVALID", "revision 1 cannot supersede a gate record")
        expected_id = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"gate|{calculated[0]}|{calculated[1]}|{revision}"))
        if raw.get("gate_record_id") != expected_id:
            raise ProvenanceQualityGateValidationError("GATE_RECORD_ID_MISMATCH", "gate_record_id is not deterministic")
        if raw.get("implementation_hash") != _implementation_hash():
            raise ProvenanceQualityGateValidationError("IMPLEMENTATION_HASH_MISMATCH", "implementation_hash is not current")
        return cls(
            gate_record_id=expected_id, artifact_kind=ARTIFACT_KIND, contract_version=CONTRACT_VERSION, match_id=match_id, canonical_entity_refs=freeze(entity), prediction_cutoff_at=cutoff_text, kickoff_at=kickoff_text,
            assessment_input_refs=tuple(assessment_refs), assessment_input_hashes=tuple(raw["assessment_input_hashes"]), v4_049_refs=tuple(v049_refs), v4_049_hashes=tuple(raw["v4_049_hashes"]), v4_050_refs=tuple(v050_refs), v4_050_hashes=tuple(raw["v4_050_hashes"]), candidate_set_ref=candidate_ref, feature_eligibility_records=feature_records, domain_eligibility_records=domain_records, candidate_set_eligibility_records=candidate_records, overall_gate_state=overall, blockers=tuple(freeze(dict(item)) for item in blockers), warning_nonblocking_reasons=tuple(freeze(dict(item)) for item in warnings), evidence_refs=tuple(evidence_refs), provenance_refs=tuple(provenance_refs), generator_version=GENERATOR_VERSION, implementation_hash=_hash(raw["implementation_hash"], "implementation_hash"), config_version=text(raw["config_version"], "config_version", ProvenanceQualityGateValidationError), config_hash=_hash(raw["config_hash"], "config_hash"), gating_matrix_version=text(raw["gating_matrix_version"], "gating_matrix_version", ProvenanceQualityGateValidationError), gating_matrix_hash=_hash(raw["gating_matrix_hash"], "gating_matrix_hash"), reason_registry_version=text(raw["reason_registry_version"], "reason_registry_version", ProvenanceQualityGateValidationError), reason_registry_hash=_hash(raw["reason_registry_hash"], "reason_registry_hash"), input_hash=calculated[0], payload_hash=calculated[1], provenance_hash=calculated[2], output_hash=calculated[3], revision=revision, supersedes_gate_record_id=text(supersedes, "supersedes_gate_record_id", ProvenanceQualityGateValidationError) if supersedes is not None else None,
        )


class ProvenanceQualityGateEngine:
    """Apply only the frozen quality-gate matrix to accepted Wave 1 outputs."""

    def __init__(self, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any], repo_root: Path):
        self.config, self.matrix, self.reasons, self.repo_root = config, matrix, reasons, Path(repo_root).resolve()
        self.implementation_hash = _implementation_hash()
        self.hard_rules = _hard_rules(matrix)

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "ProvenanceQualityGateEngine":
        root = Path(repo_root).resolve()
        if root.drive.upper() != "F:":
            raise ProvenanceQualityGateValidationError("F_DRIVE_REQUIRED", "V4-051 runtime must use the F: drive")
        return cls(*load_batch14_governance(root), root)

    def _tactical(self, raw: Union[TacticalLeagueProfileArtifact, Mapping[str, Any]]) -> TacticalLeagueProfileArtifact:
        try:
            return raw if isinstance(raw, TacticalLeagueProfileArtifact) else TacticalLeagueProfileArtifact.from_dict(raw, config=self.config, matrix=self.matrix, reasons=self.reasons)
        except TacticalLeagueProfileValidationError as exc:
            raise ProvenanceQualityGateValidationError("V4049_NOT_ACCEPTED", str(exc)) from exc

    def _assessment(self, raw: Union[DataQualityAssessmentArtifact, Mapping[str, Any]]) -> DataQualityAssessmentArtifact:
        try:
            return raw if isinstance(raw, DataQualityAssessmentArtifact) else DataQualityAssessmentArtifact.from_dict(raw, config=self.config, matrix=self.matrix, reasons=self.reasons)
        except DataQualityAssessmentValidationError as exc:
            raise ProvenanceQualityGateValidationError("V4050_NOT_ACCEPTED", str(exc)) from exc

    @staticmethod
    def _subject_ref(item: Mapping[str, Any]) -> Dict[str, str]:
        return {"id": str(item["feature_key"]), "hash": sha256_json(item)}

    def evaluate(
        self,
        *,
        tactical_artifact: Union[TacticalLeagueProfileArtifact, Mapping[str, Any]],
        quality_assessment: Union[DataQualityAssessmentArtifact, Mapping[str, Any]],
        revision: int = 1,
        supersedes_gate_record_id: Optional[str] = None,
    ) -> ProvenanceQualityGateRecord:
        tactical = self._tactical(tactical_artifact)
        assessment = self._assessment(quality_assessment)
        traw, qraw = tactical.to_dict(), assessment.to_dict()
        if traw["canonical_entity_refs"]["match_id"] != qraw["match_id"]:
            raise ProvenanceQualityGateValidationError("CANONICAL_IDENTITY_MISMATCH", "V4-049 and V4-050 are bound to different matches")
        tc = timestamp(traw["prediction_cutoff_at"], "tactical.prediction_cutoff_at", ProvenanceQualityGateValidationError)
        qc = timestamp(qraw["prediction_cutoff_at"], "assessment.prediction_cutoff_at", ProvenanceQualityGateValidationError)
        tk = timestamp(traw["kickoff_at"], "tactical.kickoff_at", ProvenanceQualityGateValidationError)
        qk = timestamp(qraw["kickoff_at"], "assessment.kickoff_at", ProvenanceQualityGateValidationError)
        if tc != qc or tk != qk:
            raise ProvenanceQualityGateValidationError("TIME_BOUNDARY_MISMATCH", "V4-049 and V4-050 cutoff/kickoff boundaries differ")
        cutoff_text, kickoff_text, _, _ = validate_boundary(traw["prediction_cutoff_at"], traw["kickoff_at"], ProvenanceQualityGateValidationError)
        blockers = [_reason_record(item, default_scope="AFFECTED_LINEAGE", default_domain="BATCH-14") for item in qraw["blockers"]]
        warnings = [_reason_record(item, default_scope="FEATURE", default_domain="BATCH-14") for item in qraw["warnings"]]
        for feature in traw["features"]:
            if feature["state"] in {"BLOCKED", "FUTURE_DATA"}:
                code = feature.get("reason_code") or feature["state"]
                if code in self.hard_rules:
                    blockers.append(_reason_record({"reason_code": code, "reason_detail": feature.get("reason_detail", "V4-049 feature is not consumable"), "scope": self.hard_rules[code], "domain": feature["category"], "input_ids": feature.get("source_refs", [])}, default_scope=self.hard_rules[code], default_domain=feature["category"]))
                else:
                    warnings.append(_reason_record({"reason_code": code, "reason_detail": feature.get("reason_detail", "V4-049 feature is not consumable"), "scope": "FEATURE", "domain": feature["category"], "input_ids": feature.get("source_refs", [])}, default_scope="FEATURE", default_domain=feature["category"]))
        feature_records: List[Mapping[str, Any]] = []
        for feature in traw["features"]:
            subject = self._subject_ref(feature)
            domain = str(feature["category"]).upper()
            related_hard = [item for item in blockers if item["scope"] in {"AFFECTED_LINEAGE", "CANDIDATE_SET", "MATRIX_RULE"} or str(item.get("domain", "")).upper() in {domain, "CONTEXT", "BATCH-14"}]
            state = str(feature["state"])
            if related_hard:
                eligibility_state = "BLOCKED"
            elif state == "AVAILABLE":
                eligibility_state = "ELIGIBLE"
            elif state in {"UNKNOWN", "UNAVAILABLE", "NOT_VERIFIED", "STALE", "CONFLICTED"}:
                rule = _non_hard(self.matrix, state)
                eligibility_state = "INELIGIBLE" if str(rule.get("feature_state", "INELIGIBLE")).startswith("INELIGIBLE") else "INELIGIBLE"
            else:
                eligibility_state = "BLOCKED"
            reasons = sorted({item["reason_code"] for item in related_hard} | ({str(feature.get("reason_code"))} if state != "AVAILABLE" and feature.get("reason_code") else set()))
            feature_records.append({"eligibility_id": _eligibility_id("FEATURE", subject["id"], eligibility_state, subject["hash"]), "contract_version": "feature-eligibility@1.0.0", "level": "FEATURE", "state": eligibility_state, "subject_ref": subject["id"], "subject_hash": subject["hash"], "required": bool(feature.get("required", False)), "upstream_refs": [traw["artifact_id"], qraw["assessment_id"]], "blocker_reason_codes": reasons if eligibility_state == "BLOCKED" else [], "warning_reason_codes": reasons if eligibility_state == "INELIGIBLE" else []})
        domain_records: List[Mapping[str, Any]] = []
        covered_domains = {str(item["category"]).upper() for item in traw["features"]}
        for domain in sorted(covered_domains):
            members = [item for item in feature_records if str(next(feature["category"] for feature in traw["features"] if feature["feature_key"] == item["subject_ref"])).upper() == domain]
            if any(item["state"] == "BLOCKED" for item in members) or any(str(blocker.get("domain", "")).upper() == domain and blocker["scope"] in {"AFFECTED_DOMAIN", "AFFECTED_LINEAGE"} for blocker in blockers):
                state = "BLOCKED"
            elif any(item["state"] == "INELIGIBLE" and item["required"] for item in members):
                state = "INELIGIBLE"
            elif any(item["state"] != "ELIGIBLE" for item in members):
                state = "PARTIALLY_ELIGIBLE"
            else:
                state = "ELIGIBLE"
            subject = {"id": f"{traw['canonical_entity_refs']['match_id']}:{domain.casefold()}", "hash": sha256_json({"domain": domain, "feature_ids": [item["subject_ref"] for item in members], "feature_hashes": [item["subject_hash"] for item in members]})}
            domain_records.append({"eligibility_id": _eligibility_id("DOMAIN", subject["id"], state, subject["hash"]), "contract_version": "feature-eligibility@1.0.0", "level": "DOMAIN", "state": state, "subject_ref": subject["id"], "subject_hash": subject["hash"], "required": any(item["required"] for item in members), "upstream_refs": [traw["artifact_id"], qraw["assessment_id"]], "blocker_reason_codes": sorted({item["reason_code"] for item in blockers if item["scope"] in {"AFFECTED_DOMAIN", "AFFECTED_LINEAGE", "CANDIDATE_SET"} and (str(item.get("domain", "")).upper() in {domain, "CONTEXT", "BATCH-14"})}), "warning_reason_codes": sorted({item["reason_code"] for item in warnings if str(item.get("domain", "")).upper() in {domain, "CONTEXT", "BATCH-14"}})})
        blocker_domains = {str(item.get("domain", "")).upper() for item in blockers if item.get("domain")}
        for domain in sorted(blocker_domains - covered_domains - {"BATCH-14"}):
            domain_blockers = [item for item in blockers if str(item.get("domain", "")).upper() == domain]
            domain_state = "BLOCKED" if any(item["scope"] in {"AFFECTED_DOMAIN", "AFFECTED_LINEAGE", "CANDIDATE_SET", "MATRIX_RULE"} for item in domain_blockers) else "PARTIALLY_ELIGIBLE"
            subject = {"id": f"{traw['canonical_entity_refs']['match_id']}:{domain.casefold()}", "hash": sha256_json({"domain": domain, "blockers": domain_blockers})}
            domain_records.append({"eligibility_id": _eligibility_id("DOMAIN", subject["id"], domain_state, subject["hash"]), "contract_version": "feature-eligibility@1.0.0", "level": "DOMAIN", "state": domain_state, "subject_ref": subject["id"], "subject_hash": subject["hash"], "required": True, "upstream_refs": [traw["artifact_id"], qraw["assessment_id"]], "blocker_reason_codes": sorted({item["reason_code"] for item in domain_blockers}), "warning_reason_codes": []})
        candidate_subject = {"id": f"{traw['canonical_entity_refs']['match_id']}:BATCH-14-CANDIDATE-SET", "hash": sha256_json({"match_id": traw["canonical_entity_refs"]["match_id"], "v4_049": traw["output_hash"], "v4_050": qraw["output_hash"]})}
        candidate_ref = {"id": candidate_subject["id"], "hash": candidate_subject["hash"]}
        if any(item["scope"] in {"CANDIDATE_SET", "AFFECTED_LINEAGE", "MATRIX_RULE"} for item in blockers):
            overall = "BLOCKED"
        elif any(item["state"] == "INELIGIBLE" and item["required"] for item in feature_records):
            overall = "INELIGIBLE"
        elif any(item["state"] != "ELIGIBLE" for item in feature_records):
            overall = "PARTIALLY_ELIGIBLE"
        else:
            overall = "ELIGIBLE"
        candidate_record = {"eligibility_id": _eligibility_id("CANDIDATE_SET", candidate_ref["id"], overall, candidate_ref["hash"]), "contract_version": "feature-eligibility@1.0.0", "level": "CANDIDATE_SET", "state": overall, "subject_ref": candidate_ref["id"], "subject_hash": candidate_ref["hash"], "required": True, "upstream_refs": [traw["artifact_id"], qraw["assessment_id"]], "blocker_reason_codes": sorted({item["reason_code"] for item in blockers}) if overall == "BLOCKED" else [], "warning_reason_codes": sorted({item["reason_code"] for item in warnings}) if overall != "ELIGIBLE" else []}
        def lineage_refs(items: Sequence[Mapping[str, Any]], field: str) -> List[Mapping[str, Any]]:
            return [{"id": str(item["id"]), "hash": item["hash"]} for item in items if item.get("hash")]
        assessment_refs = [{"id": qraw["assessment_id"], "hash": qraw["output_hash"]}]
        v049_refs = [{"id": traw["artifact_id"], "hash": traw["output_hash"]}]
        v050_refs = [{"id": qraw["assessment_id"], "hash": qraw["output_hash"]}]
        input_hashes = [str(item["hash"]) for item in qraw["assessment_inputs"] if item.get("hash")]
        evidence_refs = lineage_refs(qraw["assessment_inputs"], "evidence_refs")
        provenance_refs = [{"id": traw["artifact_id"], "hash": traw["provenance_hash"]}, {"id": qraw["assessment_id"], "hash": qraw["provenance_hash"]}]
        raw = {"gate_record_id": "pending", "artifact_kind": ARTIFACT_KIND, "contract_version": CONTRACT_VERSION, "match_id": traw["canonical_entity_refs"]["match_id"], "canonical_entity_refs": traw["canonical_entity_refs"], "prediction_cutoff_at": cutoff_text, "kickoff_at": kickoff_text, "assessment_input_refs": assessment_refs, "assessment_input_hashes": input_hashes, "v4_049_refs": v049_refs, "v4_049_hashes": [traw["output_hash"]], "v4_050_refs": v050_refs, "v4_050_hashes": [qraw["output_hash"]], "candidate_set_ref": candidate_ref, "feature_eligibility_records": feature_records, "domain_eligibility_records": domain_records, "candidate_set_eligibility_records": [candidate_record], "overall_gate_state": overall, "blockers": blockers, "warning_nonblocking_reasons": warnings, "evidence_refs": evidence_refs, "provenance_refs": provenance_refs, "generator_version": GENERATOR_VERSION, "implementation_hash": self.implementation_hash, "config_version": self.config["config_version"], "config_hash": self.config["canonical_hash"], "gating_matrix_version": self.matrix["matrix_version"], "gating_matrix_hash": self.matrix["canonical_hash"], "reason_registry_version": self.reasons["registry_version"], "reason_registry_hash": self.reasons["canonical_hash"], "revision": revision, "supersedes_gate_record_id": supersedes_gate_record_id}
        calculated = _hashes(raw)
        raw.update({name: value for name, value in zip(("input_hash", "payload_hash", "provenance_hash", "output_hash"), calculated)})
        raw["gate_record_id"] = str(uuid.uuid5(ARTIFACT_NAMESPACE, f"gate|{calculated[0]}|{calculated[1]}|{revision}"))
        return ProvenanceQualityGateRecord.from_dict(raw, config=self.config, matrix=self.matrix, reasons=self.reasons)

    generate = evaluate


class ProvenanceQualityGateStore:
    """Append-only local store for V4-051 gate records."""

    def __init__(self, config: Mapping[str, Any], matrix: Mapping[str, Any], reasons: Mapping[str, Any]):
        self.config, self.matrix, self.reasons = config, matrix, reasons
        self._items: Dict[str, ProvenanceQualityGateRecord] = {}

    @property
    def records(self) -> Tuple[ProvenanceQualityGateRecord, ...]:
        return tuple(self._items.values())

    def append(self, record: Union[ProvenanceQualityGateRecord, Mapping[str, Any]]) -> str:
        item = record if isinstance(record, ProvenanceQualityGateRecord) else ProvenanceQualityGateRecord.from_dict(record, config=self.config, matrix=self.matrix, reasons=self.reasons)
        existing = self._items.get(item.gate_record_id)
        if existing is not None:
            if existing.to_dict() == item.to_dict():
                return "DUPLICATE_NOOP"
            raise ProvenanceQualityGateValidationError("GATE_RECORD_ID_REUSE", "gate record identity cannot be reused")
        if item.supersedes_gate_record_id is not None:
            predecessor = self._items.get(item.supersedes_gate_record_id)
            if predecessor is None or predecessor.revision + 1 != item.revision:
                raise ProvenanceQualityGateValidationError("SUPERSEDES_INVALID", "corrections require the immediate predecessor and next revision")
            if predecessor.match_id != item.match_id:
                raise ProvenanceQualityGateValidationError("SUPERSEDES_FAMILY_CONFLICT", "correction must remain in the same match family")
        elif item.revision != 1:
            raise ProvenanceQualityGateValidationError("SUPERSEDES_REQUIRED", "a non-root revision must explicitly supersede the prior gate record")
        self._items[item.gate_record_id] = item
        return "APPEND"


ProvenanceQualityGateArtifact = ProvenanceQualityGateRecord


__all__ = [
    "ARTIFACT_KIND", "CONTRACT_VERSION", "GENERATOR_VERSION", "ProvenanceQualityGateArtifact", "ProvenanceQualityGateRecord", "ProvenanceQualityGateEngine", "ProvenanceQualityGateStore", "ProvenanceQualityGateValidationError",
]
