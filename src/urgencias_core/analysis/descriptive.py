"""Descriptive analysis of weekly ED attendances: what demand looks like, before forecasting.

Every function takes the weekly series from :func:`~urgencias_core.data.series.weekly_series`
(``timestamp`` = the Monday closing each DEIS week, ``count``) and returns a DataFrame. They
are pure: no I/O, no plotting (see :func:`urgencias_core.report.analysis_figure`).

- :func:`yearly_summary` — one row per year: total, weekly mean, change, peak.
- :func:`seasonal_profile` — the typical year: mean and range for each week of the year.
- :func:`level` — the 52-week rolling mean (the level without the seasonal cycle).
- :func:`year_over_year` — each week against the same week a year earlier.
- :func:`peak_weeks` — the busiest weeks and how far above their year they were.
- :func:`weekday_profile` — share of attendances by day of the week (needs daily data).

Years with gaps (2020-2021 are excluded on load) simply have no rows; comparisons against a
missing year come out as NaN instead of being filled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
FULL_YEAR_WEEKS = 52


def _prep(weekly: pd.DataFrame) -> pd.DataFrame:
    if not {"timestamp", "count"} <= set(weekly.columns):
        raise ValueError("expected a weekly series with columns timestamp, count")
    w = weekly[["timestamp", "count"]].copy()
    w["timestamp"] = pd.to_datetime(w["timestamp"])
    w["count"] = w["count"].astype(float)
    return w.sort_values("timestamp").reset_index(drop=True)


def yearly_summary(weekly: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar year of the week-ending date.

    Columns: ``weeks``, ``complete`` (at least 52 weeks), ``total``, ``weekly_mean``,
    ``change_pct``, ``peak_week`` (date of the busiest week), ``peak`` and ``peak_ratio``
    (peak over that year's median week).

    ``change_pct`` compares the year with the previous one over the **same weeks of the
    year** (ISO week of the closing Monday), so a partial year such as January-March is
    compared with January-March, not with a whole year. NaN when the previous year is
    missing. Totals of incomplete years are not comparable; weekly means and changes are.
    """
    w = _prep(weekly)
    w["year"] = w["timestamp"].dt.year
    w["week"] = w["timestamp"].dt.isocalendar().week.astype(int)
    g = w.groupby("year")
    out = pd.DataFrame(
        {
            "weeks": g.size(),
            "total": g["count"].sum(),
            "weekly_mean": g["count"].mean(),
            "peak_week": w.loc[g["count"].idxmax()].set_index("year")["timestamp"],
            "peak": g["count"].max(),
            "peak_ratio": g["count"].max() / g["count"].median(),
        }
    )
    by_week = w.pivot_table(index="year", columns="week", values="count")
    change = {}
    for year in out.index:
        if year - 1 not in by_week.index:
            change[year] = np.nan
            continue
        both = by_week.loc[[year, year - 1]].dropna(axis=1)
        change[year] = 100 * (both.loc[year].mean() / both.loc[year - 1].mean() - 1)
    out["change_pct"] = pd.Series(change)
    out["complete"] = out["weeks"] >= FULL_YEAR_WEEKS
    cols = ["weeks", "complete", "total", "weekly_mean", "change_pct", "peak_week", "peak"]
    return out[cols + ["peak_ratio"]]


def seasonal_profile(weekly: pd.DataFrame, years: int | None = None) -> pd.DataFrame:
    """The typical year: one row per week of the year (1 to 53).

    ``week`` is the ISO week of the Monday that closes each DEIS week, so week 17 is the
    DEIS week ending on the Monday of ISO week 17 (around 20-26 April).

    - ``mean``, ``low``, ``high``: attendances in that week across years (raw counts).
    - ``index``: how far that week sits from the level of its own year, averaged over the
      years: each week is divided by the centred 53-week mean around it, so growth from
      one year to the next does not leak into the seasonal shape. 1.15 means 15% above
      the level. Weeks within half a year of either end of the series have no centred
      mean and do not count towards ``index``.
    - ``years``: how many years contribute to ``mean``. With the ``years`` argument, only
      the last ``years`` years are used.
    """
    w = _prep(weekly)
    if years is not None:
        w = w[w["timestamp"] > w["timestamp"].iloc[-1] - pd.DateOffset(years=years)]
    full = w.set_index("timestamp")["count"].asfreq("W-MON")
    centred = full.rolling(53, center=True, min_periods=53).mean()
    w["ratio"] = (full / centred).reindex(w["timestamp"]).to_numpy()
    w["week"] = w["timestamp"].dt.isocalendar().week.astype(int)
    g = w.groupby("week")
    out = pd.DataFrame(
        {
            "mean": g["count"].mean(),
            "low": g["count"].min(),
            "high": g["count"].max(),
            "years": g.size(),
            "index": g["ratio"].mean(),
        }
    )
    out.index.name = "week"
    return out


def level(weekly: pd.DataFrame, window: int = FULL_YEAR_WEEKS) -> pd.DataFrame:
    """The series with its ``level``: the mean of the last ``window`` weeks.

    A 52-week mean averages out the seasonal cycle, so it shows whether demand is growing.
    ``level`` is NaN until ``window`` consecutive weeks exist (a gap restarts it).
    ``change_pct`` compares the level with the one 52 weeks earlier.
    """
    w = _prep(weekly).set_index("timestamp")
    full = w["count"].asfreq("W-MON")  # gaps become NaN, so the rolling mean stops at them
    lvl = full.rolling(window, min_periods=window).mean()
    out = pd.DataFrame({"count": full, "level": lvl})
    out["change_pct"] = 100 * (out["level"] / out["level"].shift(FULL_YEAR_WEEKS) - 1)
    out = out[out["count"].notna()]
    return out.reset_index()


def year_over_year(weekly: pd.DataFrame, smooth: int = 4) -> pd.DataFrame:
    """Each week against the same week one year earlier (52 weeks back).

    ``change_pct`` uses sums over the last ``smooth`` weeks on both sides (4 by default),
    which removes most of the week-to-week noise. NaN when the earlier weeks are missing.
    """
    w = _prep(weekly).set_index("timestamp")
    full = w["count"].asfreq("W-MON")
    recent = full.rolling(smooth, min_periods=smooth).sum()
    before = recent.shift(FULL_YEAR_WEEKS)
    out = pd.DataFrame(
        {
            "count": full,
            "last_year": full.shift(FULL_YEAR_WEEKS),
            "change_pct": 100 * (recent / before - 1),
        }
    )
    return out[out["count"].notna()].reset_index()


def peak_weeks(weekly: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """The ``top`` busiest weeks, with ``ratio`` against the median week of their year."""
    w = _prep(weekly)
    w["year"] = w["timestamp"].dt.year
    w["ratio"] = w["count"] / w.groupby("year")["count"].transform("median")
    w["week"] = w["timestamp"].dt.isocalendar().week.astype(int)
    return w.nlargest(top, "count")[["timestamp", "count", "year", "week", "ratio"]].reset_index(
        drop=True
    )


def weekday_profile(daily: pd.DataFrame) -> pd.DataFrame:
    """Share of attendances by day of the week, from daily totals (``timestamp, count``).

    Get them with :func:`urgencias_core.data.series.daily_series`. ``mean`` is the average
    count on that weekday and ``index`` its ratio to the average day.
    """
    d = _prep(daily)
    d["weekday"] = d["timestamp"].dt.dayofweek
    g = d.groupby("weekday")["count"]
    out = pd.DataFrame({"mean": g.mean(), "days": g.size()})
    out["index"] = out["mean"] / out["mean"].mean()
    out.insert(0, "name", [WEEKDAYS_ES[i] for i in out.index])
    return out


def summary(weekly: pd.DataFrame) -> dict:
    """A few headline numbers for a report: span, last level and its yearly change,
    seasonal amplitude (``index`` of the busiest typical week over the quietest) and the
    usual peak week."""
    w = _prep(weekly)
    lv = level(w)
    prof = seasonal_profile(w)
    last = lv.dropna(subset=["level"]).tail(1)
    return {
        "first_week": w["timestamp"].iloc[0],
        "last_week": w["timestamp"].iloc[-1],
        "weeks": len(w),
        "weekly_mean_last_year": float(w["count"].tail(FULL_YEAR_WEEKS).mean()),
        "level_change_pct": float(last["change_pct"].iloc[0]) if len(last) else np.nan,
        "seasonal_amplitude": float(prof["index"].max() / prof["index"].min()),
        "usual_peak_week": int(prof["index"].idxmax()),
        "usual_low_week": int(prof["index"].idxmin()),
    }


__all__ = [
    "level",
    "peak_weeks",
    "seasonal_profile",
    "summary",
    "weekday_profile",
    "year_over_year",
    "yearly_summary",
]
