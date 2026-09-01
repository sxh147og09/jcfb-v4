# JCFB V4 Version Identity Contract 1.0

Status: V4-006 COMPLETE

## 1. Contract purpose

This contract defines the field-level identity required to register a JCFB V4 component and to admit a formal Engine Run. It is the machine-oriented companion to `docs/V4_VERSIONING_STANDARD.md`. It defines identity and lineage; it does not claim that a runtime registry or database schema has already been implemented.

An implementation that cannot populate a required field must return `BLOCKED` or `NOT_IMPLEMENTED`. It must not substitute `latest`, `current`, a display name, a branch name, a timestamp, or an empty value.

## 2. Canonical forms

```text
SEMVER              = MAJOR.MINOR.PATCH
COMPONENT_VERSION   = <lower-kebab-name>@<SEMVER>
REVISION            = r<positive decimal sequence, no reuse>
HASH               = sha256:<64 lowercase hexadecimal characters>
DATASET_VERSION     = <lower-kebab-name>@<SEMVER>#<REVISION>
MIGRATION_VERSION   = migration@YYYYMMDD.NNN
FROZEN_REVISION     = fi-YYYYMMDD-NNNNNN
SHADOW_REVISION     = sh-YYYYMMDD-NNNNNN
EXPERIMENT_REVISION = ex-YYYYMMDD-NNNNNN
```

Names are lowercase machine identifiers. Display labels may be title-cased, but they do not replace the canonical values.

## 3. Required identity fields

| Field | Required when | Type / form | Identity rule |
|---|---|---|---|
| `jcfb_version` | Every V4 artifact | `COMPONENT_VERSION`, name `jcfb` | Product contract identity; not a branch or release alias |
| `model_name` | Every registered model or formal run | lower-kebab string | Stable component namespace |
| `model_version` | Every registered model or formal run | `COMPONENT_VERSION` | Must agree with `model_name`, `major`, `minor`, `patch` |
| `major` | Every registered model or formal run | non-negative integer | SemVer major component |
| `minor` | Every registered model or formal run | non-negative integer | SemVer minor component |
| `patch` | Every registered model or formal run | non-negative integer | SemVer patch component |
| `revision` | Every registered model or formal run | `REVISION` | Immutable registry instance; never reused |
| `engine_version` | Every engine run | `COMPONENT_VERSION` | Exact execution engine contract |
| `selector_name` | When a selector is executed | lower-kebab string | Selector namespace; otherwise `NOT_APPLICABLE` |
| `selector_version` | When a selector is executed | `COMPONENT_VERSION` | Selector contract and behavior identity |
| `selector_revision` | When a selector is executed | `REVISION` | Exact selector registration instance |
| `config_version` | Every formal run | `COMPONENT_VERSION` | Effective model-affecting config identity |
| `schema_version` | Every persisted/exchanged formal artifact | `COMPONENT_VERSION` | Record/interface shape and semantics |
| `migration_version` | When storage has migrations | `MIGRATION_VERSION` | Ordered storage state; otherwise explicit `NOT_APPLICABLE` |
| `dataset_version` | Every formal run | `DATASET_VERSION` | Exact accepted data release and provenance |
| `frozen_revision` | Production/Shadow and formal frozen evidence | `FROZEN_REVISION` | Immutable input boundary; otherwise declared `NOT_APPLICABLE` only for an Experiment that is not frozen |
| `frozen_input_hash` | When `frozen_revision` applies | `HASH` | Hash of the complete Frozen Input record |
| `role` | Every formal run | `PRODUCTION`, `SHADOW`, or `EXPERIMENT` | Cannot be inferred from a path or filename |
| `shadow_revision` | `role = SHADOW` | `SHADOW_REVISION` | Required and isolated; otherwise `NOT_APPLICABLE` |
| `experiment_revision` | `role = EXPERIMENT` | `EXPERIMENT_REVISION` | Required and isolated; otherwise `NOT_APPLICABLE` |
| `implementation_hash` | Every formal run | `HASH` | Exact implementation/dependency bundle |
| `config_hash` | Every formal run | `HASH` | Exact effective non-secret config |
| `input_hash` | Every formal run | `HASH` | Exact engine input envelope |
| `output_hash` | Every formal output | `HASH` | Exact raw output envelope |
| `compatibility_level` | Every released or promoted component | enum | `PATCH_COMPATIBLE`, `MINOR_COMPATIBLE`, or `MAJOR_BREAKING` |
| `status` | Every registered component/revision | lifecycle enum | Governed transition state; never encoded as a mutable name |
| `owner` | Every registered component/revision | attributable string | Accountable owner, not a secret |
| `created_at` | Every registered component/revision | timezone-aware timestamp | Creation audit; not a version substitute |
| `run_at` | Every formal run | timezone-aware timestamp | Execution audit |
| `runtime_environment` | Every formal run | declared non-secret descriptor | Reproducibility context; secrets excluded |

The complete lifecycle enum is `DRAFT`, `EXPERIMENT`, `SHADOW`, `PROMOTION_REVIEW`, `PRODUCTION`, or `RETIRED`. `BLOCKED`, `UNKNOWN`, `UNAVAILABLE`, and `NOT_IMPLEMENTED` describe gate or data states and are not successful lifecycle promotions.

## 4. Role-scoped field matrix

| Role | `frozen_revision` | `shadow_revision` | `experiment_revision` | Publication authority |
|---|---|---|---|---|
| `PRODUCTION` | Required | `NOT_APPLICABLE` | `NOT_APPLICABLE` | Formal V4 prediction only after all gates pass |
| `SHADOW` | Required for a comparable pre-match run | Required | `NOT_APPLICABLE` | Isolated evaluation only |
| `EXPERIMENT` | Required when the experiment claims a frozen A/B comparison; otherwise `NOT_APPLICABLE` with a declared reason | `NOT_APPLICABLE` | Required | Research artifact only; never formal public output |

The same `frozen_input_hash` is required for a valid Production/Shadow/Experiment comparison. A different cutoff, fact snapshot, feature bundle, dataset, or input payload is a different run even when the match is the same.

## 5. Canonical formal run envelope

The following is an `EXAMPLE ONLY` with synthetic values. The hash strings are placeholders for the real SHA-256 results of their declared payloads; they are not implementation evidence.

```json
{
  "jcfb_version": "jcfb@4.0.0",
  "model_name": "score-engine",
  "model_version": "score-engine@4.0.0",
  "major": 4,
  "minor": 0,
  "patch": 0,
  "revision": "r001",
  "engine_version": "score-engine@4.0.0",
  "selector_name": "exact-score-selector",
  "selector_version": "exact-score-selector@4.0.0",
  "selector_revision": "r001",
  "config_version": "score-engine-config@4.0.0",
  "schema_version": "prediction-record@4.0.0",
  "migration_version": "migration@20260901.001",
  "dataset_version": "pre-match-facts@4.0.0#r001",
  "frozen_revision": "fi-20260901-000001",
  "frozen_input_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "role": "PRODUCTION",
  "shadow_revision": "NOT_APPLICABLE",
  "experiment_revision": "NOT_APPLICABLE",
  "implementation_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "config_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "input_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "output_hash": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "compatibility_level": "MINOR_COMPATIBLE",
  "status": "PRODUCTION",
  "owner": "team-jcfb-v4",
  "created_at": "2026-09-01T09:00:00+08:00",
  "run_at": "2026-09-01T09:05:00+08:00",
  "runtime_environment": "python-runtime@4.0.0; lockfile=declared"
}
```

## 6. Identity invariants

1. `model_version` must equal `<model_name>@<major>.<minor>.<patch>`.
2. `engine_version`, `selector_version`, `config_version`, and `schema_version` must each identify the named component they describe.
3. A selector change creates a new `selector_revision` and a new output lineage even when the upstream score distribution is reused.
4. `config_version` and `config_hash` are both required; a version without a hash cannot prove the effective configuration.
5. `dataset_version`, `frozen_revision`, and `frozen_input_hash` identify data lineage; they cannot be inferred from a match date or file name.
6. `input_hash` is calculated before output creation. `output_hash` is calculated from the raw output and its input identity, before result or review data exists.
7. `implementation_hash`, `config_hash`, `input_hash`, `output_hash`, and `frozen_input_hash` are immutable after use.
8. A required identity or hash that is missing blocks the affected formal artifact; it is not normalized to a placeholder that looks valid.
9. A `status` transition appends an audit event with actor, reason, time, predecessor, successor, and evidence; it does not rename the revision.
10. No formal artifact may use `latest`, `current`, `default`, `the model just changed`, or an equivalent alias as a substitute for an exact field.

## 7. Hash payload contract

Hashing uses UTF-8 bytes, LF line endings, lexically sorted object keys, deterministic number/string representation, and SHA-256. The canonical serialization profile must be implemented once and versioned as part of the implementation identity.

| Hash | Includes | Excludes |
|---|---|---|
| `implementation_hash` | Source/bundle bytes, declared dependency locks, build manifest | Secrets, `.git` metadata, caches, generated outputs |
| `config_hash` | Effective non-secret model/config values and declared defaults | Credential material and unrecorded runtime overrides |
| `input_hash` | Exact engine input, cutoff, feature/dataset refs, role, component refs | Output, result, review, or later facts |
| `output_hash` | Exact raw output and input/component refs | Presentation-only formatting, result, review, or human explanation |
| `frozen_input_hash` | Complete immutable Frozen Input record | Anything observed after the freeze boundary |

If a secret value can affect a model result but cannot be represented without storing the secret, the run is `BLOCKED`; a secret is never hashed into Git or a public record as a workaround.

## 8. Revision relations

Every replacement or promotion relation must preserve the old identity:

```text
new_revision.supersedes_revision
new_revision.promotes_from_revision
new_revision.effective_from
new_revision.reason
new_revision.evidence_refs[]
```

These relations are append-only. A correction to objective facts produces a new dataset/frozen/input identity under `docs/V4_CORRECTION_POLICY.md`; it never edits the old Frozen Input or Frozen Prediction.

## 9. Contract failure states

| Failure | Required result |
|---|---|
| Missing model/engine/selector/config/schema identity | `BLOCKED` |
| Missing implementation/config/input/output hash | `BLOCKED` |
| Missing cutoff, frozen input, or provenance required by role | `BLOCKED` or `UNKNOWN_TIME` |
| Role/revision mismatch | `ROLE_VIOLATION` and `BLOCKED` |
| Incompatible schema without approved adapter/migration | `COMPATIBILITY_BLOCKED` |
| Attempt to edit an identity after use | `IDENTITY_MUTATION` and incident review |
| Use of an unqualified alias such as `latest model` | `NOT_AUDITABLE` and `BLOCKED` |

## 10. Contract references

- `docs/V4_VERSIONING_STANDARD.md` — normative version layers and lifecycle
- `docs/V4_COMPATIBILITY_POLICY.md` — SemVer, schema, migration, adapter, and breaking-change rules
- `docs/V4_RELEASE_NAMING.md` — release and revision grammar
- `docs/V4_CONSTITUTION.md` — authority and non-negotiable governance
- `docs/V4_INTEGRITY_RULES.md` — machine-oriented enforcement rules
- `docs/V4_TIME_AND_INFORMATION_POLICY.md` — cutoff and future-information boundary
