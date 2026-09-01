# JCFB V4 Runtime Candidate Manifest 1.0

- Status: RUNTIME VALIDATION CANDIDATE
- Scope: DISPOSABLE/STAGING ONLY
- Production apply: HARD BLOCK
- Source manifest: database/migrations/v4/0000_manifest.md at cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
- Promotion source commit: 1e907c7490b5e102dea69372f22073ef3970ca6a
- Canonical migration hashes: PENDING_CANONICAL_HASH until the approved canonicalizer exists

## Candidate sequence

| Sequence | Candidate | Source design | Depends on | Byte hash (non-canonical) |
|---:|---|---|---|---|
| 0001 | database/migrations/v4_runtime_candidate/0001_prerequisites.sql | database/migrations/v4/0001_prerequisites.sql @ cd7ebfd51352 | none | 08e71b93c214e2172b9cb56611fb684bec33987bc768bd2bfc30aab317ded4b2 |
| 0002 | database/migrations/v4_runtime_candidate/0002_registries_core.sql | database/migrations/v4/0002_registries_core.sql @ cd7ebfd51352 | migration@20260901.001 | 05d8d491dddb11a87a7b3647ee5959453b9d7b368a90921fcd2c31d4611f7f55 |
| 0003 | database/migrations/v4_runtime_candidate/0003_market_context.sql | database/migrations/v4/0003_market_context.sql @ cd7ebfd51352 | migration@20260901.002 | fcc97c21136f01427f8421aed262394d583bfa3deaa062b639c18640e90cc4bd |
| 0004 | database/migrations/v4_runtime_candidate/0004_frozen_runtime.sql | database/migrations/v4/0004_frozen_runtime.sql @ cd7ebfd51352 | migration@20260901.003 | eed5c84d6b315756389eb265e1d1af94ec3f4defc286a728ec6edff1cbf177f3 |
| 0005 | database/migrations/v4_runtime_candidate/0005_evaluation.sql | database/migrations/v4/0005_evaluation.sql @ cd7ebfd51352 | migration@20260901.004 | 7e6b11c886bf69df3448d866001cc012856023d5756e0d38d3b818f5539e976e |
| 0006 | database/migrations/v4_runtime_candidate/0006_governance_audit.sql | database/migrations/v4/0006_governance_audit.sql @ cd7ebfd51352 | migration@20260901.005 | ea6561889e6eb405ce281f0bcac98e4cf1c05c910216ae9cca5a9bf014f286b6 |
| 0007 | database/migrations/v4_runtime_candidate/0007_security_rls.sql | database/migrations/v4/0007_security_rls.sql @ cd7ebfd51352 | migration@20260901.006 | f75b579fbc402de74e33f8fd1d5a3a6e670784ba8731a5854bd49d039d1274d8 |
| 0008 | database/migrations/v4_runtime_candidate/0008_views_projections.sql | database/migrations/v4/0008_views_projections.sql @ cd7ebfd51352 | migration@20260901.007 | 1264ab43d7f32e3f387aede6e537dbf3934c2dee6efbf9b7b8418d97bcbcece9 |
| 0009 | database/migrations/v4_runtime_candidate/0009_seed_and_smoke.sql | database/migrations/v4/0009_seed_and_smoke.sql @ cd7ebfd51352 | migration@20260901.008 | 3ee7af8c3b4357c87fcada758cfaefb283b319f328548103170090bd688fbdec |

## Candidate execution contract

1. The original database/migrations/v4/0001-0009 design files remain immutable design artifacts.
2. These files may be considered only by a disposable/local or explicitly approved staging runtime gate.
3. No candidate file contains a production connection directive, secret, project ID, or production apply path.
4. migration_hash remains PENDING_CANONICAL_HASH; the recorded byte hash is provenance evidence, not a canonical migration identity.
5. Candidate 0007 installs real fail-closed lineage, chronology, role/source separation, review, release, public projection, audit, trigger, and RLS gates.
6. Any production extension, role, namespace, view-security, audit-hash, or executor choice remains PRODUCTION_REVIEW_REQUIRED.

## Dependency graph

migration@20260901.001
  -> .002 -> .003 -> .004 -> .005 -> .006 -> .007 -> .008 -> .009

The graph is intentionally serial. No candidate is independently executable on a clean target.

## Review boundary

This manifest is not a production approval and does not change V4-018 or V4-019. It exists to make the next disposable runtime validation reproducible and auditable.
