"""`python -m regress run`: evaluate a prompt, diff against the previous run, report, alert.

Exit codes: 0 pass/warn, 1 critical regression, 2 config/data/API error (nothing stored).
"""

import argparse
import asyncio
import sys
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
from regress.store import connect, latest_run, recent_runs, save_run


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
    return parser.parse_args(argv)


def run_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    config = load_prompt(args.prompt or latest_prompt(args.prompts_dir))
    dataset = load_dataset(args.dataset)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)
    try:
        baseline = latest_run(conn, dataset.version)
        judge = partial(judge_summary, model=settings.judge_model)
        run = asyncio.run(run_eval(config, dataset, client=make_client(), judge=judge, settings=settings))
        save_run(conn, run)
        history = recent_runs(conn, dataset.version, max(TREND_RUNS, settings.drift_window))
    finally:
        conn.close()

    outcome = EvalOutcome(
        run=run,
        baseline=baseline,
        comparison=compare(run, baseline, settings),
        drift=detect_drift([r.pass_rate for r in history], settings.drift_window, settings.drift_threshold),
        history=history,
    )
    report_path = write_text(args.out / f"{run.run_id}.html", render_html(outcome, dataset))
    summary = render_markdown(outcome, settings.report_url)
    write_text(args.out / "summary.md", summary)

    if settings.slack_webhook_url:
        try:
            slack.post(settings.slack_webhook_url, slack.build_message(outcome, settings.report_url))
        except Exception as exc:  # an alerting outage must not change the eval verdict
            print(f"warning: Slack post failed: {exc}", file=sys.stderr)

    print(summary)
    print(f"Report: {report_path}")
    return 1 if outcome.comparison.status is Status.CRITICAL else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; summaries contain emoji
    args = parse_args(argv)
    try:
        return run_command(args)
    except (ValueError, ValidationError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
    except openai.OpenAIError as exc:  # includes APIError and missing credentials
        print(f"error: OpenAI call failed; nothing was stored: {exc}", file=sys.stderr)
    return 2
