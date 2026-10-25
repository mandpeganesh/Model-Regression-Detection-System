"""`python -m regress run`: evaluate a prompt, diff against the previous run, report, alert.

Exit codes: 0 pass/warn, 1 critical regression, 2 config/data/API error (nothing stored).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from regress import slack
from regress.compare import EvalOutcome, Status, compare, detect_drift
from regress.config import Settings, latest_prompt, load_prompt
from regress.dataset import load_dataset
from regress.judge import judge_summary
from regress.report import TREND_RUNS, render_html, render_markdown, write_text
from regress.runner import run_eval
from regress.snapshot import build_snapshot, load_prompts
from regress.store import (all_runs, connect, latest_run, list_pr_runs, recent_runs, save_pr_run,
                           save_run)


def make_client() -> AsyncOpenAI:
    # Built-in exponential backoff covers 429 rate limits and 5xx.
    return AsyncOpenAI(max_retries=6)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="regress", description="Regression-test the email classifier.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="evaluate a prompt against the golden dataset")
    run.add_argument("--prompt", type=Path, help="prompt YAML (default: newest created_at in --prompts-dir)")
    run.add_argument("--prompts-dir", type=Path, default=Path("prompts"))
    run.add_argument("--dataset", type=Path, default=Path("data/golden.json"))
    run.add_argument("--db", type=Path, default=Path("runs.db"))
    run.add_argument("--out", type=Path, default=Path("reports"))
    run.add_argument("--record-to", type=Path, help="save the run here as a PR run instead of into --db")
    run.add_argument("--pr-number", type=int)
    run.add_argument("--head-sha")
    export = sub.add_parser("export", help="write the dashboard snapshot JSON")
    export.add_argument("--db", type=Path, default=Path("runs.db"))
    export.add_argument("--pr-db", type=Path)
    export.add_argument("--dataset", type=Path, default=Path("data/golden.json"))
    export.add_argument("--prompts-dir", type=Path, default=Path("prompts"))
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run" and len({args.record_to is None, args.pr_number is None, args.head_sha is None}) != 1:
        parser.error("--record-to, --pr-number and --head-sha must be given together")
    return args


def execute_run(prompt_path: Path, dataset_path: Path, db: Path, out: Path, settings: Settings, *,
                record_to: Path | None = None, pr_number: int | None = None, head_sha: str | None = None,
                on_case_done: Callable[[], None] | None = None) -> EvalOutcome:
    config = load_prompt(prompt_path)
    dataset = load_dataset(dataset_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db)
    try:
        baseline = latest_run(conn, dataset.version)
        judge = partial(judge_summary, model=settings.judge_model)
        run = asyncio.run(run_eval(config, dataset, client=make_client(), judge=judge, settings=settings,
                                   on_case_done=on_case_done))
        window = max(TREND_RUNS, settings.drift_window)
        if record_to:  # PR runs go to their own db; the baseline db stays untouched
            record_to.parent.mkdir(parents=True, exist_ok=True)
            pr_conn = connect(record_to)
            try:
                save_pr_run(pr_conn, run, pr_number, head_sha)
            finally:
                pr_conn.close()
            history = recent_runs(conn, dataset.version, window) + [run]
        else:
            save_run(conn, run)
            history = recent_runs(conn, dataset.version, window)
    finally:
        conn.close()

    outcome = EvalOutcome(
        run=run,
        baseline=baseline,
        comparison=compare(run, baseline, settings),
        drift=detect_drift([r.pass_rate for r in history], settings.drift_window, settings.drift_threshold),
        history=history,
    )
    write_text(out / f"{run.run_id}.html", render_html(outcome, dataset))
    write_text(out / "summary.md", render_markdown(outcome, settings.report_url))

    if settings.slack_webhook_url:
        try:
            slack.post(settings.slack_webhook_url, slack.build_message(outcome, settings.report_url))
        except Exception as exc:  # an alerting outage must not change the eval verdict
            print(f"warning: Slack post failed: {exc}", file=sys.stderr)
    return outcome


def run_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    outcome = execute_run(args.prompt or latest_prompt(args.prompts_dir), args.dataset, args.db, args.out, settings,
                          record_to=args.record_to, pr_number=args.pr_number, head_sha=args.head_sha)
    print((args.out / "summary.md").read_text(encoding="utf-8"))
    print(f"Report: {args.out / (outcome.run.run_id + '.html')}")
    return 1 if outcome.comparison.status is Status.CRITICAL else 0


def _read_db(path: Path | None, read):
    """Run `read(conn)` on an existing db; a missing db means no runs and is not created."""
    if path is None or not path.exists():
        return []
    conn = connect(path)
    try:
        return read(conn)
    finally:
        conn.close()


def export_command(args: argparse.Namespace) -> int:
    snapshot = build_snapshot(_read_db(args.db, all_runs), _read_db(args.pr_db, list_pr_runs),
                              load_dataset(args.dataset), load_prompts(args.prompts_dir), Settings.from_env())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshot: {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; summaries contain emoji
    args = parse_args(argv)
    try:
        return export_command(args) if args.command == "export" else run_command(args)
    except (ValueError, ValidationError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
    except openai.OpenAIError as exc:  # includes APIError and missing credentials
        print(f"error: OpenAI call failed; nothing was stored: {exc}", file=sys.stderr)
    return 2
