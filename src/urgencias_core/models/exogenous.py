"""Harmonic regression with external weekly regressors: the standard way to add one.

A regressor is any weekly table with ``timestamp`` (DEIS weeks, W-MON: the 7 days ending on
that Monday) and one numeric column per variable, for example viral positivity, temperature
or air quality. :class:`HarmonicExogenous` adds those columns to the design of
:class:`~urgencias_core.models.harmonic.HarmonicRegression` with one rule that keeps the
backtest honest: **at a forecast origin it only sees what had been published by then.**

- ``report_delay_weeks``: how long the source takes to publish a week. At origin ``T`` only
  weeks ending on or before ``T - report_delay_weeks`` exist.
- ``lag_weeks``: the target week ``t`` uses the regressor at ``t - lag_weeks``.
- ``future``: what to use for lagged weeks that are not yet published (needed whenever the
  horizon reaches past ``lag_weeks - report_delay_weeks``):

  - ``"climatology"``: the mean of the same ISO week in past years.
  - ``"forecast"``: a projection of the regressor itself with its own harmonic regression
    (no trend) and AutoARIMA residuals, so a season running early or late carries forward.
    This allows ``lag_weeks < report_delay_weeks`` (even 0: the concurrent week, projected).

With ``known_future=True`` (calendar variables: holidays, school holidays) the values are
known ahead, so every row of the table is usable, including future weeks, and nothing is
filled unless the table ends before the forecast does.

Years listed in ``exclude_years`` (2020-2021 by default, the pandemic) are left out of the
climatology and of the projection's fit. Projected values are clipped to the range observed.

The easiest way in is :meth:`HarmonicExogenous.from_regressor` with a
:class:`~urgencias_core.regressors.Regressor`, which carries the table and its publication
rules (see :mod:`urgencias_core.regressors`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from urgencias_core.models.harmonic import WEEKS_PER_YEAR, HarmonicRegression
from urgencias_core.models.protocol import HorizonSpec

if TYPE_CHECKING:
    from urgencias_core.regressors import Regressor

FUTURE_MODES = ("climatology", "forecast")


def project_series(
    published: pd.DataFrame,
    column: str,
    weeks: int,
    k: int = 3,
    period: float = WEEKS_PER_YEAR,
    exclude_years: Sequence[int] = (2020, 2021),
) -> pd.Series:
    """Project a weekly regressor ``weeks`` ahead of its last row (the median path).

    Harmonic regression without trend plus AutoARIMA residuals, fitted on ``published``
    minus ``exclude_years``; values are clipped to the range observed. Indexed by week.
    """
    pub = published.assign(timestamp=pd.to_datetime(published["timestamp"]))
    pub = pub.sort_values("timestamp")
    keep = ~pub["timestamp"].dt.year.isin(exclude_years)
    hist = (pub[keep] if keep.any() else pub)[["timestamp", column]].dropna()
    model = HarmonicRegression(k=k, trend=False, period=period)
    model.fit(hist.rename(columns={column: "y"}).reset_index(drop=True), "y")
    model._last = pub["timestamp"].iloc[-1]  # continue from the last row, not the last kept
    pred = model.predict(HorizonSpec(grain="W-MON", length=max(int(weeks), 1)))
    lo, hi = hist[column].min(), hist[column].max()
    return pd.Series(pred["q50"].clip(lo, hi).to_numpy(), index=pd.to_datetime(pred["timestamp"]))


class HarmonicExogenous(HarmonicRegression):
    """:class:`HarmonicRegression` plus external weekly regressors, published-at-origin.

    ``regressors`` is a DataFrame (``timestamp`` + ``columns``) or a zero-argument function
    that returns one, called once on first use (lets the data load lazily).
    """

    def __init__(
        self,
        regressors: pd.DataFrame | Callable[[], pd.DataFrame],
        columns: Sequence[str],
        lag_weeks: int = 0,
        report_delay_weeks: int = 0,
        future: str = "climatology",
        exclude_years: Sequence[int] = (2020, 2021),
        known_future: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if future not in FUTURE_MODES:
            raise ValueError(f"future must be one of {FUTURE_MODES}, not {future!r}")
        if lag_weeks < 0 or report_delay_weeks < 0:
            raise ValueError("lag_weeks and report_delay_weeks must be >= 0")
        if known_future and report_delay_weeks:
            raise ValueError("a variable with a known future has no report delay")
        if not known_future and future == "climatology" and lag_weeks < report_delay_weeks:
            raise ValueError(
                "with future='climatology' lag_weeks must be >= report_delay_weeks "
                "(otherwise the forecast never sees real data); use future='forecast'"
            )
        self._source = regressors
        self.columns = tuple(columns)
        self.lag_weeks = lag_weeks
        self.report_delay_weeks = report_delay_weeks
        self.future = future
        self.exclude_years = tuple(exclude_years)
        self.known_future = known_future
        self._fill: dict[str, pd.Series] = {}

    @classmethod
    def from_regressor(
        cls,
        regressor: Regressor,
        columns: Sequence[str] | None = None,
        lag_weeks: int = 0,
        future: str = "climatology",
        **kwargs,
    ) -> HarmonicExogenous:
        """Build from a :class:`~urgencias_core.regressors.Regressor`: its table (loaded
        lazily), its report delay and whether its future is known. ``columns`` defaults to
        all of the regressor's columns."""
        return cls(
            regressor.load,
            columns or regressor.columns,
            lag_weeks=lag_weeks,
            report_delay_weeks=regressor.report_delay_weeks,
            future=future,
            known_future=regressor.known_future,
            **kwargs,
        )

    # -- data ---------------------------------------------------------------------------
    @property
    def regressors(self) -> pd.DataFrame:
        if callable(self._source):
            self._source = self._source()
        df = self._source
        missing = {"timestamp", *self.columns} - set(df.columns)
        if missing:
            raise ValueError(f"regressor table lacks columns {sorted(missing)}")
        return df

    def _published(self) -> pd.DataFrame:
        df = self.regressors
        ts = pd.to_datetime(df["timestamp"])
        if self.known_future:
            cut = ts.max()  # calendar-like: known ahead, nothing is "unpublished"
        else:
            cut = self._origin - pd.Timedelta(weeks=self.report_delay_weeks)
        pub = df.loc[ts <= cut, ["timestamp", *self.columns]].copy()
        pub["timestamp"] = pd.to_datetime(pub["timestamp"])
        if pub.empty:
            raise ValueError("no regressor data published before the forecast origin")
        return pub.sort_values("timestamp").reset_index(drop=True)

    def _training(self, pub: pd.DataFrame) -> pd.DataFrame:
        keep = ~pub["timestamp"].dt.year.isin(self.exclude_years)
        return pub[keep] if keep.any() else pub

    # -- filling unpublished weeks --------------------------------------------------------
    def _climatology(self, pub: pd.DataFrame, col: str, when: pd.Series) -> np.ndarray:
        hist = self._training(pub)
        clim = hist.groupby(hist["timestamp"].dt.isocalendar().week)[col].mean()
        return when.dt.isocalendar().week.map(clim).fillna(hist[col].mean()).to_numpy(float)

    def _projection(self, pub: pd.DataFrame, col: str, until: pd.Timestamp) -> pd.Series:
        """Projection of ``col`` from the last published week through ``until`` (cached)."""
        cached = self._fill.get(col)
        if cached is None or cached.index[-1] < until:
            last = pub["timestamp"].iloc[-1]
            weeks = max(int(round((until - last).days / 7)), 52)
            cached = project_series(
                pub, col, weeks, k=self.k, period=self.period, exclude_years=self.exclude_years
            )
            self._fill[col] = cached
        return cached

    def _exog(self, ts: pd.Series) -> np.ndarray:
        pub = self._published()
        when = pd.to_datetime(ts).reset_index(drop=True) - pd.Timedelta(weeks=self.lag_weeks)
        indexed = pub.set_index("timestamp")
        cols = []
        for col in self.columns:
            values = when.map(indexed[col])
            todo = values.isna() & (when > pub["timestamp"].iloc[-1])
            if self.future == "forecast" and todo.any():
                proj = self._projection(pub, col, when[todo].max())
                values = values.fillna(when.map(proj))
            values = values.fillna(pd.Series(self._climatology(pub, col, when)))
            cols.append(values.to_numpy(dtype=float))
        return np.column_stack(cols)

    # -- model ----------------------------------------------------------------------------
    def _design(self, t: np.ndarray, ts: pd.Series | None = None) -> np.ndarray:
        return np.column_stack([super()._design(t, ts), self._exog(ts)])

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        self._origin = pd.to_datetime(history["timestamp"]).iloc[-1]
        self._fill = {}
        super().fit(history, target_col)

    def regressor_path(self, horizon: HorizonSpec) -> pd.DataFrame:
        """The regressor values the last fit used for each forecast week (after fit).

        Handy to plot what the model assumed: published data, projection or climatology.
        """
        from urgencias_core.models.protocol import future_index

        idx = pd.Series(future_index(self._last, horizon))
        out = pd.DataFrame(self._exog(idx), columns=list(self.columns))
        out.insert(0, "timestamp", idx)
        return out


def _flunet_loader():
    from urgencias_core.regressors import flunet

    return flunet().load


class HarmonicFluNet(HarmonicExogenous):
    """The worked example: national positivity of influenza and RSV from WHO FluNet.

    FluNet publishes with about two weeks of delay (``report_delay_weeks=2``). With the
    defaults (lag 3, ``future="climatology"``) real data reaches only the first forecast
    week and the rest is a seasonal average. With ``future="forecast"`` the positivity is
    projected instead, so the shape of the current season carries into the forecast.
    ``positivity`` defaults to the repository copy (:func:`~urgencias_core.data.flunet.
    load_flunet`); pass your own table to test other data. It is national: it does not
    distinguish one region from another.
    """

    def __init__(
        self,
        positivity: pd.DataFrame | None = None,
        viruses: Sequence[str] = ("flu", "rsv"),
        lag_weeks: int = 3,
        report_delay_weeks: int = 2,
        future: str = "climatology",
        **kwargs,
    ) -> None:
        super().__init__(
            positivity if positivity is not None else _flunet_loader(),
            columns=viruses,
            lag_weeks=lag_weeks,
            report_delay_weeks=report_delay_weeks,
            future=future,
            **kwargs,
        )


__all__ = ["FUTURE_MODES", "HarmonicExogenous", "HarmonicFluNet", "project_series"]
