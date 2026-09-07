"""Run the fail-closed AI visual review sidecar against the frozen 432-cell queue."""

from __future__ import annotations

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ai_visual_review.runner import run


if __name__ == "__main__":
    result = run()
    print("JCFB V4 AI VISUAL REVIEW: " + result["status"])
    print("candidate_count=" + str(result["candidate_count"]))
    print("status_counts=" + str(result["status_counts"]))
    print("provider_available=" + str(result["provider_available"]))
