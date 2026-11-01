"""Regressor sources, the weekly calendar, and calendar variables known in advance."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from urgencias_core.features.calendar import weekly_calendar
from urgencias_core.models.exogenous import HarmonicExogenous
from urgencias_core.models.harmonic import HarmonicRegression, holidays_per_week
from urgencias_core.models.protocol import HorizonSpec
from urgencias_core.models.registry import resolve_models
from urgencias_core.regressors import Regressor, available_regressors, calendar, flunet


def _history(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range("2022-01-10", periods=n, freq="W-MON")
    t = np.arange(n)
    y = 900 + 120 * np.sin(2 * np.pi * t / 52.18) + np.random.default_rng(3).normal(0, 15, n)
    y -= 60 * holidays_per_week(ts)  # fewer visits in holiday weeks
    return pd.DataFrame({"timestamp": ts, "count": y})


def test_weekly_calendar_rows_are_deis_weeks() -> None:
    wc = weekly_calendar("2025-01-01", "2025-12-31")
    assert (wc["timestamp"].dt.dayofweek == 0).all()
    assert wc["timestamp"].diff().dropna().eq(pd.Timedelta(weeks=1)).all()
    np.testing.assert_array_equal(wc["holidays"], holidays_per_week(wc["timestamp"]))
    assert wc["school_holiday"].between(0, 1).all()
    fiestas = wc.set_index("timestamp").loc["2025-09-22"]  # week of 16-22 Sep 2025
    assert fiestas["holidays"] == 2 and fiestas["school_holiday"] > 0.5


def test_regressor_sources() -> None:
    assert set(available_regressors()) == {"flunet", "calendario"}
    cal = calendar()
    assert cal.known_future and cal.report_delay_weeks == 0
    assert cal.table()["timestamp"].max().year >= pd.Timestamp.today().year + 2
    fl = flunet()
    assert not fl.known_future and fl.report_delay_weeks == 2 and fl.columns == ("flu", "rsv")
    bad = Regressor("x", lambda: pd.DataFrame({"timestamp": []}), ("y",))
    with pytest.raises(ValueError, match="lacks columns"):
        bad.table()


def test_known_future_uses_future_values() -> None:
    hist = _history()
    origin = hist["timestamp"].iloc[-1]
    cal = calendar()
    table = cal.table()
    changed = table.copy()
    changed.loc[changed["timestamp"] > origin, "holidays"] += 3  # the (known) future differs
    h = HorizonSpec(grain="W-MON", length=8)
    preds = []
    for t in (table, changed):
        m = HarmonicExogenous(t, ["holidays"], known_future=True)
        m.fit(hist, "count")
        preds.append(m.predict(h))
    assert not np.allclose(preds[0]["q50"], preds[1]["q50"])
    with pytest.raises(ValueError, match="known future"):
        HarmonicExogenous(table, ["holidays"], report_delay_weeks=1, known_future=True)


def test_from_regressor_takes_the_source_rules() -> None:
    m = HarmonicExogenous.from_regressor(flunet(), lag_weeks=1, future="forecast")
    assert m.report_delay_weeks == 2 and not m.known_future and m.columns == ("flu", "rsv")
    c = HarmonicExogenous.from_regressor(calendar(), ["holidays"])
    assert c.known_future and c.columns == ("holidays",)


def test_feriados_through_the_calendar_matches_the_original() -> None:
    hist = _history()
    h = HorizonSpec(grain="W-MON", length=6)
    new = resolve_models(["ArmonicoFeriados"])["ArmónicoFeriados"]()
    old = HarmonicRegression(holidays=True)
    for m in (new, old):
        m.fit(hist, "count")
    pd.testing.assert_frame_equal(new.predict(h), old.predict(h))
    cal = resolve_models(["ArmonicoCalendario"])["ArmónicoCalendario"]()
    cal.fit(hist, "count")
    assert len(cal.predict(h)) == 6
