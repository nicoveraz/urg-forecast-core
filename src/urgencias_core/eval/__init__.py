"""Baselines, statsforecast wrappers, and the backtest harness.

statsforecast is imported lazily, so importing this module stays fast.
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
