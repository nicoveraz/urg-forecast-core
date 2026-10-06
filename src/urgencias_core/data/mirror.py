"""Weekly mirror of DEIS daily totals, published on the repository's ``datos`` branch.

Why: every user downloading the yearly DEIS ZIPs (hundreds of MB each) puts
needless load on the DEIS server. A scheduled workflow downloads them once a
week, keeps only the daily *total* attendances per establishment, and publishes
two small files that the command reads by default:

- ``diario.parquet``: one row per (establishment, day): ``facility_code``,
  ``date``, ``count``.
- ``establecimientos.csv``: one row per establishment with its latest name,
  type (Hospital, SAPU, SAR, SUR…), region, commune and health service, plus
  the first and last date with data.
- ``meta.json``: when it was built and from which DEIS years.

The full DEIS files (by cause and age group) remain available through
``urgencias_core.data.deis`` and ``--fuente deis``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from urgencias_core.data.deis import DEFAULT_CACHE_DIR, _read_csv_chunks, download_year

logger = logging.getLogger(__name__)

MIRROR_BASE_URL = "https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/datos/"
DAILY_FILE = "diario.parquet"
FACILITIES_FILE = "establecimientos.csv"
META_FILE = "meta.json"
MIRROR_MAX_AGE_HOURS = 12
TOTAL_PATTERN = re.compile(r"SECCI.?N 1", re.IGNORECASE)

# Raw DEIS column -> mirror metadata column (only present in recent years).
_META_COLUMNS = {
    "NEstablecimiento": "nombre",
    "GLOSATIPOESTABLECIMIENTO": "tipo",
    "NombreRegion": "region",
    "NombreComuna": "comuna",
    "NombreDependencia": "servicio",
}
_NEW_CODE = re.compile(r"^1(\d{2})(\d{3})$")


def canonical_code(code: str) -> str:
    """One spelling per establishment: ``SS-NNN`` (DEIS also used ``1SSNNN``)."""
    code = str(code).strip()
    if m := _NEW_CODE.match(code):
        return f"{m.group(1)}-{m.group(2)}"
    return code


# ---------------------------------------------------------------------------
# Build (run by the scheduled workflow)
# ---------------------------------------------------------------------------


def _year_totals(path: Path, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily totals and per-row metadata for one DEIS yearly ZIP."""
    totals: list[pd.DataFrame] = []
    meta: list[pd.DataFrame] = []
    for _, chunk in _read_csv_chunks(path):
        cols = {c.lower(): c for c in chunk.columns}
        code_col = cols.get("idestablecimiento")
        cause_col = cols.get("glosacausa")
        count_col = cols.get("total")
        date_col = cols.get("fecha")
        if not all((code_col, cause_col, count_col, date_col)):
            raise ValueError(f"DEIS {year}: unexpected columns {sorted(chunk.columns)}")
        rows = chunk[chunk[cause_col].astype(str).str.contains(TOTAL_PATTERN, na=False)]
        if rows.empty:
            continue
        df = pd.DataFrame(
            {
                "facility_code": rows[code_col].map(canonical_code),
                "date": pd.to_datetime(rows[date_col], dayfirst=True, errors="coerce"),
                "count": pd.to_numeric(rows[count_col], errors="coerce").fillna(0),
            },
            index=rows.index,
        ).dropna(subset=["date"])
        totals.append(df.groupby(["facility_code", "date"], as_index=False)["count"].sum())
        m = pd.DataFrame({"facility_code": df["facility_code"], "date": df["date"]})
        for raw, name in _META_COLUMNS.items():
            col = cols.get(raw.lower())
            m[name] = rows.loc[df.index, col].astype(str).str.strip().to_numpy() if col else None
        meta.append(m.sort_values("date").groupby("facility_code").tail(1))
    if not totals:
        return pd.DataFrame(columns=["facility_code", "date", "count"]), pd.DataFrame()
    daily = pd.concat(totals).groupby(["facility_code", "date"], as_index=False)["count"].sum()
    return daily, pd.concat(meta)


def build_mirror(
    out_dir: Path | str,
    start_year: int = 2021,
    end_year: int | None = None,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> dict:
    """Download DEIS years and write the mirror files to ``out_dir``. Returns meta."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    end = end_year or datetime.now().year
    daily_parts, meta_parts, years = [], [], []
    with httpx.Client(timeout=180.0) as client:
        for year in range(start_year, end + 1):
            result = download_year(year, cache_dir=cache_dir, client=client)
            if result.path is None:
                logger.warning("DEIS %d: %s; se omite.", year, result.status)
                continue
            try:
                daily, meta = _year_totals(result.path, year)
            except (ValueError, KeyError) as exc:
                logger.warning("DEIS %d: no se pudo leer (%s); se omite.", year, str(exc)[:80])
                continue
            logger.info("DEIS %d: %s filas diarias", year, f"{len(daily):,}")
            daily_parts.append(daily)
            meta_parts.append(meta)
            years.append(year)

    daily = (
        pd.concat(daily_parts)
        .groupby(["facility_code", "date"], as_index=False)["count"]
        .sum()
        .sort_values(["facility_code", "date"])
        .reset_index(drop=True)
    )
    daily["count"] = daily["count"].astype("int32")
    daily["facility_code"] = daily["facility_code"].astype("category")
    daily.to_parquet(out / DAILY_FILE, index=False, compression="zstd")

    latest = pd.concat(meta_parts).sort_values("date").groupby("facility_code").tail(1)
    span = daily.groupby("facility_code", observed=True)["date"].agg(["min", "max", "count"])
    fac = (
        latest.drop(columns="date")
        .set_index("facility_code")
        .join(span.rename(columns={"min": "desde", "max": "hasta", "count": "dias"}), how="right")
        .reset_index()
        .rename(columns={"facility_code": "codigo"})
        .sort_values(["region", "nombre"], na_position="last")
    )
    fac["desde"] = fac["desde"].dt.date
    fac["hasta"] = fac["hasta"].dt.date
    fac.to_csv(out / FACILITIES_FILE, index=False)

    meta = {
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "anios_deis": years,
        "ultima_fecha": str(daily["date"].max().date()),
        "establecimientos": int(len(fac)),
        "filas": int(len(daily)),
        "fuente": "DEIS MINSAL, Atenciones de Urgencia (datos abiertos)",
    }
    (out / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return meta


# ---------------------------------------------------------------------------
# Read (used by the command)
# ---------------------------------------------------------------------------


class MirrorUnavailable(RuntimeError):
    """The mirror could not be downloaded and there is no cached copy."""


def _fetch(name: str, cache_dir: Path, base_url: str, max_age_hours: float) -> Path:
    dest = cache_dir / "espejo" / name
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < max_age_hours * 3600
    if fresh:
        return dest
    try:
        resp = httpx.get(base_url + name, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        if dest.exists():
            logger.warning("No se pudo actualizar %s (%s); se usa la copia local.", name, exc)
            return dest
        raise MirrorUnavailable(f"no se pudo descargar {base_url + name}: {exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)
    return dest


def mirror_meta(
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    base_url: str = MIRROR_BASE_URL,
    max_age_hours: float = MIRROR_MAX_AGE_HOURS,
) -> dict:
    return json.loads(_fetch(META_FILE, Path(cache_dir), base_url, max_age_hours).read_text())


def mirror_facilities(
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    base_url: str = MIRROR_BASE_URL,
    max_age_hours: float = MIRROR_MAX_AGE_HOURS,
) -> pd.DataFrame:
    """Establishments in the mirror: codigo, nombre, tipo, region, comuna, servicio…"""
    path = _fetch(FACILITIES_FILE, Path(cache_dir), base_url, max_age_hours)
    return pd.read_csv(path, dtype=str).fillna("")


def mirror_rows(
    codes: set[str],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    base_url: str = MIRROR_BASE_URL,
    max_age_hours: float = MIRROR_MAX_AGE_HOURS,
) -> pd.DataFrame:
    """Daily totals for ``codes`` in the canonical DEIS row schema used by the pipeline."""
    from urgencias_core.pipeline import TOTAL_CAUSE_GLOSA

    cache = Path(cache_dir)
    daily = pd.read_parquet(_fetch(DAILY_FILE, cache, base_url, max_age_hours))
    wanted = {canonical_code(c) for c in codes}
    daily = daily[daily["facility_code"].astype(str).isin(wanted)].copy()
    names = mirror_facilities(cache, base_url, max_age_hours).set_index("codigo")["nombre"]
    daily["facility_code"] = daily["facility_code"].astype(str)
    daily["date"] = pd.to_datetime(daily["date"])
    return pd.DataFrame(
        {
            "year": daily["date"].dt.year.astype("int16"),
            "date": daily["date"],
            "facility_code": daily["facility_code"],
            "facility_name": daily["facility_code"].map(names).fillna(""),
            "cause_id": "1",
            "cause_group": TOTAL_CAUSE_GLOSA,
            "age_group": "",
            "count": daily["count"].astype("int64"),
        }
    ).reset_index(drop=True)


__all__ = [
    "MIRROR_BASE_URL",
    "MirrorUnavailable",
    "build_mirror",
    "canonical_code",
    "mirror_facilities",
    "mirror_meta",
    "mirror_rows",
]
