"""V4-039 deterministic Feature Snapshot hashing and replay boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple, Union

from tools.migration_harness.common import canonical_json, sha256_json

from .feature_bundle import FEATURE_CATEGORIES, FeatureBundle, FeatureBundleValidationError


CONTRACT_VERSION = "feature-snapshot@1.0.0"
HASH_PROFILE = "feature-snapshot-canonical-json@1.0"
VOLATILE_FIELDS = ("generated_at", "metadata", "feature_snapshot_hash", "payload_hash", "provenance_hash")


class FeatureSnapshotValidationError(ValueError):
    """A Feature Snapshot cannot be deterministically represented."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _canonical_feature_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = ("value", "state", "unit", "source_refs", "evidence_refs", "derivation_ref", "generator_ref", "reason_code", "reason_detail")
    result: Dict[str, Any] = {}
    for field in allowed:
        if field in record:
            value = record[field]
            if field in {"source_refs", "evidence_refs"} and isinstance(value, (list, tuple)):
                value = sorted(value)
            result[field] = value
    return result


def _snapshot_payload(bundle: FeatureBundle) -> Dict[str, Any]:
    return {
        "contract_version": bundle.contract_version,
        "feature_schema_version": bundle.feature_schema_version,
        "generator_version": bundle.generator_version,
        "role": bundle.role,
        "config_version": bundle.config_version,
        "config_hash": bundle.config_hash,
        "canonical_entity_refs": bundle.to_dict()["canonical_entity_refs"],
        "canonical_fact_refs": bundle.to_dict()["canonical_fact_refs"],
        "official_odds_snapshot_refs": bundle.to_dict()["official_odds_snapshot_refs"],
        "external_market_refs": bundle.to_dict()["external_market_refs"],
        "team_context_refs": bundle.to_dict()["team_context_refs"],
        "evidence_graph_refs": bundle.to_dict()["evidence_graph_refs"],
        "input_hash": bundle.input_hash,
        "prediction_cutoff_at": bundle.prediction_cutoff_at,
        "kickoff_at": bundle.kickoff_at,
        "feature_values": {
            category: [_canonical_feature_record(record.to_dict()) for record in bundle.feature_values[category]]
            for category in FEATURE_CATEGORIES
        },
        "missingness_summary": bundle.to_dict()["missingness_summary"],
        "feature_quality": bundle.feature_quality.to_dict(),
        "quality_flags": sorted(bundle.quality_flags),
    }


@dataclass(frozen=True)
class FeatureSnapshotResult:
    contract_version: str
    hash_profile: str
    feature_snapshot_hash: str
    payload_hash: str
    provenance_hash: str
    volatile_fields_excluded: Tuple[str, ...]
    canonical_payload: bytes


class FeatureSnapshotHasher:
    """Compute and verify deterministic hashes without persistence or model execution."""

    @staticmethod
    def serialize(bundle: FeatureBundle) -> bytes:
        if not isinstance(bundle, FeatureBundle):
            raise FeatureSnapshotValidationError("BUNDLE_TYPE_INVALID", "serialize requires a V4-038 FeatureBundle")
        payload = _snapshot_payload(bundle)
        return canonical_json(payload)

    @classmethod
    def calculate(cls, bundle: FeatureBundle) -> FeatureSnapshotResult:
        try:
            canonical_payload = cls.serialize(bundle)
        except (FeatureBundleValidationError, TypeError, ValueError) as exc:
            raise FeatureSnapshotValidationError("SERIALIZATION_FAILED", str(exc)) from exc
        payload = _snapshot_payload(bundle)
        provenance_payload = {
            "canonical_entity_refs": payload["canonical_entity_refs"],
            "canonical_fact_refs": payload["canonical_fact_refs"],
            "official_odds_snapshot_refs": payload["official_odds_snapshot_refs"],
            "external_market_refs": payload["external_market_refs"],
            "team_context_refs": payload["team_context_refs"],
            "evidence_graph_refs": payload["evidence_graph_refs"],
            "input_hash": payload["input_hash"],
        }
        return FeatureSnapshotResult(
            contract_version=CONTRACT_VERSION,
            hash_profile=HASH_PROFILE,
            feature_snapshot_hash=sha256_json(payload),
            payload_hash=sha256_json({"feature_values": payload["feature_values"], "missingness_summary": payload["missingness_summary"], "feature_quality": payload["feature_quality"], "quality_flags": payload["quality_flags"]}),
            provenance_hash=sha256_json(provenance_payload),
            volatile_fields_excluded=VOLATILE_FIELDS,
            canonical_payload=canonical_payload,
        )

    @classmethod
    def seal(cls, bundle: FeatureBundle) -> FeatureBundle:
        """Return a new immutable bundle revision carrying the V4-039 snapshot hash."""

        result = cls.calculate(bundle)
        raw = bundle.to_dict()
        raw["feature_snapshot_hash"] = result.feature_snapshot_hash
        return FeatureBundle.from_dict(raw)

    @classmethod
    def verify(cls, bundle: FeatureBundle, expected_hash: str) -> bool:
        result = cls.calculate(bundle)
        if result.feature_snapshot_hash != expected_hash:
            raise FeatureSnapshotValidationError("FEATURE_SNAPSHOT_HASH_MISMATCH", "feature_snapshot_hash does not match deterministic serialization")
        return True

    @classmethod
    def replay_equal(cls, first: FeatureBundle, second: FeatureBundle) -> bool:
        return cls.calculate(first).feature_snapshot_hash == cls.calculate(second).feature_snapshot_hash

    @staticmethod
    def boundary_manifest() -> Mapping[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "hash_profile": HASH_PROFILE,
            "included": ["upstream lineage IDs/hashes", "input_hash", "schema/generator/config identity", "cutoff/kickoff", "typed feature values/states/units/source/evidence/derivation", "missingness", "feature_quality", "quality_flags"],
            "excluded": list(VOLATILE_FIELDS) + ["frozen_input_id", "frozen_input_hash", "prediction", "engine_output", "public_output"],
        }


__all__ = ["CONTRACT_VERSION", "HASH_PROFILE", "VOLATILE_FIELDS", "FeatureSnapshotValidationError", "FeatureSnapshotResult", "FeatureSnapshotHasher"]
