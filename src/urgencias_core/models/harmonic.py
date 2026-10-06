"""Harmonic regression: linear trend + Fourier terms for the annual cycle.

The residuals are modeled with a non-seasonal AutoARIMA, which supplies the
short-term dynamics and the prediction intervals. This captures a 52-week
seasonality cheaply (a seasonal ARIMA with period 52 is slow, and statsforecast's
ETS drops seasonality above period 24).

It is also a compact example of a custom model: any class with ``fit`` and
``predict`` returning ``timestamp, q50, q80, q90, q95`` satisfies the
:class:`~urgencias_core.models.protocol.Forecaster` protocol.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from urgencias_core.models.protocol import HorizonSpec, future_index

WEEKS_PER_YEAR = 365.25 / 7


def holidays_per_week(week_ends: pd.Series | pd.DatetimeIndex, country: str = "CL") -> np.ndarray:
    """Number of public holidays on weekdays in each week ending on ``week_ends``.

    Weeks follow DEIS aggregation (W-MON): the 7 days ending on that Monday.
    """
    import holidays as pyholidays

    ends = pd.to_datetime(pd.Series(week_ends)).reset_index(drop=True)
    years = range(ends.min().year - 1, ends.max().year + 2)
    cal = pyholidays.country_holidays(country, years=years)
    days = {d for d in cal if d.weekday() < 5}
    out = np.zeros(len(ends))
    for i, end in enumerate(ends):
        start = (end - pd.Timedelta(days=6)).date()
        out[i] = sum(1 for d in days if start <= d <= end.date())
    return out


class HarmonicRegression:
    """Trend + ``k`` annual Fourier pairs, AutoARIMA on the residuals.

    With ``holidays=True`` the number of weekday public holidays in each week
    (Chilean calendar by default) is added as a regressor.
    """

    def __init__(
        self,
        k: int = 3,
        trend: bool = True,
        period: float = WEEKS_PER_YEAR,
        holidays: bool = False,
        country: str = "CL",
        quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    ) -> None:
        self.k = k
        self.trend = trend
        self.period = period
        self.holidays = holidays
        self.country = country
        self.quantiles = tuple(quantiles)
        self._beta: np.ndarray | None = None

    def _design(self, t: np.ndarray, ts: pd.Series | None = None) -> np.ndarray:
        cols = [np.ones_like(t)]
        if self.trend:
            cols.append(t / 52.0)
        for i in range(1, self.k + 1):
            w = 2 * np.pi * i * t / self.period
            cols += [np.sin(w), np.cos(w)]
        if self.holidays:
            cols.append(holidays_per_week(ts, self.country))
        return np.column_stack(cols)

    def _t(self, ts: pd.Series) -> np.ndarray:
        return ((pd.to_datetime(ts) - self._t0).dt.days / 7.0).to_numpy(dtype=float)

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        from urgencias_core.eval.baselines import auto_arima

        ts = pd.to_datetime(history["timestamp"]).reset_index(drop=True)
        self._t0 = ts.iloc[0]
        self._last = ts.iloc[-1]
        y = history[target_col].to_numpy(dtype=float)
        X = self._design(self._t(ts), ts)
        self._beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ self._beta
        self._resid = auto_arima(season_length=1, quantiles=self.quantiles)
        self._resid.fit(pd.DataFrame({"timestamp": ts, "r": resid}), "r")

    def predict(self, horizon: HorizonSpec) -> pd.DataFrame:
        if self._beta is None:
            raise RuntimeError("HarmonicRegression.predict called before fit")
        idx = future_index(self._last, horizon)
        base = self._design(self._t(pd.Series(idx)), pd.Series(idx)) @ self._beta
        r = self._resid.predict(horizon)
        out = pd.DataFrame({"timestamp": idx})
        for col in horizon.quantile_columns:
            out[col] = base + r[col].to_numpy()[: len(base)]
        return out


__all__ = ["HarmonicRegression", "holidays_per_week"]
