# Changelog

## V4 Bootstrap

- Established V3.3.3 / V4 coexistence policy
- Defined V4 next-generation model positioning
- Added V3.3.3 architecture inventory
- Added master build checklist
- Added Codex/agent governance
- Initialized V4 engineering skeleton

## V4-006 Versioning Standard

## V4-007 Runtime Role Boundary

- Defined isolated PRODUCTION, SHADOW, and EXPERIMENT runtime roles and identities.
- Defined the same-frozen-input Forward A/B rule, pre-kickoff Shadow eligibility, and Experiment isolation.
- Defined Production uniqueness, strict Promotion Path, manual Promotion Gate, append-only rollback, Public Web isolation, Tier A eligibility, and the role-scoped access matrix.
- Added docs/V4_RUNTIME_ROLE_BOUNDARY.md, docs/V4_PRODUCTION_POLICY.md, docs/V4_SHADOW_POLICY.md, docs/V4_EXPERIMENT_POLICY.md, docs/V4_PROMOTION_PATH.md, and docs/V4_RUNTIME_ACCESS_MATRIX.md.

- Defined the auditable JCFB, model, engine, selector, config, schema, migration, dataset, Frozen, Shadow, and Experiment identities.
- Defined implementation, config, input, output, and Frozen Input hash boundaries.
- Defined compatibility, breaking-change, Promotion, Retirement, and release naming rules.
- Added `docs/V4_VERSIONING_STANDARD.md`, `docs/V4_VERSION_IDENTITY_CONTRACT.md`, `docs/V4_COMPATIBILITY_POLICY.md`, and `docs/V4_RELEASE_NAMING.md`.
- Added `scripts/validate_v4_versioning.ps1` and synchronized README, AGENTS, Constitution, architecture, model governance, integrity rules, and Checklist references.
