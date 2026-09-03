"""Command-line entry point for local no-write migration evidence generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .canonical_hash import load_candidate_manifest, verify_candidate_hashes, write_candidate_hashes
from .manifest import load_manifest
from .models import ExecutionMode
from .negative import run_negative_cases
from .preflight import run_preflight
from .report import build_batch_02_report
from .acceptance import build_batch_03_report, render_batch_03_markdown, validate_batch_03_static
from .readiness import assess_readiness, load_readiness_contract, load_staging_target_template, readiness_contract_summary, validate_target_manifest
from .runner import DryRunRunner
from .runtime_executor import (
    RuntimeExecutor,
    default_disposable_target,
    review_runtime_evidence,
    write_runtime_report,
)
from .runtime_audit import run_remediation_self_audit
from .production_target import build_production_readiness_review, production_target_binding_report
from .schema_diff import compare_schema_snapshot, load_expected_snapshot
from .smoke import load_smoke_catalog, runtime_pending_smoke_report
from .supabase_preflight import build_supabase_preflight_report


def _load_target(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JCFB V4 no-write migration harness")
    parser.add_argument("--repo-root", default=".", help="JCFB V4 repository root")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="emit a deterministic migration plan")
    plan.add_argument("--mode", choices=[mode.value for mode in ExecutionMode], default=ExecutionMode.PLAN_ONLY.value)
    plan.add_argument("--target-json", help="optional non-secret target descriptor")
    sub.add_parser("preflight", help="emit PF-01..PF-18 report without a connector")
    sub.add_parser("negative", help="run unit-level negative refusal contracts")
    sub.add_parser("smoke", help="emit runtime-pending smoke report")
    sub.add_parser("schema-diff", help="compare an absent catalog and show the blocked result")
    report = sub.add_parser("report", help="assemble the BATCH-02 acceptance report")
    report.add_argument("--final-audit", action="store_true", help="record the final clean-tree audit state")
    sub.add_parser("readiness", help="validate the BATCH-03 readiness contract and target template")
    sub.add_parser("batch-03-validate", help="run the BATCH-03 static acceptance gate")
    batch_report = sub.add_parser("batch-03-report", help="assemble the BATCH-03 acceptance package")
    batch_report.add_argument("--target-json", help="optional explicit non-secret target manifest")
    batch_report.add_argument("--catalog-json", help="optional read-only catalog evidence; never connected by this command")
    batch_report.add_argument("--source-git-commit", help="implementation commit recorded in the evidence package")
    batch_report.add_argument("--generated-at", help="fixed ISO timestamp for reproducible evidence fixtures")
    batch_md = sub.add_parser("batch-03-markdown", help="render a BATCH-03 JSON package as Markdown")
    batch_md.add_argument("--report-json", required=True, help="path to an existing BATCH-03 JSON package")
    hashes = sub.add_parser("canonical-hash", help="verify candidate canonical migration hashes")
    hashes.add_argument("--write", action="store_true", help="explicitly write generated hashes to runtime candidates")
    runtime = sub.add_parser("runtime-validate", help="plan or explicitly apply runtime candidates to a non-production target")
    runtime.add_argument("--mode", choices=["PLAN_ONLY", "DRY_RUN", "APPLY", "PRODUCTION_APPLY"], help="explicit execution mode")
    runtime.add_argument("--plan-only", action="store_true", help="explicit no-write plan mode (the default)")
    runtime.add_argument("--dry-run", action="store_true", help="explicit no-write dry-run mode")
    runtime.add_argument("--apply", action="store_true", help="explicitly allow an approved non-production apply")
    runtime.add_argument("--production-apply", action="store_true", help="always hard-blocked compatibility switch")
    runtime.add_argument("--target-json", help="explicit non-secret target descriptor")
    runtime.add_argument("--database-name", default="jcfb_v4_runtime", help="non-secret local database identity used for the default disposable target")
    runtime.add_argument("--write-report", action="store_true", help="write the redacted JSON and Markdown report under .runtime/reports")
    sub.add_parser("runtime-review", help="verify latest runtime evidence against the current Git HEAD")
    sub.add_parser("remediation-audit", help="run the static PRE-BATCH-04 remediation self-audit without a connector")
    sub.add_parser("production-binding", help="validate the checked-in non-secret Production target binding")
    sub.add_parser("supabase-preflight", help="validate the checked-in read-only Supabase Production preflight plan")
    sub.add_parser("production-readiness", help="emit the identity-only Production Readiness review input")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.command == "plan":
        value = DryRunRunner(repo_root).plan(mode=ExecutionMode(args.mode), target=_load_target(args.target_json))
    elif args.command == "preflight":
        manifest = load_manifest(repo_root)
        value = run_preflight(repo_root, manifest).to_dict()
    elif args.command == "negative":
        value = run_negative_cases(repo_root)
    elif args.command == "smoke":
        value = runtime_pending_smoke_report(load_smoke_catalog(repo_root))
    elif args.command == "schema-diff":
        value = compare_schema_snapshot(load_expected_snapshot(repo_root), None).to_dict()
    elif args.command == "report":
        value = build_batch_02_report(repo_root, final_audit=args.final_audit)
    elif args.command == "readiness":
        contract = load_readiness_contract(repo_root)
        template = load_staging_target_template(repo_root)
        value = {
            "contract": readiness_contract_summary(repo_root),
            "target_manifest_status": "PASS" if not validate_target_manifest(template) else "FAIL",
            "target_manifest_issues": [issue.to_dict() for issue in validate_target_manifest(template)],
            "deployment_readiness": assess_readiness(template),
        }
    elif args.command == "batch-03-validate":
        value = validate_batch_03_static(repo_root)
    elif args.command == "batch-03-report":
        value = build_batch_03_report(
            repo_root,
            target=_load_target(args.target_json),
            catalog=_load_target(args.catalog_json),
            source_git_commit=args.source_git_commit,
            generated_at=args.generated_at,
        )
    elif args.command == "canonical-hash":
        value = write_candidate_hashes(repo_root) if args.write else verify_candidate_hashes(repo_root)
    elif args.command == "runtime-validate":
        mode_switches = [
            ("PLAN_ONLY", args.plan_only),
            ("DRY_RUN", args.dry_run),
            ("APPLY", args.apply),
            ("PRODUCTION_APPLY", args.production_apply),
        ]
        selected_switches = [mode for mode, selected in mode_switches if selected]
        if args.mode and selected_switches:
            raise SystemExit("Use --mode or one explicit runtime mode switch, not both")
        if len(selected_switches) > 1:
            raise SystemExit("Choose only one explicit runtime mode switch")
        runtime_mode = args.mode or (selected_switches[0] if selected_switches else "PLAN_ONLY")
        target = _load_target(args.target_json) if args.target_json else default_disposable_target(args.database_name)
        value = RuntimeExecutor(repo_root).execute(target=target, mode=ExecutionMode(runtime_mode))
        if args.write_report:
            value["report_paths"] = write_runtime_report(
                value,
                repo_root,
                run_id=value.get("run_id"),
                started_at=value.get("started_at"),
                finished_at=value.get("finished_at"),
                git_head=value.get("git_head"),
                git_branch=value.get("git_branch"),
                working_tree_clean=value.get("working_tree_clean"),
                recorded_repo_root=value.get("repo_root"),
            )
    elif args.command == "runtime-review":
        value = review_runtime_evidence(repo_root)
    elif args.command == "remediation-audit":
        value = run_remediation_self_audit(repo_root)
    elif args.command == "production-binding":
        value = production_target_binding_report(repo_root)
    elif args.command == "supabase-preflight":
        value = build_supabase_preflight_report(repo_root)
    elif args.command == "production-readiness":
        value = build_production_readiness_review(repo_root)
    else:
        report_path = Path(args.report_json)
        value = render_batch_03_markdown(json.loads(report_path.read_text(encoding="utf-8")))
        print(value, end="")
        return 0
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "runtime-review":
        return 0 if value.get("status") == "PASS" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
