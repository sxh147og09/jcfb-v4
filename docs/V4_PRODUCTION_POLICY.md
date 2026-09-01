# JCFB V4 Production Policy 1.0

Status: V4-007 ACCEPTANCE PENDING

## 1. Purpose and authority

This policy defines the only formal Production path for JCFB V4. It implements the role boundary in docs/V4_RUNTIME_ROLE_BOUNDARY.md and must be read with docs/V4_CONSTITUTION.md, docs/V4_MODEL_GOVERNANCE.md, and the V4-006 identity contracts.

This policy describes governance and evidence requirements. It does not publish a model, select parameters, run a prediction, or implement a database.

## 2. Production is the sole canonical source

PRODUCTION is the only formal prediction source and the only role that may:

- generate a canonical public prediction
- create a Production Frozen Prediction after all gates pass
- update the active Production pointer through an approved release event
- append a canonical Production branch to the public read projection

The Production path may run only an approved Production release whose status is PRODUCTION, whose role is PRODUCTION, and whose revision is the single Canonical Active Production Revision for its declared model family. A SHADOW or EXPERIMENT revision cannot be accepted by changing a label or path.

Production probability, confidence, risk, abstention, five-market output, score selection, and recommendation strength are Production-owned artifacts. They remain distinguishable from Shadow and Experiment evidence.

## 3. Production release identity

Every Production release and formal run preserves:

- jcfb_version
- model_name and model_version
- major, minor, patch, and immutable revision
- engine_version and selector identity when applicable
- config_version and config_hash
- schema_version, migration_version, and dataset_version
- implementation_hash
- input_hash and output_hash
- frozen_revision and frozen_input_hash
- role=PRODUCTION
- run_at and runtime_environment
- status=PRODUCTION
- owner, release_id, created_at, and effective_at

The canonical output identity is never only a match ID, date, filename, display title, latest label, or current label. A Production release must also record its predecessor when it supersedes an existing release.

## 4. Admission and output gates

Before a Production run can create a formal prediction, the following must pass:

1. Canonical Match Identity and kickoff time are resolved.
2. Official market availability and official odds integrity are resolved; unavailable markets remain explicitly unavailable.
3. Every accepted input satisfies the V4 cutoff and no-future-information rule.
4. Frozen Input is formed and its frozen_input_hash is retained.
5. Model, engine, selector, configuration, dataset, schema, and migration identities are explicit.
6. implementation_hash, config_hash, input_hash, output_hash, run_at, and runtime_environment are present.
7. Required engine outputs are complete and independently modeled for the five markets.
8. Consistency, data-quality, context-quality, risk, abstention, and Final Prediction Gate conditions pass.
9. A Production audit event is appended before or with the formal output.

If a critical prerequisite is uncertain, Production returns BLOCKED or an explicitly governed abstention. It does not guess, use a silent default, or publish first and check later.

## 5. Production output and immutability

The Production path creates its own prediction identity and Frozen Prediction identity. After freeze:

- Prediction and Frozen Prediction are append-only.
- Probability, score, confidence, risk, market direction, and recommendation strength cannot be changed to match a result.
- A correction creates a new audited revision with a supersedes pointer.
- Postmatch Review reads the original pre-match output and appends evaluation; it cannot rewrite the output.
- Production cannot delete Shadow or Experiment evidence.

Production may read approved Shadow or Experiment evidence only through controlled review or benchmark paths. Such reads cannot change the canonical Production output or its historical lineage.

## 6. Production uniqueness and supersession

For each declared model_family and canonical_output_channel, the registry has exactly one active canonical Production pointer at any time:

active_canonical_production_count(model_family, canonical_output_channel) = 1

The model family and channel scope must be explicit. An implementation must reject two competing Production revisions for the same formal chain; it must not choose by insertion order, filename, latest timestamp, or operator preference.

To activate a new Production revision:

1. Register a new immutable revision and explicit Production release identity.
2. Record the supersedes_revision and predecessor active pointer.
3. Complete the Promotion Gate and manual approval.
4. Append the activation event and effective time.
5. Retire the predecessor explicitly with reason and successor.
6. Commit one active pointer state without a period of two canonical owners.

Retirement preserves the old implementation, configuration, hashes, runs, Frozen Inputs, Frozen Predictions, evaluations, and audit events. It does not delete or edit them.

## 7. Public projection boundary

The public path is:

Model Compute -> Production Prediction Store -> Production Canonical Public Read Projection -> Public Web

Public Web is read-only. It may read only the Production canonical public projection. SHADOW and EXPERIMENT outputs are denied by default and are never presented under a Production URL, Production label, canonical public identifier, or canonical_latest_update_at.

The Production publication adapter must verify:

- role=PRODUCTION
- active Production revision is unique
- the output is frozen and gate-approved
- the projection identity points to the Production output
- no Shadow or Experiment identity is present in the public payload
- audit and timestamp lineage are present

Page build time and cache refresh time cannot replace the real business-data update time.

## 8. Failure, demotion, and rollback

A Production integrity incident may trigger fail-closed behavior and rollback. Rollback must:

1. Preserve the failed Production revision, output, Frozen Prediction, logs, hashes, and incident evidence.
2. Append a rollback event with rollback_id, failed_revision, rollback_target_revision, actor, reason, time, and evidence.
3. Register a new rollback Production release identity with a new revision. Its immutable implementation/configuration lineage may reference the previously approved target, but the old revision is not silently reactivated.
4. Re-run the applicable identity, compatibility, integrity, and publication gates.
5. Set exactly one active pointer to the new rollback release after its effective time.

Rollback restores an approved prior behavior through a new auditable Production identity. It never edits historical Frozen Prediction, erases the failed version, changes a prior review, or hides the incident. The complete transition is governed by docs/V4_PROMOTION_PATH.md and docs/V4_INCIDENT_POLICY.md.

Operationally, the active serving pointer may be cut back to the previous approved Production behavior identified by rollback_target_revision. Because V4-006 forbids silent reactivation of a RETIRED revision, that cut-back is represented by the new rollback Production release identity; the original target record remains retained, immutable, and historically RETIRED.

## 9. Prohibited Production behavior

- Running a DRAFT, SHADOW, or EXPERIMENT revision as Production.
- Publishing before Frozen Input and Final Prediction Gate completion.
- Maintaining two active canonical Production revisions for one model family and channel.
- Mutating a Frozen Prediction or historical review in place.
- Letting Shadow or Experiment write Production state.
- Treating confidence as probability or probability as confidence.
- Letting a public page run a model or select a non-Production output.
- Auto-promoting or auto-rolling back without an explicit audit event and governed approval.

## 10. References

- docs/V4_RUNTIME_ROLE_BOUNDARY.md
- docs/V4_PROMOTION_PATH.md
- docs/V4_RUNTIME_ACCESS_MATRIX.md
- docs/V4_CONSTITUTION.md
- docs/V4_MODEL_GOVERNANCE.md
- docs/V4_VERSIONING_STANDARD.md
- docs/V4_INCIDENT_POLICY.md
- docs/V4_ARCHITECTURE_BLUEPRINT.md
