"""Fail-closed V4 prediction runtime boundaries.

This package contains interfaces and validation only.  Formal fitting,
artifact promotion, Production/Shadow execution, and persistence remain
outside this pre-training implementation wave.
"""

from .contracts import EngineRuntimeError, build_engine_output, validate_engine_output
from .engines import ENGINE_SPECS, EngineRuntime
from .frozen_input import FrozenInputScaffold, validate_frozen_input
from .model_loader import ModelArtifactLoader, ModelLoaderError
from .synthetic_pipeline import SyntheticPipeline

__all__ = [
    "ENGINE_SPECS", "EngineRuntime", "EngineRuntimeError", "FrozenInputScaffold",
    "ModelArtifactLoader", "ModelLoaderError", "SyntheticPipeline",
    "build_engine_output", "validate_engine_output", "validate_frozen_input",
]
