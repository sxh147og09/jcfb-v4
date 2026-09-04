# JCFB V4 BATCH-11 Statistical Historical Input Governance Evidence

Decision: `V4-011-ADR-001`
Workspace: `F:\Projects\jcfb-v4`
Branch: `main`
Baseline HEAD: `70e2384922da8496a41ea74284ecbadfc6b57718`

## Resolution result

`BATCH-11 STATISTICAL HISTORICAL INPUT BLOCKER RESOLVED`

The source-match `POSTMATCH_ONLY` lifecycle is preserved. A completed source-match result/statistic may be used for a later target match only through `historical-statistical-input@1.0.0`, with source/target identity separation, exact visible revision/hash, attributable evidence, and target-cutoff eligibility.

## Governance artifacts

| Artifact | Result |
|---|---|
| Historical input contract | PASS — `historical-statistical-input@1.0.0` |
| Baseline config | PASS — `statistical-strength-config@1.0.0` |
| Baseline config hash | `sha256:eadb7e85c4e170ba922f4a5a404e1f28861951c954bb8c1c06ea90ad3ceaf653` |
| Source/target distinction | PASS — `source_match_id != target_match_id` |
| Target cutoff predicate | PASS — `availability_at <= target_prediction_cutoff_at < target_kickoff_at` |
| Target self-result rejection | PASS |
| Post-cutoff correction rejection | PASS |
| Minimum sample policy | PASS — family-specific thresholds are versioned |
| Sparse-data policy | PASS — no numeric value below minimum; explicit `UNKNOWN`/`INSUFFICIENT_SAMPLE` |
| Rolling/decay policy | PASS — max 20 matches or 730 days; exponential rank decay; 10-match half-life |
| League/season policy | PASS — explicit competition/season scope and transition mapping |
| Home/away policy | PASS — neutral `NOT_APPLICABLE`; unknown venue `BLOCKED` |
| Normalization policy | PASS — per eligible match; explicit competition-season baseline |
| Conflict/stale/future handling | PASS — preserve and exclude/block; no silent selection |
| Append-only correction | PASS — revision plus `supersedes_id` |
| Prediction boundary | PASS — no Prediction, Score Engine, recommendation, or betting output |
| V3.3.3 isolation | PASS |
| Production/Supabase boundary | PASS — no reads/writes |
| Migration boundary | PASS — no migration added/applied |

## Consistency checks

- BATCH-10 remains complete and no V4-041/V4-042/V4-043 implementation was added.
- BATCH-11 remains `V4-041` and `V4-042` in parallel, followed by `V4-043` serially.
- No task edge was added or removed from the approved DAG.
- Feature Bundle v2 remains upstream of downstream Frozen Input; no Frozen Input workaround was introduced.
- Data Flow's stale reverse `Frozen Input -> Feature Bundle` diagram edge was corrected to the approved `Feature Bundle -> Frozen Input` direction.
- Existing source-match state meanings and hash profiles were not renamed or reinterpreted.

## Tests and audits

| Check | Result |
|---|---|
| BATCH-11 governance targeted tests | PASS — 8/8 |
| Full repository tests | PASS — 361/361 |
| V4 data-contract validator | PASS — 11 contract files |
| V4 versioning validator | PASS — 85 passes, 0 failures |
| Historical eligibility tests | PASS |
| Future/cutoff/self-result tests | PASS |
| Sparse/config/hash tests | PASS |
| Dependency cycle audit | PASS — existing 100-task DAG has no approved cycle |
| Documentation flow-direction audit | PASS |
| `git diff --check` | PASS |
| Migration/Production/V3.3.3 path audit | PASS |

This evidence records governance resolution only. V4-041, V4-042, and V4-043 remain unimplemented until the subsequent BATCH-11 Scope & Entry Review returns PASS.
