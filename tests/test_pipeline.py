"""Pipeline behaviour: horizon parsing, weekly aggregation, backtest + forecast."""

from __future__ import annotations

import pandas as pd
import pytest

from urgencias_core.eval.baselines import SeasonalNaiveBaseline
from urgencias_core.pipeline import (
    NoDataError,
    facility_name,
    load_deis,
    parse_horizon,
    run_forecast,
    to_weekly,
    weekly_series,
)


@pytest.mark.parametrize(
    ("text", "weeks"), [("12", 12), ("12s", 12), (" 4S ", 4), ("6m", 26), ("1m", 4), (8, 8)]
)
def test_parse_horizon(text, weeks) -> None:
    assert parse_horizon(text) == weeks


@pytest.mark.parametrize("text", ["0", "abc", "6 meses", "-3", ""])
def test_parse_horizon_rejects(text) -> None:
    with pytest.raises(ValueError):
        parse_horizon(text)


# --- to_weekly: DEIS is near-real-time, so partial edge weeks must be trimmed ---


def _daily(start: str, periods: int, value: int = 100) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"timestamp": dates, "count": value})


def test_to_weekly_keeps_only_complete_weeks() -> None:
    weekly = to_weekly(_daily("2024-01-02", 28))  # Tuesday start: four W-MON weeks
    assert len(weekly) == 4
    assert (weekly["count"] == 700).all()


def test_to_weekly_drops_trailing_incomplete_week() -> None:
    weekly = to_weekly(_daily("2024-01-02", 28).iloc[:-1])
    assert len(weekly) == 3
    assert weekly["timestamp"].max() == pd.Timestamp("2024-01-22")


def test_to_weekly_drops_leading_incomplete_week() -> None:
    weekly = to_weekly(_daily("2024-01-04", 26))
    assert (weekly["count"] == 700).all()
    assert weekly["timestamp"].min() == pd.Timestamp("2024-01-15")


def test_to_weekly_keeps_internal_low_week_to_preserve_spacing() -> None:
    daily = _daily("2024-01-02", 28)
    daily = daily[daily["timestamp"] != pd.Timestamp("2024-01-10")]
    weekly = to_weekly(daily)
    assert len(weekly) == 4
    assert weekly["count"].iloc[1] == 600


def test_to_weekly_empty_when_no_complete_week() -> None:
    assert to_weekly(_daily("2024-01-04", 3)).empty


# --- offline snapshot end to end ---


def test_load_deis_offline_accepts_both_code_formats() -> None:
    a = load_deis(["24-115"], offline=True)
    b = load_deis(["124115"], offline=True)
    assert len(a) == len(b) > 0
    assert not a["year"].isin([2020, 2021]).any()
    assert facility_name(a, "124115") == "Hospital de Frutillar"


def test_load_deis_offline_rejects_unknown_facility() -> None:
    with pytest.raises(NoDataError, match="snapshot offline"):
        load_deis(["09-999"], offline=True)


def test_run_forecast_on_snapshot() -> None:
    df = load_deis(["24-115"], offline=True)
    result = run_forecast(weekly_series(df, "24-115"), 8, code="24-115", name="Frutillar")
    assert result.backtest_weeks == 8
    assert len(result.forecast) == 8
    assert {"q50", "q80", "q90", "q95"} <= set(result.forecast.columns)
    assert (result.forecast["q95"] >= result.forecast["q50"]).all()
    assert set(result.backtest.index) == {"SeasonalNaive", "AutoARIMA", "Armónico", "MSTL"}
    assert result.backtest_origins == 3
    covered, total = result.coverage80
    assert total == 3 * 8 and 0 <= covered <= total
    assert result.best == result.backtest["qloss_80"].idxmin()
    assert len(result.backtest_pred) == 8


def test_backtest_window_is_capped() -> None:
    df = load_deis(["24-115"], offline=True)
    fast = {"SeasonalNaive": SeasonalNaiveBaseline}  # keep this test quick
    result = run_forecast(weekly_series(df, "24-115"), 40, models=fast)
    assert result.backtest_weeks == 26
    assert len(result.forecast) == 40


def test_run_forecast_needs_enough_history() -> None:
    df = load_deis(["24-115"], offline=True)
    short = weekly_series(df, "24-115").tail(30)
    with pytest.raises(NoDataError, match="semanas completas"):
        run_forecast(short, 12)


def test_fallback_to_snapshot_when_deis_unreachable(monkeypatch) -> None:
    import urgencias_core.pipeline as pl

    monkeypatch.setattr(pl, "deis_reachable", lambda: False)
    df = pl.load_deis(["24-105"], fallback_to_snapshot=True)
    assert len(df) > 0
    assert df.attrs["source"] == pl.SOURCE_SNAPSHOT


def test_fallback_when_live_fetch_is_empty(monkeypatch) -> None:
    import urgencias_core.pipeline as pl

    monkeypatch.setattr(pl, "deis_reachable", lambda: True)
    monkeypatch.setattr(pl, "fetch", lambda **kw: pd.DataFrame())
    df = pl.load_deis(["24-105"], fallback_to_snapshot=True)
    assert df.attrs["source"] == pl.SOURCE_SNAPSHOT
    with pytest.raises(pl.NoDataError, match="No hay datos DEIS"):
        pl.load_deis(["24-105"])


def test_facility_name_uses_most_recent_name() -> None:
    df = pd.DataFrame(
        {
            "facility_code": ["23-100", "123100"],
            "facility_name": ["Hospital Base de Osorno", "Hospital Base San José de Osorno"],
            "date": pd.to_datetime(["2022-01-01", "2026-01-01"]),
        }
    )
    assert facility_name(df, "23-100") == "Hospital Base San José de Osorno"


def test_rolling_origins_shrink_with_short_history() -> None:
    df = load_deis(["24-115"], offline=True)
    weekly = weekly_series(df, "24-115").tail(104 + 12 + 4)
    result = run_forecast(weekly, 12)
    assert result.backtest_origins == 1


def test_failing_model_is_skipped() -> None:
    from urgencias_core.pipeline import default_models

    class Broken:
        def fit(self, history, target_col):
            raise ValueError("boom")

        def predict(self, horizon):  # pragma: no cover
            raise AssertionError

    df = load_deis(["24-115"], offline=True)
    models = default_models() | {"Broken": Broken}
    result = run_forecast(weekly_series(df, "24-115"), 4, models=models)
    assert "Broken" in result.skipped
    assert "Broken" not in result.backtest.index


def test_harmonic_regression_follows_annual_cycle() -> None:
    import numpy as np

    from urgencias_core.models.harmonic import HarmonicRegression
    from urgencias_core.models.protocol import HorizonSpec

    ts = pd.date_range("2020-01-06", periods=260, freq="W-MON")
    t = np.arange(260)
    y = (
        1000
        + 200 * np.sin(2 * np.pi * t / (365.25 / 7))
        + np.random.default_rng(0).normal(0, 10, 260)
    )
    hist = pd.DataFrame({"timestamp": ts[:208], "count": y[:208]})
    m = HarmonicRegression(k=2)
    m.fit(hist, "count")
    pred = m.predict(HorizonSpec(grain="W-MON", length=52))
    assert np.mean(np.abs(pred["q50"].to_numpy() - y[208:])) < 40
    assert (pred["q95"] >= pred["q50"]).all()
