# JCFB V4 BATCH-10 Architecture Governance Decision

Decision ID: `V4-010-ADR-001`  
Status: `APPROVED / RESOLVED`  
Decision date: `2026-09-04`  
Baseline: `BATCH-09 COMPLETE`, BATCH-10 Entry Review previously `BLOCKED`

## 1. Decision

Frozen Input is a downstream freeze artifact of Feature Bundle. The approved data flow is:

```text
canonical facts / official odds / external markets / team context / Evidence Graph
    -> Feature Bundle (BATCH-10: V4-038 -> V4-039 -> V4-040)
    -> downstream feature/quality layers
    -> Frozen Input (BATCH-20: V4-076)
    -> Prediction
```

The approved dependency graph is authoritative. V4-076 remains downstream of V4-038 and V4-039 and is not moved into BATCH-10. No pre-freeze workaround, mock Frozen Input, or implementation of V4-076 is authorized by this decision.

## 2. Contract amendments

### Feature Bundle

`feature-bundle@1.0.0` is preserved at `docs/V4_FEATURE_BUNDLE_CONTRACT_1.0.md`. The active contract is a new breaking major version, `feature-bundle@2.0.0`, at `docs/V4_FEATURE_BUNDLE_CONTRACT.md`.

The v2 creation boundary removes the required upstream dependency on `frozen_input_id` and `frozen_input_hash`. It instead requires exact, hash-bound lineage for canonical entities/facts, official odds, external markets, team context, Evidence Graph, cutoff/kickoff, feature schema, and generator. `input_hash` is derived from those actual accepted inputs. `feature_snapshot_hash` is established by V4-039.

### Frozen Input

`frozen-input@1.0.0` is preserved at `docs/V4_FROZEN_INPUT_CONTRACT_1.0.md`. The active downstream contract is `frozen-input@2.0.0` at `docs/V4_FROZEN_INPUT_CONTRACT.md`. It requires `feature_bundle_id`, `feature_snapshot_hash`, and the exact Feature Bundle contract version, and includes them in `frozen_input_hash`. V4-076 remains the implementation boundary.

These are breaking semantic changes under the V4 Versioning Standard because required fields and dependency/time meaning change. No old contract is overwritten and no silent v1-to-v2 coercion is permitted.

## 3. Confidence semantics

The active Feature Bundle contract rejects an unqualified bare `confidence`. It uses the typed `feature_quality` object with only coverage, verification, freshness, completeness, conflict, and provenance dimensions. These describe data/evidence quality and never express win probability, model confidence, betting confidence, recommendation grade, or engine output. Source/evidence confidence remains governed by its own contract.

## 4. Dependency and task consistency

The task sequence is unchanged:

```text
V4-038 -> V4-039 -> V4-040   [BATCH-10]
                              \\-> V4-076 [BATCH-20 downstream consumer]
```

V4-038 still consumes V4-021, V4-022, V4-027, V4-031, and V4-037. V4-039 consumes V4-038. V4-040 consumes V4-039. V4-076 consumes V4-022, V4-038, V4-039, and V4-075. There is no edge from V4-076 back to V4-038 or V4-039, so the semantic cycle is removed without changing task order or scope.

## 5. Hash, time, and append-only impact

Feature Bundle `input_hash` covers only the ordered accepted upstream lineage and declared temporal/schema/generator identities. `feature_snapshot_hash` covers the deterministic feature representation and is established by V4-039. `frozen_input_hash` later covers the exact Feature Bundle identity/hash plus the other approved frozen inputs. Generation telemetry remains excluded only when the hash profile declares it volatile.

All bundle and freeze corrections are append-only with new identities, hashes, revisions, and `supersedes` references. Cutoff and future-information gates remain governed by V4-022 and are not implemented or weakened here.

## 6. Compatibility, migration, and production impact

- Compatibility: v1 artifacts remain readable only through an explicit v1 reader/adapter; no active v2 reader may treat a missing Frozen Input as valid v2 input.
- Migration: no migration is added or applied. Physical schema implications are recorded for later approved design work only.
- Production/Supabase: no reads, writes, deployment, promotion, or credential use.
- V3.3.3: no source, contract, migration, data, or runtime path under V3.3.3 is modified.
- Scope: this decision changes governance artifacts and consistency checks only. V4-038, V4-039, V4-040, V4-076, and all later engines remain unimplemented.

## 7. Acceptance gate

The resolution is accepted only when contract consistency tests, documentation consistency audit, dependency cycle audit, full repository tests, `git diff --check`, Production/migration audit, and V3.3.3 isolation audit all pass. After that gate, BATCH-10 Scope & Entry Review is re-run as a read-only review; task implementation does not start in this decision.

