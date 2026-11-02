"""Median ensemble: combine several forecasters quantile by quantile."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from urgencias_core.models.protocol import Forecaster, HorizonSpec


def median_of(preds: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    """The median of several predictions, column by column (``timestamp`` from the first).

    The median keeps the quantiles in order: if every member has q50 <= q80, so does it.
    """
    out = pd.DataFrame({"timestamp": preds[0]["timestamp"].to_numpy()})
    for col in columns:
        stacked = np.vstack([p[col].to_numpy(dtype=float)[: len(out)] for p in preds])
        out[col] = np.median(stacked, axis=0)
    return out


class MedianEnsemble:
    """Fit every member and return the median of their predictions per quantile.

    Members that fail to fit are dropped; at least one must succeed. The
    median is robust to a single member going astray, which is the usual
    reason ensembles of a few decent models beat each of them on average.

    Give it to a backtest as ``functools.partial(MedianEnsemble, members)``: if the
    members are in the same backtest, their predictions are combined instead of fitting
    them twice.
    """

    def __init__(self, members: dict[str, Callable[[], Forecaster]]) -> None:
        self.members = members
        self._fitted: dict[str, Forecaster] = {}

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        self._fitted = {}
        for name, factory in self.members.items():
            try:
                model = factory()
                model.fit(history, target_col)
            except Exception:  # noqa: BLE001 - a weak member must not sink the ensemble
                continue
            self._fitted[name] = model
        if not self._fitted:
            raise RuntimeError("MedianEnsemble: no member could be fitted")

    def predict(self, horizon: HorizonSpec) -> pd.DataFrame:
        preds = [m.predict(horizon).reset_index(drop=True) for m in self._fitted.values()]
        return median_of(preds, list(horizon.quantile_columns))


__all__ = ["MedianEnsemble", "median_of"]
