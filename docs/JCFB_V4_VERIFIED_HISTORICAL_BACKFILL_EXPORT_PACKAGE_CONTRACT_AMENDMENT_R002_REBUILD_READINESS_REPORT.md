# JCFB V4 VERIFIED HISTORICAL BACKFILL EXPORT PACKAGE CONTRACT AMENDMENT & r002 REBUILD READINESS REPORT

**Review date:** 2026-09-07  
**Workspace:** `F:\Projects\jcfb-v4`  
**Review class:** additive governance / contract amendment and no-write synthetic validation  
**Archive write:** NO  
**Real r002 package materialization:** NO

## 1. Decision summary

```text
EXPORT_PACKAGE_CONTRACT_AMENDMENT_STATUS = COMPLETE
ZIP_SERIALIZATION_READINESS = READY
EXCLUSION_MANIFEST_BINDING_READINESS = READY
PACKAGE_R002_REBUILD_READINESS = BLOCKED

CANONICAL_MATCH_IDENTITY_READINESS = BLOCKED
EXTRACTION_PROVENANCE_REVIEW_READINESS = BLOCKED
INTAKE_RUNTIME_AUTHORIZATION_READINESS = BLOCKED
Current Training Readiness = BLOCKED / TRAINING_DATA_INSUFFICIENT
```

The contract blockers from the prior review are resolved only at the contract and
synthetic-fixture level. The real r002 package is not ready: the approved staging
root still contains only `.gitkeep`, so the 40 canonical match identities, 64
artifact mappings, 64 extraction-provenance records, and final real-package ZIP
bytes have not been generated or reviewed.

This amendment is additive. It does not reopen or rewrite the completed
B15-EWP-001 or B15-EWP-001-ADDENDUM-001 facts, and it does not authorize archive
intake, dataset construction, training, or any downstream model work.

## 2. Prior evidence and amendment identity

The prior read-only remediation review was committed as documentation-only evidence:

```text
prior review evidence commit:
22ca589413e93d67df550079cac6cb59e219a699
```

The current amendment is:

```text
amendment_id: B15-EWP-001-ADDENDUM-002
amendment_revision: r002
amendment_contract_identity: v4-batch15-verified-historical-backfill-export-package-amendment@1.0.0
package_contract_identity: verified-historical-backfill-export-package@1.1.0
base_package_contract: verified-historical-backfill-export-package@1.0.0
compatibility: MINOR_COMPATIBLE
supersedes: verified-historical-backfill-export-package@1.0.0
```

The implementation was committed in the focused contract commit:

```text
41b9c18eaa6e460502d9222a4d034783aefcf8c1
chore(v4): govern deterministic historical backfill export packaging
```

The frozen `@1.0.0` schema and ADDENDUM-001 remain unchanged. The new `@1.1.0`
schema explicitly records the base identity, compatibility, unchanged base
semantics, ZIP profile, and exclusion-manifest binding.

## 3. Deterministic ZIP serialization contract

The package is bound to `v4-deterministic-zip@1.0` with these exact rules:

| Area | Frozen rule |
|---|---|
| Format | PKZIP ZIP32; version needed 2.0; version made by DOS 2.0; ZIP64 forbidden |
| Entry order | Normalize every path first, then sort by normalized UTF-8 path bytes ascending |
| Path | POSIX relative path, NFC Unicode normalization, no drive/absolute path, no `\\`, NUL, empty segment, `.`, `..`, duplicate separator, or directory suffix |
| Filename encoding | UTF-8 with the EFS/UTF-8 flag (`0x800`) in local and central headers |
| Directories | No directory entries; parent directories are implicit |
| Compression | STORED (`method = 0`); compression level is not applicable |
| Timestamp | DOS timestamp exactly `1980-01-01 00:00:00`; no time-varying extra field |
| Platform/attributes | DOS platform; version fields fixed at 20; internal attributes `0`; external attributes `0x20` DOS archive bit only; no Unix mode or executable bits |
| Extra/comment fields | Entry extra fields empty; entry comments empty; archive comment empty |
| CRC | CRC-32 of uncompressed bytes appears in both local and central headers; stored and uncompressed sizes must equal; data descriptors forbidden |
| Manifest text | Canonical JSON under `v4-canonical-json@1.0`, UTF-8, followed by exactly one LF; CRLF is forbidden |
| Rebuild | The same substantive package inputs and entry bytes must produce identical ZIP bytes and identical ZIP SHA-256 |

The implementation uses an in-memory ZIP32 writer with fixed headers rather than
delegating metadata defaults to a platform-dependent ZIP writer. The validator
reads the resulting archive and checks member order, path normalization, EFS,
timestamps, versions, attributes, compression, CRC, sizes, extra fields,
comments, and content bytes. A changed member order or normalized metadata is a
failure even when the payload bytes are unchanged.

## 4. Hash authority and exact distinction

The amendment preserves the existing canonical JSON/hash contract and adds a
separate transport hash:

| Field | Payload | Authority |
|---|---|---|
| `package_substantive_hash` | Package canonical JSON body under `v4-canonical-json@1.0`, excluding `created_at`, `exported_at`, both package hash fields, `package_zip_sha256`, and nested manifest `export_package_hash` / `package_substantive_hash` | Authoritative semantic package identity; exclusion manifest is included |
| `package_sha256` | Existing package-object canonical JSON hash, excluding only `package_sha256` | Legacy/current package-object identity; explicitly not a ZIP hash |
| `package_zip_sha256` | SHA-256 of the final serialized ZIP bytes only | Authoritative transport-integrity identity; cannot replace either JSON identity |

The ZIP hash is excluded from the substantive hash to avoid a circular
dependency. A changed exclusion record changes the substantive hash. A changed
ZIP member order or metadata changes the ZIP-byte hash and is rejected by the
deterministic ZIP validator.

## 5. Exclusion manifest binding

Every `@1.1.0` package must include an exclusion manifest with schema identity:

```text
verified-historical-backfill-exclusion-manifest@1.0.0
```

Each record requires `exclusion_id`, `category`, `reason_code`,
`source_filename`, `source_reference`, `source_sha256`,
`artifact_classification`, and `record_sha256`. The allowed category/reason
pairs are fixed:

| Category | Required reason | Classification |
|---|---|---|
| `BETTING_SLIP` | `BETTING_SLIP_NOT_RAW_FACT` | `EXCLUDED` |
| `GENERATED_PREDICTION_DASHBOARD` | `GENERATED_PREDICTION_NOT_RAW_FACT` | `EXCLUDED` |
| `RECOMMENDATION_ARTIFACT` | `RECOMMENDATION_NOT_RAW_FACT` | `EXCLUDED` |

Records are sorted by the UTF-8 tuple
`category, source_reference, source_filename, source_sha256, exclusion_id`.
Each record hash covers the record without `record_sha256`. The manifest hash
covers `schema_version` and the ordered records without `manifest_sha256`.
The complete exclusion manifest participates in `package_substantive_hash`.

The accepted raw set is `RAW_FACT` only. An excluded record's filename,
Library/reference identity, and source hash may not occur in the accepted
`file_manifest` or import-manifest set. Generated prediction dashboards,
recommendation artifacts, betting slips, and V3/V4 prediction artifacts remain
outside the accepted raw source set and can never be promoted by changing their
label.

## 6. Implemented validators and tests

The focused implementation is in:

- `src/historical_backfill_intake/package_contract.py`
- `scripts/validate_v4_batch15_export_package_amendment.py`
- `tests/unit/test_v4_batch15_export_package_amendment.py`
- `config/prediction_training/v4_batch15_verified_historical_backfill_export_package_schema_1_1_0.json`
- `config/prediction_training/v4_batch15_verified_historical_backfill_contract_amendment_002.json`

Focused coverage includes:

- substantive hash and final ZIP-byte hash recomputation;
- deterministic two-build byte/hash equality;
- entry-order mutation rejection;
- DOS metadata mutation rejection;
- UTF-8/LF manifest serialization;
- missing exclusion manifest rejection;
- deterministic exclusion ordering;
- excluded-artifact leakage into the accepted raw set;
- exclusion record reference/hash mismatch;
- betting-slip and generated-dashboard exclusion semantics;
- exclusion-manifest participation in the substantive hash;
- ZIP profile binding.

Results:

```text
focused amendment tests: 11 / 11 PASS
focused amendment validator: PASS
synthetic deterministic ZIP rebuild: PASS
full repository unit tests: 596 / 596 PASS
git diff --check at implementation boundary: PASS
```

## 7. Legacy/current validation sweep

Passing validators:

```text
validate_v4_batch15_verified_historical_backfill.py: PASS
validate_v4_batch15_ewp001.py: PASS
validate_v4_batch15_ewp002.py: PASS
validate_v4_batch15_ewp003_contract.py: PASS
validate_v4_batch15_ewp004_contract.py: PASS
validate_v4_batch15_training_amendment.py: PASS
validate_v4_batch15_export_package_amendment.py: PASS
validate_v4_batch15_governance.ps1: PASS
validate_v4_batch_03.ps1: PASS
validate_v4_data_contracts.ps1: PASS
validate_v4_migration_design.ps1: PASS
validate_v4_production_target_binding.ps1: PASS
validate_v4_runtime_candidates.ps1: PASS
validate_v4_supabase_preflight.ps1: PASS
validate_v4_versioning.ps1: PASS
```

Two pre-existing validators remain red because their frozen assertions do not
match the active repository baseline; they did not fail on any amendment file:

1. `validate_v4_batch15_entry_remediation.py` reports downstream EWP
   authorization leakage because the current registry intentionally records
   EWP-002/EWP-003/EWP-004 as complete and authorized, and it rejects the
   already-existing zero-candidate EWP-002 dataset evidence files.
2. `validate_v4_migration_harness_design.ps1` reports three historical BATCH-04/
   BATCH-05 text-boundary mismatches in the existing batch plan, master checklist,
   and acceptance rules.

These stale assertions were not changed in this contract-only task. No EWP was
rolled back, and no existing dataset/archive state was altered.

## 8. Rebuild readiness and remaining blockers

```text
PACKAGE_R002_REBUILD_READINESS = BLOCKED
CANONICAL_MATCH_IDENTITY_READINESS = BLOCKED
EXTRACTION_PROVENANCE_REVIEW_READINESS = BLOCKED
INTAKE_RUNTIME_AUTHORIZATION_READINESS = BLOCKED
```

Remaining blockers are evidence-boundary blockers, not contract blockers:

- `approved_data/historical_backfill_staging` has no r001 package, raw PNG,
  metadata snapshot, candidate mapping, or immutable predecessor package;
- the actual 40 V4-020 identities cannot be generated without the required
  data-date/official-number and competition/team structural facts;
- the actual 64 artifact mappings and V4-025/V4-026/V4-027 provenance records
  have not been reviewed;
- `source_timestamp`, `captured_at`, and `observed_at` remain literal `UNKNOWN`
  unless independently evidenced; no time may be invented;
- no real package ZIP bytes or real `package_zip_sha256` exist to validate;
- archive intake remains separately unauthorized.

## 9. Boundary audit

```text
historical_source_archive file count: 0
historical_backfill_staging file count: 1 (.gitkeep only)
archive/staging data changed from frozen baseline: 0 paths
V3.3.3 changed paths from frozen baseline: 0
EWP-005.execution_authorized: false
archive records: 0
usable training samples: 0
```

No archive record/revision was created. EWP-002/EWP-003 were not rerun. EWP-005
was not authorized or executed. There was no model fitting, calibration,
promotion, V4-076, V4-052..055, Production, Shadow, Public, Supabase, migration,
or V3.3.3 modification.

## 10. Only allowed next step

Provide the real r001 package, or its complete immutable raw/metadata/mapping
equivalent, under the approved F-drive staging root. Then perform an r002
no-write rebuild and independently validate the package substantive hash,
package-object hash, deterministic ZIP bytes/hash, 40 canonical identities, 64
extraction-provenance records, and exclusion bindings. Do not proceed to archive
intake until every one of those checks passes; do not use this amendment as
authorization for archive write or training.

## 11. Final traceability

```text
implementation commit: 41b9c18eaa6e460502d9222a4d034783aefcf8c1
report finalization boundary HEAD: 41b9c18eaa6e460502d9222a4d034783aefcf8c1
Working Tree before this report: CLEAN
```

This report is documentation-only evidence. Its own final documentation commit
is the final repository HEAD for handoff; the exact value is recorded by
`git rev-parse HEAD` after that commit and returned with the completion summary.
