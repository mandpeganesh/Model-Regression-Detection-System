# Model Regression Detection System

Regression testing for an LLM feature. Every prompt or model change runs against a hand-labeled golden dataset. Each case is scored, the run is diffed against the previous one, and the results go out as an HTML report, a Slack alert and a PR comment. A critical regression fails the PR check.

The feature under test is a customer-support email classifier: email text in, `{category, summary}` out, where `category` is one of `billing | technical | account | general`.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows; use .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
cp .env.example .env            # then fill in OPENAI_API_KEY (and SLACK_WEBHOOK_URL if wanted)
```

Env vars are read from the process environment. Load `.env` yourself (for example `set -a; . ./.env; set +a`) or pass it to Docker with `--env-file .env`.

## Running

```bash
python -m regress run           # newest prompt in prompts/, data/golden.json, runs.db, reports/
pytest                          # unit tests; no network calls
```

Options: `--prompt PATH`, `--prompts-dir`, `--dataset`, `--db`, `--out`.

Every run writes `reports/<run_id>.html` (the full diff report) and `reports/summary.md` (what CI posts on the PR), and prints the summary.

| Exit code | Meaning |
|---|---|
| 0 | pass or warn |
| 1 | critical regression |
| 2 | bad config, bad data, or an OpenAI failure. Nothing is stored. |

### Docker

```bash
docker build -t regress .
docker run --rm --env-file .env -v "$PWD/state:/state" regress
```

Run history and reports go to `./state`. Keep that directory between runs so each run has a baseline to compare against.

## Adding test cases

`data/golden.json` looks like this:

```json
{"version": "1.0.0", "cases": [
  {"id": "billing-001", "input": "...", "expected": {"category": "billing", "summary": "..."},
   "expected_difficulty": "easy", "notes": "why this case matters"}
]}
```

- Write and verify every case by hand. Never generate inputs or labels with an LLM: this file is the ground truth.
- Give each new case a new id. Never reuse or rename an id, because comparisons between runs key on it.
- Tag edge cases (two plausible categories, very short emails, typos, mixed languages, sarcasm) as `medium` or `hard`.
- Bump `version` whenever cases change. Runs are only compared within one dataset version, so the next run becomes a fresh baseline.
- `pytest tests/test_golden_dataset.py` checks the shape: 50–100 cases, all four categories, notes filled in.

## Changing a prompt

Add a new file such as `prompts/v2.yaml`, with a new `version` and a later `created_at`. Never edit an existing prompt file: CI fails PRs that do. The eval runs the prompt with the newest `created_at`.

```yaml
version: v2
created_at: 2026-11-01T00:00:00Z
model: gpt-4o-mini
system_prompt: |
  ...
few_shot_examples:
  - email: "..."
    output: {category: billing, summary: "..."}
```

## Thresholds

All thresholds come from env vars. In CI, set them as repository variables; unset ones use the defaults.

| Env var | Default | Meaning |
|---|---|---|
| `WARN_THRESHOLD` | 0.03 | Pass-rate drop (absolute) above which the run warns |
| `CRITICAL_THRESHOLD` | 0.08 | Pass-rate drop above which the run is critical and the PR check fails |
| `DRIFT_THRESHOLD` | 0.85 | Slow-drift alert when the moving average pass rate falls below this |
| `DRIFT_WINDOW` | 7 | Runs in the moving average |
| `RELEVANCE_PASS_MIN` | 3 | Minimum judge score (1–5) for a summary to pass |
| `MAX_CONCURRENCY` | 8 | Concurrent OpenAI calls |
| `JUDGE_MODEL` | gpt-4o-mini | Model used as the summary judge |
| `REPORT_URL` | (none) | Link to the full report, used in Slack and the PR comment |

## CI

`.github/workflows/eval.yml` runs on PRs and pushes to `main` that touch `prompts/` or `data/golden.json`, and can also be started by hand. Add the repository secrets `OPENAI_API_KEY` and `SLACK_WEBHOOK_URL`. The workflow posts or updates one PR comment with the summary, uploads the HTML report as the `eval-report` artifact, and fails the check on exit codes 1 and 2.

History lives on the `eval-history` branch. `runs.db` gets only `main` runs and is the only baseline. `pr-runs/` holds one DB per PR run (`<pr_number>-<short sha>.db`), which the dashboard shows but which are never a baseline. `site.yml` rebuilds the public demo after each eval and on frontend changes.

## Dashboard

A React dashboard shows run history, trends, drift, PR runs and per-case results.

- **Public demo:** https://mandpeganesh.github.io/Model-Regression-Detection-System/ (read-only, rebuilt from CI history after every eval run).
- **Owner mode** (local; can edit cases and prompts and start runs):

```bash
pip install -e ".[ui]"
set -a; . ./.env; set +a        # load OPENAI_API_KEY etc., as for `run`
cd frontend && npm ci && npm run build && cd ..
python -m regress serve         # then open http://127.0.0.1:8000
```

For frontend work, run `python -m regress serve` and, in another terminal, `cd frontend && npm run dev` (Vite proxies `/api` to the server).

One-time setup for the public site: repo Settings → Pages → Source: GitHub Actions. `.github/workflows/site.yml` then deploys it.

## How it works

```
prompts/*.yaml ─┐
data/golden.json┼─> runner (async, concurrency cap, retries) ─> per-case scores ─> runs.db
                │       classify_email ─ OpenAI structured output
                │       judge_summary  ─ DeepEval GEval (1–5)
                └─> compare (vs previous run) + drift (moving average) ─> HTML report, PR summary, Slack
```

Code is in `src/regress/`: `config` (contract and settings), `feature`, `dataset`, `judge`, `runner`, `store`, `compare`, `report`, `slack` and `cli`.

## Design decisions

- **Every case is scored on every dimension:** category exact match, summary relevance (LLM judge, 1–5), latency and tokens. A case passes when the category is right and relevance is at least `RELEVANCE_PASS_MIN`.
- **Only the overall pass rate gates the check.** Per-category accuracy and its change are reported but don't block: with about 20 cases per category, one flip moves a category by 5 points, which is too noisy to fail a build on.
- **"Exceeds" means strictly greater.** A drop of exactly 3 points is a pass. Drops are rounded before comparing, so floating-point noise (`0.94 - 0.91 = 0.030000000000000027`) can't create false warnings.
- **Comparisons stay within one dataset version.** Changing the cases moves the bar, so pass rates from different versions aren't compared.
- **API outages never become baselines.** If an OpenAI error survives the client's retries, the run aborts with exit code 2 and nothing is stored. Without this, an outage would be recorded as a 0% run and the next good run would look like a huge improvement. Model-behaviour failures (a refusal, unparseable or truncated output) fail only that case.
- **Static HTML report** with an inline SVG trend chart. It needs no server and works as a CI artifact.

### Why slow drift is tracked separately

Per-run checks compare against the previous run only. Five prompt changes that each lose 1 point never trip a 3-point gate, yet together they cost 5 points. The drift check watches the moving average over the last `DRIFT_WINDOW` runs and alerts when it falls below an absolute floor, whatever the individual steps looked like. The two signals answer different questions: "did this change break something?" and "are we slowly getting worse?" Drift is reported on its own line and never fails a PR, because no single change caused it.
