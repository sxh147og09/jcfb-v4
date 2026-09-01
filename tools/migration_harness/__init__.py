"""Fail-closed, no-write migration harness for JCFB V4 BATCH-02/BATCH-03.

The package intentionally contains no database driver and no connector.  It
parses migration metadata, validates supplied evidence, and emits plans or
explicitly pending runtime results.
"""

from .models import (
    CheckStatus,
    ExecutionMode,
    RunnerStatus,
)

__all__ = ["CheckStatus", "ExecutionMode", "RunnerStatus"]
