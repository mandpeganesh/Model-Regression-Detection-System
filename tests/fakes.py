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
