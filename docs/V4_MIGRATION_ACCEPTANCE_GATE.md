# JCFB V4 Migration Acceptance Gate 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY; GATE NOT EXECUTED)

## 1. Acceptance rule

Only a migration chain that passes every required gate may be recorded as `APPLIED` and `ACCEPTED`. A missing, unknown, or failed gate is `BLOCKED`; “mostly passed” is not a deployment state.

The future acceptance record must bind the target identity, migration ID/version/hash, schema contract, executor, approver, auditor, test run, and evidence references. It must never contain a secret or be satisfied by a free-text assertion.

## 2. Required gates

| Gate | Minimum evidence | Pass condition |
|---|---|---|
| `PRECHECK_PASS` | Completed V4 preflight | All critical target, version, extension, namespace, role, backup, history, and secret checks pass |
| `DDL_APPLY_PASS` | Executor transaction result/catalog diff | Intended DDL committed atomically with no unrecorded partial state |
| `CONSTRAINT_PASS` | Constraint catalog and negative/positive tests | PK/FK/unique/check and same-match/revision constraints enforce the contract |
| `RLS_PASS` | Role/grant/policy catalog and caller-role tests | Internal tables deny anon/authenticated writes/reads by default; approved paths are explicit |
| `TRIGGER_PASS` | Trigger/function catalog and lifecycle tests | Append-only, frozen, lineage, source, role, time, Tier A, audit, and public gates fire in order |
| `VIEW_PASS` | View definitions, grants, and public projection tests | Six views are explicit-column, Production-only, safe, and `security_invoker` or approved fallback |
| `SMOKE_PASS` | All 20 smoke cases | Every required positive/negative behavior passes in isolated target |
| `ADVISOR_REVIEW_PASS` | Supabase/Postgres advisor output | Critical findings resolved; accepted INFO/exceptions documented |
| `NO_FUTURE_LEAKAGE_GATE_PASS` | Cutoff/kickoff/run/freeze/reference evidence | No future source/event/result enters a formal pre-match chain; invalid rows cannot qualify |
| `V333_ISOLATION_PASS` | Repository and catalog boundary diff | No V3.3.3 object/path/data/lineage is changed, copied, renamed, or exposed |
| `SECRET_SCAN_PASS` | Tracked/staged/repository scan | No key, token, password, cookie, service key, URL, or private credential appears |
| `MIGRATION_HISTORY_RECORDED` | Immutable `schema_migrations` row | Exact hash, actor, time, status, success, compatibility, notes, and chain evidence are recorded |

## 3. Status transition

```text
DRAFT
  -> APPROVED_FOR_DEPLOYMENT   only after design review and canonical hash
  -> APPLIED                   only after all required gates pass
  -> FAILED                    on an apply/gate failure; preserve evidence
  -> SUPERSEDED                only for an un-applied design replaced by a new identity
```

`APPLIED` and `ACCEPTED` are coupled for this design. No direct `status=APPLIED` update is allowed after the fact. If a post-acceptance defect is found, the outcome is an incident plus a new forward migration.

## 4. Security acceptance note

RLS is enabled on every V4 table, including private schemas as defense in depth. Internal tables may intentionally have no policies: after RLS is enabled and client grants are revoked, the absence of a policy keeps them private. This is an acceptable design choice and must be explicitly recorded in the final deployment report as `INTERNAL_NO_POLICY_PRIVATE=ACCEPTED`.

Public readers receive only reviewed safe-column/view access. `service_role` or an approved backend role is server-side and does not authorize browser access. A `SECURITY DEFINER` function is not used as a generic permission bypass; if one is ever required, fixed `search_path`, actor checks, and restricted `EXECUTE` grants are mandatory.

## 5. Advisor review checklist

The post-apply reviewer checks RLS/policy state, security-definer search paths, function execute grants, FK indexes, duplicate indexes, public exposure, security-invoker definitions, extension ownership, active Production uniqueness, and history/hash drift. Unused indexes are `INFO`; they are not automatically deleted.

## 6. Roles and approval

The Human Approver explicitly authorizes the first V4 migration. The Migration Executor applies only the exact approved immutable files. The Auditor independently verifies evidence. The same unattended agent cannot approve and execute a Production migration.

## 7. Current execution declaration

Acceptance gate executed in V4-011: **NO**. All target-dependent gates are design requirements, not claimed runtime evidence. No database write was performed. V4-011 is complete as a design artifact only; V4-012 is not started.
