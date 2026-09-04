# JCFB V4 Runtime Candidate Manifest 1.0

- Status: RUNTIME VALIDATION CANDIDATE
- Scope: DISPOSABLE/STAGING ONLY
- Production apply: HARD BLOCK
- Source manifest: database/migrations/v4/0000_manifest.md at cd7ebfd5135275536c2d54ca1ecd980bb386dcfa
- Promotion source commit: 1e907c7490b5e102dea69372f22073ef3970ca6a
- Canonical migration hashes: GENERATED_CANONICAL_HASHES
- Canonicalization: v4-canonical-migration@1.0.0 / SHA-256 / v4-canonical-json@1.0

## Candidate sequence

| Sequence | Candidate | Source design | Depends on | Byte hash (non-canonical) | Canonical migration hash |
|---:|---|---|---|---|---|
| 0001 | database/migrations/v4_runtime_candidate/0001_prerequisites.sql | database/migrations/v4/0001_prerequisites.sql @ cd7ebfd51352 | none | 6ea852a6924082767912a46b8859a7610828835273f0f6fb01fe4893f6c63511 | sha256:1b959f089bc3f46e272ee7edc19b6a9665c78b4067cdad470a3ebc98a513f2bb |
| 0002 | database/migrations/v4_runtime_candidate/0002_registries_core.sql | database/migrations/v4/0002_registries_core.sql @ cd7ebfd51352 | migration@20260901.001 | c85cfae6c1fe7aba3e1bf05be794ec43d5adb47d055dd7db89c0e1f816257504 | sha256:7edfc9c4c2c0085f63d0e0860f0d2f74f6a1e85d9b1ac4e602571347e5dd332a |
| 0003 | database/migrations/v4_runtime_candidate/0003_market_context.sql | database/migrations/v4/0003_market_context.sql @ cd7ebfd51352 | migration@20260901.002 | 9b621fd38c6030f9b73e45a944a787bd214e1585e231ce7cbe3e1a79b7642881 | sha256:dc493407c012e1296b884ab64eaa251ee6b32fff6c0a9d5cacfe4860098db808 |
| 0004 | database/migrations/v4_runtime_candidate/0004_frozen_runtime.sql | database/migrations/v4/0004_frozen_runtime.sql @ cd7ebfd51352 | migration@20260901.003 | 3339d35a37d92eca4ca76bf0a42ae02deac5fcf8ed8a190a0a5830bf48140751 | sha256:660e64c210a370ac2e9d2ab13f7ac08b784caa0821df1ad0c4c81db7457ff7bb |
| 0005 | database/migrations/v4_runtime_candidate/0005_evaluation.sql | database/migrations/v4/0005_evaluation.sql @ cd7ebfd51352 | migration@20260901.004 | da6658b3e665f085c3968c3010ccfa0e17211824fdd28523faaa49aa750b4e81 | sha256:b4c5b6a276b42117a0dd830c56c8a8856f273c13016bf200838ba690b5e80394 |
| 0006 | database/migrations/v4_runtime_candidate/0006_governance_audit.sql | database/migrations/v4/0006_governance_audit.sql @ cd7ebfd51352 | migration@20260901.005 | 1ba475b2585f3f25d4984f82e2c7e8a94c815f47ff91a2d4728707adc9ee71b8 | sha256:85386b242f6f1ef8fabd1aa09b07f1b4c3082b589b0c6c320bb9705883a5a52d |
| 0007 | database/migrations/v4_runtime_candidate/0007_security_rls.sql | database/migrations/v4/0007_security_rls.sql @ cd7ebfd51352 | migration@20260901.006 | 367c0b4d52d84e60bca6c1bee797a45f5fc7ea769cf21508efacf9cb2a6978c3 | sha256:952ae622fba16f831389b8bfd3b0bfa05b6278f721c41c768532f37d6178a4b0 |
| 0008 | database/migrations/v4_runtime_candidate/0008_views_projections.sql | database/migrations/v4/0008_views_projections.sql @ cd7ebfd51352 | migration@20260901.007 | dc19e7a76839b2b2fd594f3c871d8340b4231fd4d9defb9dc6eb7f592012ca48 | sha256:f2ddf1fd7a69e38bc224c5e19c8db08824d76a6f566eae9fa722a52c644584e3 |
| 0009 | database/migrations/v4_runtime_candidate/0009_seed_and_smoke.sql | database/migrations/v4/0009_seed_and_smoke.sql @ cd7ebfd51352 | migration@20260901.008 | 57e0e3a0bf7b0d0e83f671c8caded6ffb0544568cdc81c9328cddfbcf1583132 | sha256:e4c96f434a8359b54e397f209e565b94162a01037c1cf91e9bd96bf0b948bc20 |

## Candidate execution contract

1. The original database/migrations/v4/0001-0009 design files remain immutable design artifacts.
2. These files may be considered only by a disposable/local or explicitly approved staging runtime gate.
3. No candidate file contains a production connection directive, secret, project ID, or production apply path.
4. `canonical_migration_hash` and `migration_hash` are generated SHA-256 identities; the recorded byte hash remains separate provenance evidence.
5. Canonical SQL uses UTF-8, LF line endings, strips horizontal trailing whitespace per line, emits exactly one final LF, and preserves SQL tokens, comments, internal whitespace, statement order, and dollar-quoted bodies. The self-hash fields are normalized only during digest calculation and are still verified against the manifest.
6. Stable metadata input is `migration_id`, `sequence`, `name`, `migration_version`, `depends_on`, `schema_contract_version`, `authored_at`, and the repository-relative candidate file path. Apply timestamps, actor, host, duration, and lifecycle status are excluded.
7. Candidate 0001 verifies a pre-existing service_role with `rolbypassrls=true` and fails closed; it never creates or alters the provider-owned role. The disposable container bootstrap is the only local compatibility-role provisioner.
8. Candidate 0007 installs real fail-closed lineage, chronology, role/source separation, review, release, public projection, audit, trigger, and RLS gates.
9. Any production extension, role, namespace, view-security, audit-hash, or executor choice remains PRODUCTION_REVIEW_REQUIRED.

## Dependency graph

migration@20260901.001
  -> .002 -> .003 -> .004 -> .005 -> .006 -> .007 -> .008 -> .009

The graph is intentionally serial. No candidate is independently executable on a clean target.

## 0009 pgcrypto schema forward-fix provenance

- Forward-fix identity: `JCFB V4 0009 PGCRYPTO SCHEMA FORWARD-FIX 1.0`
- Base HEAD reviewed: `aa59693621db29ea815f76da1afbcbb8928ee0f3`.
- Partial apply state: `0009_FAILED_ROLLED_BACK`; Production has the exact
  applied prefix `0001` through `0008`, and 0009 has no history row.
- Failed candidate: `0009`; the first audited registry seed insert raised
  `SQLSTATE 42883` (`PGCRYPTO_SCHEMA_MISMATCH`) because the frozen 0007 audit
  function called `public.digest(...)` while Production exposes pgcrypto under
  `extensions`.
- Forward repair: 0009 replaces the still-unapplied
  `governance.append_audit_event()` body and calls `extensions.digest(...)`
  explicitly. No `public.digest` wrapper is created and the extension is not
  moved.
- 0001–0008 canonical hashes and SQL bytes: frozen. Only 0009 and its embedded
  registry seed value are regenerated after this repair.
- Disposable bootstrap: pgcrypto is installed in `extensions` before 0001 and
  the database search path includes that schema so frozen UUID defaults resolve
  as they do on the production-like target.
- Resume scope after independent approval: `0009 ONLY`.
- New explicit resume approval: `YES`.

## Review boundary

This manifest is not a production approval and does not change V4-018 or V4-019. It exists to make the next disposable runtime validation reproducible and auditable.
