# JCFB V4 Model Data Isolation 1.0

Status: V4-009 ROLE ISOLATION DESIGN ARTIFACT

## 1. Purpose

This document defines how `PRODUCTION`, `SHADOW`, and `EXPERIMENT` data can coexist while preserving independent identity, storage ownership, permissions, and evidence eligibility. It implements the V4 Constitution and `docs/V4_RUNTIME_ROLE_BOUNDARY.md`; it does not execute any role.

## 2. Role definitions

| Role | Purpose | Formal authority | Allowed evidence |
|---|---|---|---|
| `PRODUCTION` | sole canonical prediction path | may create the canonical Production Prediction, Frozen Prediction, active release pointer, and public projection after all gates | formal public output and Production evaluation |
| `SHADOW` | genuine pre-match comparison run | may append isolated Engine Runs, Predictions, optional Shadow Frozen Predictions, review/calibration evidence in its namespace | Forward A/B and Promotion evidence only when all pre-kickoff gates pass |
| `EXPERIMENT` | research, backtesting, parameter/feature/selector/simulation studies | may append isolated research data and experiment-owned Frozen Input/Feature/Engine/Prediction records | research evidence only; never Forward Tier A or Production promotion evidence by itself |

Role is a typed required field on `engine_runs`, `predictions`, and all role-owned runtime output records. It is not inferred from a directory, database schema, filename, branch, or operator nickname.

## 3. Namespaces and row discriminators

The logical runtime key for every role-owned output is:

```text
(namespace, role, match_id, model_version_id, role_scoped_revision,
 implementation_hash, config_hash, input_hash, output_hash)
```

Each role-owned row also retains:

- exact `model_version_id` and `engine_version_id`/release identity;
- role-scoped revision (`r...`, `sh-...`, or `ex-...` under V4-006);
- `implementation_hash`, `config_hash`, `input_hash`, `output_hash`;
- `frozen_input_id` and `frozen_input_hash` for formal pre-match use;
- `prediction_cutoff_at`, `kickoff_at`, `run_at`/`model_run_at`, `run_completed_at`;
- explicit status and leakage/eligibility flags;
- audit identity for creation and any state event.

Role is immutable. Recovery or promotion creates a new role/revision identity and preserves the failed or predecessor identity.

## 4. Shared facts and private interpretation

The following `core` artifacts are objective, timestamped, provenance-preserving read inputs:

- Canonical Match Identity, Teams, Competitions;
- official odds snapshots and explicit unavailability states;
- external market snapshots marked non-official;
- Team Context snapshots;
- Evidence Items and Evidence Bundles.

All role runtimes may read approved versions of these facts. The following remain model-line private and are never merged across roles by overwriting:

- Feature Bundles and transformations;
- Engine Runs and raw payloads;
- Predictions, confidence, risk, recommendations, and consensus;
- Frozen Predictions;
- calibration, evaluation, Tier A qualification, and promotion interpretations.

A role can cite a fact by stable ID/hash, but it cannot relabel a model interpretation as an objective fact or update the source record.

## 5. Frozen Input and A/B isolation

### Production/Shadow Forward A/B

The valid A/B relationship is:

```text
one canonical match
       |
       +-- one shared Production Frozen Input (immutable)
       |       frozen_input_hash = H
       +-- Production Engine Runs/Prediction (role=PRODUCTION)
       |       input_hash = H_P
       +-- Shadow Engine Runs/Prediction (role=SHADOW)
               input_hash = H_S
```

The Production and Shadow pair must share:

- canonical `match_id` and match identity hash;
- `prediction_cutoff_at`;
- `kickoff_at` interpretation;
- exact `frozen_input_id` and `frozen_input_hash`;
- the declared `ab_comparison_group_id`.

They must retain distinct:

- role and role-scoped revision;
- model/engine release identity when different;
- `input_hash` because role/component identity is included;
- `output_hash`, Prediction identity, and optional Frozen Prediction identity;
- audit events and status.

`frozen_input_hash` is the substantive A/B equality proof. Equal match ID alone is insufficient.

### Experiment input

An Experiment may reference the shared Frozen Input for a controlled research comparison, or may create an Experiment-owned Frozen Input. In either case it must store `comparison_mode=EXPERIMENT_ONLY` when it is not a formal Production/Shadow pair. Same `frozen_input_hash` does not change `role=EXPERIMENT` and does not make the record Forward Shadow evidence.

## 6. Production uniqueness

For every declared `(model_family, canonical_output_channel)`, the governance registry must have:

```text
active_production_release_count = 1
```

The active Production release is an explicit registry/pointer identity, not the newest row. A new release:

1. creates a new Production-scoped model/engine identity;
2. records its predecessor and effective time;
3. passes Promotion Review and manual approval;
4. appends activation/pointer evidence;
5. retires/supersedes the predecessor without deleting its history.

Two active Production revisions, or a Production row with a Shadow/Experiment revision, is `PRODUCTION_UNIQUENESS_FAILURE` and must fail closed. A rollback receives a new auditable Production identity; it does not silently reactivate the old row.

## 7. Write isolation rules

| Artifact/action | Production | Shadow | Experiment | Review/Promotion | Public Web |
|---|---|---|---|---|---|
| Read approved canonical facts | READ | READ | READ | READ | no direct private read |
| Append shared Production Frozen Input | Freeze Gate only | DENY | DENY | DENY | DENY |
| Append own Feature/Engine/Prediction | own namespace | own namespace | own namespace | DENY | DENY |
| Append Production Frozen Prediction | Final Prediction Gate | DENY | DENY | DENY | DENY |
| Read paired Frozen Prediction | own/approved scope | approved comparison scope | approved research scope | READ | no direct private read |
| Append Postmatch Review | DENY as runtime | DENY as runtime | DENY as runtime | controlled service only | DENY |
| Append Tier A | DENY | DENY | DENY | after Forward gates only | DENY |
| Append Calibration | Production namespace | Shadow namespace | Experiment namespace | evaluation namespace | DENY |
| Change active Production pointer | publication/release gate only | DENY | DENY | after approved release | DENY |
| Write canonical public projection | Production publication gate only | DENY | DENY | DENY | DENY |

`APPEND_ONLY` never grants cross-role write authority. Shadow and Experiment cannot create, update, delete, replace, or hide Production Prediction, Frozen Prediction, confidence, risk, review, Tier A, active pointer, or public projection rows.

## 8. Promotion and Tier A isolation

Only a genuine pre-match Shadow run can contribute the Shadow side of a Forward A/B Tier A sample. A qualifying sample must prove:

- Production and Shadow roles are explicit and distinct;
- both outputs were completed before kickoff;
- both point to the same `frozen_input_hash` and match;
- every required hash and version identity resolves;
- Official Result and required Review exist;
- no future information entered either path;
- completeness and integrity gates pass;
- exclusion/failure rules were declared before evaluation.

Experiment data is permanently excluded from Forward Tier A and cannot be re-labeled as Shadow after kickoff, after result, or by changing a path/column. Experiment may be included in a separate research report that is clearly marked non-promotion evidence.

## 9. Public Read Projection isolation

`public_read_projections` may contain only:

- stable match identity and display fields;
- a public-safe reference to the latest approved official odds snapshot;
- canonical Production Prediction/Frozen Prediction reference and safe selections;
- Frozen timestamp and business-data `latest_update`;
- safe postmatch summary when available.

It must not contain Shadow/Experiment IDs, internal debug payloads, raw feature values, secrets, private source material, internal confidence decomposition, or unapproved model evidence. Public Web is read-only and reads the Production projection only. It cannot query private runtime tables as a shortcut.

## 10. Leakage and incident behavior

If a role reads post-cutoff or post-kickoff information, the affected run is `INVALID`/`BLOCKED`, `future_information_leakage=true`, `TIER_A_ELIGIBLE=false`, and `PROMOTION_EVIDENCE=false`. The record and evidence remain in its role namespace.

An isolated Shadow/Experiment failure does not mutate or automatically block Production. A shared Frozen Input, canonical identity, or security incident may block all affected roles under the Incident Policy. Every violation appends an audit record and, where required, an Incident; clean reruns receive new identities.

## 11. No role conversion

The following are prohibited:

- changing `role=EXPERIMENT` to `SHADOW` in place;
- copying a Shadow output identity into a Production row;
- using a different Frozen Input while claiming the same A/B pair;
- publishing a Shadow/Experiment result through the Production projection;
- using a postmatch rerun as Forward evidence;
- allowing a role-specific calibration/evaluation row to overwrite another role's row.

Promotion is a new Production release identity after evidence and manual approval, not a role rename.

## 12. V3.3.3 boundary

Role isolation is entirely within V4. No role is authorized to read, copy, merge, mutate, or publish JCFB V3.3.3 model outputs, parameters, predictions, Frozen Predictions, reviews, samples, or audit history. A separately authorized benchmark remains outside this model namespace.
