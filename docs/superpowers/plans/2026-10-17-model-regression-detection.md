# Model Regression Detection System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI (`python -m regress run`) that evaluates a versioned prompt against a hand-labeled golden dataset, scores every case, diffs against the previous run, writes an HTML report + PR markdown summary, posts to Slack, and exits non-zero on critical regressions, wired into GitHub Actions and Docker.

**Architecture:** One Python package `src/regress/`. Pure logic (comparison, thresholds, drift) is separated from I/O (OpenAI, SQLite, Slack, files) so it can be tested without mocks. The OpenAI client and the judge are injected into the runner, so tests pass fakes. SQLite (`runs.db`) holds every run and every per-case score; CI persists it between workflow runs with `actions/cache`.

**Tech Stack:** Python 3.11+ (dev 3.12), `openai` (AsyncOpenAI, structured outputs), `deepeval` (GEval judge), `pydantic` v2, `pyyaml`, stdlib `sqlite3` / `urllib` / `html` / `argparse`, `pytest`, GitHub Actions, Docker.

**Spec:** `PROJECT_SPEC.md` and `CLAUDE.md` (rules section is binding).

## Global Constraints

- Python `>=3.11`; Docker and CI use `python:3.12`.
- Runtime deps: `openai`, `deepeval`, `pydantic>=2`, `pyyaml`. Dev dep: `pytest`. Nothing else. (`pyyaml` and `pytest` are not in CLAUDE.md's stack list. **User must approve before Task 1.**)
- Categories are exactly `billing | technical | account | general`.
- Thresholds from env only, defaults: `WARN_THRESHOLD=0.03`, `CRITICAL_THRESHOLD=0.08`, `DRIFT_THRESHOLD=0.85`, `DRIFT_WINDOW=7`, `RELEVANCE_PASS_MIN=3`, `MAX_CONCURRENCY=8`, `JUDGE_MODEL=gpt-4o-mini`. Never read env at a call site; only `Settings.from_env()` reads it.
- Secrets `OPENAI_API_KEY`, `SLACK_WEBHOOK_URL` come from env; `.env` gitignored; `.env.example` committed.
- Unit tests never hit the network. No pytest plugins: async tests use `asyncio.run(...)`.
- All file I/O passes `encoding="utf-8"` explicitly (dev machine is Windows; default codepage is cp1252).
- Paths via `pathlib`, forward slashes.
- Claude never writes golden test cases or their labels (Task 11 is the user's).
- Prompts are never edited in place; a change is a new `prompts/vN.yaml` file.

## Decisions made in this plan (review these)

- **Case pass** = `category_correct and relevance >= RELEVANCE_PASS_MIN`. Pass rate = passed / total.
- **Per-category accuracy** = fraction `category_correct` among cases whose *expected* category is that category.
- **Delta** is in absolute points (0.94 → 0.90 is a 0.04 drop). Status comes from the overall pass-rate drop only: `> CRITICAL` → critical, `> WARN` → warn, else pass. Per-category deltas are reported, not gated (≈20 cases per category means one flip ≈ 5 points, too noisy to gate). "Exceeds" is strict `>`.
- **Previous run** = most recent stored run with the *same dataset version*. A dataset bump starts a fresh baseline (it moved the bar). No baseline → status `pass`, report says "first run for this dataset version".
- **Drift** = mean pass rate of the last `DRIFT_WINDOW` runs (same dataset version, including current) `< DRIFT_THRESHOLD`. Fewer runs than the window → no drift signal. Reported as its own line, never changes the exit code.
- **Infra errors abort the run**: an `openai.APIError` that survives the client's retries aborts with exit 2 and nothing is stored (otherwise an outage becomes the next baseline). Model-behavior failures (refusal, unparseable, truncated) fail that case and the run continues.
- **Retries** use `AsyncOpenAI(max_retries=6)` (built-in exponential backoff on 429/5xx); concurrency capped with one `asyncio.Semaphore`.
- **Which prompt CI evaluates**: the `prompts/*.yaml` with the latest `created_at`. CI also fails if a PR *modifies* an existing prompt file.
- **Report**: static HTML, trend chart as inline SVG (no JS). Not Streamlit.
- **CI baseline storage**: `runs.db` in `actions/cache` (key `evaldb-<run_id>`, restore prefix `evaldb-`). PRs restore main's cache; cache eviction (7 days unused) means the next run is a fresh baseline.
- **Exit codes**: 0 pass/warn, 1 critical, 2 error.
- `prompts/v1.yaml` ships with no few-shot examples; the user adds them in a new version if wanted.

## Review Focus

1. **Non-ASCII emails on Windows** (mixed-language cases are in the spec): dataset, prompt YAML, HTML and markdown must round-trip `"Ich kann mich nicht einloggen — ¿ayuda? 日本語"` unchanged. Tested in Tasks 3 and 8.
2. **Float edge at the threshold**: 0.94 → 0.91 is exactly a 3-point drop and must be `pass`, not `warn` (`0.94-0.91 == 0.030000000000000027`). Round the drop to 9 decimals before comparing. Tested in Task 7.
3. **API outage / bad key** must exit 2 and store nothing, not record a 0% run that becomes the baseline and shows 100% regressions. Tested in Tasks 5 and 10.
4. **Model refusal or unparseable output** fails that one case with an `error` string; the run completes. Tested in Tasks 2 and 5.
5. **Email text containing HTML** (`<script>alert(1)</script>`) is escaped in the report. Tested in Task 8.

---

## File Structure

```
pyproject.toml                 # deps, pytest config, package discovery (src layout)
.gitignore  .env.example
prompts/v1.yaml                # baseline prompt
data/golden.json               # golden dataset (USER-written, Task 11)
src/regress/
  __init__.py
  __main__.py                  # `python -m regress` -> cli.main
  config.py                    # Category, ClassificationResult, FewShotExample, PromptConfig, load_prompt, latest_prompt, Settings
  feature.py                   # build_messages, classify_email -> FeatureResponse
  dataset.py                   # GoldenCase, GoldenDataset, load_dataset
  judge.py                     # judge_summary (DeepEval GEval), score_to_scale
  runner.py                    # CaseResult, RunResult, run_eval
  store.py                     # SQLite: connect, save_run, latest_run, recent_runs
  compare.py                   # Status, Flip, Comparison, compare, classify_delta, Drift, detect_drift, EvalOutcome
  report.py                    # render_html, render_markdown, write_text
  slack.py                     # build_message, post
  cli.py                       # argparse, wiring, exit codes
tests/
  fixtures/mini_dataset.json   # 4 synthetic fixture cases (NOT golden data)
  fakes.py                     # fake OpenAI client + result builders shared by tests
  test_*.py                    # one per module, plus test_golden_dataset.py
.github/workflows/eval.yml
Dockerfile  .dockerignore
README.md
```

---

### Task 1: Scaffold and contracts

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/regress/__init__.py`, `src/regress/config.py`, `prompts/v1.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Category = Literal["billing", "technical", "account", "general"]`; `CATEGORIES: tuple[str, ...]` in that order.
  - `ClassificationResult(BaseModel)`: `category: Category`, `summary: str`.
  - `FewShotExample(BaseModel)`: `email: str`, `output: ClassificationResult`.
  - `PromptConfig(BaseModel, extra="forbid")`: `version: str`, `created_at: datetime`, `model: str`, `system_prompt: str`, `few_shot_examples: list[FewShotExample] = []`.
  - `load_prompt(path: Path) -> PromptConfig`
  - `latest_prompt(prompts_dir: Path) -> Path` (max `created_at`; raises `ValueError` on empty dir or a tie).
  - `@dataclass(frozen=True) Settings` with fields `warn_threshold: float`, `critical_threshold: float`, `drift_threshold: float`, `drift_window: int`, `relevance_pass_min: int`, `max_concurrency: int`, `judge_model: str`, `slack_webhook_url: str | None`, `report_url: str | None`, defaults per Global Constraints; `Settings.from_env(env: Mapping[str, str] = os.environ) -> Settings`.

- [ ] **Step 1: `git init`, write `pyproject.toml`** (setuptools, src layout, deps per Global Constraints, `[project.optional-dependencies] dev = ["pytest"]`, `[tool.pytest.ini_options] pythonpath = ["src"]`), `.gitignore` (`.env`, `runs.db`, `reports/`, `__pycache__/`, `.venv/`, `*.egg-info/`), `.env.example` (every env var from Global Constraints plus `OPENAI_API_KEY=`, `SLACK_WEBHOOK_URL=`, `REPORT_URL=`, `DEEPEVAL_TELEMETRY_OPT_OUT=YES`). Run `python -m venv .venv` then `pip install -e ".[dev]"`. Expected: installs cleanly.

- [ ] **Step 2: Write failing tests**

```python
def test_load_prompt_v1():
    cfg = load_prompt(Path("prompts/v1.yaml"))
    assert cfg.version == "v1" and cfg.model == "gpt-4o-mini" and cfg.few_shot_examples == []

def test_prompt_rejects_unknown_field(tmp_path): ...  # yaml with extra key "temprature" -> ValidationError
def test_classification_rejects_bad_category():  # ClassificationResult(category="sales", summary="x") -> ValidationError
def test_latest_prompt_picks_newest_created_at(tmp_path): ...  # v1 2026-01-01, v2 2026-02-01 -> v2 path
def test_latest_prompt_tie_raises(tmp_path): ...

def test_settings_defaults():
    s = Settings.from_env({})
    assert (s.warn_threshold, s.critical_threshold, s.drift_threshold, s.drift_window) == (0.03, 0.08, 0.85, 7)
    assert (s.relevance_pass_min, s.max_concurrency, s.judge_model) == (3, 8, "gpt-4o-mini")
    assert s.slack_webhook_url is None and s.report_url is None

def test_settings_from_env_overrides():  # {"WARN_THRESHOLD": "0.05", "CRITICAL_THRESHOLD": "0.1"} -> 0.05, 0.1
def test_settings_invalid_raises_naming_var():  # {"WARN_THRESHOLD": "abc"} -> ValueError with "WARN_THRESHOLD" in str
def test_settings_warn_must_be_below_critical():  # warn 0.1, critical 0.05 -> ValueError
def test_settings_empty_string_is_unset():  # {"SLACK_WEBHOOK_URL": ""} -> None
```

- [ ] **Step 3: Run** `pytest tests/test_config.py -v`. Expected: FAIL (import error).

- [ ] **Step 4: Implement `config.py` and `prompts/v1.yaml`.** `v1.yaml`: `version: v1`, `created_at: 2026-10-17T00:00:00Z`, `model: gpt-4o-mini`, a system prompt that defines each of the four categories in one line, says to pick the single best category when an email spans two, and requires a one-sentence summary; `few_shot_examples: []`. YAML read with `yaml.safe_load` and `encoding="utf-8"`. `Settings` validates: thresholds in `(0, 1)`, `warn < critical`, `drift_window >= 1`, `relevance_pass_min` in `1..5`, `max_concurrency >= 1`.

- [ ] **Step 5: Run** `pytest tests/test_config.py -v`. Expected: PASS.

- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: scaffold package, PromptConfig contract, settings"`

---

### Task 2: Feature under test

**Files:**
- Create: `src/regress/feature.py`, `tests/fakes.py`
- Test: `tests/test_feature.py`

**Interfaces:**
- Consumes: `PromptConfig`, `ClassificationResult` (Task 1).
- Produces:
  - `build_messages(email: str, config: PromptConfig) -> list[dict[str, str]]`: system prompt, then each few-shot as a `user` (email) / `assistant` (`output.model_dump_json()`) pair, then the `user` email.
  - `@dataclass FeatureResponse`: `result: ClassificationResult | None`, `error: str | None`, `latency_ms: float`, `prompt_tokens: int`, `completion_tokens: int`.
  - `async classify_email(email: str, config: PromptConfig, client: AsyncOpenAI) -> FeatureResponse`
  - `tests/fakes.py`: `FakeClient(responses: list | Callable)` exposing `client.chat.completions.parse(**kwargs)` as an async method that records `kwargs` in `client.calls` and returns objects shaped like OpenAI's parsed completion (`.choices[0].message.parsed`, `.choices[0].message.refusal`, `.usage.prompt_tokens`, `.usage.completion_tokens`). Helpers `parsed(category, summary, pt=10, ct=5)` and `refused(text)`. An item that is an `Exception` instance is raised.

- [ ] **Step 1: Write failing tests**

```python
def test_build_messages_orders_few_shots():
    cfg = PromptConfig(version="t", created_at=..., model="gpt-4o-mini", system_prompt="SYS",
                       few_shot_examples=[FewShotExample(email="E1", output=ClassificationResult(category="billing", summary="S1"))])
    msgs = build_messages("NEW", cfg)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0]["content"] == "SYS" and msgs[-1]["content"] == "NEW"
    assert json.loads(msgs[2]["content"]) == {"category": "billing", "summary": "S1"}

def test_classify_success_records_tokens_and_latency():
    r = asyncio.run(classify_email("hi", cfg, FakeClient([parsed("technical", "App crashes.", pt=12, ct=7)])))
    assert r.result.category == "technical" and r.error is None
    assert (r.prompt_tokens, r.completion_tokens) == (12, 7) and r.latency_ms >= 0

def test_classify_passes_model_temperature_and_schema():
    client = FakeClient([parsed("billing", "x")]); asyncio.run(classify_email("hi", cfg, client))
    kw = client.calls[0]
    assert kw["model"] == cfg.model and kw["temperature"] == 0 and kw["response_format"] is ClassificationResult

def test_classify_refusal_is_case_error_not_exception():  # refused("no") -> result None, error startswith "refusal"
def test_classify_api_error_propagates():  # FakeClient([openai.APIConnectionError(request=httpx.Request("POST", "http://x"))]) -> raises openai.APIError
```

- [ ] **Step 2: Run** `pytest tests/test_feature.py -v`. Expected: FAIL (import error).

- [ ] **Step 3: Implement.** Call `client.chat.completions.parse(model=config.model, messages=..., response_format=ClassificationResult, temperature=0)`; if the installed `openai` only has `client.beta.chat.completions.parse`, use that and make `FakeClient` mirror it. Time with `time.perf_counter()`. Catch `pydantic.ValidationError`, `openai.LengthFinishReasonError`, `openai.ContentFilterFinishReasonError` into `error` (`"parse_error: ..."`, `"truncated"`, `"content_filter"`); `parsed is None` with a refusal → `"refusal: <text>"`. Let every other `openai.APIError` propagate.

- [ ] **Step 4: Run** `pytest tests/test_feature.py -v`. Expected: PASS.

- [ ] **Step 5: Commit** `git commit -am "feat: email classifier with structured output" ` (add new files first).

---

### Task 3: Golden dataset schema and loader

**Files:**
- Create: `src/regress/dataset.py`, `tests/fixtures/mini_dataset.json`
- Test: `tests/test_dataset.py`, `tests/test_golden_dataset.py`

**Interfaces:**
- Consumes: `Category`, `ClassificationResult`, `CATEGORIES`.
- Produces:
  - `Difficulty = Literal["easy", "medium", "hard"]`
  - `GoldenCase(BaseModel, extra="forbid")`: `id: str`, `input: str` (min length 1), `expected: ClassificationResult`, `expected_difficulty: Difficulty`, `notes: str`.
  - `GoldenDataset(BaseModel, extra="forbid")`: `version: str`, `cases: list[GoldenCase]` (non-empty; duplicate `id` → validation error naming the id).
  - `load_dataset(path: Path) -> GoldenDataset`
  - File format: `{"version": "1.0.0", "cases": [ {...}, ... ]}`.
  - Fixture `tests/fixtures/mini_dataset.json`: version `"test-1"`, ids `t-billing-1`, `t-technical-1`, `t-account-1`, `t-general-1`, one per category, inputs are obviously synthetic (`"FIXTURE: refund request"` etc.); `t-general-1` input is `"FIXTURE: Ich kann mich nicht einloggen — ¿ayuda? 日本語 <script>alert(1)</script>"`.

- [ ] **Step 1: Write failing tests**

```python
FIXTURE = Path("tests/fixtures/mini_dataset.json")

def test_loads_fixture():
    ds = load_dataset(FIXTURE)
    assert ds.version == "test-1" and [c.id for c in ds.cases] == ["t-billing-1", "t-technical-1", "t-account-1", "t-general-1"]

def test_non_ascii_round_trips():
    assert "¿ayuda? 日本語" in load_dataset(FIXTURE).cases[3].input

def test_duplicate_ids_rejected(tmp_path): ...       # ValueError/ValidationError mentioning the duplicated id
def test_unknown_field_rejected(tmp_path): ...       # "expected_dificulty" typo -> ValidationError
def test_bad_category_rejected(tmp_path): ...
def test_empty_cases_rejected(tmp_path): ...
```

`tests/test_golden_dataset.py` guards the real file (skips until it exists):

```python
GOLDEN = Path("data/golden.json")
pytestmark = pytest.mark.skipif(not GOLDEN.exists(), reason="golden dataset not written yet")

def test_golden_dataset_shape():
    ds = load_dataset(GOLDEN)
    assert 50 <= len(ds.cases) <= 100
    assert {c.expected.category for c in ds.cases} == set(CATEGORIES)
    assert {c.expected_difficulty for c in ds.cases} >= {"easy", "hard"}
    assert all(c.notes.strip() for c in ds.cases)
```

- [ ] **Step 2: Run** `pytest tests/test_dataset.py tests/test_golden_dataset.py -v`. Expected: FAIL in test_dataset, golden SKIPPED.

- [ ] **Step 3: Implement** `dataset.py`; read with `encoding="utf-8"`, parse via `GoldenDataset.model_validate_json`.

- [ ] **Step 4: Run** same command. Expected: PASS (golden SKIPPED).

- [ ] **Step 5: Commit** `feat: golden dataset schema and loader`

---

### Task 4: Summary relevance judge

**Files:**
- Create: `src/regress/judge.py`
- Test: `tests/test_judge.py`

**Interfaces:**
- Produces:
  - `score_to_scale(score: float) -> int`: `1 + round(score * 4)`, clamped to `1..5`.
  - `async judge_summary(email: str, expected_summary: str, actual_summary: str, model: str) -> int` (1–5).
  - Runner's judge type (Task 5) is `Callable[[str, str, str], Awaitable[int]]`; CLI binds `model` with `functools.partial`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("score,expected", [(0.0, 1), (0.25, 2), (0.5, 3), (0.75, 4), (1.0, 5), (-0.1, 1), (1.2, 5)])
def test_score_to_scale(score, expected):
    assert score_to_scale(score) == expected

def test_empty_summary_scores_1_without_calling_judge(monkeypatch):
    monkeypatch.setattr(judge, "GEval", lambda **kw: pytest.fail("judge called"))
    assert asyncio.run(judge.judge_summary("e", "exp", "   ", "gpt-4o-mini")) == 1

def test_judge_uses_fresh_metric_per_call(monkeypatch):
    # fake GEval class: records instances; a_measure sets self.score = 0.75
    ...  # two concurrent judge_summary calls via asyncio.gather -> both return 4, two distinct instances created
```

- [ ] **Step 2: Run** `pytest tests/test_judge.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** Build a **new** `GEval` per call (an instance stores `.score`, so sharing one across concurrent calls races): `name="Summary relevance"`, criteria "Does the actual summary capture the customer's core issue as the expected summary does, in one sentence?", `evaluation_params=[INPUT, ACTUAL_OUTPUT, EXPECTED_OUTPUT]`, `model=model`. `await metric.a_measure(LLMTestCase(input=email, actual_output=actual_summary, expected_output=expected_summary))`, return `score_to_scale(metric.score)`. Import `GEval` at module level as `judge.GEval` so tests can patch it.

- [ ] **Step 4: Run** `pytest tests/test_judge.py -v`. Expected: PASS.

- [ ] **Step 5: Commit** `feat: DeepEval summary relevance judge`

---

### Task 5: Runner and per-case scoring

**Files:**
- Create: `src/regress/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `classify_email`, `FeatureResponse` (Task 2), `GoldenDataset` (Task 3), judge type (Task 4), `Settings`, `PromptConfig`.
- Produces:
  - `@dataclass CaseResult`: `case_id: str`, `expected_category: str`, `actual_category: str | None`, `actual_summary: str | None`, `category_correct: bool`, `relevance: int`, `latency_ms: float`, `prompt_tokens: int`, `completion_tokens: int`, `passed: bool`, `error: str | None`.
  - `@dataclass RunResult`: `run_id: str` (`uuid4().hex[:12]`), `created_at: datetime` (UTC), `prompt_version: str`, `model: str`, `dataset_version: str`, `cases: list[CaseResult]`; properties `pass_rate -> float`, `category_accuracy -> dict[str, float]` (only categories present in the run), `total_tokens -> int`, `mean_latency_ms -> float`.
  - `async run_eval(config: PromptConfig, dataset: GoldenDataset, *, client, judge, settings: Settings) -> RunResult`

- [ ] **Step 1: Write failing tests** (use `FakeClient`, a fake judge returning a fixed int, fixture dataset)

```python
def test_all_correct_passes():  # client answers each case with its expected category, judge -> 4: pass_rate == 1.0
def test_wrong_category_fails_case():  # t-billing-1 answered "general": that case category_correct False, passed False; pass_rate == 0.75
def test_low_relevance_fails_case():  # judge -> 2 with relevance_pass_min 3: all passed False
def test_case_error_fails_case_and_run_continues():  # refused() for one case: error set, relevance 1, judge not called for it, other 3 pass
def test_api_error_aborts_run():  # one case raises openai.APIConnectionError -> run_eval raises openai.APIError
def test_category_accuracy_keys_on_expected():  # 1 of 4 wrong -> {"billing": 0.0, "technical": 1.0, "account": 1.0, "general": 1.0}

def test_concurrency_is_capped():
    # fake client's parse awaits asyncio.sleep(0.01) and tracks max in-flight; 20 cases (fixture cases repeated with new ids)
    ...  # with max_concurrency=3: assert peak == 3
```

- [ ] **Step 2: Run** `pytest tests/test_runner.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** One `asyncio.Semaphore(settings.max_concurrency)` wraps classify + judge per case; `asyncio.gather` over cases (an exception propagates and aborts). Judge only when `result` is not None; else `relevance = 1`. Preserve dataset order in `cases`.

- [ ] **Step 4: Run** `pytest tests/test_runner.py -v`. Expected: PASS.

- [ ] **Step 5: Commit** `feat: async eval runner with per-case scoring`

---

### Task 6: SQLite run store

**Files:**
- Create: `src/regress/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `RunResult`, `CaseResult`.
- Produces:
  - `connect(path: Path) -> sqlite3.Connection` (creates tables `runs(run_id PK, created_at, prompt_version, model, dataset_version)` and `case_results(run_id, case_id, <every CaseResult field>, PRIMARY KEY(run_id, case_id))`).
  - `save_run(conn, run: RunResult) -> None` (one transaction).
  - `latest_run(conn, dataset_version: str) -> RunResult | None`
  - `recent_runs(conn, dataset_version: str, limit: int) -> list[RunResult]` (oldest → newest).
  - Ordering: `created_at` then insertion `rowid`.

- [ ] **Step 1: Write failing tests** (build `RunResult`s by hand; add a `make_run(run_id, dataset_version, created_at, passed_flags)` helper to `tests/fakes.py`)

```python
def test_round_trip(tmp_path):  # save then latest_run returns an equal RunResult (all CaseResult fields, created_at tz-aware)
def test_latest_run_filters_dataset_version(tmp_path):  # runs on "1.0.0" and "2.0.0" -> latest_run("1.0.0") is the 1.0.0 one
def test_latest_run_none_when_empty(tmp_path):
def test_recent_runs_order_and_limit(tmp_path):  # 9 runs -> recent_runs(limit=7) returns last 7, oldest first
def test_persists_across_connections(tmp_path):  # close, reconnect, still there
```

- [ ] **Step 2: Run** `pytest tests/test_store.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with stdlib `sqlite3`; datetimes stored as ISO strings.
- [ ] **Step 4: Run** `pytest tests/test_store.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: SQLite run history`

---

### Task 7: Comparison, thresholds, drift

**Files:**
- Create: `src/regress/compare.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: `RunResult`, `CaseResult`, `Settings`.
- Produces:
  - `class Status(StrEnum)`: `PASS="pass"`, `WARN="warn"`, `CRITICAL="critical"`.
  - `classify_delta(delta: float, warn: float, critical: float) -> Status` — `delta` is current − baseline; drop = `round(-delta, 9)`; `drop > critical` → CRITICAL, `drop > warn` → WARN, else PASS.
  - `@dataclass Flip`: `case_id: str`, `before: CaseResult`, `after: CaseResult`.
  - `@dataclass Comparison`: `baseline_run_id: str | None`, `pass_rate: float`, `baseline_pass_rate: float | None`, `pass_rate_delta: float | None`, `category_deltas: dict[str, float]` (categories in both runs), `regressions: list[Flip]`, `improvements: list[Flip]`, `status: Status`.
  - `compare(current: RunResult, baseline: RunResult | None, settings: Settings) -> Comparison` — flips only for case ids present in both runs, sorted by `case_id`.
  - `@dataclass Drift`: `moving_average: float | None`, `threshold: float`, `window: int`, `drifting: bool`.
  - `detect_drift(pass_rates: list[float], window: int, threshold: float) -> Drift` (uses last `window` values; fewer → `moving_average=None, drifting=False`).
  - `@dataclass EvalOutcome`: `run: RunResult`, `baseline: RunResult | None`, `comparison: Comparison`, `drift: Drift`, `history: list[RunResult]` (oldest → newest, includes `run`).

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("before,after,status", [
    (0.94, 0.91, Status.PASS),      # exactly 3 points: not "exceeds"; float trap
    (0.94, 0.90, Status.WARN),
    (0.94, 0.86, Status.WARN),      # exactly 8 points
    (0.94, 0.85, Status.CRITICAL),
    (0.80, 0.95, Status.PASS),      # improvement
    (0.90, 0.90, Status.PASS),
])
def test_classify_delta(before, after, status):
    assert classify_delta(after - before, 0.03, 0.08) is status

def test_no_baseline_is_pass():  # compare(run, None, s): status PASS, deltas None, no flips
def test_flips():  # baseline passes a,b fails c; current fails a, passes b,c -> regressions ["a"], improvements ["c"]
def test_cases_missing_from_one_run_ignored():  # id only in current -> not a flip
def test_category_deltas():  # billing accuracy 1.0 -> 0.5 gives category_deltas["billing"] == -0.5
def test_thresholds_come_from_settings():  # same runs, Settings(warn 0.01) -> WARN, default -> PASS

def test_drift_needs_full_window():  # 6 rates with window 7 -> moving_average None, drifting False
def test_drift_fires_below_threshold():  # [0.9, 0.88, 0.86, 0.84, 0.83, 0.82, 0.81] th 0.85 -> avg ≈ 0.8486, drifting True
def test_drift_uses_last_window_only():  # 10 old 0.5s then 7 x 0.95 -> drifting False
def test_drift_without_per_run_alert():  # each step drops 1 point (all PASS by classify_delta) yet drift fires
```

- [ ] **Step 2: Run** `pytest tests/test_compare.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** (pure functions, no I/O).
- [ ] **Step 4: Run** `pytest tests/test_compare.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: run comparison, thresholds, slow drift detection`

---

### Task 8: HTML report and PR markdown summary

**Files:**
- Create: `src/regress/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `EvalOutcome`, `GoldenDataset`.
- Produces:
  - `render_html(outcome: EvalOutcome, dataset: GoldenDataset) -> str` — sections: run metadata (run id, prompt version, model, dataset version, UTC timestamp, total tokens, mean latency); scorecard vs baseline (pass rate, delta, status, per-category accuracy + delta); slow-drift line; regressed cases table (id, email input, expected, old category+summary, new category+summary, new error); improvements list; inline-SVG line of pass rate over `history` (last 20 runs, labeled with prompt version). All dynamic text through `html.escape`. Self-contained, no external assets.
  - `render_markdown(outcome: EvalOutcome, report_url: str | None) -> str` — status line (`✅ PASS` / `⚠️ WARN` / `❌ CRITICAL`), pass rate `old → new (delta)`, regression and improvement counts, up to 10 regressed ids, drift line if drifting, report link if given.
  - `write_text(path: Path, text: str) -> Path` (creates parent dirs, utf-8).

- [ ] **Step 1: Write failing tests** (build an `EvalOutcome` from `make_run` + `compare` + `detect_drift`; dataset = fixture; one regression on `t-general-1`)

```python
def test_html_escapes_email_text():
    html = render_html(outcome, ds)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html

def test_html_contains_metadata_and_regression():  # prompt version, model, "t-general-1", old and new summaries present
def test_html_trend_has_point_per_run():  # history of 5 -> svg polyline with 5 points
def test_first_run_html():  # baseline None -> contains "first run" text, no crash
def test_markdown_headline():  # contains "CRITICAL" (or chosen status), "1 regression", "94% → 85%"
def test_markdown_drift_line_only_when_drifting():
def test_write_text_round_trips_unicode(tmp_path):  # "¿ayuda? 日本語" written and read back with utf-8
```

- [ ] **Step 2: Run** `pytest tests/test_report.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with f-strings and `html.escape`; SVG points scaled to a fixed 600×120 viewBox, y from 0–100%.
- [ ] **Step 4: Run** `pytest tests/test_report.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: HTML diff report and PR summary`

---

### Task 9: Slack alert

**Files:**
- Create: `src/regress/slack.py`
- Test: `tests/test_slack.py`

**Interfaces:**
- Consumes: `EvalOutcome`, `Status`.
- Produces:
  - `build_message(outcome: EvalOutcome, report_url: str | None) -> dict` — `{"text": ...}`: first line `"{emoji} {STATUS} · prompt {version} · {model}"`; headline `"{n} regressions detected, pass rate dropped from 94% to 89%"` (or "rose"/"unchanged"; "first run for dataset X" with no baseline); separate line `"📉 Slow drift: {window}-run average {avg:.0%} below {threshold:.0%}"` only when drifting; report link last.
  - `post(webhook_url: str, payload: dict, timeout: float = 10) -> None` — stdlib `urllib.request`, JSON body, raises on non-2xx or network error.

- [ ] **Step 1: Write failing tests**

```python
def test_message_headline_numbers():  # 3 regressions, 0.94 -> 0.89: text contains "3 regressions detected" and "94% to 89%" and "WARN"
def test_message_drift_line_is_separate():  # drifting outcome with PASS status: contains "Slow drift" and "PASS"
def test_message_first_run():
def test_post_sends_json(monkeypatch):  # patch urllib.request.urlopen; assert method POST, Content-Type application/json, body round-trips
def test_post_raises_on_http_error(monkeypatch):  # urlopen raises HTTPError -> post raises
```

- [ ] **Step 2: Run** `pytest tests/test_slack.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_slack.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Slack webhook alerts`

---

### Task 10: CLI wiring and exit codes

**Files:**
- Create: `src/regress/cli.py`, `src/regress/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `main(argv: list[str] | None = None) -> int`; `__main__.py` does `raise SystemExit(main())`.
  - Command: `python -m regress run [--prompt PATH] [--prompts-dir prompts] [--dataset data/golden.json] [--db runs.db] [--out reports]`. Without `--prompt`, uses `latest_prompt(prompts_dir)`.
  - `make_client() -> AsyncOpenAI` returns `AsyncOpenAI(max_retries=6)`; module-level so tests monkeypatch `cli.make_client` and `cli.judge_summary`.
  - Flow: settings → prompt → dataset → `baseline = latest_run(conn, ds.version)` → `run_eval` → `save_run` → `history = recent_runs(conn, ds.version, 20)` → `compare` → `detect_drift([r.pass_rate for r in history], ...)` → write `out/<run_id>.html` and `out/summary.md` → Slack if `slack_webhook_url` set (failure logs a warning to stderr, never changes exit code) → print summary markdown to stdout.
  - Exit: 0 PASS/WARN, 1 CRITICAL, 2 on `ValueError`/`pydantic.ValidationError`/`FileNotFoundError` (config/data) or `openai.APIError` (message to stderr, nothing saved).

- [ ] **Step 1: Write failing tests** (monkeypatch client + judge; temp db/out; fixture dataset; `--prompt prompts/v1.yaml`)

```python
def test_first_run_exits_0_and_writes_reports(tmp_path, monkeypatch):  # all correct; out has <run_id>.html and summary.md; db has 1 run
def test_critical_regression_exits_1(tmp_path, monkeypatch):  # run 1 all correct; run 2 two wrong (pass 1.0 -> 0.5) -> 1
def test_warn_exits_0(tmp_path, monkeypatch):  # use Settings via env WARN_THRESHOLD=0.01, CRITICAL_THRESHOLD=0.5 and one wrong of 4 -> 0
def test_api_failure_exits_2_and_saves_nothing(tmp_path, monkeypatch):  # client raises APIConnectionError -> 2; latest_run is None
def test_bad_env_exits_2(tmp_path, monkeypatch):  # WARN_THRESHOLD=abc -> 2
def test_slack_failure_does_not_change_exit(tmp_path, monkeypatch):  # SLACK_WEBHOOK_URL set, slack.post raises -> still 0
def test_slack_skipped_without_webhook(tmp_path, monkeypatch):  # post never called
```

- [ ] **Step 2: Run** `pytest tests/test_cli.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with `argparse` and `asyncio.run`.
- [ ] **Step 4: Run** `pytest -v` (whole suite). Expected: all PASS, golden SKIPPED.
- [ ] **Step 5: Commit** `feat: regress CLI with exit codes`

---

### Task 11: Golden dataset — USER WRITES THIS (agent does not)

**Files:** Create `data/golden.json` (by the user).

The agent stops here and hands off. Claude may suggest *case ideas* or review structure on request, but writes no inputs, labels, or summaries.

- [ ] **Step 1 (user):** write 50–100 cases in the Task 3 format, `version: "1.0.0"`, ids like `billing-001` (never reused), all four categories, edge cases (two-category ambiguity, very short, typos, mixed language, sarcasm) tagged `hard`/`medium`, `notes` saying why each matters.
- [ ] **Step 2:** `pytest tests/test_golden_dataset.py -v`. Expected: PASS (no longer skipped).
- [ ] **Step 3 (user, needs `OPENAI_API_KEY`):** `python -m regress run`. Expected: exit 0, `reports/<run_id>.html` opens and looks right. This is the first baseline.
- [ ] **Step 4:** commit `data: golden dataset v1.0.0`

---

### Task 12: GitHub Actions and Docker

**Files:**
- Create: `.github/workflows/eval.yml`, `Dockerfile`, `.dockerignore`

**Interfaces:**
- Consumes: CLI from Task 10 (exit codes, `reports/summary.md`).

- [ ] **Step 1: Write `eval.yml`.** Triggers: `pull_request` with `paths: ["prompts/**"]`, `push` to `main` with same paths, `workflow_dispatch`. `permissions: contents: read, pull-requests: write`. Steps, in order:
  1. `actions/checkout@v4` with `fetch-depth: 0`; `actions/setup-python@v5` 3.12; `pip install .`
  2. PR only: fail if an existing prompt was modified: `git diff --name-only --diff-filter=MR origin/${{ github.base_ref }}...HEAD -- prompts/` non-empty → `exit 1` with message "Prompts are immutable; add a new version file".
  3. `actions/cache/restore@v4` path `runs.db`, key `evaldb-${{ github.run_id }}`, `restore-keys: evaldb-`.
  4. Eval step `id: eval`: `set +e; python -m regress run; echo "code=$?" >> "$GITHUB_OUTPUT"`. Env: `OPENAI_API_KEY`, `SLACK_WEBHOOK_URL` from secrets; thresholds from `vars.*` (repo variables, fall back to code defaults when unset); `REPORT_URL=${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`; `DEEPEVAL_TELEMETRY_OPT_OUT=YES`.
  5. `actions/upload-artifact@v4` name `eval-report`, path `reports/`, `if: always()`.
  6. `actions/cache/save@v4` path `runs.db` key `evaldb-${{ github.run_id }}`, only if `steps.eval.outputs.code` is `0` or `1` (a code-2 run stored nothing).
  7. PR only, `if: always() && hashFiles('reports/summary.md') != ''`: `gh pr comment ${{ github.event.pull_request.number }} --body-file reports/summary.md --edit-last --create-if-none` with `GH_TOKEN: ${{ github.token }}`.
  8. Final: `exit ${{ steps.eval.outputs.code }}` (fails the check on 1 or 2).

- [ ] **Step 2: Write `Dockerfile`** — `python:3.12-slim`, `WORKDIR /app`, copy `pyproject.toml src prompts data`, `pip install --no-cache-dir .`, `ENTRYPOINT ["python", "-m", "regress"]`, `CMD ["run", "--db", "/state/runs.db", "--out", "/state/reports"]`. `.dockerignore`: `.git .venv .env runs.db reports tests docs`.

- [ ] **Step 3: Verify Docker.** `docker build -t regress .` then `docker run --rm regress run --help`. Expected: argparse help text. (A real run: `docker run --rm --env-file .env -v "$PWD/state:/state" regress`.)

- [ ] **Step 4: Verify workflow syntax.** Push a branch with a new `prompts/v2.yaml` (copy of v1 with new version/created_at) and open a PR. Expected: workflow runs, PR gets one summary comment, artifact `eval-report` present. Then edit `prompts/v1.yaml` in the same PR. Expected: immutability step fails. Revert that edit.

- [ ] **Step 5: Commit** `ci: eval workflow on prompt PRs, Dockerfile`

---

### Task 13: Docs and status

**Files:**
- Create: `README.md`
- Modify: `CLAUDE.md` (Layout + Commands sections), `PROJECT_SPEC.md` (Status tracking)

- [ ] **Step 1: README** as onboarding docs: what it does (3 lines); setup (venv, `pip install -e ".[dev]"`, `.env` from `.env.example`); run (`python -m regress run`, exit codes); how to add a test case (append with a new never-reused id, bump `version`, explain fresh baseline); how to change a prompt (new `prompts/vN.yaml`, never edit old); thresholds table (env var, default, meaning); CI setup (secrets `OPENAI_API_KEY`, `SLACK_WEBHOOK_URL`; optional repo variables for thresholds); architecture decisions with rationale — each bullet from "Decisions made in this plan", and a short section on why slow drift is separate from per-run regressions (five 1-point drops never trip a 3-point gate, but are a 5-point loss).
- [ ] **Step 2: CLAUDE.md** — replace "Layout (planned)" with the real tree; fill Commands: Install `pip install -e ".[dev]"`, Run eval `python -m regress run`, Tests `pytest`, Docker `docker build -t regress . && docker run --rm --env-file .env -v "$PWD/state:/state" regress`.
- [ ] **Step 3: PROJECT_SPEC.md** — tick Phases 1, 3, 4, 5 that are done; Phase 2 only once Task 11 is done; Phase 6 (Loom, blog) is the user's.
- [ ] **Step 4: Run** `pytest -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `docs: README, CLAUDE.md commands, status`

---

## Out of scope

- Phase 6 Loom recording and blog post (user).
- Real statistical significance tests (spec defines significance as the 3%/8% thresholds; with ≤100 cases a binomial test would rarely fire anyway). Add if the dataset grows past a few hundred cases.
- Streamlit dashboard (static HTML covers the report).
- Fork PRs: secrets are unavailable, so the eval step fails with exit 2. Acceptable for a single-owner repo.
