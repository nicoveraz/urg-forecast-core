"""Tests for demo helpers that carry real methodological weight.

`_to_weekly` must trim partial weeks at the series edges. DEIS is near-real-time,
so the latest week is often under-counted (reporting lag or a missing day); if
kept, it shows up as a spurious drop that contaminates the backtest.
"""

from __future__ import annotations

import pandas as pd

from urgencias_core.demos.deis import _to_weekly


def _daily(start: str, periods: int, value: int = 100) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"timestamp": dates, "count": value})


def test_to_weekly_keeps_only_complete_weeks() -> None:
    # 2024-01-02 is a Tuesday: four clean W-MON weeks (each ends on a Monday).
    weekly = _to_weekly(_daily("2024-01-02", 28))
    assert len(weekly) == 4
    assert (weekly["count"] == 700).all()  # 7 days * 100


def test_to_weekly_drops_trailing_incomplete_week() -> None:
    # Drop the final day so the last W-MON bin has 6 of 7 days: it must be trimmed
    # rather than reported as a low week.
    daily = _daily("2024-01-02", 28).iloc[:-1]
    weekly = _to_weekly(daily)
    assert len(weekly) == 3
    assert (weekly["count"] == 700).all()
    assert weekly["timestamp"].max() == pd.Timestamp("2024-01-22")


def test_to_weekly_drops_leading_incomplete_week() -> None:
    # Start mid-week (2024-01-04 is a Thursday): the first W-MON bin is partial.
    daily = _daily("2024-01-04", 26)  # partial first week, then full weeks
    weekly = _to_weekly(daily)
    assert (weekly["count"] == 700).all()
    assert weekly["timestamp"].min() == pd.Timestamp("2024-01-15")


def test_to_weekly_keeps_internal_low_week_to_preserve_spacing() -> None:
    # A missing day in an INTERNAL week must not be dropped (that would break the
    # regular weekly frequency); only edge weeks are trimmed.
    daily = _daily("2024-01-02", 28)
    daily = daily[daily["timestamp"] != pd.Timestamp("2024-01-10")]  # drop one mid day
    weekly = _to_weekly(daily)
    assert len(weekly) == 4  # nothing trimmed; still four contiguous weeks
    assert weekly["count"].iloc[1] == 600  # the internal week is low (6 days), kept


def test_to_weekly_empty_when_no_complete_week() -> None:
    weekly = _to_weekly(_daily("2024-01-04", 3))  # only a few days, no full week
    assert weekly.empty
