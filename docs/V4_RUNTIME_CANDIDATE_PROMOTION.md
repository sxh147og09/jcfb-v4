# JCFB V4 Runtime Candidate Promotion 1.0

## Scope and boundary

This document records the Pre-BATCH-04 remediation Track A. It creates a
separate disposable/staging execution package from the approved V4 migration
design artifacts. It does not promote the design migrations to production and
does not consume a new V4 task ID.

- Task: JCFB V4 PRE-BATCH-04 REMEDIATION — DISPOSABLE RUNTIME ENABLEMENT 1.0
- Candidate directory: database/migrations/v4_runtime_candidate/
- Candidate count: 9/9
- Allowed runtime identities: DISPOSABLE_LOCAL, explicitly approved STAGING
- Production apply: HARD_BLOCK
- V4-018/V4-019: unchanged and not completed
- V3.3.3: unchanged and isolated

## Source and provenance

The original files under database/migrations/v4/0001_*.sql through
0009_*.sql remain design-only artifacts. Each candidate has a one-to-one
sequence, source design file, source design commit, candidate identity, and
dependency metadata. The JSON and Markdown manifests are:

- database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.json
- database/migrations/v4_runtime_candidate/0000_runtime_candidate_manifest.md

The recorded content_sha256_noncanonical values are byte-level provenance
evidence only. The canonical migration hashes are generated with the approved
`v4-canonical-migration@1.0.0` / SHA-256 profile and are still evidence, not
Production approval.

## Runtime-safe determinations

The candidates resolve only decisions needed to make a fresh disposable
PostgreSQL target executable and testable:

1. The session timezone is UTC.
2. pgcrypto is installed in the provider-compatible local `extensions`
   namespace. The disposable database search path includes `extensions` so
   frozen UUID defaults remain resolvable.
3. The disposable container bootstrap provisions a local compatibility
   `service_role` without a password. Candidate 0001 verifies that the role
   exists with `rolbypassrls = true`, verifies that `anon` and `authenticated`
   do not bypass RLS, and fails closed without creating or altering the
   provider-owned role. A missing or false `service_role` capability is not
   repaired by the migration.
4. Fresh local no-login public and V4 roles are created without passwords; the
   runtime case adapter may create only its minimal local backend fixtures and
   grant their disposable memberships.
5. The V4 namespaces are created on a fresh local target.
6. Candidate 0007 contains fail-closed implementations for chronology,
   frozen-input lineage, role/source separation, review/release scope,
   append-only mutation, public projection, audit, triggers, and RLS.
7. Candidate 0009 contains registry/acceptance metadata only; it does not seed
   business matches, odds, predictions, or results.
8. The 0009 pgcrypto schema forward-fix replaces the still-unapplied
   `governance.append_audit_event()` body before its first audited seed insert
   and calls `extensions.digest(...)` explicitly. It records the prior
   `SQLSTATE 42883` / `PGCRYPTO_SCHEMA_MISMATCH` provenance and is resumable only
   as `0009 ONLY` after new explicit approval.

Production extension availability, role mapping and ownership, namespace
coexistence, security_invoker support, audit hash profile, release executor,
and reconciliation of the existing schema snapshot with governance history
remain PRODUCTION_REVIEW_REQUIRED. They are not silently decided here.

## Static acceptance performed

scripts/validate_v4_runtime_candidates.ps1 checks the complete sequence,
manifest graph, provenance, pending-hash marker, transaction shape, dollar
quoting balance, forbidden connection/apply paths, required security objects,
original design markers, V3.3.3 isolation, and the repository Secret Scan.

The validator passed all checks. PostgreSQL parsing and the 35 runtime cases
were not run because this Windows host currently has no Docker, Docker daemon,
psql, or listening PostgreSQL service. That remains the separate
BLOCKED_ENV_SETUP_REQUIRED condition.

## Next gate

After a user installs and starts Docker Desktop, the local wrapper in
scripts/v4_disposable_runtime.ps1 may create the localhost-only disposable
runtime. Only then may a separately approved Pre-BATCH-04 Runtime Validation
Gate apply these candidates to that disposable target. This package contains
no production connection path and does not execute BATCH-04.
