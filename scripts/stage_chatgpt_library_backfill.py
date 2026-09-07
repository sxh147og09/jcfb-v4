"""Validate and append-stage a real Library export package without archive writes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.historical_backfill_intake import AppendOnlyStaging, IntakeValidationError  # noqa: E402
from src.historical_backfill_intake.package_contract import normalize_zip_entry_path, validate_export_package_v1_1  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-json", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True, help="directory containing the declared raw package members")
    parser.add_argument("--package-name", required=True)
    args = parser.parse_args()
    package = json.loads(args.package_json.read_text(encoding="utf-8"))
    validate_export_package_v1_1(package)
    raw_root = args.raw_root.resolve()
    raw_files: dict[str, bytes] = {}
    for item in package["file_manifest"]:
        relative = normalize_zip_entry_path(str(item["original_filename"]))
        path = (raw_root / relative).resolve()
        if raw_root not in path.parents:
            raise IntakeValidationError("RAW_PATH_ESCAPE", relative)
        if not path.is_file():
            raise IntakeValidationError("RAW_FILE_MISSING", str(path))
        raw_files[relative] = path.read_bytes()
    result = AppendOnlyStaging(ROOT).stage_validated_package(package, package_name=args.package_name, raw_files=raw_files)
    if result.get("archive_written") or result.get("training_written"):
        raise IntakeValidationError("WRITE_BOUNDARY_VIOLATION", "stager reported forbidden write")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntakeValidationError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(2)
