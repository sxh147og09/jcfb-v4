# JCFB V4 Supabase Preflight Plan Completion 1.0

Status: `SUPABASE PREFLIGHT PLAN PASS` / `NO PRODUCTION WRITE`

Scope: `JCFB_V4_SUPABASE_PREFLIGHT_PLAN_COMPLETION`

V4-011 vocabulary compatibility: legacy critical IDs `PF-01` through
`PF-18` remain reserved for the original deployment-preflight surface. In
this completion plan, `PF-01` (target project identity) and `PF-18`
(production release state) are represented by the target binding,
apply-before checklist, and final-review separation below. The legacy
`target_project_identity` output name remains an identity-evidence label;
`NOT_RUN` is not a pass, and any live check that has not been recaptured is
still an apply blocker.

Machine-readable contract: [`config/migration_harness/v4_supabase_preflight_plan.json`](../config/migration_harness/v4_supabase_preflight_plan.json)

Machine validator: [`scripts/validate_v4_supabase_preflight.ps1`](../scripts/validate_v4_supabase_preflight.ps1)

The Production target identity is known from the separately approved binding
[`config/migration_harness/v4_production_target_identity.json`](../config/migration_harness/v4_production_target_identity.json):

```text
provider: Supabase
project_ref: icndieflfvydixtehgzu
region: us-west-2
postgres major: 17
binding_state: BOUND_APPROVED
```

This document completes the repository preflight plan from the previously
supplied connected Supabase read-only baseline. It does not connect to
Supabase, execute SQL, apply a migration, modify a V3.3.3 object, execute
BATCH-04, or grant Production apply permission. `PASS` means that the plan,
baseline contract, comparison rules, recovery rules, and verification plan
are complete and can feed the independent Final Readiness Review. It does not
mean that Production apply is allowed.

## 1. Production baseline snapshot

The baseline is recorded without credentials or connection material.

| Field | Captured value |
|---|---|
| Provider | `Supabase` |
| Project ref | `icndieflfvydixtehgzu` |
| Region | `us-west-2` |
| Database identity | `postgres` |
| PostgreSQL server version | `17.6` |
| PostgreSQL major | `17` |
| Captured at | `UNKNOWN_SUPPLIED_BASELINE_TIME` (the reference did not include a timestamp) |
| Capture source | `connected Supabase read-only inspection` |
| Production/Supabase writes in this task | `NO` |

The unknown timestamp is explicit rather than invented. `APPLY-02` through
`APPLY-05` require a fresh, attributable recapture immediately before any
future apply decision.

### 1.1 Existing migration history

The current Production history is a nine-row V3.3.3-era baseline. It is not
the V4 `0001 -> 0009` sequence. Before apply, the exact version/name sequence
must be recaptured; any drift is `BLOCK_UNLESS_EXPLICITLY_REVIEWED`.

| Ordinal | Version | Name |
|---:|---|---|
| 1 | `20260831064909` | `jcfb_v3_3_3_central_data_schema_1_0` |
| 2 | `20260831064938` | `jcfb_v3_3_3_schema_1_0_security_hardening` |
| 3 | `20260831064955` | `jcfb_v3_3_3_schema_1_0_fk_indexes` |
| 4 | `20260831065135` | `jcfb_v3_3_3_central_data_schema_1_1` |
| 5 | `20260831065552` | `jcfb_v3_3_3_official_odds_ingestion_gate_1_0` |
| 6 | `20260831070156` | `jcfb_v3_3_3_official_screenshot_intake_1_0` |
| 7 | `20260831073246` | `jcfb_v3_3_3_shadow_execution_provenance_guard_1_0` |
| 8 | `20260831074714` | `historical_tier_a_recovery_quarantine_1_0` |
| 9 | `20260831080846` | `jcfb_v3_3_3_forward_tier_a_collection_1_0` |

### 1.2 Existing public schema counts

| Object group | Baseline count |
|---|---:|
| Public tables | 20 |
| Public views/materialized views | 11 |
| Public functions | 18 |
| Public RLS-enabled tables | 20 |
| Public non-internal triggers | 38 |

The supplied baseline identifies the current objects as V3.3.3-era objects,
including model versions, matches, odds snapshots, predictions, frozen
predictions, Tier A samples, screenshot intake, shadow/forward Tier A objects,
and audit logs. The contract retains named identity samples rather than
inventing names for objects that were not present in the supplied evidence.
The named view identities are:

```text
public.v_canonical_latest_update
public.v_current_frozen_predictions
public.v_forward_tier_a_progress
public.v_historical_tier_a_recovery_status
public.v_latest_odds_snapshots
public.v_odds_ingestion_gate_status
public.v_public_latest_odds
public.v_public_predictions
public.v_screenshot_intake_status
public.v_shadow_run_latest
public.v_tier_a_progress
```

The baseline identity sample is intentionally marked
`PARTIAL_NAMED_IDENTITIES_FROM_SUPPLIED_BASELINE`. Counts are not treated as
identity evidence. A complete `pg_catalog`/`information_schema` identity
recapture is mandatory before apply.

### 1.3 0008 public-view collision decision

The V4 runtime candidate does not claim any of the unprefixed public view names
above. The supplied `public.v_public_predictions` definition is a V3.3.3 view
over the legacy `public` data surface, while the V4 intended definition reads
the V4 `public_read_projections` ledger; its semantics, columns, source
lineage, `security_invoker` contract, and grants are not equivalent. The other
known name collisions are likewise unproven from the supplied baseline and are
not eligible for implicit reuse.

The forward-fix therefore creates these V4-owned names only:

```text
public.v4_public_predictions
public.v4_public_latest_odds
public.v4_current_frozen_predictions
public.v4_canonical_latest_update
public.v4_tier_a_progress
public.v4_model_registry_public
```

No V3.3.3 view is dropped, replaced, renamed, or granted new permissions by
0008. An equivalent pre-existing view may be reused only after an exact
definition, `security_invoker`, and grant assertion; an incompatible collision
is fail-closed and requires an explicit V4-owned name.

## 2. Apply-before mandatory checklist

Every item below is a blocking gate. The checked-in plan records the required
assertion and evidence reference; it does not fabricate a future recapture.

| ID | Mandatory assertion | Evidence | Failure action |
|---|---|---|---|
| APPLY-01 | Verify `project_ref` is exactly `icndieflfvydixtehgzu`. | baseline target identity | `BLOCK` |
| APPLY-02 | Verify database identity is `postgres`, server version is `17.6`, and major is `17`. | read-only database identity/version | `BLOCK` |
| APPLY-03 | Recapture all nine existing history rows and require exact version/name equality unless drift is explicitly reviewed. | migration history | `BLOCK` |
| APPLY-04 | Recapture complete schema object identities and compare names, types, definitions, constraints, RLS, grants, policies, view security, functions, and triggers. | schema identity catalog | `BLOCK` |
| APPLY-05 | Recapture Supabase Security and Performance advisors and compare stable baseline fingerprints. | advisor before/after evidence | `BLOCK` |
| APPLY-06 | Verify current Git HEAD equals the approved runtime-evidence HEAD. | runtime evidence Git identity | `BLOCK` |
| APPLY-07 | Verify the nine runtime-candidate canonical hashes are `9/9 PASS`; do not rewrite hashes. | runtime-candidate manifest | `BLOCK` |
| APPLY-08 | Verify the Production hard block remains closed and no apply approval has been inferred from binding or preflight. | Production apply gate | `BLOCK` |
| APPLY-09 | Verify the independent Final Review is complete before any explicit apply approval is considered. | Final Review record | `BLOCK` |

`APPLY-06` is a live identity check, not a value that can be copied from an
older report. The latest local runtime evidence must be recaptured after the
approved source commit is fixed; an old evidence HEAD is not silently accepted.

## 3. Schema baseline and diff contract

The machine contract uses the identity tuple:

```text
(object_kind, schema, name)
```

Where the catalog supplies them, definition/property signatures are compared
after the identity match. The following rules apply:

1. Compare object identities and properties, not only aggregate counts.
2. Detect missing, extra, changed, malformed, and unexpected pre-existing
   objects before apply. Unknown or incomplete identity evidence blocks apply.
3. After apply, classify `PRESERVED_V3_3_3`, `V4_ADDED`, `V4_CHANGED`,
   `MISSING_PRE_EXISTING`, `CHANGED_PRE_EXISTING`, and `UNEXPECTED_ADDED`
   separately.
4. The V4 expected catalog is sourced from
   `config/migration_harness/v4_schema_snapshot_contract.json`; it is not
   compared directly against the V3.3.3 baseline as if the baseline were
   empty.
5. V3.3.3 tables, views, functions, and triggers remain unchanged. The current
   compatibility-change manifest is empty. Any compatibility change requires
   an explicit migration-manifest declaration and independent review.
6. No object is auto-dropped, rewritten, renamed, disabled, or repaired by
   this preflight validator.

The comparison helpers are in
`tools/migration_harness/supabase_preflight.py`:
`compare_schema_object_identities` detects pre-existing drift and
`classify_post_apply_schema` separates V3.3.3 preservation from V4 additions.

## 4. Advisor before/after contract

Every baseline finding has a stable fingerprint derived from the canonical
JSON of `advisor`, `code`, `severity`, `scope`, `object_identity`, `role`, and
`attribution`. The baseline attribution is
`PRE_EXISTING_V3_3_3_DEBT`.

### Security advisor baseline

| Finding | Severity | Identity/scope | Policy |
|---|---|---|---|
| `rls_enabled_no_policy` | INFO | all/most internal tables | Track as baseline; do not auto-fix |
| `security_definer_view` | ERROR | `public.v_shadow_run_latest` | Track as V3.3.3 debt; do not modify |
| `anon_security_definer_function_executable` | WARN | `public.rls_auto_enable()` / `anon` | Track as V3.3.3 debt; do not modify |
| `authenticated_security_definer_function_executable` | WARN | `public.rls_auto_enable()` / `authenticated` | Track as V3.3.3 debt; do not modify |

The V4 rule is zero new V4-attributable Security `ERROR`/`WARN` findings and
no worsening or unreviewed change to the pre-existing baseline. The
`v_shadow_run_latest` and `rls_auto_enable()` findings remain V3.3.3 debt and
are not fixed by this task.

### Performance advisor baseline

| Finding | Identity |
|---|---|
| Unindexed foreign key | `forward_shadow_outputs.frozen_prediction_id` |
| Unindexed foreign key | `forward_tier_a_epochs.production_model_version_id` |
| Unindexed foreign key | `forward_tier_a_epochs.shadow_model_version_id` |
| Unused-index INFO findings | multiple existing V3.3.3 tables |

The preflight does not remove unused indexes or add unrelated indexes. New
high-impact performance regressions block. New INFO findings are
`REVIEW_REQUIRED_NO_SILENT_REGRESSION`; they are never silently discarded.

The before/after helper returns `PASS`, `REVIEW_REQUIRED`, or `BLOCKED` and
retains preserved, new, and missing-baseline finding sets.

## 5. Partial apply detection

The expected V4 sequence is strictly serial:

```text
0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 -> 0007 -> 0008 -> 0009
```

Each committed step must be recorded atomically with its canonical migration
identity in `governance.schema_migrations` (or the governed migration-history
registry for the target adapter). A row with `APPLYING`, `FAILED`, `PARTIAL`,
`BLOCKED`, or `partial_state=true`, a duplicate step, a gap, or an out-of-order
step enters `FORWARD_FIX_REQUIRED` and stops further execution.

The validator never fabricates a missing history row and never repairs an
applied history row manually. A clean prefix that is not yet complete is also
`PARTIAL_APPLY_STOP_REQUIRED`; the next migration is not run automatically.

## 6. Forward-fix and recovery contract

- Applied migration files and history rows are immutable.
- There is no historical rollback rewriting.
- Use one transaction per safe migration where the target supports it.
- Irreversible DDL must be identified and reviewed before approval.
- On uncertainty, stop, preserve the observed state, reconcile by read-only
  inspection, record the incident/partial state, and design a new forward
  migration identity.
- A rollback is allowed only for a separately approved, proven,
  transactionally reversible empty-target operation; it never rewrites history
  and never affects V3.3.3.

## 7. Post-apply mandatory verification plan

The following fourteen checks are required after any future approved apply;
each failure blocks acceptance:

| ID | Verification |
|---|---|
| POST-01 | Schema diff and object identity classification |
| POST-02 | Migration history and atomic step records |
| POST-03 | RLS and grants for all exposed/internal surfaces |
| POST-04 | `security_invoker` view behavior |
| POST-05 | Function owner, `SECURITY DEFINER`, fixed `search_path`, and execute exposure |
| POST-06 | Triggers, append-only rules, and Frozen Input/Prediction immutability |
| POST-07 | Production uniqueness and one active canonical revision |
| POST-08 | No-future-leakage and cutoff/kickoff boundaries |
| POST-09 | Tier A pair integrity and same-frozen-input rule |
| POST-10 | Canonical latest update uses business timestamps, not page build time |
| POST-11 | Public projection isolation and role boundary |
| POST-12 | V3.3.3 isolation and unchanged legacy identities |
| POST-13 | Supabase Security advisor before/after comparison |
| POST-14 | Supabase Performance advisor before/after comparison |

## 8. Human approval separation

The gates are intentionally separate:

```text
Target Binding Approval (BOUND_APPROVED)
        != Production Apply Approval

Supabase Preflight Plan (PASS)
        != Production Apply Approval

Final Review decision (READY_FOR_PRODUCTION_APPLY_APPROVAL)
        -> explicit human apply approval still pending
```

Only an explicit Human Approver decision after the Final Review may open the
Production apply gate. The checked-in state remains:

```text
hard_block_preserved = true
explicit_approval_required = true
target_binding_authorizes_apply = false
approval_state = PENDING_PRODUCTION_APPLY_APPROVAL
production_apply_allowed = false
```

## 9. Validation boundary and commands

The following validations are repository-only/read-only:

```powershell
Set-Location F:\Projects\jcfb-v4
python -m tools.migration_harness --repo-root . supabase-preflight
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate_v4_supabase_preflight.ps1 -RepoRoot F:\Projects\jcfb-v4
python -m tools.migration_harness --repo-root . production-readiness
```

The canonical hash command is verification-only in this task:

```powershell
python -m tools.migration_harness --repo-root . canonical-hash
```

No `--write` hash maintenance operation is part of this completion. The
Production target binding validator remains required and must continue to
pass.

## 10. Completion disposition

```text
Production Target Identity: KNOWN
Supabase Preflight Plan: PASS
Final Readiness Decision: READY_FOR_PRODUCTION_APPLY_APPROVAL
Production Apply: CLOSED_PENDING_EXPLICIT_APPROVAL
Production/Supabase Writes Performed: NO
BATCH-04 Executed: NO
V4-018/V4-019 Changed: NO
V3.3.3 Modified: NO
Next Stage: BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3
```

The next stage is a separate Final Review. This document never advances the
repository into Production Apply.
