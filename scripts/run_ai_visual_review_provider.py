"""Run the connected provider adapter over the existing review queue.

This command is intentionally opt-in and local/staging-only.  Without a real
credential it exits without writing anything; it never accepts odds or writes
the historical archive.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ai_visual_review.provider import OpenAICompatibleVisionProvider, ProviderNeutralBatchVisionAdapter, StagingImageResolver, run_adapter_batch


def main() -> int:
    staging = ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001"
    queue = staging / "manual_review_workbench_r001_revision_001/review_queue.jsonl"
    raw_zip = staging / "chatgpt-library-handoff.zip"
    output = staging / "ai_visual_review_provider_r001_revision_001"
    provider = OpenAICompatibleVisionProvider()
    if not provider.available:
        print("VISION_PROVIDER_CONNECTION_REQUIRED")
        print("No output written; provide JCFB_VISION_API_KEY (and optionally JCFB_VISION_API_URL/JCFB_VISION_MODEL).")
        return 2
    adapter = ProviderNeutralBatchVisionAdapter(provider, image_resolver=StagingImageResolver(staging, raw_zip))
    manifest = run_adapter_batch(queue, output, adapter, reviewer_run_id="AI-VISUAL-PROVIDER-20260907-R001")
    print("AI VISUAL PROVIDER REVIEW: COMPLETE_WITH_FAIL_CLOSED_ESCALATIONS")
    print(f"candidate_count={manifest['candidate_count']}")
    print(f"status_counts={manifest['status_counts']}")
    print("accepted_payload_written=false")
    print("archive_written=false")
    print("training_written=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
