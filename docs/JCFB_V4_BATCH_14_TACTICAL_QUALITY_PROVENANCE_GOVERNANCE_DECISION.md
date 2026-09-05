# JCFB V4 BATCH-14 Tactical, Quality & Provenance Architecture Governance Decision

Decision status: **APPROVED GOVERNANCE RESOLUTION**  
Active lifecycle: **Pre-Prediction Tactical, Quality & Provenance Gate Layer**  
Decision baseline: `515d1b141fc3dba54dd3cc6e57e5101e018d047f`

## 1. Decision

BATCH-14 is formally classified as the pre-prediction, pre-Frozen quality and
provenance layer. It does not enter Prediction, Score Engine, Frozen Input,
Prediction Abstention, Shadow/Tier A, Public Page, Promotion, Deployment,
Production, Supabase, or migration work.

The governed flow is:

```text
accepted canonical / evidence / context / feature artifacts
    -> V4-049 Tactical & League Profile
    -> V4-050 Data Quality Assessment
    -> V4-051 Provenance & Quality Gate
    -> downstream prediction-input preparation
    -> future V4-076 Frozen Input
    -> Prediction
```

## 2. Dependency decision

The approved direct dependencies remain unchanged:

- batch level: `BATCH-09`, `BATCH-10`, `BATCH-12`;
- V4-049: `V4-040 + V4-045 + V4-037`;
- V4-050: `V4-021 + V4-022 + V4-027 + V4-031 + V4-037`;
- V4-051: `V4-049 + V4-050`.

BATCH-11 and BATCH-13 are not added as direct BATCH-14 dependencies merely
because they are complete. Their Statistical Strength and Market Intelligence
artifacts remain independent-by-reference inputs for their approved downstream
consumers. No cross-domain fusion is created by this decision.

If a future approved Prediction task requires V4-051 to gate those lines, that
must be a separately recorded dependency amendment. It cannot be introduced by
implementation convention.

## 3. Active governance artifacts

This decision activates the following versioned artifacts:

| Artifact | Version | File |
|---|---|---|
| Tactical/League Profile Feature | `tactical-league-profile-feature@1.0.0` | `V4_TACTICAL_LEAGUE_PROFILE_FEATURE_CONTRACT.md` |
| Data Quality Assessment | `data-quality-assessment@1.0.0` | `V4_DATA_QUALITY_ASSESSMENT_CONTRACT.md` |
| Provenance/Quality Gate | `provenance-quality-gate@1.0.0` | `V4_PROVENANCE_QUALITY_GATE_CONTRACT.md` |
| Feature Eligibility | `feature-eligibility@1.0.0` | `V4_FEATURE_ELIGIBILITY_CONTRACT.md` |
| Quality Gate Config | `quality-gate-config@1.0.0` | `V4_QUALITY_GATE_CONFIG.json` |
| Quality Gate Matrix | `quality-gate-matrix@1.0.0` | `V4_QUALITY_GATE_MATRIX.json` |
| Quality Reason Registry | `quality-gate-reason-registry@1.0.0` | `V4_QUALITY_GATE_REASON_REGISTRY.json` |

All JSON config/matrix/registry artifacts carry a canonical SHA-256 field whose
value is computed over canonical JSON with that self-referential field
excluded.

## 4. Scorecard semantics

BATCH-14 v1 does not create a fourth scoring model. The historical registry
labels `DATA_QUALITY_SCORE`, `ODDS_QUALITY_SCORE`, `CONTEXT_QUALITY_SCORE`, and
`SOURCE_CONFIDENCE` are clarified as typed multidimensional assessment objects:

```text
data_quality_assessment
odds_quality_assessment
context_quality_assessment
source_quality_assessment
blockers[]
warnings[]
```

The dimensions are identity, availability, coverage, verification, freshness,
completeness, conflict, provenance, timestamp validity, cutoff eligibility,
duplication/integrity, and future-data risk. Each dimension retains state,
basis refs, evidence refs, reason codes, relevant counts, and source/input
hashes.

No global numeric threshold is approved in v1. No composite quality score,
cross-domain weight, missingness penalty, conflict penalty, provenance score,
feature importance, model confidence, prediction confidence, or betting
confidence may be introduced.

Upstream contracts remain authoritative for their own sample, freshness, and
availability rules. Future engine-specific minimum feature requirements must
be defined in a future versioned engine eligibility profile.

## 5. Hard blocker and eligibility decision

`quality-gate-matrix@1.0.0` is the sole BATCH-14 blocker propagation authority.
Hard blockers include unresolved canonical identity, unsupported contracts,
missing or invalid hashes, missing provenance, unknown/ambiguous source time,
future or post-cutoff data, post-match contamination, unresolved integrity or
revision conflict, rejected required evidence, explicit upstream BLOCKED, and
deterministic replay failure.

Eligibility is layered at feature, domain, and candidate-set levels:

- `ELIGIBLE`: all required inputs in scope pass;
- `PARTIALLY_ELIGIBLE`: no hard blocker, but optional/non-required inputs are
  not consumable;
- `INELIGIBLE`: inputs are valid and auditable but fail a declared required
  feature profile;
- `BLOCKED`: a hard safety, identity, time, provenance, integrity, or future
  data condition exists.

`INELIGIBLE` and `BLOCKED` are distinct. An optional `UNKNOWN` feature does not
automatically block an unrelated feature or candidate set. An unresolved
identity or hash-integrity failure may block the affected candidate set.

## 6. Three feature lines

Statistical Strength, Football Intelligence, and Market Intelligence remain
separate dimensions. BATCH-14 may validate their referenced identity, state,
time, provenance, and hash lineage where the approved input scope requires it;
it may not rewrite their values or numerically aggregate them.

The default and only active interaction policy is:

```text
SEPARATE_DIMENSIONS_ONLY
```

No tactical/statistical/market composite score or unified confidence exists in
this version.

V4-049 does not reimplement V4-043 League Statistical Strength. Its league
profile is tactical/contextual and uses typed relational or categorical values
from an approved vocabulary.

## 7. Frozen Input and Prediction boundary

BATCH-14 emits a **Pre-Freeze Quality Gate Record** and feature/domain
eligibility records only. It does not emit `FROZEN_INPUT_ELIGIBLE=true/false`,
create `frozen_input_id`, create `frozen_input_hash`, or provide a mock Frozen
Input.

V4-076 may later cite the gate record ID/hash, eligible feature references,
rejected/blocked references, and blocker reasons, while independently applying
the Frozen Input contract. Prediction, Score Engine, and Prediction Abstention
remain downstream and outside this resolution.

## 8. Lifecycle, hash, and isolation

Quality assessments and gate records are append-only. A correction creates a
new identity, revision, hash, reason, and explicit supersedes reference; the
prior record remains immutable.

Hashes cover exact upstream IDs, revisions, hashes, typed states, cutoff/
kickoff, contract/config/matrix/reason-registry identities, implementation
identity, and the decision payload. Equal logical input plus identical
governance identities must replay to the same decision/hash.

This is an additive governance resolution. No historical contract is
overwritten, no migration is added or applied, no Production/Supabase access is
authorized, and no V3.3.3 artifact is modified.

## 9. Entry condition after this decision

V4-049/V4-050/V4-051 remain **NOT IMPLEMENTED** until the follow-up BATCH-14
Scope & Entry Review verifies these artifacts, their hashes, contract
consistency, dependency consistency, and all governance tests.
