# JCFB V4 BATCH-15 B15-EWP-001 ADDITIVE VERIFIED HISTORICAL BACKFILL INTAKE GOVERNANCE AMENDMENT & IMPLEMENTATION READINESS REVIEW REPORT

## 1. Amendment identity

| Field | Decision |
|---|---|
| Amendment | `B15-EWP-001-ADDENDUM-001` |
| Revision | `r001` |
| Amendment contract | `v4-batch15-verified-historical-backfill-intake-amendment@1.0.0` |
| Import manifest contract | `verified-historical-backfill-import-manifest@1.0.0` |
| Export package contract | `verified-historical-backfill-export-package@1.0.0` |
| Execution class | Additive governance amendment + contract remediation + implementation readiness review |
| Archive/data execution | Not performed |

This amendment is additive. It does not reopen B15-EWP-001, modify its closure
evidence, or replace its `r002` revision.

## 2. EWP-001 historical fact preservation

`B15-EWP-001` remains `COMPLETE`, revision `r002`, and execution-authorized in
the existing registry. The amendment records `reopens_completed_work_package:
false`, preserves the existing acceptance/closure documents, and introduces a
separate historical intake identity. No archive record, archive revision, or
training sample was created.

## 3. Acquisition mode and authorization boundary

The frozen historical entrypoint is
`verified_historical_backfill_export_package_dry_run` with acquisition mode
`VERIFIED_HISTORICAL_BACKFILL`. It is separate from
`PROSPECTIVE_CAPTURE`. This round only validates export and staging contracts;
archive write authorization is `false`, import action is `NOT_PERFORMED`, and
training readiness effect is `NONE`.

The candidate baseline remains review-level only:

| Candidate population | Count/status |
|---|---:|
| Unique matches | 40 |
| Official China Sports Lottery screenshots | 64 |
| Matches with two distinct pre-match snapshots | 24 |
| Matches with one snapshot | 16 |
| Current status | `VERIFIED_HISTORICAL_BACKFILL_CANDIDATE / PENDING_EXPORT_AND_INTAKE_VERIFICATION` |

Betting slips, generated prediction dashboards, recommendation cards, and
prediction summaries are excluded.

## 4. Import manifest contract

Each manifest requires a positive revision, `import_batch_id`, source origin,
export package binding, external ChatGPT Library identity, original filename
and SHA-256, metadata snapshot SHA-256, source identity/reference, canonical
match identity, intended cutoff profile, official-play coverage, extraction
method/status/payload, raw-fact artifact classification, review decision,
eligibility decision, revision lineage,
artifact substantive hash, provenance root, reviewer/reviewed time, all
timestamp fields, package substantive hash, and manifest substantive hash.

The required fields are machine-checked by
`config/prediction_training/v4_batch15_verified_historical_backfill_import_manifest_schema.json`.
Missing original hash, external identity, metadata snapshot hash, or any
required timestamp field fails closed. `UNKNOWN` is explicit data, not an
empty or substituted value.

## 5. ChatGPT timestamp evidence policy

`chatgpt_upload_timestamp` means only:

> The artifact existed in the ChatGPT Library no later than this upload timestamp.

It is not bookmaker publication time, official publish time, original odds
time, observed time, or capture time. An upload before kickoff permits only
`PROCEED_TO_EXPORT_INTAKE_VERIFICATION`; it does not prove that the artifact
was available at an earlier prediction cutoff. Upload at or after kickoff is
`NOT_ELIGIBLE_FOR_AS_OF_TRAINING`. Unknown upload time is `REVIEW_REQUIRED`.
Kickoff conflicts are fail-closed as `CONFLICT` in package review.

The following fields remain distinct and are never auto-interchanged:
`source_timestamp`, `source_uploaded_at`, `observed_at`, `captured_at`,
`exported_at`, `ingested_at`, `prediction_cutoff_at`, and `kickoff_at`.

## 6. F-drive staging and export package

The only approved staging root is:

`F:\Projects\jcfb-v4\approved_data\historical_backfill_staging\`

It is separate from the final archive root:

`F:\Projects\jcfb-v4\approved_data\historical_source_archive\`

C-drive, Desktop, Downloads, `.runtime`, test fixtures, V3.3.3, and
Supabase/db-blob locations are not approved historical source roots.

An export package requires `export_package_id`, revision, created/exported
times, one file-manifest entry per original file, one metadata-manifest entry
per file, one import manifest per file, `package_substantive_hash`, and
`package_sha256`; each manifest binds to the package substantive hash. The
substantive hash excludes volatile `created_at` and
`exported_at`; the package SHA-256 is separately checked. Every candidate
artifact can therefore be independently checked against original bytes,
original SHA-256, Library identity, and metadata snapshot hash.

## 7. Dedupe, revision, and conflict semantics

Exact `DUPLICATE_NOOP` requires the same original bytes hash, external source
identity, canonical match identity, substantive extracted market payload, and
the same external observation timestamp. Same bytes with a different upload
timestamp is `SAME_BYTES_DIFFERENT_EXTERNAL_OBSERVATION`: provenance is
retained, but it is not treated as two independent market states. A same-match
candidate with a different timestamp or substantive payload is retained as a
distinct snapshot. A revision greater than `r001` must name its predecessor in
`revision_lineage.supersedes`; corrections are append-only.

Image/OCR, manual/OCR, match identity, kickoff, handicap, market availability,
and timestamp disagreements are conflict inputs. The validator does not pick
the value that merely appears plausible. A package containing such a conflict
returns `CONFLICT` and writes nothing.

## 8. Official odds extraction and engine eligibility

The manifest binds the active equivalent official contracts `V4-025`, `V4-026`,
and `V4-027`, and records market-level states for `SPF`, `RQSPF`,
`EXACT_SCORE`, `TOTAL_GOALS`, and `HTFT` as `AVAILABLE`, `UNAVAILABLE`,
`NOT_VERIFIED`, or `BLOCKED`. An unavailable market requires an explicit
reason; a missing SPF does not invalidate the whole match.

Eligibility is independent by engine:

| Engine | Intake requirement |
|---|---|
| OUTCOME | SPF available |
| HANDICAP | exact cutoff-visible RQSPF handicap line |
| GOALS | Total Goals available |
| HTFT | halftime and fulltime labels |

These are intake-review signals, not archive eligibility or training approval.
`Historical Official Odds Artifact Accepted` remains distinct from
`Training Sample Eligible`; a full sample still needs feature bundle,
statistical/football/market/tactical/quality gates, cutoff-visible lineage,
label, and revision evidence.

## 9. Post-match and generated-artifact boundaries

Post-match labels are physically/logically separate from pre-match facts. A
label source timestamp must be at or after kickoff and label fields never enter
the pre-match feature hash. V3 predictions/probabilities/confidence/model
parameters/frozen predictions, V4 generated cards/dashboards, recommendation
cards, betting slips, and prediction summary images are not raw training facts.
Only independently verifiable raw factual artifacts may later be re-ingested.

## 10. Dry-run validator and legacy validator decision

`src/historical_backfill_intake/__init__.py` provides schema validation,
timestamp evidence evaluation, dedupe semantics, conflict detection, F-drive
boundary validation, export package validation, and a no-write dry-run. Its
only package outcomes are `VALID_FOR_INTAKE`, `REVIEW_REQUIRED`, `REJECTED`,
`DUPLICATE_NOOP_CANDIDATE`, and `CONFLICT`.

The focused historical-backfill validator is
`scripts/validate_v4_batch15_verified_historical_backfill.py`. It checks the
three canonical contract hashes, amendment bindings, EWP-001 preservation,
EWP-005 authorization, empty archive, unchanged zero-data readiness, F-drive
staging, forbidden paths, and no-write boundaries.

The existing `validate_v4_batch15_ewp001.py` and
`validate_v4_batch15_ewp002.py` remain legacy validators for their original
contracts. Their stale assumptions were corrected additively: EWP-001 now
recognizes the current EWP-004 runtime-complete registry status, and EWP-002
now recognizes EWP-003/EWP-004 as complete and authorized while preserving
EWP-005 as unauthorized; the EWP-002 script also received its missing
repository import-path bootstrap. Both now pass, with no rollback or boundary
loosening. EWP-003 and EWP-004 validators also pass.

## 11. Validation and readiness decision

| Review | Decision |
|---|---|
| Historical Backfill Intake Contract Readiness | `READY_FOR_IMPLEMENTATION` |
| Candidate batch 40 matches / 64 screenshots | `PROCEED_TO_EXPORT_INTAKE_VERIFICATION` review-level only |
| Current archive records | `0` |
| Current usable training samples | `0` |
| Current Training Readiness | `BLOCKED / TRAINING_DATA_INSUFFICIENT` |
| EWP-005 execution authorization | `false` |

The candidate decision does not authorize import, archive write, dataset
rebuild, temporal split, readiness rerun, training, fitting, calibration,
prediction, Shadow, Production, Public, Supabase, migration, or V3.3.3 work.

Remaining blockers are the export package itself, independent verification of
each original byte/hash and Library metadata snapshot, match/kickoff/market
conflict review, and a later explicit intake runtime authorization. No current
candidate is a training sample.

The only allowed next step is:

`VERIFIED HISTORICAL BACKFILL EXPORT PACKAGE & INTAKE RUNTIME AUTHORIZATION REVIEW`

## 12. Traceability

Focused implementation commit: `chore(v4): govern verified historical backfill intake`

The final commit and HEAD are recorded in the handoff after all focused,
governance, contract, versioning, F-drive, V3 isolation, diff-check, legacy,
and full-repository validations complete. This report itself is a governance
artifact; it is not an import receipt and does not change archive counts.
