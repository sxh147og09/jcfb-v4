# JCFB V4 RESERVED SERVICE_ROLE FORWARD-FIX REPORT

Status: `LOCAL CANDIDATE REPAIR COMPLETE; FRESH APPROVAL REQUIRED`

This document records the failed Production attempt and the repair of the
unapplied runtime candidate. It is not a Production approval, does not authorize
BATCH-04, and does not change V4-018 or V4-019.

## Failed Production attempt

| Field | Result |
|---|---|
| Production project_ref | `icndieflfvydixtehgzu` |
| Approved/actual HEAD at attempt | `ca0e1899b983867b67ca67c3589ab38c4cd65a42` |
| Failure type | `RESERVED_ROLE_MUTATION` |
| Failed migration | `0001 v4_prerequisites` |
| Database error | `ERROR: "service_role" is a reserved role, only superusers can modify it` |
| Failed statement | `ALTER ROLE service_role BYPASSRLS` |
| Transaction result | 0001 rolled back inside its own transaction |
| 0002-0009 | NOT RUN |
| Production partial apply | `NONE` |
| Production migration history changed | `NO`; the nine pre-existing V3.3.3 rows remain unchanged |
| Production/Supabase committed writes during attempt | `NO` |

The read-only role-state verification recorded the following baseline:

- `service_role`: `rolsuper=false`, `rolbypassrls=true`, `rolcanlogin=false`,
  `rolcreaterole=false`, `rolcreatedb=false`.
- `anon`: `rolbypassrls=false`.
- `authenticated`: `rolbypassrls=false`.
- `postgres`: `rolbypassrls=true`.

The root cause was an unnecessary migration-time mutation of a provider-managed
reserved role. The platform already supplied the required capability, so the
mutation was both redundant and incompatible with the provider policy.

## Forward-fix contract

Candidate `database/migrations/v4_runtime_candidate/0001_prerequisites.sql`
now performs a verification-only prerequisite:

1. It requires `service_role` to already exist.
2. It requires `pg_catalog.pg_roles.rolbypassrls = true`.
3. It raises an explicit prerequisite error and rolls back if either condition
   is false.
4. It rejects `anon` or `authenticated` when either has `rolbypassrls = true`.
5. It contains no `ALTER ROLE service_role`, `CREATE ROLE service_role`, or
   `SET ROLE service_role` operation.

The disposable Docker initialization file
`database/runtime/0000_service_role.sql` is deliberately outside the migration
candidate. On a new local disposable data directory it provisions a no-login
compatibility role with `BYPASSRLS`; candidate 0001 then verifies that state. The
file is mounted read-only by the disposable compose configuration and is not a
Supabase, staging, or Production patch.

## Canonical hash impact

The canonical SHA-256 profile was rerun after the SQL revision. The 0009 change
is required because its static registry seed embeds every candidate hash.

| Candidate | Previous canonical hash | New canonical hash | Change reason |
|---|---|---|---|
| 0001 | `sha256:c55c6d4a882691d9dc006d55915e8584a696de1c9fd9792243c0b0c50713bb28` | `sha256:1b959f089bc3f46e272ee7edc19b6a9665c78b4067cdad470a3ebc98a513f2bb` | Verification-only service_role prerequisite |
| 0009 | `sha256:56c0ad2da49d0a169c080eca023a5a54af4c2089565c244fec5d88301bfd6448` | `sha256:009467fa464f08457ade762500245918bb7ac251077c5b2ec0b539ca981aadb7` | Dependent registry seed embeds the new 0001 hash |

Candidates `0002` through `0008` retained their canonical hashes. The JSON and
Markdown manifests, both 0001/0009 SQL headers, and the 0009 registry seed were
regenerated and verified together.

## Validation boundary

- Reserved-role regression tests cover pass, false, missing, public-role
  invariants, candidate mutation scans, and the separate disposable bootstrap.
- Runtime role simulation now fails closed for a missing service-role capability
  or a public-role bypass invariant violation.
- Docker/PostgreSQL runtime validation: `NOT RUN IN CODEX` by explicit task rule.
- Production/Supabase writes during this forward-fix: `NO`.
- V3.3.3 objects/history: unchanged.
- V4-018/V4-019: unchanged.
- BATCH-04: not executed and not completed.

## Required fresh approval chain

The candidate hash change invalidates the previous approval chain. Before any
second Production Apply, the operator must complete all of the following on the
new Git HEAD: (A) new HEAD review; (B) fresh disposable destroy/start; (C)
0001-to-0009 runtime validation; (D) 20/20 smoke and 15/15 enforcement; (E) Git
HEAD match; (F) refreshed Supabase Preflight/Final Review; and (G) explicit human
approval for the second Production Apply.
