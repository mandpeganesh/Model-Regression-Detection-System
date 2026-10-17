"""SQLite history of every run and every per-case score."""

import sqlite3
from dataclasses import astuple, fields
from datetime import datetime
from pathlib import Path

from regress.runner import CaseResult, RunResult

CASE_FIELDS = [f.name for f in fields(CaseResult)]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, prompt_version TEXT NOT NULL,
    model TEXT NOT NULL, dataset_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_results (
    run_id TEXT NOT NULL REFERENCES runs(run_id), {", ".join(CASE_FIELDS)},
    PRIMARY KEY (run_id, case_id)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_run(conn: sqlite3.Connection, run: RunResult) -> None:
    with conn:
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
            (run.run_id, run.created_at.isoformat(), run.prompt_version, run.model, run.dataset_version),
        )
        conn.executemany(
            f"INSERT INTO case_results VALUES (?, {', '.join('?' * len(CASE_FIELDS))})",
            [(run.run_id, *astuple(c)) for c in run.cases],
        )


def _load(conn: sqlite3.Connection, row) -> RunResult:
    run_id, created_at, prompt_version, model, dataset_version = row
    rows = conn.execute(
        f"SELECT {', '.join(CASE_FIELDS)} FROM case_results WHERE run_id = ? ORDER BY rowid", (run_id,)
    ).fetchall()
    cases = []
    for r in rows:
        c = CaseResult(*r)
        c.category_correct, c.passed = bool(c.category_correct), bool(c.passed)
        cases.append(c)
    return RunResult(prompt_version=prompt_version, model=model, dataset_version=dataset_version,
                     cases=cases, run_id=run_id, created_at=datetime.fromisoformat(created_at))


def recent_runs(conn: sqlite3.Connection, dataset_version: str, limit: int) -> list[RunResult]:
    """Last `limit` runs for this dataset version, oldest first."""
    rows = conn.execute(
        "SELECT run_id, created_at, prompt_version, model, dataset_version FROM runs "
        "WHERE dataset_version = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (dataset_version, limit),
    ).fetchall()
    return [_load(conn, r) for r in reversed(rows)]


def latest_run(conn: sqlite3.Connection, dataset_version: str) -> RunResult | None:
    runs = recent_runs(conn, dataset_version, 1)
    return runs[0] if runs else None
