"""Generate the current V4 Wednesday completion status without overstating readiness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "approved_data/historical_backfill_staging/CHATGPT-20260901-20260904-R001"
AI_DIR = STAGING / "ai_visual_review_r001_revision_001"
OUT_JSON = ROOT / "docs/V4_WEDNESDAY_COMPLETION_STATUS.json"
OUT_MD = ROOT / "docs/V4_WEDNESDAY_COMPLETION_STATUS.md"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ai_manifest = json.loads((AI_DIR / "ai_visual_review_manifest.json").read_text(encoding="utf-8"))
    ewp003 = json.loads((ROOT / "config/prediction_training/v4_batch15_ewp003_readiness_report.json").read_text(encoding="utf-8"))
    status = {
        "status_identity": "V4_WEDNESDAY_COMPLETION_STATUS@1.0.0",
        "as_of": "2026-09-07",
        "overall_status": "BLOCKED_FAIL_CLOSED",
        "SYSTEM_IMPLEMENTATION_COMPLETE": {
            "value": False,
            "completed": [
                "B15-EWP-001 historical archive contract/runtime",
                "B15-EWP-002 dataset builder",
                "B15-EWP-003 temporal split/readiness runtime",
                "B15-EWP-004 training infrastructure and contract validators",
                "official odds extraction/OCR/layout profiles",
                "manual review Workbench Git fail-safe",
                "additive AI visual review contract/runtime",
                "provider-neutral Pass A/Pass B adapter and provider hash bindings",
                "four fail-closed engine shells, model loader, Frozen Input scaffold, and synthetic E2E",
                "append-only Library staging, canonical identity mapping, dedupe, and backfill request"
            ],
            "not_completed": ["formal model artifacts", "V4-076 Frozen Input runtime", "V4-052 Outcome", "V4-053 Handicap", "V4-054 Goals", "V4-055 HTFT"],
            "reason": "Infrastructure is ready, but downstream formal engine implementation is correctly gated on approved model artifacts and Frozen Input; no artifacts exist."
        },
        "SYSTEM_INFRASTRUCTURE_READINESS": "PASS",
        "DATA_PIPELINE_COMPLETE_PARTIAL": {
            "value": "PARTIAL",
            "complete": ["immutable source handoff inventory", "OCR traces and evidence", "432-cell AI review sidecar with canonical bindings", "provider-neutral vision adapter", "append-only Library staging/package preparation", "zero-data EWP-003 readiness rerun"],
            "blocked": ["accepted official odds payload", "r002 package", "historical archive intake", "non-empty as-of dataset", "formal temporal split"]
        },
        "AI_VISUAL_REVIEW": {
            "status": ai_manifest["status"],
            "candidate_count": ai_manifest["candidate_count"],
            "status_counts": ai_manifest["status_counts"],
            "provider_available": ai_manifest["provider_available"],
            "evidence_manifest_hash": ai_manifest["manifest_hash"],
            "quality_statement": "No OCR-only value was accepted as AI visual evidence; candidates remain fail-closed until a repeatable visual provider is connected."
        },
        "VISION_PROVIDER_ADAPTER_READY": True,
        "VISION_PROVIDER_CONNECTION_REQUIRED": not ai_manifest["provider_available"],
        "ADDITIONAL_LIBRARY_BACKFILL_REQUEST_STATUS": "COMPLETE",
        "DATA_PIPELINE_PREP_STATUS": "READY_FOR_NEXT_VALIDATED_LIBRARY_PACKAGE",
        "FORMAL_MODEL_TRAINING": "NOT_STARTED",
        "ENGINE_ROLE_READINESS_TRAINING": {
            role: {
                "readiness": ewp003.get("per_engine_readiness", {}).get(role, {}).get("readiness_state", "BLOCKED"),
                "usable_samples": ewp003.get("per_engine_counts", {}).get(role, {}).get("usable", 0),
                "formal_training": "NOT_EXECUTED",
                "reason_codes": ewp003.get("per_engine_readiness", {}).get(role, {}).get("reason_codes", ["TRAINING_DATA_INSUFFICIENT"]),
            }
            for role in ("OUTCOME", "HANDICAP", "GOALS", "HTFT")
        },
        "BLOCKERS_REQUIRING_USER": [
            {
                "code": "SAFE_REPEATABLE_VISUAL_PROVIDER_REQUIRED",
                "action": "Provide or connect a batch-capable visual review provider that can independently inspect deterministic crops and original images and return evidence hashes; no provider credentials or connector are available in this runtime.",
                "scope": "local research/staging only; no production authorization requested"
            },
            {
                "code": "ADDITIONAL_LIBRARY_BACKFILL_FILES_REQUIRED",
                "action": "Supply an approved Library package satisfying ADDITIONAL_LIBRARY_BACKFILL_REQUEST.json and the machine-readable 99-match request; the current package contains only 40 match identities and is not accepted into the archive.",
                "scope": "historical source acquisition only"
            }
        ],
        "BLOCKERS_REQUIRING_MORE_DATA": {
            "status": "TRAINING_DATA_EXPANSION_REQUIRED",
            "distinct_matches_lower_bound": 99,
            "partition_targets": {"train": 45, "validation": 27, "holdout": 27},
            "per_engine_lower_bounds": {"OUTCOME": 33, "HANDICAP": 33, "GOALS": 88, "HTFT": 99},
            "details_file": "docs/V4_TRAINING_DATA_EXPANSION_REQUIRED.json"
        },
        "SAFETY_BOUNDARY": {
            "production": "NOT_TOUCHED",
            "supabase": "NOT_TOUCHED",
            "public_deployment": "NOT_TOUCHED",
            "v333": "NOT_MODIFIED",
            "thresholds_lowered": False,
            "formal_training_executed": False,
            "model_artifacts_written": False,
            "accepted_archive_records_written": False,
            "formal_prediction_binding_executed": False
        }
    }
    body = json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    status["canonical_hash"] = "sha256:" + hashlib.sha256(body).hexdigest()
    OUT_JSON.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# V4_WEDNESDAY_COMPLETION_STATUS",
        "",
        "当前总状态：`BLOCKED_FAIL_CLOSED`。软件和治理基础设施已推进到可复核状态，但不能把缺视觉 provider、缺 accepted archive 和缺模型 artifacts 报成 V4 全部完成。",
        "",
        "## 结论",
        "",
        "- `SYSTEM_IMPLEMENTATION_COMPLETE`: `false`。Workbench、OCR/evidence、EWP-001..004 和 AI review sidecar 已完成；V4-076、V4-052/053/054/055 仍未实现，因为没有 approved model artifacts。",
        "- `DATA_PIPELINE_COMPLETE/PARTIAL`: `PARTIAL`。432 个候选已生成完整升级记录，但 0 个 AI confirmed；accepted payload、r002、archive intake、非空 dataset 和 split 均未发生。",
        "- 4 个 engine role：全部 `BLOCKED / TRAINING_DATA_INSUFFICIENT`，usable samples 全部为 0；formal training 未执行。",
        "- 数据最低下限：99 个 distinct matches，TRAIN 45、VALIDATION 27、HOLDOUT 27；实际需要可能更多。",
        "",
        "## 当前唯一外部推进条件",
        "",
        "需要一个可批量、可重复的视觉 review provider，以及满足 `docs/V4_TRAINING_DATA_EXPANSION_REQUIRED.json` 的 approved Library 数据包。两者都只针对 local research/staging，不涉及 Production/Supabase/public。",
        "",
        "完整机器可读状态见 `V4_WEDNESDAY_COMPLETION_STATUS.json`。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("V4_WEDNESDAY_COMPLETION_STATUS=BLOCKED_FAIL_CLOSED")
    print("SYSTEM_IMPLEMENTATION_COMPLETE=false")
    print("DATA_PIPELINE_COMPLETE_PARTIAL=PARTIAL")
    print("engine_roles_blocked=OUTCOME,HANDICAP,GOALS,HTFT")
    print("additional_distinct_matches_lower_bound=99")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
