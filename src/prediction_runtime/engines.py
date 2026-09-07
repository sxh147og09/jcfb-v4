"""Independent prediction-engine shells with a formal execution gate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from .contracts import EngineRuntimeError, build_engine_output, sha256_json
from .frozen_input import FrozenInputError, validate_frozen_input
from .model_loader import ModelArtifactLoader, ModelLoaderError


ENGINE_SPECS = {
    "OUTCOME": {"engine_version": "outcome-engine@4.0.0", "config_version": "outcome-engine-config@4.0.0"},
    "HANDICAP": {"engine_version": "handicap-engine@4.0.0", "config_version": "handicap-engine-config@4.0.0"},
    "GOALS": {"engine_version": "goals-engine@4.0.0", "config_version": "goals-engine-config@4.0.0"},
    "HTFT": {"engine_version": "htft-engine@4.0.0", "config_version": "htft-engine-config@4.0.0"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineRuntime:
    def __init__(self, project_root: str, *, loader: Optional[ModelArtifactLoader] = None, predictor: Optional[Callable[[str, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]] = None) -> None:
        self.project_root = project_root
        self.loader = loader or ModelArtifactLoader(project_root)
        self.predictor = predictor

    def _blocked(self, role: str, input_value: Mapping[str, Any], code: str, message: str) -> dict[str, Any]:
        spec = ENGINE_SPECS[role]
        input_hash = sha256_json({"engine_role": role, "input": input_value})
        frozen_hash = sha256_json(input_value)
        now = _now()
        return build_engine_output(
            role="EXPERIMENT", engine_role=role, model_name="NOT_AVAILABLE", model_version="NOT_AVAILABLE",
            engine_version=spec["engine_version"], revision="r001", implementation_hash=sha256_json({"runtime": "jcfb-v4-prediction-runtime@1.0.0"}),
            config_version=spec["config_version"], config_hash=sha256_json({"config": spec["config_version"]}), input_hash=input_hash,
            frozen_input_id=str(input_value.get("frozen_input_id", "NOT_AVAILABLE")), frozen_input_hash=frozen_hash,
            run_at=now, run_completed_at=now, runtime_ms=0, payload={"state": "BLOCKED", "reason_code": code},
            status="BLOCKED", errors=({"code": code, "message": message},),
        )

    def run(self, role: str, frozen_input: Mapping[str, Any], features: Mapping[str, Any], *, execution_authorized: bool = False, model_artifact: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if role not in ENGINE_SPECS:
            raise EngineRuntimeError("ENGINE_ROLE_INVALID", role)
        try:
            validate_frozen_input(frozen_input, require_formal_frozen=True)
        except FrozenInputError as exc:
            return self._blocked(role, frozen_input, exc.code, exc.message)
        if not execution_authorized:
            return self._blocked(role, frozen_input, "FORMAL_ENGINE_EXECUTION_NOT_AUTHORIZED", "formal prediction-engine execution is outside the current authorized wave")
        if model_artifact is None:
            try:
                model_artifact = self.loader.load(role)
            except ModelLoaderError as exc:
                return self._blocked(role, frozen_input, exc.code, exc.message)
        if model_artifact.get("status") != "APPROVED_FOR_ENGINE" or model_artifact.get("engine_role") != role:
            return self._blocked(role, frozen_input, "MODEL_ARTIFACT_NOT_APPROVED", role)
        if self.predictor is None:
            return self._blocked(role, frozen_input, "PREDICTOR_BINDING_NOT_IMPLEMENTED", role)
        try:
            payload = self.predictor(role, features, model_artifact)
            if not isinstance(payload, Mapping):
                raise TypeError("predictor must return an object")
        except Exception as exc:
            return self._blocked(role, frozen_input, "PREDICTOR_EXECUTION_FAILED", type(exc).__name__)
        now = _now()
        input_hash = sha256_json({"role": role, "frozen_input": frozen_input, "features": features})
        return build_engine_output(
            role="PRODUCTION", engine_role=role, model_name=str(model_artifact.get("model_name", f"{role.lower()}-model")), model_version=str(model_artifact.get("model_version", "UNKNOWN")),
            engine_version=ENGINE_SPECS[role]["engine_version"], revision=str(model_artifact.get("revision", "r001")), implementation_hash=sha256_json({"runtime": "jcfb-v4-prediction-runtime@1.0.0"}),
            config_version=ENGINE_SPECS[role]["config_version"], config_hash=sha256_json({"config": ENGINE_SPECS[role]["config_version"]}), input_hash=input_hash,
            frozen_input_id=str(frozen_input["frozen_input_id"]), frozen_input_hash=str(frozen_input["frozen_input_hash"]), run_at=now, run_completed_at=now, runtime_ms=0, payload=payload,
        )


__all__ = ["ENGINE_SPECS", "EngineRuntime"]
