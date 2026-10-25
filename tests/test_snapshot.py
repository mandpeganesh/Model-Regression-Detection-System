import json
from datetime import datetime, timedelta, timezone

from fakes import make_run
from regress.compare import compare
from regress.config import Settings
from regress.dataset import load_dataset
from regress.snapshot import build_snapshot

DS = load_dataset("tests/fixtures/mini_dataset.json")
S = Settings()


def at(i):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)


def snap(runs, pr_runs=(), settings=S):
    return build_snapshot(list(runs), list(pr_runs), DS, [], settings)


def test_main_run_comparisons_match_compare():
    r = [make_run("a", passed_flags=(True, True), created_at=at(0)),
         make_run("b", passed_flags=(True, False), created_at=at(1)),
         make_run("c", passed_flags=(True, True), created_at=at(2))]
    runs = snap(r)["runs"]
    exp = compare(r[1], r[0], S)
    cmp = runs[1]["comparison"]
    assert cmp["baseline_run_id"] == "a" and cmp["pass_rate_delta"] == exp.pass_rate_delta
    assert cmp["regressions"] == ["c1"] and cmp["status"] == exp.status.value
    assert cmp["category_deltas"] == exp.category_deltas
    assert runs[0]["comparison"]["baseline_run_id"] is None and runs[0]["comparison"]["status"] == "pass"


def test_comparison_restarts_per_dataset_version():
    runs = snap([make_run("a", created_at=at(0)), make_run("b", dataset_version="2.0.0", created_at=at(1))])["runs"]
    assert runs[1]["comparison"]["baseline_run_id"] is None


def test_drift_window():
    runs = snap([make_run(f"r{i}", created_at=at(i)) for i in range(7)])["runs"]
    assert runs[6]["drift"]["moving_average"] == 1.0 and runs[5]["drift"]["moving_average"] is None


def test_pr_run_uses_latest_main_baseline_and_no_drift():
    main = [make_run("a", created_at=at(0)), make_run("b", created_at=at(1))]
    s = snap(main, [(make_run("p", created_at=at(2)), 7, "abc123")])
    pr = s["pr_runs"][0]
    assert pr["comparison"]["baseline_run_id"] == "b" and pr["drift"] is None
    assert (pr["pr_number"], pr["head_sha"]) == (7, "abc123")
    assert [r["run_id"] for r in s["runs"]] == ["a", "b"]


def test_failed_case_serializes():
    run = make_run("a")
    run.cases[0].actual_category, run.cases[0].error, run.cases[0].passed = None, "refusal: no", False
    case = snap([run])["runs"][0]["cases"][0]
    assert case["actual_category"] is None and case["error"] == "refusal: no"
    json.dumps(case)


def test_empty_history():
    s = snap([])
    assert s["runs"] == [] and s["pr_runs"] == [] and {"generated_at", "settings", "dataset", "prompts"} <= set(s)


def test_snapshot_has_no_secrets():
    s = snap([make_run("a")], settings=Settings(slack_webhook_url="https://hooks.slack.com/x"))
    assert "hooks.slack.com" not in json.dumps(s)
    assert set(s["settings"]) == {"warn_threshold", "critical_threshold", "drift_threshold", "drift_window",
                                  "relevance_pass_min"}
