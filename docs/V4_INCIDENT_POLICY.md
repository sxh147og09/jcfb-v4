# JCFB V4 Incident Policy 1.0

Status: V4-005 COMPLETE

## 1. Purpose

This policy defines incident classes, severity, containment, evidence preservation, communication, recovery, and closure. Incidents must not be silently repaired by deleting records, changing model output, or rewriting history.

## 2. Incident classes

- `DATA_INCIDENT` — incorrect identity, corrupted fact, fabricated odds, provenance failure, or materially conflicting data admitted to a formal path
- `MODEL_INCIDENT` — wrong model identity, unauthorized parameter/config change, incorrect engine role, or invalid output lineage
- `TIME_LEAKAGE_INCIDENT` — post-cutoff, post-kickoff, future odds, result, or post-match evidence entered a pre-match run
- `FREEZE_INTEGRITY_INCIDENT` — Frozen Input or Frozen Prediction mutated, overwritten, deleted, or detached from its hashes
- `SECURITY_INCIDENT` — API key, password, token, cookie, Supabase Service Role Key, private credential, or unauthorized access exposed or committed
- `PUBLICATION_INCIDENT` — public read projection shows stale, wrong, non-frozen, non-production, or unauthorized output, or bypasses read-only rules

## 3. Severity levels

| Severity | Meaning | Default response |
|---|---|---|
| `SEV-1` | Integrity, security, or Production failure that can invalidate formal predictions or historical evidence | Immediately stop affected Production path, preserve evidence, notify owner, contain, investigate, and require formal recovery approval |
| `SEV-2` | Material Shadow, Experiment, data, model, or publication failure with contained Production impact | Pause affected role/path, preserve evidence, correct through approved revision, and review before restart |
| `SEV-3` | Limited publication, freshness, provenance, or operational failure without known formal-output corruption | Contain the affected component, record impact, repair, and verify |
| `SEV-4` | Minor anomaly or near miss with no material output impact | Record, monitor, and address through normal maintenance |

Severity may be raised when impact or uncertainty grows. When severity is uncertain, V4 fails closed at the higher plausible level.

## 4. Required examples

| Scenario | Classification | Severity / handling |
|---|---|---|
| Post-match data pollutes a Production pre-match run | `TIME_LEAKAGE_INCIDENT` | `SEV-1`; invalidate run and stop affected Production path |
| Frozen Prediction is overwritten | `FREEZE_INTEGRITY_INCIDENT` | `SEV-1`; preserve original evidence and stop affected writes |
| Official odds are partially missing and the prediction is blocked by the gate | Normal quality gate | Not an incident by itself; record `UNAVAILABLE` / `BLOCKED` |
| Public page displays an old or incorrect update time | `PUBLICATION_INCIDENT` | `SEV-3` by default; correct projection and verify timestamp lineage |
| A secret is committed to Git | `SECURITY_INCIDENT` | `SEV-1`; revoke/rotate externally, preserve evidence, block publication |
| Shadow output is accidentally shown as Production output | `MODEL_INCIDENT` / `PUBLICATION_INCIDENT` | `SEV-2` or higher depending on exposure |

## 5. SEV-1 response

When a SEV-1 is discovered:

1. Immediately stop the related Production path and prevent new affected output.
2. Preserve logs, source snapshots, hashes, timestamps, repository state, and access evidence.
3. Mark affected runs and outputs `INVALID`, `BLOCKED`, or `UNKNOWN` as appropriate.
4. Do not delete evidence, overwrite Frozen records, or silently repair the history.
5. Identify scope, first known occurrence, affected model roles, public exposure, and possible future leakage.
6. Notify the responsible human operator and require a documented containment decision.
7. Create a recovery plan with validation, re-run, publication, and Promotion Review requirements.

## 6. Detection and triage

Initial triage records:

```text
incident_id
incident_class
severity
detected_at
detected_by
affected_component
affected_role
first_known_time
last_known_time
affected_match_or_run_ids
initial_description
containment_state
```

The triage decision must distinguish a normal gate rejection from an incident. Missing official odds that correctly produce `BLOCKED` are expected gate behavior, not an incident, unless the gate itself failed or the data was fabricated.

## 7. Evidence preservation

Incident evidence includes relevant fact and odds snapshots, source provenance, cutoff and kickoff times, feature and Frozen Input hashes, engine metadata, output hashes, logs, Git commit, publication state, and review communications. Evidence is append-only and retains before/after state for any approved correction.

## 8. Recovery rules

Recovery cannot:

- make a leaked run eligible by deleting the leak
- turn Shadow or Experiment into Production retroactively
- overwrite a Frozen Input or Frozen Prediction
- change historical KPI records to hide impact
- bypass Secret or Promotion gates

A clean recovery run receives new input, implementation, configuration, and output identities. Re-publication requires a valid Production output and read-only projection checks.

## 9. Closure criteria

An incident may close only when:

1. scope and root cause are documented
2. affected artifacts are identified and preserved
3. containment is verified
4. required corrections are append-only and audited
5. no-future-leakage and integrity checks pass
6. regression or security checks pass where applicable
7. a human owner approves recovery or accepts residual risk
8. follow-up actions have owners and due states

An incident cannot be closed merely because the public page looks correct.
