# JCFB V4 Gate-to-Prediction Interface Contract 1.0

Status: **BATCH-15 ARCHITECTURE GOVERNANCE / ACTIVE / IMPLEMENTATION NOT STARTED**
Contract version: `gate-to-prediction@1.0.0`

## State mapping

| BATCH-14 Gate state | Formal engine behavior |
|---|---|
| `BLOCKED` | Prohibited for every engine. No successful probability payload is emitted. A rejected run may retain typed errors only. |
| `INELIGIBLE` | Prohibited for the affected engine/domain. It is not relabeled as BLOCKED or converted to an unavailable market. |
| `PARTIALLY_ELIGIBLE` | Not globally allowed. Each engine profile must prove all required inputs are present and every missing optional input is an explicitly allowed state. |
| `ELIGIBLE` | May proceed only after Frozen Input, approved model artifact, profile, and Engine Output checks pass. |

`UNKNOWN`, `UNAVAILABLE`, `NOT_VERIFIED`, `STALE`, `CONFLICTED`, `FUTURE_DATA`,
and `BLOCKED` remain typed states. Silent imputation, default substitution,
quality penalties, and missingness collapse are prohibited.

The BATCH-14 Gate Record is referenced by ID/hash. It is not a probability,
confidence grade, risk decision, or final prediction gate.
