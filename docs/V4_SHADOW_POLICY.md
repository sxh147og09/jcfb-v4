# JCFB V4 Shadow Policy 1.0

Status: V4-007 ACCEPTANCE PENDING

## 1. Purpose and authority

This policy governs a real pre-match SHADOW run. Shadow is a controlled comparison role, not an alternate Production channel and not a renamed Experiment. It is subordinate to docs/V4_CONSTITUTION.md and the role, identity, time, integrity, and lifecycle policies already accepted for V4.

This policy creates no model execution and does not claim that a Shadow run has occurred.

## 2. Shadow identity

Every Shadow run has an explicit identity separate from Production and Experiment:

- role=SHADOW
- model_name, model_version, major, minor, patch, and revision
- engine_version and selector identity when applicable
- shadow_revision in the sh-YYYYMMDD-NNNNNN form
- implementation_hash
- config_hash
- input_hash
- output_hash
- run_at and run_completed_at
- runtime_environment
- dataset_version, schema_version, migration_version, and config_version
- frozen_revision and frozen_input_hash for a comparable run
- kickoff_at and prediction_cutoff_at
- shadow status and audit identity

The Shadow revision is never copied into a Production revision. If the same implementation later enters Production, it receives a new Production-scoped revision and must pass the full Promotion Gate.

## 3. Pre-kickoff admission

A Shadow run is Forward-eligible only when all of the following are proven:

1. Canonical match identity and kickoff_at are valid.
2. prediction_cutoff_at is explicit and before kickoff.
3. Every input satisfies input_timestamp <= prediction_cutoff_at.
4. Frozen Input was formed before the run and frozen_input_hash is retained.
5. run_completed_at < kickoff_at.
6. No result, match event, post-match lineup, post-match statistic, or later odds entered the run.
7. The Shadow identity and all required hashes are present.
8. The output is stored in the Shadow namespace and is immutable after freeze.

Starting a run before kickoff is not sufficient if the run completes after kickoff or if the completion time cannot be proven.

## 4. Forward A/B frozen-input rule

When SHADOW is paired with PRODUCTION for the same match, the pair must reference:

- the same canonical match identity
- the same prediction_cutoff_at
- the same frozen_revision
- the same frozen_input_hash

The Shadow input_hash can differ from the Production input_hash because it includes the Shadow role, revision, component versions, and engine envelope. This difference is expected and does not weaken the same-frozen-input rule.

If the frozen_input_hash differs, the pair is:

- PAIR_INVALID = TRUE
- TIER_A_ELIGIBLE = FALSE
- PROMOTION_EVIDENCE = FALSE

An Experiment with a different input may be stored for research, but it is not a Shadow pair and cannot be used to repair a mismatched pair.

## 5. Shadow output isolation

Shadow output has its own prediction identity, output identity, and optional Shadow Frozen Prediction reference. Shadow may append its own Engine Outputs, Prediction, review evidence, calibration evidence, and audit events in its namespace.

Shadow may not:

- create or replace canonical Production Prediction
- update Production Frozen Prediction
- modify Production confidence, risk, review, or Tier A records
- change the active Production pointer
- write the Production branch of Public Read Projection
- delete or edit its own historical output after freeze
- auto-deploy or auto-promote

Production failure is not inferred from a Shadow disagreement. Shadow disagreement is preserved as evidence and may enter Promotion Review.

## 6. Forward eligibility and Promotion Review

Only a genuine pre-match Shadow run can contribute Shadow evidence to a Forward Frozen sample. The minimum evidence package contains:

- V4 Tier A sample identity beginning at V4 Tier A Sample #001
- Production and Shadow role identities
- the same frozen_input_hash
- pre-kickoff run_completed_at for both sides
- implementation_hash, config_hash, input_hash, and output_hash for both sides
- complete five-market and required score evidence
- no-future-leakage result
- official result received through the post-match result path
- completeness gate result
- audit events and any declared exclusions

Historical backtesting can supplement evaluation but cannot substitute for a pre-match Shadow run. Experiment outputs, even when they use the same frozen_input_hash, never qualify as Forward Tier A samples.

Promotion Review reads immutable Shadow and Production evidence. It does not merge their output identities or overwrite either Frozen Prediction.

## 7. Post-match invalidation

If Shadow output is first produced after kickoff, or if a rerun uses post-match knowledge, the record remains auditable but must be marked:

invalid_for_forward_promotion = TRUE

It is not a Forward sample, not Tier A evidence, and not Promotion evidence. The output may be used only for a separately labeled diagnostic or post-match research review.

Backfilling a missing Shadow output after the match is prohibited.

## 8. Shadow incidents

An isolated Shadow failure creates a Shadow incident, preserves the failure evidence, and does not block Production. Examples include missing Shadow hashes, a Shadow process error, or a Shadow output that fails its own completeness gate.

Production may be blocked only when the issue is a shared global data or Frozen Input incident that also invalidates the Production path. A shared incident is not hidden as a Shadow-only failure.

The incident path is append-only and follows docs/V4_INCIDENT_POLICY.md. Recovery creates new Shadow identities and does not overwrite the failed run.

## 9. References

- docs/V4_RUNTIME_ROLE_BOUNDARY.md
- docs/V4_PRODUCTION_POLICY.md
- docs/V4_PROMOTION_PATH.md
- docs/V4_RUNTIME_ACCESS_MATRIX.md
- docs/V4_CONSTITUTION.md
- docs/V4_MODEL_GOVERNANCE.md
- docs/V4_TIME_AND_INFORMATION_POLICY.md
- docs/V4_VERSION_IDENTITY_CONTRACT.md
