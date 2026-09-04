# JCFB V4 0009 PGCRYPTO SCHEMA FORWARD-FIX REPORT

## Decision

- **Candidate:** `migration@20260901.009` (`v4-seed-smoke`)
- **Fix identity:** `JCFB V4 0009 PGCRYPTO SCHEMA FORWARD-FIX 1.0`
- **Result:** `READY_FOR_PRODUCTION_REVIEW` on the fresh disposable target
- **Production Resume Scope:** `0009 ONLY`
- **Requires New Explicit Resume Approval:** `YES`
- **Production/Supabase writes during this repair:** `NO`
- **V4-018/V4-019 or BATCH-04 status changes:** `NO`

This report records a forward-only repair package. It does not approve,
connect to, or apply anything to Production.

## Incident provenance and immutable boundary

The operator-supplied Production state is: V4 `0001`-`0008` are `APPLIED`,
the prior `0009` attempt failed and rolled back without a history row, and
pgcrypto is installed by the provider in schema `extensions` with
`extensions.digest(bytea,text)` and `extensions.digest(text,text)` available;
`public.digest` is absent. The failure is recorded as:

- `failure_code`: `PGCRYPTO_SCHEMA_MISMATCH`
- `SQLSTATE`: `42883` (`UndefinedFunction`)
- `failed migration`: `migration@20260901.009`
- `transaction outcome`: `0009 FAILED AND ROLLED BACK; no history row`
- `unapplied suffix`: `migration@20260901.009`

Candidate SQL bytes, canonical hashes, and history identity for `0001`-`0008`
remain frozen. No file under `database/migrations/v4/` was changed, and no
V3.3.3 object or history was touched.

## Forward fix

The still-unapplied `0009` candidate replaces the existing
`governance.append_audit_event()` body before its first audited insert. The
digest call is explicitly `extensions.digest(...)`. The repair does not create
a `public.digest` wrapper, move pgcrypto, or alter the frozen `0001`-`0008`
candidate files or hashes.

The disposable bootstrap mirrors the provider layout by creating the
`extensions` schema, installing pgcrypto there, adding it to the disposable
database search path for frozen UUID defaults, and granting schema usage only
to the controlled local `service_role`. The runtime catalog records extension
name, version, schema, and installed state.

Because frozen `0007` installs its history audit trigger with the pre-fix body,
the disposable executor has a narrowly scoped local-only accommodation: while
recording the `0007` and `0008` history rows, it disables only
`v4_schema_history_audit_event` and re-enables it before each transaction
commits. This preserves the frozen SQL and lets `0009` apply its forward fix;
`0009` history and runtime data writes use the repaired trigger normally.
`SMOKE-16` is the executable audit-trigger gate.

## Fresh disposable validation

Validation was run after destroying the previous data directory and starting a
new project-scoped PostgreSQL 16.15 container with no migration history.

- **Run ID:** `prebatch04-20260904T033826Z-7bf0d60f620347fd925bdf1af94a17d4`
- **Target:** `DISPOSABLE_LOCAL` / `jcfb-v4-disposable-runtime`
- **pgcrypto:** version `1.3`, installed schema `extensions`
- **Canonical hash verification:** `9/9 PASS`
- **Migration history:** `9/9 PASS`, exact immutable prefix and chain
- **Smoke cases:** `20/20 PASS`
- **Enforcement cases:** `15/15 PASS`
- **Audit trigger execution:** `PASS` (`SMOKE-16`, audit row + trigger path)
- **Schema/security checks:** `PASS`
- **No-future-leakage, production uniqueness, frozen-input and Tier A gates:** `PASS`
- **Role simulation cleanup:** `PASS`
- **V3.3.3 objects after apply:** `0`
- **Staging readiness:** `READY_FOR_PRODUCTION_REVIEW`

The redacted runtime evidence is persisted under:

`.runtime/reports/prebatch04/runs/prebatch04-20260904T033826Z-7bf0d60f620347fd925bdf1af94a17d4/`

The run captured Git HEAD `aa59693621db29ea815f76da1afbcbb8928ee0f3` on
`main`, and the report pointer, JSON, Markdown, and repository HEAD were
verified by the read-only runtime evidence review. The working tree was
intentionally recorded as dirty because this implementation package was still
being assembled at capture time; a post-commit evidence run is required for
the final handoff snapshot.

## Approval boundary

This package is ready for a human Production review only. The next permitted
database action is a separately approved forward apply of
`migration@20260901.009` **only**. No `0001`-`0008` replay, history rewrite,
extension move, public wrapper, V4-018/V4-019 update, BATCH-04 closure, or
Production action is authorized by this report.
