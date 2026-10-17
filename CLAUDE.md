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

Python 3.11+ · OpenAI API (`gpt-4o`, `gpt-4o-mini`) · DeepEval · SQLite + JSON · Slack incoming webhooks · GitHub Actions · Streamlit or static HTML report · Docker.

Don't add dependencies beyond this list without asking.

## Layout (planned)

```
prompts/        # versioned prompt YAML: version id, timestamp, system prompt, few-shot examples
data/           # golden dataset JSON (versioned)
src/            # feature, runner, scoring, comparison, drift, report, alerts
reports/        # generated HTML reports (gitignored)
tests/
.github/workflows/
Dockerfile
```

Update this section when the real layout settles.

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
- The workflow triggers on PRs that touch `prompts/`, posts a PR summary comment, and fails the check on critical regressions.

## Testing

- Unit tests must not call the real OpenAI API or Slack. Mock them.
- Comparison, threshold, and drift logic must have tests, because a bug there means silent false passes.

## Commands

<!-- Fill in once tooling is chosen -->
- Install: `TBD`
- Run eval: `TBD`
- Tests: `TBD`
- Docker: `TBD`

## Environment

Dev machine is Windows (PowerShell / Git Bash). Use forward slashes and `pathlib` in code. CI and Docker run on Linux.
