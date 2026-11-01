"""Forecast error metrics: pinball (quantile) loss and the per-window score table."""

from __future__ import annotations

import numpy as np
import pandas as pd

QUANTILES = (0.5, 0.8, 0.9, 0.95)


def quantile_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    """Pinball loss at quantile ``q``."""
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def score(
    actual: pd.DataFrame, pred: pd.DataFrame, quantiles=QUANTILES, target_col: str = "count"
) -> dict:
    """Errors of one forecast against the actual weeks.

    ``mae`` and ``mape`` use the median (``q50``); ``qloss_XX`` is the pinball loss at each
    quantile; ``covered`` counts weeks at or below ``q80`` out of ``n``.
    """
    y = actual[target_col].to_numpy(dtype=float)
    q50 = pred["q50"].to_numpy(dtype=float)[: len(y)]
    nz = y != 0
    row = {
        "mae": float(np.mean(np.abs(y - q50))),
        "mape": float(np.mean(np.abs((y[nz] - q50[nz]) / y[nz]))) if nz.any() else float("nan"),
    }
    for q in quantiles:
        col = f"q{int(round(q * 100))}"
        row[f"qloss_{int(round(q * 100))}"] = quantile_loss(
            y, pred[col].to_numpy(dtype=float)[: len(y)], q
        )
    row["covered"] = int(np.sum(y <= pred["q80"].to_numpy(dtype=float)[: len(y)]))
    row["n"] = len(y)
    return row


__all__ = ["QUANTILES", "quantile_loss", "score"]
