# JCFB V4 Runtime Role Boundary 1.0

Status: V4-007 COMPLETE

## 1. Purpose and authority

This contract defines the runtime boundary between PRODUCTION, SHADOW, and EXPERIMENT for JCFB V4. It is a governance and audit contract. It does not implement a model runner, registry, database schema, deployment service, or actual Shadow run.

The authority order is:

1. docs/V4_CONSTITUTION.md
2. this contract and the six V4-007 companion contracts
3. docs/V4_ARCHITECTURE_BLUEPRINT.md, docs/V4_MODEL_GOVERNANCE.md, and the V4-006 versioning contracts
4. implementation details that remain compatible with the rules above

If a later implementation cannot prove a required identity, time, hash, permission, or lifecycle condition, it must fail closed with BLOCKED, RUN_INVALID, NOT_VERIFIED, or NOT_IMPLEMENTED. It must not infer a safe state from a path, filename, nickname, or missing value.

## 2. The three roles

### PRODUCTION

PRODUCTION is the only formal prediction source. It is the only role allowed to create a canonical public prediction and the only role allowed to write the Production branch of the canonical public read projection. A Production run must use an approved Production release, the single active revision for its model family, an eligible Frozen Input, and all declared data-quality, consistency, risk, freeze, and audit gates.

PRODUCTION cannot run an EXPERIMENT or SHADOW revision under a Production label. A Production label is a role identity, not a display name.

### SHADOW

SHADOW is a real pre-match comparison run. It must complete before kickoff, carry its own shadow revision identity, and remain isolated from formal output. It may run beside PRODUCTION for Forward A/B and Promotion Review, but it cannot change Production Prediction, Frozen Prediction, confidence, review conclusions, Tier A qualification, the active Production pointer, or the public projection.

SHADOW is evidence only. It has no publication authority and no auto-deployment authority.

### EXPERIMENT

EXPERIMENT is the research role for development, offline backtesting, historical recomputation, parameter exploration, feature studies, simulation studies, and hypothesis testing. Every experiment has an explicit experiment_id, build_id, and experiment_revision. Experiment input may differ from formal A/B input, but the difference must be declared and must never be confused with a Forward Shadow pair.

EXPERIMENT cannot enter a formal public projection, cannot count as a Forward Tier A sample, cannot be relabeled as SHADOW after the fact, and cannot transition directly to PRODUCTION.

The role field is mandatory for every formal run. No role may be inferred from a directory, branch, process name, or output filename.

The deployment target identity is a separate environment contract. For the
bound Production target, `project_ref` is the unique identity key and
`role=PRODUCTION` must agree with the named environment. `BOUND_APPROVED`
means that the target identity was explicitly approved; it does not grant
Production schema-apply or database-write permission. The three-environment
binding and its fail-closed apply gate are recorded in
docs/V4_PRODUCTION_TARGET_BINDING.md.

## 3. Runtime identity envelope

Every formal run preserves, at minimum:

| Field | PRODUCTION | SHADOW | EXPERIMENT |
|---|---|---|---|
| role | PRODUCTION | SHADOW | EXPERIMENT |
| model_version | Required | Required | Required |
| engine_version | Required | Required | Required |
| revision | Required immutable registry revision | Required immutable registry revision | Required immutable registry revision |
| implementation_hash | Required | Required | Required |
| config_hash | Required | Required | Required |
| input_hash | Required | Required | Required |
| output_hash | Required for every output | Required for every output | Required for every output |
| run_at | Required timezone-aware execution timestamp | Required timezone-aware execution timestamp | Required timezone-aware execution timestamp |
| run_completed_at | Required for pre-match eligibility | Required for pre-match eligibility | Required when the run claims pre-match evidence |
| frozen_revision | Required | Required for a comparable pre-match run | Required for a frozen experiment; otherwise NOT_APPLICABLE with a reason |
| frozen_input_hash | Required | Must equal the paired Production hash for A/B | Required for a frozen experiment; an alternate value is not a formal A/B pair |
| shadow_revision | NOT_APPLICABLE | Required, in the sh-YYYYMMDD-NNNNNN form | NOT_APPLICABLE |
| experiment_revision | NOT_APPLICABLE | NOT_APPLICABLE | Required, in the ex-YYYYMMDD-NNNNNN form |
| experiment_id | NOT_APPLICABLE | NOT_APPLICABLE | Required |
| build_id | NOT_APPLICABLE | NOT_APPLICABLE | Required |
| prediction_cutoff_at | Required | Required | Required when the run is pre-match |
| kickoff_at | Required | Required | Required when the run is pre-match |
| runtime_environment | Required non-secret descriptor | Required non-secret descriptor | Required non-secret descriptor |
| status | PRODUCTION or a governed gate state | SHADOW or a governed gate state | EXPERIMENT or a governed gate state |

The complete V4 identity tuple, hash canonicalization, and NOT_APPLICABLE rules remain defined by docs/V4_VERSION_IDENTITY_CONTRACT.md and docs/V4_VERSIONING_STANDARD.md. Confidence, risk, recommendation strength, and review status are output or review artifacts; they are not substitutes for identity fields.

## 4. Input and time boundary

Every formal pre-match input must satisfy:

input_timestamp <= prediction_cutoff_at < kickoff_at

The accepted input set is frozen before the formal prediction. A valid Production/Shadow A/B comparison requires the same canonical match identity, the same prediction cutoff, and the same frozen_input_hash. The two runs may have different input_hash values because input_hash includes role, component, and engine identity; the shared frozen_input_hash proves that the substantive frozen pre-match input boundary is the same.

An EXPERIMENT may use a different frozen input or an unfrozen research input. It must declare comparison_mode=EXPERIMENT_ONLY, its input identity, and the reason it is not a Forward A/B pair. A different input never becomes comparable merely because the match identity is the same.

If a Shadow run is generated or completed at or after kickoff, or if its pre-match completion cannot be proven, its output must carry:

- invalid_for_forward_promotion = TRUE
- TIER_A_ELIGIBLE = FALSE
- PROMOTION_EVIDENCE = FALSE

The invalid record and evidence remain append-only. Removing the offending evidence does not restore eligibility.

## 5. Output and history isolation

Each role owns a separate prediction and output identity. The identity includes role, model version, role-scoped revision, match identity, input_hash, and output_hash. A role revision or output identity cannot be copied into another role.

The following are immutable or append-only after formation:

- Feature bundles used by a formal run
- Engine Outputs
- Prediction
- Frozen Input
- Frozen Prediction
- confidence, risk, and recommendation metadata attached to the prediction
- Postmatch Review and Tier A evidence
- audit events

SHADOW and EXPERIMENT are denied any write path that can create, update, delete, or replace a Production Prediction, Frozen Prediction, confidence, review, Tier A record, active Production pointer, or canonical public projection.

PRODUCTION cannot delete, rewrite, or conceal SHADOW or EXPERIMENT history. A post-match review may compare role outputs, but it appends a review artifact and never writes back into any pre-match output.

The exact role-by-artifact permissions are defined in docs/V4_RUNTIME_ACCESS_MATRIX.md.

## 6. Lifecycle and transition boundary

The only promotion lifecycle is:

 DRAFT -> EXPERIMENT -> SHADOW -> PROMOTION_REVIEW -> PRODUCTION -> RETIRED

The following are always blocked:

- DRAFT -> PRODUCTION
- EXPERIMENT -> PRODUCTION
- SHADOW -> PRODUCTION without PROMOTION_REVIEW
- EXPERIMENT -> PUBLIC
- SHADOW -> PUBLIC
- any role rename that preserves an old output identity

Every transition appends an audit event with actor, reason, time, predecessor, successor, evidence, and the exact revision identities. Moving from EXPERIMENT to SHADOW creates a new Shadow revision and a new governed run; it does not rename or mutate the experiment. Promotion and rollback rules are fully specified in docs/V4_PROMOTION_PATH.md.

## 7. Fail-closed enforcement outcomes

| Violation | Required outcome |
|---|---|
| Missing role or role inferred from a path | NOT_AUDITABLE and BLOCKED |
| Production/Shadow A/B frozen_input_hash mismatch | PAIR_INVALID and PROMOTION_EVIDENCE=FALSE |
| Future information in a pre-match input | FUTURE_INFORMATION_LEAKAGE and RUN_INVALID |
| Shadow completed after kickoff | invalid_for_forward_promotion=TRUE and TIER_A_ELIGIBLE=FALSE |
| Experiment output enters public projection | ROLE_VIOLATION; block publication and open an incident |
| Shadow or Experiment attempts a Production write | ROLE_VIOLATION; reject the write and preserve the audit event |
| More than one active Production revision | PRODUCTION_UNIQUENESS_FAILURE; fail closed and open an incident |
| Missing implementation, config, input, or output hash | BLOCKED and not eligible for promotion |

## 8. V3.3.3 protection

This boundary applies only to JCFB V4. It does not authorize any change to JCFB V3.3.3 code, model parameters, predictions, Frozen Prediction, reviews, Tier A samples, database history, or audit history. A cross-version benchmark may read separately frozen artifacts through an approved read boundary; it must not merge or mutate them.

## 9. Companion contracts

- docs/V4_PRODUCTION_POLICY.md
- docs/V4_SHADOW_POLICY.md
- docs/V4_EXPERIMENT_POLICY.md
- docs/V4_PROMOTION_PATH.md
- docs/V4_RUNTIME_ACCESS_MATRIX.md
- docs/V4_CONSTITUTION.md
- docs/V4_MODEL_GOVERNANCE.md
- docs/V4_VERSIONING_STANDARD.md
- docs/V4_VERSION_IDENTITY_CONTRACT.md
- docs/V4_ARCHITECTURE_BLUEPRINT.md
- docs/V4_PRODUCTION_TARGET_BINDING.md
