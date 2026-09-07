"""Read-only smoke test for the additive official-odds layout profiles.

The command reads raw PNG members from the handoff ZIP in memory.  It emits
detector and geometry coverage only; it never emits OCR evidence, traces, or
accepted official odds payloads.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.official_odds_cells import (
    RemediatedCellLocatorRegistry,
    RemediatedLayoutProfileRegistry,
    load_remediated_contract,
)
from src.official_odds_cells.contract import MARKETS


def run(handoff_zip: Path) -> dict[str, object]:
    contract = load_remediated_contract()
    detector = RemediatedLayoutProfileRegistry(contract)
    locator = RemediatedCellLocatorRegistry(contract)
    geometry_errors = locator.validate()
    profile_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    market_ready = {market: 0 for market in MARKETS}
    market_total = {market: 0 for market in MARKETS}
    artifacts: list[dict[str, object]] = []
    with zipfile.ZipFile(handoff_zip) as archive:
        raw_members = sorted(name for name in archive.namelist() if name.startswith("raw/") and name.endswith(".png"))
        for member in raw_members:
            detection = detector.detect(raw_image=archive.read(member))
            status_counts[detection.status] += 1
            if detection.status == "SELECTED":
                profile_counts[detection.profile_id] += 1
                profile = detector.profile(detection.profile_id)
                for market in MARKETS:
                    cells = profile["cell_geometry_pixels"][market]
                    market_total[market] += len(cells)
                    market_ready[market] += sum(cell is not None for cell in cells)
            artifacts.append({"member": member, "status": detection.status, "profile_id": detection.profile_id})
    selected = sum(profile_counts.values())
    return {
        "status": "PASS" if not geometry_errors and status_counts["UNSUPPORTED_LAYOUT"] == 0 and status_counts["AMBIGUOUS_LAYOUT"] == 0 else "FAIL",
        "mode": "NO_WRITE_PROFILE_DETECTION_AND_GEOMETRY_ONLY",
        "input_zip": str(handoff_zip),
        "profile_registry_identity": contract["layout_profile_registry"]["registry_identity"],
        "profile_selection_counts": dict(sorted(profile_counts.items())),
        "unsupported_count": status_counts["UNSUPPORTED_LAYOUT"],
        "ambiguous_count": status_counts["AMBIGUOUS_LAYOUT"],
        "selected_count": selected,
        "detector_status_counts": dict(sorted(status_counts.items())),
        "per_market_geometry_ready": {
            market: {"ready_artifacts": market_ready[market] // (3 if market == "SPF" else 4 if market == "RQSPF" else 8 if market == "TOTAL_GOALS" else 31 if market == "EXACT_SCORE" else 9), "artifact_count": selected, "cell_count": market_ready[market], "declared_cell_count": market_total[market]} for market in MARKETS
        },
        "htft_region_support": {"ready_artifacts": profile_counts["china-sports-lottery-official-standard"] + profile_counts["china-sports-lottery-official-spf-absent"], "artifact_count": selected},
        "total_goals_geometry_ready_artifacts": selected,
        "exact_score_geometry_ready_artifacts": selected,
        "geometry_registry_errors": geometry_errors,
        "ocr_evidence_generated": False,
        "accepted_official_odds_payload_written": False,
        "r002_generated": False,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff_zip", type=Path)
    args = parser.parse_args()
    result = run(args.handoff_zip)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
