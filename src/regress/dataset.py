"""Golden dataset schema. Cases are hand-written ground truth; this only validates them."""

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from regress.config import ClassificationResult

Difficulty = Literal["easy", "medium", "hard"]


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected: ClassificationResult
    expected_difficulty: Difficulty
    notes: str


class GoldenDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[GoldenCase] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def unique_ids(cls, cases: list[GoldenCase]) -> list[GoldenCase]:
        dupes = [i for i, n in Counter(c.id for c in cases).items() if n > 1]
        if dupes:
            raise ValueError(f"duplicate case ids: {', '.join(dupes)}")
        return cases


def load_dataset(path: Path) -> GoldenDataset:
    return GoldenDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
