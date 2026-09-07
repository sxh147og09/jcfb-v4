# JCFB V4 Historical Official Odds Manual Review Workbench

This is an additive, local-only tool for the 432 unresolved official-odds cells in the `CHATGPT-20260901-20260904-R001` staging batch. It reads the immutable OCR-enriched trace, OCR evidence, and handoff ZIP. It writes only:

```text
approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001/manual_review_workbench_r001_revision_001/
```

The prior manual-review revisions are not modified. No accepted official odds payload, historical source archive, r002 package, EWP-002/EWP-003 rerun, EWP-005 authorization, model output, database/Supabase write, or V3.3.3 change is available through this tool.

## Start

From `F:\Projects\jcfb-v4`:

```powershell
python scripts/run_manual_review_workbench.py
```

Open `http://127.0.0.1:8765/`. Stop the server with `Ctrl+C`. Optional flags are `--host`, `--port`, `--staging`, `--output`, and `--reviewer-id`.

The first start creates the new revision and queue. Later starts validate its source fingerprints and resume the same revision. The UI requires a reviewer ID before writing an action.

## Review semantics

The queue contains only trace records in the active unresolved review scope. The nine SPF `MARKET_UNAVAILABLE` records are excluded. Ordering is deterministic: market priority, artifact slot, ordering index, then queue item ID.

The UI shows the original PNG directly from the immutable handoff ZIP, a deterministic crop, the source-cell overlay, OCR text, prior parser status/value/reason, coordinates, hashes, and progress. It supports:

- `CONFIRM OCR VALUE`, only when normalized OCR text is present and format-valid;
- `ENTER CORRECT VALUE`, preserving the exact entered source text;
- `UNKNOWN / CANNOT READ`;
- `CONFLICT`, which requires an observed value so the conflict is an actual human observation;
- `SKIP FOR LATER`, which updates session state without creating a ledger record.

Values receive format validation only. Odds must be finite and greater than zero; handicap lines may be finite numeric values including zero and negative lines. No neighboring cell, other snapshot, old baseline, probability, or pattern is used to infer a value.

Every non-skip action is appended to `cell_level_manual_review_ledger.jsonl` with the immutable bindings, reviewer identity, review time, source timestamps copied unchanged, and a canonical SHA-256 self-hash. Identical duplicate submissions are rejected. A different later decision creates a new explicit superseding revision and does not rewrite the old record.

Git is optional provenance metadata only. If `git.exe` is unavailable, a Git command fails, or Git returns a non-zero status, the readiness report records `GIT_NOT_AVAILABLE` and the review submission still succeeds. If a post-append export/report refresh fails for another non-critical reason, the API returns HTTP success with `submission_committed: true` and a warning; retrying the same action still uses the existing duplicate-submission check.

## Validation

```powershell
python scripts/validate_manual_review_workbench.py
python -m unittest tests.unit.test_manual_review_workbench -v
```

The readiness state remains `BLOCKED_WAITING_FOR_HUMAN_REVIEW` until a human operator actually reviews the cells. The only permitted next step after implementation is user human review execution; this tool does not auto-confirm cells.
