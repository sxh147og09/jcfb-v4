# V4 BATCH-15 Four Engine Training Profiles

Status: **GOVERNANCE ACTIVE / NO FITTED ARTIFACTS**

The canonical machine-readable profiles are embedded in
`config/prediction_training/v4_prediction_training_governance.json`. They are
independent profiles sharing only the training infrastructure contract.

| Role | Target | Required model identity | Independence rule |
|---|---|---|---|
| `OUTCOME` | `H/D/A` | Own feature profile, parameters, metrics, and artifact hash | Cannot derive another role |
| `HANDICAP` | `H/D/A` using cutoff-bound official RQSPF handicap | Own handicap ref/value and parameter artifact | Cannot copy Outcome output |
| `GOALS` | `0..6, 7+` | Own count-distribution feature profile and parameters | Cannot derive from Outcome |
| `HTFT` | Nine official HTFT states | Own halftime/fulltime feature profile and parameters | Cannot combine a heuristic with another engine |

Each profile must declare exact features, missing-state behavior, target class
ordering, candidate family, search configuration/hash, dataset/split hashes,
and deterministic fitting implementation before fitting. No profile currently
has a training dataset, fitted parameters, or `APPROVED_FOR_ENGINE` artifact.
