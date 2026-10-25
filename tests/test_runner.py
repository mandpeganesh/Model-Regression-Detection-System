import asyncio

import openai
import pytest

from fakes import FakeClient, parsed, refused
from regress.config import Settings, load_prompt
from regress.dataset import GoldenDataset, load_dataset
from regress.runner import run_eval

CFG = load_prompt("prompts/v1.yaml")
DS = load_dataset("tests/fixtures/mini_dataset.json")
EXPECTED = {c.input: c.expected.category for c in DS.cases}


def answer(overrides=None):
    """Client answering each case with its expected category unless overridden by case input."""
    overrides = overrides or {}

    def respond(kwargs):
        email = kwargs["messages"][-1]["content"]
        return overrides.get(email) or parsed(EXPECTED[email], "A summary.")

    return FakeClient(respond)


def judge_returning(score, calls=None):
    async def judge(email, expected, actual):
        if calls is not None:
            calls.append(email)
        return score

    return judge


def run(client, judge, settings=Settings(), dataset=DS):
    return asyncio.run(run_eval(CFG, dataset, client=client, judge=judge, settings=settings))


def test_all_correct_passes():
    result = run(answer(), judge_returning(4))
    assert result.pass_rate == 1.0
    assert (result.prompt_version, result.model, result.dataset_version) == ("v1", "gpt-4o-mini", "test-1")
    assert [c.case_id for c in result.cases] == [c.id for c in DS.cases]
    assert result.total_tokens == 4 * 15


def test_wrong_category_fails_case():
    result = run(answer({"FIXTURE: refund request": parsed("general", "x")}), judge_returning(4))
    case = result.cases[0]
    assert (case.category_correct, case.passed, case.actual_category) == (False, False, "general")
    assert result.pass_rate == 0.75


def test_low_relevance_fails_case():
    result = run(answer(), judge_returning(2))
    assert not any(c.passed for c in result.cases)
    assert all(c.relevance == 2 for c in result.cases)


def test_case_error_fails_case_and_run_continues():
    calls = []
    result = run(answer({"FIXTURE: app crash": refused("no")}), judge_returning(4, calls))
    case = result.cases[1]
    assert case.error.startswith("refusal") and case.relevance == 1 and not case.passed
    assert "FIXTURE: app crash" not in calls
    assert sum(c.passed for c in result.cases) == 3


def test_api_error_aborts_run():
    with pytest.raises(openai.APIError):
        run(answer({"FIXTURE: app crash": openai.APIConnectionError(request=None)}), judge_returning(4))


def test_category_accuracy_keys_on_expected():
    result = run(answer({"FIXTURE: refund request": parsed("general", "x")}), judge_returning(4))
    assert result.category_accuracy == {"billing": 0.0, "technical": 1.0, "account": 1.0, "general": 1.0}


def test_concurrency_is_capped():
    cases = [c.model_copy(update={"id": f"c{i}", "input": f"email {i}"}) for i, c in enumerate(DS.cases * 5)]
    dataset = GoldenDataset(version="x", cases=cases)
    in_flight = peak = 0

    async def respond(kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return parsed("billing", "x")

    run(FakeClient(respond), judge_returning(4), Settings(max_concurrency=3), dataset)
    assert peak == 3
