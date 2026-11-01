"""Regenerate the DEIS snapshot bundled with the package (``urg-forecast demo --offline``).

The snapshot holds every DEIS row (all causes and age groups) of the two demo hospitals,
so the package, its tests, the examples and the developer page work without network.
Run by ``.github/workflows/snapshot.yml`` before each release; it can also run locally
with the DEIS files in the cache:

    uv run python scripts/construir_snapshot.py                # writes the package fixture
    uv run python scripts/construir_snapshot.py --cache CARPETA

It refuses to write a snapshot that would lose data: both hospitals must be present, it
must not end earlier than the current one, and every year must keep at least 90% of its
rows. The README next to the parquet is rewritten with the coverage table.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "src" / "urgencias_core" / "data" / "_fixtures"
PARQUET = FIXTURES / "deis_demo_snapshot.parquet"
README = FIXTURES / "deis_demo_snapshot.README.md"
HOSPITALS = {"24-105": "Hospital de Puerto Montt", "24-115": "Hospital de Frutillar"}
START_YEAR = 2021
MIN_ROWS_KEPT = 0.9  # per year, against the current snapshot


class SnapshotError(RuntimeError):
    """The new snapshot would lose data; nothing is written."""


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical codes, the snapshot's column order and types, sorted."""
    from urgencias_core.data.mirror import canonical_code

    cols = [
        "year",
        "date",
        "facility_code",
        "facility_name",
        "cause_id",
        "cause_group",
        "age_group",
        "count",
    ]
    out = df[cols].copy()
    out["facility_code"] = out["facility_code"].astype(str).map(canonical_code)
    out = out[out["facility_code"].isin(HOSPITALS)]
    out["date"] = pd.to_datetime(out["date"])
    out["year"] = out["year"].astype("int16")
    out["count"] = out["count"].astype("int64")
    return out.sort_values(["facility_code", "date", "cause_id"]).reset_index(drop=True)


def check(new: pd.DataFrame, old: pd.DataFrame | None) -> None:
    """Raise :class:`SnapshotError` if ``new`` would lose data against ``old``."""
    missing = set(HOSPITALS) - set(new["facility_code"])
    if missing:
        raise SnapshotError(f"faltan hospitales: {sorted(missing)}")
    if old is None or old.empty:
        return
    if new["date"].max() < old["date"].max():
        raise SnapshotError(
            f"termina el {new['date'].max():%Y-%m-%d}, antes que el actual "
            f"({old['date'].max():%Y-%m-%d})"
        )
    before = old.groupby("year").size()
    after = new.groupby("year").size().reindex(before.index, fill_value=0)
    short = after[after < MIN_ROWS_KEPT * before]
    if not short.empty:
        detail = ", ".join(f"{y}: {after[y]} de {before[y]}" for y in short.index)
        raise SnapshotError(f"años con menos filas que el snapshot actual: {detail}")


def same_data(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """True when both snapshots hold exactly the same rows."""
    if a.shape != b.shape:
        return False
    hash_a = pd.util.hash_pandas_object(a.astype(str), index=False)
    hash_b = pd.util.hash_pandas_object(b.astype(str), index=False)
    return bool((hash_a.to_numpy() == hash_b.to_numpy()).all())


def readme(df: pd.DataFrame, generated: date) -> str:
    """The README next to the parquet, with the coverage table of ``df``."""
    rows = []
    last = df["date"].max()
    for year, g in df.groupby("year"):
        end = g["date"].max()
        complete = end.month == 12 and end.day == 31
        note = "Año completo" if complete else f"Año parcial, hasta el {end:%d-%m-%Y}"
        n = f"{len(g):,}".replace(",", ".")
        rows.append(f"| {year} | {n} | {note} |")
    hospitals = "\n".join(f"- `{c}`: {n}." for c, n in HOSPITALS.items())
    total = f"{len(df):,}".replace(",", ".")
    return f"""# deis_demo_snapshot.parquet

Lo usan `urg-forecast demo --offline`, `--offline` en los demás comandos, el respaldo
cuando el DEIS no responde, los tests, los ejemplos y la página para desarrolladores. Los
comandos en línea leen siempre los datos más recientes.

Snapshot de los datos abiertos *Atenciones de Urgencia* del DEIS MINSAL, con todas las
causas y grupos de edad, filtrado a los dos hospitales de demostración de la región de
Los Lagos (Servicio de Salud Reloncaví):

{hospitals}

## Generación

- Generado el **{generated:%d-%m-%Y}** con `scripts/construir_snapshot.py`, desde los
  archivos anuales del DEIS. Datos hasta el **{last:%d-%m-%Y}**.
- Se regenera antes de cada versión con el workflow `snapshot` (Actions → snapshot → Run
  workflow), que abre una rama con el cambio para revisarlo en un PR.
- Origen: `https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia/AtencionesUrgencia{{AÑO}}.zip`
  (CSV separado por punto y coma, codificación latin-1).

## Cobertura

| Año | Filas | Nota |
|------|------|------|
{chr(10).join(rows)}

Total: {total} filas, una por (hospital, fecha, causa, grupo de edad).

## Años no incluidos

- **2017–2019:** el DEIS los publicó como `.xlsx` + `.mdb` dentro del ZIP anual y el
  lector de `deis.py` los omite. Ver `docs/roadmap.md`.
- **2020:** el archivo trae una fila de cabecera corrupta. Se excluye por la pandemia.

## Atribución

DEIS, Departamento de Estadísticas e Información de Salud, Ministerio de Salud de Chile,
<https://deis.minsal.cl/>. Datos abiertos bajo el marco de datos abiertos de Chile. Este
repositorio redistribuye un subconjunto filtrado con fines de enseñanza y
reproducibilidad; para cualquier uso de investigación u operacional del dataset completo,
descárgalo directamente desde la fuente.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default="data/external/deis_cache", help="DEIS downloads")
    ap.add_argument("--desde", type=int, default=START_YEAR)
    args = ap.parse_args(argv)

    from urgencias_core.data.deis import fetch_demo_hospitals

    old = pd.read_parquet(PARQUET) if PARQUET.exists() else None
    new = prepare(fetch_demo_hospitals(start_year=args.desde, cache_dir=args.cache))
    if old is not None and same_data(new, prepare(old)):
        print("snapshot: sin datos nuevos; no se modifica")
        return 0
    try:
        check(new, old)
    except SnapshotError as exc:
        print(f"snapshot: no se actualiza, {exc}", file=sys.stderr)
        return 1
    new.to_parquet(PARQUET, index=False, compression="zstd")
    README.write_text(readme(new, date.today()), encoding="utf-8")
    prev = f"{old['date'].max():%Y-%m-%d}" if old is not None else "–"
    print(f"snapshot: {len(new)} filas, datos hasta {new['date'].max():%Y-%m-%d} (antes {prev})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
