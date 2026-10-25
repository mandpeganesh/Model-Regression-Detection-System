from datetime import datetime, timedelta, timezone
from pathlib import Path

from fakes import make_run
from regress.compare import Drift, EvalOutcome, compare, detect_drift
from regress.config import Settings
from regress.dataset import load_dataset
from regress.report import render_html, render_markdown, write_text

DS = load_dataset(Path("tests/fixtures/mini_dataset.json"))
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fixture_run(run_id, flags, hours=0):
    run = make_run(run_id, "test-1", T0 + timedelta(hours=hours), flags)
    for case, golden in zip(run.cases, DS.cases):
        case.case_id = golden.id
    return run


def outcome(history_len=2, drift=None, baseline=True):
    history = [fixture_run(f"h{i}", (True,) * 4, i) for i in range(history_len - 1)]
    base = history[-1] if baseline and history else None
    run = fixture_run("cur", (True, True, True, False), history_len)
    history.append(run)
    drift = drift or detect_drift([r.pass_rate for r in history], 7, 0.85)
    return EvalOutcome(run, base, compare(run, base, Settings()), drift, history)


def test_html_escapes_email_text():
    html = render_html(outcome(), DS)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_html_contains_metadata_and_regression():
    html = render_html(outcome(), DS)
    for text in ("v1", "gpt-4o-mini", "test-1", "t-general-1", "summary h0 3", "summary cur 3"):
        assert text in html


def test_html_trend_has_point_per_run():
    html = render_html(outcome(history_len=5), DS)
    points = html.split('<polyline points="')[1].split('"')[0].split()
    assert len(points) == 5


def test_first_run_html():
    html = render_html(outcome(history_len=1, baseline=False), DS)
    assert "first run" in html.lower()


def test_markdown_headline():
    md = render_markdown(outcome(), "https://example.test/run/1")
    assert "CRITICAL" in md and "1 regression" in md and "100% → 75%" in md
    assert "https://example.test/run/1" in md and "t-general-1" in md


def test_markdown_drift_line_only_when_drifting():
    assert "Slow drift" not in render_markdown(outcome(), None)
    assert "Slow drift" in render_markdown(outcome(drift=Drift(0.8, 0.85, 7, True)), None)


def test_write_text_round_trips_unicode(tmp_path):
    p = write_text(tmp_path / "a" / "r.html", "¿ayuda? 日本語")
    assert p.read_text(encoding="utf-8") == "¿ayuda? 日本語"
