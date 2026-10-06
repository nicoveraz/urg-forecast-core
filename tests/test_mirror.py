"""Mirror build/read round trip on synthetic DEIS-format ZIPs (no network)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from urgencias_core.data import mirror as mirror_mod
from urgencias_core.data.deis import YearFetchResult
from urgencias_core.data.fixtures import deis_snapshot_path
from urgencias_core.pipeline import load_deis, run_forecast, weekly_series

NAMES = {"24-105": "Hospital de Puerto Montt", "24-115": "Hospital de Frutillar"}


def _raw_zip(path: Path, year: int, snap: pd.DataFrame) -> None:
    """Write a DEIS-like yearly ZIP (raw column names, ; separated, latin-1)."""
    sub = snap[snap["year"] == year]
    raw = pd.DataFrame(
        {
            # Old and new code spellings mixed, like real DEIS files over the years.
            "IdEstablecimiento": sub["facility_code"].map(
                lambda c: ("1" + c.replace("-", "")) if year % 2 else c
            ),
            "NEstablecimiento": sub["facility_code"].map(NAMES),
            "IdCausa": sub["cause_id"],
            "GlosaCausa": sub["cause_group"],
            "Total": sub["count"],
            "fecha": pd.to_datetime(sub["date"]).dt.strftime("%d/%m/%Y"),
            "GLOSATIPOESTABLECIMIENTO": "Hospital",
            "NombreRegion": "De Los Lagos",
            "NombreComuna": sub["facility_code"].map(
                {"24-105": "Puerto Montt", "24-115": "Frutillar"}
            ),
            "NombreDependencia": "Servicio de Salud Reloncaví",
        }
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            f"AtencionesUrgencia{year}.csv", raw.to_csv(sep=";", index=False).encode("latin-1")
        )


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mirror")
    snap = pd.read_parquet(deis_snapshot_path())
    zips = {}
    for year in sorted(snap["year"].unique()):
        p = tmp / f"AtencionesUrgencia{year}.zip"
        _raw_zip(p, int(year), snap)
        zips[int(year)] = p

    def fake_download(year, cache_dir=None, client=None, **kw):
        if year in zips:
            return YearFetchResult(year=year, path=zips[year], status="cached")
        return YearFetchResult(year=year, path=None, status="not_available")

    mp = pytest.MonkeyPatch()
    mp.setattr(mirror_mod, "download_year", fake_download)
    out = tmp / "salida"
    meta = mirror_mod.build_mirror(out, start_year=2021, end_year=2026)
    mp.undo()
    # Pre-seed a cache as if the files had been downloaded from the repo.
    cache = tmp / "cache"
    (cache / "espejo").mkdir(parents=True)
    for f in ("diario.parquet", "establecimientos.csv", "meta.json"):
        (cache / "espejo" / f).write_bytes((out / f).read_bytes())
    return {"out": out, "meta": meta, "cache": cache, "snap": snap}


def test_canonical_code() -> None:
    assert mirror_mod.canonical_code(" 124105 ") == "24-105"
    assert mirror_mod.canonical_code("24-105") == "24-105"


def test_mirror_files_and_metadata(built) -> None:
    fac = pd.read_csv(built["out"] / "establecimientos.csv", dtype=str)
    assert sorted(fac["codigo"]) == ["24-105", "24-115"]  # both spellings merged
    row = fac.set_index("codigo").loc["24-115"]
    assert row["nombre"] == "Hospital de Frutillar"
    assert row["tipo"] == "Hospital" and row["comuna"] == "Frutillar"
    assert built["meta"]["establecimientos"] == 2
    daily = pd.read_parquet(built["out"] / "diario.parquet")
    assert set(daily.columns) == {"facility_code", "date", "count"}
    assert not daily.duplicated(["facility_code", "date"]).any()


def test_mirror_matches_direct_totals(built) -> None:
    snap = built["snap"]
    direct = weekly_series(snap.assign(date=pd.to_datetime(snap["date"])), "24-105")
    rows = mirror_mod.mirror_rows({"124105"}, cache_dir=built["cache"])
    via_mirror = weekly_series(rows, "24-105")
    pd.testing.assert_frame_equal(
        direct.reset_index(drop=True), via_mirror.reset_index(drop=True), check_dtype=False
    )


def test_load_deis_from_repo_source(built) -> None:
    df = load_deis(["24-115"], cache_dir=built["cache"], source="repo")
    assert "copia semanal" in df.attrs["source"]
    assert not df["year"].isin([2020, 2021]).any()
    res = run_forecast(weekly_series(df, "24-115"), 4, origins=1)
    assert len(res.forecast) == 4


def test_unreachable_mirror_without_cache_errors(tmp_path, monkeypatch) -> None:
    import httpx

    from urgencias_core.pipeline import NoDataError

    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(mirror_mod.httpx, "get", boom)
    with pytest.raises(NoDataError, match="--fuente deis"):
        load_deis(["24-105"], cache_dir=tmp_path, source="repo")
    df = load_deis(["24-105"], cache_dir=tmp_path, source="repo", fallback_to_snapshot=True)
    assert "snapshot" in df.attrs["source"]


def test_buscar_uses_mirror(built, capsys) -> None:
    from urgencias_core import cli

    assert cli.main(["buscar", "frutillar", "--cache", str(built["cache"])]) == 0
    out = capsys.readouterr().out
    assert "24-115" in out and "Hospital" in out and "Frutillar" in out
