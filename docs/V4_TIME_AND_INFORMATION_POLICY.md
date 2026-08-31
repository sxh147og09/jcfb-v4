# JCFB V4 Time and Information Policy 1.0

Status: V4-005 GOVERNANCE ARTIFACT

## 1. Purpose

This policy defines the temporal boundary for V4 pre-match runs, result intake, review, calibration, and promotion evidence. Time is part of input identity. A fact with an unknown or unverifiable availability time cannot be treated as eligible pre-match information.

## 2. Required timestamps

| Timestamp | Meaning | Governance use |
|---|---|---|
| `kickoff_at` | Scheduled or officially confirmed match start time in its canonical timezone | Upper boundary for pre-match input |
| `prediction_cutoff_at` | Declared latest time at which a pre-match run may accept information | Cutoff for input admission |
| `source_published_at` | Time a source published a claim or snapshot | Evidence of public availability |
| `source_timestamp` | Time attached to the source observation or market snapshot | Source-specific observation identity |
| `observed_at` | Time V4 or an intake operator observed/captured the source | Future-information and screenshot checks |
| `ingested_at` | Time V4 accepted the source record | Audit only; never a substitute for availability |
| `model_run_at` | Time an engine or model executed | Run ordering and audit |
| `frozen_at` | Time Frozen Input or Frozen Prediction became immutable | Freeze boundary |
| `result_known_at` | Time an official result became available to the result path | Separates post-match evaluation |
| `reviewed_at` | Time a post-match review was recorded | Review audit and calibration lineage |

`Kickoff Time`, `Screenshot Time`, `Odds Time`, `Prediction Time`, `Freeze Time`, and `Public Page Time` are distinct business concepts. They must not be collapsed into a generic “updated at” field.

## 3. Formal pre-match rule

For every input used by a formal pre-match run:

```text
input_timestamp <= prediction_cutoff_at < kickoff_at
```

`input_timestamp` is the earliest defensible time at which the information was available for the declared source semantics. It may require `source_published_at`, `source_timestamp`, and `observed_at`; `ingested_at` alone never makes a fact eligible.

The cutoff must be explicit, timezone-aware, and retained in the Frozen Input. If `kickoff_at`, `prediction_cutoff_at`, or the relevant input time cannot be established, the run is `BLOCKED` or `UNKNOWN_TIME`, not silently admitted.

## 4. Information states

### `PREMATCH_ALLOWED`

Use only when identity is valid, the input time is known, and the formal inequality passes. The fact may enter a pre-match Frozen Input subject to provenance and quality checks.

### `POSTMATCH_ONLY`

Use for information that becomes available at or after kickoff, including match events, official result, post-match statistics, and post-match explanation. It may enter Review or Match Explanation but not a pre-match run.

### `UNKNOWN_TIME = BLOCKED`

Use when the publication or observation time cannot be verified, timestamps conflict, timezone conversion is ambiguous, or the system cannot prove that information was available by the cutoff. The fact requires review and remains blocked until proven eligible.

### `REQUIRES_REVIEW / BLOCKED`

Use for a claim with a plausible time but insufficient evidence, such as an undated injury report or a screenshot without reliable capture context. No formal run may treat it as eligible by default.

### `FUTURE_INFORMATION_LEAKAGE`

Use when an input is discovered to be after the cutoff, after kickoff, or derived from post-match knowledge. The run is invalid regardless of whether the leaked information changed the prediction.

## 5. Admission procedure

1. Resolve the canonical match identity and timezone.
2. Record `kickoff_at` and `prediction_cutoff_at` before selecting model inputs.
3. Resolve source publication, observation, or snapshot time for every candidate fact.
4. Compare the defensible input time to the cutoff and kickoff.
5. Retain the decision, source reference, and reason in provenance and audit records.
6. Reject future, ambiguous, conflicting, stale, or unverified inputs according to the quality policy.
7. Freeze the accepted set and its `frozen_input_hash` before formal prediction.

## 6. Required examples

| Scenario | Classification | Reason |
|---|---|---|
| Odds snapshot captured five minutes before kickoff and before cutoff | `PREMATCH_ALLOWED` | Observation and source time are before kickoff and eligible cutoff |
| Official Starting XI published one hour before kickoff | `PREMATCH_ALLOWED` | Publication time is verified before cutoff |
| Red card occurs at the 10th minute | `POSTMATCH_ONLY` | Match event exists after kickoff |
| xG published after the final whistle | `POSTMATCH_ONLY` | Post-match statistic cannot enter pre-match features |
| Injury message has no verifiable publication or observation time | `REQUIRES_REVIEW / BLOCKED` | Eligibility cannot be proven |
| Odds snapshot published after the prediction cutoff but before kickoff | `UNKNOWN_TIME = BLOCKED` / future relative to run | It was unavailable at the declared cutoff |
| Official result received after the match | `POSTMATCH_ONLY` | Result belongs to evaluation and review |
| Screenshot timestamp conflicts with source timestamp | `UNKNOWN_TIME = BLOCKED` | Conflicting time evidence must not be silently resolved |

## 7. Leakage consequences

When future information is detected:

```text
FUTURE_INFORMATION_LEAKAGE = TRUE
RUN_INVALID = TRUE
TIER_A_ELIGIBLE = FALSE
PROMOTION_EVIDENCE = FALSE
```

The invalid run, source record, decision, and evidence remain available. Removing a leaked input or deleting the evidence does not restore eligibility. A new clean run requires a new input identity and new hashes.

## 8. Result and review boundary

`result_known_at` opens the post-match path. MODEL EVALUATION consumes Frozen Prediction plus Official Result. MATCH EXPLANATION may consume events, xG, red cards, technical statistics, and interviews, but it cannot write these facts back into pre-match input or historical Prediction Evaluation.

## 9. Publication time boundary

`canonical_latest_update_at` is derived only from the maximum real business-data update time in the read projection. Page build time, cache refresh time, and HTML generation time are not data timestamps and cannot be used to make a stale fact appear current.

