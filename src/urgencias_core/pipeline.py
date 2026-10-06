"""Weekly ED attendance forecasting on DEIS MINSAL data.

The pieces the ``urg-forecast`` command is built from, usable on their own:

1. :func:`load_deis` — DEIS rows for one or more establishments (live or the
   bundled offline snapshot).
2. :func:`weekly_series` — daily totals → complete weeks (W-MON), trimming
   partial weeks at the edges.
3. :func:`run_forecast` — backtest a set of models on the last weeks, pick the
   best by P80 quantile loss, refit it on all history and forecast forward.

Everything returns plain DataFrames; plotting and printing live in
:mod:`urgencias_core.report`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from urgencias_core.data.deis import deis_reachable, facility_code_variants, fetch
from urgencias_core.data.fixtures import deis_snapshot_path
from urgencias_core.eval.baselines import SeasonalNaiveBaseline, auto_arima, auto_ets
from urgencias_core.eval.harness import run_harness
from urgencias_core.models.protocol import Forecaster, HorizonSpec

COVID_EXCLUDE_YEARS = frozenset({2020, 2021})
TOTAL_CAUSE_GLOSA = "SECCIÓN 1. TOTAL ATENCIONES DE URGENCIA"
DEMO_FACILITIES = ("24-105", "24-115")  # Hospital de Puerto Montt, Hospital de Frutillar
SEASON_WEEKS = 52
MAX_BACKTEST_WEEKS = 26
GRAIN = "W-MON"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Horizon parsing
# ---------------------------------------------------------------------------


def parse_horizon(text: str | int) -> int:
    """Parse a forecast horizon into weeks.

    Accepts ``"12"`` or ``"12s"`` (weeks) and ``"6m"`` (months, converted at
    52/12 weeks per month and rounded). Raises ``ValueError`` otherwise.
    """
    m = re.fullmatch(r"\s*(\d+)\s*([sSmM]?)\s*", str(text))
    if not m:
        raise ValueError(f"horizonte inválido: {text!r} (usa p. ej. 12, 12s o 6m)")
    n, unit = int(m.group(1)), m.group(2).lower()
    weeks = round(n * SEASON_WEEKS / 12) if unit == "m" else n
    if weeks < 1:
        raise ValueError("el horizonte debe ser de al menos 1 semana")
    return weeks


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


class NoDataError(RuntimeError):
    """Raised when the requested establishments have no usable DEIS rows."""


SOURCE_LIVE = "DEIS MINSAL (descarga actualizada)"
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
) -> pd.DataFrame:
    """DEIS rows for ``codes`` (any DEIS spelling), COVID years excluded.

    - ``offline=True`` reads the snapshot bundled with the package (demo
      hospitals only).
    - Otherwise downloads from DEIS (cached; the current year is refreshed
      weekly). With ``fallback_to_snapshot=True``, falls back to the snapshot
      when DEIS is unreachable or returns nothing.

    The data source used is recorded in ``df.attrs["source"]``.
    """
    wanted = set().union(*(facility_code_variants(c) for c in codes))
    source = SOURCE_SNAPSHOT
    if offline:
        df = _read_snapshot(wanted)
    elif fallback_to_snapshot and not deis_reachable():
        logger.warning("DEIS no responde; se usa el snapshot incluido.")
        df = _read_snapshot(wanted)
    else:
        df = fetch(start_year=start_year, facility_filter=wanted)
        source = SOURCE_LIVE
        if df.empty and fallback_to_snapshot:
            logger.warning("DEIS no entregó datos; se usa el snapshot incluido.")
            df, source = _read_snapshot(wanted), SOURCE_SNAPSHOT
        elif df.empty:
            raise NoDataError(
                f"No hay datos DEIS para {', '.join(codes)} desde {start_year}. "
                "Revisa el código con 'urg-forecast buscar' o tu conexión."
            )
    df = df[~df["year"].astype(int).isin(COVID_EXCLUDE_YEARS)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df.attrs["source"] = source
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


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


# AutoARIMA with a 52-week season is slow with the full search (~20 s per fit).
# The approximate, bounded search below runs in ~1 s with a modest accuracy cost
# on the demo hospitals. Swap in ``auto_arima(season_length=52)`` for the full
# search when time is not an issue.
FAST_ARIMA = dict(approximation=True, max_p=2, max_q=2, max_P=1, max_Q=1)


def default_models() -> dict[str, Callable[[], Forecaster]]:
    """Factories for the baseline battery (fresh instance per fit)."""
    return {
        "SeasonalNaive": SeasonalNaiveBaseline,
        "AutoARIMA": lambda: auto_arima(season_length=SEASON_WEEKS, **FAST_ARIMA),
        "AutoETS": lambda: auto_ets(season_length=SEASON_WEEKS),
    }


@dataclass
class ForecastResult:
    code: str
    name: str
    history: pd.DataFrame  # weekly: timestamp, count
    backtest_weeks: int
    backtest: pd.DataFrame  # one row per model: mae, mape, qloss_80, ...
    best: str
    backtest_pred: pd.DataFrame  # best model on the backtest window
    forecast: pd.DataFrame  # timestamp, q50, q80, q90, q95
    horizon_weeks: int
    source: str = SOURCE_LIVE

    @property
    def backtest_actual(self) -> pd.DataFrame:
        return self.history.iloc[-self.backtest_weeks :].reset_index(drop=True)


def min_weeks_needed(horizon_weeks: int) -> int:
    return min(horizon_weeks, MAX_BACKTEST_WEEKS) + SEASON_WEEKS


def run_forecast(
    history: pd.DataFrame,
    horizon_weeks: int,
    *,
    code: str = "",
    name: str = "",
    models: dict[str, Callable[[], Forecaster]] | None = None,
    source: str = SOURCE_LIVE,
) -> ForecastResult:
    """Backtest ``models`` and forecast ``horizon_weeks`` ahead with the best one.

    The backtest window equals the horizon, capped at 26 weeks, so the reported
    error reflects the horizon you asked for. Needs ``backtest + 52`` complete
    weeks of history; raises ``NoDataError`` otherwise.
    """
    models = models or default_models()
    backtest_weeks = min(horizon_weeks, MAX_BACKTEST_WEEKS)
    if len(history) < backtest_weeks + SEASON_WEEKS:
        raise NoDataError(
            f"{name or code}: se necesitan al menos {backtest_weeks + SEASON_WEEKS} "
            f"semanas completas y hay {len(history)}."
        )

    bt_horizon = HorizonSpec(grain=GRAIN, length=backtest_weeks)
    report = run_harness(
        series=history,
        target_col="count",
        horizon=bt_horizon,
        holdout_length=backtest_weeks,
        baselines={k: f() for k, f in models.items()},
        verbose=False,
    )
    table = report.table.drop(columns=["role"], errors="ignore")
    best = str(table["qloss_80"].idxmin())

    actual = history.iloc[-backtest_weeks:].reset_index(drop=True)
    bt_pred = report.predictions[best].reset_index(drop=True)
    # statsforecast can offset weekly stamps slightly; align to the actual weeks.
    bt_pred["timestamp"] = actual["timestamp"].to_numpy()[: len(bt_pred)]

    fc = models[best]()
    fc.fit(history, "count")
    forward = fc.predict(HorizonSpec(grain=GRAIN, length=horizon_weeks))

    return ForecastResult(
        code=code,
        name=name or code,
        history=history,
        backtest_weeks=backtest_weeks,
        backtest=table,
        best=best,
        backtest_pred=bt_pred,
        forecast=forward,
        horizon_weeks=horizon_weeks,
        source=source,
    )


__all__ = [
    "COVID_EXCLUDE_YEARS",
    "DEMO_FACILITIES",
    "ForecastResult",
    "NoDataError",
    "daily_totals",
    "default_models",
    "facility_name",
    "load_deis",
    "min_weeks_needed",
    "parse_horizon",
    "run_forecast",
    "to_weekly",
    "weekly_series",
]
