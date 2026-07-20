"""Helpers for guarding optional-dependency imports with actionable errors.

The core install (``pip install urgencias-core``) ships only the data,
timeseries, feature, and simulation layers. Heavier capabilities live behind
extras: ``models`` (LightGBM/statsforecast), ``server`` (FastAPI/uvicorn),
``viz`` (matplotlib/tabulate), and ``fetch`` (httpx). Modules that need those
libraries raise a clear, install-me error instead of a bare ``ImportError``.
"""

from __future__ import annotations


def missing_extra_error(extra: str, feature: str) -> ImportError:
    """Build an ImportError telling the user which extra to install.

    Usage::

        try:
            from lightgbm import LGBMRegressor
        except ImportError as exc:
            raise missing_extra_error("models", "LGBQuantileForecaster") from exc
    """
    return ImportError(
        f'{feature} requires the "{extra}" extra. '
        f'Install it with: pip install "urgencias-core[{extra}]"'
    )
