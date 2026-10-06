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

import importlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from urgencias_core.data.deis import deis_reachable, facility_code_variants, fetch
from urgencias_core.data.fixtures import deis_snapshot_path
from urgencias_core.eval.baselines import (
    SeasonalNaiveBaseline,
    StatsForecastWrapper,
    auto_arima,
)
from urgencias_core.eval.harness import quantile_loss
from urgencias_core.models.ensemble import MedianEnsemble
from urgencias_core.models.harmonic import HarmonicRegression
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
# The approximate, bounded search below runs in ~1 s; on live DEIS data for seven
# hospitals its quantile loss was within 3% of the full search.
FAST_ARIMA = dict(approximation=True, max_p=2, max_q=2, max_P=1, max_Q=1)

BACKTEST_ORIGINS = 3  # rolling backtest windows
BACKTEST_STEP = 8  # weeks between window starts
MIN_TRAIN_WEEKS = 2 * SEASON_WEEKS  # MSTL needs two full seasons
QUANTILES = (0.5, 0.8, 0.9, 0.95)


def _mstl() -> Forecaster:
    from statsforecast.models import MSTL, AutoETS

    model = MSTL(season_length=[SEASON_WEEKS], trend_forecaster=AutoETS(model="ZZN"))
    return StatsForecastWrapper(model, name="MSTL")


def default_models() -> dict[str, Callable[[], Forecaster]]:
    """Factories for the model battery compared by default (fresh instance per fit).

    SeasonalNaive is the reference. The other three all capture the annual
    cycle in different ways; on live DEIS data none of them won everywhere, so
    the best one is chosen per establishment by rolling backtest.
    """
    return {
        "SeasonalNaive": SeasonalNaiveBaseline,
        "AutoARIMA": lambda: auto_arima(season_length=SEASON_WEEKS, **FAST_ARIMA),
        "Armónico": HarmonicRegression,
        "MSTL": _mstl,
    }


def _tbats() -> Forecaster:
    from statsforecast.models import AutoTBATS

    return StatsForecastWrapper(AutoTBATS(season_length=[SEASON_WEEKS]), name="TBATS")


def _theta() -> Forecaster:
    from statsforecast.models import AutoTheta

    return StatsForecastWrapper(AutoTheta(season_length=SEASON_WEEKS), name="Theta")


def _ensemble() -> Forecaster:
    core = default_models()
    return MedianEnsemble({k: core[k] for k in ("AutoARIMA", "Armónico", "MSTL")})


def extra_models() -> dict[str, Callable[[], Forecaster]]:
    """Opt-in models for experimenting (``-m NAME``); not compared by default."""
    return {
        "TBATS": _tbats,
        "Theta": _theta,
        "Ensamble": _ensemble,
        "ArmónicoFeriados": lambda: HarmonicRegression(holidays=True),
    }


# One-line descriptions shown by ``urg-forecast modelos``.
MODEL_INFO = {
    "SeasonalNaive": "referencia: misma semana de años anteriores (cuantiles empíricos)",
    "AutoARIMA": "ARIMA estacional (52 semanas) con búsqueda acotada",
    "Armónico": "tendencia + ciclo anual con términos de Fourier, ARIMA en los residuos",
    "MSTL": "descomposición estacional + tendencia ETS",
    "TBATS": "estacionalidad trigonométrica con Box-Cox y errores ARMA; lento (~15 s)",
    "Theta": "solo tendencia (no detecta el ciclo anual); sirve de contraste",
    "Ensamble": "mediana, cuantil a cuantil, de AutoARIMA, Armónico y MSTL",
    "ArmónicoFeriados": "Armónico + feriados chilenos en día hábil de cada semana",
}


def available_models() -> dict[str, Callable[[], Forecaster]]:
    """All built-in models: the default battery plus the opt-in extras."""
    return default_models() | extra_models()


def _fold(name: str) -> str:
    """Case- and accent-insensitive key, so 'armonico' matches 'Armónico'."""
    import unicodedata

    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def resolve_models(names: list[str] | None) -> dict[str, Callable[[], Forecaster]]:
    """Model factories for ``names``: built-in names or ``"module.path:Class"``.

    ``None`` or an empty list returns :func:`default_models`. A custom class is
    imported from the given module and must be constructible without arguments
    and satisfy the :class:`~urgencias_core.models.protocol.Forecaster`
    protocol. Raises ``ValueError`` for unknown names or bad imports.
    """
    if not names:
        return default_models()
    builtin = available_models()
    lookup = {_fold(k): k for k in builtin}
    out: dict[str, Callable[[], Forecaster]] = {}
    for name in names:
        if ":" in name:
            module_name, _, attr = name.partition(":")
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, attr)
            except (ImportError, AttributeError) as exc:
                raise ValueError(f"no se pudo importar el modelo {name!r}: {exc}") from exc
            if not (hasattr(cls, "fit") and hasattr(cls, "predict")):
                raise ValueError(f"{name!r} no tiene métodos fit y predict")
            out[attr] = cls
        elif _fold(name) in lookup:
            key = lookup[_fold(name)]
            out[key] = builtin[key]
        else:
            raise ValueError(
                f"modelo desconocido: {name!r}. Opciones: {', '.join(builtin)} "
                "o 'modulo:Clase' para un modelo propio ('urg-forecast modelos' los describe)."
            )
    return out


@dataclass
class ForecastResult:
    code: str
    name: str
    history: pd.DataFrame  # weekly: timestamp, count
    backtest_weeks: int  # length of each backtest window
    backtest: pd.DataFrame  # one row per model, averaged over windows
    best: str
    backtest_pred: pd.DataFrame  # best model on the most recent window
    forecast: pd.DataFrame  # timestamp, q50, q80, q90, q95
    horizon_weeks: int
    source: str = SOURCE_LIVE
    backtest_origins: int = 1
    coverage80: tuple[int, int] = (0, 0)  # best model: weeks at/below P80, total weeks
    skipped: dict[str, str] = field(default_factory=dict)  # model -> error
    # Factor applied to each upper band (q - q50) after calibration; 1.0 = unchanged.
    interval_scale: dict[str, float] = field(default_factory=dict)

    @property
    def backtest_actual(self) -> pd.DataFrame:
        return self.history.iloc[-self.backtest_weeks :].reset_index(drop=True)


def min_weeks_needed(horizon_weeks: int) -> int:
    return min(horizon_weeks, MAX_BACKTEST_WEEKS) + MIN_TRAIN_WEEKS


def _score(actual: pd.DataFrame, pred: pd.DataFrame) -> dict:
    y = actual["count"].to_numpy(dtype=float)
    q50 = pred["q50"].to_numpy(dtype=float)[: len(y)]
    nz = y != 0
    row = {
        "mae": float(np.mean(np.abs(y - q50))),
        "mape": float(np.mean(np.abs((y[nz] - q50[nz]) / y[nz]))) if nz.any() else float("nan"),
    }
    for q in QUANTILES:
        col = f"q{int(round(q * 100))}"
        row[f"qloss_{int(round(q * 100))}"] = quantile_loss(
            y, pred[col].to_numpy(dtype=float)[: len(y)], q
        )
    row["_covered"] = int(np.sum(y <= pred["q80"].to_numpy(dtype=float)[: len(y)]))
    row["_n"] = len(y)
    return row


def calibration_factors(
    actuals: list[pd.DataFrame], preds: list[pd.DataFrame], quantiles=QUANTILES
) -> dict[str, float]:
    """Scale factors that make each upper band reach its nominal coverage.

    For each quantile ``q`` above the median, the factor is the ``q``-th
    empirical quantile of ``(y - q50) / (q_pred - q50)`` over all backtest
    weeks: multiplying the band width by it would have covered a fraction ``q``
    of those weeks. Factors are never below 1 (bands are widened, never
    narrowed), so a well-calibrated model is left unchanged.
    """
    y = np.concatenate([a["count"].to_numpy(dtype=float) for a in actuals])
    out: dict[str, float] = {}
    for q in quantiles:
        if q <= 0.5:
            continue
        col = f"q{int(round(q * 100))}"
        med = np.concatenate(
            [p["q50"].to_numpy(dtype=float)[: len(a)] for a, p in zip(actuals, preds, strict=True)]
        )
        up = np.concatenate(
            [p[col].to_numpy(dtype=float)[: len(a)] for a, p in zip(actuals, preds, strict=True)]
        )
        width = up - med
        ok = width > 1e-9
        if ok.sum() < 5:
            out[col] = 1.0
            continue
        ratio = (y[ok] - med[ok]) / width[ok]
        out[col] = float(max(1.0, np.quantile(ratio, q)))
    return out


def apply_calibration(forecast: pd.DataFrame, factors: dict[str, float]) -> pd.DataFrame:
    """Widen each upper band of ``forecast`` by its factor, keeping bands ordered."""
    out = forecast.copy()
    prev = out["q50"]
    for col in sorted(factors, key=lambda c: int(c[1:])):
        out[col] = np.maximum(out["q50"] + factors[col] * (forecast[col] - forecast["q50"]), prev)
        prev = out[col]
    return out


def run_forecast(
    history: pd.DataFrame,
    horizon_weeks: int,
    *,
    code: str = "",
    name: str = "",
    models: dict[str, Callable[[], Forecaster]] | None = None,
    source: str = SOURCE_LIVE,
    origins: int = BACKTEST_ORIGINS,
    step: int = BACKTEST_STEP,
    calibrate: bool = True,
) -> ForecastResult:
    """Rolling backtest of ``models``, then forecast with the best one.

    Each backtest window is as long as the horizon (capped at 26 weeks). Up to
    ``origins`` windows are used, ``step`` weeks apart, so the choice does not
    hinge on a single season; fewer are used when history is short. The best
    model has the lowest mean P80 quantile loss across windows. A model that
    fails to fit is skipped and reported in ``skipped``.

    With ``calibrate=True`` the forward intervals are widened by
    :func:`calibration_factors`, computed from the chosen model's backtest
    errors. The reported backtest coverage is always the raw, uncalibrated one.
    """
    models = models or default_models()
    bt = min(horizon_weeks, MAX_BACKTEST_WEEKS)
    n = len(history)
    if n < bt + MIN_TRAIN_WEEKS:
        raise NoDataError(
            f"{name or code}: se necesitan al menos {bt + MIN_TRAIN_WEEKS} "
            f"semanas completas y hay {n}."
        )
    usable = 1 + (n - bt - MIN_TRAIN_WEEKS) // step
    origins = max(1, min(origins, usable))
    spec = HorizonSpec(grain=GRAIN, length=bt, quantiles=QUANTILES)

    rows: list[dict] = []
    skipped: dict[str, str] = {}
    latest_preds: dict[str, pd.DataFrame] = {}
    all_preds: dict[str, list[tuple[pd.DataFrame, pd.DataFrame]]] = {}
    for k in range(origins):
        cut = n - bt - k * step
        train = history.iloc[:cut].reset_index(drop=True)
        actual = history.iloc[cut : cut + bt].reset_index(drop=True)
        for model_name, factory in models.items():
            if model_name in skipped:
                continue
            try:
                fc = factory()
                fc.fit(train, "count")
                pred = fc.predict(spec).reset_index(drop=True)
            except Exception as exc:  # noqa: BLE001 - one bad model must not sink the run
                logger.warning("%s: se omite (%s)", model_name, str(exc)[:80])
                skipped[model_name] = str(exc)
                continue
            # statsforecast can offset weekly stamps slightly; align to actual weeks.
            pred["timestamp"] = actual["timestamp"].to_numpy()[: len(pred)]
            rows.append({"model": model_name, **_score(actual, pred)})
            all_preds.setdefault(model_name, []).append((actual, pred))
            if k == 0:
                latest_preds[model_name] = pred

    scores = pd.DataFrame([r for r in rows if r["model"] not in skipped])
    if scores.empty:
        raise NoDataError(f"{name or code}: ningún modelo pudo ajustarse.")
    sums = scores.groupby("model")[["_covered", "_n"]].sum()
    table = scores.drop(columns=["_covered", "_n"]).groupby("model").mean()
    best = str(table["qloss_80"].idxmin())

    fc = models[best]()
    fc.fit(history, "count")
    forward = fc.predict(HorizonSpec(grain=GRAIN, length=horizon_weeks, quantiles=QUANTILES))
    scale: dict[str, float] = {}
    if calibrate:
        pairs = all_preds[best]
        scale = calibration_factors([a for a, _ in pairs], [p for _, p in pairs])
        forward = apply_calibration(forward, scale)

    return ForecastResult(
        code=code,
        name=name or code,
        history=history,
        backtest_weeks=bt,
        backtest=table,
        best=best,
        backtest_pred=latest_preds[best],
        forecast=forward,
        horizon_weeks=horizon_weeks,
        source=source,
        backtest_origins=origins,
        coverage80=(int(sums.loc[best, "_covered"]), int(sums.loc[best, "_n"])),
        skipped=skipped,
        interval_scale=scale,
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
    "resolve_models",
    "available_models",
    "extra_models",
    "MODEL_INFO",
    "calibration_factors",
    "apply_calibration",
    "run_forecast",
    "to_weekly",
    "weekly_series",
]
