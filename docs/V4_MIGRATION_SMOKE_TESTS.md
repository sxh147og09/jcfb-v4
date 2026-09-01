# JCFB V4 Migration Smoke Tests 1.0

Status: V4-011 COMPLETE (DESIGN-ONLY; TESTS NOT RUN)

## 1. Test boundary

These are future tests for a disposable/local/staging PostgreSQL target after an approved migration. They are not executed in V4-011. The harness must use isolated data, real `anon`, `authenticated`, `service_role`/backend, executor, and auditor caller contexts, and must roll back or destroy the disposable target after evidence capture. No smoke test may use a V3.3.3 table or payload.

Every test records migration identity, schema contract version, target identity, caller role, test transaction ID, expected result, actual result, and evidence hash. A failed test blocks `SMOKE_PASS`.

## 2. Required smoke matrix

| # | Scenario | Expected result | Gate/evidence |
|---:|---|---|---|
| 1 | Insert a valid `core.matches` record with source, timestamps, hashes, distinct home/away, and a canonical business key | Insert succeeds and an audit event is attributable | `CONSTRAINT_PASS`, `MIGRATION_HISTORY_RECORDED` |
| 2 | Insert a duplicate `(data_date, official_match_no)` | Unique business-key constraint rejects the write; no second canonical match exists | `CONSTRAINT_PASS` |
| 3 | Insert an official snapshot where a market is explicitly unavailable with a reason | Snapshot is accepted with `UNAVAILABLE`; that market payload is absent | `CONSTRAINT_PASS`, `TRIGGER_PASS` |
| 4 | Mark an official market available while omitting its payload | Write is rejected or stored only as `BLOCKED`; no fabricated payload is accepted | `TRIGGER_PASS` |
| 5 | Mark `rqspf` available while omitting the required handicap line | Write is rejected/blocked; no RQSPF selection is created | `TRIGGER_PASS` |
| 6 | Insert or complete a Production Engine Run after kickoff | Rejected or retained as `INVALID`; it is not Tier A or promotion eligible | `NO_FUTURE_LEAKAGE_GATE_PASS` |
| 7 | Update a Frozen Input after `immutable=true`/`FROZEN` | RLS/grant and immutability trigger reject the mutation | `TRIGGER_PASS` |
| 8 | Update or delete a Frozen Prediction | Both operations reject, including a no-op update | `TRIGGER_PASS` |
| 9 | Correct an official result | A new result revision with predecessor/reason/evidence is required; old row is unchanged | `CONSTRAINT_PASS`, audit evidence |
| 10 | Create a review whose Result and Frozen Prediction have different `match_id` values | FK/lineage trigger rejects or records `BLOCKED`; no review is valid | `CONSTRAINT_PASS` |
| 11 | Register a Tier A pair whose Production and Shadow rows have different `frozen_input_hash` | Pair rejects or is permanently ineligible; `tier_a_eligible=false` | `Tier A pair integrity` |
| 12 | Use an `EXPERIMENT` Prediction/Frozen Prediction as a forward Tier A member | Write rejects or becomes `BLOCKED`; Experiment never qualifies | `ROLE_VIOLATION` |
| 13 | Try to publish a Shadow or Experiment row through a public projection | Projection trigger rejects; public views return no such row | `VIEW_PASS`, role isolation |
| 14 | Activate two Production revisions for one family/channel | Partial unique index/activation function rejects the second active pointer | `CONSTRAINT_PASS` |
| 15 | Use `anon` and ordinary `authenticated` to write an internal table | Grant/RLS denies with expected privilege failure (`42501` where applicable) | `RLS_PASS` |
| 16 | Use the approved service/backend writer on a valid controlled path | Valid write succeeds only through reviewed grants/functions; critical triggers still run | `RLS_PASS`, `TRIGGER_PASS` |
| 17 | Inspect every `SECURITY DEFINER` function, if any | No unapproved definer exists; each has fixed `search_path`, actor check, and restricted `EXECUTE` | `ADVISOR_REVIEW_PASS` |
| 18 | Change source business timestamps without changing page/build time | `canonical_latest_update_at` equals the maximum real Prediction/Frozen/Odds/Context/Result/Review business time | `VIEW_PASS` |
| 19 | Perform intake, freeze, run, result, review, Tier A, promotion, incident, and publication lifecycle events | Critical events create audit entries with actor/action/entity/before/after/time/prev/entry hash | `TRIGGER_PASS`, audit evidence |
| 20 | Compare V3.3.3 repository/database boundary before and after the run | No V3.3.3 path, table, row, parameter, output, result, review, sample, or audit history changes | `V333_ISOLATION_PASS` |

## 3. Advisor review design

After smoke data is loaded, the future advisor review must report:

- RLS enabled/forced state and policy status for every table;
- every `SECURITY DEFINER` function, its fixed `search_path`, owner, actor check, and `EXECUTE` grants;
- FK columns without supporting indexes;
- duplicate, overlapping, or redundant indexes;
- public schema/table/view exposure and safe-column grants;
- `security_invoker` view definitions and underlying safe grants;
- unused indexes as `INFO` only; no automatic deletion;
- extension ownership/version and migration-history drift;
- active Production partial-unique predicates and trigger coverage.

An advisor warning is not automatically a failure when a documented, approved exception exists. A critical security or integrity finding is always `BLOCKED` until remediated or formally accepted by the Human Approver and Auditor.

## 4. Execution declaration

Tests run in V4-011: **NO**. No database connection, SQL execution, test seed, model run, Shadow run, or Production write occurred.
