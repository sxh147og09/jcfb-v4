# JCFB V4 Canonical Facts Schema 1.0

Status: V4-008 DATA CONTRACT DESIGN ARTIFACT

## 1. Purpose and boundary

This contract defines the canonical match identity and objective fact envelope consumed by the V4 data, odds, context, evidence, and result contracts. It is a read-only factual schema. It does not create a database schema, infer identity from a model output, or authorize a V3.3.3 change.

`OBJECTIVE_FACT` is the only allowed fact class in this contract. Team strength, market heat, upset risk, confidence, recommendation, and other interpretations belong downstream and must reference this object rather than modify it.

## 2. Canonical Match Identity Contract

The canonical identity fields are:

| Field | Type | Requiredness | Rule |
|---|---|---|---|
| `object_id` | UUID/UUIDv7 string | REQUIRED | Stable record identity. |
| `contract_version` | string | REQUIRED | `canonical-match@MAJOR.MINOR.PATCH`. |
| `match_id` | UUID/UUIDv7 string | REQUIRED | Permanent cross-contract match identity. It is not generated from a display name. |
| `match_identity_key` | string | REQUIRED derived index | `data_date + ":" + official_match_no`; useful for daily lookup only. |
| `data_date` | `YYYY-MM-DD` | REQUIRED | Official lottery data day in the declared local timezone. |
| `official_match_no` | non-empty string | REQUIRED | Preserve leading zeros. Unique only within `data_date`; never a cross-day key by itself. |
| `competition_id` | stable string | REQUIRED | Canonical competition identity. |
| `competition_name` | string | REQUIRED display value | Source display name; not the competition primary key. |
| `kickoff_at` | ISO-8601 timezone-aware timestamp | REQUIRED | Exact scheduled kickoff with an explicit offset or IANA timezone interpretation. |
| `timezone` | IANA timezone string | REQUIRED | Timezone used to interpret `data_date`, kickoff, and cutoff. |
| `home_team_id` / `away_team_id` | stable strings | REQUIRED | Canonical team identities; must be distinct. |
| `home_team_name` / `away_team_name` | string | REQUIRED display values | Source/canonical display names; never permanent keys. |
| `official_handicap` | typed object | CONDITIONAL | Required when an official handicap exists or when RQSPF is available; otherwise explicit `UNAVAILABLE`/`UNKNOWN` with reason. |
| `match_status` | enum | REQUIRED | One of the governed `match_status` values. |
| `source` | string/object | REQUIRED | Attributable fixture authority. |
| `source_type` | enum | REQUIRED | Usually `OFFICIAL_FEED`, `OFFICIAL_DOCUMENT`, or an attributed fallback. |
| `source_reference` | string | REQUIRED | Replayable source reference; no secret material. |

The common metadata envelope in `V4_DATA_CONTRACT.md` is required in addition to these identity fields.

`official_handicap` has this shape when available:

```json
{
  "status": "AVAILABLE",
  "line": -1.0,
  "unit": "goals",
  "source_reference": "ref://official/fixture/20260901/001"
}
```

If the official handicap is not supplied, the object must remain explicit:

```json
{
  "status": "UNAVAILABLE",
  "reason": "OFFICIAL_HANDICAP_NOT_SUPPLIED",
  "source_reference": "ref://official/fixture/20260901/001"
}
```

An unknown handicap is different:

```json
{
  "status": "UNKNOWN",
  "reason": "SOURCE_TIME_OR_VALUE_CANNOT_BE_VERIFIED"
}
```

## 3. Identity and conflict rules

1. `official_match_no` cannot be used alone as a cross-day unique key. `data_date + official_match_no` is a daily uniqueness constraint; `match_id` is the stable cross-contract identity.
2. `kickoff_at` must include a timezone offset and must resolve consistently with `timezone`. A timestamp without timezone is invalid for a formal record.
3. `home_team_name` and `away_team_name` are display values. Stable `home_team_id` and `away_team_id` are separate fields and are used for references.
4. The two team IDs must not be equal. A name collision, alias ambiguity, duplicate official number, conflicting kickoff, or conflicting home/away orientation is an identity conflict.
5. Identity conflict handling is fail-closed: set the record `status=BLOCKED`, set `identity_resolution_state=REQUIRES_REVIEW`, retain all conflicting source references, and do not silently merge records.
6. A corrected identity creates a new append-only canonical revision with a new payload/provenance hash. It does not mutate a Frozen Input that already referenced the old identity.
7. `match_status=FINISHED` is an objective status only. It does not authorize a result to enter a pre-match Frozen Input.

## 4. Minimum legal JSON example

```json
{
  "object_id": "019a0000-0000-7000-8000-000000000001",
  "contract_version": "canonical-match@1.0.0",
  "created_at": "2026-09-01T09:00:00+08:00",
  "source_timestamp": "2026-09-01T08:55:00+08:00",
  "observed_at": "2026-09-01T09:00:00+08:00",
  "ingested_at": "2026-09-01T09:01:00+08:00",
  "effective_at": "2026-09-01T00:00:00+08:00",
  "source": "China Sports Lottery official fixture source",
  "source_type": "OFFICIAL_FEED",
  "source_reference": "ref://official/fixture/20260901/001",
  "confidence": {
    "state": "ASSESSED",
    "score": 0.99,
    "basis": "Official fixture source with a timezone-aware schedule"
  },
  "provenance_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "payload_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "status": "AVAILABLE",
  "metadata": {
    "hash_exclusions": ["created_at", "ingested_at"]
  },
  "match_id": "019a0000-0000-7000-8000-000000000002",
  "match_identity_key": "2026-09-01:001",
  "data_date": "2026-09-01",
  "official_match_no": "001",
  "competition_id": "competition-example-001",
  "competition_name": "Example League",
  "kickoff_at": "2026-09-01T19:35:00+08:00",
  "timezone": "Asia/Shanghai",
  "home_team_id": "team-example-home-001",
  "home_team_name": "Example Home",
  "away_team_id": "team-example-away-001",
  "away_team_name": "Example Away",
  "official_handicap": {
    "status": "AVAILABLE",
    "line": -1.0,
    "unit": "goals",
    "source_reference": "ref://official/fixture/20260901/001"
  },
  "match_status": "SCHEDULED",
  "identity_resolution_state": "RESOLVED",
  "identity_conflicts": []
}
```

## 5. Validation rules

### Required fields

All fields in section 2 marked `REQUIRED`, the common metadata fields marked required in `V4_DATA_CONTRACT.md`, and `identity_resolution_state` are required. `identity_conflicts` is required as an array, including an empty array only when identity resolution is `RESOLVED`.

### Type and range checks

- UUID fields must be valid UUID/UUIDv7 strings according to the runtime identity policy.
- `data_date` must be a real calendar date; `official_match_no` is a non-empty string and preserves leading zeros.
- `home_team_id != away_team_id`.
- `kickoff_at` and all supplied timestamps must parse as timezone-aware ISO-8601 values.
- `official_handicap.line` is numeric when `status=AVAILABLE`; the source sign convention must be retained and documented.
- `match_status`, `source_type`, and all state fields must use governed enums.

### Timestamp checks

- `observed_at` cannot precede a source event it claims to observe without a declared source correction.
- `data_date` is interpreted in `timezone`.
- A consuming pre-match run must separately verify `prediction_cutoff_at < kickoff_at` and the source availability boundary; this schema does not turn an ingested fact into a pre-match-eligible fact automatically.

### Referential and identity checks

- `match_identity_key` must equal exactly `data_date + ":" + official_match_no`.
- Every snapshot, context, evidence, feature, prediction, and result reference must use `match_id`, not a display name or official number alone.
- Any unresolved source collision sets `status=BLOCKED` and `identity_resolution_state=REQUIRES_REVIEW`.

### Hash and role checks

- `provenance_hash` and `payload_hash` must be present and format-valid.
- The canonical facts schema carries no `role`, prediction, confidence grade, recommendation, or engine output. Adding those as fact fields is a boundary violation and requires a separate contract.
- Official Result may reference this identity after kickoff, but a result reference cannot enter a pre-match input.

## 6. Hash boundary and compatibility

The logical payload includes `match_id`, `data_date`, `official_match_no`, competition identity/name, kickoff/timezone, both team IDs/names, official handicap state/value, `match_status`, identity resolution state, and declared source identity. It excludes the common transport timestamps listed as volatile in `V4_DATA_CONTRACT.md` unless a correction contract explicitly makes one business-relevant.

Adding an optional fact field is `MINOR`; changing a team identity field's meaning, timezone rule, requiredness, or hash interpretation is `MAJOR`; a wording-only clarification is `PATCH`. Historical match IDs and hashes are never reused.
