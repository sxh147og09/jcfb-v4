# JCFB V4 Frozen Input Contract 2.0

Status: V4-010 ARCHITECTURE GOVERNANCE AMENDMENT  
Contract version: `frozen-input@2.0.0`  
Supersedes: `frozen-input@1.0.0` in `docs/V4_FROZEN_INPUT_CONTRACT_1.0.md`

## 1. Decision and boundary

Frozen Input is the immutable downstream freeze artifact for a formal pre-match run. It consumes accepted canonical facts, source snapshots, context, Evidence, and the exact Feature Bundle; it is not an upstream prerequisite of Feature Bundle creation.

```text
canonical facts / official odds / external markets / team context / Evidence Graph
    -> Feature Bundle (feature-bundle@2.0.0)
    -> downstream feature/quality acceptance
    -> Frozen Input (frozen-input@2.0.0)
    -> Prediction
```

## 2. Required fields

In addition to the existing Frozen Input identity, role, cutoff, registry, and immutability fields, a validated or frozen object must contain:

| Field | Rule |
|---|---|
| `feature_bundle_id` | Exact accepted Feature Bundle identity; required and resolvable. |
| `feature_snapshot_hash` | Exact snapshot hash produced by V4-039; required and equal to the referenced bundle. |
| `feature_bundle_contract_version` | Exact Feature Bundle contract version used, currently `feature-bundle@2.0.0`. |
| `frozen_input_hash` | Includes the exact Feature Bundle identity/hash and all other approved frozen inputs. |

All existing required fields in the archived v1 contract remain governed unless expressly amended here. A missing or mismatched Feature Bundle reference is `BLOCKED`; no mock, placeholder, or silent fallback is valid.

## 3. Hash and immutability rules

The Frozen Input hash covers canonical identity, selected official/external/context/evidence references and hashes, `feature_bundle_id`, `feature_snapshot_hash`, feature schema, cutoff/kickoff, model/engine/config registry identities, dataset/schema versions, role/group/mode, and supersession lineage. It is distinct from `input_hash` and `feature_snapshot_hash`.

After `FROZEN`, the record and its referenced Feature Bundle are immutable. A correction appends a new revision with a new hash and explicit `supersedes_frozen_input_id`; it never edits the prior record or rewrites the Feature Bundle.

## 4. Time and role boundary

All selected inputs must be eligible by `prediction_cutoff_at`, with cutoff before kickoff. This contract does not weaken V4-022. Production, Shadow, and Experiment records retain their role and may be compared only under the approved same-frozen-input rules.

Frozen Input is not implemented by this amendment; V4-076 remains the approved implementation task in BATCH-20.

