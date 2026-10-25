# CLAUDE.md

CI/CD-style regression testing for an LLM feature. Every prompt/model change is run against a hand-labeled golden dataset; regressions are scored, diffed against the previous run, reported (HTML + Slack), and block PR merges when critical.

Full requirements and build phases: @PROJECT_SPEC.md. Update its **Status tracking** checklist when a phase is done.

## Feature under test

A customer-support email classifier: email text in → JSON `{category, summary}` out.
- `category` ∈ `billing | technical | account | general`
- `summary` is one sentence.
- One Python function; the prompt is a parameter, never hardcoded.
- `PromptConfig` (Pydantic) is the interface contract. Change it only deliberately: everything downstream depends on it.

## Stack

Python 3.11+ · OpenAI API (`gpt-4o`, `gpt-4o-mini`) · DeepEval · PyYAML · pytest · SQLite + JSON · Slack incoming webhooks · GitHub Actions · static HTML report · Docker · FastAPI + uvicorn (owner API) · React + Vite + TypeScript (dashboard; frontend deps limited to the list in the frontend plan).

Don't add dependencies beyond this list without asking.

## Layout

```
prompts/vN.yaml          # versioned prompts (immutable; newest created_at is evaluated)
data/golden.json         # golden dataset, hand-written (versioned via its "version" field)
src/regress/
  config.py              # PromptConfig contract, ClassificationResult, Settings.from_env
  feature.py             # classify_email (the feature under test)
  dataset.py             # golden dataset schema + loader
  judge.py               # DeepEval GEval summary relevance, 1-5
  runner.py              # async eval run, per-case scoring
  store.py               # SQLite run history (runs.db)
  compare.py             # previous-run diff, thresholds, slow drift (pure logic)
  report.py              # HTML report + PR markdown summary
  slack.py               # Slack webhook
  cli.py                 # `python -m regress run`, exit codes 0/1/2
  snapshot.py            # dashboard snapshot export (JSON)
  edits.py               # golden/prompt edit rules for the owner API
  api.py                 # FastAPI owner API (`python -m regress serve`)
frontend/                # React + Vite + TypeScript dashboard
tests/                   # fakes.py holds the fake OpenAI client; fixtures/ is synthetic, not golden
.github/workflows/eval.yml
.github/workflows/site.yml   # builds + deploys the public demo to GitHub Pages
Dockerfile
```

## Rules that matter

**Golden dataset**
- Never generate or "fill in" golden test cases with an LLM. They are human-verified ground truth. Claude may propose the *structure* or a case *idea*, but the user writes or verifies every label and summary.
- Each case has: stable `id`, `input`, `expected` (`category`, `summary`), `expected_difficulty`, `notes` (why the case matters).
- IDs never change or get reused. Comparisons between runs key on them.
- Any change to cases means bumping the dataset version, because it moves the eval bar.

**Prompts**
- Prompts live only in `prompts/*.yaml`. Editing a prompt means a new version id, not an in-place edit of an old version.

**Evaluation**
- Score every case on every dimension: category exact match (binary), summary relevance (LLM-as-judge, 1–5), latency, token usage. Persist all of them per case, per run.
- Comparison is always against the previous run: overall pass-rate delta, per-category delta, pass→fail (regressions), fail→pass (improvements).
- Thresholds: warn > 3%, critical > 8%. Configurable via env/config, never hardcoded at the call site.
- Slow drift (rolling 7-run moving average below threshold) is a separate signal from per-run regressions. Keep both.
- Run LLM calls with async batching and a concurrency cap. Retry on rate limits.

**Secrets and config**
- `OPENAI_API_KEY`, `SLACK_WEBHOOK_URL`, and the thresholds come from env vars only. Never commit them. Keep `.env` gitignored and ship a `.env.example`.

**CI**
- The workflow triggers on PRs that touch `prompts/` or `data/golden.json`, posts a PR summary comment, and fails the check on critical regressions.

## Testing

- Unit tests must not call the real OpenAI API or Slack. Mock them.
- Comparison, threshold, and drift logic must have tests, because a bug there means silent false passes.

## Commands

<!-- Fill in once tooling is chosen -->
- Install: `python -m venv .venv && .venv/Scripts/activate && pip install -e ".[dev]"`
- Run eval: `python -m regress run` (exit 0 pass/warn, 1 critical, 2 error)
- Tests: `pytest`
- Owner dashboard: `python -m regress serve` (needs `.[ui]`; build `frontend/` first)
- Frontend dev: `cd frontend && npm run dev`
- Docker: `docker build -t regress . && docker run --rm --env-file .env -v "$PWD/state:/state" regress`

## Environment

Dev machine is Windows (PowerShell / Git Bash). Use forward slashes and `pathlib` in code. CI and Docker run on Linux.
