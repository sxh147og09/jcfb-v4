# JCFB V4 Migration Dependency Graph 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY)

## 1. Strict graph

The approved design graph is a total order. Each edge is an explicit dependency, not merely a preferred human sequence:

```mermaid
flowchart LR
    M1["0001 prerequisites"] --> M2["0002 registries/core"]
    M2 --> M3["0003 market/context/evidence"]
    M3 --> M4["0004 frozen/runtime"]
    M4 --> M5["0005 evaluation"]
    M5 --> M6["0006 governance/audit"]
    M6 --> M7["0007 security/RLS/triggers"]
    M7 --> M8["0008 projections/views"]
    M8 --> M9["0009 seed/smoke"]
```

The edge labels are:

| From | To | Reason |
|---|---|---|
| 0001 | 0002 | Namespaces, hash helper, migration history, and registry metadata must exist before version/core tables. |
| 0002 | 0003 | All market/context/evidence rows require canonical `core.matches`, `core.teams`, and `core.competitions`. |
| 0003 | 0004 | Frozen Input selection tables require exact market, context, evidence, and bundle parent identities. |
| 0004 | 0005 | Results/reviews/Tier A reference frozen runtime artifacts and their hashes. |
| 0005 | 0006 | Governance audit and release-pointer design records evaluation and promotion lifecycle events. |
| 0006 | 0007 | Security functions and audit triggers require all governance tables and the final internal table set. |
| 0007 | 0008 | Public projection must be created only after grants, RLS, and validator functions are ready. |
| 0008 | 0009 | Seed/acceptance evidence must inspect the complete projection/view surface. |

## 2. Dependency matrix

| Migration | Direct parents | Objects consumed | Objects produced |
|---:|---|---|---|
| 0001 | none | approved target prerequisites only | schemas, `is_v4_hash`, `schema_migrations`, `v4_schema_registry`, hash registry |
| 0002 | 0001 | `governance.is_v4_hash`, `core`/`governance` namespaces | registries and canonical identity tables |
| 0003 | 0002 | match/team FKs and hash helper | market, context, evidence, and membership tables |
| 0004 | 0003 | snapshot/context/evidence IDs and registry IDs | frozen, feature, runtime, prediction tables and joins |
| 0005 | 0004 | Frozen Prediction, Prediction, Engine Run, Frozen Input | result, review, Tier A, promotion, calibration tables |
| 0006 | 0005 | match and evaluation lineage | release pointer, incident, audit tables and active-pointer indexes |
| 0007 | 0006 | all internal tables and audit functions | trigger functions, trigger attachments, RLS, revokes, controlled grants |
| 0008 | 0007 | secured internal rows and `public` namespace | projection ledger and six views |
| 0009 | 0008 | complete schema plus version registries | static registry seed, smoke manifest, acceptance snapshot shape |

## 3. Parallelism decision

No 0001-0009 migration is approved for parallel execution. PostgreSQL DDL, foreign keys, trigger order, RLS, and audit dependencies make serial application the safe default. Running two files concurrently could produce locks, missing-parent failures, incomplete trigger coverage, or a schema that appears present but has not passed its gate.

Future deployment optimization may split independent, read-only work only after the serial schema contract is already committed and tested:

- `CREATE INDEX CONCURRENTLY` for an existing table may be a separate non-transactional migration with its own preflight and history row.
- A view rebuild may be staged after its underlying projection and grants are stable.
- Advisor-only catalog inspection may run in parallel with no DDL.

Those are future optimization notes, not alternate dependencies and not actions in V4-011. They cannot weaken the total-order acceptance gates.

## 4. Cycle and completeness check

Cycle check: **PASS**. Every edge points from a lower sequence to the next higher sequence, and the topological order is exactly `0001, 0002, 0003, 0004, 0005, 0006, 0007, 0008, 0009`. No back-edge, self-edge, or unlisted parent exists.

Dependency completeness: **PASS**. All required phases are represented, each SQL filename is unique, each migration ID is unique, and every phase has a documented parent, purpose, object set, and gate.
