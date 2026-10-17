"""Run-vs-previous-run comparison, threshold status, and slow-drift detection. Pure logic."""

from dataclasses import dataclass
from enum import StrEnum

from regress.config import Settings
from regress.runner import CaseResult, RunResult


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    CRITICAL = "critical"


def classify_delta(delta: float, warn: float, critical: float) -> Status:
    """`delta` is current minus baseline. Only a drop that strictly exceeds a threshold alerts."""
    drop = round(-delta, 9)  # 0.94 - 0.91 is 0.030000000000000027; exactly 3 points must not warn
    if drop > critical:
        return Status.CRITICAL
    if drop > warn:
        return Status.WARN
    return Status.PASS


@dataclass
class Flip:
    case_id: str
    before: CaseResult
    after: CaseResult


@dataclass
class Comparison:
    baseline_run_id: str | None
    pass_rate: float
    baseline_pass_rate: float | None
    pass_rate_delta: float | None
    category_deltas: dict[str, float]
    regressions: list[Flip]
    improvements: list[Flip]
    status: Status


def compare(current: RunResult, baseline: RunResult | None, settings: Settings) -> Comparison:
    if baseline is None:
        return Comparison(None, current.pass_rate, None, None, {}, [], [], Status.PASS)
    before = {c.case_id: c for c in baseline.cases}
    flips = [Flip(c.case_id, before[c.case_id], c) for c in current.cases
             if c.case_id in before and before[c.case_id].passed != c.passed]
    flips.sort(key=lambda f: f.case_id)
    old_acc, new_acc = baseline.category_accuracy, current.category_accuracy
    delta = current.pass_rate - baseline.pass_rate
    return Comparison(
        baseline_run_id=baseline.run_id,
        pass_rate=current.pass_rate,
        baseline_pass_rate=baseline.pass_rate,
        pass_rate_delta=delta,
        category_deltas={cat: new_acc[cat] - old_acc[cat] for cat in new_acc if cat in old_acc},
        regressions=[f for f in flips if f.before.passed],
        improvements=[f for f in flips if f.after.passed],
        status=classify_delta(delta, settings.warn_threshold, settings.critical_threshold),
    )


@dataclass
class Drift:
    moving_average: float | None
    threshold: float
    window: int
    drifting: bool


def detect_drift(pass_rates: list[float], window: int, threshold: float) -> Drift:
    """Moving average of the last `window` pass rates; separate from per-run alerts."""
    if len(pass_rates) < window:
        return Drift(None, threshold, window, False)
    average = sum(pass_rates[-window:]) / window
    return Drift(average, threshold, window, average < threshold)


@dataclass
class EvalOutcome:
    run: RunResult
    baseline: RunResult | None
    comparison: Comparison
    drift: Drift
    history: list[RunResult]
