import asyncio

import pytest

from regress import judge
from regress.judge import score_to_scale


@pytest.mark.parametrize("score,expected", [(0.0, 1), (0.25, 2), (0.5, 3), (0.75, 4), (1.0, 5), (-0.1, 1), (1.2, 5)])
def test_score_to_scale(score, expected):
    assert score_to_scale(score) == expected


def test_empty_summary_scores_1_without_calling_judge(monkeypatch):
    monkeypatch.setattr(judge, "GEval", lambda **kw: pytest.fail("judge called"))
    assert asyncio.run(judge.judge_summary("e", "exp", "   ", "gpt-4o-mini")) == 1


def test_judge_uses_fresh_metric_per_call(monkeypatch):
    instances = []

    class FakeGEval:
        def __init__(self, **kwargs):
            self.kwargs, self.score = kwargs, None
            instances.append(self)

        async def a_measure(self, test_case):
            self.test_case = test_case
            await asyncio.sleep(0)
            self.score = 0.75
            return self.score

    monkeypatch.setattr(judge, "GEval", FakeGEval)

    async def both():
        return await asyncio.gather(
            judge.judge_summary("e1", "x1", "a1", "gpt-4o-mini"),
            judge.judge_summary("e2", "x2", "a2", "gpt-4o-mini"),
        )

    assert asyncio.run(both()) == [4, 4]
    assert len({id(i) for i in instances}) == 2
    assert instances[0].kwargs["model"] == "gpt-4o-mini"
    tc = instances[1].test_case
    assert (tc.input, tc.expected_output, tc.actual_output) == ("e2", "x2", "a2")
