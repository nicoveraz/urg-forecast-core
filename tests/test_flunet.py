"""FluNet positivity and the HarmonicFluNet example model (synthetic FluNet rows only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from urgencias_core.data.flunet import weekly_positivity
from urgencias_core.models.exogenous import HarmonicFluNet
from urgencias_core.models.protocol import HorizonSpec


def _raw(starts: pd.DatetimeIndex) -> pd.DataFrame:
    """Synthetic FluNet rows: two sources per week, seasonal positivity."""
    rows = []
    for i, s in enumerate(starts):
        flu = 0.05 + 0.25 * max(0.0, np.sin(2 * np.pi * (s.dayofyear - 120) / 365.25))
        for src, n in (("SENTINEL", 100), ("NONSENTINEL", 400)):
            rows.append(
                {
                    "ISO_WEEKSTARTDATE": s.strftime("%Y-%m-%dT00:00:00Z"),
                    "ORIGIN_SOURCE": src,
                    "SPEC_PROCESSED_NB": n,
                    "INF_ALL": round(flu * n),
                    "RSV_PROCESSED": n if i % 50 else None,  # some missing denominators
                    "RSV": round(0.1 * n),
                }
            )
    return pd.DataFrame(rows)


STARTS = pd.date_range("2016-01-04", "2026-09-28", freq="W-MON")


def test_weekly_positivity_pools_sources_and_aligns_to_deis_weeks() -> None:
    raw = _raw(pd.DatetimeIndex(["2025-06-02", "2025-06-09"]))
    raw.loc[0, "INF_ALL"], raw.loc[1, "INF_ALL"] = 10, 40  # week 1: 50 / 500
    pos = weekly_positivity(raw)
    assert pos["timestamp"].iloc[0] == pd.Timestamp("2025-06-09")  # ISO Mon + 7 = DEIS label
    assert pos["flu"].iloc[0] == pytest.approx(50 / 500)
    assert pos["specimens"].iloc[0] == 500
    assert pos["rsv"].notna().all()


def _history(n: int = 260) -> pd.DataFrame:
    ts = pd.date_range("2021-01-04", periods=n, freq="W-MON")
    t = np.arange(n)
    y = (
        1000
        + 150 * np.sin(2 * np.pi * t / (365.25 / 7))
        + np.random.default_rng(0).normal(0, 20, n)
    )
    return pd.DataFrame({"timestamp": ts, "count": y})


def test_flunet_model_never_uses_unpublished_weeks() -> None:
    pos = weekly_positivity(_raw(STARTS))
    hist = _history()
    origin = hist["timestamp"].iloc[-1]
    cutoff = origin - pd.Timedelta(weeks=2)
    tampered = pos.copy()
    tampered.loc[tampered["timestamp"] > cutoff, ["flu", "rsv"]] = 0.99  # the "future"
    h = HorizonSpec(grain="W-MON", length=8)
    a, b = HarmonicFluNet(positivity=pos), HarmonicFluNet(positivity=tampered)
    a.fit(hist, "count")
    b.fit(hist, "count")
    pa, pb = a.predict(h), b.predict(h)
    pd.testing.assert_frame_equal(pa, pb)
    assert (pa["q95"] >= pa["q50"]).all()


def test_flunet_model_rejects_lag_shorter_than_delay() -> None:
    with pytest.raises(ValueError):
        HarmonicFluNet(lag_weeks=1, report_delay_weeks=2)


def test_flunet_model_resolves_by_name() -> None:
    from urgencias_core.models.registry import resolve_models

    assert list(resolve_models(["armonicoflunet"])) == ["ArmónicoFluNet"]
