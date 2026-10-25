# Frontend design: regression dashboard

Status: draft for review · 2026-10-25

## Intent

A web frontend for the regression-detection system, built mainly as a **portfolio/demo piece** (Loom video, blog, recruiters). It must look like a real app, not a report page, and must show the project's core ideas: per-case scoring, run-vs-previous-run diffs, thresholds, slow drift, immutable prompts and a human-verified golden dataset.

One app, two modes:

- **Public demo mode:** read-only, static, hosted on GitHub Pages. Shows the real CI history from `main` and updates automatically. No server, no API key, nothing a visitor can trigger or change.
- **Local owner mode:** the same app on the owner's machine, backed by a local API. Adds: start an eval run, add or edit golden cases, and create new prompt versions.

## Goals

- Dashboard of run history, pass-rate trend, status, drift.
- Run detail with per-category accuracy and case-level before/after diffs.
- Browse golden cases and prompt versions (both modes).
- Owner mode: trigger runs with live progress; edit golden cases; create new prompt versions.
- Public demo updates itself from CI history with no manual step, and shows PR runs (including blocked regressions) next to `main`'s history.
- CI history is durable: it no longer disappears when the Actions cache is evicted.

## Non-goals

- Hosted multi-user service, logins, auth. Owner mode is local only.
- Visitors running evals or editing anything in the demo.
- Deleting golden cases from the UI (do it by hand, so the "IDs never reused" rule stays safe).
- Committing or pushing from the UI. Edits change local files; the owner commits and opens a PR, and CI evaluates as it does today.
- Owner mode inside Docker. The existing Docker image stays CLI-only.
- Replacing `report.py`'s static HTML report or the PR summary. Both stay.

## Anti-goals (would make this a failure even if it works)

- Any LLM generating or filling in golden labels, summaries, notes or case text. No "AI suggest" anywhere.
- A golden case ID changed, reused, or a case change saved without a dataset version bump.
- An existing `prompts/*.yaml` file overwritten.
- The frontend re-implementing pass/fail, threshold, delta or drift logic. Those stay in `compare.py`; the frontend only displays computed values.
- The OpenAI key or Slack webhook ever reaching the browser or the public site.
- The owner API reachable from other machines.

## Constraints

- Existing rules in `CLAUDE.md` stay binding (golden dataset, prompts, evaluation, secrets).
- `PromptConfig` unchanged.
- Thresholds only via `Settings.from_env()`.
- Windows dev, Linux CI: `pathlib`, forward slashes, explicit `encoding="utf-8"` on all file I/O. Non-ASCII email text must round-trip through API, JSON snapshot and UI.
- Unit tests make no network calls (OpenAI and Slack mocked, as today).

## Decided

### Stack (approved by the owner: "full stack OK")

- **Backend:** FastAPI + uvicorn, in a new optional extra `[project.optional-dependencies] ui = ["fastapi", "uvicorn"]`. The CLI, CI eval job and Docker image don't install it.
- **Frontend:** React + Vite + TypeScript in `frontend/`. JS dependencies limited to `react`, `react-dom`, `vite`, `@vitejs/plugin-react`, `typescript` (+ their `@types`). **(My call)** No router, chart, CSS or state libraries: hash-based routing (works on GitHub Pages without 404 handling), hand-written SVG charts (as `report.py` already does), plain CSS. Anything beyond this list needs the owner's OK.
- Update `CLAUDE.md`'s Stack and Layout sections to match.

### Layout (approved via mockups: option A)

Sidebar nav: **Overview · Runs · Golden cases · Prompts**. Top bar holds **▶ Run eval** (owner only). Owner-only elements are not rendered at all in demo mode.

1. **Overview:** tiles for latest pass rate (with change vs previous run), status (PASS/WARN/CRITICAL), drift (moving average or "needs N runs"), tokens/latency. Pass-rate trend chart with the drift floor drawn as a dashed line and points labelled by prompt version. Recent-runs table (run id, prompt, pass rate, change, status), rows link to run detail.
2. **Runs → Run detail:** metadata line (run id, prompt version, model, dataset version, UTC time, baseline run id + its prompt version or "first run for this dataset version"). Tiles: pass rate with old → new and points change, regressions count, improvements count, tokens/latency. Per-category accuracy bars with deltas, labelled "reported, not gated". Filter chips: Regressions / Improvements / All failing / All. Case table: id, difficulty, expected category, before (category + relevance), after (category + relevance). Expanding a row shows the email text, expected summary, before and after summaries side by side, error if any, and the case notes.
3. **Golden cases:** dataset version and counts; search; filter by category and difficulty; table with id, category, difficulty, latest result (pass/fail from the latest run on that dataset version). Owner: **+ Add case** and an edit panel. ID field locked when editing. Notes required. Saving requires choosing a new dataset version, with a warning that the next run starts a fresh baseline. No delete. No AI assistance.
4. **Prompts:** version list (newest first, with created date, model and latest pass rate for that version), read-only diff between any two versions. Owner: **+ New version from vX** opens an editor pre-filled from that version; saves a new `prompts/<version>.yaml`.
5. **Run eval (owner):** dialog with prompt selector (default newest by `created_at`), dataset shown read-only, progress bar `done / total cases`, then navigates to the new run's detail. One run at a time.

### Data flow

```
                 ┌── regress export ──> snapshot.json ──> React build (demo) ──> GitHub Pages
runs.db ─┐       │
golden ──┼──> regress.snapshot.build_snapshot()   (Python; uses store + compare)
prompts ─┘       │
                 └── GET /api/snapshot ──> React app (owner)   +   write endpoints (owner)
```

- **One data shape for both modes.** A new Python function `build_snapshot(...)` in `src/regress/snapshot.py` produces everything the UI shows: all runs with per-case results; for each run its `Comparison` against the previous run of the same dataset version and its `Drift` (computed with `compare.compare` and `compare.detect_drift`, in the same way `cli.run_command` does); the current golden dataset; every prompt version's full content; and the threshold settings in effect. The frontend never computes status, deltas or drift itself.
- **Public demo:** new CLI subcommand `python -m regress export --db runs.db [--pr-db pr-runs.db] [--dataset ...] [--prompts-dir ...] --out <path>/snapshot.json` writes `build_snapshot(...)` as JSON (`ensure_ascii=False`, utf-8). The demo build fetches `./data/snapshot.json`.
- **Owner mode:** `GET /api/snapshot` returns the same JSON from the local `runs.db`, `data/golden.json` and `prompts/`. The frontend refetches it after any write or finished run.
- **Mode switch (my call):** build-time flag. The Pages build sets `VITE_DEMO=1` (read snapshot file, render no owner UI). The owner build talks to `/api`.
- Statuses in the snapshot are computed with the thresholds in effect at export time, which matches what CI reported as long as thresholds don't change.
- **(My call)** Snapshot size ceiling: about 80 cases × run count. Fine to a few hundred runs; paginate per run if it grows past that.

### Owner API (local only)

`python -m regress serve [--port 8000]` starts uvicorn bound to **127.0.0.1** only and serves the API plus the built frontend (`frontend/dist`). In development, the Vite dev server proxies `/api` to it. **(My call)** Write endpoints check the `Origin`/`Host` headers against localhost, so a malicious web page can't send writes to the local API.

- `GET /api/snapshot`: as above.
- `POST /api/runs` with `{prompt_version}`: starts a run in the background; `409` if one is already running. **Same pipeline as the CLI**: save to `runs.db`, write the HTML report and `summary.md`, Slack if configured. Refactor `cli.run_command`'s body into a shared function so the CLI and API don't diverge; the CLI keeps its exit codes. On an OpenAI/config error nothing is stored (as today) and the error is reported to the UI.
- `GET /api/runs/current`: `{state: idle|running|done|error, done, total, run_id, error}`; the UI polls it about every second.
- Progress needs one small change: `run_eval` gets an optional progress callback (`on_case_done`), default `None`, so existing callers and tests are unaffected.
- `POST /api/golden/cases` (add) and `PUT /api/golden/cases/{id}` (edit), both with a required `new_version`. The server enforces:
  - the whole resulting file validates as `GoldenDataset` (so existing schema rules apply);
  - the version bump rule below (frozen versions, no reuse of old version strings);
  - edit: the case id in the body equals the path id (IDs can't be renamed);
  - add: the id isn't in the current file **and** never appears in `runs.db`'s `case_results` (catches reuse of an id that was removed by hand);
  - written back to `data/golden.json` with `ensure_ascii=False`, `indent=2`, utf-8, preserving case order (new cases appended).
- `POST /api/prompts` with a full prompt body: validated as `PromptConfig`; `version` must not exist among loaded prompts and `prompts/<version>.yaml` must not exist (never overwrite); `created_at` is set by the server to now (UTC) so it becomes the newest prompt. Written as YAML, utf-8.
- Secrets stay server-side: the API reads `OPENAI_API_KEY` and `SLACK_WEBHOOK_URL` from env as the CLI does (owner loads `.env` before `serve`, as the README already says for `run`). No endpoint returns them.

### CI run history (decided: durable history branch, PR runs shown)

The Actions cache is replaced as the store of CI history, because GitHub evicts it after 7 days unused (wiping both the demo and the CI baseline) and PR-scoped cache entries are invisible to `main`.

- An orphan branch **`eval-history`** holds two SQLite files with the existing `store.py` schema:
  - `runs.db`: runs from pushes to `main`. **This alone is the baseline** for every comparison, exactly as today.
  - `pr-runs.db`: runs from PRs, plus a small extra table `pr_runs(run_id, pr_number, head_sha)`. Never used as a baseline.
- `eval.yml` changes:
  - Check out `eval-history` (into a subdirectory) instead of restoring the cache; if the branch doesn't exist yet, start empty and create it on the first save.
  - On `main`: `regress run --db <history>/runs.db`, then commit and push `runs.db` to `eval-history`.
  - On a PR: baseline from `<history>/runs.db`, but the run is saved to `<history>/pr-runs.db` with its PR number and head SHA, then committed and pushed. This needs a new CLI option to save somewhere other than the baseline DB (e.g. `--record-to PATH --pr-number N --head-sha SHA`); default behaviour unchanged.
  - Exit code 2 stores nothing, so nothing is committed.
  - `permissions: contents: write` (for the branch push). All eval jobs share one concurrency group (`eval-history`, `cancel-in-progress: false`) so pushes to the binary DB files never race. Accepted limit: GitHub keeps only one queued run per group, so a burst of pushes can skip an intermediate PR run; fine for a single-owner repo.
  - Remove the `actions/cache` steps.
- **Triggers now include `data/golden.json`** (decided), on both `pull_request` and `push` to `main`, so a dataset bump gets its baseline straight away. Update the CI rule in `CLAUDE.md` ("triggers on PRs that touch `prompts/` or `data/golden.json`") and the README.
- Fork PRs still can't push (no secrets, no write token); out of scope as before.

### Public site deployment (decided: CI history, automatic)

New workflow `.github/workflows/site.yml`:

- Triggers: `workflow_run` of "Prompt regression eval" completed (any branch, since PR runs are shown too); `push` to `main` touching `frontend/**` or `src/regress/snapshot.py`; `workflow_dispatch`. (`workflow_run` is needed because pushes made with `GITHUB_TOKEN`, like the history commit, don't trigger workflows.)
- Steps: check out `main`'s code and the `eval-history` branch; `pip install .`; `python -m regress export --db <history>/runs.db --pr-db <history>/pr-runs.db --out frontend/public/data/snapshot.json` (with golden and prompts read from `main`); `npm ci && npm run build` with `VITE_DEMO=1`; deploy with `actions/upload-pages-artifact` + `actions/deploy-pages`. Permissions `pages: write`, `id-token: write`. Threshold repo variables are passed as env, as in `eval.yml`.
- If `eval-history` doesn't exist yet, the site deploys with an empty snapshot and shows "No runs yet".
- **Owner action needed once:** repo Settings → Pages → Source: "GitHub Actions".
- The snapshot includes golden emails and prompts, which are already public in the repo, so the demo exposes nothing new.

### PR runs in the UI

- Snapshot gets a `pr_runs` list: each PR run with its PR number, head SHA, and its `Comparison` against the `main` baseline it was evaluated against (the latest `main` run of the same dataset version at export time; **my call**, close enough since baselines only move on merge).
- Overview: a **"Pull requests"** panel listing the latest run per PR with status: `CRITICAL → blocked`, `WARN`/`PASS → passed`, and a link to the PR on GitHub. This is where a visitor sees a regression get caught.
- Clicking a PR run opens the normal run detail, labelled "PR #N · not merged into history".
- PR runs never appear in the main trend line or drift calculation.

### Dataset versions in the UI (my calls)

- Overview, trend, drift and the Runs table show **one dataset version at a time**: the current one by default, with a selector for older versions. Trends and drift restart per version, matching `compare.py`.
- Run detail shows email text, expected summary and notes only when the run's dataset version equals the current file's version. For older versions it shows the stored per-case results and the note "Case text is from a different dataset version and isn't shown." (Run history doesn't store case text; the schema stays unchanged.)

### Dataset version bump rule (my call, protects baselines)

- A dataset version is **frozen once any run in the local `runs.db` used it**. Saving an edit to a frozen version requires a new version string.
- While the current version has no runs yet (a pending version), further edits may keep it, so editing five cases before committing produces one new version, not five.
- A new version string must not already appear in `runs.db` (no reuse of an old version with new content).
- The API refuses golden and prompt writes while a run is in progress.

### Testing

- pytest, no network: `build_snapshot` (comparisons and drift match `compare.py` for a hand-built history, first-run case, multiple dataset versions, PR runs compared against the main baseline and excluded from trend/drift, non-ASCII text round-trips); the CLI's `--record-to` saves to the PR DB and leaves the baseline DB untouched; every golden/prompt guard above, one test per rule including the version bump rule (these protect ground truth); writes refused while a run is in progress and from a non-localhost `Origin`; run endpoint `409` while busy and "nothing stored" on an API error, with the fake client. Use FastAPI's `TestClient` (its `httpx` dependency is already installed via `openai`).
- Workflows: verified by a real PR, as with Task 12 (PR run appears in `pr-runs.db` on `eval-history` and on the site; merge creates a `main` run; a golden-only PR triggers the eval).
- Frontend: `tsc --noEmit` and `vite build` must pass, in CI before deploy. **(My call)** No JS unit-test framework.

## Left to the builder

- Component structure, styling details, colours (match the mockups' feel: dark top bar, light content, green/amber/red status tags).
- Exact JSON field names in the snapshot (keep them close to the Python dataclasses).
- How `site.yml` passes artifacts between steps; Node version (current LTS).
- Whether `regress serve` rebuilds the frontend or expects a prior `npm run build` (document whichever).
- README section for the frontend (owner mode setup, Pages setup).

## Mockups

Approved mockups (layout A and the four screens) are in `.superpowers/brainstorm/1690-1792931085/content/` (`layout.html`, `screens.html`). Add `.superpowers/` to `.gitignore`.
