"""Validate Library backfill handoff/candidate metadata without materializing bytes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.historical_backfill_intake import IntakeValidationError  # noqa: E402
from src.historical_backfill_intake.library_handoff import build_candidate_dedupe_index, validate_candidate_manifest, validate_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dedupe-output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("contract_identity") == "chatgpt-library-backfill-handoff@1.0.0":
        result = validate_handoff(manifest)
        candidates = manifest.get("candidate_manifest", [])
    elif manifest.get("contract_identity") == "chatgpt-library-backfill-candidate-manifest@1.0.0":
        result = {"contract_identity": manifest["contract_identity"], **validate_candidate_manifest(manifest.get("candidates", []))}
        candidates = manifest.get("candidates", [])
    else:
        raise IntakeValidationError("HANDOFF_CONTRACT_INVALID", str(manifest.get("contract_identity")))
    if args.dedupe_output:
        args.dedupe_output.write_text(json.dumps(build_candidate_dedupe_index(candidates), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        result["dedupe_output"] = str(args.dedupe_output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntakeValidationError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(2)
