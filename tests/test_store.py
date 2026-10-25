from datetime import datetime, timedelta, timezone

from fakes import make_run
from regress.store import connect, latest_run, recent_runs, save_run

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
