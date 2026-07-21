"""urg-forecast-core: reference code for Chilean ED analytics, simulation, and forecasting."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# Curated, minimal-install-safe top-level API. Heavier capabilities (LightGBM
# forecaster, DEIS fetcher, weather client, FastAPI server) stay behind their
# own submodules + extras and are intentionally NOT re-exported here, so that
# ``import urgencias_core`` never pulls an optional dependency.
from urgencias_core.data.loader import load_visits
from urgencias_core.data.timeseries import hourly_timeseries
from urgencias_core.eval.baselines import SeasonalNaiveBaseline
from urgencias_core.eval.harness import run_harness
from urgencias_core.features.calendar import calendar_features
from urgencias_core.models.protocol import HorizonSpec
from urgencias_core.simulation.engine import simulate

try:
    __version__ = version("urg-forecast-core")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "load_visits",
    "hourly_timeseries",
    "calendar_features",
    "HorizonSpec",
    "SeasonalNaiveBaseline",
    "run_harness",
    "simulate",
]
