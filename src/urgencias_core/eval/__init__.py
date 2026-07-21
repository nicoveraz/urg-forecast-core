"""Baselines, statsforecast wrappers, and the backtest harness.

``StatsForecastWrapper`` and the ``auto_*`` factories are import-safe; they only
need the ``models`` extra when a model is actually fitted.
"""

from urgencias_core.eval.baselines import (
    SeasonalNaiveBaseline,
    StatsForecastWrapper,
    auto_arima,
    auto_ets,
    auto_theta,
    mstl,
)
from urgencias_core.eval.harness import HarnessReport, quantile_loss, run_harness

__all__ = [
    "SeasonalNaiveBaseline",
    "StatsForecastWrapper",
    "auto_arima",
    "auto_ets",
    "auto_theta",
    "mstl",
    "run_harness",
    "HarnessReport",
    "quantile_loss",
]
