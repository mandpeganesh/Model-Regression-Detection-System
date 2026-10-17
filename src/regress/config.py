"""Interface contract (PromptConfig) and env-driven settings."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

Category = Literal["billing", "technical", "account", "general"]
CATEGORIES: tuple[str, ...] = ("billing", "technical", "account", "general")


class ClassificationResult(BaseModel):
    category: Category
    summary: str


class FewShotExample(BaseModel):
    email: str
    output: ClassificationResult


class PromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    created_at: datetime
    model: str
    system_prompt: str
    few_shot_examples: list[FewShotExample] = []


def load_prompt(path: Path) -> PromptConfig:
    return PromptConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def latest_prompt(prompts_dir: Path) -> Path:
    """The prompt file with the newest created_at."""
    dated = sorted((load_prompt(p).created_at, p) for p in Path(prompts_dir).glob("*.yaml"))
    if not dated:
        raise ValueError(f"no prompt files in {prompts_dir}")
    if len(dated) > 1 and dated[-1][0] == dated[-2][0]:
        raise ValueError(f"{dated[-1][1].name} and {dated[-2][1].name} share created_at; cannot pick latest")
    return dated[-1][1]


@dataclass(frozen=True)
class Settings:
    warn_threshold: float = 0.03
    critical_threshold: float = 0.08
    drift_threshold: float = 0.85
    drift_window: int = 7
    relevance_pass_min: int = 3
    max_concurrency: int = 8
    judge_model: str = "gpt-4o-mini"
    slack_webhook_url: str | None = None
    report_url: str | None = None

    def __post_init__(self):
        for name in ("warn_threshold", "critical_threshold", "drift_threshold"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} must be between 0 and 1")
        if self.warn_threshold >= self.critical_threshold:
            raise ValueError("WARN_THRESHOLD must be below CRITICAL_THRESHOLD")
        if self.drift_window < 1:
            raise ValueError("DRIFT_WINDOW must be >= 1")
        if not 1 <= self.relevance_pass_min <= 5:
            raise ValueError("RELEVANCE_PASS_MIN must be 1..5")
        if self.max_concurrency < 1:
            raise ValueError("MAX_CONCURRENCY must be >= 1")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        kwargs = {}
        for name, typ in (
            ("warn_threshold", float), ("critical_threshold", float), ("drift_threshold", float),
            ("drift_window", int), ("relevance_pass_min", int), ("max_concurrency", int),
            ("judge_model", str), ("slack_webhook_url", str), ("report_url", str),
        ):
            raw = env.get(name.upper(), "").strip()
            if not raw:
                continue
            try:
                kwargs[name] = typ(raw)
            except ValueError:
                raise ValueError(f"{name.upper()}={raw!r} is not a valid {typ.__name__}") from None
        return cls(**kwargs)
