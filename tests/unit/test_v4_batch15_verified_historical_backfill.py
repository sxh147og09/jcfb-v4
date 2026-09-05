import copy
import unittest
from pathlib import Path

from src.historical_backfill_intake import (
    ARCHIVE_ROOT,
    STAGING_ROOT,
    UNKNOWN,
    IntakeValidationError,
    dry_run_validate,
    duplicate_semantics,
    evaluate_timestamp_evidence,
    sha256_json,
    validate_export_package,
    validate_manifest,
    validate_staging_path,
)


class B15VerifiedHistoricalBackfillTests(unittest.TestCase):
    @staticmethod
    def manifest(**overrides):
        body = {
            "manifest_id": "vhb-manifest-001",
            "import_batch_id": "vhb-batch-20260905-001",
            "revision": 1,
            "acquisition_mode": "VERIFIED_HISTORICAL_BACKFILL",
            "source_origin": "CHATGPT_LIBRARY_EXPORT",
            "export_package_id": "vhb-export-001",
            "export_package_hash": "sha256:" + "1" * 64,
            "external_source_identity": {"provider": "ChatGPT Library", "library_file_id_or_ref": "library:file-001"},
            "original_filename": "official-001.png",
            "original_file_sha256": "sha256:" + "2" * 64,
            "metadata_snapshot_sha256": "sha256:" + "3" * 64,
            "source_type": "OFFICIAL_SPORTS_LOTTERY_SCREENSHOT",
            "source_identity": "china-sports-lottery",
            "source_reference": "library:file-001",
            "chatgpt_upload_timestamp": "2026-09-01T12:00:00+08:00",
            "source_timestamp": UNKNOWN,
            "source_uploaded_at": UNKNOWN,
            "observed_at": UNKNOWN,
            "captured_at": UNKNOWN,
            "exported_at": "2026-09-05T10:00:00+08:00",
            "ingested_at": UNKNOWN,
            "prediction_cutoff_at": UNKNOWN,
            "kickoff_at": "2026-09-02T20:00:00+08:00",
            "timestamp_evidence_basis": "CHATGPT_LIBRARY_UPLOAD_TIMESTAMP_ONLY",
            "canonical_match_identity": {"canonical_match_id": "match-001", "competition": "league-1", "home": "home-1", "away": "away-1"},
            "intended_cutoff_profile": "T_MINUS_60M",
            "official_play_coverage": {
                "SPF": {"state": "AVAILABLE"},
                "RQSPF": {"state": "AVAILABLE", "exact_cutoff_visible": True, "handicap_line": "-0.25"},
                "EXACT_SCORE": {"state": "NOT_VERIFIED"},
                "TOTAL_GOALS": {"state": "AVAILABLE"},
                "HTFT": {"state": "AVAILABLE", "halftime_label": "H", "fulltime_label": "H"},
            },
            "extraction": {"extraction_method": "OCR_PLUS_MANUAL_REVIEW", "extraction_status": "REVIEWED", "extracted_market_payload": {"SPF": {"home": "2.10"}}},
            "artifact_classification": "RAW_FACT",
            "review_decision": "PROCEED_TO_EXPORT_INTAKE_VERIFICATION",
            "eligibility_decision": "NOT_YET_EVALUATED",
            "revision_lineage": {"supersedes": None},
            "artifact_substantive_hash": "sha256:" + "4" * 64,
            "provenance_root": "sha256:" + "5" * 64,
            "reviewer": "reviewer-001",
            "reviewed_at": "2026-09-05T10:01:00+08:00",
            "package_substantive_hash": "sha256:" + "6" * 64,
        }
        body.update(overrides)
        body["manifest_substantive_hash"] = sha256_json({key: value for key, value in body.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        return body

    @classmethod
    def package(cls, manifest=None, **overrides):
        item = manifest or cls.manifest()
        body = {
            "export_package_id": "vhb-export-001",
            "revision": 1,
            "contract_version": "verified-historical-backfill-export-package@1.0.0",
            "source_origin": "CHATGPT_LIBRARY_EXPORT",
            "created_at": "2026-09-05T10:00:00+08:00",
            "exported_at": "2026-09-05T10:00:00+08:00",
            "file_manifest": [{"manifest_id": item["manifest_id"], "original_filename": item["original_filename"], "original_file_sha256": item["original_file_sha256"], "library_file_id_or_ref": "library:file-001"}],
            "metadata_manifest": [{"manifest_id": item["manifest_id"], "metadata_snapshot_sha256": item["metadata_snapshot_sha256"]}],
            "manifests": [item],
        }
        item["export_package_hash"] = "sha256:" + "0" * 64
        item["manifest_substantive_hash"] = sha256_json({key: value for key, value in item.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        package_body = {key: value for key, value in body.items() if key not in {"package_substantive_hash", "package_sha256", "created_at", "exported_at"}}
        package_body["manifests"] = [{key: value for key, value in item.items() if key not in {"export_package_hash", "package_substantive_hash"}}]
        body["package_substantive_hash"] = sha256_json(package_body)
        item["export_package_hash"] = body["package_substantive_hash"]
        item["manifest_substantive_hash"] = sha256_json({key: value for key, value in item.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        body["package_sha256"] = sha256_json({key: value for key, value in body.items() if key != "package_sha256"})
        body.update(overrides)
        return body

    def test_upload_before_kickoff_is_review_only_and_not_earlier_cutoff_proof(self):
        result = evaluate_timestamp_evidence(self.manifest())
        self.assertEqual("PROCEED_TO_EXPORT_INTAKE_VERIFICATION", result["status"])
        self.assertEqual("REVIEW_REQUIRED", result["as_of_training_decision"])
        self.assertEqual("NOT_PERFORMED", result["import_action"])

    def test_upload_after_kickoff_is_not_eligible(self):
        result = evaluate_timestamp_evidence(self.manifest(chatgpt_upload_timestamp="2026-09-03T12:00:00+08:00"))
        self.assertEqual("NOT_ELIGIBLE_FOR_AS_OF_TRAINING", result["status"])

    def test_unknown_upload_and_kickoff_are_explicit_fail_closed_review(self):
        self.assertEqual("REVIEW_REQUIRED", evaluate_timestamp_evidence(self.manifest(chatgpt_upload_timestamp=UNKNOWN))["status"])
        self.assertEqual("REVIEW_REQUIRED", evaluate_timestamp_evidence(self.manifest(kickoff_at=UNKNOWN))["status"])

    def test_required_hash_identity_and_timestamp_fields_reject_missing_or_substitution(self):
        for field in ("original_file_sha256", "metadata_snapshot_sha256", "external_source_identity", "source_timestamp"):
            candidate = self.manifest()
            candidate.pop(field)
            with self.assertRaises(IntakeValidationError):
                validate_manifest(candidate)
        candidate = self.manifest()
        candidate["source_timestamp"] = candidate.pop("source_uploaded_at")
        with self.assertRaises(IntakeValidationError):
            validate_manifest(candidate)

    def test_generated_dashboard_and_betting_slip_are_excluded(self):
        for artifact_classification in ("GENERATED_PREDICTION", "BETTING_SLIP"):
            with self.assertRaisesRegex(ValueError, "GENERATED_ARTIFACT_EXCLUDED"):
                validate_manifest(self.manifest(artifact_classification=artifact_classification))
        with self.assertRaisesRegex(ValueError, "GENERATED_ARTIFACT_EXCLUDED"):
            validate_manifest(self.manifest(generated_artifact=True))

    def test_market_role_isolation_allows_missing_spf_without_invalidating_rqspf(self):
        candidate = self.manifest()
        candidate["official_play_coverage"]["SPF"] = {"state": "UNAVAILABLE", "unavailable_reason": "NOT_PUBLISHED"}
        candidate["manifest_substantive_hash"] = sha256_json({key: value for key, value in candidate.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        result = validate_manifest(candidate)
        self.assertEqual("REVIEW_REQUIRED", result["engine_eligibility"]["OUTCOME"]["status"])
        self.assertEqual("ELIGIBLE_FOR_REVIEW", result["engine_eligibility"]["HANDICAP"]["status"])

    def test_snapshot_duplicate_and_same_bytes_observation_semantics(self):
        first = self.manifest()
        self.assertEqual("DUPLICATE_NOOP", duplicate_semantics(first, copy.deepcopy(first)))
        same_bytes = self.manifest(chatgpt_upload_timestamp="2026-09-01T13:00:00+08:00")
        self.assertEqual("SAME_BYTES_DIFFERENT_EXTERNAL_OBSERVATION", duplicate_semantics(first, same_bytes))
        distinct = self.manifest(original_file_sha256="sha256:" + "9" * 64, source_timestamp="2026-09-01T11:00:00+08:00")
        self.assertEqual("RETAIN_AS_DISTINCT_SNAPSHOT", duplicate_semantics(first, distinct))

    def test_conflict_is_fail_closed(self):
        candidate = self.manifest(conflicts=["IMAGE_VS_OCR"])
        result = evaluate_timestamp_evidence(candidate)
        self.assertEqual("PROCEED_TO_EXPORT_INTAKE_VERIFICATION", result["status"])
        candidate["manifest_substantive_hash"] = sha256_json({key: value for key, value in candidate.items() if key not in {"manifest_substantive_hash", "exported_at", "export_package_hash"}})
        with self.assertRaisesRegex(ValueError, "PACKAGE_CONFLICT"):
            validate_export_package(self.package(candidate))

    def test_staging_is_f_drive_and_separate_from_archive(self):
        self.assertEqual("F:", validate_staging_path(STAGING_ROOT).drive.upper())
        self.assertNotEqual(STAGING_ROOT.resolve(), ARCHIVE_ROOT.resolve())
        with self.assertRaisesRegex(ValueError, "F_DRIVE_REQUIRED"):
            validate_staging_path("C:/Users/Administrator/Desktop/historical_backfill_staging")
        with self.assertRaisesRegex(ValueError, "ARCHIVE_ROOT_FORBIDDEN"):
            validate_staging_path(ARCHIVE_ROOT)

    def test_package_hash_boundary_and_dry_run_do_not_write(self):
        package = self.package()
        self.assertEqual(1, validate_export_package(package)["manifest_count"])
        result = dry_run_validate(package)
        self.assertEqual("VALID_FOR_INTAKE", result["state"])
        self.assertFalse(result["write_performed"])
        self.assertEqual([], [path for path in ARCHIVE_ROOT.rglob("*") if path.is_file()])

    def test_revision_supersedes_is_required(self):
        candidate = self.manifest(revision=2, revision_lineage={"supersedes": None})
        with self.assertRaisesRegex(ValueError, "SUPERSEDES_REQUIRED"):
            validate_manifest(candidate)


if __name__ == "__main__":
    unittest.main()
