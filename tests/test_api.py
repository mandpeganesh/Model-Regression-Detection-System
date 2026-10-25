import builtins
import shutil
import sys
import threading
from pathlib import Path

import openai
import pytest
from fastapi.testclient import TestClient

from fakes import FakeClient, parsed
from regress import api, cli
from regress.api import AppPaths, create_app
from regress.config import Settings
from regress.dataset import load_dataset
from regress.store import all_runs, connect

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset.json"
EXPECTED = {c.input: c.expected.category for c in load_dataset(FIXTURE).cases}
ENV_VARS = [f.upper() for f in Settings.__dataclass_fields__]
NEW_CASE = {"id": "t-new-1", "input": "FIXTURE: new", "expected": {"category": "billing", "summary": "New."},
            "expected_difficulty": "easy", "notes": "why"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    async def judge(email, expected, actual, model):
        return 4

    monkeypatch.setattr(cli, "judge_summary", judge)


def use_client(monkeypatch, error=None, gate=None):
    def respond(kwargs):
        if gate:
            gate.wait(5)
        return error or parsed(EXPECTED[kwargs["messages"][-1]["content"]], "A summary.")

    monkeypatch.setattr(cli, "make_client", lambda: FakeClient(respond))


def make_app(tmp_path):
    (tmp_path / "prompts").mkdir()
    shutil.copy(ROOT / "prompts" / "v1.yaml", tmp_path / "prompts" / "v1.yaml")
    shutil.copy(FIXTURE, tmp_path / "golden.json")
    paths = AppPaths(tmp_path / "golden.json", tmp_path / "prompts", tmp_path / "runs.db", tmp_path / "reports", None)
    app = create_app(paths)
    return app, TestClient(app), paths


def test_snapshot_endpoint(tmp_path):
    _, client, _ = make_app(tmp_path)
    body = client.get("/api/snapshot").json()
    assert body["dataset"]["version"] == "test-1" and body["runs"] == []


def test_run_completes_and_is_stored(tmp_path, monkeypatch):
    use_client(monkeypatch)
    app, client, _ = make_app(tmp_path)
    assert client.post("/api/runs", json={"prompt_version": "v1"}).status_code == 202
    app.state.run_thread.join(10)
    cur = client.get("/api/runs/current").json()
    assert cur["state"] == "done" and cur["done"] == cur["total"] == 4 and cur["run_id"]
    assert len(client.get("/api/snapshot").json()["runs"]) == 1


def test_second_run_while_busy_is_409(tmp_path, monkeypatch):
    gate = threading.Event()
    use_client(monkeypatch, gate=gate)
    app, client, _ = make_app(tmp_path)
    assert client.post("/api/runs", json={"prompt_version": "v1"}).status_code == 202
    assert client.post("/api/runs", json={"prompt_version": "v1"}).status_code == 409
    gate.set()
    app.state.run_thread.join(10)


def test_api_error_stores_nothing(tmp_path, monkeypatch):
    use_client(monkeypatch, error=openai.APIConnectionError(request=None))
    app, client, paths = make_app(tmp_path)
    client.post("/api/runs", json={"prompt_version": "v1"})
    app.state.run_thread.join(10)
    cur = client.get("/api/runs/current").json()
    assert cur["state"] == "error" and cur["error"]
    assert all_runs(connect(paths.db)) == []


def test_unknown_prompt_version_404(tmp_path):
    _, client, _ = make_app(tmp_path)
    assert client.post("/api/runs", json={"prompt_version": "nope"}).status_code == 404


def test_add_case_then_snapshot_shows_it(tmp_path):
    _, client, _ = make_app(tmp_path)
    r = client.post("/api/golden/cases", json={"case": NEW_CASE, "new_version": "test-2"})
    assert r.status_code == 200 and r.json() == {"version": "test-2"}
    assert client.get("/api/snapshot").json()["dataset"]["version"] == "test-2"


def test_golden_write_422_on_rule_break(tmp_path):
    _, client, _ = make_app(tmp_path)
    r = client.post("/api/golden/cases", json={"case": {**NEW_CASE, "id": "t-billing-1"}, "new_version": "test-2"})
    assert r.status_code == 422 and "t-billing-1" in r.json()["detail"]


def test_golden_write_during_run_409_file_untouched(tmp_path, monkeypatch):
    gate = threading.Event()
    use_client(monkeypatch, gate=gate)
    app, client, paths = make_app(tmp_path)
    before = paths.dataset.read_bytes()
    client.post("/api/runs", json={"prompt_version": "v1"})
    r = client.post("/api/golden/cases", json={"case": NEW_CASE, "new_version": "test-2"})
    gate.set()
    app.state.run_thread.join(10)
    assert r.status_code == 409 and paths.dataset.read_bytes() == before


def test_write_from_foreign_origin_403(tmp_path):
    _, client, _ = make_app(tmp_path)
    body = {"case": NEW_CASE, "new_version": "test-2"}
    assert client.post("/api/golden/cases", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/golden/cases", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_create_prompt_201(tmp_path):
    _, client, paths = make_app(tmp_path)
    r = client.post("/api/prompts", json={"version": "v2", "model": "gpt-4o-mini", "system_prompt": "Classify.",
                                          "few_shot_examples": []})
    assert r.status_code == 201 and r.json() == {"path": "prompts/v2.yaml"}
    assert (paths.prompts_dir / "v2.yaml").exists()
    assert "v2" in [p["version"] for p in client.get("/api/snapshot").json()["prompts"]]


def test_serve_without_ui_extra_exits_2(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] in ("fastapi", "uvicorn"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "regress.api", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert cli.main(["serve"]) == 2


def test_committed_version_is_frozen_with_empty_db(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "committed_version", lambda dataset: "test-1")
    _, client, _ = make_app(tmp_path)
    r = client.post("/api/golden/cases", json={"case": NEW_CASE, "new_version": "test-1"})
    assert r.status_code == 422 and "test-1" in r.json()["detail"]


def test_edit_unknown_case_404(tmp_path):
    _, client, _ = make_app(tmp_path)
    r = client.put("/api/golden/cases/t-nope", json={"case": {**NEW_CASE, "id": "t-nope"}, "new_version": "test-2"})
    assert r.status_code == 404
