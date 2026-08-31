# JCFB V4 Agent Governance

These rules apply to all work inside the JCFB V4 repository.

1. Never modify JCFB V3.3.3 from V4 work.
2. V4 is an independent model, not a rename of V3.3.3.
3. Never use post-match information in a pre-match model run.
4. Never use future odds.
5. Never modify historical Frozen Prediction.
6. Never fabricate missing China Sports Lottery odds.
7. Missing market must be explicitly marked unavailable.
8. Every model run must eventually support:
   - `model_version`
   - `implementation_hash`
   - `config_hash`
   - `input_hash`
   - `output_hash`
9. Production and Shadow outputs must remain distinguishable.
10. Model experiments must never silently affect Production.
11. Objective facts may be shared across model versions. Predictions and model outputs must remain isolated.
12. No automatic model promotion without a formal Promotion Gate.
13. A completed checklist item requires engineering evidence.
14. If information is unknown, record `UNKNOWN` / `BLOCKED` / `NOT_IMPLEMENTED`. Never invent completion.

## Repository boundary

All V4 changes must stay inside this repository. The V3.3.3 repository, database history, frozen predictions, historical predictions, reviews, and model parameters are protected external assets. They must not be copied, migrated, renamed, or edited as part of V4 bootstrap work.

## Evidence boundary

A task may be marked complete only when its design is finalized, an engineering artifact exists, validation has completed, documentation is present, and Git traceability exists. Discussion alone is not completion evidence.

