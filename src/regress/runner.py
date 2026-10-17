"""Runs every golden case through the feature and scores it on every dimension."""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from regress.config import PromptConfig, Settings
from regress.dataset import GoldenCase, GoldenDataset
from regress.feature import classify_email

Judge = Callable[[str, str, str], Awaitable[int]]


@dataclass
class CaseResult:
    case_id: str
    expected_category: str
    actual_category: str | None
    actual_summary: str | None
    category_correct: bool
    relevance: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    passed: bool
    error: str | None


@dataclass
class RunResult:
    prompt_version: str
    model: str
    dataset_version: str
    cases: list[CaseResult]
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pass_rate(self) -> float:
        return sum(c.passed for c in self.cases) / len(self.cases)

    @property
    def category_accuracy(self) -> dict[str, float]:
        by_category = defaultdict(list)
        for c in self.cases:
            by_category[c.expected_category].append(c.category_correct)
        return {cat: sum(hits) / len(hits) for cat, hits in by_category.items()}

    @property
    def total_tokens(self) -> int:
        return sum(c.prompt_tokens + c.completion_tokens for c in self.cases)

    @property
    def mean_latency_ms(self) -> float:
        return sum(c.latency_ms for c in self.cases) / len(self.cases)


async def run_eval(config: PromptConfig, dataset: GoldenDataset, *, client, judge: Judge, settings: Settings) -> RunResult:
    """API errors (after the client's own retries) propagate and abort the whole run."""
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def score(case: GoldenCase) -> CaseResult:
        async with semaphore:
            response = await classify_email(case.input, config, client)
            result = response.result
            relevance = await judge(case.input, case.expected.summary, result.summary) if result else 1
        correct = result is not None and result.category == case.expected.category
        return CaseResult(
            case_id=case.id,
            expected_category=case.expected.category,
            actual_category=result.category if result else None,
            actual_summary=result.summary if result else None,
            category_correct=correct,
            relevance=relevance,
            latency_ms=response.latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            passed=correct and relevance >= settings.relevance_pass_min,
            error=response.error,
        )

    cases = await asyncio.gather(*(score(c) for c in dataset.cases))
    return RunResult(prompt_version=config.version, model=config.model, dataset_version=dataset.version, cases=list(cases))
