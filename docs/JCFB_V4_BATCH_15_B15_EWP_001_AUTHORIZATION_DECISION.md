# JCFB V4 BATCH-15 B15-EWP-001 Authorization Decision

Decision identity: `V4-015-EWP001-AUTH-001`

Decision date: `2026-09-05` (`Asia/Shanghai`)

Decision: **APPROVED FOR EWP-001 HISTORICAL SOURCE ARCHIVE AND PROSPECTIVE CAPTURE ONLY**

`B15-EWP-001` is the only authorized work package in this execution. Its
authorization changes only its own registered envelope to
`execution_authorized=true`, revision `r002`, with status `COMPLETE` after the
acceptance evidence passes. `B15-EWP-002` through `B15-EWP-005` remain
`execution_authorized=false` and are not executed.

## Frozen scope

- Approved root: `F:\Projects\jcfb-v4\approved_data\historical_source_archive\`
- Scope: pre-match source artifacts, provenance, append-only revisions,
  official screenshot originals, provider-separated external snapshots,
  post-match label append, and verified-backfill evaluation interface.
- Activation: `2026-09-05T00:00:00+08:00`; observations before this instant
  are never relabeled as prospective.
- Output contract: `historical-source-archive@1.0.0` and
  `b15-ewp001-archive-record@1.0.0`.

## Explicit exclusions

This decision does not authorize historical data import, as-of dataset
construction, sample assembly, temporal splitting, training, fitting, model
artifacts, Score, Calibration, Shadow, Production, Public, Supabase,
migrations, V4-076, V4-052 through V4-055, or any V3.3.3 operation.

## Authorization evidence

The frozen execution manifest is
`config/prediction_training/v4_batch15_ewp001_execution_manifest.json`.
The acceptance evidence is
`docs/JCFB_V4_BATCH_15_B15_EWP_001_ACCEPTANCE_EVIDENCE.json`.
The archive runtime is implemented at
`src/historical_source_archive/__init__.py` and writes only below the
approved F-drive root when persistence is enabled.
