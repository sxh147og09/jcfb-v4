# JCFB V4 Feature Eligibility Contract 1.0

Status: **BATCH-14 ARCHITECTURE GOVERNANCE / ACTIVE**  
Contract version: `feature-eligibility@1.0.0`  
Lifecycle: **PRE_FREEZE_QUALITY_PREPARATION**

## 1. Purpose

This contract defines feature-, domain-, and candidate-set eligibility
records used by the BATCH-14 quality boundary. It does not decide final
Frozen Input eligibility and does not create a `frozen_input_id` or
`frozen_input_hash`. It is not a Prediction or Score Engine decision.

## 2. Eligibility states

| State | Meaning |
|---|---|
| `ELIGIBLE` | All required inputs in the declared assessment scope satisfy their contracts. |
| `PARTIALLY_ELIGIBLE` | No hard blocker exists, but one or more optional/non-required features are not consumable. |
| `INELIGIBLE` | Inputs are valid and auditable, but the declared eligibility profile's required feature requirement is not met. |
| `BLOCKED` | An identity, time, provenance, integrity, future-data, unsupported-contract, or other hard safety blocker exists. |

`INELIGIBLE` is not `BLOCKED`. The distinction is mandatory and must not be
collapsed by an implementation.

## 3. Gate levels

Every eligibility record declares one level:

```text
FEATURE
DOMAIN
CANDIDATE_SET
```

Propagation is defined by `quality-gate-matrix@1.0.0`:

- optional feature `UNKNOWN` may make that feature non-eligible while the
  candidate set remains `PARTIALLY_ELIGIBLE`;
- an unavailable provider is excluded from its provider set, not automatically
  promoted to a market blocker;
- an official required market with `FUTURE_DATA` blocks its affected domain;
- canonical identity conflict or hash-integrity failure blocks the entire
  affected candidate set;
- unresolved conflict cannot be silently selected or relabeled as eligible.

## 4. Required record

An eligibility record contains:

- `eligibility_id`, `contract_version`, `level`, and `state`;
- exact subject feature/domain/candidate references and hashes;
- upstream quality assessment and gate record references;
- required/optional input summary;
- blocker and warning reason codes;
- cutoff/kickoff and time decision references;
- input, payload, provenance, and output hashes;
- positive revision and explicit supersedes reference for corrections.

The overall state is a quality/preparation decision only. It must never be
serialized as win probability, model confidence, betting confidence,
recommendation grade, or abstention.

## 5. Frozen Input relationship

BATCH-14 may emit a pre-Freeze eligibility record that V4-076 can later cite.
V4-076 remains the only approved implementation point for the final Frozen
Input and must independently validate its own contract. BATCH-14 does not emit
`FROZEN_INPUT_ELIGIBLE=true/false`, create Frozen Input, or provide a mock.
