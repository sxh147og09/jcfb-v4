# JCFB V4 BATCH-15 B15-EWP-001 Implementation Report

Implementation status: **COMPLETE**

The EWP-001 runtime provides a file-backed, append-only historical source
archive with a memory-only test mode. The production default validates and
creates only the approved F-drive root:

`F:\Projects\jcfb-v4\approved_data\historical_source_archive\`

## Runtime behavior

- A capture requires `work_package_id=B15-EWP-001`, an explicit authorized
  execution identity, and a start time at or after activation.
- Pre-match records retain canonical match identity, artifact type, source and
  reference, source/observed/captured/ingested/availability times, cutoff,
  kickoff, payload/file hash, provenance hash, feature/context references,
  eligibility, and revision lineage.
- `CAPTURED`, `PARTIAL`, and `BLOCKED` session states are persisted as
  deterministic session manifests; no single success boolean is used.
- Duplicate logical artifacts are `DUPLICATE_NOOP`. Corrections append a new
  record, hash, and revision with explicit `supersedes`; the predecessor is
  retained.
- Official screenshots require the original bytes or a readable F-drive
  source file. The original is stored below `provenance/` and is the
  provenance root; OCR/manual structured extraction is retained as a child
  payload.
- External snapshots retain one provider, exact market line, exact prices,
  source timestamp, and `source_is_official=false`. Consensus-only payloads
  are rejected.
- Post-match labels are written under `post_match/` and never enter a
  pre-match payload. The runtime reports `usable_training_sample_count` as
  `NOT_COMPUTED` because no Dataset Builder exists in this work package.
- Historical backfill is evaluation-only. Unverifiable candidates return
  `NOT_ELIGIBLE_FOR_AS_OF_TRAINING`; no candidate is imported.

## Layout

```text
approved_data/historical_source_archive/
  pre_match/<match_id>/<cutoff_profile>/<artifact_type>/
  post_match/<match_id>/<cutoff_profile>/<artifact_type>/
  manifests/<archive_record_id>.json
  manifests/sessions/<session_id>.json
  provenance/<archive_record_id>/original<extension>
  revisions/
```

Tests and fixtures are not archive inputs. `.runtime`, `src/data`, database,
Supabase, and V3.3.3 boundaries are not used.
