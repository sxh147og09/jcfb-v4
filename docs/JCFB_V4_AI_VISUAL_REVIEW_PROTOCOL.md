# JCFB V4 AI Visual Review Protocol

Contract: `official-odds-ai-visual-review@1.0.0` with evidence schema `official-odds-review-evidence@1.0.0`.

This is an additive staging-sidecar contract. The existing `HUMAN_VISUAL_FROM_ORIGINAL_IMAGE` contract remains unchanged. An AI record is never emitted with a human review method or human reviewer state.

## Decision rule

Pass A reads the deterministic crop and cell label. Pass B independently reads the original image with locator context. The runtime accepts a value only when both visual passes are readable, label mapping is exact, and either both equal a readable OCR value or both independently agree while OCR is empty. A disagreement, unclear mapping, unreadable pass, missing provider, or invalid evidence becomes `AI_REVIEW_AMBIGUOUS`, `CONFLICT`, or `HUMAN_ESCALATION_REQUIRED`.

The runtime forbids adjacent-cell inference, later-snapshot filling, duplicate-image inference, baseline/probability guessing, and silent conflict resolution. Source trace, OCR evidence, raw images, and crops are read-only.

## Current execution boundary

`scripts/run_ai_visual_review.py` runs against the immutable 432-cell queue and writes only `ai_visual_review_r001_revision_001` under the staging batch. In the current Codex runtime no safe, repeatable visual-provider batch interface is available. The runner therefore emits a deterministic escalation record for every candidate with both passes marked `NOT_EXECUTED`; this is a measured blocker, not AI confirmation.

No accepted official-odds payload, archive record, r002 package, training dataset, model artifact, Production, Shadow, public, Supabase, or V3.3.3 write is enabled by this protocol.
