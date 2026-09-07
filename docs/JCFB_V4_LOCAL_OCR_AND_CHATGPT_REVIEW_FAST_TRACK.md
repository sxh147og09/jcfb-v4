# JCFB V4 three-lane fast-track handoff

This addendum is evidence-only. It does not authorize accepted official-odds payload writes, archive writes, EWP-002/EWP-003 reruns, EWP-005, model fitting, or promotion.

## Lane A

`scripts/run_local_ocr_consensus.py` reads the existing 432-cell manual-review queue and immutable OCR evidence crops. It discovers locally available engines, records unavailable engines, runs deterministic preprocessing passes, and emits a new append-only `local_ocr_consensus_r001_revision_001` directory. Tesseract multi-pass agreement is labeled `OCR_CONSENSUS_AMBIGUOUS`; it is not treated as two engines and cannot auto-confirm by default.

## Lane B

`scripts/build_chatgpt_review_package.py` creates one deterministic ZIP containing each remaining crop, the necessary original source pages, `review_items.jsonl`, the response schema, hashes, and a README. The only permitted review method is `CHATGPT_ASSISTED_VISUAL_REVIEW`.

After the user returns a JSONL response, run `scripts/import_chatgpt_review_response.py`. The importer requires complete one-to-one item coverage, raw/crop SHA binding, the allowed numeric grammar, and the explicit assisted-review method. It writes only an additive import revision and fails closed on any mismatch.

## Lane C

`config/prediction_training/chatgpt_library_backfill_handoff.schema.json`, `docs/CHATGPT_LIBRARY_BACKFILL_HANDOFF_TEMPLATE.json`, and `src/historical_backfill_intake/library_handoff.py` define the pending Library handoff and candidate manifest. `scripts/validate_chatgpt_library_backfill_handoff.py` validates candidate metadata and can emit a deterministic dedupe index. Real bytes remain required before staging; the existing append-only historical backfill stager remains the only permitted local staging path.

When a real verified v1.1 package arrives, `scripts/stage_chatgpt_library_backfill.py` validates the package, binds every declared raw file hash, and append-stages a new revision. It refuses path escapes and never writes `historical_source_archive` or training data.
