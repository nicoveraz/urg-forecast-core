"""Monte Carlo discrete-event simulator for ED census over a short horizon.

The simulator takes an arrivals forecast (hourly mean arrivals), an empirical
LOS sampler, and the current state of the ED (patients already in care and,
optionally, their hours-in-ED), then runs ``n_sims`` independent Poisson
arrival trajectories. Each arrival samples an acuity from a configurable mix
and a LOS from the sampler; each current patient contributes a residual LOS
drawn from its acuity bucket.

The output is the per-simulation, per-hour census matrix, plus convenience
derivatives: per-hour empirical quantiles and exceedance probabilities for
user-supplied thresholds.

Census definition (fixed 2026-09): each cell is the **time-weighted mean of the
instantaneous census during that hour** — the same quantity
``urgencias_core.data.timeseries`` reports as ``occupancy``, so simulated and
observed census are directly comparable. Until 2026-09 the engine counted
patients still present at the END of the hour, which silently dropped everyone
who arrived and left inside the same hour and under-counted the census by ~30 %
on a typical ED (median LOS ~1.8 h). Anything calibrated against the old
behaviour (staffing thresholds, exceedance probabilities) shifts upward.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .los_empirical import EmpiricalLOSSampler


@dataclass
class CurrentPatient:
    """A patient already in the ED at simulation start (t=0)."""

    acuity: str
    hours_in_ed: float = 0.0


@dataclass
class SimulationResult:
    """Result of a Monte Carlo simulation run.

    Attributes
    ----------
    census
        Array of shape ``(n_sims, horizon_hours)``; each entry is the
        time-weighted MEAN census during that hour (same definition as
        ``timeseries.hourly_timeseries``'s ``occupancy``), so values are
        fractional.
    hours_since_start
        Array of shape ``(horizon_hours,)`` with hour offsets 1..H.
    """

    census: np.ndarray
    hours_since_start: np.ndarray
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95)

    def quantile_frame(self) -> pd.DataFrame:
        """Per-hour empirical quantiles across simulations."""
        q = np.quantile(self.census, self.quantiles, axis=0)
        cols = {f"q{int(round(p * 100))}": q[i] for i, p in enumerate(self.quantiles)}
        return pd.DataFrame({"hour_offset": self.hours_since_start, **cols})

    def exceedance(self, threshold: float) -> np.ndarray:
        """Empirical P(census > threshold) for each future hour."""
        return np.mean(self.census > threshold, axis=0)


def _mean_census_per_hour(
    arrivals: np.ndarray, departures: np.ndarray, horizon: int
) -> np.ndarray:
    """Time-weighted mean census for each hour ``[h, h+1)``, h = 0..horizon-1.

    Exact, not sampled: person-hours accumulated up to ``T`` are
    ``F(T) = sum(min(departure, T)) - sum(min(arrival, T))``, so the mean census
    during hour ``h`` is ``F(h+1) - F(h)``. Matches the definition
    ``data.timeseries._occupancy_by_events`` uses for observed occupancy.
    """
    a = np.sort(np.asarray(arrivals, dtype="float64"))
    d = np.sort(np.asarray(departures, dtype="float64"))
    ca = np.concatenate(([0.0], np.cumsum(a)))
    cd = np.concatenate(([0.0], np.cumsum(d)))
    edges = np.arange(horizon + 1, dtype="float64")

    def _clipped_sum(x_sorted: np.ndarray, cum: np.ndarray, t: np.ndarray) -> np.ndarray:
        k = np.searchsorted(x_sorted, t, side="right")
        return cum[k] + (len(x_sorted) - k) * t

    f = _clipped_sum(d, cd, edges) - _clipped_sum(a, ca, edges)
    return np.diff(f)


def simulate(
    arrivals_mean: np.ndarray,
    start_hour: int,
    los_sampler: EmpiricalLOSSampler,
    current_patients: list[CurrentPatient] | int = 0,
    arrival_acuity_mix: dict[str, float] | None = None,
    n_sims: int = 1000,
    quantiles: tuple[float, ...] = (0.5, 0.8, 0.9, 0.95),
    seed: int = 42,
) -> SimulationResult:
    """Run a Monte Carlo simulation of ED census.

    Parameters
    ----------
    arrivals_mean
        Expected arrivals per hour for each of the next ``H`` hours.
    start_hour
        Hour-of-day at simulation start (0..23). Used to determine which
        LOS bucket each hour's arrivals sample from.
    los_sampler
        A fit ``EmpiricalLOSSampler``.
    current_patients
        Either a list of ``CurrentPatient`` (exact) or an integer count. If
        an integer, patients are drawn from the sampler's empirical acuity
        mix and assumed to have just arrived at t=0.
    arrival_acuity_mix
        Probability per acuity code for future arrivals. Defaults to the
        sampler's empirical mix.
    n_sims
        Number of simulation trajectories (default 1000).
    quantiles
        Quantile levels to summarize the result with.
    seed
        RNG seed for reproducibility.

    Returns
    -------
    SimulationResult
        ``census[s, h]`` is the time-weighted mean census during hour ``h`` of
        simulation ``s`` — comparable to observed ``occupancy``, and fractional.
    """
    arrivals_mean = np.asarray(arrivals_mean, dtype="float64")
    if arrivals_mean.ndim != 1:
        raise ValueError("arrivals_mean must be a 1-D array")
    horizon = len(arrivals_mean)
    if horizon == 0:
        raise ValueError("arrivals_mean must be non-empty")

    mix = arrival_acuity_mix or los_sampler.acuity_mix
    acuity_codes = np.array(list(mix.keys()))
    acuity_probs = np.asarray(list(mix.values()), dtype="float64")
    acuity_probs = acuity_probs / acuity_probs.sum()

    rng = np.random.default_rng(seed)
    census = np.zeros((n_sims, horizon), dtype="float64")

    if isinstance(current_patients, int):
        baseline_count = current_patients
        baseline_acuities_sample = rng.choice(acuity_codes, size=baseline_count, p=acuity_probs)
        baseline_known: list[CurrentPatient] = [
            CurrentPatient(acuity=str(a), hours_in_ed=0.0) for a in baseline_acuities_sample
        ]
    else:
        baseline_known = list(current_patients)

    for s in range(n_sims):
        # Residual LOS for current patients: sample fresh from acuity bucket
        # at current hour_of_day. Subtract hours already in ED (truncate to 0).
        # They are present from t=0.
        arrive_times: list[np.ndarray] = []
        depart_times: list[np.ndarray] = []
        if baseline_known:
            acuities = np.array([p.acuity for p in baseline_known])
            hours = np.full(len(baseline_known), start_hour, dtype="int64")
            los_samples = los_sampler.sample_many(acuities, hours)
            already_in = np.array([p.hours_in_ed for p in baseline_known], dtype="float64")
            remaining = np.maximum(los_samples - already_in, 1 / 60)
            arrive_times.append(np.zeros(len(baseline_known), dtype="float64"))
            depart_times.append(remaining.astype("float64"))

        # Arrivals placed UNIFORMLY inside their hour. Pinning them to the hour
        # mark, as the old code did, is what made sub-hour stays invisible.
        n_arrivals = rng.poisson(arrivals_mean)
        total = int(n_arrivals.sum())
        if total > 0:
            hour_of = np.repeat(np.arange(horizon), n_arrivals)
            arrived_acuities = rng.choice(acuity_codes, size=total, p=acuity_probs)
            arrival_hod = ((start_hour + hour_of) % 24).astype("int64")
            los_new = los_sampler.sample_many(arrived_acuities, arrival_hod)
            arr = hour_of + rng.random(total)
            arrive_times.append(arr)
            depart_times.append(arr + los_new)

        if arrive_times:
            census[s] = _mean_census_per_hour(
                np.concatenate(arrive_times), np.concatenate(depart_times), horizon
            )

    hours_since_start = np.arange(1, horizon + 1)
    return SimulationResult(
        census=census,
        hours_since_start=hours_since_start,
        quantiles=tuple(quantiles),
    )


__all__ = ["CurrentPatient", "SimulationResult", "simulate"]
