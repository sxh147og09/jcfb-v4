# JCFB V4 BATCH-15 Independent Engine Contracts 1.0

Status: **GOVERNANCE ONLY / ENGINES NOT IMPLEMENTED**
Contract version: `engine-feature-profile@1.0.0`
Output envelope: `engine-output@1.0.0`

All four engines use the active Engine Output Contract and must include
`frozen_input_id/hash`, model/engine/config identity, implementation/input/
output hashes, cutoff/kickoff, role, status, warnings/errors, and a typed
engine payload. `SUCCEEDED` requires valid probabilities; `BLOCKED`, `FAILED`,
or `INVALID` cannot carry a fabricated successful probability payload.

## Outcome Engine (`V4-052`)

Output exactly H/D/A (`outcome_probability`) with finite values in `[0,1]`,
full normalization, and its own feature/model/input/output lineage. It does
not produce RQSPF, Goals, HTFT, Score, or any other market.

## Handicap Engine (`V4-053`)

Output official RQSPF identity, exact official handicap value and availability
state, sign convention `home_minus_away`, H/D/A handicap probabilities, and
the approved goal-difference distribution when required. External Asian
Handicap is not an official RQSPF substitute. The engine performs its own run;
it does not copy Outcome output.

## Goals Engine (`V4-054`)

Output explicit buckets `0`, `1`, `2`, `3`, `4`, `5`, `6`, and `7+`, with
tail semantics, support, normalization, and official Total Goals availability
state. It does not derive from Outcome and does not implement Score Engine.

## HTFT Engine (`V4-055`)

Output all nine explicit states `H/H`, `H/D`, `H/A`, `D/H`, `D/D`, `D/A`,
`A/H`, `A/D`, and `A/A`, normalized as one independent distribution. A
half-time heuristic combined with final SPF is not an accepted implementation.

The four profiles, model identities, feature subsets, parameter artifacts,
and output hashes are independent even when they share the same Frozen Input.
