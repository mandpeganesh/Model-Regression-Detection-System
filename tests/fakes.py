"""Fake OpenAI client and builders shared by tests. No network."""

from types import SimpleNamespace

from regress.config import ClassificationResult


def parsed(category: str, summary: str, pt: int = 10, ct: int = 5):
    message = SimpleNamespace(parsed=ClassificationResult(category=category, summary=summary), refusal=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct),
    )


def refused(text: str):
    message = SimpleNamespace(parsed=None, refusal=text)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1),
    )


class FakeClient:
    """Mimics `client.chat.completions.parse`.

    `responses` is a list consumed in order, or a callable `(kwargs) -> response`
    (sync or async). An Exception instance is raised instead of returned.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if callable(self.responses):
            response = self.responses(kwargs)
            if hasattr(response, "__await__"):
                response = await response
        else:
            response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_run(run_id, dataset_version="1.0.0", created_at=None, passed_flags=(True,), categories=None, prompt_version="v1"):
    """A RunResult built by hand; case ids are c0, c1, ...; passed cases are also category-correct."""
    from datetime import datetime, timezone

    from regress.runner import CaseResult, RunResult

    categories = categories or ["billing"] * len(passed_flags)
    cases = [
        CaseResult(
            case_id=f"c{i}", expected_category=cat, actual_category=cat if ok else "general",
            actual_summary=f"summary {run_id} {i}", category_correct=ok, relevance=4 if ok else 2,
            latency_ms=100.0, prompt_tokens=10, completion_tokens=5, passed=ok, error=None,
        )
        for i, (ok, cat) in enumerate(zip(passed_flags, categories))
    ]
    return RunResult(
        prompt_version=prompt_version, model="gpt-4o-mini", dataset_version=dataset_version, cases=cases,
        run_id=run_id, created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
