# JCFB V4 Historical Backfill Eligibility Policy

Policy identity: `historical-backfill-eligibility-policy@1.0.0`

A record can be `ELIGIBLE_FOR_AS_OF_TRAINING` only if all required identity,
provenance, revision, source-time, cutoff, kickoff, and hash predicates pass.
The eligibility decision is per record and append-only.

Required predicates:

1. `match_identity` resolves deterministically to the target match.
2. The source is independently identified by `source_reference`.
3. `source_timestamp` or a defensible historical `observed_at` proves
   availability before the declared cutoff.
4. `prediction_cutoff_at < kickoff_at` and the feature record is not future
   information.
5. The revision visible at cutoff is identified; the present-day final state
   is not substituted.
6. Raw payload/image/file and canonical artifact hashes are retained when
   available.
7. Labels are post-match targets and are not present in the feature payload.
8. No V3.3.3 prediction, model artifact, confidence, calibration, or
   review-derived parameter is referenced.

Eligibility states are `ELIGIBLE_FOR_AS_OF_TRAINING`,
`NOT_ELIGIBLE_FOR_AS_OF_TRAINING`, `UNKNOWN`, and `BLOCKED`. An unverifiable
source time must be rejected as `NOT_ELIGIBLE_FOR_AS_OF_TRAINING`. Missing
population counts remain `NOT_AVAILABLE` or `UNKNOWN`; they are not reported
as zero.

No result, handicap, goal, or HTFT sample may be counted until a real dataset
artifact and its lineage manifest exist.
