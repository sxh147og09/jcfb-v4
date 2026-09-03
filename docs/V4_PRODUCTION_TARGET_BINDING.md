# JCFB V4 Production Target Binding 1.0

Status: `BOUND_APPROVED` for target identity only; Production apply remains separately blocked.

## 1. Authority and source of truth

The machine-readable contract is [`config/migration_harness/v4_production_target_identity.json`](../config/migration_harness/v4_production_target_identity.json), validated by [`scripts/validate_v4_production_target_binding.ps1`](../scripts/validate_v4_production_target_binding.ps1) and [`tools/migration_harness/production_target.py`](../tools/migration_harness/production_target.py).

This contract records non-secret identity metadata. It is a repository configuration and audit artifact. It does not connect to Supabase, inspect the database, apply migrations, grant roles, or activate Production writes.

## 2. Bound Production identity

| Field | Recorded value |
|---|---|
| provider | `Supabase` |
| project_ref | `icndieflfvydixtehgzu` |
| region | `us-west-2` |
| postgres_major | `17` |
| role | `PRODUCTION` |
| binding_state | `BOUND_APPROVED` |
| approved_by | `human_approver` |
| approval_basis | `explicit user confirmation in ChatGPT` |

`project_ref` is the unique Production identity key. The Supabase project display name, `1347427215@qq.com's Project`, is retained only as display metadata and is never used as a security or routing primary key.

## 3. Environment separation

The contract declares exactly one Production target and keeps the environment roles distinct:

- `DISPOSABLE_LOCAL`: local PostgreSQL runtime identity, `NOT_BOUND` in this Production binding contract.
- `STAGING`: `NOT_BOUND` until a separately reviewed staging identity is supplied.
- `PRODUCTION`: the single Supabase target with project ref `icndieflfvydixtehgzu` and role `PRODUCTION`.

The validator rejects duplicate Production entries, duplicate target IDs, role/environment mismatches, an invalid Supabase project ref, and any Production identity collision with disposable or staging metadata.

## 4. Binding is not apply approval

Target binding does not authorize Production apply. Binding only answers “which named project is the V4 Production target?” It does not answer “may the approved migration manifest be applied now?”

The Production apply gate remains explicit and fail-closed:

- `hard_block_preserved = true`
- `explicit_approval_required = true`
- `target_binding_authorizes_apply = false`
- `approval_state = PENDING_PRODUCTION_APPLY_APPROVAL`
- `production_apply_allowed = false`

The runtime executor continues to reject `PRODUCTION_APPLY`. V4-018 and V4-019 remain TODO and are not marked complete by this binding.

## 5. Secrets and preflight

The contract contains no database URL, password, token, API key, service-role key, cookie, or connection secret. Credentials, when a future approved runtime path needs them, remain process-environment-only and are not copied into this contract or its evidence.

Production Target Identity is now `KNOWN` from the binding contract. The Supabase Preflight Plan is not automatically `PASS`: security/advisor evidence, schema baseline/diff, extension and role review, migration-history state, and the remaining target checks must be completed separately in the next stage, `SUPABASE_PREFLIGHT_PLAN_COMPLETION`.

## 6. Read-only verification

Run from `F:\Projects\jcfb-v4`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate_v4_production_target_binding.ps1 -RepoRoot F:\Projects\jcfb-v4
python -m tools.migration_harness --repo-root F:\Projects\jcfb-v4 production-readiness
```

Both commands are read-only. A passing binding validator is not permission to run BATCH-04 or write Supabase.

## 7. Related contracts

- [`docs/V4_PRODUCTION_POLICY.md`](V4_PRODUCTION_POLICY.md)
- [`docs/V4_RUNTIME_ROLE_BOUNDARY.md`](V4_RUNTIME_ROLE_BOUNDARY.md)
- [`docs/V4_MIGRATION_PREFLIGHT.md`](V4_MIGRATION_PREFLIGHT.md)
- [`docs/V4_PRE_BATCH_04_LOCAL_EXECUTION.md`](V4_PRE_BATCH_04_LOCAL_EXECUTION.md)
