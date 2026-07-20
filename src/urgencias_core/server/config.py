"""TOML config loader for the reference HTTP server.

The server reads a single TOML file (default: ``urg-forecast-core.toml`` in the
current working directory). When no file is present it falls back to a
built-in default that points at the synthetic fixture shipped inside the
package, so the server runs out of the box from both a source checkout and
a ``pip install``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from urgencias_core.data.fixtures import synthetic_visits_path


def default_fixture_path() -> Path:
    """Filesystem path to the synthetic demo fixture bundled with the package.

    The fixture is a compact one-year synthetic ED visit table used as the
    zero-config default dataset for the reference server and demos. Resolves
    correctly from both a source checkout and an installed wheel.
    """
    return synthetic_visits_path()


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parquet: Path = Field(
        default_factory=default_fixture_path,
        description="Path to a visit-level parquet file matching the loader schema.",
    )


class ForecastConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forecaster: str = Field(
        default="seasonal_naive",
        description="Forecaster to run on /forecast. One of: seasonal_naive, lgb_quantile.",
    )
    target: str = Field(
        default="arrivals",
        description="Column from the hourly time series to forecast.",
    )
    horizon_hours: int = Field(default=168, ge=1, le=24 * 30)


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_hours: int = Field(default=24, ge=1, le=72)
    n_sims: int = Field(default=200, ge=10, le=5000)
    current_census: int = Field(default=0, ge=0)
    start_hour: int = Field(default=12, ge=0, le=23)
    arrivals_per_hour: float | None = Field(
        default=None,
        description=(
            "Flat arrivals mean per hour. When None, uses the recent history "
            "mean from the hourly time series."
        ),
    )


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: DataConfig = Field(default_factory=DataConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)


DEFAULT_CONFIG_FILENAME = "urg-forecast-core.toml"


def load_config(path: str | Path | None = None) -> ServerConfig:
    """Load and validate a TOML config. Falls back to defaults when absent."""
    if path is None:
        candidate = Path.cwd() / DEFAULT_CONFIG_FILENAME
        if not candidate.exists():
            return ServerConfig()
        path = candidate
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return ServerConfig(**raw)


__all__ = [
    "DataConfig",
    "ForecastConfig",
    "ServerConfig",
    "SimulationConfig",
    "load_config",
    "default_fixture_path",
    "DEFAULT_CONFIG_FILENAME",
]
