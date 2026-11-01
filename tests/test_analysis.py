"""Descriptive analysis on synthetic weekly series with a known shape."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from urgencias_core.analysis import (
    level,
    peak_weeks,
    seasonal_profile,
    summary,
    weekday_profile,
    year_over_year,
    yearly_summary,
)
from urgencias_core.analysis.report import analysis_text, week_label, write_analysis


def _weekly(years: int = 4, growth: float = 0.10, amp: float = 0.2, start="2022-01-03"):
    """Weekly series: level growing ``growth`` per year, seasonal peak in ISO week ~17."""
    ts = pd.date_range(start, periods=52 * years, freq="W-MON")
    week = ts.isocalendar().week.to_numpy().astype(float)
    t = np.arange(len(ts)) / 52.0
    lvl = 1000 * (1 + growth) ** t
    season = 1 + amp * np.cos(2 * np.pi * (week - 17) / 52)
    return pd.DataFrame({"timestamp": ts, "count": lvl * season})


def test_seasonal_index_recovers_the_peak_without_the_trend() -> None:
    w = _weekly(growth=0.30)
    prof = seasonal_profile(w)
    assert prof["index"].idxmax() in (16, 17, 18)
    assert prof["index"].idxmin() in (42, 43, 44)
    # Detrended: the index is close to the true seasonal factor, despite 30%/year growth.
    assert prof.loc[17, "index"] == pytest.approx(1.2, abs=0.03)
    assert prof["index"].mean() == pytest.approx(1.0, abs=0.02)


def test_yearly_change_compares_the_same_weeks() -> None:
    w = _weekly(years=3, growth=0.10, amp=0.3)
    ys = yearly_summary(w)
    assert ys.loc[2023, "change_pct"] == pytest.approx(10, abs=1.5)
    assert np.isnan(ys.loc[2022, "change_pct"])
    assert ys["complete"].all()
    # A partial year is compared with the same weeks a year earlier, not the whole year.
    ys2 = yearly_summary(w.iloc[: 52 + 10])
    assert not ys2.loc[2023, "complete"]
    assert ys2.loc[2023, "change_pct"] == pytest.approx(10, abs=1.5)


def test_level_and_year_over_year() -> None:
    w = _weekly(years=3, growth=0.10)
    lv = level(w)
    assert lv["level"].iloc[:51].isna().all() and lv["level"].iloc[51:].notna().all()
    assert lv["change_pct"].dropna().iloc[-1] == pytest.approx(10, abs=0.5)
    yoy = year_over_year(w)
    assert yoy["change_pct"].dropna().median() == pytest.approx(10, abs=0.5)
    assert (yoy["last_year"].iloc[52:].to_numpy() == w["count"].iloc[:-52].to_numpy()).all()


def test_gaps_are_not_filled() -> None:
    w = _weekly(years=4)
    gap = w[(w["timestamp"].dt.year != 2023)]  # a missing year, like 2020-2021
    ys = yearly_summary(gap)
    assert 2023 not in ys.index and np.isnan(ys.loc[2024, "change_pct"])
    yoy = year_over_year(gap)
    assert yoy.loc[yoy["timestamp"].dt.year == 2024, "change_pct"].isna().all()


def test_peaks_weekday_and_summary() -> None:
    w = _weekly()
    pk = peak_weeks(w, 3)
    assert len(pk) == 3 and pk["count"].is_monotonic_decreasing
    days = pd.date_range("2024-01-01", periods=70, freq="D")
    daily = pd.DataFrame({"timestamp": days, "count": np.where(days.dayofweek == 0, 140, 100)})
    wd = weekday_profile(daily)
    assert wd.loc[0, "name"] == "lunes" and wd.loc[0, "index"] > wd.loc[3, "index"]
    s = summary(w)
    assert s["usual_peak_week"] in (16, 17, 18) and s["seasonal_amplitude"] > 1.3


def test_week_label() -> None:
    assert week_label(17) == "mediados de abril"
    assert week_label(1).endswith("diciembre")  # ISO week 1 of 2026 starts on 29 Dec 2025


def test_text_and_files(tmp_path) -> None:
    w = _weekly()
    text = analysis_text(w, "Hospital X", "99-999")
    for part in ("Nivel", "Estación", "Interanual", "Por año", "Año típico"):
        assert part in text
    paths = write_analysis(w, tmp_path, "Hospital X", "99-999")
    assert all(p.exists() for p in paths)
