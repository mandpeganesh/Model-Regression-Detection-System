import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from regress.dataset import load_dataset

FIXTURE = Path("tests/fixtures/mini_dataset.json")


def write(tmp_path, data) -> Path:
    p = tmp_path / "ds.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def fixture_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_loads_fixture():
    ds = load_dataset(FIXTURE)
    assert ds.version == "test-1"
    assert [c.id for c in ds.cases] == ["t-billing-1", "t-technical-1", "t-account-1", "t-general-1"]


def test_non_ascii_round_trips():
    assert "¿ayuda? 日本語" in load_dataset(FIXTURE).cases[3].input


def test_duplicate_ids_rejected(tmp_path):
    data = fixture_data()
    data["cases"][1]["id"] = "t-billing-1"
    with pytest.raises(ValidationError, match="t-billing-1"):
        load_dataset(write(tmp_path, data))


def test_unknown_field_rejected(tmp_path):
    data = fixture_data()
    data["cases"][0]["expected_dificulty"] = "easy"
    with pytest.raises(ValidationError):
        load_dataset(write(tmp_path, data))


def test_bad_category_rejected(tmp_path):
    data = fixture_data()
    data["cases"][0]["expected"]["category"] = "sales"
    with pytest.raises(ValidationError):
        load_dataset(write(tmp_path, data))


def test_empty_cases_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_dataset(write(tmp_path, {"version": "x", "cases": []}))


def test_empty_input_rejected(tmp_path):
    data = fixture_data()
    data["cases"][0]["input"] = ""
    with pytest.raises(ValidationError):
        load_dataset(write(tmp_path, data))
