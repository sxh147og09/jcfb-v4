# JCFB V4 RLS and Security Blueprint 1.0

Status: V4-010 RLS, PRIVILEGE, AND SECURITY BLUEPRINT (DESIGN-ONLY)

This blueprint is a candidate security model for the future V4 schemas. It does not create roles, grant privileges, enable RLS, expose a Supabase Data API object, or run a database advisor.

## 1. Security boundary

The database is split into private ownership schemas and one constrained read-projection schema:

| Boundary | Default posture | Browser access |
|---|---|---|
| `core` | RLS enabled; private source-of-truth tables | none |
| `market` | RLS enabled; official/external source isolation | none |
| `context` | RLS enabled; evidence and context isolation | none |
| `model` | RLS enabled; role-owned runtime isolation | none |
| `evaluation` | RLS enabled; review/promotion isolation | none |
| `governance` | RLS enabled; registry/audit/admin isolation | none |
| `public` | RLS enabled on projection ledger; only explicit read views exposed | read-only allow-list |

RLS is defense in depth. It does not replace `REVOKE`, typed FKs, append-only triggers, hash checks, no-future gates, or Promotion gates. The future implementation must separately verify Supabase Data API exposure settings: a table being present in a schema and a row passing RLS are separate concerns.

## 2. Database identities

These are logical identities; creation and membership grants require a future approved migration and deployment review.

| Identity | Intended capability | Hard limits |
|---|---|---|
| `postgres`/admin | schema owner and emergency maintenance | not used by browser/app; emergency actions follow Incident Policy and are audited |
| `service_role` / backend service | server-side controlled functions and approved reads/writes | Supabase `service_role` bypasses RLS; never ship to a client, log, SQL file, or repository |
| `v4_fact_intake` | append canonical facts, source snapshots, context, evidence, and correction events | no model output, Tier A, Promotion, or public writes |
| `v4_production_runtime` | read approved facts; append Production feature/run/prediction/freeze records through gates | cannot write Shadow/Experiment/evaluation history or bypass gates |
| `v4_shadow_runtime` | read approved facts/shared Frozen Input; append Shadow-owned feature/run/prediction records | no Production, Frozen Prediction, Tier A, pointer, or public write |
| `v4_experiment_runtime` | read approved scope; append Experiment research records | no public/Tier A/promotion-activation write and no role conversion |
| `v4_review_promotion` | read immutable evidence; append Results, Reviews, Tier A, Promotion, Calibration, and audit records | no historical output mutation or role conversion |
| `v4_registry_admin` | append registry/release identities and controlled pointer/status transitions | no runtime history rewrite/delete |
| `v4_incident_admin` | append incidents, containment/recovery/closure events | no output rewrite/delete |
| `authenticated` (internal future path) | read only if explicitly authorized by an internal claim/policy | ordinary authenticated users are not internal operators; no direct writes |
| `anon` | read approved public views only | no table writes, model reads, functions that compute models, or private data |

The backend role is a service boundary, not a general-purpose unrestricted client. Where `service_role` is unavoidable, the caller is server-side, the function validates actor/role/action, and the operation emits a complete audit event.

The runtime candidate treats `service_role` as provider-owned: candidate 0001
checks `pg_catalog.pg_roles.rolbypassrls` and fails closed when the role is
missing or false. It never creates or alters that reserved role. The disposable
container may provision a local compatibility role before candidate execution;
that local bootstrap is not a Production or Supabase migration path. `anon` and
`authenticated` must retain `rolbypassrls = false`.

## 3. Grant and revoke blueprint

The real migration must review the actual Supabase default privileges. Candidate order:

```sql
-- Candidate only; do not apply from the blueprint.
REVOKE ALL ON SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA core, market, context, model, evaluation, governance
  FROM PUBLIC, anon, authenticated;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON public.v4_public_predictions,
               public.v4_public_latest_odds,
               public.v4_current_frozen_predictions,
               public.v4_canonical_latest_update
  TO anon, authenticated;

-- If security-invoker views require base-table privileges, grant only these
-- safe projection columns; never grant the internal proof/reference columns.
GRANT SELECT (
  match_id, competition_name, home_team_name, away_team_name, kickoff_at,
  match_status, public_model_name, public_model_version,
  public_model_revision, safe_odds_summary, safe_selection_summary,
  safe_result_summary, prediction_business_at, frozen_business_at,
  odds_business_at, context_business_at, result_business_at,
  review_business_at, projection_revision, publication_status, created_at
)
ON public.public_read_projections TO anon, authenticated;
```

No `GRANT ALL ON ALL TABLES` is permitted. Custom backend roles receive only the tables/functions required for their path, and sequence usage is granted only where an identity sequence is directly used by that controlled writer. If `security_invoker` view execution requires underlying privileges, grant only the exact safe projection columns or move the view into a private API schema with a reviewed safe function; never grant private raw tables to satisfy a view.

`v4_tier_a_progress` and `v4_model_registry_public` are not automatically public. They are exposed only if their final columns are approved as public-safe and the underlying privilege/RLS path is tested.

## 4. RLS policy model

RLS is enabled on every candidate table, including private schemas and `public.public_read_projections`. `FORCE ROW LEVEL SECURITY` is recommended for the public projection ledger and any table whose owner could otherwise bypass policy. The `service_role` exception is intentional and remains server-side.

There are no `UPDATE` or `DELETE` policies for append-only tables. There are no `INSERT` policies for `anon` or ordinary `authenticated` on internal tables. A missing policy is an intentional deny and is recorded in the advisor checklist.

### 4.1 Private fact intake pattern

Fact intake uses a controlled backend role or function. A direct policy, if approved, is conceptually:

```sql
-- Candidate pattern only; use the actual role/function after review.
CREATE POLICY fact_intake_insert
ON core.matches
FOR INSERT TO v4_fact_intake
WITH CHECK (current_setting('v4.write_boundary', true) = 'FACT_INTAKE');
```

The same operation needs a server-side actor check, source/provenance validation, and an audit event. RLS `WITH CHECK` does not prove hashes, chronology, or canonical identity by itself.

### 4.2 Role-owned runtime pattern

Runtime insert policies must bind the row's explicit `role` to the caller's controlled boundary. They must not infer role from a schema, path, filename, or process name.

```sql
-- Candidate pattern only; no application role is created by V4-010.
CREATE POLICY runtime_shadow_insert
ON model.engine_runs
FOR INSERT TO v4_shadow_runtime
WITH CHECK (
  role = 'SHADOW'
  AND current_setting('v4.write_boundary', true) = 'SHADOW_RUNTIME'
);
```

Production, Shadow, and Experiment use separate policies/functions and separate version identities. The policies never allow a Shadow/Experiment row to target a Production pointer, Production Frozen Prediction, Tier A, or public projection.

### 4.3 Internal authenticated read pattern

If future internal users need browser reads, use a dedicated authorization helper based on `raw_app_meta_data`/server-controlled claims and a scoped ownership predicate. Do not use editable `raw_user_meta_data` for authorization. Do not use the deprecated `auth.role()` predicate. A policy must have both the target role and a row/claim condition, for example:

```sql
-- Candidate shape only; helper implementation is a future reviewed function.
CREATE POLICY internal_read_evidence
ON context.evidence_items
FOR SELECT TO authenticated
USING ((SELECT governance.is_v4_internal_reader()));
```

The helper must be in a non-exposed schema if it is `SECURITY DEFINER`, use a fixed `search_path`, perform an explicit caller check, and have `EXECUTE` revoked from roles that do not need it. Ordinary authenticated users remain denied.

### 4.4 Public projection policy

`public.public_read_projections` contains only safe projection values plus internal proof refs that are not granted to clients. Candidate policy:

```sql
-- Candidate only; do not apply from the blueprint.
ALTER TABLE public.public_read_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_read_projections FORCE ROW LEVEL SECURITY;

CREATE POLICY public_projection_published_read
ON public.public_read_projections
FOR SELECT TO anon, authenticated
USING (publication_status = 'PUBLISHED');
```

There is intentionally no client `INSERT`, `UPDATE`, or `DELETE` policy. Only the Production publication function/backend role can append a row after checking the Production references, safe column allow-list, source times, and audit event.

## 5. Security-definer and function rules

`SECURITY DEFINER` is exceptional, not a general way to fix permissions. Any approved definer function must:

1. live outside an exposed public API schema;
2. use a fixed `SET search_path` containing only explicitly qualified trusted schemas and `pg_catalog`;
3. validate the calling identity/role inside the function;
4. use fully qualified object names and parameter names that cannot be shadowed;
5. have `EXECUTE` revoked from `PUBLIC`, `anon`, and `authenticated` unless explicitly required;
6. emit an audit event for every state-changing operation;
7. avoid taking arbitrary table/function names or raw SQL from the caller.

Candidate controlled functions include `governance.append_audit_log`, `governance.activate_production_release`, `governance.validate_prematch_gate`, `governance.validate_tier_a_pair`, and a narrow `public.publish_projection`. Their canonical hash implementation is not invented here. A missing or ambiguous gate implementation fails closed rather than returning approval.

## 6. Public view security

The six named V4 public objects use the explicit `public.v4_*` name prefix so
they cannot collide with the protected V3.3.3 `public.v_*` surface. Where the
deployed PostgreSQL version supports it, they use `WITH (security_invoker =
true)`. The migration must verify the deployed version and test view behavior
under `anon` and `authenticated`:

- `v4_public_predictions`, `v4_public_latest_odds`, `v4_current_frozen_predictions`, and `v4_canonical_latest_update` may be public-safe after column review;
- `v4_tier_a_progress` exposes only an approved aggregate and is normally internal/authenticated-only;
- `v4_model_registry_public` exposes only approved Production registry display metadata and is public only if a safe projection path exists;
- no view uses `SELECT *` or exposes raw payloads, feature values, source references, internal confidence decomposition, Shadow/Experiment identity, secrets, or debug traces;
- no view invokes a model, mutates a table, or bypasses a gate.

On an older PostgreSQL deployment where `security_invoker` is unavailable, the public views remain in a private/unexposed schema or use a separately reviewed safe definer function with fixed path and minimal output. A view created with default definer semantics is not approved for public exposure.

## 7. Secret boundary

No API key, password, database URL, Supabase service key, token, cookie, private key, or credential-bearing connection string may enter:

- a table, JSONB payload, metadata, `runtime_environment`, or audit before/after state;
- a view, index, function argument default, SQL comment example, or migration;
- Git history, staged content, README, or test fixture.

Only non-secret `config_version`, `config_hash`, and a non-secret runtime environment descriptor are persisted. The future deployment uses approved secret storage and scans both working-tree and staged content.

## 8. Supabase advisor checklist

Before any future migration is applied, verify:

- RLS is enabled on every exposed table and intentional private/no-policy tables are documented.
- `anon`/`authenticated` table grants are revoked by default; public view/table grants are allow-listed.
- `service_role` is server-side only and not exposed to browser code.
- Every `SECURITY DEFINER` function has a fixed search path, explicit actor check, and restricted execute grant.
- `security_invoker` is available and effective on every public view, or the older-version fallback is used.
- Each FK has an index; duplicate/unused indexes and overlapping partial predicates are removed.
- Schema usage, table/column privileges, sequence privileges, function privileges, and Data API exposure are explicit.
- `pgcrypto`/UUIDv7 extension availability and placement are verified before a default is selected.
- No function, view, policy, or trigger can read/write V3.3.3 artifacts.
- No secrets occur in repository or staged content.

## 9. V3.3.3 isolation

This security design gives no role, policy, grant, view, function, or service path access to JCFB V3.3.3 predictions, parameters, results, reviews, samples, database history, or audit history. Any future benchmark is a separately authorized read-only adapter outside the V4 schema graph.
