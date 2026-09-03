# JCFB V4 View Blueprint 1.0

Status: V4-010 PUBLIC READ VIEW DESIGN (DESIGN-ONLY)

The views below are candidates only. No view is created or exposed by this task. They read an append-only, Production-only safe projection ledger; they are not alternate sources of truth.

The runtime forward-fix reserves the explicit V4-owned public name prefix
`public.v4_`. The unprefixed `public.v_*` names are retained as a protected
V3.3.3 compatibility surface and must never be replaced or dropped by V4.

## 1. View security contract

- Use explicit column lists; never `SELECT *`.
- Use `WITH (security_invoker = true)` on PostgreSQL versions that support it.
- Grant `SELECT` on the approved public-safe views only. There are no public write grants.
- `anon` and ordinary `authenticated` have no direct private-table privileges. If a security-invoker view needs an underlying privilege, grant only the exact safe projection columns or use a separately reviewed private API schema/function. Never grant raw `model`, `evaluation`, `market`, `context`, or `governance` tables merely to make a view work.
- Public predicates must exclude `BLOCKED`, `WITHDRAWN`, non-frozen, non-Production, Shadow, Experiment, and incident-withdrawn projection rows.
- A view cannot execute a model, update state, bypass a gate, or infer a missing fact.

## 2. Safe projection ledger

`public.public_read_projections` is inserted only by the Production publication gate. It contains public-safe display/selection/summary fields and internal proof references whose columns are not granted to browser roles. It also carries typed source business times:

```text
prediction_business_at
frozen_business_at
odds_business_at
context_business_at
result_business_at (nullable)
review_business_at (nullable)
```

The publication gate verifies these values against the exact upstream Production Prediction, Frozen Prediction, official odds, Team Context, Official Result, and Review rows before insert. They are not page-build, deploy, API response, or row-insertion times.

## 3. Required candidate views

### 3.1 `public.v4_public_predictions`

Purpose: public-facing current Production prediction summary.

Safe columns:

`match_id`, `competition_name`, `home_team_name`, `away_team_name`, `kickoff_at`, `match_status`, `safe_selection_summary`, `safe_odds_summary`, `frozen_at`, `canonical_latest_update_at`.

Source: latest `PUBLISHED` projection row per `match_id`, ordered by `projection_revision` and `created_at` after the Production Frozen Prediction/publication gate has passed; latest is a query ordering, never an identity. No raw model payload, internal risk decomposition, Shadow/Experiment ID, source reference, or secret is selected.

### 3.2 `public.v4_public_latest_odds`

Purpose: public-safe latest official market summary.

Safe columns: `match_id`, `kickoff_at`, `safe_odds_summary`, `odds_business_at`, `publication_status`.

Source: published Projection ledger only. The summary is populated from an official snapshot and retains explicit unavailable-market states/reasons. The view never queries an external snapshot as official and never fabricates a missing market.

### 3.3 `public.v4_current_frozen_predictions`

Purpose: public-safe Production Frozen Prediction read model.

Safe columns: `match_id`, `kickoff_at`, `safe_selection_summary`, `frozen_at`, `prediction_business_at`, `frozen_business_at`, `projection_revision`.

Predicate: `publication_status='PUBLISHED'` and the projection's internal role/reference checks have passed. It exposes a summary, not the embedded private Prediction snapshot.

### 3.4 `public.v4_canonical_latest_update`

Purpose: business-data freshness projection.

For each published projection row, calculate the maximum real business timestamp:

```sql
-- Candidate only; do not apply from this blueprint.
SELECT
  p.match_id,
  GREATEST(
    p.prediction_business_at,
    p.frozen_business_at,
    p.odds_business_at,
    p.context_business_at,
    COALESCE(p.result_business_at, '-infinity'::timestamptz),
    COALESCE(p.review_business_at, '-infinity'::timestamptz)
  ) AS canonical_latest_update_at
FROM public.public_read_projections AS p
WHERE p.publication_status = 'PUBLISHED';
```

`GREATEST` is the row-level form of `MAX` over the declared source timestamps. If a future implementation aggregates multiple projection revisions, it must apply `MAX` over these derived business times after selecting only valid published rows. The view must never use `published_at`, `created_at`, page build time, deploy time, or API request time as a substitute. Missing required source time fails publication; optional postmatch times remain NULL and are ignored by the explicit `COALESCE` sentinels.

### 3.5 `public.v4_tier_a_progress`

Purpose: controlled progress summary for Promotion Review/internal governance.

Safe aggregate columns: `eligible_sample_count`, `rejected_sample_count`, `blocked_sample_count`, `last_eligible_sample_no`, `as_of_business_at`.

Source: `evaluation.tier_a_samples` with explicit V4 role/hash/gate predicates. Default grant is `v4_review_promotion`/approved internal readers only, not `anon`. It does not expose individual private payloads or allow a client to qualify a sample.

### 3.6 `public.v4_model_registry_public`

Purpose: optional public display of the currently active Production model identity.

Safe columns: `public_model_name`, `public_model_version`, `public_model_revision`, `publication_status`, `effective_at`.

Source: an approved public-safe registry projection or safe fields copied by the Production publication gate. Direct governance registry access is not granted to public roles. Shadow/Experiment rows and implementation/config hashes are excluded unless separately approved as public-safe.

## 4. Candidate DDL shape

```sql
-- Candidate only; do not apply from the blueprint.
CREATE VIEW public.v4_public_predictions
WITH (security_invoker = true)
AS
SELECT
  p.match_id,
  p.competition_name,
  p.home_team_name,
  p.away_team_name,
  p.kickoff_at,
  p.match_status,
  p.safe_selection_summary,
  p.safe_odds_summary,
  p.frozen_at,
  GREATEST(
    p.prediction_business_at,
    p.frozen_business_at,
    p.odds_business_at,
    p.context_business_at,
    COALESCE(p.result_business_at, '-infinity'::timestamptz),
    COALESCE(p.review_business_at, '-infinity'::timestamptz)
  ) AS canonical_latest_update_at
FROM public.public_read_projections AS p
WHERE p.publication_status = 'PUBLISHED';
```

The other views use the same explicit-column, published-only pattern. The runtime
candidate creates only the V4-prefixed names. A pre-existing unprefixed view is
reusable only after an exact definition, `security_invoker`, and grant-contract
assertion; an incompatible object is fail-closed and must be given an explicit
V4-owned name. No V3.3.3 view is replaced, dropped, or rebuilt.

## 5. Projection validation before publication

`governance.validate_public_projection()` must fail closed unless:

1. the match exists and all display fields agree with the canonical match;
2. Production model/prediction/Frozen Prediction identities resolve to the same match and role;
3. the Production model is the unique active release for its family/channel;
4. the odds ref is official and its safe summary preserves unavailable states;
5. Frozen Prediction is immutable and frozen before kickoff;
6. every business timestamp is copied from a real source row and is not a page/deploy time;
7. no Shadow/Experiment/raw feature/debug/secret data is present;
8. the projection insert and audit event succeed in the same controlled publication path.

A withdrawal appends a new projection revision/status and incident/audit evidence; it does not delete the prior published history.

## 6. Grants and read-only behavior

After security review, the intended grant is:

```sql
-- Candidate only; do not apply from this blueprint.
GRANT SELECT ON public.v4_public_predictions,
               public.v4_public_latest_odds,
               public.v4_current_frozen_predictions,
               public.v4_canonical_latest_update
  TO anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.v4_public_predictions,
                                public.v4_public_latest_odds,
                                public.v4_current_frozen_predictions,
                                public.v4_canonical_latest_update
  FROM anon, authenticated;
```

The view names are read models, not writable views. `v4_tier_a_progress` and `v4_model_registry_public` receive only their approved internal/public grants after a column-level review.

## 7. Older-version fallback

If the deployed PostgreSQL version does not support `security_invoker`, do not expose default-definer views to `anon`/`authenticated`. Keep them private/unexposed, or use a narrowly scoped, fixed-search-path safe function that returns only the approved projection columns. The implementation must test RLS/grants under each caller role before enabling the Data API.

## 8. V3.3.3 boundary

No view may read or expose V3.3.3 tables, prediction history, parameters, results, reviews, samples, or audit data. A benchmark view, if ever approved, is a separate non-public adapter outside this projection set.
