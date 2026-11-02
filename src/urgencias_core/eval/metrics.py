"""Forecast error metrics: pinball (quantile) loss, the per-window score table and the
criteria that can choose or compare models."""

from __future__ import annotations

import numpy as np
import pandas as pd

QUANTILES = (0.5, 0.8, 0.9, 0.95)
# Symmetric set for the weighted interval score: the median and the 60, 80 and 90 %
# central intervals. Models produce the lower quantiles only when the horizon asks.
WIS_QUANTILES = (0.05, 0.1, 0.2, 0.5, 0.8, 0.9, 0.95)

# Score columns that can choose a model (lower is better), with their Spanish label.
# The quantile to plan with follows from what each error costs: if falling short costs
# k times more than over-planning, the right quantile is k / (k + 1). P50: same cost;
# P80: 4 times; P90: 9 times; P95: 19 times. ``qloss_mean`` scores the median and the
# upper tail together; ``wis`` scores the whole forecast, both tails (WIS_QUANTILES).
CRITERIA = {
    "qloss_80": "pérdida P80",
    "qloss_50": "pérdida P50",
    "qloss_90": "pérdida P90",
    "qloss_95": "pérdida P95",
    "qloss_mean": "pérdida media P50–P95",
    "wis": "WIS",
    "mae": "MAE",
}
DEFAULT_CRITERION = "qloss_80"


def criterion_label(criterion: str) -> str:
    """Spanish label of a score column, e.g. ``"pérdida P80"``."""
    return CRITERIA.get(criterion, criterion)


def quantiles_for(criterion: object) -> tuple[float, ...]:
    """The quantiles a backtest must produce to score ``criterion``."""
    return WIS_QUANTILES if criterion == "wis" else QUANTILES


def quantile_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    """Pinball loss at quantile ``q``."""
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def weighted_interval_score(y_true: np.ndarray, pred: pd.DataFrame) -> float:
    """Weighted interval score (Bracher et al., 2021) on :data:`WIS_QUANTILES`.

    The median's absolute error plus, for the 60, 80 and 90 % central intervals, their
    width and a penalty for each attendance outside them, weighted by ``alpha / 2`` and
    divided by ``K + 1/2`` (K = 3 intervals). It equals twice the mean pinball loss over
    the seven quantiles. Lower is better; NaN if a quantile column is missing.
    """
    cols = [f"q{int(round(q * 100))}" for q in WIS_QUANTILES]
    if any(c not in pred.columns for c in cols):
        return float("nan")
    n = len(y_true)
    losses = [
        quantile_loss(y_true, pred[c].to_numpy(dtype=float)[:n], q)
        for q, c in zip(WIS_QUANTILES, cols, strict=True)
    ]
    return float(2 * np.mean(losses))


def score(
    actual: pd.DataFrame, pred: pd.DataFrame, quantiles=QUANTILES, target_col: str = "count"
) -> dict:
    """Errors of one forecast against the actual weeks.

    ``mae`` and ``mape`` use the median (``q50``); ``qloss_XX`` is the pinball loss at each
    quantile (NaN if the model did not produce it); ``qloss_mean`` averages P50, P80, P90 and
    P95, the median and the upper tail; ``wis`` is :func:`weighted_interval_score`, which
    also scores the lower tail and needs ``q5``, ``q10`` and ``q20`` (NaN without them);
    ``covered`` counts weeks at or below ``q80`` out of ``n``.

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
        row[f"qloss_{int(round(q * 100))}"] = (
            quantile_loss(y, pred[col].to_numpy(dtype=float)[: len(y)], q)
            if col in pred.columns
            else float("nan")
        )
    upper = [row.get(f"qloss_{int(round(q * 100))}", float("nan")) for q in QUANTILES]
    row["qloss_mean"] = float(np.mean(upper))
    row["wis"] = weighted_interval_score(y, pred)
    row["qloss_80_short"] = float(np.mean(0.8 * np.maximum(y - q80, 0)))
    row["qloss_80_excess"] = float(np.mean(0.2 * np.maximum(q80 - y, 0)))
    row["width_80"] = float(np.mean(q80 - q50))
    row["covered"] = int(np.sum(y <= q80))
    row["n"] = len(y)
    return row


__all__ = [
    "WIS_QUANTILES",
    "quantiles_for",
    "weighted_interval_score",
    "CRITERIA",
    "DEFAULT_CRITERION",
    "QUANTILES",
    "criterion_label",
    "quantile_loss",
    "score",
]
