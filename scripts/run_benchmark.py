from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leadflow_agent.benchmark import (  # noqa: E402
    BenchmarkCase,
    automatic_metrics,
    build_review_rows,
    load_benchmark_cases,
    read_review_csv,
    summarize_manual_review,
    write_metrics,
    write_review_csv,
    write_summary,
)
from leadflow_agent.config import Settings  # noqa: E402
from leadflow_agent.search_service import (  # noqa: E402
    SearchBudgets,
    SearchFeatures,
    SearchRequest,
    execute_search,
)
from leadflow_agent.security import redact_text  # noqa: E402
from leadflow_agent.replay import replay_finalize  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LeadFlow Phase 8.4.4 real-world quality benchmark harness."
    )
    parser.add_argument("--cases", default=str(ROOT / "benchmarks" / "cases.yaml"))
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--case", action="append", dest="case_ids", help="Benchmark id; may be repeated.")
    select.add_argument("--all", action="store_true", help="Run every official case (can consume provider quota).")
    parser.add_argument("--list", action="store_true", help="List benchmark cases and exit.")
    parser.add_argument("--dotenv", help="Explicit .env path for provider keys.")
    parser.add_argument("--provider", choices=["auto", "tavily", "brave", "outscraper"], default="auto")
    parser.add_argument("--refresh-cache", action="store_true", help="Force fresh search calls and refresh cache.")
    parser.add_argument("--no-cache", action="store_true", help="Disable persistent search cache for the run.")
    parser.add_argument("--no-persist", action="store_true", help="Do not save the research run to SQLite.")
    parser.add_argument("--output-root", default=str(ROOT / "benchmarks" / "results"))
    parser.add_argument("--summarize", help="Summarize a manually reviewed review.csv instead of running providers.")
    parser.add_argument(
        "--replay",
        help="Replay a captured benchmark snapshot locally (result dir, run.json or replay_snapshot.json).",
    )
    parser.add_argument(
        "--replay-stage",
        choices=["post_discovery", "post_investigation", "post_audits"],
        default="post_audits",
        help="Snapshot stage used by --replay (default: post_audits).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a non-official 3-lead smoke test instead of the full case target.",
    )
    parser.add_argument(
        "--capture-only",
        action="store_true",
        help=(
            "Fast development capture: discovery only, deterministic extraction, "
            "no Gemini, no investigation and no audits."
        ),
    )
    return parser


def _select_cases(cases: list[BenchmarkCase], ids: list[str] | None, run_all: bool) -> list[BenchmarkCase]:
    if run_all:
        return cases
    if not ids:
        raise ValueError("Choose --case <id> or --all. Use --list to see available cases.")
    by_id = {case.id: case for case in cases}
    missing = [case_id for case_id in ids if case_id not in by_id]
    if missing:
        raise ValueError("Unknown benchmark case(s): " + ", ".join(missing))
    return [by_id[case_id] for case_id in ids]


def _settings(dotenv: str | None) -> Settings:
    return Settings.load(dotenv) if dotenv else Settings.load()


def _run_fast_capture(
    case: BenchmarkCase,
    *,
    settings: Settings,
    provider: str,
    refresh_cache: bool,
    use_cache: bool,
    output_root: Path,
) -> Path:
    """Capture a real candidate pool with the smallest external surface possible.

    This mode is for development fixtures, not product-quality measurement. It
    intentionally disables Gemini, Investigator and every audit layer. Tavily
    (or another selected provider) is used only for up to two discovery queries;
    provider-local deterministic extraction builds the candidate pool.
    """

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_dir = output_root / f"{stamp}_{case.id}_capture"
    result_dir.mkdir(parents=True, exist_ok=False)

    # Fifteen candidates are enough to exercise ordering/dedupe/filter logic
    # while keeping the external portion intentionally tiny. This is a fixture
    # capture, not an attempt to fulfil an end-user quota.
    capture_target = max(12, min(20, case.target * 2))
    request = SearchRequest(
        segment=case.segment,
        city=case.city,
        state=case.state,
        limit=capture_target,
        max_queries=2,
        profile="balanced",
        provider=provider,
        no_ai=True,
        filter_pool_multiplier=1,
        contact_strategy="digital-first",
        fulfill_quota=False,
        use_cache=use_cache,
        refresh_cache=refresh_cache,
        use_memory=False,
        features=SearchFeatures(
            investigate=False,
            investigation_limit=0,
            investigation_budget=1,
            audit_websites=False,
            audit_limit=0,
            browser_audit=False,
            visual_audit=False,
            capture_replay=True,
        ),
        budgets=SearchBudgets(
            max_search_calls=2,
            max_llm_calls=1,
            max_website_audits=0,
            max_browser_audits=0,
            max_visual_audits=0,
        ),
    )

    print(
        f"\n[{case.id}] {case.segment} — {case.city}/{case.state} "
        f"— FAST CAPTURE (<=2 search calls, 0 Gemini)"
    )
    execution = execute_search(
        request,
        settings=settings,
        persist=False,
        export_results=True,
    )
    if not execution.json_path:
        raise RuntimeError("Fast capture completed without JSON artifact")

    report = json.loads(Path(execution.json_path).read_text(encoding="utf-8"))
    snapshot = report.get("replay_snapshot")
    if not snapshot:
        raise RuntimeError("Fast capture did not produce replay_snapshot")

    # Capture runs do not execute Investigator, but local replay should still
    # show which candidates the current policy *would* spend that budget on.
    # Keep a small diagnostic selection cap in the fixture rather than zero.
    snapshot.setdefault("settings", {})["investigation_limit"] = min(5, capture_target)
    snapshot["settings"]["capture_only"] = True

    stages = snapshot.get("stages") or {}
    post_discovery = stages.get("post_discovery") or []
    capture_path = result_dir / "replay_snapshot.json"
    run_path = result_dir / "run.json"
    capture_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    replay = replay_finalize(snapshot, stage="post_discovery")
    (result_dir / "replay_post_discovery.json").write_text(
        json.dumps(replay, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = [
        "# LeadFlow Fast Capture",
        "",
        f"- Case: **{case.segment} — {case.city}/{case.state}**",
        f"- Discovery candidates captured: **{len(post_discovery)}**",
        f"- Queries executed: **{len(report.get('queries_executed') or [])}**",
        f"- Search calls: **{int(report.get('usage_search_calls') or 0)}**",
        f"- LLM calls: **{int(report.get('usage_llm_calls') or 0)}**",
        f"- Investigator calls: **{int(report.get('investigated_leads') or 0)}**",
        f"- Website audits: **{int(report.get('website_audits_run') or 0)}**",
        f"- Estimated investigation searches under current code: **{replay.get('estimated_investigation_searches_max', 0)}**",
        f"- Estimated batched investigation extractions: **{replay.get('estimated_investigation_extractions_batch_max', 0)}**",
        f"- Estimated legacy per-query extractions: **{replay.get('estimated_investigation_extractions_legacy_max', 0)}**",
        "",
        "This is a development fixture, not an official Phase 8.4.4 benchmark.",
        "Use replay_snapshot.json for local ordering/filter/scoring regression work.",
        "",
        "## Current investigation order (local replay)",
        "",
    ]
    selected = replay.get("investigation_order") or []
    summary_lines.extend(
        f"{index}. {name}" for index, name in enumerate(selected[:15], start=1)
    )
    if not selected:
        summary_lines.append("No candidates captured.")
    (result_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"  captured={len(post_discovery)} | search={int(report.get('usage_search_calls') or 0)} "
        f"| llm={int(report.get('usage_llm_calls') or 0)} | investigator=0 | audits=0"
    )
    print(f"  snapshot: {capture_path}")
    return result_dir


def _run_case(
    case: BenchmarkCase,
    *,
    settings: Settings,
    provider: str,
    refresh_cache: bool,
    use_cache: bool,
    persist: bool,
    output_root: Path,
    smoke: bool = False,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = min(3, case.target) if smoke else case.target
    suffix = "_smoke" if smoke else ""
    result_dir = output_root / f"{stamp}_{case.id}{suffix}"
    result_dir.mkdir(parents=True, exist_ok=False)

    request = SearchRequest(
        segment=case.segment,
        city=case.city,
        state=case.state,
        limit=target,
        max_queries=20,
        profile="website-sales",
        provider=provider,
        filter_pool_multiplier=5,
        contact_strategy="digital-first",
        fulfill_quota=True,
        use_cache=use_cache,
        refresh_cache=refresh_cache,
        use_memory=True,
        features=SearchFeatures(
            investigate=True,
            investigation_limit=3,
            investigation_budget=2,
            audit_websites=True,
            audit_limit=target,
            audit_timeout=8.0,
            browser_audit=False,
            visual_audit=False,
            capture_replay=True,
        ),
        budgets=SearchBudgets(
            max_search_calls=30,
            max_llm_calls=40,
            max_website_audits=max(25, target),
            max_browser_audits=0,
            max_visual_audits=0,
        ),
    )

    mode = "SMOKE" if smoke else "OFFICIAL"
    print(f"\n[{case.id}] {case.segment} — {case.city}/{case.state} — target {target} [{mode}]")
    execution = execute_search(
        request,
        settings=settings,
        persist=persist,
        export_results=True,
    )
    if not execution.json_path or not execution.csv_path:
        raise RuntimeError("Search completed without export artifacts")

    exported_json = Path(execution.json_path)
    exported_csv = Path(execution.csv_path)
    report = json.loads(exported_json.read_text(encoding="utf-8"))
    automatic = automatic_metrics(report)
    automatic["benchmark_mode"] = "smoke" if smoke else "official"
    automatic["official_phase_gate_eligible"] = bool(
        not smoke and automatic.get("quality_gate_measurement_valid", False)
    )

    run_json = result_dir / "run.json"
    leads_csv = result_dir / "leads.csv"
    shutil.copy2(exported_json, run_json)
    shutil.copy2(exported_csv, leads_csv)
    replay_snapshot = report.get("replay_snapshot")
    if replay_snapshot:
        (result_dir / "replay_snapshot.json").write_text(
            json.dumps(replay_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        baseline_replay = replay_finalize(replay_snapshot, stage="post_audits")
        (result_dir / "replay_baseline.json").write_text(
            json.dumps(baseline_replay, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        live_names = [str(item.get("name") or "") for item in report.get("leads") or []]
        replay_names = [str(item.get("name") or "") for item in baseline_replay.get("leads") or []]
        automatic["replay_consistent_with_live"] = live_names == replay_names
        automatic["replay_baseline_returned"] = int(baseline_replay.get("returned") or 0)

    review_rows = build_review_rows(
        report,
        benchmark_id=(f"{case.id}-smoke" if smoke else case.id),
        run_id=execution.db_run_id,
    )
    write_review_csv(result_dir / "review.csv", review_rows)
    write_metrics(result_dir / "metrics.json", automatic)
    summary_case = BenchmarkCase(case.id, case.segment, case.city, case.state, target)
    write_summary(result_dir / "summary.md", case=summary_case, automatic=automatic)

    print(
        "  returned={returned}/{requested} | queries={queries_executed} | "
        "unique={unique_candidates} | prequalified={prequalified_candidates} | "
        "search={search_calls} | llm={llm_calls} | stop={stop_reason}".format(**automatic)
    )
    if not automatic.get("quality_gate_measurement_valid", False):
        print("  WARNING: run is not valid for the Phase 8.4.4 quality gate")
        for reason in automatic.get("validity_reasons") or []:
            print(f"    - {reason}")
    print(f"  review: {result_dir / 'review.csv'}")
    return result_dir


def _summarize(review_path: Path) -> int:
    rows = read_review_csv(review_path)
    manual = summarize_manual_review(rows)
    result_dir = review_path.parent
    metrics_path = result_dir / "metrics.json"
    if metrics_path.exists():
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        automatic = payload.get("automatic") or {}
    else:
        automatic = {}
    write_metrics(metrics_path, automatic, manual)

    case = None
    if rows:
        benchmark_id = str(rows[0].get("benchmark_id") or "").strip()
        if benchmark_id:
            case = BenchmarkCase(benchmark_id, "", "", "", int(automatic.get("requested") or len(rows) or 10))
    write_summary(result_dir / "summary.md", case=case, automatic=automatic, manual=manual)
    print(json.dumps(manual, ensure_ascii=False, indent=2))
    return 0


def _load_replay_snapshot(path: Path) -> tuple[dict, Path]:
    if path.is_dir():
        snapshot_path = path / "replay_snapshot.json"
        run_path = path / "run.json"
        if snapshot_path.exists():
            return json.loads(snapshot_path.read_text(encoding="utf-8")), path
        if run_path.exists():
            payload = json.loads(run_path.read_text(encoding="utf-8"))
            snapshot = payload.get("replay_snapshot")
            if snapshot:
                return snapshot, path
        raise ValueError(
            "This result directory predates replay capture. Run one new smoke/benchmark with the current build first."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if path.name == "replay_snapshot.json" and "stages" in payload:
        return payload, path.parent
    snapshot = payload.get("replay_snapshot") if isinstance(payload, dict) else None
    if not snapshot:
        raise ValueError(
            "This run predates replay capture. Run one new smoke/benchmark with the current build first."
        )
    return snapshot, path.parent


def _replay(path: Path, stage: str) -> int:
    snapshot, result_dir = _load_replay_snapshot(path)
    replay = replay_finalize(snapshot, stage=stage)
    out_json = result_dir / f"replay_{stage}.json"
    out_md = result_dir / f"replay_{stage}.md"
    out_json.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")

    selected = replay.get("investigation_selected") or []
    lines = [
        "# LeadFlow Fast Replay",
        "",
        f"- Stage: `{stage}`",
        f"- Provider calls: **{replay['provider_calls']}**",
        f"- LLM calls: **{replay['llm_calls']}**",
        f"- Input candidates: **{replay['input_candidates']}**",
        f"- Returned: **{replay['returned']}/{replay['requested']}**",
        f"- Filter rejected: **{replay['filter_rejected']}**",
        f"- Estimated investigation searches (max): **{replay.get('estimated_investigation_searches_max', 0)}**",
        f"- Estimated batched investigation extractions (max): **{replay.get('estimated_investigation_extractions_batch_max', 0)}**",
        f"- Estimated legacy per-query extractions (max): **{replay.get('estimated_investigation_extractions_legacy_max', 0)}**",
        f"- Estimated extraction calls avoided by batching (max): **{replay.get('estimated_batch_extraction_savings_max', 0)}**",
        "",
        "## Investigation selection under current code",
        "",
    ]
    lines.extend(f"{index}. {name}" for index, name in enumerate(selected, start=1))
    if not selected:
        lines.append("No captured post-discovery selection is available.")
    plan = replay.get("investigation_plan") or []
    lines.extend(["", "## Investigation query plan", ""] )
    for item in plan:
        purposes = ", ".join(item.get("purposes") or []) or "none"
        lines.append(
            f"- {item.get('name')}: {item.get('searches', 0)} search(es) — {purposes}"
        )
    if not plan:
        lines.append("- none")
    lines.extend(["", "## Filter rejection reasons", ""] )
    reasons = replay.get("filter_rejection_reasons") or {}
    lines.extend(f"- `{reason}`: {count}" for reason, count in sorted(reasons.items()))
    if not reasons:
        lines.append("- none")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"Replay complete: {replay['returned']}/{replay['requested']} | "
        f"provider calls=0 | llm calls=0 | stage={stage}"
    )
    print(f"  {out_json}")
    print(f"  {out_md}")
    return 0


def main() -> int:
    args = _parser().parse_args()
    if args.replay:
        try:
            return _replay(Path(args.replay), args.replay_stage)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Replay failed: {exc}", file=sys.stderr)
            return 2
    if args.summarize:
        return _summarize(Path(args.summarize))

    cases = load_benchmark_cases(args.cases)
    if args.list:
        for case in cases:
            print(f"{case.id:<34} {case.segment:<22} {case.city}/{case.state} target={case.target}")
        return 0

    if args.no_cache and args.refresh_cache:
        print("--no-cache and --refresh-cache cannot be combined", file=sys.stderr)
        return 2

    try:
        selected = _select_cases(cases, args.case_ids, args.all)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    settings = _settings(args.dotenv)
    if args.smoke and args.capture_only:
        print("--smoke and --capture-only cannot be combined", file=sys.stderr)
        return 2

    output_root = Path(args.output_root)
    if args.capture_only and args.output_root == str(ROOT / "benchmarks" / "results"):
        output_root = ROOT / "benchmarks" / "captures"
    elif args.smoke and args.output_root == str(ROOT / "benchmarks" / "results"):
        output_root = ROOT / "benchmarks" / "smoke"
    output_root.mkdir(parents=True, exist_ok=True)

    for case in selected:
        try:
            if args.capture_only:
                _run_fast_capture(
                    case,
                    settings=settings,
                    provider=args.provider,
                    refresh_cache=args.refresh_cache,
                    use_cache=not args.no_cache,
                    output_root=output_root,
                )
                continue
            _run_case(
                case,
                settings=settings,
                provider=args.provider,
                refresh_cache=args.refresh_cache,
                use_cache=not args.no_cache,
                persist=not args.no_persist,
                output_root=output_root,
                smoke=args.smoke,
            )
        except Exception as exc:
            # Never print provider secrets; search/runtime errors are already
            # sanitized, and generic fallback avoids dumping request objects.
            safe_error = redact_text(str(exc), secrets=settings.secret_values())
            print(f"[{case.id}] benchmark failed: {type(exc).__name__}: {safe_error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
