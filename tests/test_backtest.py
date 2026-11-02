"""The rolling backtest engine and the aliases for paths that moved in 0.4."""

from __future__ import annotations

import importlib
import warnings

import numpy as np
import pandas as pd
import pytest

from urgencias_core.eval.backtest import backtest, window_cuts
from urgencias_core.eval.compare import compare_many, compare_scores
from urgencias_core.eval.metrics import WIS_QUANTILES, score, weighted_interval_score
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


def test_backtest_combines_an_ensemble_of_its_own_models() -> None:
    from functools import partial

    from urgencias_core.models.ensemble import MedianEnsemble

    h = _history()
    calls = {"n": 0}

    def harmonic() -> HarmonicRegression:
        calls["n"] += 1
        return HarmonicRegression()

    members = {"SN": SeasonalNaiveBaseline, "H": harmonic, "X": _Boom}
    models = members | {"E": partial(MedianEnsemble, members)}
    run = backtest(h, models, 4, 3, 8, min_train_weeks=104, quantiles=WIS_QUANTILES)
    assert calls["n"] == 3  # the ensemble did not fit its members again
    alone = backtest(
        h,
        {"E": partial(MedianEnsemble, members)},
        4,
        3,
        8,
        min_train_weeks=104,
        quantiles=WIS_QUANTILES,
    )  # fitted as usual: the members are not there
    assert calls["n"] == 6
    cols = ["q5", "q10", "q20", "q50", "q80", "q90", "q95"]
    for a, b in zip(run.windows, alone.windows, strict=True):
        assert np.allclose(a.preds["E"][cols].to_numpy(), b.preds["E"][cols].to_numpy())
        assert "X" in a.errors and "E" not in a.errors  # a failed member is dropped
    # same names but other factories: not combined, fitted as usual
    other = {"SN": SeasonalNaiveBaseline, "H": HarmonicRegression}
    backtest(h, other | {"E": partial(MedianEnsemble, members)}, 4, 1, 8, min_train_weeks=104)
    assert calls["n"] == 7


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
    by_mae = compare_scores(run.scores(), "H", ["N"], 4, metric="mae")["N"]
    mae = run.scores().pivot(index="origin", columns="model", values="mae")
    assert by_mae.metric == "mae" and "MAE" in by_mae.text()
    assert by_mae.windows["base"].tolist() == mae.sort_index()["H"].tolist()
    with pytest.raises(ValueError, match="métrica desconocida"):
        compare_scores(run.scores(), "H", ["N"], 4, metric="p80")


def test_qloss_mean_averages_the_quantile_losses() -> None:
    actual = pd.DataFrame({"count": [100.0, 120.0, 90.0, 110.0]})
    s = score(actual, _pred([95, 95, 95, 95], [110, 110, 110, 110]))
    parts = [s["qloss_50"], s["qloss_80"], s["qloss_90"], s["qloss_95"]]
    assert s["qloss_mean"] == pytest.approx(sum(parts) / 4)


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


def test_wis_matches_the_interval_score_formula() -> None:
    rng = np.random.default_rng(3)
    y = rng.normal(100, 15, 12)
    m = np.full(12, 100.0)
    cols = {"q50": m}
    for alpha, half in ((0.4, 8.0), (0.2, 15.0), (0.1, 20.0)):  # 60, 80, 90 % intervals
        lo, hi = round(100 * alpha / 2), round(100 * (1 - alpha / 2))
        cols[f"q{lo}"], cols[f"q{hi}"] = m - half, m + half
    pred = pd.DataFrame(cols)
    total = 0.5 * np.abs(y - m)
    for alpha in (0.4, 0.2, 0.1):
        lo = pred[f"q{round(100 * alpha / 2)}"].to_numpy()
        hi = pred[f"q{round(100 * (1 - alpha / 2))}"].to_numpy()
        interval = (hi - lo) + 2 / alpha * (lo - y) * (y < lo) + 2 / alpha * (y - hi) * (y > hi)
        total += alpha / 2 * interval
    expected = float(np.mean(total / (3 + 0.5)))  # Bracher et al. (2021), K = 3
    assert weighted_interval_score(y, pred) == pytest.approx(expected)
    s = score(pd.DataFrame({"count": y}), pred, WIS_QUANTILES)
    assert s["wis"] == pytest.approx(expected)
    assert s["qloss_mean"] == pytest.approx(
        np.mean([s["qloss_50"], s["qloss_80"], s["qloss_90"], s["qloss_95"]])
    )


def test_wis_is_missing_without_lower_quantiles() -> None:
    actual = pd.DataFrame({"count": [100.0, 120.0]})
    s = score(actual, _pred([95, 95], [110, 110]))
    assert np.isnan(s["wis"]) and not np.isnan(s["qloss_mean"])


def test_compare_on_wis_asks_the_models_for_lower_quantiles() -> None:
    h = _history()
    cmp = compare_many(
        h, ("H", HarmonicRegression), {"N": SeasonalNaiveBaseline}, 4, 4, 4, metric="wis"
    )["N"]
    assert cmp.metric == "wis" and cmp.n == 4
    assert cmp.windows[["base", "candidate"]].notna().all().all()
    assert "WIS" in cmp.text()
