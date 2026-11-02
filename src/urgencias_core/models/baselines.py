"""Baselines the eval harness uses to establish the accuracy bar.

- ``SeasonalNaiveBaseline``: empirical quantiles conditional on a seasonal
  key inferred from the grain (``(dow, hour)`` for hourly, ``(month, dow)``
  for daily, etc.).
- ``StatsForecastWrapper``: thin wrapper around any statsforecast model that
  produces quantile intervals, mapping the ``level`` API back to the standard
  quantile columns (q50/q80/q90/q95, and q5/q10/q20 when the horizon asks for them).

Every model produces the quantiles the horizon asks for (``horizon.quantiles``); the
``quantiles`` argument of the constructors is kept for compatibility and ignored.
- Convenience factories for the baseline battery: ``auto_arima``,
  ``auto_ets``, ``auto_theta``, ``mstl``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from urgencias_core.models.protocol import HorizonSpec, future_index


class SeasonalNaiveBaseline:
    """Empirical quantile lookup conditional on a grain-specific seasonal key.

    The lookup key depends on the inferred frequency:
    - Hourly (``h``): ``(dayofweek, hour)``.
    - Daily (``D``): ``(month, dayofweek)``.
    - Weekly (``W*``): ``(isoweek,)``.
    - Monthly (``M*``): ``(month,)``.

    Unknown keys at predict time fall back to the global empirical quantiles.
    """

    def __init__(self, quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95)) -> None:
        self.quantiles = tuple(quantiles)  # ignored: predict uses horizon.quantiles
        self._lookup: dict[tuple, np.ndarray] = {}  # key -> observed values
        self._fallback: np.ndarray | None = None
        self._key_fn: Callable[[pd.Timestamp], tuple] | None = None
        self._history_end: pd.Timestamp | None = None

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        ts = pd.to_datetime(history["timestamp"])
        freq = pd.infer_freq(ts)
        self._key_fn = _key_func(freq)
        keys = pd.Series([self._key_fn(t) for t in ts])
        y = np.asarray(history[target_col], dtype="float64")
        df = pd.DataFrame({"key": keys.values, "y": y})
        for k, g in df.groupby("key", sort=False):
            self._lookup[k] = g["y"].to_numpy()
        self._fallback = y
        self._history_end = ts.max()

    def predict(self, horizon: HorizonSpec) -> pd.DataFrame:
        if self._key_fn is None or self._history_end is None or self._fallback is None:
            raise RuntimeError("SeasonalNaiveBaseline.predict called before fit")
        # Rebuild the key function from the requested grain: the fitted freq is
        # not stored, so the horizon grain is the source of truth on predict.
        key_fn = _key_func(horizon.grain)
        future = future_index(self._history_end, horizon)
        qs = list(horizon.quantiles)  # sorted ascending (HorizonSpec checks it)
        values = np.zeros((len(future), len(qs)), dtype="float64")
        for i, t in enumerate(future):
            values[i] = np.quantile(self._lookup.get(key_fn(t), self._fallback), qs)
        out = pd.DataFrame({"timestamp": future})
        for j, col in enumerate(horizon.quantile_columns):
            out[col] = values[:, j]
        return out


class StatsForecastWrapper:
    """Wrap a statsforecast model to conform to the Forecaster protocol.

    Quantile columns are derived from statsforecast's ``level`` API:
    - ``q50`` = point forecast (statsforecast median).
    - ``q80``, ``q90``, ``q95`` = upper edge of the 60, 80 and 90 % intervals (``hi``).
    - ``q20``, ``q10``, ``q5`` = lower edge of the same intervals (``lo``).
    """

    def __init__(
        self,
        model,
        quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
        name: str | None = None,
    ) -> None:
        self.model = model
        self.quantiles = tuple(quantiles)  # ignored: predict uses horizon.quantiles
        self.name = name or model.__class__.__name__
        self._sf = None
        self._freq: str | None = None
        self._alias: str | None = None

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        from statsforecast import StatsForecast

        ts = pd.to_datetime(history["timestamp"])
        freq = pd.infer_freq(ts) or "h"
        df = pd.DataFrame(
            {
                "unique_id": "series",
                "ds": ts.to_numpy(),
                "y": np.asarray(history[target_col], dtype="float64"),
            }
        )
        self._sf = StatsForecast(models=[self.model], freq=freq)
        self._sf.fit(df)
        self._freq = freq

    def predict(self, horizon: HorizonSpec) -> pd.DataFrame:
        if self._sf is None:
            raise RuntimeError(f"{self.name}.predict called before fit")
        levels = sorted({_quantile_to_level(q) for q in horizon.quantiles if q != 0.5})
        pred = self._sf.predict(h=horizon.length, level=levels)
        if "unique_id" in pred.columns:
            pred = pred.drop(columns=["unique_id"])
        alias = _infer_alias(pred)
        out = pd.DataFrame({"timestamp": pd.to_datetime(pred["ds"]).to_numpy()})
        for q, col in zip(horizon.quantiles, horizon.quantile_columns, strict=True):
            if q == 0.5:
                out[col] = pred[alias].to_numpy()
            else:
                side = "hi" if q > 0.5 else "lo"
                out[col] = pred[f"{alias}-{side}-{_quantile_to_level(q)}"].to_numpy()
        return out


def auto_arima(
    season_length: int = 24,
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    **kwargs,
) -> StatsForecastWrapper:
    """AutoARIMA forecaster (statsforecast) wrapped to the Forecaster protocol."""
    from statsforecast.models import AutoARIMA

    model = AutoARIMA(season_length=season_length, **kwargs)
    return StatsForecastWrapper(model, quantiles=quantiles, name="AutoARIMA")


def auto_ets(
    season_length: int = 24,
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    **kwargs,
) -> StatsForecastWrapper:
    """AutoETS forecaster (statsforecast) wrapped to the Forecaster protocol."""
    from statsforecast.models import AutoETS

    model = AutoETS(season_length=season_length, **kwargs)
    return StatsForecastWrapper(model, quantiles=quantiles, name="AutoETS")


def auto_theta(
    season_length: int = 24,
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    **kwargs,
) -> StatsForecastWrapper:
    """AutoTheta forecaster (statsforecast) wrapped to the Forecaster protocol."""
    from statsforecast.models import AutoTheta

    model = AutoTheta(season_length=season_length, **kwargs)
    return StatsForecastWrapper(model, quantiles=quantiles, name="AutoTheta")


def mstl(
    season_length: list[int] | tuple[int, ...] = (24, 168),
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    **kwargs,
) -> StatsForecastWrapper:
    """MSTL (multi-seasonal decomposition) forecaster wrapped to the protocol.

    Defaults to daily+weekly seasonality with an AutoARIMA trend.
    """
    from statsforecast.models import MSTL, AutoARIMA

    trend_fc = kwargs.pop("trend_forecaster", None) or AutoARIMA()
    model = MSTL(season_length=list(season_length), trend_forecaster=trend_fc, **kwargs)
    return StatsForecastWrapper(model, quantiles=quantiles, name="MSTL")


def _quantile_to_level(q: float) -> int:
    """The statsforecast central interval whose edge is quantile ``q``: 0.8 and 0.2 -> 60."""
    return int(round(abs(2 * q - 1) * 100))


def _key_func(freq: str | None) -> Callable[[pd.Timestamp], tuple]:
    if not freq:
        return lambda t: (t.dayofweek, t.hour)
    f = freq.upper()
    if f.startswith("H") or f == "h":
        return lambda t: (t.dayofweek, t.hour)
    if f.startswith("D"):
        return lambda t: (t.month, t.dayofweek)
    if f.startswith("W"):
        return lambda t: (int(t.isocalendar().week),)
    if f.startswith("M"):
        return lambda t: (t.month,)
    return lambda t: (t.dayofweek, t.hour)


def _infer_alias(pred: pd.DataFrame) -> str:
    for col in pred.columns:
        if col == "ds":
            continue
        if "-lo-" in col or "-hi-" in col:
            continue
        return col
    raise ValueError(f"Could not infer model alias from predict columns: {list(pred.columns)}")


__all__ = [
    "SeasonalNaiveBaseline",
    "StatsForecastWrapper",
    "auto_arima",
    "auto_ets",
    "auto_theta",
    "mstl",
]
