import pytest

from fakes import make_run
from regress.compare import Status, classify_delta, compare, detect_drift
from regress.config import Settings


@pytest.mark.parametrize("before,after,status", [
    (0.94, 0.91, Status.PASS),      # exactly 3 points: not "exceeds"; float trap
    (0.94, 0.90, Status.WARN),
    (0.94, 0.86, Status.WARN),      # exactly 8 points
    (0.94, 0.85, Status.CRITICAL),
    (0.80, 0.95, Status.PASS),      # improvement
    (0.90, 0.90, Status.PASS),
])
def test_classify_delta(before, after, status):
    assert classify_delta(after - before, 0.03, 0.08) is status


def test_no_baseline_is_pass():
    c = compare(make_run("r", passed_flags=(False,)), None, Settings())
    assert c.status is Status.PASS and c.baseline_pass_rate is None and c.pass_rate_delta is None
    assert c.regressions == [] and c.improvements == []


def test_flips():
    base = make_run("b", passed_flags=(True, True, False))
    cur = make_run("c", passed_flags=(False, True, True))
    c = compare(cur, base, Settings())
    assert [f.case_id for f in c.regressions] == ["c0"]
    assert [f.case_id for f in c.improvements] == ["c2"]
    assert c.regressions[0].before.passed and not c.regressions[0].after.passed


def test_cases_missing_from_one_run_ignored():
    base = make_run("b", passed_flags=(True,))
    cur = make_run("c", passed_flags=(True, False))
    assert compare(cur, base, Settings()).regressions == []


def test_category_deltas():
    base = make_run("b", passed_flags=(True, True), categories=["billing", "billing"])
    cur = make_run("c", passed_flags=(True, False), categories=["billing", "billing"])
    assert compare(cur, base, Settings()).category_deltas == {"billing": -0.5}


def test_thresholds_come_from_settings():
    base = make_run("b", passed_flags=(True,) * 50)
    cur = make_run("c", passed_flags=(False,) + (True,) * 49)   # 2-point drop
    assert compare(cur, base, Settings()).status is Status.PASS
    assert compare(cur, base, Settings(warn_threshold=0.01)).status is Status.WARN


def test_drift_needs_full_window():
    d = detect_drift([0.5] * 6, window=7, threshold=0.85)
    assert d.moving_average is None and not d.drifting


def test_drift_fires_below_threshold():
    d = detect_drift([0.9, 0.88, 0.86, 0.84, 0.83, 0.82, 0.81], window=7, threshold=0.85)
    assert d.moving_average == pytest.approx(0.848571, abs=1e-6) and d.drifting


def test_drift_uses_last_window_only():
    assert not detect_drift([0.5] * 10 + [0.95] * 7, window=7, threshold=0.85).drifting


def test_drift_without_per_run_alert():
    rates = [0.90 - 0.01 * i for i in range(7)]   # 0.90 .. 0.84, each step a 1-point drop
    assert all(classify_delta(b - a, 0.03, 0.08) is Status.PASS for a, b in zip(rates, rates[1:]))
    assert detect_drift(rates, window=7, threshold=0.88).drifting
