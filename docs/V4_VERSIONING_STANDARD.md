# JCFB V4 Versioning Standard 1.0

Status: V4-006 COMPLETE

## 1. Authority and scope

This standard defines the canonical, auditable identity of every JCFB V4 product, model, engine, selector, configuration, schema, migration, dataset, frozen input, Shadow run, Experiment run, release, and formal output. It is a V4-006 governance artifact; it does not implement a model registry, database migration, model execution path, or promotion service.

The authority order is:

1. `docs/V4_CONSTITUTION.md`
2. this standard and `docs/V4_VERSION_IDENTITY_CONTRACT.md`
3. `docs/V4_COMPATIBILITY_POLICY.md` and `docs/V4_RELEASE_NAMING.md`
4. the model, data-flow, integrity, correction, and incident policies referenced by those documents

If an implementation cannot satisfy this standard, the affected artifact is `BLOCKED`, `NOT_VERIFIED`, or `NOT_IMPLEMENTED`; an approximate identity is not acceptable.

## 2. Non-negotiable principles

- Every formal artifact has an exact identity. A human-readable nickname is never the identity.
- A semantic version, a registry revision, a lifecycle status, and a content hash are different fields and cannot substitute for one another.
- A version or hash is immutable after it has been used by a run. A change creates a new identity and an append-only relation to the prior identity.
- A model change, selector change, configuration change, schema change, dataset change, or hash-canonicalization change creates new evidence requirements as defined below.
- Production, Shadow, and Experiment are separate roles with separate revision namespaces and separate outputs.
- `UNKNOWN` is for an unknown property; `NOT_APPLICABLE` is for a role-scoped field that does not apply. Neither may be replaced by an empty string.
- `latest model`, `latest version`, `current model`, `current version`, `the model just changed`, and `the current one` are not version identities. Formal records must use the exact fields in the Identity Contract.

The word `latest` may be used only for an explicitly ordered data or read-projection concept, such as `Latest Snapshot` or `canonical_latest_update_at`. It must not identify a model, engine, selector, config, dataset, release, or run.

## 3. Version identity layers

The following fields form the V4 identity vocabulary. The canonical machine forms and requiredness rules are defined in `docs/V4_VERSION_IDENTITY_CONTRACT.md`.

| Layer | Required identity | Canonical example | What a change means |
|---|---|---|---|
| JCFB product | `jcfb_version` | `jcfb@4.0.0` | Product contract change; apply SemVer and compatibility review |
| Model | `model_name`, `model_version`, `major`, `minor`, `patch`, `revision` | `outcome-model@4.0.0`, `r001` | New registered model identity; behavior changes require new evidence |
| Engine | `engine_version` | `score-engine@4.0.0` | Engine contract or implementation identity |
| Selector | `selector_name`, `selector_version`, `selector_revision` when used | `exact-score-selector@4.0.0`, `r001` | New candidate/ranking/selection identity; output lineage is new |
| Configuration | `config_version`, `config_hash` | `score-engine-config@4.0.0` | Effective model-affecting configuration must be addressable and hashed |
| Schema | `schema_version` | `prediction-record@4.0.0` | Record/API shape and semantics; compatibility policy applies |
| Migration | `migration_version` | `migration@20260901.001` | Ordered storage transition; migrations never rewrite immutable history |
| Dataset | `dataset_version` | `pre-match-facts@4.0.0#r001` | Exact dataset release, contents, cutoff, and provenance |
| Frozen input | `frozen_revision`, `frozen_input_hash` | `fi-20260901-000001` | Exact immutable pre-match input boundary |
| Shadow run | `shadow_revision` | `sh-20260901-000001` | Isolated comparison run; never a Production identity |
| Experiment run | `experiment_revision` | `ex-20260901-000001` | Isolated research run; never a Production identity |
| Implementation | `implementation_hash` | `sha256:<64 lowercase hex>` | Exact implementation/dependency bundle |
| Input | `input_hash` | `sha256:<64 lowercase hex>` | Exact engine input envelope |
| Output | `output_hash` | `sha256:<64 lowercase hex>` | Exact raw output envelope before presentation or review |
| Lifecycle | `status` | `PROMOTION_REVIEW` | Governed state transition, not a replacement for version identity |

## 4. Canonical identity tuple

For a formal run, the auditable identity is the tuple below. Fields marked `when applicable` remain explicit as `NOT_APPLICABLE` when the role or component does not use them.

```text
(
  jcfb_version,
  model_name, model_version, major, minor, patch, revision,
  engine_version,
  selector_name, selector_version, selector_revision,
  config_version, schema_version, migration_version, dataset_version,
  frozen_revision, frozen_input_hash,
  role, shadow_revision, experiment_revision,
  implementation_hash, config_hash, input_hash, output_hash,
  compatibility_level, status
)
```

`run_id` may be added by a future runtime, but it cannot replace any field in this tuple. Match identity, kickoff, cutoff, source provenance, `feature_snapshot_hash`, and runtime environment remain required lineage fields under the existing V4 contracts.

## 5. SemVer and revision rules

V4 uses `MAJOR.MINOR.PATCH` with numeric components. The semantic version identifies a compatible contract family; `revision` identifies one immutable registry instance within that family.

### Breaking Change Rules

A breaking change is any change that makes an existing reader, stored artifact, hash interpretation, role boundary, or model-output meaning unsafe to consume without an explicit adapter or migration. It must receive a new major identity, new revision, compatibility review, and the evidence required by `docs/V4_COMPATIBILITY_POLICY.md`.

- `MAJOR` increments for an incompatible contract, semantic meaning, unit, time boundary, required field, output interpretation, hash canonicalization, or migration boundary.
- `MINOR` increments for a backward-compatible additive contract or capability. A new behavior still needs a new implementation hash, revision, and forward evidence.
- `PATCH` increments for a backward-compatible correction or documentation/implementation maintenance. If a patch changes model output, it still requires a new revision, output hash, and new evidence; the patch number must not hide a behavior change.
- `revision` is unique within its component namespace and is never reused. A revision is not a loophole for keeping an old semantic version after an algorithm, feature, weight, selector, calibration, simulation, league-profile, threshold, or effective configuration change.
- A content change that changes `implementation_hash`, `config_hash`, `input_hash`, or `output_hash` creates a new immutable run or registry identity. Historical records are not edited.

The full compatibility matrix, adapter rules, and breaking-change procedure are in `docs/V4_COMPATIBILITY_POLICY.md`.

## 6. Dataset, schema, and migration versioning

`dataset_version` identifies the exact accepted data release, including its declared cutoff, source/provenance boundary, freshness policy, and content hash. A corrected or re-ingested payload is a new dataset revision; it does not overwrite a dataset used by a Frozen Input.

`schema_version` identifies the shape and meaning of a record or interface. `migration_version` identifies an ordered storage transition applied to that schema. They are not model versions and must never be used to imply a model release.

Migration rules:

- migration identifiers are append-only, ordered, and immutable;
- a migration may add a new representation or adapter, but may not rewrite a Frozen Input, Frozen Prediction, historical result, or historical evaluation in place;
- an incompatible schema requires a new major schema version, an explicit adapter or migration, compatibility validation, and a new write identity;
- an unavailable migration or adapter produces `BLOCKED`, not silent coercion.

## 7. Hash identity rules

All required content hashes use the same deterministic hash profile:

1. build the declared payload with UTF-8 encoding;
2. canonicalize object keys in lexical order using the V4 canonical JSON profile;
3. normalize line endings to LF and numeric representations according to the profile;
4. hash the canonical bytes with SHA-256;
5. serialize as `sha256:<64 lowercase hexadecimal characters>`.

The payload boundaries are:

- `implementation_hash`: the exact implementation bundle and dependency-lock identity used by the component. It excludes `.git` metadata, caches, generated output, and secrets; excluded material cannot affect model behavior.
- `config_hash`: the effective non-secret, model-affecting configuration after declared defaults are resolved. Secret values never enter the payload. Missing required configuration is `BLOCKED`.
- `input_hash`: the exact engine input envelope, including the relevant `frozen_revision`/input identity, cutoff, dataset and feature references, role, and component versions.
- `output_hash`: the exact raw output envelope plus its input and component references, before display formatting, post-match result, review, or human explanation is attached.
- `frozen_input_hash`: the exact immutable Frozen Input record, including accepted facts, snapshots, provenance, cutoff, features, versions, and configurations.

Hashes are content identities, not confidence scores, timestamps, Git branch names, or release aliases. Same payload and same canonicalization must produce the same hash; a changed payload must not retain the old hash.

## 8. Lifecycle, Promotion, and Retirement

The allowed component lifecycle is:

```text
DRAFT -> EXPERIMENT -> SHADOW -> PROMOTION_REVIEW -> PRODUCTION -> RETIRED
```

These are lifecycle states, not version names. `BLOCKED` is a gate/result state and does not grant a transition.

Promotion requires a new immutable revision, declared compatibility, Frozen Forward Samples, statistical and calibration evaluation, integrity and no-future-leakage audits, regression and performance evidence, Promotion Review, and explicit human approval. `AUTO_PROMOTION = TRUE` is prohibited. A successful promotion records the promoted revision, predecessor, effective time, evidence references, and approval; it does not edit the predecessor.

For each declared model or engine, Production has exactly one Canonical Active Revision at a time. A new revision becomes active only after the Promotion Gate passes. Shadow and Experiment revisions cannot be copied into Production; they must pass the same formal promotion path.

Retirement is explicit and append-only. It stops new Production use after a declared effective time and reason, records a replacement when one exists, and preserves every historical run, Frozen Input, Frozen Prediction, evaluation, hash, and audit event. A retired revision is not silently reactivated; reuse requires a newly registered revision and the applicable gates.

## 9. Compatibility with the V4 architecture and Constitution

This standard implements the identity requirements of Constitution Articles 4, 7, 8, 13, 14, 25, 29, 30, 33, 35, 36, and 40. It preserves the architecture boundaries in `V4_ARCHITECTURE_BLUEPRINT.md`:

- canonical facts are shared only as timestamped, provenance-preserving facts;
- features, model outputs, Frozen Inputs, Frozen Predictions, reviews, and parameters remain isolated by model line;
- independent engines and selectors retain their own versions and hashes;
- the Final Prediction Gate precedes Frozen Prediction;
- Production, Shadow, and Experiment remain distinguishable;
- Public Web reads a projection and does not create or mutate model identity;
- V3.3.3 remains an independent protected model line.

The supporting field contract, compatibility policy, release grammar, model lifecycle policy, integrity rules, correction policy, and time policy must be read together. This standard does not authorize V4-007 or any Production, Shadow, or Experiment execution.

## 10. Required validation evidence

Before V4-006 is marked complete, the repository must show:

- all four V4-006 documents are present and cross-referenced;
- README, AGENTS, CHANGELOG, Constitution, architecture/model-governance references, and Checklist use the same vocabulary;
- no operational or implementation file uses an unqualified model/version alias;
- required version and hash fields are present in the contract and compatible with existing V4 governance;
- Secret Scan finds no credential material in repository content or staged content;
- V3.3.3 files are unchanged;
- `git diff --check` passes and Git traceability exists.

The repeatable repository check is `scripts/validate_v4_versioning.ps1`.
