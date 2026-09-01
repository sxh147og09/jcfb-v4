# JCFB V4 Promotion Path 1.0

Status: V4-007 ACCEPTANCE PENDING

## 1. Purpose and authority

This contract defines the only path by which a V4 candidate may become Production. It applies to models, engines, selectors, calibration components, simulation components, and any release that can affect formal output.

The Constitution is highest. This contract must be read with docs/V4_RUNTIME_ROLE_BOUNDARY.md, docs/V4_PRODUCTION_POLICY.md, docs/V4_SHADOW_POLICY.md, docs/V4_EXPERIMENT_POLICY.md, docs/V4_RUNTIME_ACCESS_MATRIX.md, docs/V4_MODEL_GOVERNANCE.md, and the V4-006 versioning contracts.

No transition in this document is an auto-promotion. A future implementation must fail closed when an evidence item or approval is missing.

## 2. Strict lifecycle

The allowed lifecycle is:

 DRAFT -> EXPERIMENT -> SHADOW -> PROMOTION_REVIEW -> PRODUCTION -> RETIRED

Allowed transitions are:

| From | To | Minimum condition |
|---|---|---|
| DRAFT | EXPERIMENT | Explicit experiment_id, build_id, experiment_revision, and research scope |
| EXPERIMENT | SHADOW | New Shadow revision, new identity, declared cutoff, and Shadow admission |
| SHADOW | PROMOTION_REVIEW | Complete Forward evidence package and a registered review request |
| PROMOTION_REVIEW | PRODUCTION | All gates pass, manual approval, and explicit Production release identity |
| PRODUCTION | RETIRED | Explicit supersession, retirement reason, effective time, and preserved history |

The following transitions are prohibited:

- DRAFT -> PRODUCTION
- EXPERIMENT -> PRODUCTION
- SHADOW -> PRODUCTION without PROMOTION_REVIEW
- any direct role rename that preserves an old revision or output identity
- any automatic transition based only on a metric, hit streak, scheduler, or operator preference

BLOCKED, RUN_INVALID, NOT_VERIFIED, and NOT_IMPLEMENTED are gate or evidence states. They do not grant a lifecycle transition.

## 3. Minimum Promotion Gate

Every Promotion Review must explicitly evaluate:

1. Forward frozen samples.
2. No future leakage.
3. Completeness gate.
4. Calibration evaluation.
5. Regression evaluation.
6. Performance evaluation.
7. Integrity audit.
8. Manual approval.
9. Explicit Production release identity and compatibility declaration.

AUTO_PROMOTION = TRUE is prohibited.

### 3.1 Forward frozen samples

Forward evidence begins at V4 Tier A Sample #001. A qualifying sample must preserve the original Production and Shadow identities, the same frozen_input_hash, pre-kickoff completion times, all required hashes, the official result, the completeness result, and no-future-leakage evidence.

Only a genuine pre-match Shadow pair can contribute Shadow evidence. Historical backtesting is supporting evidence and cannot replace the Forward sample requirement. Experiment samples are permanently excluded from Forward Tier A and Promotion evidence, even if they use the same frozen_input_hash.

### 3.2 No future leakage

The review must check source publication or observation time, prediction cutoff, kickoff, run completion, later odds, result data, post-match statistics, lineup confirmation, and any post-match explanation. A future-information finding sets:

- FUTURE_INFORMATION_LEAKAGE = TRUE
- RUN_INVALID = TRUE
- TIER_A_ELIGIBLE = FALSE
- PROMOTION_EVIDENCE = FALSE

Deleting or editing the evidence cannot restore eligibility.

### 3.3 Completeness gate

The candidate package must identify the declared sample scope, match identities, required five-market outputs, score evidence when applicable, all role-scoped revisions, implementation/config/input/output hashes, frozen identities, timestamps, exclusions, failures, and missing values. Missing critical evidence is BLOCKED, not silently completed.

### 3.4 Calibration evaluation

Calibration must be evaluated by the declared market, league or scope, confidence band, model version, and sample period. Probability, confidence, and recommendation strength remain separate. Hit rate alone is not sufficient.

### 3.5 Regression evaluation

Regression evidence must cover the declared baseline and candidate across at least league degradation, score distribution, BTTS, calibration, upset recognition, abstention behavior, market outputs, and material runtime degradation. A candidate cannot hide a material degradation behind an improved overall average.

### 3.6 Performance evaluation

Performance evidence must cover correctness-preserving runtime, reproducibility, resource behavior, cache identity, and any declared latency or throughput target. Performance optimization cannot skip validation, timestamp, provenance, hash, or freeze gates.

### 3.7 Integrity audit

The audit must verify role separation, exact identity, immutable Frozen Input and Frozen Prediction, append-only evidence, same-frozen-input A/B, pre-kickoff Shadow, no Experiment-as-Tier-A, Public Web isolation, Production uniqueness, Secret Scan, and V3.3.3 protection.

## 4. Promotion Review record

The Promotion Review appends a record containing:

- promotion_review_id
- candidate model, engine, selector, configuration, and revision identities
- source_role=SHADOW
- sample scope and V4 Tier A references
- forward frozen evidence references
- calibration, regression, performance, leakage, completeness, and integrity results
- known limitations and failure handling
- compatibility_level
- decision: APPROVED, REJECTED, BLOCKED, or NEEDS_MORE_EVIDENCE
- manual approver, approval time, reason, and audit identity
- production_release_id when approved
- supersedes_revision when a Production revision exists

The review reads immutable evidence. It does not modify a prediction, Frozen Prediction, Shadow output, Experiment output, result, or previous review.

## 5. Activation, uniqueness, and retirement

An approved candidate receives an explicit Production release identity and a new Production-scoped revision. It becomes active only after the release and compatibility gates pass.

For each model_family and canonical_output_channel, exactly one Canonical Active Production Revision may exist at any time. Activation appends the new pointer event and explicitly supersedes the prior active revision. The prior revision becomes RETIRED with reason, effective time, successor, and preserved history. There is no period in which two Production revisions compete for canonical output.

Production activation never copies a Shadow or Experiment output identity into Production. It creates a new role identity, new release identity, and new formal evidence period.

## 6. Demotion and rollback

If the active Production revision has an integrity, security, leakage, or material correctness incident, the system may fail closed and perform a governed rollback:

1. Stop the affected formal path as required by incident severity.
2. Preserve the failed Production revision and every historical artifact.
3. Append rollback_id, failed_revision, rollback_target_revision, actor, reason, time, and evidence.
4. Register a new rollback Production release identity with a new revision that explicitly references the previously approved target behavior.
5. Re-run applicable identity, compatibility, integrity, and public projection checks.
6. Set one active pointer to the rollback release and append its effective time.

The prior approved behavior is restored through a new auditable identity. The old failed revision is not deleted, its Frozen Predictions are not changed, and a retired revision is not silently reactivated. Rollback cannot erase the failed version from the promotion or incident history.

Operationally, the active serving pointer may be cut back to the previous approved Production behavior identified by rollback_target_revision. The cut-back is recorded as the new rollback Production release identity required by the V4-006 no-silent-reactivation rule; the original target revision remains retained and historically immutable.

## 7. Incident behavior

| Incident | Default effect |
|---|---|
| Shadow failure with isolated scope | Record Shadow incident; do not block Production |
| Experiment failure with isolated scope | Record Experiment incident; do not affect Production or Shadow |
| Shared global input or Frozen Input incident | Block affected roles and assess Production impact |
| Production integrity incident | Fail closed, preserve evidence, and consider governed rollback |
| Public projection shows Shadow or Experiment | Block publication and open a publication/model incident |

Recovery always receives new identities and hashes. A clean rerun does not make the original incident disappear.

## 8. Postmatch separation

Postmatch Review may compare Production, Shadow, and Experiment outputs after the official result is available. The review must cite the original pre-match output identities and cannot write back into Prediction, Frozen Input, Frozen Prediction, confidence, or role history.

Promotion evaluation uses the original immutable pre-match outputs. Match Explanation may use events, xG, red cards, technical statistics, or interviews as separate evidence; those facts cannot become pre-match input retroactively.

## 9. References

- docs/V4_RUNTIME_ROLE_BOUNDARY.md
- docs/V4_PRODUCTION_POLICY.md
- docs/V4_SHADOW_POLICY.md
- docs/V4_EXPERIMENT_POLICY.md
- docs/V4_RUNTIME_ACCESS_MATRIX.md
- docs/V4_CONSTITUTION.md
- docs/V4_MODEL_GOVERNANCE.md
- docs/V4_INCIDENT_POLICY.md
- docs/V4_CORRECTION_POLICY.md
