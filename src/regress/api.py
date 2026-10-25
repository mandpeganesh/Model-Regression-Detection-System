"""Local owner API for the dashboard: serves the snapshot, runs evals, edits golden cases and prompts.

Binds to localhost only (see `regress serve`); write endpoints also reject foreign Origins.
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import openai
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from regress import cli
from regress.config import Settings, load_prompt
from regress.dataset import GoldenCase, load_dataset
from regress.edits import add_case, create_prompt, edit_case, save_dataset
from regress.snapshot import build_snapshot, load_prompts
from regress.store import all_runs, used_case_ids, used_dataset_versions


@dataclass
class AppPaths:
    dataset: Path
    prompts_dir: Path
    db: Path
    out: Path
    static_dir: Path | None = None


class CaseBody(BaseModel):
    case: GoldenCase
    new_version: str


class PromptBody(BaseModel):
    version: str
    model: str
    system_prompt: str
    few_shot_examples: list[dict] = []


class RunBody(BaseModel):
    prompt_version: str


def _local_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and urlparse(origin).hostname not in ("localhost", "127.0.0.1"):
        raise HTTPException(403, "write endpoints only accept localhost origins")


def create_app(paths: AppPaths) -> FastAPI:
    app = FastAPI()
    app.state.run_thread = None
    lock = threading.Lock()
    state = {"state": "idle", "done": 0, "total": 0, "run_id": None, "error": None}

    def check_idle() -> None:
        if state["state"] == "running":
            raise HTTPException(409, "a run is in progress")

    @app.exception_handler(ValueError)
    def _value_error(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    def _key_error(request: Request, exc: KeyError):
        return JSONResponse({"detail": f"not found: {exc}"}, status_code=404)

    @app.get("/api/snapshot")
    def snapshot():
        return build_snapshot(cli._read_db(paths.db, all_runs), [], load_dataset(paths.dataset),
                              load_prompts(paths.prompts_dir), Settings.from_env())

    @app.get("/api/runs/current")
    def current():
        with lock:
            return dict(state)

    def do_run(prompt_path: Path) -> None:
        def on_case_done() -> None:
            with lock:
                state["done"] += 1

        try:
            outcome = cli.execute_run(prompt_path, paths.dataset, paths.db, paths.out, Settings.from_env(),
                                      on_case_done=on_case_done)
            result = {"state": "done", "run_id": outcome.run.run_id}
        except (ValueError, ValidationError, FileNotFoundError) as exc:
            result = {"state": "error", "error": str(exc)}
        except openai.OpenAIError as exc:
            result = {"state": "error", "error": f"OpenAI call failed; nothing was stored: {exc}"}
        except Exception as exc:  # the thread must always leave "running"
            result = {"state": "error", "error": f"{type(exc).__name__}: {exc}"}
        with lock:
            state.update(result)

    @app.post("/api/runs", status_code=202, dependencies=[Depends(_local_origin)])
    def start_run(body: RunBody):
        matches = [p for p in paths.prompts_dir.glob("*.yaml") if load_prompt(p).version == body.prompt_version]
        if not matches:
            raise HTTPException(404, f"unknown prompt version {body.prompt_version!r}")
        with lock:
            check_idle()
            total = len(load_dataset(paths.dataset).cases)
            state.update(state="running", done=0, total=total, run_id=None, error=None)
            app.state.run_thread = threading.Thread(target=do_run, args=(matches[0],), daemon=True)
            app.state.run_thread.start()
        return {"run_id": None}

    def write_dataset(make) -> dict:
        with lock:  # also stops a run from starting mid-write
            check_idle()
            ds = make(load_dataset(paths.dataset), set(cli._read_db(paths.db, used_dataset_versions)),
                      set(cli._read_db(paths.db, used_case_ids)))
            save_dataset(paths.dataset, ds)
            return {"version": ds.version}

    @app.post("/api/golden/cases", dependencies=[Depends(_local_origin)])
    def post_case(body: CaseBody):
        return write_dataset(lambda ds, versions, ids: add_case(ds, body.case, body.new_version, versions, ids))

    @app.put("/api/golden/cases/{case_id}", dependencies=[Depends(_local_origin)])
    def put_case(case_id: str, body: CaseBody):
        return write_dataset(lambda ds, versions, ids: edit_case(ds, case_id, body.case, body.new_version, versions))

    @app.post("/api/prompts", status_code=201, dependencies=[Depends(_local_origin)])
    def post_prompt(body: PromptBody):
        with lock:
            check_idle()
            create_prompt(paths.prompts_dir, version=body.version, model=body.model,
                          system_prompt=body.system_prompt, few_shot_examples=body.few_shot_examples,
                          now=datetime.now(timezone.utc))
        return {"path": f"prompts/{body.version}.yaml"}

    if paths.static_dir and paths.static_dir.exists():
        app.mount("/", StaticFiles(directory=paths.static_dir, html=True))
    return app
