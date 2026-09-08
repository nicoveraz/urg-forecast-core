from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from urgencias_core.simulation.engine import (
    CurrentPatient,
    _mean_census_per_hour,
    simulate,
)
from urgencias_core.simulation.los_empirical import EmpiricalLOSSampler


def _fit_sampler(visits: pd.DataFrame) -> EmpiricalLOSSampler:
    return EmpiricalLOSSampler(seed=0).fit(visits)


def test_zero_arrivals_and_empty_ed_gives_zero_census(visits: pd.DataFrame) -> None:
    sampler = _fit_sampler(visits)
    result = simulate(
        arrivals_mean=np.zeros(24),
        start_hour=0,
        los_sampler=sampler,
        current_patients=0,
        n_sims=50,
        seed=1,
    )
    assert result.census.shape == (50, 24)
    assert (result.census == 0).all()


def test_current_patients_drain_over_time(visits: pd.DataFrame) -> None:
    sampler = _fit_sampler(visits)
    start_patients = [CurrentPatient(acuity="C3") for _ in range(50)]
    result = simulate(
        arrivals_mean=np.zeros(48),
        start_hour=10,
        los_sampler=sampler,
        current_patients=start_patients,
        n_sims=100,
        seed=1,
    )
    mean_by_hour = result.census.mean(axis=0)
    # Census should be monotonically non-increasing on average with zero arrivals.
    assert mean_by_hour[0] <= len(start_patients)
    # By hour 48 nearly everyone should have departed (median LOS < 3h).
    assert mean_by_hour[-1] < mean_by_hour[0] * 0.2


def test_exceedance_probabilities_bounded(visits: pd.DataFrame) -> None:
    sampler = _fit_sampler(visits)
    result = simulate(
        arrivals_mean=np.full(24, 5.0),
        start_hour=12,
        los_sampler=sampler,
        current_patients=10,
        n_sims=200,
        seed=2,
    )
    p = result.exceedance(threshold=5)
    assert p.shape == (24,)
    assert ((p >= 0.0) & (p <= 1.0)).all()


def test_reproducible_with_seed(visits: pd.DataFrame) -> None:
    sampler = _fit_sampler(visits)
    args = dict(
        arrivals_mean=np.full(12, 4.0),
        start_hour=8,
        los_sampler=sampler,
        current_patients=5,
        n_sims=50,
        seed=42,
    )
    r1 = simulate(**args)
    # Rebuild sampler so its internal RNG state is also fresh.
    args["los_sampler"] = _fit_sampler(visits)
    r2 = simulate(**args)
    np.testing.assert_array_equal(r1.census, r2.census)


def test_quantile_frame_has_expected_shape(visits: pd.DataFrame) -> None:
    sampler = _fit_sampler(visits)
    result = simulate(
        arrivals_mean=np.full(6, 3.0),
        start_hour=0,
        los_sampler=sampler,
        current_patients=0,
        n_sims=100,
        seed=3,
    )
    qf = result.quantile_frame()
    assert list(qf.columns) == ["hour_offset", "q50", "q80", "q90", "q95"]
    assert len(qf) == 6
    assert (qf["q50"] <= qf["q95"]).all()


def test_mean_census_matches_littles_law(visits: pd.DataFrame) -> None:
    """Steady-state census must equal arrival rate x mean LOS.

    Regression test for the 2026-09 fix: the engine used to count patients still
    present at the END of each hour, which dropped everyone arriving and leaving
    inside the same hour and under-counted the census by ~30% (ratio ~0.70 on an
    ED with ~1.8 h median LOS). No shape/monotonicity test caught it, because
    only the MAGNITUDE was wrong. This pins the magnitude to theory.
    """
    sampler = _fit_sampler(visits)
    rng = np.random.default_rng(0)
    codes = np.array(list(sampler.acuity_mix))
    probs = np.array(list(sampler.acuity_mix.values()), dtype="float64")
    probs = probs / probs.sum()
    # LOS of the acuity MIX the simulator draws from (not of a single bucket)
    mean_los = float(
        sampler.sample_many(rng.choice(codes, 20000, p=probs), rng.integers(0, 24, 20000)).mean()
    )
    rate = 5.0
    horizon = 400
    result = simulate(
        arrivals_mean=np.full(horizon, rate),
        start_hour=0,
        los_sampler=sampler,
        current_patients=0,
        n_sims=40,
        seed=3,
    )
    steady = result.census[:, horizon // 2:].mean()
    assert steady == pytest.approx(rate * mean_los, rel=0.05)


def test_census_is_the_time_weighted_hourly_mean() -> None:
    """One patient present for half of hour 0 contributes 0.5, not 0 and not 1."""
    census = _mean_census_per_hour(
        arrivals=np.array([0.25]), departures=np.array([0.75]), horizon=2
    )
    assert census[0] == pytest.approx(0.5)
    assert census[1] == pytest.approx(0.0)
    # a patient spanning a whole hour contributes exactly 1 to it
    census = _mean_census_per_hour(
        arrivals=np.array([0.0]), departures=np.array([1.0]), horizon=2
    )
    assert census[0] == pytest.approx(1.0)
    assert census[1] == pytest.approx(0.0)
    # and one straddling the boundary splits across both hours
    census = _mean_census_per_hour(
        arrivals=np.array([0.5]), departures=np.array([1.5]), horizon=2
    )
    assert census[0] == pytest.approx(0.5)
    assert census[1] == pytest.approx(0.5)


def test_sub_hour_stays_are_not_invisible(visits: pd.DataFrame) -> None:
    """The exact failure mode of the old implementation: short stays counted 0."""
    # 10 patients arriving in hour 0, each staying 30 minutes: the mean census
    # during hour 0 is 10 * 0.5 = 5, while an end-of-hour snapshot would see 0.
    census = _mean_census_per_hour(
        arrivals=np.full(10, 0.0), departures=np.full(10, 0.5), horizon=1
    )
    assert census[0] == pytest.approx(5.0)
