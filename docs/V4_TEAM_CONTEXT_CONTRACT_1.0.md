# JCFB V4 Team Context Contract 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and boundary

This contract turns time-valid football context into a structured, provenance-preserving object. It is still an objective/context fact boundary: it may state what an attributed source reports, but it does not output SPF, handicap, goals, exact score, Half-Full, confidence grade, or recommendation.

A Team Context object is tied to one `match_id`, one team side, and one declared `as_of_at`/cutoff. Context from after kickoff cannot enter a pre-match object. Conflicting context remains visible and blocks or downgrades the consuming gate according to the applicable policy.

## 2. Required structure

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` / `team_context_id` | UUID/UUIDv7 | REQUIRED | Stable context identity. |
| `contract_version` | string | REQUIRED | `team-context@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 | REQUIRED | Canonical match reference. |
| `team_id` / `team_display_name` | stable ID/string | REQUIRED | ID and display name are separate. |
| `side` | `HOME`/`AWAY` | REQUIRED | Must agree with the canonical match identity. |
| `as_of_at` | timezone-aware timestamp | REQUIRED | Context validity boundary used by the consumer. |
| `injuries` | `FactCollection` | REQUIRED | Confirmed injuries, or explicit `UNKNOWN`/`NONE_CONFIRMED`. |
| `suspensions` | `FactCollection` | REQUIRED | Confirmed suspensions, or explicit state. |
| `lineup_status` | `ContextValue` | REQUIRED | `CONFIRMED`, `PROJECTED`, `UNKNOWN`, `NOT_VERIFIED`, `BLOCKED`, or source-specific governed state. |
| `starting_xi` | `ContextCollection` | REQUIRED | Confirmed/projected players or explicit unknown; never assume a complete lineup. |
| `coach` | `ContextValue` | REQUIRED | Current coach fact and source state. |
| `tactical_style` | `ContextValue` | REQUIRED | Attributed description; interpretation remains labeled as context/analysis. |
| `motivation` | `ContextValue` | REQUIRED | Source-backed context; never a certainty claim. |
| `schedule_pressure` | `ContextValue` | REQUIRED | Fixture congestion/priority context with time boundary. |
| `fatigue` | `ContextValue` | REQUIRED | Structured state or explicit unknown. |
| `travel` | `ContextValue` | REQUIRED | Travel burden/source state. |
| `weather` | `ContextValue` | REQUIRED | Forecast/observed weather available by cutoff, with source time. |
| `pitch` | `ContextValue` | REQUIRED | Pitch state/source or explicit unknown. |
| `source_summary` | array of source refs | REQUIRED | Sources supporting the fields; may be empty only with `status=UNKNOWN`/`BLOCKED` and reason. |
| `context_confidence` | `ConfidenceValue` | REQUIRED | Confidence in context completeness/provenance, not prediction probability. |
| `conflicts` | array | REQUIRED | Conflicting claims and resolution status; empty only when no conflict was found and the search scope is declared. |
| common metadata | typed metadata | REQUIRED | Source/time/provenance/hash/status fields. |

### 2.1 Context value types

`ContextValue` has a state, an optional typed value, supporting references, and a reason when the value is not usable:

```json
{
  "state": "AVAILABLE",
  "value": "HIGH",
  "basis_refs": ["evidence-001"],
  "reason": "NOT_APPLICABLE"
}
```

`FactCollection` has:

```json
{
  "state": "NONE_CONFIRMED",
  "items": [],
  "basis_refs": ["evidence-002"],
  "reason": "Official team report found no confirmed absences"
}
```

When the state is `UNKNOWN`, `items` must be omitted, not set to an empty array. When the state is `NONE_CONFIRMED`, `items=[]` is allowed only with a source that explicitly confirms the negative fact. A source that simply says nothing is not confirmation.

`starting_xi` uses `state=CONFIRMED` only for an attributable confirmed lineup, `state=PROJECTED` for a clearly labeled projection, and `state=UNKNOWN` when no defensible lineup is available. A projected XI must not be relabeled as confirmed.

## 3. Unknown, negative, and conflict rules

- `UNKNOWN` means V4 does not know the state. It is not 鈥渘o injury鈥? 鈥渘o suspension鈥? 鈥渘o rotation鈥? 鈥渟table lineup鈥? or zero.
- `NONE_CONFIRMED` means the accepted source explicitly confirmed an empty collection. It is a positive factual claim with provenance.
- `NOT_VERIFIED` means a claim exists but the required verification has not passed; it cannot silently become `AVAILABLE`.
- `CONFLICTED`/`conflicts[]` retain both claims, source references, timestamps, and the unresolved resolution state. Do not choose a preferred claim silently.
- `STALE` means the claim exceeds its freshness/expiry policy. It remains auditable but is not a fresh pre-match input.
- `BLOCKED` means a gate prevents use; it is not a value and cannot be converted to an average or default.

The `context_confidence` value measures source coverage, verification, freshness, and conflict level. It is not a probability of a match outcome and not the prediction's confidence grade.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000201",
  "team_context_id": "019a0000-0000-7000-8000-000000000201",
  "contract_version": "team-context@1.0.0",
  "created_at": "2026-09-01T11:00:00+08:00",
  "source_timestamp": "2026-09-01T10:50:00+08:00",
  "observed_at": "2026-09-01T11:00:00+08:00",
  "ingested_at": "2026-09-01T11:00:05+08:00",
  "effective_at": "2026-09-01T10:50:00+08:00",
  "source": "Example club and competition reports",
  "source_type": "CLUB_STATEMENT",
  "source_reference": "ref://context/20260901/001/home/105000",
  "confidence": {"state": "ASSESSED", "score": 0.86, "basis": "Multiple time-valid attributed sources"},
  "provenance_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  "payload_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
  "status": "AVAILABLE",
  "metadata": {"hash_exclusions": ["created_at", "ingested_at"]},
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "team_id": "team-example-home-001",
  "team_display_name": "Example Home",
  "side": "HOME",
  "as_of_at": "2026-09-01T10:50:00+08:00",
  "injuries": {
    "state": "NONE_CONFIRMED",
    "items": [],
    "basis_refs": ["evidence-example-injury-clearance-001"],
    "reason": "Accepted team report explicitly confirmed no confirmed injury absences"
  },
  "suspensions": {
    "state": "UNKNOWN",
    "basis_refs": [],
    "reason": "No source in the accepted search scope confirms suspension status"
  },
  "lineup_status": {"state": "PROJECTED", "value": "PROJECTED", "basis_refs": ["evidence-example-lineup-001"]},
  "starting_xi": {
    "state": "PROJECTED",
    "players": ["player-example-01", "player-example-02"],
    "basis_refs": ["evidence-example-lineup-001"],
    "reason": "Projected XI; not a confirmed starting lineup"
  },
  "coach": {"state": "AVAILABLE", "value": {"coach_id": "coach-example-001", "display_name": "Example Coach"}, "basis_refs": ["evidence-example-coach-001"]},
  "tactical_style": {"state": "AVAILABLE", "value": "High press with wide progression", "basis_refs": ["evidence-example-tactic-001"]},
  "motivation": {"state": "NOT_VERIFIED", "basis_refs": ["evidence-example-motivation-001"], "reason": "Reported priority is not independently verified"},
  "schedule_pressure": {"state": "AVAILABLE", "value": {"matches_in_window": 3, "window_days": 10}, "basis_refs": ["evidence-example-schedule-001"]},
  "fatigue": {"state": "UNKNOWN", "basis_refs": [], "reason": "No sufficiently granular time-valid workload source"},
  "travel": {"state": "AVAILABLE", "value": {"travel_class": "LOW", "distance_km": 120}, "basis_refs": ["evidence-example-travel-001"]},
  "weather": {"state": "AVAILABLE", "value": {"temperature_c": 24, "precipitation_risk": "LOW"}, "basis_refs": ["evidence-example-weather-001"]},
  "pitch": {"state": "UNKNOWN", "basis_refs": [], "reason": "Pitch condition not reported by an accepted source"},
  "source_summary": ["ref://context/20260901/001/home/105000"],
  "context_confidence": {"state": "ASSESSED", "score": 0.86, "basis": "Some fields are verified; lineup is projected and fatigue/pitch remain unknown"},
  "conflicts": []
}
```

## 5. Validation rules

### Required and type checks

- All fields in section 2 marked required and all common required metadata are present.
- `side` is `HOME` or `AWAY`; `team_id` matches the corresponding canonical team ID.
- Every `FactCollection` has a state. `items=[]` is valid for `NONE_CONFIRMED`, invalid as a substitute for `UNKNOWN`.
- `starting_xi.players` is present only for `CONFIRMED` or `PROJECTED`; each player has a stable ID or a declared `NOT_VERIFIED` state.
- `context_confidence.score` is in `[0,1]` only when assessed; it is not an outcome probability.

### Source and time checks

- Every non-unknown value has at least one source/evidence reference.
- `as_of_at` and all source availability times must be no later than the consumer's `prediction_cutoff_at` for a pre-match run.
- A post-kickoff source or post-match lineup confirmation sets the relevant field `BLOCKED`/`FUTURE_DATA` for pre-match use; it is not silently retained as if known earlier.
- Expired facts use `STALE` and retain `expires_at`; the engine cannot treat stale context as current without a governed policy.

### Conflict, referential, and hash checks

- `conflicts=[]` is allowed only when the declared source search scope found no conflict. Otherwise each conflict contains both claim refs and resolution state.
- `basis_refs` resolve to Evidence objects; source references must remain replayable.
- `match_id` and `team_id` resolve to Canonical Facts; display names are never join keys.
- `provenance_hash`, `payload_hash`, and the declared specialized hash must be format-valid and recomputable.

### Role and leakage checks

- Team Context has no authority to write a Prediction or official odds.
- A Production/Shadow Frozen Input may reference only context accepted before the cutoff.
- Experiment context may be different only when the experiment declares its alternate input identity; it cannot be relabeled as Forward Shadow evidence.

## 6. Hash and compatibility boundary

The logical payload includes `match_id`, `team_id`, `side`, `as_of_at`, each context field's state/value/basis references/reason, and the conflict list. It includes source/evidence references needed to reproduce the context. It excludes transport-only timestamps and non-authoritative trace metadata.

Adding a new optional context category is `MINOR`; changing `UNKNOWN`, `NONE_CONFIRMED`, or `PROJECTED` semantics, changing a field type, or allowing post-kickoff facts into pre-match context is `MAJOR`; a wording clarification is `PATCH`. Context corrections are new append-only objects.
