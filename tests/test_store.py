from datetime import datetime, timedelta, timezone

from fakes import make_run
from regress.store import (all_runs, connect, latest_run, list_pr_runs, recent_runs, save_pr_run, save_run,
                           used_case_ids, used_dataset_versions)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_round_trip(tmp_path):
    conn = connect(tmp_path / "runs.db")
    run = make_run("r1", passed_flags=(True, False))
    run.cases[1].error = "refusal: no"
    save_run(conn, run)
    assert latest_run(conn, "1.0.0") == run


def test_latest_run_filters_dataset_version(tmp_path):
    conn = connect(tmp_path / "runs.db")
    save_run(conn, make_run("old", "1.0.0", T0))
    save_run(conn, make_run("new", "2.0.0", T0 + timedelta(hours=1)))
    assert latest_run(conn, "1.0.0").run_id == "old"


def test_latest_run_none_when_empty(tmp_path):
    assert latest_run(connect(tmp_path / "runs.db"), "1.0.0") is None


def test_recent_runs_order_and_limit(tmp_path):
    conn = connect(tmp_path / "runs.db")
    for i in range(9):
        save_run(conn, make_run(f"r{i}", created_at=T0 + timedelta(hours=i)))
    assert [r.run_id for r in recent_runs(conn, "1.0.0", 7)] == [f"r{i}" for i in range(2, 9)]


def test_persists_across_connections(tmp_path):
    conn = connect(tmp_path / "runs.db")
    save_run(conn, make_run("r1"))
    conn.close()
    assert latest_run(connect(tmp_path / "runs.db"), "1.0.0").run_id == "r1"


def test_pr_run_round_trip(tmp_path):
    conn = connect(tmp_path / "pr.db")
    run = make_run("r1", passed_flags=(True, False))
    save_pr_run(conn, run, 12, "abc")
    assert list_pr_runs(conn) == [(run, 12, "abc")]


def test_all_runs_spans_dataset_versions(tmp_path):
    conn = connect(tmp_path / "runs.db")
    save_run(conn, make_run("b", "2.0.0", T0 + timedelta(hours=1)))
    save_run(conn, make_run("a", "1.0.0", T0))
    assert [r.run_id for r in all_runs(conn)] == ["a", "b"]


def test_used_versions_and_ids(tmp_path):
    conn = connect(tmp_path / "runs.db")
    save_run(conn, make_run("r1", "1.0.0", passed_flags=(True, True)))
    assert used_dataset_versions(conn) == {"1.0.0"}
    assert used_case_ids(conn) == {"c0", "c1"}


def test_recent_runs_reads_only_selected_case_results(tmp_path):
    conn = connect(tmp_path / "r.db")
    save_run(conn, make_run("a", created_at=T0))
    save_run(conn, make_run("b", created_at=T0 + timedelta(days=1)))
    queries = []
    conn.set_trace_callback(queries.append)
    assert [r.run_id for r in recent_runs(conn, "1.0.0", 1)] == ["b"]
    case_queries = [q for q in queries if "FROM case_results" in q]
    assert case_queries and all("WHERE run_id IN" in q for q in case_queries)
