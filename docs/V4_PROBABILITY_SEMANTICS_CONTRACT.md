# JCFB V4 Probability Semantics Contract 1.0

Status: **BATCH-15 ARCHITECTURE GOVERNANCE / ACTIVE / CALIBRATION OUT OF SCOPE**
Contract version: `prediction-probability@1.0.0`

## 1. Typed stages

1. `RAW_MODEL_SCORE_OR_LOGIT` is the direct model value before probability
   normalization.
2. `UNCALIBRATED_MODEL_PROBABILITY` is the normalized model distribution
   emitted by BATCH-15.
3. `CALIBRATED_PROBABILITY` is a later artifact produced by V4-082. It never
   overwrites the original normalized value.

BATCH-15 may emit only the first two stages and must carry
`calibration_state=NOT_CALIBRATED` (or the active equivalent). It must not
claim calibrated output, confidence, uncertainty, or recommendation strength.

## 2. Normalization and hash rules

Every value is finite and in `[0,1]`; the complete distribution sums to one
within the active tolerance `1e-6`. Missing keys, NaN, Inf, range violations,
or normalization failure are fail-closed. Canonical full-precision values are
used for substantive hashes; display rounding is not part of probability
semantics or hashes.

Probability is not confidence. BATCH-15 does not derive confidence from max
probability, margin, entropy, quality, source quality, or market consistency.
Confidence and uncertainty remain later approved layers.
