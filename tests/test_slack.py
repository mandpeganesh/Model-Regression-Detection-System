import json
import urllib.error

import pytest

from fakes import make_run
from regress import slack
from regress.compare import Drift, EvalOutcome, compare
from regress.config import Settings


def outcome(base_flags, cur_flags, drift=Drift(None, 0.85, 7, False)):
    base = make_run("b", passed_flags=base_flags) if base_flags else None
    cur = make_run("c", passed_flags=cur_flags)
    return EvalOutcome(cur, base, compare(cur, base, Settings()), drift, [cur])


def test_message_headline_numbers():
    # 94 -> 89 with 5 regressions: a 5-point drop is WARN
    msg = slack.build_message(outcome([True] * 94 + [False] * 6, [False] * 5 + [True] * 89 + [False] * 6), "https://r")
    text = msg["text"]
    assert "WARN" in text and "5 regressions detected" in text and "94% → 89%" in text
    assert text.rstrip().endswith("https://r>")


def test_message_drift_line_is_separate():
    text = slack.build_message(outcome([True], [True], Drift(0.8, 0.85, 7, True)), None)["text"]
    assert "PASS" in text and "Slow drift" in text


def test_message_first_run():
    assert "First run" in slack.build_message(outcome(None, [True]), None)["text"]


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_post_sends_json(monkeypatch):
    sent = {}

    def urlopen(req, timeout):
        sent.update(method=req.get_method(), ctype=req.get_header("Content-type"), body=req.data, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(slack.urllib.request, "urlopen", urlopen)
    slack.post("https://hooks.example/x", {"text": "hi ¿"})
    assert sent["method"] == "POST" and sent["ctype"] == "application/json"
    assert json.loads(sent["body"]) == {"text": "hi ¿"} and sent["timeout"] == 10


def test_post_raises_on_http_error(monkeypatch):
    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(slack.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        slack.post("https://hooks.example/x", {"text": "hi"})
