"""Read-only model artifact loader with an approval and role boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from src.prediction_training.ewp004_contract import Ewp004ContractError, validate_model_artifact_package
from src.prediction_training.ewp004_runtime import Ewp004Runtime


class ModelLoaderError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ModelArtifactLoader:
    """Resolve only explicit, approved, non-ephemeral artifacts.

    The loader never searches arbitrary paths and never writes a registry.
    With the current empty registry it therefore returns a measurable blocked
    state, which is the intended pre-training behavior.
    """

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        if self.project_root.drive.upper() != "F:":
            raise ModelLoaderError("F_DRIVE_REQUIRED", "V4 model artifacts must remain on F:")
        self.registry_path = self.project_root / "config/prediction_training/v4_prediction_model_registry.json"
        self.artifact_root = self.project_root / "approved_data/model_artifacts"
        self._contract_runtime = Ewp004Runtime(self.project_root)

    def registry(self) -> Mapping[str, Any]:
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ModelLoaderError("MODEL_REGISTRY_MISSING", str(self.registry_path)) from exc

    def resolve(self, engine_role: str) -> dict[str, Any]:
        artifacts = [item for item in self.registry().get("artifacts", []) if item.get("engine_role") == engine_role]
        approved = [item for item in artifacts if item.get("status") == "APPROVED_FOR_ENGINE" and item.get("ephemeral") is not True]
        if not approved:
            return {"status": "BLOCKED", "reason_code": "MODEL_ARTIFACT_NOT_APPROVED", "engine_role": engine_role, "artifact": None}
        if len(approved) != 1:
            return {"status": "BLOCKED", "reason_code": "MODEL_ARTIFACT_SELECTION_AMBIGUOUS", "engine_role": engine_role, "artifact": None}
        return {"status": "RESOLVED", "reason_code": None, "engine_role": engine_role, "artifact": approved[0]}

    def load(self, engine_role: str, path: Optional[str | Path] = None) -> Mapping[str, Any]:
        if path is None:
            resolved = self.resolve(engine_role)
            if resolved["status"] != "RESOLVED":
                raise ModelLoaderError(resolved["reason_code"], engine_role)
            candidate = resolved["artifact"].get("artifact_path")
            if not isinstance(candidate, str):
                raise ModelLoaderError("MODEL_ARTIFACT_PATH_MISSING", engine_role)
            path = self.artifact_root / candidate
        artifact_path = Path(path).resolve()
        try:
            artifact_path.relative_to(self.artifact_root)
        except ValueError as exc:
            raise ModelLoaderError("MODEL_ARTIFACT_PATH_OUTSIDE_BOUNDARY", str(artifact_path)) from exc
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ModelLoaderError("MODEL_ARTIFACT_NOT_FOUND", str(artifact_path)) from exc
        if artifact.get("engine_role") != engine_role or artifact.get("status") != "APPROVED_FOR_ENGINE" or artifact.get("ephemeral") is True:
            raise ModelLoaderError("MODEL_ARTIFACT_NOT_APPROVED", engine_role)
        try:
            validate_model_artifact_package(artifact, self._contract_runtime.contract)
        except (Ewp004ContractError, KeyError) as exc:
            raise ModelLoaderError("MODEL_ARTIFACT_CONTRACT_INVALID", str(exc)) from exc
        return artifact


__all__ = ["ModelArtifactLoader", "ModelLoaderError"]
