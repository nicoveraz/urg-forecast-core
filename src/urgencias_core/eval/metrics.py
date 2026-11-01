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

    The P80 loss is split in its two parts, ``qloss_80 = qloss_80_short + qloss_80_excess``:
    weeks above ``q80`` cost 0.8 per attendance (``short``), weeks below cost 0.2
    (``excess``). ``width_80`` is the mean ``q80 - q50``. Together they show why a narrower
    band is not better by itself: lowering ``q80`` pays only while fewer than one week in
    five ends above it.
    """
    y = actual[target_col].to_numpy(dtype=float)
    q50 = pred["q50"].to_numpy(dtype=float)[: len(y)]
    q80 = pred["q80"].to_numpy(dtype=float)[: len(y)]
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
    row["qloss_80_short"] = float(np.mean(0.8 * np.maximum(y - q80, 0)))
    row["qloss_80_excess"] = float(np.mean(0.2 * np.maximum(q80 - y, 0)))
    row["width_80"] = float(np.mean(q80 - q50))
    row["covered"] = int(np.sum(y <= q80))
    row["n"] = len(y)
    return row


__all__ = ["QUANTILES", "quantile_loss", "score"]
