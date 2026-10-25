# Project Spec: Model Regression Detection System

## What you're building

A CI/CD-style pipeline that continuously tests an LLM-powered feature against a golden dataset whenever a prompt or model changes, detects quality regressions, and alerts the team via Slack before bad outputs reach users.

## Why this project matters

Most AI teams ship prompt changes blind, with no systematic check that a "small tweak" hasn't silently degraded quality on edge cases. This project demonstrates thinking about what happens *after* deployment — treating prompts like code that needs regression testing, not just creative writing.

## Tech stack

| Component | Tool / Library | Why this choice |
|---|---|---|
| Language | Python 3.11+ | Industry standard for ML tooling |
| LLM Provider | OpenAI API (gpt-4o / gpt-4o-mini) | Widely recognized; easy to swap later |
| Eval Framework | DeepEval | Shows understanding of eval beyond accuracy |
| Data Storage | SQLite + JSON files | Zero infrastructure, portable, git-friendly |
| Alerting | Slack Webhooks | What real teams actually use |
| Scheduling | GitHub Actions | Runs on every PR; free tier is enough |
| Visualization | Streamlit or simple HTML report | Quick dashboard for diff views |
| Containerization | Docker | Shows production readiness |

## Build phases

### Phase 1 — Define the LLM Feature Under Test (Day 1–2)
1. Build a simple LLM feature: a customer support email classifier that reads an email and returns a category (`billing`, `technical`, `account`, `general`) plus a one-sentence summary. Wrap it in a single Python function with the prompt as a configurable parameter.
2. Version prompts as YAML files in `/prompts`. Each file has a version ID, timestamp, system prompt, and any few-shot examples. This is the "code" the CI runs against.
3. Define a `PromptConfig` (Pydantic) as the interface contract: input is email text, output is structured JSON with `category` and `summary`.

### Phase 2 — Build the Golden Dataset (Day 2–4)
1. Curate 50–100 test cases **by hand** — real-looking customer emails across all categories, each with the correct category and an ideal summary. **Do not generate these with an LLM**; they must be human-verified ground truth.
2. Deliberately include edge cases: ambiguous emails spanning two categories, extremely short emails, typos, mixed-language emails, sarcasm. Tag these with an `expected_difficulty` field.
3. Store as versioned JSON. Each test case has a stable ID, input, expected output, difficulty tag, and a notes field explaining why the case matters. Version the dataset file itself to track when the eval bar changes.

> **Talking point for interviews:** lead with how the golden dataset was built — seeded with hand-labeled data, then expanded over time using real failure cases. Evaluation quality is bounded by data quality.

### Phase 3 — Build the Evaluation Engine (Day 4–7)
1. Test runner: takes a `PromptConfig` and the golden dataset, runs every case through the LLM feature, collects raw outputs. Use async batching for cost and speed.
2. Multi-dimensional scoring: exact category match (binary), summary relevance (LLM-as-judge, 1–5), latency per request, token usage. Store all dimensions per test case.
3. Comparison logic: for every eval run, diff against the previous run — overall pass rate delta, per-category accuracy delta, cases that flipped pass→fail (regressions), cases that flipped fail→pass (improvements).
4. Statistical significance thresholds: warning if delta exceeds 3%, critical if delta exceeds 8%. Make both configurable.

### Phase 4 — Build the Alerting and Reporting Layer (Day 7–9)
1. HTML diff report: run metadata (prompt version, model, timestamp), summary scorecard vs. baseline, table of regressed cases (old output vs. new output side by side), trend chart of scores over the last N runs.
2. Slack alerts via incoming webhook: pass/warn/fail status, headline numbers (e.g. "3 regressions detected, accuracy dropped from 94% to 89%"), link to the full HTML report.
3. Drift detection: rolling 7-run moving average of scores; if it drops below a threshold even with no single-run alert, fire a "slow drift" warning to catch gradual degradation.

### Phase 5 — Wire into CI/CD (Day 9–11)
1. GitHub Action: triggers on every PR modifying `/prompts`. Runs the eval, generates the report, posts a PR summary comment with pass/fail status, blocks merge on critical regressions.
2. Dockerize the eval runner, golden dataset, and reporting layer. Accept env vars for the LLM API key, Slack webhook URL, and threshold configs.
3. README written as onboarding docs, not a tutorial: what this does, setup, how to add test cases, how to adjust thresholds, architecture decisions with rationale.

### Phase 6 — Polish for Portfolio (Day 11–12)
1. Record a 3-minute Loom walkthrough: change a prompt, trigger the eval, show the Slack alert, walk through the diff report.
2. Write a short blog post / README section: the problem (teams ship prompt changes blind), the approach (CI/CD for model behavior), and one design decision to highlight (e.g., why slow drift is tracked separately from per-run regressions).

## Status tracking

- [x] Phase 1
- [x] Phase 2
- [x] Phase 3
- [x] Phase 4
- [x] Phase 5
- [ ] Phase 6