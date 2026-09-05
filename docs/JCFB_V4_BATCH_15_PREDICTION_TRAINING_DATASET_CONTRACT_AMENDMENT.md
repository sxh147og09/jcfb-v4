# JCFB V4 BATCH-15 Prediction Training Dataset Contract Amendment

Contract family: `prediction-training-dataset`
Active additive version: `prediction-training-dataset@1.1.0`
Preserved predecessor: `prediction-training-dataset@1.0.0`

This is a backward-compatible, versioned amendment. The `@1.0.0` contract is
not overwritten. The active sample identity is frozen as:

`match_id + cutoff_profile + engine_role`

The amended envelope uses explicit, non-aliased fields for the feature bundle,
four feature domains, Gate Record, source/evidence/provenance references,
engine eligibility, post-match label references, builder/dataset identity,
input/sample/provenance hashes, revision, and supersession. The old composite
aliases (`sample_id`, `target_role`, `*_refs_and_hashes`, and
`label_ref_and_hash`) are rejected as ambiguous.

## Handicap binding

The Handicap role requires the exact official RQSPF snapshot reference and
hash, exact official handicap value, `home_minus_away` sign convention, source
availability time, and prediction cutoff. External Asian Handicap, closing,
latest, and default values cannot satisfy this binding. A missing official
RQSPF binding marks only Handicap `INELIGIBLE`; Outcome, Goals, and HTFT remain
independently eligible for evaluation.

## Runtime boundary

The contract validator and hash-boundary helper are schema/governance helpers
only. This amendment does not implement a Dataset Builder, construct a formal
dataset, perform a temporal split, or authorize fitting.
