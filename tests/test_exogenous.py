"""The generic external-regressor model and the paired comparison (synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from urgencias_core.eval.compare import compare_models, sign_test
from urgencias_core.models.exogenous import HarmonicExogenous, HarmonicFluNet
from urgencias_core.models.harmonic import HarmonicRegression
from urgencias_core.models.protocol import HorizonSpec

N = 260
TS = pd.date_range("2021-01-04", periods=N, freq="W-MON")


def _signal(seed: int = 1) -> np.ndarray:
    """A seasonal series with a random onset each year, like a viral season."""
    rng = np.random.default_rng(seed)
    t = np.arange(N + 60)
    shift = np.repeat(rng.integers(-6, 7, size=(N + 60) // 52 + 1), 52)[: N + 60]
    return np.clip(np.sin(2 * np.pi * (t - shift) / 52.18), 0, None) + rng.normal(0, 0.05, N + 60)


def _regressor() -> pd.DataFrame:
    ts = pd.date_range(TS[0] - pd.Timedelta(weeks=10), periods=N + 60, freq="W-MON")
    return pd.DataFrame({"timestamp": ts, "x": _signal()})


def _history(reg: pd.DataFrame, lag: int, beta: float) -> pd.DataFrame:
    x = reg.set_index("timestamp")["x"]
    driver = (TS - pd.Timedelta(weeks=lag)).map(x).to_numpy(dtype=float)
    noise = np.random.default_rng(0).normal(0, 10, N)
    return pd.DataFrame({"timestamp": TS, "count": 1000 + beta * driver + noise})


@pytest.mark.parametrize("future", ["climatology", "forecast"])
def test_never_uses_unpublished_weeks(future: str) -> None:
    reg = _regressor()
    hist = _history(reg, lag=1, beta=200)
    cutoff = hist["timestamp"].iloc[-1] - pd.Timedelta(weeks=2)
    tampered = reg.copy()
    tampered.loc[tampered["timestamp"] > cutoff, "x"] = 99.0
    lag = 1 if future == "forecast" else 2
    h = HorizonSpec(grain="W-MON", length=6)
    preds = []
    for r in (reg, tampered):
        m = HarmonicExogenous(r, ["x"], lag_weeks=lag, report_delay_weeks=2, future=future)
        m.fit(hist, "count")
        preds.append(m.predict(h))
    pd.testing.assert_frame_equal(*preds)


def test_projection_follows_the_current_season_and_stays_in_range() -> None:
    reg = _regressor()
    hist = _history(reg, lag=0, beta=200)
    m = HarmonicExogenous(reg, ["x"], lag_weeks=0, report_delay_weeks=2, future="forecast")
    m.fit(hist, "count")
    path = m.regressor_path(HorizonSpec(grain="W-MON", length=8))
    assert len(path) == 8 and path["x"].notna().all()
    assert path["x"].between(reg["x"].min(), reg["x"].max()).all()


def test_climatology_needs_lag_at_least_delay_and_columns_must_exist() -> None:
    with pytest.raises(ValueError, match="future='forecast'"):
        HarmonicExogenous(_regressor(), ["x"], lag_weeks=1, report_delay_weeks=2)
    HarmonicExogenous(_regressor(), ["x"], lag_weeks=1, report_delay_weeks=2, future="forecast")
    with pytest.raises(ValueError, match="future must be"):
        HarmonicExogenous(_regressor(), ["x"], future="magic")
    m = HarmonicExogenous(_regressor(), ["y"])
    with pytest.raises(ValueError, match="lacks columns"):
        m.fit(_history(_regressor(), 0, 0), "count")


def test_flunet_is_an_instance_of_the_generic_model() -> None:
    assert issubclass(HarmonicFluNet, HarmonicExogenous)
    m = HarmonicFluNet(future="forecast", lag_weeks=1)
    assert m.columns == ("flu", "rsv") and m.report_delay_weeks == 2
    from urgencias_core.models.harmonic import HarmonicFluNet as old_path

    assert old_path is HarmonicFluNet


def test_sign_test() -> None:
    assert sign_test(0, 0) == 1.0
    assert sign_test(5, 10) == 1.0
    assert sign_test(10, 10) == pytest.approx(2 / 2**10)
    assert sign_test(2, 10) == sign_test(8, 10) == pytest.approx(2 * 56 / 1024)


def test_comparison_detects_an_informative_regressor() -> None:
    reg = _regressor()
    hist = _history(reg, lag=4, beta=300)  # the driver is fully published 4 weeks ahead
    cmp = compare_models(
        hist,
        ("Armónico", HarmonicRegression),
        ("ConX", lambda: HarmonicExogenous(reg, ["x"], lag_weeks=4)),
        horizon_weeks=4,
        origins=12,
        step=4,
        min_train_weeks=104,
    )
    assert cmp.n == 12
    assert cmp.verdict == "mejora"
    s = cmp.summary()
    assert list(s.index) == ["todas", "invierno", "resto"]
    assert s.loc["todas", "gana"] + s.loc["todas", "pierde"] <= 12
    assert "Veredicto: mejora" in cmp.text()
