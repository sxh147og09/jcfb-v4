# JCFB V4 Runtime Access Matrix 1.0

Status: V4-007 ACCEPTANCE PENDING

## 1. Purpose and scope

This matrix defines role-scoped access for the V4 runtime boundary. It covers the three runtime roles and the controlled Review/Promotion and Public Web boundaries. It is an authorization contract, not a database schema.

The matrix is subordinate to docs/V4_CONSTITUTION.md. A permission cannot override immutability, timestamp, no-future-leakage, role, Promotion, Secret, Public Web, or V3.3.3 rules.

## 2. Permission meanings

- READ: may read an approved artifact in the declared scope; no mutation.
- WRITE: may create or update a role-owned working artifact before it is hashed or frozen. It never permits changing an immutable historical artifact and never crosses a role namespace.
- APPEND_ONLY: may create a new immutable role-scoped record or audit event. It cannot update, delete, replace, or hide an existing record.
- DENY: no access through this boundary.

Every write is also subject to identity, provenance, cutoff, hash, and audit gates. APPEND_ONLY on a role-owned namespace does not authorize a write to a Production namespace. The Review/Promotion column represents a controlled service with explicit evidence scope, not a free-form operator account.

All role write cells are limited to that role's namespace. A cell that permits APPEND_ONLY for Shadow or Experiment never permits a cross-role write to Production, Frozen Prediction, confidence, review, Tier A, or the canonical public projection.

## 3. Access matrix

| Artifact | PRODUCTION read | PRODUCTION write | SHADOW read | SHADOW write | EXPERIMENT read | EXPERIMENT write | REVIEW/PROMOTION read | REVIEW/PROMOTION write | PUBLIC WEB read | PUBLIC WEB write |
|---|---|---|---|---|---|---|---|---|---|---|
| Canonical Facts | READ | DENY | READ | DENY | READ | DENY | READ | DENY | DENY | DENY |
| Frozen Input | READ | APPEND_ONLY for the canonical Production freeze gate | READ | DENY for the shared Production record | READ | APPEND_ONLY for its own frozen research input only | READ | DENY | DENY | DENY |
| Feature Bundles | READ | APPEND_ONLY in the Production namespace | READ | APPEND_ONLY in the Shadow namespace | READ | WRITE for working research data, then APPEND_ONLY after hashing | READ | DENY | DENY | DENY |
| Engine Outputs | READ | APPEND_ONLY in the Production namespace | READ | APPEND_ONLY in the Shadow namespace | READ | APPEND_ONLY in the Experiment namespace | READ | DENY | DENY | DENY |
| Prediction | READ | APPEND_ONLY in the Production namespace | READ | APPEND_ONLY in the Shadow namespace | READ | APPEND_ONLY in the Experiment namespace | READ | DENY | DENY | DENY |
| Prediction metadata: confidence, risk, recommendation strength | READ | APPEND_ONLY in the Production namespace | READ | APPEND_ONLY in the Shadow namespace | READ | APPEND_ONLY in the Experiment namespace | READ | DENY | DENY | DENY |
| Frozen Prediction | READ | APPEND_ONLY after the Production Final Prediction Gate | READ only for an approved paired comparison scope | DENY | READ only for an approved postmatch research scope | DENY | READ | DENY | DENY | DENY |
| Postmatch Review | READ | DENY | READ | DENY | READ | DENY | READ | APPEND_ONLY as a new review revision | DENY | DENY |
| Tier A | READ | DENY | READ | DENY | DENY | DENY | READ | APPEND_ONLY after all Forward gates pass | DENY | DENY |
| Calibration Store | READ | APPEND_ONLY in the Production calibration namespace | READ | APPEND_ONLY in the Shadow calibration namespace | READ | APPEND_ONLY in the Experiment calibration namespace | READ | APPEND_ONLY as a new evaluation record | DENY | DENY |
| Audit Logs | READ within permitted evidence scope | APPEND_ONLY for Production events | READ within permitted evidence scope | APPEND_ONLY for Shadow events | READ within permitted evidence scope | APPEND_ONLY for Experiment events | READ | APPEND_ONLY | DENY | DENY |
| Public Read Projection | READ | APPEND_ONLY only through the Production publication gate | DENY | DENY | DENY | DENY | READ | DENY | READ | DENY |

## 4. Matrix constraints

### 4.1 Canonical facts

Canonical Facts are a read-only cross-role boundary. Fact Intake may have a separate append-only authority, but PRODUCTION, SHADOW, and EXPERIMENT cannot write the canonical facts record through this matrix. Corrections follow docs/V4_CORRECTION_POLICY.md and create new fact identities where required.

### 4.2 Frozen Input and feature bundles

The shared Production Frozen Input is created once by the Freeze Gate. A comparable Shadow reads that exact identity. An Experiment may append a separately identified frozen research input, but it cannot modify or replace the Production Frozen Input. Same match identity does not make separate inputs equivalent.

Role-owned feature bundles may be created only before their formal hash/freeze boundary. Once used by a formal run, a change creates a new identity and new hashes.

### 4.3 Prediction and Frozen Prediction

Each role's Prediction and output identity is separate. Shadow and Experiment access to Frozen Prediction is read-only and scope-limited; neither role can write it. Review can append a review revision, never a Frozen Prediction revision in place.

### 4.4 Tier A and calibration

Only Promotion Review can append a Tier A record, and only after the formal Forward evidence gate. Experiment has DENY for Tier A. Calibration entries are append-only and namespaced by role and model identity; a Shadow or Experiment calibration record cannot overwrite Production calibration.

### 4.5 Public projection

Only the Production publication path may append a canonical public projection. Public Web has READ for that projection and DENY for every model or write path. A future research projection must be a separate artifact and route outside this matrix's Production projection.

## 5. V3.3.3 isolation

This matrix grants no access to JCFB V3.3.3 predictions, Frozen Predictions, reviews, Tier A records, parameters, or audit history. A benchmark may read separately authorized artifacts without merging, copying, or mutating either model line.

## 6. References

- docs/V4_RUNTIME_ROLE_BOUNDARY.md
- docs/V4_PRODUCTION_POLICY.md
- docs/V4_SHADOW_POLICY.md
- docs/V4_EXPERIMENT_POLICY.md
- docs/V4_PROMOTION_PATH.md
- docs/V4_CONSTITUTION.md
- docs/V4_VERSION_IDENTITY_CONTRACT.md
- docs/V4_CORRECTION_POLICY.md
