# JCFB V4 Evidence Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and evidence boundary

Evidence is a source-bound record supporting or contradicting a claim. The Evidence Contract does not turn a claim into an objective fact automatically, and it does not permit post-match explanation to rewrite a pre-match evidence bundle.

Each Evidence record is independently addressable, time-scoped, hashable, and auditable. Downstream Team Context, Market Intelligence, Feature Bundles, and Review objects reference `evidence_id` and `evidence_hash`; they do not copy an unversioned free-form claim into a formal path.

## 2. Evidence fields

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `evidence_id` | UUID/UUIDv7 | REQUIRED | Stable evidence identity. |
| `contract_version` | string | REQUIRED | `evidence@MAJOR.MINOR.PATCH`. |
| `claim_type` | enum/string | REQUIRED | Governed category such as `INJURY_STATUS`, `LINEUP_STATUS`, `ODDS_OBSERVATION`, `MATCH_IDENTITY`, or `RESULT`. |
| `claim` | structured text/object | REQUIRED | Atomic claim; distinguish observation from interpretation. |
| `entity_refs` | non-empty array | REQUIRED | Stable refs to match/team/player/market objects. |
| `source` | string/object | REQUIRED | Attributable publisher/provider/authority. |
| `source_type` | enum | REQUIRED | Source class from the umbrella contract. |
| `source_reference` | string | REQUIRED | Replayable article/feed/document/screenshot reference without secrets. |
| `published_at` | timezone-aware timestamp or explicit state | REQUIRED | Source publication time; `UNKNOWN` is a gate-relevant state if absent. |
| `retrieved_at` | timezone-aware timestamp | REQUIRED | Time V4 retrieved/observed the source. |
| `valid_from` | timezone-aware timestamp or explicit state | REQUIRED | Beginning of the claim's validity or `UNKNOWN` with reason. |
| `expires_at` | timezone-aware timestamp or explicit state | CONDITIONAL | Required when the claim has a declared expiry/freshness boundary. |
| `confidence` | `ConfidenceValue` | REQUIRED | Confidence in evidence provenance/claim verification, not outcome probability. |
| `verification_state` | enum | REQUIRED | `VERIFIED`, `NOT_VERIFIED`, `CONFLICTED`, `STALE`, or `REJECTED`. |
| `contradiction_state` | enum | REQUIRED | `NONE`, `PENDING`, `CONFLICTED`, `RESOLVED`, or `NOT_APPLICABLE`. |
| `evidence_hash` | SHA-256 string | REQUIRED | Hash of the exact evidence record boundary. |
| `payload_hash` / `provenance_hash` / `status` / `metadata` | common fields | REQUIRED | Hash and lifecycle lineage. |

`claim_type` may be extended only through enum governance. The claim field must make clear whether it is an observation (“club statement lists player X as unavailable”) or an interpretation (“this may weaken the left side”). The latter is not an Objective Fact and belongs in a model-private interpretation object.

## 3. Verification and contradiction lifecycle

| State | Meaning | Formal use |
|---|---|---|
| `VERIFIED` | Source, identity, time, and claim checks pass | May enter a formal input when cutoff/freshness gates also pass |
| `NOT_VERIFIED` | Information exists but required verification is incomplete | Remains visible; cannot be silently treated as verified |
| `CONFLICTED` | Material claims or sources disagree | Preserve all claims; downstream use is blocked or explicitly gated |
| `STALE` | Claim passed its freshness/expiry boundary | Historical evidence only unless a governed consumer permits it |
| `REJECTED` | Source/claim failed acceptance, identity, or integrity checks | Retain audit record; cannot feed formal inputs |

`contradiction_state` is separate from `verification_state`. A verified source can still be part of a `CONFLICTED` evidence set. `RESOLVED` means a documented resolution exists; it does not erase the rejected or superseded evidence.

Corrections append a new Evidence object containing `supersedes_evidence_id`, reason, actor/time, before/after references, and a new hash. The old evidence remains immutable.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000301",
  "evidence_id": "019a0000-0000-7000-8000-000000000301",
  "contract_version": "evidence@1.0.0",
  "created_at": "2026-09-01T12:00:00+08:00",
  "source_timestamp": "2026-09-01T11:40:00+08:00",
  "observed_at": "2026-09-01T11:55:00+08:00",
  "ingested_at": "2026-09-01T12:00:01+08:00",
  "effective_at": "2026-09-01T11:40:00+08:00",
  "expires_at": "2026-09-01T19:35:00+08:00",
  "source": "Example club official bulletin",
  "source_type": "CLUB_STATEMENT",
  "source_reference": "ref://club/example-home/bulletin/20260901-1140",
  "confidence": {"state": "ASSESSED", "score": 0.96, "basis": "Direct official bulletin with publication time"},
  "provenance_hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
  "payload_hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
  "status": "VERIFIED",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "claim_type": "INJURY_STATUS",
  "claim": {
    "kind": "OBSERVATION",
    "text": "The official bulletin lists no confirmed injury absence for the named first-team group.",
    "language": "en"
  },
  "entity_refs": [
    "match:019a0000-0000-7000-8000-000000000002",
    "team:team-example-home-001"
  ],
  "published_at": "2026-09-01T11:40:00+08:00",
  "retrieved_at": "2026-09-01T11:55:00+08:00",
  "valid_from": "2026-09-01T11:40:00+08:00",
  "verification_state": "VERIFIED",
  "contradiction_state": "NONE",
  "evidence_hash": "sha256:4444444444444444444444444444444444444444444444444444444444444444"
}
```

## 5. Validation rules

- All fields in section 2 marked required and common required metadata are present.
- `evidence_id` is stable and never generated from claim text, display name, or publication time.
- `entity_refs` resolve to stable identities. A display name alone is not a referential key.
- `published_at`, `retrieved_at`, `valid_from`, and `expires_at` are timezone-aware when supplied. `expires_at >= valid_from` when both are known.
- A source with unknown publication/availability time may remain in the Evidence Graph as `NOT_VERIFIED`, but cannot pass a formal pre-match cutoff gate merely because `retrieved_at` is before cutoff.
- `verification_state`, `contradiction_state`, and `status` use explicit enums and do not rely on empty fields.
- For a pre-match Evidence Bundle, `valid_from`/defensible availability must be at or before `prediction_cutoff_at`; post-kickoff evidence is `FUTURE_DATA`/`BLOCKED` for that bundle.
- `confidence` is a fact/evidence confidence object. It is not a market probability, model confidence grade, or recommendation strength.
- `evidence_hash`, `payload_hash`, and `provenance_hash` must be format-valid and recomputable from the declared hash boundary.
- `REJECTED`, `STALE`, or unresolved `CONFLICTED` evidence cannot silently become an accepted feature input.

## 6. Hash, compatibility, and isolation boundary

The evidence hash includes the claim, entity refs, source identity, all declared publication/retrieval/validity times, verification/contradiction states, and supersession references. It excludes only transport timestamps and non-authoritative trace metadata declared in the object.

Adding an optional claim annotation or a new non-breaking source detail is `MINOR`; changing claim semantics, verification state meaning, time validity, hash interpretation, or requiredness is `MAJOR`; a documentation clarification is `PATCH`.

Evidence may be shared as provenance-preserving objective support. A Model Interpretation may reference evidence but cannot rewrite the Evidence object, promote its own conclusion to `VERIFIED`, or use a post-match claim in a pre-match Frozen Input.
