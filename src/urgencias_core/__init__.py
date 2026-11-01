"""urg-forecast-core: an open base for analysing and forecasting Chilean ED demand.

The package is organised by question:

- :mod:`urgencias_core.data` — where the series come from (DEIS, the weekly copy, FluNet).
- :mod:`urgencias_core.analysis` — what demand looks like (yearly summary, typical year,
  level, year over year, weekday).
- :mod:`urgencias_core.models` — how to forecast (the ``Forecaster`` protocol, built-in
  models, external regressors, the registry of names).
- :mod:`urgencias_core.eval` — how good a forecast is (rolling backtest, metrics,
  calibration, paired comparison).
- :mod:`urgencias_core.forecast` — pick the best model and forecast forward.
- :mod:`urgencias_core.regressors` — external weekly variables (FluNet, the Chilean
  calendar) with their publication rules.
- :mod:`urgencias_core.features` — Chilean calendar variables, daily and weekly.

The names below are the usual entry points.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from urgencias_core._compat import moved
from urgencias_core.data.series import load_deis, weekly_series
from urgencias_core.eval.backtest import backtest
from urgencias_core.eval.compare import compare_models
from urgencias_core.features.calendar import calendar_features
from urgencias_core.forecast import parse_horizon, run_forecast
from urgencias_core.models.baselines import SeasonalNaiveBaseline
from urgencias_core.models.protocol import Forecaster, HorizonSpec
from urgencias_core.models.registry import available_models, default_models

try:
    __version__ = version("urg-forecast-core")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__getattr__ = moved("urgencias_core", {"run_harness": "urgencias_core.eval.harness"})

__all__ = [
    "__version__",
    "Forecaster",
    "HorizonSpec",
    "SeasonalNaiveBaseline",
    "available_models",
    "backtest",
    "calendar_features",
    "compare_models",
    "default_models",
    "load_deis",
    "parse_horizon",
    "run_forecast",
    "weekly_series",
]
