"""Weekly series of ED attendances for one establishment, from any DEIS source.

1. :func:`load_deis` — DEIS rows for one or more establishments: the repository's weekly
   copy (default), the full yearly DEIS files, or the snapshot bundled with the package.
2. :func:`weekly_series` — daily totals to complete weeks (W-MON: the 7 days ending on
   that Monday), trimming partial weeks at the edges.

Every other module (analysis, models, evaluation) starts from the ``timestamp, count``
frame that :func:`weekly_series` returns.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from urgencias_core.data.deis import (
    DEFAULT_CACHE_DIR,
    deis_reachable,
    facility_code_variants,
    fetch,
)
from urgencias_core.data.fixtures import deis_snapshot_path

COVID_EXCLUDE_YEARS = frozenset({2020, 2021})
TOTAL_CAUSE_GLOSA = "SECCIÓN 1. TOTAL ATENCIONES DE URGENCIA"
DEMO_FACILITIES = ("24-105", "24-115")  # Hospital de Puerto Montt, Hospital de Frutillar
GRAIN = "W-MON"
SEASON_WEEKS = 52

logger = logging.getLogger(__name__)


class NoDataError(RuntimeError):
    """Raised when the requested establishments have no usable DEIS rows."""


SOURCE_LIVE = "DEIS MINSAL (descarga actualizada)"
SOURCE_MIRROR = "DEIS MINSAL, copia semanal del repositorio"
SOURCE_SNAPSHOT = "snapshot DEIS incluido en el paquete"


def _read_snapshot(wanted: set[str]) -> pd.DataFrame:
    df = pd.read_parquet(deis_snapshot_path())
    df = df[df["facility_code"].astype(str).isin(wanted)]
    if df.empty:
        raise NoDataError(
            "El snapshot offline solo incluye los hospitales de demostración "
            f"({', '.join(DEMO_FACILITIES)}). Quita --offline para descargar desde DEIS."
        )
    return df


def load_deis(
    codes: list[str],
    start_year: int = 2022,
    offline: bool = False,
    fallback_to_snapshot: bool = False,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    source: str = "repo",
) -> pd.DataFrame:
    """DEIS rows for ``codes`` (any DEIS spelling), COVID years excluded.

    - ``offline=True`` reads the snapshot bundled with the package (demo
      hospitals only).
    - ``source="repo"`` (default) reads the weekly mirror of daily totals that
      the project publishes on its ``datos`` branch, so users do not download
      the full DEIS files (see :mod:`urgencias_core.data.mirror`).
    - ``source="deis"`` downloads the yearly files from DEIS into ``cache_dir``
      (the current year is refreshed weekly); needed for causes or age groups.

    With ``fallback_to_snapshot=True``, falls back to the snapshot when the
    source is unreachable or returns nothing.

    The data source used is recorded in ``df.attrs["source"]``.
    """
    wanted = set().union(*(facility_code_variants(c) for c in codes))
    if source not in ("repo", "deis"):
        raise ValueError(f"fuente desconocida: {source!r} (usa 'repo' o 'deis')")
    label = SOURCE_SNAPSHOT
    if offline:
        df = _read_snapshot(wanted)
    elif source == "repo":
        from urgencias_core.data.mirror import MirrorUnavailable, mirror_meta, mirror_rows

        try:
            df = mirror_rows(wanted, cache_dir=cache_dir)
            df = df[df["year"].astype(int) >= start_year]
            label = f"{SOURCE_MIRROR} (al {mirror_meta(cache_dir=cache_dir)['ultima_fecha']})"
        except MirrorUnavailable as exc:
            if not fallback_to_snapshot:
                raise NoDataError(
                    f"No se pudo leer la copia de datos del repositorio ({exc}). "
                    "Revisa tu conexión o usa --fuente deis."
                ) from exc
            logger.warning("La copia del repositorio no responde; se usa el snapshot incluido.")
            df = pd.DataFrame()
        if df.empty and fallback_to_snapshot:
            df, label = _read_snapshot(wanted), SOURCE_SNAPSHOT
        elif df.empty:
            raise NoDataError(
                f"No hay datos para {', '.join(codes)} desde {start_year}. "
                "Revisa el código con 'urg-forecast buscar'."
            )
    elif fallback_to_snapshot and not deis_reachable():
        logger.warning("DEIS no responde; se usa el snapshot incluido.")
        df = _read_snapshot(wanted)
    else:
        df = fetch(start_year=start_year, cache_dir=cache_dir, facility_filter=wanted)
        label = SOURCE_LIVE
        if df.empty and fallback_to_snapshot:
            logger.warning("DEIS no entregó datos; se usa el snapshot incluido.")
            df, label = _read_snapshot(wanted), SOURCE_SNAPSHOT
        elif df.empty:
            raise NoDataError(
                f"No hay datos DEIS para {', '.join(codes)} desde {start_year}. "
                "Revisa el código con 'urg-forecast buscar' o tu conexión."
            )
    df = df[~df["year"].astype(int).isin(COVID_EXCLUDE_YEARS)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df.attrs["source"] = label
    return df


def daily_totals(df: pd.DataFrame, codes: set[str]) -> pd.DataFrame:
    """Daily total attendances for one establishment (``timestamp``, ``count``)."""
    sub = df[df["facility_code"].astype(str).isin(codes)]
    totals = sub[sub["cause_group"] == TOTAL_CAUSE_GLOSA]
    if totals.empty:
        totals = sub[
            sub["cause_group"].str.upper().str.contains("SECCI.?N 1", regex=True, na=False)
        ]
    daily = (
        totals.groupby("date")["count"]
        .sum()
        .reset_index()
        .rename(columns={"date": "timestamp"})
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    daily["timestamp"] = pd.to_datetime(daily["timestamp"])
    return daily


def to_weekly(daily: pd.DataFrame, min_days: int = 7) -> pd.DataFrame:
    """Aggregate daily counts to weekly totals (weeks ending Monday, W-MON).

    Partial weeks at the series edges — fewer than ``min_days`` days present —
    are trimmed. This matters most at the trailing edge: DEIS is updated in
    near-real-time, so the latest week(s) can be under-counted by reporting lag
    or a missing day and would otherwise appear as a spurious drop that
    contaminates the backtest. Internal weeks are kept as-is to preserve regular
    weekly spacing.
    """
    agg = daily.set_index("timestamp")["count"].resample(GRAIN).agg(["sum", "count"])
    complete = agg["count"] >= min_days
    if not complete.any():
        return pd.DataFrame(
            {"timestamp": pd.to_datetime([]), "count": pd.Series([], dtype="int64")}
        )
    agg = agg.loc[complete.idxmax() : complete[::-1].idxmax()]
    return agg["sum"].rename("count").reset_index()


def weekly_series(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Complete weekly totals for one establishment."""
    return to_weekly(daily_totals(df, facility_code_variants(code)))


def facility_name(df: pd.DataFrame, code: str) -> str:
    """Most recent published name (DEIS names change over the years)."""
    rows = df[df["facility_code"].astype(str).isin(facility_code_variants(code))]
    if rows.empty:
        return code
    return str(rows.sort_values("date")["facility_name"].iloc[-1])


__all__ = [
    "COVID_EXCLUDE_YEARS",
    "DEMO_FACILITIES",
    "GRAIN",
    "NoDataError",
    "SEASON_WEEKS",
    "SOURCE_LIVE",
    "SOURCE_MIRROR",
    "SOURCE_SNAPSHOT",
    "TOTAL_CAUSE_GLOSA",
    "daily_totals",
    "facility_name",
    "load_deis",
    "to_weekly",
    "weekly_series",
]
