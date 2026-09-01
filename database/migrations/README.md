# JCFB V4 Migration Design Directory

Status: V4-011 DESIGN-ONLY / DO NOT APPLY

This directory contains migration architecture artifacts, not an executable deployment bundle. Every SQL file in this directory begins with `DESIGN ONLY - DO NOT APPLY`. Do not pipe a file to `psql`, `supabase db query`, `supabase db push`, `apply_migration`, a CI job, or any other execution tool.

## Ordered files

| Sequence | File | Design purpose |
|---:|---|---|
| 0000 | `v4/0000_manifest.md` | Immutable manifest, dependencies, object scope, approval conditions |
| 0001 | `v4/0001_prerequisites.sql` | Extensions/namespaces/helper and migration registries; design only |
| 0002 | `v4/0002_registries_core.sql` | Model/engine registries and canonical core tables |
| 0003 | `v4/0003_market_context.sql` | Market snapshots, context, evidence, bundle lineage |
| 0004 | `v4/0004_frozen_runtime.sql` | Frozen Input, feature, runtime, Prediction, Frozen Prediction |
| 0005 | `v4/0005_evaluation.sql` | Results, reviews, Tier A, promotion, calibration |
| 0006 | `v4/0006_governance_audit.sql` | Release pointers, incidents, audit chain |
| 0007 | `v4/0007_security_rls.sql` | RLS, grants, validators, trigger design |
| 0008 | `v4/0008_views_projections.sql` | Safe Production projection and read views |
| 0009 | `v4/0009_seed_and_smoke.sql` | Static registry seed and smoke/acceptance design |

The design is a strict `0001 -> 0009` dependency order. A future executor must first pass `docs/V4_MIGRATION_PREFLIGHT.md`, obtain explicit Human Approver authorization, and record each immutable history row. A pending or missing migration hash blocks deployment.

## Identity and hash rules

Each file declares `migration_id`, `sequence`, `name`, `migration_version`, `depends_on`, `schema_contract_version`, `authored_at`, `migration_hash`, and `status`. Applied migrations are never edited or reused. The canonical hash is computed from canonical SQL bytes plus immutable metadata; deployment timestamps and status are excluded. Until canonicalization is actually performed, files use `PENDING_CANONICAL_HASH` and remain `DRAFT`.

## Security and rollback

Internal schemas/tables are private by default. `anon` and ordinary `authenticated` have no internal write grants. Public access is restricted to reviewed safe projections/views. `service_role` is server-side only. RLS, triggers, and grants are separate controls.

Before Production and with no retained data, an approved empty-target rollback may be possible in reverse dependency order. After Production acceptance, all fixes are forward migrations with new identities. Historical migration files, rows, frozen records, audit evidence, and V3.3.3 assets are not rewritten or deleted.

## Current boundary

No SQL in this directory has been executed. No database, Supabase project, model, Shadow run, Experiment, or Production release was touched by V4-011.
