# JCFB V4 V4-020 CANONICAL MATCH IDENTITY IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`

Branch/HEAD: `main` / `fa76bb35f7077c0fe597f1489f7fbd9712be205b`

Implementation Status: `COMPLETE` for the V4-020 local, no-write implementation boundary

Files Added/Changed:

- `tools/canonical_intake/__init__.py`
- `tools/canonical_intake/match_identity.py`
- `tests/fixtures/v4_020/identity_cases.json`
- `tests/unit/test_v4_020_canonical_match_identity.py`
- `docs/V4_020_CANONICAL_MATCH_IDENTITY_IMPLEMENTATION.md`
- `docs/V4_020_ACCEPTANCE_EVIDENCE.json`
- current V4 task-status documents listed in the evidence JSON

Canonical Identity Contract: `canonical-match@1.0.0`; the envelope carries source, source type/reference, official/source match references, competition, home/away teams, kickoff, timezone, observed/published/ingested timing, hashes, status, resolution state, and conflict evidence. The envelope has no prediction, recommendation, confidence, model interpretation, risk, probability, or engine-output fields.

Business Key Strategy: A root identity uses the contract-defined `data_date:official_match_no` business key. `match_id` is a separate deterministic UUIDv5 derived from a fixed V4 namespace and the business key; the business key is never used as the primary identity.

Cross-Source Identity Strategy: A source with a different local reference maps to an existing `match_id` only when the canonical structural fingerprint matches exactly: canonical competition ID, ordered canonical home/away team IDs, and kickoff instant normalized to UTC. Source references and mappings are retained in the append-only event ledger. No source-specific random UUID is generated.

Home/Away Conflict Handling: A changed ordered home/away pair for an existing business key returns `BLOCKED / REQUIRES_REVIEW`, retains both observations, and records both source references and values.

Kickoff Conflict Handling: Kickoff instants are compared after UTC normalization. A different instant returns `BLOCKED / REQUIRES_REVIEW`; the original envelope is not overwritten.

Competition Conflict Handling: A different canonical competition ID returns `BLOCKED / REQUIRES_REVIEW`; both source observations remain available for audit.

Timezone Handling: Recognized aliases such as `PRC` and `+08:00` normalize to an IANA zone (`Asia/Shanghai`). The declared timezone remains a separate identity field, and its offset must agree with `kickoff_at`; invalid or conflicting values fail closed.

Append-Only/Revision Boundary: V4-020 implements an in-memory append-only observation/event boundary for unit validation. Root identity envelopes are immutable; duplicate deliveries append a `DUPLICATE_NOOP` event, aliases append a mapping event, and conflicts append a blocked event. A physical persistence adapter, fact envelope, timestamp/cutoff gate, and full orchestrator remain deferred to V4-021/V4-022/V4-023.

Prediction Fields Present: `NO`

Tests Passed: Targeted V4-020 suite `15/15 PASS`; full repository suite `170/170 PASS`; `git diff --check = PASS`.

V3.3.3 Isolation: `PASS`; no V3.3.3 path was changed, and V4 intake rejects V3.3.3 references in input metadata.

F-Drive Policy: `PASS`; runtime/output path resolution rejects non-F-drive roots and traversal outside `F:\Projects\jcfb-v4`.

Production/Supabase Writes: `NO`

Migration Applied: `NO`

Git Commit: `fa76bb35f7077c0fe597f1489f7fbd9712be205b` (`feat(v4-020): add canonical match identity intake`)

Working Tree: `CLEAN` after the acceptance commit

V4-020 DoD: `PASS`

V4-020 Status: `COMPLETE`

Next Recommended Task: `V4-021` only; V4-022 and V4-023 remain outside this implementation and must not be treated as complete.
