import json

import openai
import pytest

from fakes import FakeClient, parsed
from regress import cli, slack
from regress.config import Settings
from regress.dataset import load_dataset
from regress.store import connect, latest_run, list_pr_runs

DS_PATH = "tests/fixtures/mini_dataset.json"
EXPECTED = {c.input: c.expected.category for c in load_dataset(DS_PATH).cases}
ENV_VARS = [f.upper() for f in Settings.__dataclass_fields__]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    async def judge(email, expected, actual, model):
        return 4

    monkeypatch.setattr(cli, "judge_summary", judge)


def use_client(monkeypatch, wrong=0, error=None):
    """Client that gets the first `wrong` cases wrong, or raises `error`."""
    order = list(EXPECTED)

    def respond(kwargs):
        if error:
            return error
        email = kwargs["messages"][-1]["content"]
        return parsed("general" if order.index(email) < wrong else EXPECTED[email], "A summary.")

    monkeypatch.setattr(cli, "make_client", lambda: FakeClient(respond))


def run(tmp_path):
    return cli.main(["run", "--prompt", "prompts/v1.yaml", "--dataset", DS_PATH,
                     "--db", str(tmp_path / "runs.db"), "--out", str(tmp_path / "reports")])


def test_first_run_exits_0_and_writes_reports(tmp_path, monkeypatch):
    use_client(monkeypatch)
    assert run(tmp_path) == 0
    saved = latest_run(connect(tmp_path / "runs.db"), "test-1")
    assert (tmp_path / "reports" / f"{saved.run_id}.html").exists()
    assert "First run" in (tmp_path / "reports" / "summary.md").read_text(encoding="utf-8")


def test_critical_regression_exits_1(tmp_path, monkeypatch):
    use_client(monkeypatch)
    assert run(tmp_path) == 0
    use_client(monkeypatch, wrong=2)
    assert run(tmp_path) == 1


def test_warn_exits_0(tmp_path, monkeypatch):
    monkeypatch.setenv("WARN_THRESHOLD", "0.01")
    monkeypatch.setenv("CRITICAL_THRESHOLD", "0.5")
    use_client(monkeypatch)
    run(tmp_path)
    use_client(monkeypatch, wrong=1)
    assert run(tmp_path) == 0
    assert "WARN" in (tmp_path / "reports" / "summary.md").read_text(encoding="utf-8")


def test_api_failure_exits_2_and_saves_nothing(tmp_path, monkeypatch):
    use_client(monkeypatch, error=openai.APIConnectionError(request=None))
    assert run(tmp_path) == 2
    assert latest_run(connect(tmp_path / "runs.db"), "test-1") is None


def test_bad_env_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("WARN_THRESHOLD", "abc")
    use_client(monkeypatch)
    assert run(tmp_path) == 2


def test_missing_dataset_exits_2(tmp_path, monkeypatch):
    use_client(monkeypatch)
    assert cli.main(["run", "--prompt", "prompts/v1.yaml", "--dataset", str(tmp_path / "nope.json"),
                     "--db", str(tmp_path / "runs.db"), "--out", str(tmp_path / "r")]) == 2


def test_slack_failure_does_not_change_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(slack, "post", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    use_client(monkeypatch)
    assert run(tmp_path) == 0


def test_slack_posted_with_report_url(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setenv("REPORT_URL", "https://ci.example/run/9")
    monkeypatch.setattr(slack, "post", lambda url, payload: sent.append((url, payload)))
    use_client(monkeypatch)
    run(tmp_path)
    assert sent[0][0] == "https://hooks.example/x" and "https://ci.example/run/9" in json.dumps(sent[0][1])


def test_slack_skipped_without_webhook(tmp_path, monkeypatch):
    monkeypatch.setattr(slack, "post", lambda *a, **k: pytest.fail("posted"))
    use_client(monkeypatch)
    assert run(tmp_path) == 0


def test_missing_api_key_exits_2(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "make_client", lambda: cli.AsyncOpenAI(max_retries=6))
    assert run(tmp_path) == 2


def run_pr(tmp_path):
    return cli.main(["run", "--prompt", "prompts/v1.yaml", "--dataset", DS_PATH,
                     "--db", str(tmp_path / "runs.db"), "--out", str(tmp_path / "reports"),
                     "--record-to", str(tmp_path / "pr.db"), "--pr-number", "7", "--head-sha", "s"])


def test_record_to_saves_pr_run_and_leaves_baseline_db(tmp_path, monkeypatch):
    use_client(monkeypatch)
    assert run(tmp_path) == 0
    use_client(monkeypatch, wrong=1)
    assert run_pr(tmp_path) == 0
    assert len(connect(tmp_path / "runs.db").execute("SELECT 1 FROM runs").fetchall()) == 1
    [(pr_run, number, sha)] = list_pr_runs(connect(tmp_path / "pr.db"))
    assert (number, sha, pr_run.pass_rate) == (7, "s", 0.75)


def test_record_to_critical_exits_1(tmp_path, monkeypatch):
    use_client(monkeypatch)
    assert run(tmp_path) == 0
    use_client(monkeypatch, wrong=2)
    assert run_pr(tmp_path) == 1


def test_pr_args_must_come_together(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--pr-number", "7"])
    assert exc.value.code == 2
