# JCFB V4 Data Quality Assessment Contract 1.0

Status: **BATCH-14 ARCHITECTURE GOVERNANCE / ACTIVE**  
Contract version: `data-quality-assessment@1.0.0`  
Lifecycle: **PRE_PREDICTION_PRE_FREEZE**

## 1. Purpose and boundary

This contract governs the V4-050 assessment artifact. It evaluates accepted
identity, facts, official odds, external market observations, Team Context,
Evidence Graph references, timestamps, cutoff relation, availability,
missingness, freshness, duplication/integrity, conflicts, and future-data
risk.

It produces a typed multidimensional assessment and blocker/warning records.
It does not produce a scalar quality score, feature importance, prediction
probability, model confidence, betting confidence, recommendation, or
cross-domain weight.

## 2. Required assessment envelope

Every assessment must contain:

| Field | Rule |
|---|---|
| `assessment_id` | Stable immutable identity; never reused. |
| `artifact_kind` | Exact `PRE_FREEZE_DATA_QUALITY_ASSESSMENT`. |
| `contract_version` | Exact `data-quality-assessment@1.0.0`. |
| `match_id` / `canonical_entity_refs` | Resolved V4-020 identity; orphan assessments are invalid. |
| `prediction_cutoff_at` / `kickoff_at` | Explicit timezone-aware boundary; cutoff precedes kickoff. |
| `assessment_inputs` | Exact accepted IDs, revisions, and hashes used. |
| `data_quality_assessment` | Typed dimensions, states, refs, counts, and reasons. |
| `odds_quality_assessment` | Official/external market quality dimensions with role preserved. |
| `context_quality_assessment` | Team Context and tactical/context quality dimensions. |
| `source_quality_assessment` | Source identity, provenance, freshness, and contradiction quality only. |
| `blockers` / `warnings` | Stable reason-coded decisions; no hidden omissions. |
| `input_hash` / `payload_hash` / `provenance_hash` / `output_hash` | Recomputable V4 SHA-256 identities. |
| `revision` / `supersedes_assessment_id` | Append-only correction lineage. |

The legacy task labels `DATA_QUALITY_SCORE`, `ODDS_QUALITY_SCORE`,
`CONTEXT_QUALITY_SCORE`, and `SOURCE_CONFIDENCE` are governed as the typed
assessment objects above. They are not scalar numeric fields.

## 3. Fixed dimensions

Each dimension is an object containing at least:

```json
{
  "state": "PASS|PARTIAL|UNKNOWN|STALE|CONFLICTED|BLOCKED",
  "basis_refs": [],
  "evidence_refs": [],
  "reason_codes": [],
  "counts": {},
  "source_input_hashes": []
}
```

The required dimensions are:

```text
identity
availability
coverage
verification
freshness
completeness
conflict
provenance
timestamp_validity
cutoff_eligibility
duplication_integrity
future_data_risk
```

No dimension is automatically aggregated into a prediction-like confidence
or importance value. A missing dimension is a contract failure, not an
implicit `UNKNOWN` conversion.

## 4. Threshold and state policy

This v1 contract defines no global numeric threshold. No value such as
`coverage >= 80%`, `freshness >= 0.7`, or `provenance >= 0.9` is approved here.
An upstream contract's own minimum sample, freshness, or availability policy
may be verified by reference. A future Prediction Engine may define its own
versioned eligibility profile; that profile is not created by BATCH-14.

Hard safety conditions are evaluated through
`quality-gate-matrix@1.0.0`. Non-hard states remain visible and are evaluated
at feature, domain, and candidate-set levels. An optional `UNKNOWN` feature
does not automatically block unrelated features.

## 5. Time, provenance, and replay

The assessment must prove
`input_availability_at <= prediction_cutoff_at < kickoff_at` for any pre-match
consumable input. Unknown or conflicting source time, timezone ambiguity,
future data, and post-match contamination follow the hard blocker matrix.

The input, payload, provenance, and output hashes include exact upstream
references/hashes/revisions, typed states, cutoff/kickoff, contract/config/
matrix/reason-registry versions and hashes, and generator identity. Equal
logical input and configuration must replay to the same assessment decision.

## 6. Lifecycle and isolation

Assessments are append-only. A correction creates a new ID, revision, hash, and
`supersedes_assessment_id`; the predecessor remains immutable. This contract
does not create a Frozen Input, Prediction, Score Engine output, Shadow/Tier A
record, Production record, or Supabase write.
