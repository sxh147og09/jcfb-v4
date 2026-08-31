# JCFB V4 Engine and Layer Boundaries

Status: V4-004 ARCHITECTURE ARTIFACT

## Purpose

This document defines ownership and prohibited cross-layer behavior. A component may consume only the inputs declared for its layer, and it may publish only artifacts owned by that layer. Boundary violations are architecture defects and must be recorded as blockers rather than silently repaired downstream.

## Boundary matrix

| Layer / component | May consume | May produce | Must never do |
|---|---|---|---|
| Canonical Data Layer | Official, external, team, and result sources | Canonical objective facts and immutable source snapshots | Generate predictions, confidence, model output, or review conclusions |
| Match Identity | Match identity evidence and competition metadata | Canonical match ID, team identity, kickoff and timezone | Merge uncertain matches or infer identity from a prediction |
| Official Odds Intake | Official China Sports Lottery snapshots | SPF, RQSPF, Total Goals, Exact Score, Half-Full odds with provenance | Fabricate missing odds, rewrite an official snapshot, or use a future snapshot |
| External Market Intake | European 1X2, Asian Handicap, Over/Under sources | Timestamped external market facts | Treat an external quote as official China Sports Lottery odds |
| Data Quality Engine 4.0 | Facts, snapshots, timestamps, provenance, availability | Quality scores and `BLOCKERS[]` | Turn a blocked input set into Production Prediction |
| Timestamp / Future-Data Gate | Source timestamps, observed time, cutoff, kickoff | Eligibility decision and rejection reason | Accept information published or observed after the pre-match cutoff |
| Provenance / Audit Ledger | Accepted facts and processing events | Source lineage, hashes, append-only audit events | Delete history or hide a conflicting source |
| Football Intelligence Engine 4.0 | Valid team, player, coach, tactical, schedule, weather, and pitch facts | Football features, context confidence, conflicts, risk flags | Output final SPF, final score, or modify official odds |
| Evidence Graph 1.0 | Claims and source evidence | Claim lifecycle, evidence hash, contradiction state | Admit an unsupported claim as trusted context |
| Market Intelligence Engine 4.0 | Official and external odds time series | Market features, movement, heat, divergence, trap-risk signal | Assert bookmaker intent, fabricate market facts, or override football facts |
| Feature Representation Layer 4.0 | Validated data and intelligence outputs | Versioned feature bundles and `feature_snapshot_hash` | Read raw unversioned input directly into an engine or rewrite source facts |
| Statistical Strength Model 4.0 | Versioned features and pre-match facts | Strength, attack, defence, home advantage, and opponent-adjusted signals | Make a large rating change from a short streak alone or read results from the future |
| Outcome Engine 4.0 | Its declared feature bundle and config | Home / Draw / Away probabilities | Mechanically determine all other markets or edit another engine's output |
| Handicap Engine 4.0 | Its declared feature bundle and config | Handicap outcome and goal-difference distribution | Copy Outcome output as its own judgment without an independent run |
| Goals Engine 4.0 | Its declared feature bundle and config | 0–7+ goal distribution and bands | Treat score selection as its distribution or read post-match goals |
| HTFT Engine 4.0 | Its declared feature bundle and config | Nine Half-Full state probabilities | Infer a formal state without recording its own inputs and version |
| Score Engine 4.0 | Pre-match score features, context, market signals, and config | Dynamic lambdas, score matrix, full score distribution | Read official results, use post-match data, or silently choose an undocumented algorithm |
| Score Candidate Generator 4.0 | Score distribution and declared selector config | Top20 candidate scores | Alter the distribution to make a preferred score appear |
| Exact Score Selector 4.0 | Candidate scores, distribution, scenario metadata | Top1, Top2, Top3, Top5, Top10 selections | Be conflated with distribution estimation or hide candidate coverage |
| Scenario Diversity Selector | Candidate scores and match-script labels | Diverse candidate set and diversity diagnostics | Pretend adjacent scores are independent scenarios when they share one path |
| Match Simulation Engine 1.0 | Pre-match features, engine outputs, and simulation config | State-path probabilities, score summaries, variances, scripts | Read official results during pre-match execution or modify frozen inputs |
| Match Script Engine 4.0 | Pre-match features and simulation state | Script labels and script probabilities | Replace Score Distribution or claim a script is a confirmed fact |
| Cross-Model Consensus Engine 4.0 | Raw statistical, intelligence, market, engine, simulation, and upset outputs | Votes, support, conflicts, consensus score | Simple-average away disagreement or discard raw engine outputs |
| Model Disagreement Index 1.0 | Raw probability distributions and votes | Level and numeric disagreement score | Treat an average as agreement without measuring dispersion |
| Uncertainty Engine 4.0 | Quality, context, market, disagreement, entropy, variance, calibration | Uncertainty, interval, confidence grade | Equate model probability with confidence |
| Risk & Abstention Engine 4.0 | Quality, market, context, upset, volatility, and conflict signals | Risk state and abstention decision | Force a strong recommendation for every match |
| Upset Engine 4.0 | Pre-match features, market risk, and context | Upset probability, type, drivers, confidence | Increase upset probability merely to find a cold result |
| Five-Market Orchestrator 4.0 | Independent outputs plus consistency and risk signals | SPF, RQSPF, Goals, Exact Score, Half-Full package | Let Outcome Engine mechanically produce every market |
| Prediction Consistency Engine 4.0 | Independent market outputs and score/script outputs | `CONSISTENCY_CONFLICT` and diagnostics | Silently edit an engine output to make the package look consistent |
| Final Prediction Gate 4.0 | Quality, odds, timestamps, completeness, consistency, risk decisions | Formal prediction eligibility and rejection reasons | Bypass a failed gate or issue a formal prediction on blocked inputs |
| Frozen Input 4.0 | Exact pre-match facts, snapshots, features, versions, and configs | Frozen input record and `frozen_input_hash` | Add new information after freezing or make roles use incomparable inputs |
| Frozen Prediction 4.0 | Gated prediction package and frozen input | Immutable prediction and `output_hash` | Update in place, delete history, or overwrite a prior freeze |
| Production Role | Approved V4 Production configuration and frozen inputs | Formal V4 prediction | Consume Shadow or Experiment output as Production without Promotion Review |
| Shadow Role | Same pre-match frozen input and shadow configuration | Isolated shadow prediction | Modify Production, public output, or Production configuration |
| Experiment Role | Declared research input and experiment configuration | Research output and diagnostics | Appear in formal public prediction or silently affect Production |
| Postmatch Result Intake | Official result and post-match facts | Result record attached after kickoff | Feed post-match information into a pre-match run |
| Postmatch Review Engine 4.0 | Frozen Prediction, Official Result, and separately labeled post-match statistics | Prediction evaluation and match explanation | Overwrite Frozen Prediction or rewrite pre-match inputs |
| Error Attribution Engine 4.0 | Frozen outputs, result, and review evidence | Diagnostic error category and evidence | Modify model parameters automatically after one match |
| Calibration Engine 4.0 | Historical frozen outcomes and evaluation records | Brier, Log Loss, reliability, sharpness, calibration evidence | Backfill or alter historical frozen predictions |
| Tier A Qualification | Complete V4 frozen records, result, hashes, and gates | V4 Tier A qualification from Sample #001 | Import V3.3.3 Tier A labels or treat an incomplete run as qualified |
| Cross-Version Benchmark | Separate V3.3.3 and V4 frozen records plus shared objective facts | Comparison metrics | Merge, mutate, or recalibrate V3.3.3 outputs |
| Canonical Prediction Store | Gated, frozen model outputs | Immutable read projection source | Accept an unfrozen or untraceable prediction |
| Public Read Projection / Web | Canonical prediction store | Read-only, cached, incrementally published view | Run models, write predictions, or bypass a gate |

## Absolute prohibitions

The following are explicit architecture failures:

- Data Layer generating a prediction
- Football Intelligence modifying official odds
- Market Intelligence claiming bookmaker intent as fact
- Score Engine reading official results or future information
- Postmatch Review cannot overwrite Frozen Prediction.
- Postmatch Review overwriting Frozen Prediction
- Shadow modifying Production
- Public Web running a model
- Outcome Engine mechanically deriving all five markets
- Probability being presented as confidence without an uncertainty/calibration layer
- A blocked quality or future-data gate being silently ignored

## Boundary violation handling

Every violation must be recorded with the component, input artifact, output artifact, timestamp, model role, and reason. The default response is `BLOCKED` or `NOT_IMPLEMENTED`; downstream components must not silently normalize away the violation.
