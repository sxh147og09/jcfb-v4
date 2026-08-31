# JCFB V4 Integrity Rules 1.0

Status: V4-005 GOVERNANCE ARTIFACT

## Purpose

This catalogue translates Constitutional rules into checks that can be enforced at intake, feature construction, engine execution, freeze, review, publication, and promotion. A failed critical rule fails closed. These rules describe enforcement contracts, not implemented code.

## Rule catalogue

| Rule-ID | Description | Severity | Enforcement Stage | Failure State |
|---|---|---|---|---|
| INT-001 | `NO_FUTURE_INFORMATION`: every pre-match input is available by `prediction_cutoff_at` and before `kickoff_at` | CRITICAL | Timestamp Gate, Final Prediction Gate | `FUTURE_INFORMATION_LEAKAGE=TRUE`; `RUN_INVALID=TRUE` |
| INT-002 | `OFFICIAL_ODDS_NOT_FABRICATED`: official China Sports Lottery odds are sourced or explicitly unavailable | CRITICAL | Official Odds Intake, Data Quality Gate | `BLOCKED` or `UNAVAILABLE`; no fabricated value |
| INT-003 | `FROZEN_INPUT_IMMUTABLE`: a Frozen Input cannot be updated after its hash is formed | CRITICAL | Frozen Input creation and every subsequent write | `FROZEN_INPUT_MUTATION=TRUE`; run invalid |
| INT-004 | `FROZEN_PREDICTION_IMMUTABLE`: a Frozen Prediction is append-only and cannot be updated in place | CRITICAL | Freeze, Correction, Review | `FROZEN_PREDICTION_MUTATION=TRUE`; incident review required |
| INT-005 | `MODEL_VERSION_REQUIRED`: every formal model run identifies model and engine version | HIGH | Model Registry, Engine Run | `BLOCKED` |
| INT-006 | `CONFIG_HASH_REQUIRED`: every formal run records the configuration identity | HIGH | Engine Run, Frozen Input | `BLOCKED` |
| INT-007 | `IMPLEMENTATION_HASH_REQUIRED`: every formal run records implementation identity | HIGH | Engine Run, Tier A Gate | `BLOCKED` |
| INT-008 | `INPUT_HASH_REQUIRED`: every formal run records exact input identity | CRITICAL | Engine Run, Freeze | `BLOCKED`; A/B may be invalid |
| INT-009 | `OUTPUT_HASH_REQUIRED`: every formal output records deterministic output identity | HIGH | Engine Output, Frozen Prediction | `BLOCKED` |
| INT-010 | `PRE_KICKOFF_RUN_REQUIRED`: a formal pre-match run completes before kickoff under the declared cutoff | CRITICAL | Run Admission, Freeze | `RUN_INVALID=TRUE`; not Tier A |
| INT-011 | `PRODUCTION_SHADOW_ISOLATION`: Production, Shadow, and Experiment outputs and roles remain distinct | CRITICAL | Registry, Orchestrator, Publication | `ROLE_VIOLATION=TRUE`; Production path blocked |
| INT-012 | `NO_POSTMATCH_BACKFILL`: post-match result, review, or explanation cannot become pre-match input | CRITICAL | Result Intake, Feature Builder, Review | `FUTURE_INFORMATION_LEAKAGE=TRUE` |
| INT-013 | `MARKET_AVAILABILITY_EXPLICIT`: unavailable markets carry `market_available=FALSE` and `unavailable_reason` | HIGH | Official Odds Gate, Orchestrator | `UNAVAILABLE` or `BLOCKED`; no substitute odds |
| INT-014 | `AUDIT_REQUIRED`: intake, run, freeze, correction, result, review, Tier A, and promotion events are logged | HIGH | Every lifecycle transition | `BLOCKED`; no unlogged production operation |
| INT-015 | `SECRET_NOT_IN_REPOSITORY`: secrets and credential material are absent from Git and staged content | CRITICAL | Pre-commit, CI, Publication | Commit blocked; `SECURITY_INCIDENT` if bypassed |
| INT-016 | `TIER_A_NO_CHERRY_PICKING`: V4 Tier A uses predeclared complete samples beginning at Sample #001 | CRITICAL | Tier A Registration | `TIER_A_ELIGIBLE=FALSE` |
| INT-017 | `PUBLIC_WEB_READ_ONLY`: Public Web reads a projection and never executes or mutates a model | HIGH | Publication, Web boundary | Publication blocked; incident if exposed |
| INT-018 | `V333_ISOLATION`: V4 cannot modify V3.3.3 code, history, outputs, samples, or parameters | CRITICAL | Repository, Data, Benchmark | Operation blocked; isolation incident |

## Enforcement semantics

- `CRITICAL` failures fail closed and cannot be bypassed by a downstream layer.
- `HIGH` failures block the affected formal artifact until evidence is repaired through an allowed append-only path.
- A failure state is evidence, not a value to be normalized away.
- Repeating a run after a correction creates a new input, run, and output identity.
- A result discovered after a run cannot retroactively make the run valid.

## Minimum run evidence

An eligible formal engine run references `model_version`, `engine_version`, `implementation_hash`, `config_hash`, `input_hash`, `output_hash`, `run_at`, `runtime_environment`, the cutoff, and the Frozen Input identity. A stochastic run additionally records `random_seed` and `simulation_version`.

