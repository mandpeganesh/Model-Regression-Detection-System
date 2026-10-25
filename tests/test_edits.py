import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from regress.config import latest_prompt, load_prompt
from regress.dataset import GoldenCase, GoldenDataset, load_dataset
from regress.edits import add_case, check_version, create_prompt, edit_case, save_dataset

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "mini_dataset.json"
NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def _case(id, summary="A summary."):
    return GoldenCase(
        id=id, input="some email", expected={"category": "billing", "summary": summary},
        expected_difficulty="easy", notes="why",
    )


def _ds():
    return load_dataset(FIXTURE)


def _prompts(tmp_path):
    shutil.copy(ROOT / "prompts" / "v1.yaml", tmp_path / "v1.yaml")
    return tmp_path


def _new_prompt(d, version="v2", **kw):
    args = dict(version=version, model="gpt-4o-mini", system_prompt="Line one.\nLine two ¿ü? 日本語\n",
                few_shot_examples=[], now=NOW)
    return create_prompt(d, **{**args, **kw})


def test_frozen_version_needs_bump():
    with pytest.raises(ValueError):
        check_version("1.0.0", "1.0.0", {"1.0.0"})


def test_pending_version_may_be_kept():
    check_version("1.0.1", "1.0.1", {"1.0.0"})


def test_old_version_cannot_be_reused():
    with pytest.raises(ValueError):
        check_version("1.0.1", "1.0.0", {"1.0.0"})


def test_add_rejects_existing_id():
    with pytest.raises(ValueError):
        add_case(_ds(), _case("t-billing-1"), "test-2", set(), set())


def test_add_rejects_id_seen_in_history():
    with pytest.raises(ValueError):
        add_case(_ds(), _case("old-id"), "test-2", set(), {"old-id"})


def test_add_appends_and_keeps_others():
    ds = _ds()
    new = add_case(ds, _case("t-new"), "test-2", {"test-1"}, set())
    assert new.cases[:-1] == ds.cases
    assert new.cases[-1].id == "t-new"
    assert new.version == "test-2"


def test_edit_cannot_rename():
    with pytest.raises(ValueError):
        edit_case(_ds(), "t-billing-1", _case("B999"), "test-2", set())


def test_edit_unknown_id():
    with pytest.raises(KeyError):
        edit_case(_ds(), "nope", _case("nope"), "test-2", set())


def test_edit_keeps_position():
    ds = _ds()
    new = edit_case(ds, "t-account-1", _case("t-account-1", "Changed."), "test-2", {"test-1"})
    assert [c.id for c in new.cases] == [c.id for c in ds.cases]
    assert new.cases[2].expected.summary == "Changed."
    assert new.version == "test-2"


def test_save_round_trips_unicode(tmp_path):
    ds = _ds()
    p = tmp_path / "g.json"
    save_dataset(p, ds)
    assert "¿ayuda? 日本語" in p.read_text(encoding="utf-8")
    assert load_dataset(p) == ds


def test_create_prompt_writes_new_newest_file(tmp_path):
    d = _prompts(tmp_path)
    path = _new_prompt(d)
    assert path == d / "v2.yaml"
    assert latest_prompt(d) == path
    assert load_prompt(path).system_prompt == "Line one.\nLine two ¿ü? 日本語\n"
    assert "|" in path.read_text(encoding="utf-8")


def test_create_prompt_never_overwrites(tmp_path):
    d = _prompts(tmp_path)
    before = (d / "v1.yaml").read_bytes()
    with pytest.raises(ValueError):
        _new_prompt(d, version="v1")
    (d / "v3.yaml").write_text("placeholder", encoding="utf-8")
    with pytest.raises(ValueError):
        _new_prompt(d, version="v3")
    assert (d / "v1.yaml").read_bytes() == before
    assert (d / "v3.yaml").read_text(encoding="utf-8") == "placeholder"


@pytest.mark.parametrize("bad", ["../evil", "v2/../../x", "a b", "..", ""])
def test_create_prompt_rejects_unsafe_version(tmp_path, bad):
    d = _prompts(tmp_path)
    with pytest.raises(ValueError):
        _new_prompt(d, version=bad)
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["v1.yaml"]


def test_create_prompt_validates_contract(tmp_path):
    d = _prompts(tmp_path)
    bad = [{"email": "hi", "output": {"category": "sales", "summary": "x"}}]
    with pytest.raises(ValueError):
        _new_prompt(d, few_shot_examples=bad)
    assert not (d / "v2.yaml").exists()
