# JCFB V4 Raw-Fact Re-ingestion Decision

Decision identity: `v4-raw-fact-reingestion@1.0.0`

Decision: **CONDITIONALLY APPROVED FOR VERIFIED OBJECTIVE RAW FACTS ONLY**

V4 may re-ingest an external objective fact when the fact is independently
verifiable and passes the Historical Source Archive contract. Permitted
examples are official raw odds, external raw market snapshots, official match
results, official halftime results, and verified lineup/source records.

Re-ingestion requires a source reference, historical source/observation time,
original payload/image/file hash, canonical match identity, market/context
type, revision identity, ingestion timestamp, and an eligibility decision.
The record becomes a V4 independent source artifact through re-ingestion; it
does not become a V3.3.3 artifact or a shortcut around V4 provenance.

Always forbidden are V3.3.3 coefficients, model artifacts, predictions,
Frozen Predictions, confidence, calibration results, review-outcome-derived
parameters, or direct V3 runtime/model namespace references. Those are not
raw facts even if they are stored outside the V3 repository.

If the active V4 isolation policy cannot distinguish objective source facts
from generated outputs, ingestion is blocked. This decision does not loosen
that policy and does not authorize any import in this phase.
