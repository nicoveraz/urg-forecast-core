"""The rolling-origin backtest every evaluation in the package is built on.

Windows run backwards from the end of the history: window ``k`` trains on everything up
to ``n - length - k * step`` weeks and is scored on the next ``length`` weeks. Each model
is fitted from scratch on each window (``models`` holds factories), so no window sees
the future of another. A median ensemble given as ``partial(MedianEnsemble, members)``,
whose members are all in ``models``, is combined from their predictions instead of
fitting them again: the same result in a fraction of the time.

:func:`~urgencias_core.forecast.run_forecast` uses it to pick and calibrate a model and
:func:`~urgencias_core.eval.compare.compare_models` to test whether a change helps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import pandas as pd

from urgencias_core.data.series import GRAIN, SEASON_WEEKS
from urgencias_core.eval.metrics import QUANTILES, score
from urgencias_core.models.ensemble import MedianEnsemble, median_of
from urgencias_core.models.protocol import Forecaster, HorizonSpec

MIN_TRAIN_WEEKS = 2 * SEASON_WEEKS  # MSTL needs two full seasons


def window_cuts(
    n: int, length: int, origins: int, step: int, min_train_weeks: int = MIN_TRAIN_WEEKS
) -> list[int]:
    """Training lengths of the backtest windows, most recent first.

    At most ``origins`` windows, ``step`` weeks apart, each leaving at least
    ``min_train_weeks`` for training.
    """
    cuts = []
    for k in range(origins):
        cut = n - length - k * step
        if cut < min_train_weeks:
            break
        cuts.append(cut)
    return cuts


@dataclass
class Window:
    """One backtest window: what each model predicted and what happened."""

    origin: pd.Timestamp  # last training week
    actual: pd.DataFrame  # timestamp + target for the scored weeks
    preds: dict[str, pd.DataFrame] = field(default_factory=dict)  # aligned to actual
    errors: dict[str, str] = field(default_factory=dict)  # model -> exception text


@dataclass
class Backtest:
    """Result of :func:`backtest`: the windows, most recent first."""

    windows: list[Window]
    length: int
    quantiles: tuple[float, ...] = QUANTILES
    target_col: str = "count"

    @property
    def failed(self) -> dict[str, str]:
        """First error of each model that failed in some window."""
        out: dict[str, str] = {}
        for w in self.windows:
            for m, e in w.errors.items():
                out.setdefault(m, e)
        return out

    def scores(self) -> pd.DataFrame:
        """One row per (window, model): ``origin``, ``model`` and :func:`score` columns."""
        rows = [
            {"origin": w.origin, "model": m, **score(w.actual, p, self.quantiles, self.target_col)}
            for w in self.windows
            for m, p in w.preds.items()
        ]
        return pd.DataFrame(rows)

    def pairs(self, model: str) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
        """``(actual, prediction)`` for each window where ``model`` produced one."""
        return [(w.actual, w.preds[model]) for w in self.windows if model in w.preds]


def _members_in(factory: Callable[[], Forecaster], models: dict) -> tuple[str, ...]:
    """Member names if ``factory`` is ``partial(MedianEnsemble, members)`` of models in
    ``models``: the very same factories, not just the same names."""
    if not (isinstance(factory, partial) and factory.func is MedianEnsemble and factory.args):
        return ()
    members = factory.args[0]
    if all(models.get(name) is f for name, f in members.items()):
        return tuple(members)
    return ()


def backtest(
    history: pd.DataFrame,
    models: dict[str, Callable[[], Forecaster]],
    length: int,
    origins: int,
    step: int,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
    quantiles: tuple[float, ...] = QUANTILES,
    target_col: str = "count",
    stop_failed: bool = False,
) -> Backtest:
    """Fit every model on every rolling window of ``history`` and keep its predictions.

    A model that raises on a window is recorded in that window's ``errors``. With
    ``stop_failed=True`` it is not fitted again on later (older) windows.
    """
    spec = HorizonSpec(grain=GRAIN, length=length, quantiles=quantiles)
    n = len(history)
    dead: set[str] = set()
    combined = {name: m for name, f in models.items() if (m := _members_in(f, models))}
    windows = []
    for cut in window_cuts(n, length, origins, step, min_train_weeks):
        train = history.iloc[:cut].reset_index(drop=True)
        actual = history.iloc[cut : cut + length].reset_index(drop=True)
        w = Window(origin=pd.Timestamp(train["timestamp"].iloc[-1]), actual=actual)
        for name, factory in models.items():
            if name in dead or name in combined:
                continue
            try:
                fc = factory()
                fc.fit(train, target_col)
                pred = fc.predict(spec).reset_index(drop=True)
            except Exception as exc:  # noqa: BLE001 - one bad model must not sink the run
                w.errors[name] = str(exc)
                if stop_failed:
                    dead.add(name)
                continue
            # statsforecast can offset weekly stamps slightly; align to actual weeks.
            pred["timestamp"] = actual["timestamp"].to_numpy()[: len(pred)]
            w.preds[name] = pred
        for name, members in combined.items():  # as MedianEnsemble: drop failed members
            got = [w.preds[m] for m in members if m in w.preds]
            if got:
                w.preds[name] = median_of(got, list(spec.quantile_columns))
            else:
                w.errors[name] = "MedianEnsemble: no member could be fitted"
        windows.append(w)
    return Backtest(windows, length, tuple(quantiles), target_col)


__all__ = ["MIN_TRAIN_WEEKS", "Backtest", "Window", "backtest", "window_cuts"]
