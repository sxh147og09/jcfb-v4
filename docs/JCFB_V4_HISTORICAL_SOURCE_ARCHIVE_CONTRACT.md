# JCFB V4 Historical Source Archive Contract

Contract identity: `historical-source-archive@1.0.0`

Status: **ACTIVE GOVERNANCE CONTRACT / NO POPULATION FOUND**

The archive is the only approved boundary for historical raw facts used in a
future V4 as-of dataset. It stores source observations and provenance, not
predictions or model outputs. The archive must preserve append-only revisions;
corrections create a new revision and never overwrite the original record.

## Required record provenance

Each record must retain `source`, `source_reference`, `source_timestamp`,
`observed_at` when available, `captured_at` when available, `ingested_at`,
original payload/image/file hash, canonical match identity, market or context
type, revision identity, supersession relation, provenance state, and
`availability_at`. A source timestamp must describe when the source made the
fact available, not merely when V4 downloaded it.

The as-of predicate is:

`feature_availability_at <= prediction_cutoff_at < kickoff_at`

An ingestion time, a current final revision, or a generated time cannot stand
in for source availability.

## Acquisition modes

The contract supports exactly two modes:

1. `PROSPECTIVE_CAPTURE`: capture real pre-match observations from the point
   of approval onward, retaining source and capture chronology.
2. `VERIFIED_HISTORICAL_BACKFILL`: import an older record only when its
   original source, historical time, payload/file hash, match identity, and
   revision/provenance chain can be independently verified.

If historical availability cannot be proven, the record is
`NOT_ELIGIBLE_FOR_AS_OF_TRAINING`. It is never silently downgraded to a
usable sample.

## Domain separation

Allowed raw factual domains include official odds snapshots, external market
snapshots, official result facts, halftime result facts, and verified lineup
or source records. Feature Bundles, Gate Records, and derived feature
artifacts require their own lineage and are not manufactured from an
unverified raw fact. Pre-match archive records and post-match labels must be
physically or logically separate.

The machine-readable contract is
`config/prediction_training/historical_source_archive_contract.json`.
