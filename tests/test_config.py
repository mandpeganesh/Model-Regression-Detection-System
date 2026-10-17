from pathlib import Path

import pytest
from pydantic import ValidationError

from regress.config import ClassificationResult, Settings, latest_prompt, load_prompt


def write_prompt(path: Path, version: str, created_at: str, extra: str = "") -> Path:
    path.write_text(
        f"version: {version}\ncreated_at: {created_at}\nmodel: gpt-4o-mini\n"
        f"system_prompt: SYS\n{extra}",
        encoding="utf-8",
    )
    return path


def test_load_prompt_v1():
    cfg = load_prompt(Path("prompts/v1.yaml"))
    assert cfg.version == "v1" and cfg.model == "gpt-4o-mini" and cfg.few_shot_examples == []


def test_prompt_rejects_unknown_field(tmp_path):
    p = write_prompt(tmp_path / "p.yaml", "v9", "2026-01-01T00:00:00Z", "temprature: 0\n")
    with pytest.raises(ValidationError):
        load_prompt(p)


def test_classification_rejects_bad_category():
    with pytest.raises(ValidationError):
        ClassificationResult(category="sales", summary="x")


def test_latest_prompt_picks_newest_created_at(tmp_path):
    write_prompt(tmp_path / "v1.yaml", "v1", "2026-01-01T00:00:00Z")
    v2 = write_prompt(tmp_path / "v2.yaml", "v2", "2026-02-01T00:00:00Z")
    assert latest_prompt(tmp_path) == v2


def test_latest_prompt_tie_raises(tmp_path):
    write_prompt(tmp_path / "a.yaml", "a", "2026-01-01T00:00:00Z")
    write_prompt(tmp_path / "b.yaml", "b", "2026-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        latest_prompt(tmp_path)


def test_latest_prompt_empty_dir_raises(tmp_path):
    with pytest.raises(ValueError):
        latest_prompt(tmp_path)


def test_settings_defaults():
    s = Settings.from_env({})
    assert (s.warn_threshold, s.critical_threshold, s.drift_threshold, s.drift_window) == (0.03, 0.08, 0.85, 7)
    assert (s.relevance_pass_min, s.max_concurrency, s.judge_model) == (3, 8, "gpt-4o-mini")
    assert s.slack_webhook_url is None and s.report_url is None


def test_settings_from_env_overrides():
    s = Settings.from_env({"WARN_THRESHOLD": "0.05", "CRITICAL_THRESHOLD": "0.1"})
    assert (s.warn_threshold, s.critical_threshold) == (0.05, 0.1)


def test_settings_invalid_raises_naming_var():
    with pytest.raises(ValueError, match="WARN_THRESHOLD"):
        Settings.from_env({"WARN_THRESHOLD": "abc"})


def test_settings_warn_must_be_below_critical():
    with pytest.raises(ValueError):
        Settings.from_env({"WARN_THRESHOLD": "0.1", "CRITICAL_THRESHOLD": "0.05"})


def test_settings_empty_string_is_unset():
    assert Settings.from_env({"SLACK_WEBHOOK_URL": ""}).slack_webhook_url is None
