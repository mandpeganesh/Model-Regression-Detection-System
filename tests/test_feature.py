import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import openai
import pytest

from fakes import FakeClient, parsed, refused
from regress.config import ClassificationResult, FewShotExample, PromptConfig
from regress.feature import build_messages, classify_email

cfg = PromptConfig(version="t", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), model="gpt-4o-mini", system_prompt="SYS")


def test_build_messages_orders_few_shots():
    few = cfg.model_copy(update={"few_shot_examples": [
        FewShotExample(email="E1", output=ClassificationResult(category="billing", summary="S1"))
    ]})
    msgs = build_messages("NEW", few)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0]["content"] == "SYS" and msgs[-1]["content"] == "NEW"
    assert json.loads(msgs[2]["content"]) == {"category": "billing", "summary": "S1"}


def test_classify_success_records_tokens_and_latency():
    r = asyncio.run(classify_email("hi", cfg, FakeClient([parsed("technical", "App crashes.", pt=12, ct=7)])))
    assert r.result.category == "technical" and r.error is None
    assert (r.prompt_tokens, r.completion_tokens) == (12, 7) and r.latency_ms >= 0


def test_classify_passes_model_temperature_and_schema():
    client = FakeClient([parsed("billing", "x")])
    asyncio.run(classify_email("hi", cfg, client))
    kw = client.calls[0]
    assert kw["model"] == cfg.model and kw["temperature"] == 0 and kw["response_format"] is ClassificationResult


def test_classify_refusal_is_case_error_not_exception():
    r = asyncio.run(classify_email("hi", cfg, FakeClient([refused("no")])))
    assert r.result is None and r.error.startswith("refusal")


def test_classify_truncation_is_case_error():
    r = asyncio.run(classify_email("hi", cfg, FakeClient([openai.LengthFinishReasonError(completion=SimpleNamespace(usage=None))])))
    assert r.result is None and r.error == "truncated"


def test_classify_api_error_propagates():
    err = openai.APIConnectionError(request=None)
    with pytest.raises(openai.APIError):
        asyncio.run(classify_email("hi", cfg, FakeClient([err])))
