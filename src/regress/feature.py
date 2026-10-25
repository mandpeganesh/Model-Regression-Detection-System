"""The feature under test: email text in, {category, summary} out."""

import time
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from regress.config import ClassificationResult, PromptConfig


@dataclass
class FeatureResponse:
    result: ClassificationResult | None
    error: str | None
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int


def build_messages(email: str, config: PromptConfig) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": config.system_prompt}]
    for example in config.few_shot_examples:
        messages.append({"role": "user", "content": example.email})
        messages.append({"role": "assistant", "content": example.output.model_dump_json()})
    messages.append({"role": "user", "content": email})
    return messages


async def classify_email(email: str, config: PromptConfig, client: AsyncOpenAI) -> FeatureResponse:
    """Classify one email. Model-behaviour failures become `error`; API failures raise."""
    start = time.perf_counter()
    result, error, usage = None, None, None
    try:
        completion = await client.chat.completions.parse(
            model=config.model,
            messages=build_messages(email, config),
            response_format=ClassificationResult,
            temperature=0,
        )
        message = completion.choices[0].message
        usage = completion.usage
        result = message.parsed
        if result is None:
            error = f"refusal: {message.refusal}" if message.refusal else "parse_error: empty response"
    except openai.LengthFinishReasonError:
        error = "truncated"
    except openai.ContentFilterFinishReasonError:
        error = "content_filter"
    except ValidationError as exc:
        error = f"parse_error: {exc.error_count()} validation error(s)"
    return FeatureResponse(
        result=result,
        error=error,
        latency_ms=(time.perf_counter() - start) * 1000,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )
