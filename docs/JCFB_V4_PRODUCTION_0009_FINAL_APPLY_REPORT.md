# JCFB V4 PRODUCTION 0009 FINAL APPLY REPORT

## Final disposition

- Report status: `PASS`
- Production project ref: `icndieflfvydixtehgzu`
- Database: `postgres` / PostgreSQL `17.6`
- Apply scope: `0009 ONLY`
- Applied migration: `20260904040147 / v4_seed_and_smoke`
- Official migration history: `17 -> 18`
- V3.3.3 migration history: `9 -> 9` (unchanged)
- V4 migration history: `8 -> 9`
- Partial apply: `NO`
- V4-018: `COMPLETE`
- V4-019: `COMPLETE`
- BATCH-04: `COMPLETE`
- Public page deployment: `NO`
- Prediction/model execution: `NO`

## Approved source and pre-apply gates

- Human approval: explicit Production resume approval for `0009 ONLY` was
  retained from the approved continuation.
- Source Git HEAD: `e05b6be7df74927afed4161ec81ac298de6abfff`.
- Fresh runtime evidence:
  `prebatch04-20260904T034354Z-9f2784895c3c48a6bf0ea2cbcb688dae`.
- Runtime evidence status: `RUNTIME_VALIDATION_PASS` with a clean working tree
  and an exact Git HEAD match.
- Canonical migration hashes: `9/9 PASS`.
- Exact 0009 canonical hash:
  `sha256:e4c96f434a8359b54e397f209e565b94162a01037c1cf91e9bd96bf0b948bc20`.
- Exact 0009 byte SHA-256:
  `57e0e3a0bf7b0d0e83f671c8caded6ffb0544568cdc81c9328cddfbcf1583132`.
- `0009_seed_and_smoke.sql` uses `extensions.digest(...)` and contains no
  `public.digest(...)` call.
- Production `pgcrypto` schema: `extensions`; two `extensions.digest`
  overloads exist; `public.digest` overload count is zero.
- Pre-apply official history was exactly 17 rows, latest
  `20260904023555 / v4_views_projections`; `v4_seed_and_smoke` was absent.

The only pre-apply working-tree difference was the previously prepared 0009
forward-fix report refresh. It was preserved in a recoverable Git stash before
the clean-tree apply gate, then restored after the Production apply completed.

## Apply result

The Supabase migration operation returned `success=true`. The first read after
the operation proved that official migration history changed from 17 to 18 and
that the sole new row was:

```text
20260904040147  v4_seed_and_smoke
```

No migration from 0001 through 0008 was rerun. No unexpected migration-history
row appeared.

## Post-apply final verification

| Gate | Result | Production evidence |
|---|---|---|
| Schema diff / identities | `PASS` | Expected V4 tables `40/40`, functions `19/19`, public views `6/6`, and critical triggers `14/14`; no expected identity missing. |
| Migration history | `PASS` | Total `18`; V3.3.3 `9`; V4 `9`; exactly one `v4_seed_and_smoke` row. |
| Registry seed / smoke | `PASS` | One canonical hash registry row and nine exact V4 schema-registry rows; all nine migration hashes match the canonical manifest. |
| Audit trigger execution | `PASS` | Registry seed produced `1 + 9` audited INSERT events; all recorded entry hashes match `sha256:[0-9a-f]{64}`. |
| RLS and grants | `PASS` | RLS is enabled on all 40 V4 tables; `public_read_projections` has FORCE RLS; no client grants exist on internal schemas; the published-read policy targets only `anon` and `authenticated`. |
| Function security | `PASS` | All 19 V4 functions are `SECURITY INVOKER`, all 19 have a fixed `search_path`, and no V4 function EXECUTE grant is exposed to `PUBLIC`, `anon`, or `authenticated`. |
| Frozen immutability | `PASS` | Frozen Input mutation guard, Frozen Prediction append-only guard, and append-only rejection function are installed; fresh exact-HEAD runtime tests passed. |
| Production uniqueness | `PASS` | `active_production_model_uq` and `active_production_engine_uq` are present and unique. |
| No-future leakage | `PASS` | Runtime, engine, prediction, and Tier A prematch triggers are installed; prematch validation binds cutoff and kickoff. |
| Tier A integrity | `PASS` | Same match, same Frozen Input ID/hash, Production/Shadow role, prematch completion, and future-leakage rejection semantics are present. |
| Canonical latest update | `PASS` | The V4 view is `security_invoker`, reads six business timestamp fields, uses the business-latest index, and contains no wall-clock/page-build time. |
| Public projection isolation | `PASS` | Production/PUBLISHED checks, scope gate, append-only gate, FORCE RLS, and the published-read policy are present. |
| V4 `public.v4_*` views | `PASS` | All six views exist and are `security_invoker`; the four approved safe views have client SELECT grants, while Tier A and model-registry views remain internal. |
| V3.3.3 isolation | `PASS` | All nine legacy migration rows and all eleven legacy public-view identities remain present; legacy view fingerprint is `3dfd3bbc87d7fc342c4bdb1b287e9d77`. |
| Security advisor delta | `PASS` | No new `WARN` or `ERROR`. One expected `INFO` was added for the new internal acceptance table having RLS enabled and no policy. |
| Performance advisor delta | `PASS` | `119 -> 119`; no finding added or removed. |

Fresh disposable runtime evidence for the exact apply HEAD also records:

```text
Smoke: 20/20 PASS
Enforcement: 15/15 PASS
Audit trigger execution: PASS
Frozen immutability: PASS
Production uniqueness: PASS
No-future leakage: PASS
Tier A same-frozen-input: PASS
Canonical latest update: PASS
```

## Advisor disposition

The single new Security Advisor INFO is intentional and accepted as
`INTERNAL_NO_POLICY_PRIVATE=ACCEPTED`: the new
`governance.deployment_acceptance_snapshots` table has RLS enabled, has no
client grants, and intentionally has no permissive policy. The unchanged
pre-existing advisor baseline remains tracked separately and was not modified
by 0009.

## Data and release boundary

Post-apply row checks confirmed zero V4 matches, odds snapshots, Frozen Inputs,
predictions, Frozen Predictions, Tier A samples, public projections, or
acceptance snapshots. The only persistent data written by 0009 was the approved
registry seed and its audit trail. No public page was deployed, no canonical
public pointer was switched, and no prediction or model run occurred.

## Completion decision

All required post-apply gates passed or, for the single intentional advisor
INFO, received the policy-defined internal/no-policy disposition. Therefore:

```text
V4-018 = COMPLETE
V4-019 = COMPLETE
BATCH-04 = COMPLETE
NEXT EXECUTION BOUNDARY = BATCH-05 / V4-020
```

This completion does not authorize BATCH-05 execution, public deployment,
prediction execution, Shadow execution, Promotion, or any V3.3.3 mutation.
