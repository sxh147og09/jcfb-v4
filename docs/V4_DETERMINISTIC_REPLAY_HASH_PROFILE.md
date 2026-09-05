# JCFB V4 Deterministic Replay & Hash Profile 1.0

Status: **BATCH-15 ARCHITECTURE GOVERNANCE / ACTIVE**
Contract version: `deterministic-replay@1.0.0`

The substantive Engine Output hash covers the canonical Frozen Input
identity/hash, exact engine model artifact, feature profile and subset,
configuration, implementation/dependency identity, typed probability payload,
calibration state, warnings/errors that affect interpretation, and declared
lineage refs. Canonical serialization uses sorted keys, stable field names,
full-precision numeric values, and explicit missingness states.

`created_at`, `run_at`, process IDs, runtime duration, transport metadata,
logging IDs, and other declared volatile telemetry are excluded from
substantive probability/output hashes. They may remain in audit metadata.

Same Frozen Input + same approved model artifact + same profile/config + same
implementation must produce the same logical probability payload and hash.
Any input, artifact, profile, configuration, or implementation change creates
a new version/revision or fails closed.
