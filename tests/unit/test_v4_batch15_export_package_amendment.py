from __future__ import annotations

import io
import unittest
import zipfile

from src.historical_backfill_intake import IntakeValidationError, sha256_bytes, sha256_json
from src.historical_backfill_intake.package_contract import (
    EXCLUSION_REASONS,
    ZIP_PROFILE,
    build_deterministic_zip,
    exclusion_manifest_hash,
    exclusion_record_hash,
    package_substantive_body,
    run_synthetic_validation,
    serialize_manifest_text,
    synthetic_fixture,
    validate_deterministic_zip,
    validate_exclusion_manifest,
    validate_export_package_v1_1,
)


class ExportPackageAmendmentTests(unittest.TestCase):
    def test_synthetic_fixture_rebuilds_identically_and_separates_hashes(self):
        package, entries = synthetic_fixture()
        result = run_synthetic_validation()
        self.assertEqual(build_deterministic_zip(entries), build_deterministic_zip(entries))
        self.assertEqual(result["package_zip_sha256"], package["package_zip_sha256"])
        self.assertNotEqual(package["package_substantive_hash"], package["package_zip_sha256"])
        self.assertEqual(validate_deterministic_zip(build_deterministic_zip(entries), entries), package["package_zip_sha256"])

    def test_manifest_text_is_utf8_with_one_lf(self):
        encoded = serialize_manifest_text({"中文": "值", "a": 1})
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertNotIn(b"\r", encoded)
        self.assertEqual(encoded.count(b"\n"), 1)
        self.assertEqual(encoded[:-1].decode("utf-8"), '{"a":1,"中文":"值"}')

    def test_entry_order_change_is_rejected(self):
        _, entries = synthetic_fixture()
        canonical = build_deterministic_zip(entries)
        reversed_bytes = io.BytesIO()
        with zipfile.ZipFile(reversed_bytes, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            for path in reversed(list(entries)):
                archive.writestr(path, entries[path])
        with self.assertRaisesRegex(IntakeValidationError, "ZIP_ENTRY_ORDER_INVALID"):
            validate_deterministic_zip(reversed_bytes.getvalue(), entries)
        self.assertNotEqual(canonical, reversed_bytes.getvalue())

    def test_metadata_normalization_change_is_rejected(self):
        _, entries = synthetic_fixture()
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            for path in sorted(entries):
                content = entries[path]
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 2, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, content)
        with self.assertRaisesRegex(IntakeValidationError, "ZIP_METADATA_INVALID"):
            validate_deterministic_zip(changed.getvalue(), entries)

    def test_missing_exclusion_manifest_is_rejected(self):
        package, _ = synthetic_fixture()
        package.pop("exclusion_manifest")
        with self.assertRaisesRegex(IntakeValidationError, "PACKAGE_FIELD_MISSING"):
            validate_export_package_v1_1(package)

    def test_exclusion_records_are_deterministically_ordered(self):
        package, _ = synthetic_fixture()
        records = package["exclusion_manifest"]["records"]
        second = dict(records[0])
        second["exclusion_id"] = "ex-002"
        second["source_filename"] = "dashboard.json"
        second["category"] = "GENERATED_PREDICTION_DASHBOARD"
        second["reason_code"] = EXCLUSION_REASONS[second["category"]]
        second["source_reference"] = "library://synthetic/dashboard"
        second["source_sha256"] = sha256_bytes(b"dashboard")
        second["record_sha256"] = exclusion_record_hash(second)
        records.extend([second])
        package["exclusion_manifest"]["manifest_sha256"] = exclusion_manifest_hash(package["exclusion_manifest"])
        records.reverse()
        with self.assertRaisesRegex(IntakeValidationError, "EXCLUSION_ORDER_INVALID"):
            validate_exclusion_manifest(package["exclusion_manifest"], package["file_manifest"])

    def test_excluded_artifact_leaking_into_raw_set_is_rejected(self):
        package, _ = synthetic_fixture()
        record = package["exclusion_manifest"]["records"][0]
        package["file_manifest"][0].update({
            "original_filename": record["source_filename"],
            "library_file_id_or_ref": record["source_reference"],
            "original_file_sha256": record["source_sha256"],
        })
        with self.assertRaisesRegex(IntakeValidationError, "EXCLUDED_ARTIFACT_LEAK"):
            validate_export_package_v1_1(package, verify_hash=False)

    def test_exclusion_record_hash_or_reference_mismatch_is_rejected(self):
        package, _ = synthetic_fixture()
        package["exclusion_manifest"]["records"][0]["source_reference"] = "library://synthetic/changed"
        with self.assertRaisesRegex(IntakeValidationError, "EXCLUSION_RECORD_HASH_MISMATCH"):
            validate_export_package_v1_1(package, verify_hash=False)

    def test_betting_slip_and_generated_artifact_semantics_are_excluded(self):
        package, _ = synthetic_fixture()
        record = package["exclusion_manifest"]["records"][0]
        self.assertEqual(record["category"], "BETTING_SLIP")
        self.assertEqual(record["reason_code"], "BETTING_SLIP_NOT_RAW_FACT")
        package["file_manifest"][0]["generated_artifact"] = True
        with self.assertRaisesRegex(IntakeValidationError, "EXCLUDED_ARTIFACT_LEAK"):
            validate_export_package_v1_1(package, verify_hash=False)

    def test_exclusion_manifest_participates_in_substantive_hash(self):
        package, _ = synthetic_fixture()
        before = package["package_substantive_hash"]
        package["exclusion_manifest"]["records"][0]["reason_code"] = "BETTING_SLIP_NOT_RAW_FACT"
        self.assertEqual(before, sha256_json(package_substantive_body(package)))
        package["exclusion_manifest"]["records"][0]["source_filename"] = "changed.png"
        self.assertNotEqual(before, sha256_json(package_substantive_body(package)))

    def test_zip_profile_is_bound_to_package(self):
        package, _ = synthetic_fixture()
        self.assertEqual(package["zip_serialization_profile"], ZIP_PROFILE)
        package["zip_serialization_profile"] = "other"
        with self.assertRaisesRegex(IntakeValidationError, "ZIP_PROFILE_INVALID"):
            validate_export_package_v1_1(package, verify_hash=False)


if __name__ == "__main__":
    unittest.main()
