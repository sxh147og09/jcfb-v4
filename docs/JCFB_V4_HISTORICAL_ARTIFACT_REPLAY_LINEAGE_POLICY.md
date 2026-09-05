# JCFB V4 Historical Artifact Reconstruction / Replay Lineage Policy

Policy identity: `historical-artifact-replay-lineage-policy@1.0.0`

Historical feature reconstruction has exactly two legal paths, evaluated in
order.

1. `STORED_ACCEPTED_ARTIFACT`: when the archive contains the accepted artifact,
   bind its exact archive record reference, artifact hash, and revision. Keep
   the stored generator/config/mapping identity when present. Do not regenerate
   it with current code.
2. `DETERMINISTIC_HISTORICAL_REPLAY`: only when raw cutoff-visible inputs are
   complete; exact generator version and implementation hash, exact config
   version and hash, exact mapping version and hash, valid source timestamps,
   and absence of a post-cutoff revision are all proven.

Missing proof, an invalid timestamp, a post-cutoff correction, or use of a
"latest" generator/config/mapping produces `INELIGIBLE_FOR_TRAINING`. There is
no fallback to a latest implementation. The pure selector in
`src/historical_source_archive/replay_policy.py` does not write records or
construct a dataset.
