"""The script that regenerates the bundled DEIS snapshot (no network: uses the current one)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from urgencias_core.data.fixtures import deis_snapshot_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def snap():
    spec = importlib.util.spec_from_file_location(
        "construir_snapshot", ROOT / "scripts/construir_snapshot.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def current() -> pd.DataFrame:
    return pd.read_parquet(deis_snapshot_path())


def test_prepare_keeps_the_schema_and_both_hospitals(snap, current) -> None:
    raw = current.copy()
    raw["facility_code"] = raw["facility_code"].str.replace("24-", "124", regex=False)
    out = snap.prepare(raw)
    assert list(out.columns) == list(current.columns)
    assert set(out["facility_code"]) == {"24-105", "24-115"}
    assert len(out) == len(current)
    assert out["year"].dtype == current["year"].dtype


def test_check_refuses_snapshots_that_lose_data(snap, current) -> None:
    snap.check(current, current)  # same data is fine
    with pytest.raises(snap.SnapshotError, match="hospitales"):
        snap.check(current[current["facility_code"] == "24-105"], current)
    with pytest.raises(snap.SnapshotError, match="antes que el actual"):
        snap.check(current[current["date"] < current["date"].max()], current)
    thinner = current.drop(current[current["year"] == 2023].index[::2])
    with pytest.raises(snap.SnapshotError, match="2023"):
        snap.check(thinner, current)


def test_readme_lists_the_coverage(snap, current) -> None:
    text = snap.readme(current, date(2026, 11, 1))
    assert "01-11-2026" in text and "| 2025 |" in text
    assert "Año parcial, hasta el" in text and "deis_demo_snapshot.parquet" in text
    assert "| 2025 | 28.749 | Año completo |" in text


def test_same_data_detects_no_change(snap, current) -> None:
    prepared = snap.prepare(current)
    assert snap.same_data(prepared, snap.prepare(current.sample(frac=1, random_state=0)))
    changed = prepared.copy()
    changed.loc[0, "count"] += 1
    assert not snap.same_data(prepared, changed)
