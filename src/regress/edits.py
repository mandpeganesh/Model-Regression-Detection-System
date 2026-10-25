"""Guards for editing ground truth (golden cases) and prompt files. Pure, no LLM calls.

Every function raises ValueError on a rule break and writes nothing.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from regress.config import PromptConfig, find_prompt
from regress.dataset import GoldenCase, GoldenDataset

_VERSION_RE = re.compile(r"[A-Za-z0-9._-]+")


def check_version(current: str, new: str, used_versions: set[str]) -> None:
    if current in used_versions and new == current:
        raise ValueError(f"dataset version {current!r} has already been used in a run; bump it")
    if new != current and new in used_versions:
        raise ValueError(f"dataset version {new!r} was already used in a run; pick a new one")


def add_case(
    ds: GoldenDataset, case: GoldenCase, new_version: str, used_versions: set[str], used_ids: set[str]
) -> GoldenDataset:
    if case.id in {c.id for c in ds.cases} or case.id in used_ids:
        raise ValueError(f"case id {case.id!r} already exists or was used in a past run; ids are never reused")
    check_version(ds.version, new_version, used_versions)
    return GoldenDataset.model_validate({"version": new_version, "cases": [*ds.cases, case]})


def edit_case(
    ds: GoldenDataset, case_id: str, case: GoldenCase, new_version: str, used_versions: set[str]
) -> GoldenDataset:
    if case.id != case_id:
        raise ValueError(f"case ids never change (got {case.id!r} for {case_id!r})")
    if case_id not in {c.id for c in ds.cases}:
        raise KeyError(case_id)
    check_version(ds.version, new_version, used_versions)
    cases = [case if c.id == case_id else c for c in ds.cases]
    return GoldenDataset.model_validate({"version": new_version, "cases": cases})


def save_dataset(path: Path, ds: GoldenDataset) -> None:
    text = json.dumps(ds.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")


class _BlockDumper(yaml.SafeDumper):
    pass


def _str_repr(dumper: yaml.SafeDumper, data: str):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)


_BlockDumper.add_representer(str, _str_repr)


def create_prompt(
    prompts_dir: Path, *, version: str, model: str, system_prompt: str, few_shot_examples: list[dict], now: datetime
) -> Path:
    if not _VERSION_RE.fullmatch(version) or version in (".", ".."):
        raise ValueError(f"invalid prompt version {version!r}: use letters, digits, '.', '_' or '-'")
    prompts_dir = Path(prompts_dir)
    if find_prompt(prompts_dir, version):
        raise ValueError(f"prompt version {version!r} already exists; prompts are immutable")
    path = prompts_dir / f"{version}.yaml"
    if path.exists():
        raise ValueError(f"{path.name} already exists; prompts are never overwritten")
    created_at = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    config = PromptConfig.model_validate(
        {
            "version": version,
            "created_at": created_at,
            "model": model,
            "system_prompt": system_prompt,
            "few_shot_examples": few_shot_examples,
        }
    )
    text = yaml.dump(config.model_dump(), Dumper=_BlockDumper, allow_unicode=True, sort_keys=False)
    with open(path, "x", encoding="utf-8") as f:  # "x": never overwrite
        f.write(text)
    return path
