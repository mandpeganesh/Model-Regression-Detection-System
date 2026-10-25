"""Static HTML diff report and the markdown summary posted on PRs."""

from html import escape
from pathlib import Path

from regress.compare import Comparison, Drift, EvalOutcome, Status
from regress.dataset import GoldenDataset
from regress.runner import CaseResult

TREND_RUNS = 20
STATUS_LABEL = {Status.PASS: "✅ PASS", Status.WARN: "⚠️ WARN", Status.CRITICAL: "❌ CRITICAL"}


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def pct(x: float) -> str:
    return f"{x:.0%}"


def points(delta: float) -> str:
    return f"{delta * 100:+.1f} pts"


def headline(c: Comparison, dataset_version: str) -> str:
    """One line shared by the PR comment and Slack."""
    if c.baseline_pass_rate is None:
        return f"First run for dataset {dataset_version}: pass rate {pct(c.pass_rate)}"
    return (f"{plural(len(c.regressions), 'regression')} detected, "
            f"pass rate {pct(c.baseline_pass_rate)} → {pct(c.pass_rate)} ({points(c.pass_rate_delta)})")


def drift_line(d: Drift) -> str | None:
    if not d.drifting:
        return None
    return f"📉 Slow drift: {d.window}-run average {pct(d.moving_average)} is below {pct(d.threshold)}"


def render_markdown(outcome: EvalOutcome, report_url: str | None) -> str:
    run, c = outcome.run, outcome.comparison
    lines = [
        f"## {STATUS_LABEL[c.status]} · prompt `{run.prompt_version}` · `{run.model}`",
        "",
        headline(c, run.dataset_version),
        f"{plural(len(c.improvements), 'improvement')}.",
    ]
    if c.regressions:
        ids = [f"`{f.case_id}`" for f in c.regressions[:10]]
        more = f" and {len(c.regressions) - 10} more" if len(c.regressions) > 10 else ""
        lines.append(f"Regressed: {', '.join(ids)}{more}")
    if line := drift_line(outcome.drift):
        lines.append(line)
    if report_url:
        lines.append(f"[Full report]({report_url})")
    return "\n".join(lines) + "\n"


def _output(c: CaseResult) -> str:
    if c.error:
        return f"<em>error: {escape(c.error)}</em>"
    return f"<b>{escape(c.actual_category or '')}</b><br>{escape(c.actual_summary or '')}"


def _trend_svg(outcome: EvalOutcome) -> str:
    runs = outcome.history[-TREND_RUNS:]
    width, height = 600, 120
    step = width / max(len(runs) - 1, 1)
    coords = [(round(i * step, 1), round(height - r.pass_rate * height, 1)) for i, r in enumerate(runs)]
    dots = "".join(
        f'<circle cx="{x}" cy="{y}" r="3"><title>{escape(r.prompt_version)} · {pct(r.pass_rate)}</title></circle>'
        for (x, y), r in zip(coords, runs)
    )
    return (
        f'<svg viewBox="-5 -5 {width + 10} {height + 10}" width="100%" role="img" aria-label="Pass rate trend">'
        f'<polyline points="{" ".join(f"{x},{y}" for x, y in coords)}" fill="none" stroke="currentColor" stroke-width="2"/>'
        f"{dots}</svg>"
    )


def render_html(outcome: EvalOutcome, dataset: GoldenDataset) -> str:
    run, c, base = outcome.run, outcome.comparison, outcome.baseline
    inputs = {case.id: case for case in dataset.cases}
    e = escape

    if base is None:
        scorecard = f"<p>First run for dataset {e(run.dataset_version)}; no baseline to compare against.</p>"
    else:
        scorecard = (
            f"<p>Pass rate <b>{pct(c.baseline_pass_rate)} → {pct(c.pass_rate)}</b> ({points(c.pass_rate_delta)}) "
            f"vs run {e(base.run_id)} (prompt {e(base.prompt_version)})</p>"
        )
    accuracy_rows = "".join(
        f"<tr><td>{e(cat)}</td><td>{pct(acc)}</td><td>{points(c.category_deltas[cat]) if cat in c.category_deltas else '—'}</td></tr>"
        for cat, acc in sorted(run.category_accuracy.items())
    )
    regression_rows = "".join(
        f"<tr><td>{e(f.case_id)}</td><td>{e(inputs[f.case_id].input) if f.case_id in inputs else ''}</td>"
        f"<td>{e(inputs[f.case_id].expected.category) if f.case_id in inputs else ''}</td>"
        f"<td>{_output(f.before)}</td><td>{_output(f.after)}</td></tr>"
        for f in c.regressions
    )
    improvements = "".join(f"<li>{e(f.case_id)}</li>" for f in c.improvements) or "<li>None</li>"
    drift = e(drift_line(outcome.drift) or "No slow drift detected.")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval {e(run.run_id)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; padding: 0 1rem; color: #1a1a1a; background: #fff; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
th, td {{ border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top; }}
th {{ background: #f4f4f4; }}
.status {{ font-size: 1.4rem; }}
svg {{ color: #2563eb; max-width: 600px; }}
@media (prefers-color-scheme: dark) {{ body {{ color: #eee; background: #111; }} th {{ background: #222; }} th, td {{ border-color: #333; }} svg {{ color: #60a5fa; }} }}
</style></head><body>
<h1>Eval report</h1>
<p class="status">{STATUS_LABEL[c.status]}</p>
<table><tr><th>Run</th><td>{e(run.run_id)}</td><th>Prompt</th><td>{e(run.prompt_version)}</td></tr>
<tr><th>Model</th><td>{e(run.model)}</td><th>Dataset</th><td>{e(run.dataset_version)}</td></tr>
<tr><th>Timestamp (UTC)</th><td>{run.created_at:%Y-%m-%d %H:%M:%S}</td><th>Cases</th><td>{len(run.cases)}</td></tr>
<tr><th>Total tokens</th><td>{run.total_tokens}</td><th>Mean latency</th><td>{run.mean_latency_ms:.0f} ms</td></tr></table>
<h2>Scorecard</h2>
{scorecard}
<table><tr><th>Category</th><th>Accuracy</th><th>Delta</th></tr>{accuracy_rows}</table>
<p>{drift}</p>
<h2>Regressions ({len(c.regressions)})</h2>
<table><tr><th>Case</th><th>Email</th><th>Expected</th><th>Previous output</th><th>New output</th></tr>{regression_rows}</table>
<h2>Improvements ({len(c.improvements)})</h2>
<ul>{improvements}</ul>
<h2>Pass rate, last {min(len(outcome.history), TREND_RUNS)} runs</h2>
{_trend_svg(outcome)}
</body></html>
"""


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
