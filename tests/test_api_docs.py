"""The developer reference page: its examples run and its signatures match the code."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "construir_api", ROOT / "scripts/construir_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def test_every_example_runs(tmp_path, monkeypatch) -> None:
    api = _builder()
    monkeypatch.chdir(tmp_path)  # examples write their files under ./salida
    outputs = api.run_examples()
    runnable = [e.id for s in api.SECTIONS for e in s.entries if e.example and e.run]
    assert set(outputs) == set(runnable)
    assert all(outputs[i].strip() for i in runnable)


def test_published_page_matches_the_code() -> None:
    api = _builder()
    published = json.loads((ROOT / "sitio/src/data/api.json").read_text(encoding="utf-8"))
    entries = {e["id"]: e for s in published["sections"] for e in s["entries"]}
    for section in api.SECTIONS:
        for e in section.entries:
            assert e.id in entries, f"{e.id}: run scripts/construir_api.py"
            assert entries[e.id]["signature"] == api.signature(
                e.target
            ), f"{e.target} changed: run `uv run python scripts/construir_api.py`"
            assert entries[e.id]["example"] == e.example.strip()
            assert entries[e.id]["source"] == api.source(e.target)


@pytest.mark.parametrize("target", ["urgencias_core:nope", "urgencias_core.nope:x"])
def test_bad_targets_fail_loudly(target: str) -> None:
    with pytest.raises((AttributeError, ModuleNotFoundError)):
        _builder().signature(target)
