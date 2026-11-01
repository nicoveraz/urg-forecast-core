"""Interval calibration from backtest errors: widen bands that were too narrow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from urgencias_core.eval.metrics import QUANTILES


def calibration_factors(
    actuals: list[pd.DataFrame], preds: list[pd.DataFrame], quantiles=QUANTILES
) -> dict[str, float]:
    """Scale factors that make each upper band reach its nominal coverage.

    For each quantile ``q`` above the median, the factor is the ``q``-th
    empirical quantile of ``(y - q50) / (q_pred - q50)`` over all backtest
    weeks: multiplying the band width by it would have covered a fraction ``q``
    of those weeks. Factors are never below 1 (bands are widened, never
    narrowed), so a well-calibrated model is left unchanged.
    """
    y = np.concatenate([a["count"].to_numpy(dtype=float) for a in actuals])
    out: dict[str, float] = {}
    for q in quantiles:
        if q <= 0.5:
            continue
        col = f"q{int(round(q * 100))}"
        med = np.concatenate(
            [p["q50"].to_numpy(dtype=float)[: len(a)] for a, p in zip(actuals, preds, strict=True)]
        )
        up = np.concatenate(
            [p[col].to_numpy(dtype=float)[: len(a)] for a, p in zip(actuals, preds, strict=True)]
        )
        width = up - med
        ok = width > 1e-9
        if ok.sum() < 5:
            out[col] = 1.0
            continue
        ratio = (y[ok] - med[ok]) / width[ok]
        out[col] = float(max(1.0, np.quantile(ratio, q)))
    return out


def apply_calibration(forecast: pd.DataFrame, factors: dict[str, float]) -> pd.DataFrame:
    """Widen each upper band of ``forecast`` by its factor, keeping bands ordered."""
    out = forecast.copy()
    prev = out["q50"]
    for col in sorted(factors, key=lambda c: int(c[1:])):
        out[col] = np.maximum(out["q50"] + factors[col] * (forecast[col] - forecast["q50"]), prev)
        prev = out[col]
    return out


__all__ = ["apply_calibration", "calibration_factors"]
