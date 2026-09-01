# JCFB V4 Release Naming Standard 1.0

Status: V4-006 COMPLETE

## 1. Purpose

This document defines the release, component, dataset, migration, and run naming grammar used by JCFB V4. Names are stable pointers to exact identities; they are not informal status labels.

The version identity fields and lifecycle rules are defined in `docs/V4_VERSIONING_STANDARD.md` and `docs/V4_VERSION_IDENTITY_CONTRACT.md`. Compatibility classification is defined in `docs/V4_COMPATIBILITY_POLICY.md`.

## 2. Canonical naming grammar

```text
SEMVER_RELEASE       = <name>-v<MAJOR>.<MINOR>.<PATCH>
PRERELEASE           = <name>-v<MAJOR>.<MINOR>.<PATCH>-rc.<N>
COMPONENT_ID         = <lower-kebab-name>@<MAJOR>.<MINOR>.<PATCH>#r<N>
DATASET_ID           = <lower-kebab-name>@<MAJOR>.<MINOR>.<PATCH>#r<N>
MIGRATION_ID         = migration@YYYYMMDD.NNN
FROZEN_ID            = fi-YYYYMMDD-NNNNNN
SHADOW_ID            = sh-YYYYMMDD-NNNNNN
EXPERIMENT_ID        = ex-YYYYMMDD-NNNNNN
```

The `#r<N>` registry revision is an exact identity suffix. It is not SemVer build metadata and it is never reused. Dates in Frozen/Shadow/Experiment IDs are creation-date components for traceability; they do not define precedence or data availability.

## 3. Allowed examples

| Kind | Allowed name | Meaning |
|---|---|---|
| Product release | `jcfb-v4.0.0` | JCFB product contract release |
| Product candidate | `jcfb-v4.1.0-rc.1` | Pre-release candidate, not Production approval |
| Engine release | `score-engine-v4.0.0` | Score Engine SemVer release |
| Selector release | `exact-score-selector-v4.0.0` | Exact Score Selector SemVer release |
| Config identity | `score-engine-config@4.0.0` plus its `config_hash` | Exact effective config identity |
| Dataset identity | `pre-match-facts@4.0.0#r001` | Exact dataset release/revision |
| Migration | `migration@20260901.001` | Ordered schema/storage migration |
| Frozen revision | `fi-20260901-000001` | Immutable Frozen Input revision |
| Shadow revision | `sh-20260901-000001` | Isolated Shadow run revision |
| Experiment revision | `ex-20260901-000001` | Isolated Experiment run revision |

The examples are naming examples, not evidence that those runtime artifacts already exist.

## 4. Forbidden names

The following cannot be used as a model, engine, selector, config, dataset, release, or run identity:

```text
latest
latest-model
latest-model-v4
current
current-version
current-model
default-model
the-current-one
model-final
model-final-final
v4
the-model-just-changed
```

`latest` may appear only in an explicitly ordered read/data concept such as `Latest Snapshot` or `canonical_latest_update_at`. That exception must not leak into a model registry, formal run envelope, release name, or hash key.

## 5. Naming and lifecycle separation

Lifecycle is stored as an explicit `status` field:

```text
DRAFT
EXPERIMENT
SHADOW
PROMOTION_REVIEW
PRODUCTION
RETIRED
```

Do not encode mutable state in a release name, for example `score-engine-v4.0.0-production` or `score-engine-v4.0.0-latest`. A release can be promoted or retired while its exact name remains unchanged; the registry appends status events and evidence.

`BLOCKED`, `UNKNOWN`, `UNAVAILABLE`, `NOT_IMPLEMENTED`, and `NOT_APPLICABLE` are explicit states/values, not release names.

## 6. Release record requirements

Every release or promotion record must include:

- exact `jcfb_version`, component/model/engine/selector version, and `revision`;
- `config_version`, `schema_version`, `migration_version`, and `dataset_version` as applicable;
- `implementation_hash`, `config_hash`, and compatibility level;
- predecessor/replacement relation, status, effective time, owner, reason, and evidence references;
- Promotion Gate result and explicit human approval for Production;
- no secrets, credential values, or private tokens.

Release names never carry the responsibility of proving reproducibility. Reproducibility comes from the identity tuple and the declared hashes.

## 7. Version bump naming rules

- A breaking contract gets a new major release name.
- A backward-compatible additive contract gets a new minor release name.
- A backward-compatible correction gets a new patch release name.
- Any behavior-affecting implementation/config/selector change also gets a new revision and new evidence, even when the SemVer bump is patch-compatible.
- A new dataset or migration revision is named independently and referenced by the run; it is not hidden in a model release name.

## 8. Naming audit

Before a release is accepted, check that:

1. the name matches the canonical grammar;
2. the embedded SemVer agrees with the identity fields;
3. the registry revision is unique and immutable;
4. status is stored separately;
5. exact hashes and compatibility are declared;
6. no unqualified alias appears in the release, run, config, dataset, or public projection identity;
7. the release does not alter V3.3.3 content or lineage.

## 9. References

- `docs/V4_VERSIONING_STANDARD.md`
- `docs/V4_VERSION_IDENTITY_CONTRACT.md`
- `docs/V4_COMPATIBILITY_POLICY.md`
- `docs/V4_CONSTITUTION.md`
- `docs/V4_MODEL_GOVERNANCE.md`
