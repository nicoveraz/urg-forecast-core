"""Backtest a set of models, pick the best, and forecast forward with calibrated bands.

:func:`run_forecast` is what ``urg-forecast pronosticar`` runs: a rolling backtest
(:mod:`urgencias_core.eval.backtest`) of every model on windows as long as the horizon,
the best model refitted on all history, and its upper bands widened by the backtest
errors (:mod:`urgencias_core.eval.calibration`).

"Best" is a choice, not a fact: by default the lowest mean P80 quantile loss (falling
short costs four times more than over-planning). ``select_by`` takes any other score
column (:data:`~urgencias_core.eval.metrics.CRITERIA`) or a function of the backtest table.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from urgencias_core.data.series import GRAIN, SEASON_WEEKS, SOURCE_LIVE, NoDataError
from urgencias_core.eval.backtest import MIN_TRAIN_WEEKS, backtest
from urgencias_core.eval.calibration import apply_calibration, calibration_factors
from urgencias_core.eval.metrics import CRITERIA, DEFAULT_CRITERION, criterion_label, quantiles_for
from urgencias_core.models.protocol import Forecaster, HorizonSpec
from urgencias_core.models.registry import default_models

MAX_BACKTEST_WEEKS = 26
BACKTEST_ORIGINS = 3  # rolling backtest windows
BACKTEST_STEP = 8  # weeks between window starts

logger = logging.getLogger(__name__)

# A criterion is a score column (lower is better) or a function that receives the backtest
# table (one row per model) and returns the name of the model to use.
Criterion = str | Callable[[pd.DataFrame], str]


def parse_horizon(text: str | int) -> int:
    """Parse a forecast horizon into weeks.

    Accepts ``"12"`` or ``"12s"`` (weeks) and ``"6m"`` (months, converted at
    52/12 weeks per month and rounded). Raises ``ValueError`` otherwise.
    """
    m = re.fullmatch(r"\s*(\d+)\s*([sSmM]?)\s*", str(text))
    if not m:
        raise ValueError(f"horizonte inválido: {text!r} (usa p. ej. 12, 12s o 6m)")
    n, unit = int(m.group(1)), m.group(2).lower()
    weeks = round(n * SEASON_WEEKS / 12) if unit == "m" else n
    if weeks < 1:
        raise ValueError("el horizonte debe ser de al menos 1 semana")
    return weeks


@dataclass
class ForecastResult:
    code: str
    name: str
    history: pd.DataFrame  # weekly: timestamp, count
    backtest_weeks: int  # length of each backtest window
    backtest: pd.DataFrame  # one row per model, averaged over windows
    best: str
    backtest_pred: pd.DataFrame  # best model on the most recent window
    forecast: pd.DataFrame  # timestamp, q50, q80, q90, q95
    horizon_weeks: int
    source: str = SOURCE_LIVE
    backtest_origins: int = 1
    coverage80: tuple[int, int] = (0, 0)  # best model: weeks at/below P80, total weeks
    skipped: dict[str, str] = field(default_factory=dict)  # model -> error
    # Factor applied to each upper band (q - q50) after calibration; 1.0 = unchanged.
    interval_scale: dict[str, float] = field(default_factory=dict)
    select_by: str = DEFAULT_CRITERION  # score column, or the name of the function used

    @property
    def backtest_actual(self) -> pd.DataFrame:
        return self.history.iloc[-self.backtest_weeks :].reset_index(drop=True)


def min_weeks_needed(horizon_weeks: int) -> int:
    return min(horizon_weeks, MAX_BACKTEST_WEEKS) + MIN_TRAIN_WEEKS


def choose_model(table: pd.DataFrame, select_by: Criterion = DEFAULT_CRITERION) -> str:
    """The model that ``select_by`` prefers in a backtest ``table`` (one row per model).

    A string is a column of the table, lower is better: ``"qloss_80"`` (default),
    ``"qloss_50"``, ``"qloss_90"``, ``"qloss_95"``, ``"qloss_mean"``, ``"wis"`` or ``"mae"``.
    Models with a missing score (``wis`` from a model without lower quantiles) are left out. A
    function receives the table, with ``coverage_80`` (share of weeks at or below the P80)
    besides the score columns, and returns a model name. Fix the criterion before looking
    at the results: choosing it afterwards finds a winner by chance.
    """
    if callable(select_by):
        best = select_by(table)
        if best not in table.index:
            raise ValueError(f"el criterio devolvió {best!r}, que no está entre los modelos")
        return str(best)
    if select_by not in table.columns:
        raise ValueError(
            f"criterio desconocido: {select_by!r}; usa uno de {', '.join(CRITERIA)} "
            "o una función que reciba la tabla del backtest"
        )
    if table[select_by].isna().all():
        raise ValueError(
            f"ningún modelo tiene {criterion_label(select_by)}"
            + (": el WIS necesita los cuantiles q5, q10 y q20" if select_by == "wis" else "")
        )
    return str(table[select_by].idxmin())


def criterion_name(select_by: Criterion) -> str:
    """How a criterion is reported: its Spanish label, or the function's name."""
    if callable(select_by):
        return getattr(select_by, "__name__", "criterio propio")
    return criterion_label(select_by)


def run_forecast(
    history: pd.DataFrame,
    horizon_weeks: int,
    *,
    code: str = "",
    name: str = "",
    models: dict[str, Callable[[], Forecaster]] | None = None,
    source: str = SOURCE_LIVE,
    origins: int = BACKTEST_ORIGINS,
    step: int = BACKTEST_STEP,
    calibrate: bool = True,
    select_by: Criterion = DEFAULT_CRITERION,
    quantiles: tuple[float, ...] | None = None,
) -> ForecastResult:
    """Rolling backtest of ``models``, then forecast with the best one.

    Each backtest window is as long as the horizon (capped at 26 weeks). Up to
    ``origins`` windows are used, ``step`` weeks apart, so the choice does not
    hinge on a single season; fewer are used when history is short. The best
    model is the one ``select_by`` prefers (:func:`choose_model`); by default the
    lowest mean P80 quantile loss across windows. A model that fails to fit is
    skipped and reported in ``skipped``.

    ``quantiles`` are the ones the backtest scores and the forecast returns: by default
    q50, q80, q90 and q95, plus q5, q10 and q20 when ``select_by="wis"``.

    With ``calibrate=True`` the forward intervals are widened by
    :func:`calibration_factors`, computed from the chosen model's backtest
    errors. The reported backtest coverage is always the raw, uncalibrated one.
    """
    models = models or default_models()
    qs = tuple(quantiles) if quantiles else quantiles_for(select_by)
    bt = min(horizon_weeks, MAX_BACKTEST_WEEKS)
    n = len(history)
    if n < bt + MIN_TRAIN_WEEKS:
        raise NoDataError(
            f"{name or code}: se necesitan al menos {bt + MIN_TRAIN_WEEKS} "
            f"semanas completas y hay {n}."
        )
    run = backtest(
        history, models, bt, max(1, origins), step, MIN_TRAIN_WEEKS, qs, stop_failed=True
    )
    skipped = run.failed
    for model_name, err in skipped.items():
        logger.warning("%s: se omite (%s)", model_name, err[:80])
    scores = run.scores()
    scores = scores[~scores["model"].isin(skipped)] if not scores.empty else scores
    if scores.empty:
        raise NoDataError(f"{name or code}: ningún modelo pudo ajustarse.")
    sums = scores.groupby("model")[["covered", "n"]].sum()
    table = scores.drop(columns=["origin", "covered", "n"]).groupby("model").mean()
    table["coverage_80"] = sums["covered"] / sums["n"]
    best = choose_model(table, select_by)
    table = table.dropna(axis=1, how="all")  # e.g. wis when no lower quantiles were asked for

    fc = models[best]()
    fc.fit(history, "count")
    forward = fc.predict(HorizonSpec(grain=GRAIN, length=horizon_weeks, quantiles=qs))
    scale: dict[str, float] = {}
    if calibrate:
        pairs = run.pairs(best)
        given = tuple(q for q in qs if f"q{int(round(q * 100))}" in forward.columns)
        scale = calibration_factors([a for a, _ in pairs], [p for _, p in pairs], given)
        forward = apply_calibration(forward, scale)

    return ForecastResult(
        code=code,
        name=name or code,
        history=history,
        backtest_weeks=bt,
        backtest=table,
        best=best,
        backtest_pred=run.windows[0].preds[best],
        forecast=forward,
        horizon_weeks=horizon_weeks,
        source=source,
        backtest_origins=len(run.windows),
        coverage80=(int(sums.loc[best, "covered"]), int(sums.loc[best, "n"])),
        skipped=skipped,
        interval_scale=scale,
        select_by=select_by if isinstance(select_by, str) else criterion_name(select_by),
    )


__all__ = [
    "BACKTEST_ORIGINS",
    "BACKTEST_STEP",
    "Criterion",
    "choose_model",
    "criterion_name",
    "ForecastResult",
    "MAX_BACKTEST_WEEKS",
    "min_weeks_needed",
    "parse_horizon",
    "run_forecast",
]
