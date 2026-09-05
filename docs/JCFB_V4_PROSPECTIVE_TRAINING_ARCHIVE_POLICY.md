# JCFB V4 Prospective Training Archive Policy

Policy identity: `prospective-training-archive-policy@1.0.0`

The prospective archive is approved for future accumulation under
`PROSPECTIVE_CAPTURE`. It is not a current training dataset and no fitting is
authorized by this policy.

## Pre-match append set

For each formal V4 pre-match execution, append the canonical match facts,
official odds snapshots, external market snapshots, Statistical feature
artifact, Football artifact, Market artifact, Tactical artifact, BATCH-14
Gate Record, Feature Bundle, cutoff, source timestamps, revision identities,
and hashes. Each record must state its source availability and cutoff
eligibility.

## Post-match label append set

After the match, append final result and halftime result labels through a
separate post-match path. Labels include source, verification time, revision,
and hash. The archive must make it impossible for label ingestion to mutate
the pre-match frozen input or feature payload.

## Isolation and replay

Pre-match records and post-match labels are physically or logically separate,
append-only, and independently hashed. A future Dataset Builder may join them
only through a governed target identity after the cutoff and leakage checks
pass. A failed source, cutoff, identity, or hash check yields
`NOT_ELIGIBLE_FOR_AS_OF_TRAINING` or `BLOCKED`.

The archive may accumulate samples prospectively while historical backfill is
absent. It must not publish a usable sample count before a real dataset
artifact exists.
