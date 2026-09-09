# JCFB V4 B15-EWP-001 ADDENDUM-003 Local Historical Intake Authorization

Decision identity: `B15-EWP-001-ADDENDUM-003`

Revision: `r003`

This is an additive, append-only governance authorization. It does not reopen
B15-EWP-001, alter ADDENDUM-001, alter the frozen `@1.1.0` transport
semantics, or rewrite any prior evidence. It authorizes one local research /
history execution chain against the already-verified ChatGPT-assisted review
and explicit visible-label mapping evidence.

## Authorized scope

The execution may, in order:

1. generate a reviewed extraction trace;
2. generate an accepted official odds payload candidate, without promotion until
   all active intake gates pass;
3. build and validate `verified-historical-backfill-export-package@1.1.0`
   r002 deterministically;
4. run the no-write intake gate, including canonical identity, source
   provenance, timestamp/cutoff semantics, dedupe, and package/hash integrity;
5. if and only if that gate is `PASS`, append verified historical records,
   revisions, manifests, and provenance below
   `F:\Projects\jcfb-v4\approved_data\historical_source_archive\`;
6. after successful archive intake, rerun EWP-002 REAL and EWP-003 REAL and
   update local Wednesday/Fast-Track counts.

All archive writes are append-only. Existing revision paths may not be
overwritten. Any failure stops the chain at that phase.

## Conditions and preserved locks

The active import-manifest, archive, official-extraction, and deterministic ZIP
contracts remain bound. `UNKNOWN` identity, source time, cutoff, or provenance
is never substituted or inferred from ChatGPT upload time and fails closed at
the no-write gate.

This authorization does not authorize EWP-005 formal model fit, formal
training, model artifacts or promotion, V4-076 formal Frozen Input emission,
V4-052/053/054/055 production model binding, Production, Supabase, public
deployment, migrations, V3.3.3 reads/writes, threshold lowering, data
sufficiency relaxation, or post-match leakage.

`FORMAL_MODEL_TRAINING = NOT_STARTED` remains mandatory. A later training
authorization would still require separate explicit authorization plus real
EWP-002/EWP-003 readiness, class support, 100% feature availability, and
leakage/lineage PASS.

## Execution evidence

The executable boundary is
`scripts/run_v4_batch15_verified_historical_backfill_authorized.py`. It writes
only additive evidence below the approved staging root until the conditional
archive gate is passed. Its report records the exact stop phase and hashes.
