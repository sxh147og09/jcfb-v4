# JCFB V4 Historical Source Acquisition Mode Policy

Policy identity: `historical-acquisition-mode-policy@1.0.0`

## PROSPECTIVE_CAPTURE

Prospective capture begins with a real future V4 pre-match execution. The
archive records the source reference, source timestamp, capture/observation
timestamp, cutoff, kickoff, canonical identity, revision identity, and raw
payload/file hash. New records are appended; a later correction supersedes an
older revision without deletion. Prospective capture may accumulate evidence
but cannot be called a historical training dataset until the dataset and
readiness gates pass.

## VERIFIED_HISTORICAL_BACKFILL

Backfill is permitted only when an auditor can tie the record to an original
source and historical availability. The evidence must include a stable source
reference, source or observation timestamp, original payload/image/file hash
when available, canonical match identity, revision/supersession chain, and
ingestion provenance. A screenshot without a defensible historical timestamp
is not enough to establish cutoff availability.

The following are explicit rejection cases:

- using a current final revision as an earlier state;
- treating closing odds as an arbitrary earlier cutoff snapshot;
- inferring lineup publication from a later lineup or match result;
- deriving a feature from the outcome or post-match review;
- synthesizing market movement or source timestamps;
- importing any V3.3.3 generated artifact as a raw fact.

The absence of proof produces `NOT_ELIGIBLE_FOR_AS_OF_TRAINING`, not a guess.
