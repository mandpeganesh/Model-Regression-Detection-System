"""Slack incoming-webhook alerts."""

import json
import urllib.request

from regress.compare import EvalOutcome, Status
from regress.report import drift_line, headline

EMOJI = {Status.PASS: "✅", Status.WARN: "⚠️", Status.CRITICAL: "🚨"}


def build_message(outcome: EvalOutcome, report_url: str | None) -> dict:
    run, c = outcome.run, outcome.comparison
    lines = [
        f"{EMOJI[c.status]} *{c.status.upper()}* · prompt {run.prompt_version} · {run.model}",
        headline(c, run.dataset_version),
    ]
    if line := drift_line(outcome.drift):
        lines.append(line)
    if report_url:
        lines.append(f"<{report_url}>")
    return {"text": "\n".join(lines)}


def post(webhook_url: str, payload: dict, timeout: float = 10) -> None:
    """Raises on network errors and non-2xx responses (urlopen raises HTTPError for those)."""
    request = urllib.request.Request(
        webhook_url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):
        pass
