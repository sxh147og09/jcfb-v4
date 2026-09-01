# JCFB V4 Migration Plan 1.0

Status: V4-010 MIGRATION ORDER BLUEPRINT (DESIGN-ONLY)

This is the V4-010 future deployment order reference, not an executable migration. V4-010 did not create a migration file, connect to Supabase, execute SQL, seed data, or run smoke tests. V4-011 now assigns the design-only immutable migration identities and deployment gates; no database change is authorized by this document.

## 1. Migration rules

- Migrations are ordered, immutable, reviewable, and never silently rewritten.
- Apply only after the corresponding contract/schema compatibility review, advisor review, Secret Scan, and V3.3.3 boundary check.
- Use dependency order and `NOT VALID`/backfill validation only when the operation cannot weaken a gate; historical immutable rows are never rewritten.
- No routine `DROP`, hard delete, destructive `CASCADE`, or table recreation is permitted for audit-critical history.
- A first deployment that has not entered Production may be rolled back in reverse dependency order if no retained data/evidence depends on it. Once a migration is used by Production or historical evidence, repair forward with a new migration; never rewrite the old migration or history.
- `CREATE INDEX CONCURRENTLY`/lock planning is an implementation decision for live systems and must not change integrity semantics.

## 2. Dependency-ordered phases

### Phase 0: prerequisites, extensions, and namespaces

Scope:

- verify target PostgreSQL/Supabase version and `security_invoker` support;
- verify approved extensions/functions (`pgcrypto` for portable UUID defaults and/or an approved UUIDv7 provider);
- register the future immutable `migration_version`, schema versions, and hash profile;
- create `core`, `market`, `context`, `model`, `evaluation`, `governance`, and `public` namespaces with owners;
- set schema/default privileges to deny public/client access by default.

Gate: extension ownership/version, role model, search path, Data API exposure, and secret storage are documented. No V3.3.3 connection or import is allowed.

Rollback: before first deployment only, drop empty namespaces/extensions in reverse order if approved and unused. After any dependent object/data exists, use a forward repair migration; do not remove an extension or rewrite its recorded identity.

### Phase 1: registries and canonical core

Scope:

- create `governance.model_versions` and `governance.engine_versions` without circular Promotion FKs;
- create `core.competitions`, `core.teams`, `core.team_aliases`, and `core.matches`;
- add UUID PKs, stable source-scoped keys, match daily unique key, home/away/competition FKs, basic checks, and hash/time metadata;
- add registry active-pointer partial unique indexes only after the active predicate is finalized.

Gate: duplicate daily match rejects; home/away IDs differ; source/status/version/hash checks fail closed; no V3.3.3 FK exists.

Rollback: before first use, drop Phase 1 objects in reverse FK order. After a match or registry is referenced, retain rows and forward-correct; never delete canonical identity history or change a used registry identity.

### Phase 2: market, context, and evidence

Scope:

- create official/external snapshot tables in separate `market` schema;
- create Team Context, normalized context-to-evidence membership, Evidence, Bundles, and bundle membership in `context`;
- add official/external source separation, market availability, source-time state, payload/hash constraints, dedup keys, and typed scope FKs;
- add controlled evidence references after both parent schemas exist.

Gate: an unavailable official market is accepted only with explicit reason; an available market without payload rejects; external data cannot satisfy official lineage; snapshot dedup is deterministic.

Rollback: before first evidence use, reverse-drop empty tables only. Once a snapshot/evidence row is used or audited, preserve it and repair forward with a new revision; never delete or overwrite a source observation.

### Phase 3: Frozen Input and runtime outputs

Scope:

- create `model.frozen_inputs` and normalized exact-selection child tables;
- create `model.feature_bundles`, `model.engine_runs`, `model.predictions`, `model.prediction_engine_runs`, and `model.frozen_predictions`;
- add typed FKs, same-match deferred checks, role/version identity fields, all required hashes, cutoff/kickoff/run/freeze timestamps, and immutable/future-leakage flags;
- install no public read path.

Gate: Frozen Input revision uniqueness; `prediction.match_id`/Frozen Input match equality; Feature/Engine/Prediction exact hash lineage; no formal run after kickoff; frozen mutation denied; Production/Shadow/Experiment roles remain distinct.

Rollback: before any formal run, reverse-drop empty runtime objects in dependency order. After a Frozen Input, Engine Run, Prediction, or Frozen Prediction exists, history is retained and any defect is corrected by a new identity/revision and forward migration; no down migration may mutate/delete it.

### Phase 4: evaluation, review, Tier A, and promotion evidence

Scope:

- create `evaluation.official_results`, `postmatch_reviews`, `tier_a_samples`, `tier_a_run_members`, `promotion_reviews`, `promotion_review_samples`, and `calibration_records`;
- add result/review revision chains, same-match checks, regulation-result scope, Model Evaluation/Match Explanation separation, Tier A sequence/pair unique rules, and manual Promotion evidence fields;
- add post-creation FK from registry rows to approved Promotion Review only if the dependency direction is safe.

Gate: result correction inserts a new revision; review mismatch rejects; an Experiment cannot qualify Tier A; a Tier A pair must share `frozen_input_hash` and pre-kickoff outputs; `auto_promotion=true` rejects; promotion requires manual approval and a new Production identity.

Rollback: before evidence is used, reverse-drop empty evaluation objects. Once a result/review/sample/promotion/calibration row exists, preserve it; corrections/retractions are new append-only rows and new migration logic.

### Phase 5: governance, audit, incidents, and release pointers

Scope:

- create `governance.release_pointer_events`, `governance.incidents`, and `governance.audit_logs`;
- add audit sequence/bigint identity, hash-chain columns, entity/action allow-lists, incident revisions, and release pointer predecessor/successor evidence;
- add controlled active Production pointer cache only when the activation transaction and partial unique index are both ready.

Gate: all lifecycle operations have actor/action/entity/before/after/metadata/time/prev_hash/entry_hash evidence; duplicate active Production fails closed; audit rows are append-only; an incident cannot erase the offending history.

Rollback: an unused empty governance schema may be removed before first deployment. Once audit/pointer/incident history exists, never drop or rewrite it; repair forward and preserve the chain.

### Phase 6: RLS, functions, triggers, grants, and privileges

Scope:

- enable (and, where approved, force) RLS on every table;
- revoke default `PUBLIC`, `anon`, and ordinary `authenticated` table privileges;
- create least-privilege backend/runtime/review/admin grants and explicit function execute grants;
- add append-only, frozen immutability, revision, source separation, role, cross-match, no-future, Tier A, Production uniqueness, public projection, and audit triggers;
- verify every security-definer function has fixed `search_path`, actor check, restricted execute, and no arbitrary SQL/table parameters;
- verify `security_invoker` compatibility and fallback before public exposure.

Gate: RLS/grants tests deny anon/internal writes; valid controlled service paths pass; invalid match/hash/role/time/pair writes fail closed; registry updates are audited; public cannot bypass private tables.

Rollback: before production, disable/remove unreferenced policies/functions/triggers in a reviewed reverse migration only. Once used by Production, do not weaken/remove a security or immutability gate; add a forward-compatible policy/trigger fix and incident evidence.

### Phase 7: views and read projections

Scope:

- create `public.public_read_projections` ledger with no client write policy;
- create explicit-column `v_public_predictions`, `v_public_latest_odds`, `v_current_frozen_predictions`, `v_canonical_latest_update`, `v_tier_a_progress`, and `v_model_registry_public`;
- grant only approved public/internal views and, if required by security-invoker semantics, only safe underlying columns;
- verify latest update is computed from real business timestamps and not page/deploy time.

Gate: Shadow/Experiment rows cannot appear; public views are read-only; source-safe unavailable markets remain explicit; latest update tracks source business time; public anon reads allowed views and cannot write.

Rollback: before publication, remove unreferenced views/grants in reverse dependency order. After public use, withdraw via an append-only projection/status event and forward view migration; never erase publication/audit history or revert a used migration file.

### Phase 8: seed registries and smoke validation

Scope:

- seed only reviewed, non-secret registry metadata through an audited service path;
- no V3.3.3 rows, outputs, parameters, results, or audit history are copied;
- run the smoke matrix below in an isolated transaction/test database with real RLS caller roles;
- run advisor checks, FK-index checks, `git diff --check`, Secret Scan, and cross-contract validation;
- record migration, test, advisor, and audit identities.

Gate: all smoke cases pass, no unsafe advisor finding remains without an accepted exception, and no Production release is activated by a seed step.

Rollback: roll back the isolated test transaction. For a pre-production seed, remove only unreferenced seed metadata through an audited forward/cleanup path; after production, preserve registry/audit history and append retirement/withdrawal events instead of deleting rows.

## 3. Future smoke validation blueprint

These checks are planned only; V4-010 does not run them:

| Case | Expected result |
|---|---|
| insert valid canonical match | accepted with UUID identity, source/provenance/hash, and audit event |
| duplicate `(data_date, official_match_no)` | rejected by unique constraint |
| official unavailable market with reason | accepted as explicit `UNAVAILABLE`, no payload required for that market |
| official available market missing payload | rejected by market payload trigger |
| post-kickoff Production Engine Run | rejected or stored only as `INVALID`; never Tier A/public eligible |
| mutate Frozen Prediction | rejected by RLS/grant and append-only trigger |
| publish Experiment output | rejected by role/public projection trigger |
| Tier A pair with different `frozen_input_hash` | rejected or `PAIR_INVALID`, `tier_a_eligible=false` |
| anon write to internal table | denied by grant/RLS (`42501` expected) |
| canonical latest update source | equals max of typed Prediction/Frozen/Odds/Context/Result/Review business times, never page/deploy time |

## 4. Migration approval checklist

Before V4-011 is allowed to design/apply a migration, confirm:

- all V4-008/V4-009 field, identity, role, hash, correction, and time contracts are mapped;
- exact migration/schema versions are registered;
- dependency order and rollback boundary are reviewed;
- all FKs, unique keys, checks, deferred triggers, RLS policies, grants, and views are tested;
- active Production uniqueness and new-identity rollback are proven;
- append-only/audit hash chain and result/review correction paths are proven;
- public view security-invoker behavior is verified on the target version;
- Secret Scan, advisor review, `git diff --check`, and V3.3.3 isolation pass;
- no migration applies automatically from the blueprint SQL.

V4-010 stops at this plan. V4-011 extends it with migration design, registry, preflight, roll-forward, smoke, and acceptance artifacts; no migration is executed here. The next task is `V4-012 Migration Dry-Run & Validation Harness Design 1.0`.
