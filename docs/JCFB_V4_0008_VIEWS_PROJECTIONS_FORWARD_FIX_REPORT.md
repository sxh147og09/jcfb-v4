# JCFB V4 0008 VIEWS/PROJECTIONS FORWARD-FIX REPORT

Status: `LOCAL FORWARD-FIX CANDIDATE; FRESH APPROVAL REQUIRED`

This report records the local repair of the unapplied runtime candidate after a
partial migration state. It does not authorize a resume, modify migration
history, or change V4-018/V4-019.

## Root cause and recovery boundary

| Field | Result |
|---|---|
| Production project_ref supplied for the incident | `icndieflfvydixtehgzu` |
| Applied V4 migration prefix | `0001-0007` |
| Production migration history count supplied for the incident | `16` |
| Production partial apply | `PARTIAL` |
| Failed migration | `0008 v4_views_projections` |
| Failed statement | `CREATE VIEW public.v_public_predictions` |
| Failure | `relation "v_public_predictions" already exists` |
| Transaction outcome | `0008 FAILED and rolled back` |
| 0009 state | `NOT_RUN` |
| Forward-fix required | `YES` |

The existing `public.v_public_predictions` is a V3.3.3 view owned by the
pre-existing public data surface. Its definition reads
`v_current_frozen_predictions`, `matches`, `predictions`, and `model_versions`
and exposes the legacy prediction contract. The intended V4 definition reads
the V4 `public_read_projections` ledger and exposes a different safe projection
contract. The definitions, lineage, columns, security properties, and grants
are therefore not equivalent.

## Collision and compatibility decision

| Existing baseline view | 0008 status | Strategy |
|---|---|---|
| `public.v_public_predictions` | `INCOMPATIBLE` | Preserve V3.3.3; create `public.v4_public_predictions` |
| `public.v_public_latest_odds` | `COLLISION; SEMANTICS UNPROVEN` | Preserve V3.3.3; create `public.v4_public_latest_odds` |
| `public.v_current_frozen_predictions` | `COLLISION; SEMANTICS UNPROVEN` | Preserve V3.3.3; create `public.v4_current_frozen_predictions` |
| `public.v_canonical_latest_update` | `COLLISION; SEMANTICS UNPROVEN` | Preserve V3.3.3; create `public.v4_canonical_latest_update` |
| `public.v_tier_a_progress` | `COLLISION; SEMANTICS UNPROVEN` | Preserve V3.3.3; create `public.v4_tier_a_progress` |
| `public.v_forward_tier_a_progress` | No 0008 name match | Preserved |
| `public.v_historical_tier_a_recovery_status` | No 0008 name match | Preserved |
| `public.v_latest_odds_snapshots` | No 0008 name match | Preserved |
| `public.v_odds_ingestion_gate_status` | No 0008 name match | Preserved |
| `public.v_screenshot_intake_status` | No 0008 name match | Preserved |
| `public.v_shadow_run_latest` | No 0008 name match | Preserved |

`public.v4_model_registry_public` is also V4-prefixed even though it is not in
the supplied 11-name baseline. The six V4 views are explicit-column,
`security_invoker`, read-only projections. The candidate contains no
`CREATE OR REPLACE VIEW` and no `DROP VIEW`.

An equivalent existing view is reusable only through a definition,
`security_invoker`, and grant-contract assertion. An incompatible existing view
fails closed; the V4 path then uses an explicit V4-owned name. No compatibility
assertion grants permission to replace or drop a V3.3.3 object.

## Required invariants

| Check | Result |
|---|---|
| Existing `v_public_predictions` compatibility | `INCOMPATIBLE` |
| 0008 strategy | `V4_RENAME` |
| V4 view namespace | `public.v4_*` |
| Other view collisions found | `v_public_predictions`, `v_public_latest_odds`, `v_current_frozen_predictions`, `v_canonical_latest_update`, `v_tier_a_progress` |
| V3.3.3 objects modified | `NO` |
| 0001-0007 hashes changed | `NO` |
| 0008 hash recomputed | `YES` |
| 0009 hash recomputed | `YES` |
| Manifest updated | `PASS` |
| Fresh disposable required | `YES` |
| Production/Supabase writes during fix | `NO` |
| Production resume scope | `0008 THEN 0009 ONLY` |
| New explicit resume approval required | `YES` |

## Validation evidence

The local compatibility unit tests cover equivalent-view assertion/reuse,
incompatible-view fail-closed behavior, missing V4-owned view creation,
all 11 baseline names, no legacy view replacement/drop, and
`security_invoker`/grant equivalence. The candidate package also passed the
canonical verifier and a fresh disposable execution of 0001-0009.

| Evidence | Result |
|---|---|
| Tests passed | `147/147 PASS` |
| Canonical hashes | `9/9 PASS` |
| Fresh disposable 0001-0009 | `9/9 PASS` |
| Smoke | `20/20 PASS` |
| Enforcement | `15/15 PASS` |
| Runtime status | `RUNTIME_VALIDATION_PASS` |
| Fresh run ID | `prebatch04-20260903T102619Z-12189f611f044934b3c0a9b1fa4688e4` |
| Runtime target | `DISPOSABLE_LOCAL` |
| Runtime write boundary | `production_db_writes_performed=NO; supabase_writes_performed=NO` |
| Git commit used for fresh runtime evidence | `114b0c11c2395783fbcdd03bb693a47b936df730` |
| Working tree at fresh runtime evidence | `CLEAN` |

## Resume instructions

After independent review and new explicit approval, the operator may resume only
the repaired 0008 and then 0009 against the already applied prefix. No 0001-0007
re-application, manual history repair, view replacement, or V3.3.3 permission
change is permitted. This report is local provenance and is not an execution
authorization.

## Next local validation commands

```powershell
Set-Location F:\Projects\jcfb-v4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\v4_disposable_runtime.ps1 -RepoRoot F:\Projects\jcfb-v4 -Action destroy -ConfirmDestroy
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\v4_disposable_runtime.ps1 -RepoRoot F:\Projects\jcfb-v4 -Action start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\v4_disposable_runtime.ps1 -RepoRoot F:\Projects\jcfb-v4 -Action readiness
python -m tools.migration_harness --repo-root . canonical-hash
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\v4_run_prebatch04_runtime_validation.ps1 -RepoRoot F:\Projects\jcfb-v4 -ApplyDisposable
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\v4_disposable_runtime.ps1 -RepoRoot F:\Projects\jcfb-v4 -Action stop
```
