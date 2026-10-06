"""urg-forecast-core: an open base for forecasting Chilean ED demand from DEIS data."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from urgencias_core.eval.baselines import SeasonalNaiveBaseline
from urgencias_core.eval.harness import run_harness
from urgencias_core.features.calendar import calendar_features
from urgencias_core.models.protocol import Forecaster, HorizonSpec
from urgencias_core.pipeline import load_deis, parse_horizon, run_forecast, weekly_series

try:
    __version__ = version("urg-forecast-core")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "Forecaster",
    "HorizonSpec",
    "SeasonalNaiveBaseline",
    "calendar_features",
    "load_deis",
    "parse_horizon",
    "run_forecast",
    "run_harness",
    "weekly_series",
]
