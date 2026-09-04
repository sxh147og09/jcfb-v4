# JCFB V4 V4-042 ATTACK DEFENCE HOME ADVANTAGE IMPLEMENTATION REPORT

Workspace: `F:\Projects\jcfb-v4`
Task: `V4-042｜Attack, Defence & Home Advantage Model 1.0`
Historical contract: `historical-statistical-input@1.0.0`
Feature Bundle: `feature-bundle@2.0.0`
Statistical config: `statistical-strength-config@1.0.0`
Execution manifest: [V4 BATCH-11 Execution Manifest](<F:/Projects/jcfb-v4/docs/V4_BATCH_11_EXECUTION_MANIFEST.json>)

## Implementation Status

`COMPLETE / DoD PASS`

## Implemented Boundary

The V4-042 engine emits three separate typed statistical features: `ATTACK_STRENGTH`, `DEFENCE_STRENGTH`, and `HOME_ADVANTAGE`.

Attack and defence use explicitly typed goals-for and goals-against observations. Home advantage uses only canonical HOME-side paired goal facts and requires the approved 20-source-match scope. The implementation preserves source units, sample identity, cutoff eligibility, configuration identity, and output hashes.

## Safety Semantics

- The same source/target canonical identity and cutoff predicate as V4-041 is mandatory.
- Attack and defence require at least five eligible source matches per team.
- Home advantage requires at least 20 eligible HOME-side source matches.
- Neutral venue is not assigned home advantage; unknown venue blocks the home-advantage feature.
- No fixed hidden home advantage, zero fallback, mean fallback, previous-value fallback, xG prediction, lambda, probability, or score output is generated.
- The feature quality object only describes statistical data quality and provenance.
- Output hashes include the exact accepted source match set, configuration, decay policy, implementation identity, and derivation identity.

## Verification

- V4-042 targeted tests: **2/2 PASS**
- Full repository tests: **370/370 PASS**
- Attack/defence units and minimum sample audit: **PASS**
- Home/away/neutral/unknown venue audit: **PASS**
- Cutoff and target self-result audit: **PASS**
- Prediction/Score boundary audit: **PASS**
- V3.3.3 isolation: **PASS**
- F-drive policy: **PASS**
- Production/Supabase reads/writes: **NO**
- Migration added/applied: **NO**

## DoD

`PASS`

V4-043 is the next approved task in Wave 2. No BATCH-12 task, Prediction, Score Engine, Frozen Input, Production write, migration apply, or V3.3.3 modification was authorized by V4-042.
