# JCFB V4 V4-021 CANONICAL FACT ENVELOPE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch/HEAD: `main` / `58598a4` (`feat(v4-021): add canonical fact envelope`; acceptance-closure metadata is committed immediately after)

Implementation Status: `COMPLETE` for the V4-021 local, no-write implementation boundary

## Files Added/Changed

- `tools/canonical_intake/fact_envelope.py`
- `tools/canonical_intake/__init__.py`
- `tests/fixtures/v4_021/fact_cases.json`
- `tests/unit/test_v4_021_canonical_fact_envelope.py`
- `docs/V4_021_CANONICAL_FACT_ENVELOPE_IMPLEMENTATION.md`
- `docs/V4_021_ACCEPTANCE_EVIDENCE.json`
- V4 task-status documents updated to record V4-021 acceptance and V4-022 as the next task

## Fact Envelope Contract

`canonical-fact@1.0.0` / `canonical-fact-envelope@1.0.0` is an immutable typed objective-fact envelope. It carries:

- `fact_type`
- `subject.match_id` and `subject.match_identity_key`
- `source`, `source_ref`, and `provenance_ref`
- object-shaped JSON `payload` when present
- exact `availability_status`
- `reason_code` and optional `reason_detail`
- `published_at`, `observed_at`, and `ingested_at` as timezone-aware carrying fields
- `provenance_hash`, `payload_hash`, and `observation_id`
- `revision` and `supersedes_object_id`
- `conflict_evidence` for competing source sides

The envelope has no role, prediction, recommendation, confidence, model interpretation, or engine-output fields.

## Availability Status Semantics

| Status | Meaning and admission rule |
|---|---|
| `AVAILABLE` | A typed non-empty payload is present, the source and source reference are attributable, the subject resolves to V4-020 identity, and provenance is hashable. |
| `UNKNOWN` | V4 cannot establish the fact property; `reason_code` is mandatory and payload may be absent. |
| `UNAVAILABLE` | The source/context was explicitly not supplied or offered; `reason_code` is mandatory and no substitute payload is created. |
| `CONFLICT` | Source observations disagree; `reason_code` and at least two source-side payloads with refs/hashes are mandatory. |
| `STALE` | The observation is outside a later freshness policy; `reason_code` is mandatory. Freshness evaluation is not implemented here. |
| `FUTURE_DATA` | The observation is marked ineligible for a declared pre-match boundary; `reason_code` is mandatory. Cutoff evaluation is deferred to V4-022. |
| `BLOCKED` | A quality, identity, or governance gate prevents formal use; `reason_code` is mandatory. |

Statuses are exact typed enum values. The implementation does not derive a status from `NULL`, an empty payload, a missing source, or a boolean `available` flag.

## Reason-Code Contract

Every non-`AVAILABLE` observation must provide an uppercase stable `reason_code` matching `^[A-Z][A-Z0-9_]{2,63}$`. `reason_detail` is optional but cannot appear without a code. Examples include `SOURCE_VALUE_UNKNOWN`, `OFFICIAL_MARKET_NOT_SUPPLIED`, `SOURCES_DISAGREE`, `OUTSIDE_FRESHNESS_WINDOW`, `AFTER_DECLARED_CUTOFF`, and `IDENTITY_GATE_FAILED`.

## Payload Rules

The envelope payload is a JSON object at this generic boundary. `AVAILABLE` requires a non-empty object; non-`AVAILABLE` states may carry no payload or an explicitly empty object only when the source semantics require it. A list, scalar, non-JSON value, or model-layer field fails closed. The payload is recursively frozen in memory and returned as a thawed copy for serialization.

## Source/Provenance Rules

`source`, `source_ref`, `provenance_ref`, `observed_at`, and `ingested_at` are required. `published_at` is optional, but when supplied it is timezone-aware. A supplied provenance hash must be a `sha256:` reference; otherwise a deterministic hash is derived from the attributable source/reference/time manifest. The V4-021 module carries times but does not implement the V4-022 cutoff or availability-time selection gate.

## V4-020 Identity Binding

`CanonicalFactStore` requires a `CanonicalMatchIdentityStore`. The subject UUID and identity key must resolve to an existing V4-020 identity with `status=AVAILABLE` and `identity_resolution_state=RESOLVED`. Missing, orphaned, unresolved, or key-mismatched subjects are blocked; no orphan fact envelope is created.

## Conflict Preservation

`CONFLICT` requires at least two `FactConflictEvidence` entries. Each entry preserves the source, source reference, typed payload, provenance reference/hash, and observation reference. The competing sides remain attached to the immutable conflict envelope and are not merged or discarded.

## Implicit Coercions Rejected

- `NULL` is not converted to `UNKNOWN`.
- An empty payload is not converted to `UNAVAILABLE`.
- Missing source is not converted to `UNKNOWN`.
- `STALE` is not converted to `UNAVAILABLE`.
- `CONFLICT` is not converted to `BLOCKED`.
- `FUTURE_DATA` is not converted to `AVAILABLE`.
- Lowercase/unknown status strings, `status` aliases, and `available` booleans are rejected.

## Append-Only Boundary

The local store retains validated source observations, immutable fact envelopes, duplicate no-op events, blocked identity/validation events, and revision events. A changed observation appends a new revision with a new object/hash identity and `supersedes_object_id`; the predecessor remains addressable. No update/delete API, database adapter, migration, Supabase connection, or V4-023 full dedup/orchestrator was added.

## Acceptance

- Targeted V4-021 suite: `17/17 PASS`
- Full repository suite: recorded in `V4_021_ACCEPTANCE_EVIDENCE.json`
- V3.3.3 isolation: `PASS`
- F-drive policy: `PASS`
- Production/Supabase writes: `NO`
- Migration added/applied: `NO`
- Prediction, Score Engine, Shadow, Public Page, and Promotion: `NOT EXECUTED`

V4-021 DoD: `PASS`

V4-021 Status: `COMPLETE`

Git Commit(s): `58598a4` (`feat(v4-021): add canonical fact envelope`), followed by the acceptance-closure metadata commit.

Next Recommended Task: `V4-022` only; V4-023 remains outside this implementation.
