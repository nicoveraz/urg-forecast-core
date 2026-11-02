"""Paired comparison of two models over many backtest windows: does a regressor help?

The usual backtest (three windows) is enough to pick a model, not to tell whether a new
regressor really helps one establishment: with few windows the difference is mostly noise.
:func:`compare_models` fits both models on the same windows (many origins, a few weeks
apart, spanning several seasons) and reports:

- the median relative change in P80 quantile loss per window (negative = candidate better),
  or in any other score column passed as ``metric`` (see
  :data:`~urgencias_core.eval.metrics.CRITERIA`);
- how many windows the candidate wins, with an exact two-sided sign test;
- the same split by season (winter windows, May-September, versus the rest), because a
  respiratory-virus regressor should matter in winter if it matters at all;
- a verdict in plain Spanish: "mejora", "empeora" or "sin diferencia clara".

The verdict is per establishment. When you check many establishments, expect about one in
twenty to come out "mejora" or "empeora" by chance at ``alpha=0.05``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import comb

import pandas as pd

from urgencias_core.eval.backtest import MIN_TRAIN_WEEKS, backtest
from urgencias_core.eval.metrics import (
    CRITERIA,
    DEFAULT_CRITERION,
    QUANTILES,
    criterion_label,
    quantiles_for,
)
from urgencias_core.models.protocol import Forecaster

WINTER_MONTHS = (5, 6, 7, 8, 9)


def sign_test(wins: int, n: int) -> float:
    """Exact two-sided sign test p-value for ``wins`` successes in ``n`` ties-free trials."""
    if n == 0:
        return 1.0
    k = min(wins, n - wins)
    p = 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n
    return float(min(1.0, p))


def paired_windows(
    history: pd.DataFrame,
    models: dict[str, Callable[[], Forecaster]],
    horizon_weeks: int = 4,
    origins: int = 36,
    step: int = 4,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
    quantiles: tuple[float, ...] = QUANTILES,
) -> pd.DataFrame:
    """Per-window scores of each model on the same rolling windows.

    Returns one row per (window, model): ``origin`` (last training week), ``model`` and
    every :func:`~urgencias_core.eval.metrics.score` column. Windows run backwards from
    the end of ``history``, ``step`` weeks apart, while at least ``min_train_weeks`` remain
    for training. A model that fails on a window is left out of that window.
    """
    scores = backtest(
        history, models, horizon_weeks, origins, step, min_train_weeks, quantiles
    ).scores()
    return scores if not scores.empty else pd.DataFrame(columns=["origin", "model", *CRITERIA])


@dataclass
class Comparison:
    """Result of :func:`compare_models` (candidate against base)."""

    base: str
    candidate: str
    windows: pd.DataFrame  # origin, base, candidate, rel_change, winter
    horizon_weeks: int
    alpha: float = 0.05
    metric: str = DEFAULT_CRITERION  # score column compared in each window (lower is better)

    @property
    def n(self) -> int:
        return len(self.windows)

    def _stats(self, w: pd.DataFrame) -> dict:
        diff = w["candidate"] - w["base"]
        wins, losses = int((diff < 0).sum()), int((diff > 0).sum())
        return {
            "ventanas": len(w),
            "cambio_mediano": float(w["rel_change"].median()) if len(w) else float("nan"),
            "cambio_total": float(w["candidate"].sum() / w["base"].sum() - 1)
            if len(w) and w["base"].sum() > 0
            else float("nan"),
            "gana": wins,
            "pierde": losses,
            "p": sign_test(wins, wins + losses),
        }

    def summary(self) -> pd.DataFrame:
        """Stats for all windows, winter windows and the rest (one row each)."""
        w = self.windows
        parts = {"todas": w, "invierno": w[w["winter"]], "resto": w[~w["winter"]]}
        return pd.DataFrame({k: self._stats(v) for k, v in parts.items()}).T

    @property
    def verdict(self) -> str:
        s = self._stats(self.windows)
        if s["p"] >= self.alpha:
            return "sin diferencia clara"
        return "mejora" if s["gana"] > s["pierde"] else "empeora"

    def text(self) -> str:
        """A short Spanish summary, e.g. for a report or the demo."""
        s = self._stats(self.windows)
        return (
            f"{self.candidate} frente a {self.base}, {s['ventanas']} ventanas de "
            f"{self.horizon_weeks} semanas: gana {s['gana']}, pierde {s['pierde']} "
            f"(p = {s['p']:.2f}); cambio mediano de la {criterion_label(self.metric)} "
            f"{100 * s['cambio_mediano']:+.1f} %. Veredicto: {self.verdict}."
        )


def _comparison(
    long: pd.DataFrame, bname: str, cname: str, horizon_weeks: int, alpha: float, metric: str
) -> Comparison:
    if metric not in long.columns:
        raise ValueError(f"métrica desconocida: {metric!r}; usa una de {', '.join(CRITERIA)}")
    sub = long[long["model"].isin([bname, cname])]
    wide = sub.pivot(index="origin", columns="model", values=metric)
    wide = wide.reindex(columns=[bname, cname]).dropna()
    wide = wide.rename(columns={bname: "base", cname: "candidate"}).reset_index()
    wide.columns.name = None
    wide["rel_change"] = wide["candidate"] / wide["base"].where(wide["base"] > 0) - 1
    first_target = pd.to_datetime(wide["origin"]) + pd.Timedelta(weeks=1)
    wide["winter"] = first_target.dt.month.isin(WINTER_MONTHS)
    wide = wide.sort_values("origin").reset_index(drop=True)
    return Comparison(bname, cname, wide, horizon_weeks, alpha, metric)


def compare_many(
    history: pd.DataFrame,
    base: tuple[str, Callable[[], Forecaster]],
    candidates: dict[str, Callable[[], Forecaster]],
    horizon_weeks: int = 4,
    origins: int = 36,
    step: int = 4,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
    alpha: float = 0.05,
    metric: str = DEFAULT_CRITERION,
) -> dict[str, Comparison]:
    """Like :func:`compare_models` for several candidates, fitting the base only once."""
    bname, bf = base
    if bname in candidates:
        raise ValueError("base and candidates need different names")
    long = paired_windows(
        history,
        {bname: bf, **candidates},
        horizon_weeks,
        origins,
        step,
        min_train_weeks,
        quantiles_for(metric),
    )
    return compare_scores(long, bname, list(candidates), horizon_weeks, alpha, metric)


def compare_scores(
    scores: pd.DataFrame,
    base: str,
    candidates: list[str],
    horizon_weeks: int,
    alpha: float = 0.05,
    metric: str = DEFAULT_CRITERION,
) -> dict[str, Comparison]:
    """The comparisons of :func:`compare_many` from a backtest already run.

    ``scores`` is ``Backtest.scores()`` (or :func:`paired_windows`). Use it to run the
    backtest once and both compare the models and look at what each one predicted.
    """
    if base in candidates:
        raise ValueError("base and candidates need different names")
    return {c: _comparison(scores, base, c, horizon_weeks, alpha, metric) for c in candidates}


def compare_models(
    history: pd.DataFrame,
    base: tuple[str, Callable[[], Forecaster]],
    candidate: tuple[str, Callable[[], Forecaster]],
    horizon_weeks: int = 4,
    origins: int = 36,
    step: int = 4,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
    alpha: float = 0.05,
    metric: str = DEFAULT_CRITERION,
) -> Comparison:
    """Paired backtest of ``candidate`` against ``base`` (each a ``(name, factory)`` pair).

    Defaults: 4-week windows, up to 36 origins 4 weeks apart (about three winters), at least
    two years of training, compared on the P80 quantile loss (``metric``: any column of
    :data:`~urgencias_core.eval.metrics.CRITERIA`). Only windows where both models fit are
    compared.
    """
    cname, cf = candidate
    if base[0] == cname:
        raise ValueError("base and candidate need different names")
    out = compare_many(
        history, base, {cname: cf}, horizon_weeks, origins, step, min_train_weeks, alpha, metric
    )
    return out[cname]


__all__ = [
    "Comparison",
    "WINTER_MONTHS",
    "compare_many",
    "compare_models",
    "compare_scores",
    "paired_windows",
    "sign_test",
]
