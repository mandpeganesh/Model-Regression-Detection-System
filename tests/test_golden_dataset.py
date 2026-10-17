from pathlib import Path

import pytest

from regress.config import CATEGORIES
from regress.dataset import load_dataset

GOLDEN = Path("data/golden.json")
pytestmark = pytest.mark.skipif(not GOLDEN.exists(), reason="golden dataset not written yet")


def test_golden_dataset_shape():
    ds = load_dataset(GOLDEN)
    assert 50 <= len(ds.cases) <= 100
    assert {c.expected.category for c in ds.cases} == set(CATEGORIES)
    assert {c.expected_difficulty for c in ds.cases} >= {"easy", "hard"}
    assert all(c.notes.strip() for c in ds.cases)
