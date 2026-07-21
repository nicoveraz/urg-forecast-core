"""Forecasting protocol + horizon helpers.

The LightGBM quantile forecaster lives in
:mod:`urgencias_core.models.lgb_quantile` (needs the ``models`` extra) and is
not re-exported here.
"""

from urgencias_core.models.protocol import (
    Forecaster,
    HorizonSpec,
    future_index,
    next_timestamp,
)

__all__ = ["Forecaster", "HorizonSpec", "future_index", "next_timestamp"]
