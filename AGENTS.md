# JCFB V4 Agent Governance

These rules apply to all work inside the JCFB V4 repository.

1. Never modify JCFB V3.3.3 from V4 work.
2. V4 is an independent model, not a rename of V3.3.3.
3. Never use post-match information in a pre-match model run.
4. Never use future odds.
5. Never modify historical Frozen Prediction.
6. Never fabricate missing China Sports Lottery odds.
7. Missing market must be explicitly marked unavailable.
8. Every model run must eventually support:
   - `model_version`
   - `implementation_hash`
   - `config_hash`
   - `input_hash`
   - `output_hash`
9. Production and Shadow outputs must remain distinguishable.
10. Model experiments must never silently affect Production.
11. Objective facts may be shared across model versions. Predictions and model outputs must remain isolated.
12. No automatic model promotion without a formal Promotion Gate.
13. A completed checklist item requires engineering evidence.
14. If information is unknown, record `UNKNOWN` / `BLOCKED` / `NOT_IMPLEMENTED`. Never invent completion.

## Version governance

V4-006 establishes the exact version identity contract in [`docs/V4_VERSIONING_STANDARD.md`](docs/V4_VERSIONING_STANDARD.md), [`docs/V4_VERSION_IDENTITY_CONTRACT.md`](docs/V4_VERSION_IDENTITY_CONTRACT.md), [`docs/V4_COMPATIBILITY_POLICY.md`](docs/V4_COMPATIBILITY_POLICY.md), and [`docs/V4_RELEASE_NAMING.md`](docs/V4_RELEASE_NAMING.md).

- Every formal artifact uses explicit `jcfb_version`, model/engine/selector/config/schema/migration/dataset versions, role-scoped revisions, lifecycle `status`, and the required hashes.
- `PRODUCTION`, `SHADOW`, and `EXPERIMENT` identities remain isolated. A role revision cannot be copied into another role.
- `latest`, `current`, `default`, or an equivalent nickname is never a model, engine, selector, config, dataset, release, or run identity.
- Version, revision, status, compatibility, and hash changes are append-only and require the evidence and promotion rules defined by the linked contracts.
- Production/Shadow/Experiment code must consume versioned contracts; free-form unversioned payloads are forbidden in formal paths.

## Repository boundary

All V4 changes must stay inside this repository. The V3.3.3 repository, database history, frozen predictions, historical predictions, reviews, and model parameters are protected external assets. They must not be copied, migrated, renamed, or edited as part of V4 bootstrap work.

## Evidence boundary

A task may be marked complete only when its design is finalized, an engineering artifact exists, validation has completed, documentation is present, and Git traceability exists. Discussion alone is not completion evidence.

Database changes must originate from approved migrations.
Blueprint SQL must never be auto-applied.
Audit-critical tables are append-only unless a Constitution-approved correction path exists.

## Constitutional Rules

JCFB V4 is governed by [`docs/V4_CONSTITUTION.md`](docs/V4_CONSTITUTION.md). If an AGENTS instruction conflicts with `docs/V4_CONSTITUTION.md`, then `V4_CONSTITUTION.md` wins.

The highest-priority operational rules are:

- Verified objective data comes before prediction; unknown, unavailable, or unverified information is never guessed.
- Objective facts and model interpretation remain separate.
- Pre-match inputs must pass the declared cutoff and no-future-information boundary.
- Frozen Input and Frozen Prediction are immutable; corrections and revisions are append-only.
- Production, Shadow, and Experiment remain isolated, and Promotion requires evidence and manual approval.
- Shadow and Experiment cannot mutate Production, Frozen Prediction, confidence, review, Tier A, or the canonical public projection.
- Experiment cannot count as Forward Tier A evidence or be relabeled as Shadow.
- Promotion requires manual review and an explicit Production release identity; auto-promotion is prohibited.
- Probability is not confidence; abstention is valid; five markets and score selection remain independently governed.
- Formal persistence paths must respect append-only history, role isolation, and Frozen Input lineage; directly overwriting audit-critical records is prohibited.
- Secrets never enter Git, Public Web is read-only, and failures default to `BLOCKED` / fail closed.

The full Articles, machine-oriented rule IDs, time policy, runtime role boundary, access matrix, model lifecycle, correction workflow, and incident response are defined in the Constitution and its companion governance documents, including docs/V4_RUNTIME_ROLE_BOUNDARY.md, docs/V4_PRODUCTION_POLICY.md, docs/V4_SHADOW_POLICY.md, docs/V4_EXPERIMENT_POLICY.md, docs/V4_PROMOTION_PATH.md, and docs/V4_RUNTIME_ACCESS_MATRIX.md. Agents must not silently promote, rewrite history, or begin the next V4 task.
