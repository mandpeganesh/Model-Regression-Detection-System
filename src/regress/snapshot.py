"""The single JSON document the dashboard renders. All status/delta/drift logic happens here."""

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from regress.compare import compare, detect_drift
from regress.config import PromptConfig, Settings, load_prompt
from regress.dataset import GoldenDataset
from regress.runner import RunResult


def load_prompts(prompts_dir: Path) -> list[PromptConfig]:
    """Every prompt in `prompts_dir`, newest created_at first."""
    prompts = [load_prompt(p) for p in Path(prompts_dir).glob("*.yaml")]
    return sorted(prompts, key=lambda p: p.created_at, reverse=True)


def _view(run: RunResult, baseline: RunResult | None, drift, settings: Settings) -> dict:
    c = compare(run, baseline, settings)
    return {
        "run_id": run.run_id,
        "created_at": run.created_at.isoformat(),
        "prompt_version": run.prompt_version,
        "model": run.model,
        "dataset_version": run.dataset_version,
        "pass_rate": run.pass_rate,
        "category_accuracy": run.category_accuracy,
        "total_tokens": run.total_tokens,
        "mean_latency_ms": run.mean_latency_ms,
        "cases": [asdict(case) for case in run.cases],
        "comparison": {
            "baseline_run_id": c.baseline_run_id,
            "baseline_pass_rate": c.baseline_pass_rate,
            "pass_rate_delta": c.pass_rate_delta,
            "category_deltas": c.category_deltas,
            "regressions": [f.case_id for f in c.regressions],
            "improvements": [f.case_id for f in c.improvements],
            "status": c.status.value,
        },
        "drift": asdict(drift) if drift else None,
    }


def build_snapshot(runs: list[RunResult], pr_runs: list[tuple[RunResult, int, str]], dataset: GoldenDataset,
                   prompts: list[PromptConfig], settings: Settings) -> dict:
    main_views = []
    latest_main: dict[str, RunResult] = {}  # dataset_version -> newest main run so far
    rates: dict[str, list[float]] = {}
    for run in runs:  # oldest first
        v = run.dataset_version
        rates.setdefault(v, []).append(run.pass_rate)
        drift = detect_drift(rates[v], settings.drift_window, settings.drift_threshold)
        main_views.append(_view(run, latest_main.get(v), drift, settings))
        latest_main[v] = run
    pr_views = []
    for run, number, sha in pr_runs:
        view = _view(run, latest_main.get(run.dataset_version), None, settings)
        pr_views.append({**view, "pr_number": number, "head_sha": sha})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {k: getattr(settings, k) for k in (
            "warn_threshold", "critical_threshold", "drift_threshold", "drift_window", "relevance_pass_min")},
        "dataset": dataset.model_dump(mode="json"),
        "prompts": [p.model_dump(mode="json") for p in prompts],
        "runs": main_views,
        "pr_runs": pr_views,
    }
