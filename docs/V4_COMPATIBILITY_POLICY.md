# JCFB V4 Compatibility Policy 1.0

Status: V4-006 COMPLETE

## 1. Purpose

This policy determines whether a JCFB V4 artifact can be read, compared, reused, promoted, or retired across versions. It covers product, model, engine, selector, configuration, schema, migration, dataset, Frozen Input, Shadow, Experiment, and output contracts.

Compatibility is a declared property of exact identities. It is never inferred from a similar name, matching teams, matching date, a successful parse, or a label such as `latest` or `current`.

## 2. Compatibility outcomes

Every cross-version consumer decision returns one of:

- `COMPATIBLE` — the declared contract and identity rules permit direct use;
- `ADAPTER_REQUIRED` — an approved, versioned, tested adapter is required and is recorded in the run identity;
- `BLOCKED` — compatibility is not proven, a required migration is missing, or the change is breaking without approval.

A compatibility decision records both exact source and target identities, schema/migration versions, adapter identity when used, input/output hashes, reviewer/evidence references, and time.

## 3. SemVer compatibility matrix

| Change class | Version action | Consumer expectation | Promotion/evidence rule |
|---|---|---|---|
| `PATCH_COMPATIBLE` | Increment patch and create new revision | Existing readers may consume the contract without a required migration | Validate regression; if output changes, collect new forward evidence |
| `MINOR_COMPATIBLE` | Increment minor and create new revision | Existing readers may ignore declared optional additions; new required behavior needs an adapter | Validate old-reader behavior, new fields, and forward evidence |
| `MAJOR_BREAKING` | Increment major and create new revision | Direct cross-read is forbidden; use an approved adapter/migration or block | Compatibility review, migration/adapter tests, full evidence, and manual Promotion Review |

SemVer precedence does not decide whether two records are comparable. A `4.1.0` output cannot be silently treated as a `4.0.0` output, even if a consumer can technically parse it.

## 4. What is breaking

The following are `MAJOR_BREAKING` unless a formally reviewed adapter preserves the old semantics without ambiguity:

- removing, renaming, or changing the meaning/type/unit of a required field;
- changing timezone, cutoff, source-availability, result, or future-information semantics;
- changing the interpretation of a market, score state, probability, confidence, risk, or abstention value;
- changing the meaning or canonicalization of `implementation_hash`, `config_hash`, `input_hash`, `output_hash`, or `frozen_input_hash`;
- changing the role boundary so Shadow or Experiment can affect Production, or changing a read-only path into a mutating path;
- changing the ordering or immutability guarantees of Frozen Input, Frozen Prediction, migrations, or audit events;
- changing an enum so an existing value has a different meaning or a previously valid value becomes ambiguous;
- changing a migration in place or requiring an old immutable artifact to be rewritten.

These changes require a new major identity even when the code diff is small.

## 5. What is compatible

The following can be `MINOR_COMPATIBLE` or `PATCH_COMPATIBLE` only when their semantics remain explicit and validated:

- adding an optional field with a declared default or explicit `UNKNOWN`/`UNAVAILABLE` state;
- adding a new independent engine or selector output without changing existing fields;
- adding a new diagnostic field that cannot alter historical evaluation or Production behavior;
- correcting a non-behavioral documentation or metadata defect;
- improving implementation performance while preserving output contract and hash profile.

An output-affecting bug fix is still a new model/engine/selector revision with a new hash and forward evidence, even if the compatibility level is `PATCH_COMPATIBLE`.

## 6. Schema and migration policy

`schema_version` answers “what shape and semantics does this record expose?” `migration_version` answers “which ordered storage transition has been applied?” They are independent identities.

Schema rules:

1. A schema version is immutable after use.
2. Required fields may not be silently removed, renamed, narrowed, or reinterpreted.
3. Optional additions must be declared and must not break old readers that are within the supported major family.
4. A major schema change requires a new schema major, an adapter or migration plan, compatibility tests, and a new write identity.
5. A migration has one immutable identifier, one ordered application record, and one rollback/forward-recovery decision. Editing a migration after application is prohibited.
6. Frozen Input, Frozen Prediction, historical results, evaluations, and audit records are never rewritten to satisfy a new schema. A new representation or read adapter may be created.
7. If `schema_version` or `migration_version` cannot be proven, the consumer returns `BLOCKED`.

The database and migration runtime are deferred V4 implementation work; this policy defines the contract they must satisfy.

## 7. Model, engine, and selector compatibility

- A model or engine consumer must declare exact `model_version`, `engine_version`, `config_version`, `schema_version`, `dataset_version`, `implementation_hash`, and `input_hash` values.
- A configuration change must create a new `config_version` and `config_hash`. If it can change a model result, it also requires a new model/engine revision and evidence.
- A selector may reuse an unchanged score distribution only when the selector input contract and `input_hash` are compatible. The selector still creates a new `selector_version`/revision and `output_hash` when its behavior changes.
- A model or engine major change cannot consume old features or outputs directly without an explicitly compatible feature/schema contract or adapter.
- An implementation hash change cannot be hidden under an old version or revision.
- Same match, same teams, same date, or apparently unchanged odds do not establish compatibility; exact hashes and declared versions do.

## 8. Dataset and Frozen Input compatibility

`dataset_version` includes the accepted data boundary, cutoff, provenance, availability states, and content identity. A new source correction, added observation, removed row, changed cutoff, or changed canonicalization creates a new dataset revision and usually a new `input_hash`/`frozen_input_hash`.

Production, Shadow, and Experiment comparisons are valid only when the comparison contract requires the same `frozen_input_hash` and each role retains its own output and revision. If inputs differ, the comparison is `INCOMPARABLE`, not normalized by a label or a re-used output.

Historical Frozen Inputs and Frozen Predictions remain readable under their original schema/identity. A new consumer may use an adapter for analysis, but the adapted record is not a new historical prediction and cannot erase the original.

## 9. Breaking-change procedure

1. Identify the exact source and target component identities.
2. Declare the change and classify it as patch-compatible, minor-compatible, or major-breaking.
3. Create new SemVer, revision, implementation/config/schema/migration identities as applicable.
4. Define an adapter or migration for every supported old consumer; otherwise mark the path `BLOCKED`.
5. Run contract, serialization, hash, regression, no-future-leakage, and role-isolation tests.
6. Preserve old artifacts and record `supersedes_revision` or `promotes_from_revision`.
7. Complete Promotion Review and manual approval before Production use.
8. Retire the predecessor explicitly only after the replacement is effective and evidence is recorded.

No breaking change may be introduced by editing a version string, reusing a revision, overwriting a migration, or updating a Frozen record in place.

## 10. Promotion and retirement compatibility gates

Promotion is allowed only when:

- the target exact identity and compatibility level are registered;
- all required schema/migration adapters are available and tested;
- the target uses declared data and Frozen Input identity;
- implementation/config/input/output hashes are present;
- Production, Shadow, and Experiment evidence remains isolated;
- forward, calibration, integrity, regression, performance, and no-leakage evidence passes;
- a human reviewer approves the Promotion Gate.

Retirement stops new Production use but does not remove compatibility obligations for historical reads. A retired identity remains reproducible where its original implementation, configuration, dataset, and input references are available. Reactivation is not an implicit compatibility action; it requires a new revision and review.

## 11. Prohibited shortcuts

- treating `latest model`, `current version`, or `the current one` as a compatible identity;
- parsing a new major schema and silently dropping or guessing fields;
- copying Shadow or Experiment output into Production;
- using a new dataset or cutoff while retaining an old input hash;
- applying a migration by mutating historical Frozen records;
- calling a patch change “non-breaking” when its output changed without new evidence;
- declaring compatibility because two outputs look numerically similar.

## 12. References

- `docs/V4_VERSIONING_STANDARD.md`
- `docs/V4_VERSION_IDENTITY_CONTRACT.md`
- `docs/V4_RELEASE_NAMING.md`
- `docs/V4_CONSTITUTION.md`, Articles 4, 7, 8, 13, 14, 25, 29, 30, 33, 35, 36, and 40
- `docs/V4_MODEL_GOVERNANCE.md`
- `docs/V4_INTEGRITY_RULES.md`
- `docs/V4_CORRECTION_POLICY.md`
