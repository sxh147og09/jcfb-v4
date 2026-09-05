# V4 BATCH-15 Frozen Input Ordering Amendment

Amendment ID: `V4-015-ORD-001`
Status: **ACTIVE**
Contract boundary: `frozen-input@2.0.0` remains active; this amendment changes
execution ordering, not the logical Frozen Input payload.

## Canonical edge set

```text
V4-022 + V4-038 + V4-039 + V4-049 + V4-050 + V4-051
  -> V4-076 Frozen Input
  -> V4-052 / V4-053 / V4-054 / V4-055
  -> V4-074 Five-Market Orchestrator
  -> V4-075 Final Prediction Gate
  -> V4-077 Frozen Prediction
```

V4-076 is a pre-prediction immutable artifact. Its upstreams are actual
pre-freeze prerequisites: cutoff/provenance lineage, Feature Bundle contract
and version registry, feature snapshot hash, and the accepted BATCH-14
tactical/quality/gate artifacts. It has no dependency on V4-052 through
V4-055, V4-074, V4-075, Prediction, or Final Gate.

The task registry primary batch for V4-076 is BATCH-15. BATCH-20 retains
V4-074, V4-075, and V4-077, so BATCH-20 continues to own downstream
orchestration, final gating, and Frozen Prediction lineage.

## Frozen Input content and revision rule

Every future Frozen Input must freeze exact canonical match identity,
Feature Bundle ID/hash, feature snapshot hash, BATCH-11 statistical refs and
hashes, BATCH-12 football/context refs and hashes, BATCH-13 market refs and
hashes, BATCH-14 tactical refs and hashes, BATCH-14 Gate Record ID/hash,
accepted/rejected refs, prediction cutoff, kickoff, dataset/schema versions,
and exact model/engine/config revisions. Post-freeze upstream correction
creates a new Frozen Input identity/hash with explicit `supersedes`; existing
Engine Output remains bound to its original Frozen Input.

No pre-freeze formal Prediction Run is valid. No Engine Run may re-read raw
upstream source after freeze; it consumes only the exact frozen references.
