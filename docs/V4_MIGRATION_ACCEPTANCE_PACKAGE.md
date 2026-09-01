# JCFB V4 Migration Acceptance Package

Contract: `v4-batch-03-acceptance-package@1.0.0`
Task: `V4-017`
Batch: `BATCH-03`
Status: `STATIC_PACKAGE_READY; RUNTIME_PENDING_DISPOSABLE_DB`

## Scope

This package binds the ordered V4 migration manifest to the later human acceptance process. It is an evidence packet and roll-forward decision contract, not a migration runner. The builder is [`tools/migration_harness/acceptance.py`](../tools/migration_harness/acceptance.py), the JSON shape is [`config/migration_harness/v4_batch_03_acceptance_package.schema.json`](../config/migration_harness/v4_batch_03_acceptance_package.schema.json), and the reference index is [`config/migration_harness/v4_batch_03_evidence_index.json`](../config/migration_harness/v4_batch_03_evidence_index.json).

`NO_PRODUCTION_APPLY_IN_THIS_BATCH = TRUE`. The packet requests independent approval but does not grant it. It cannot produce `READY_FOR_PRODUCTION_APPLY`, invoke a connector, execute SQL, apply migration, write Supabase, run a model, run Production/Shadow, promote a revision, or mutate V3.3.3.

## Package contents

1. **Target environment identity snapshot** — target ID, environment, provider, safe database identity, target identity hash, ownership, and `RUNTIME_PENDING_DISPOSABLE_DB` status. No URL or credential value is stored.
2. **Migration manifest 0001–0009** — migration IDs/versions, predecessor dependencies, design-only status, `PENDING_CANONICAL_HASH` values, and the metadata-only manifest identity hash.
3. **Expected schema/object catalog** — seven schemas, 36 tables, 64 indexes, 18 functions, 6 views, 45 triggers, 1 policy, and 30 RLS tables from the authoritative snapshot. An absent actual catalog is unknown and blocks rather than auto-repairing.
4. **Preflight result schema** — PF-01 through PF-18 with status, target dependence, reason, and evidence reference. Without a supplied disposable catalog, runtime checks are `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB`; PF-13 remains blocked while canonical hashes are pending.
5. **Smoke and negative matrix** — all 20 smoke cases and all 22 negative cases are registered. The 22 pure refusal contracts execute locally; 15 database-enforcement negatives and all 20 smoke cases remain runtime-pending.
6. **Security and data-integrity gates** — RLS, triggers, views, SECURITY DEFINER/search-path, advisor, audit chain, namespace/V3.3.3 isolation, no-future-leakage, and Tier A same-frozen-input checks are linked and explicitly pending where a database is required.
7. **Migration-history and schema-diff expectations** — exact ordered history, immutable applied rows, partial-state preservation, no in-place repair, expected-vs-actual classifications, and `unknown => BLOCKED` behavior.
8. **Roll-forward drill** — a no-SQL control-flow simulation: stop at a simulated failed migration, retain partial history, reconcile read-only, create a new forward identity for repair, and hold for independent approval. It is not a runtime database drill.
9. **Roles and signoff placeholders** — Human Approver, Migration Executor, and Auditor remain distinct, pending, and auditable. Approval is requested, not granted.
10. **Machine-readable evidence index and report** — [`docs/V4_BATCH_03_ACCEPTANCE_REPORT.json`](V4_BATCH_03_ACCEPTANCE_REPORT.json) and the Markdown rendering at [`docs/V4_BATCH_03_ACCEPTANCE_REPORT.md`](V4_BATCH_03_ACCEPTANCE_REPORT.md) reference the checked-in source index.

## Runtime disposition

| Evidence group | Registered | Executed in BATCH-03 | Status |
|---|---:|---:|---|
| Repository unit tests | actual test run | yes | `PASS` |
| Negative unit refusal contracts | 22 | 22 | `PASS` for pure refusal contracts only |
| Database-enforcement negative cases | 15 | 0 | `RUNTIME_NEGATIVE_TEST_PENDING` |
| Migration smoke runtime cases | 20 | 0 | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |
| PostgreSQL catalog/RLS/trigger/view/security/advisor checks | required | 0 | `NOT_EXECUTED_REQUIRES_DISPOSABLE_DB` |

No pending case may be counted as PASS. Production deployment approval is blocked until all required disposable/staging runtime evidence is present, independently reviewed, and linked to the exact target identity and manifest.

## Evidence contract

Each evidence package records migration IDs and hashes, tool/harness version, source Git commit, config hash, target identity hash, preflight outcomes, tests executed, tests pending, failures, blockers, timestamp, and separate approver/executor/auditor fields. `PENDING_CANONICAL_HASH` is retained literally until canonicalization; it is not replaced by a guessed hash. Raw secrets are excluded.

## Acceptance disposition

This package may be accepted for BATCH-03 static readiness and evidence assembly while runtime evidence remains pending. The next step is the separate BATCH-04 HARD_GATE for formal schema apply and Production DB write activation. BATCH-03 does not cross that gate automatically.
