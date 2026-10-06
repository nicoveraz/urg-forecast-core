"""The ``Forecaster`` protocol and horizon helpers. Implement it to add your own model."""

from urgencias_core.models.protocol import (
    Forecaster,
    HorizonSpec,
    future_index,
    next_timestamp,
)

__all__ = ["Forecaster", "HorizonSpec", "future_index", "next_timestamp"]
