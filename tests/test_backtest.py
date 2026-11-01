"""The rolling backtest engine and the aliases for paths that moved in 0.4."""

from __future__ import annotations

import importlib
import warnings

import numpy as np
import pandas as pd
import pytest

from urgencias_core.eval.backtest import backtest, window_cuts
from urgencias_core.eval.compare import compare_many, compare_scores
from urgencias_core.eval.metrics import score
from urgencias_core.models.baselines import SeasonalNaiveBaseline
from urgencias_core.models.harmonic import HarmonicRegression


def _history(n: int = 160) -> pd.DataFrame:
    ts = pd.date_range("2022-01-03", periods=n, freq="W-MON")
    t = np.arange(n)
    y = 500 + 80 * np.sin(2 * np.pi * t / 52.18) + np.random.default_rng(0).normal(0, 5, n)
    return pd.DataFrame({"timestamp": ts, "count": y})


def test_window_cuts_most_recent_first_and_respects_min_train() -> None:
    assert window_cuts(130, 4, 10, 8, min_train_weeks=104) == [126, 118, 110]
    assert window_cuts(100, 4, 3, 8, min_train_weeks=104) == []


class _Boom:
    def fit(self, history, target_col):
        raise RuntimeError("no fit")

    def predict(self, horizon):  # pragma: no cover - never reached
        raise AssertionError


def test_backtest_scores_each_window_and_records_failures() -> None:
    h = _history()
    calls = {"n": 0}

    def boom() -> _Boom:
        calls["n"] += 1
        return _Boom()

    run = backtest(h, {"H": HarmonicRegression, "X": boom}, 4, 3, 8, min_train_weeks=104)
    assert len(run.windows) == 3 and calls["n"] == 3
    w0 = run.windows[0]
    assert w0.origin == h["timestamp"].iloc[len(h) - 4 - 1]
    assert (w0.preds["H"]["timestamp"].to_numpy() == w0.actual["timestamp"].to_numpy()).all()
    assert "X" in run.failed and "X" not in w0.preds
    s = run.scores()
    assert set(s["model"]) == {"H"} and len(s) == 3
    assert {"origin", "mae", "mape", "qloss_80", "covered", "n"} <= set(s.columns)
    assert len(run.pairs("H")) == 3

    calls["n"] = 0
    backtest(h, {"X": boom}, 4, 3, 8, min_train_weeks=104, stop_failed=True)
    assert calls["n"] == 1


def _pred(q50: list[float], q80: list[float]) -> pd.DataFrame:
    q80a = np.array(q80, dtype=float)
    return pd.DataFrame({"q50": q50, "q80": q80a, "q90": q80a + 1, "q95": q80a + 2})


def test_p80_loss_splits_into_short_and_excess() -> None:
    actual = pd.DataFrame({"count": [100.0, 120.0, 90.0, 110.0]})
    s = score(actual, _pred([95, 95, 95, 95], [110, 110, 110, 110]))
    # 120 is 10 above the P80 (0.8 x 10); 100, 90 and 110 leave 10, 20 and 0 below (0.2 x ...)
    assert s["qloss_80_short"] == pytest.approx(0.8 * 10 / 4)
    assert s["qloss_80_excess"] == pytest.approx(0.2 * (10 + 20 + 0) / 4)
    assert s["qloss_80"] == pytest.approx(s["qloss_80_short"] + s["qloss_80_excess"])
    assert s["width_80"] == pytest.approx(15) and s["covered"] == 3


def test_narrower_band_is_worse_when_more_than_one_week_in_five_ends_above() -> None:
    actual = pd.DataFrame({"count": [100.0, 106.0, 98.0, 106.0, 101.0]})
    wide, narrow = _pred([95] * 5, [107] * 5), _pred([95] * 5, [103] * 5)
    sw, sn = score(actual, wide), score(actual, narrow)
    assert sn["width_80"] < sw["width_80"]
    assert sn["covered"] == 3  # 2 of 5 weeks above the narrow P80
    assert sn["qloss_80"] > sw["qloss_80"]


def test_compare_scores_matches_compare_many() -> None:
    h = _history()
    models = {"H": HarmonicRegression, "N": SeasonalNaiveBaseline}
    run = backtest(h, models, 4, 6, 4, min_train_weeks=104)
    a = compare_scores(run.scores(), "H", ["N"], 4)["N"]
    b = compare_many(h, ("H", HarmonicRegression), {"N": SeasonalNaiveBaseline}, 4, 6, 4)["N"]
    pd.testing.assert_frame_equal(a.windows, b.windows)
    with pytest.raises(ValueError):
        compare_scores(run.scores(), "H", ["H"], 4)


@pytest.mark.parametrize(
    ("old", "name", "new"),
    [
        ("urgencias_core.pipeline", "load_deis", "urgencias_core.data.series"),
        ("urgencias_core.pipeline", "run_forecast", "urgencias_core.forecast"),
        ("urgencias_core.pipeline", "resolve_models", "urgencias_core.models.registry"),
        ("urgencias_core.pipeline", "calibration_factors", "urgencias_core.eval.calibration"),
        ("urgencias_core.eval.baselines", "auto_arima", "urgencias_core.models.baselines"),
        ("urgencias_core.eval", "SeasonalNaiveBaseline", "urgencias_core.models.baselines"),
        ("urgencias_core", "run_harness", "urgencias_core.eval.harness"),
    ],
)
def test_old_import_paths_still_work_with_a_warning(old: str, name: str, new: str) -> None:
    module = importlib.import_module(old)
    with pytest.warns(DeprecationWarning, match="removed in 0.5"):
        obj = getattr(module, name)
    assert obj is getattr(importlib.import_module(new), name)


def test_new_paths_do_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        from urgencias_core import backtest, compare_models, load_deis, run_forecast  # noqa: F401
        from urgencias_core.models.registry import resolve_models  # noqa: F401


def test_unknown_name_on_old_module_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError):
        importlib.import_module("urgencias_core.pipeline").no_such_thing  # noqa: B018
