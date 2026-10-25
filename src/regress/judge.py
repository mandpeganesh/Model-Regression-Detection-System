"""LLM-as-judge for summary relevance (DeepEval GEval), scored 1-5."""

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

CRITERIA = (
    "Does the actual output summarise the customer's core issue or request as the "
    "expected output does, accurately and in one sentence?"
)


def score_to_scale(score: float) -> int:
    """Map GEval's 0-1 score onto 1-5."""
    return min(5, max(1, 1 + round(score * 4)))


async def judge_summary(email: str, expected_summary: str, actual_summary: str, model: str) -> int:
    if not actual_summary.strip():
        return 1
    # A new metric per call: GEval keeps its score on the instance, so sharing one races.
    metric = GEval(
        name="Summary relevance",
        criteria=CRITERIA,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
        model=model,
    )
    await metric.a_measure(LLMTestCase(input=email, actual_output=actual_summary, expected_output=expected_summary))
    return score_to_scale(metric.score)
