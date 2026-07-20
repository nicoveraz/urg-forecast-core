"""The 30-second synthetic demo.

Loads the packaged synthetic fixture, computes the hourly occupancy time
series, fits ``SeasonalNaiveBaseline`` on arrivals, runs the Monte Carlo
simulator for 24 hours, and writes three PNG charts plus a short summary.

Run with::

    urgencias-demo-synthetic              # after: pip install "urgencias-core[viz]"
    uv run python scripts/demo_synthetic.py   # from a source checkout

Outputs land in ``./outputs`` (override with ``--out``):

- ``demo_synthetic_occupancy.png``  historical hourly occupancy (last week)
- ``demo_synthetic_forecast.png``   48-hour arrivals forecast with bands
- ``demo_synthetic_simulation.png`` 24-hour Monte Carlo census fan chart
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

from urgencias_core._logging import setup_logging
from urgencias_core._optional import missing_extra_error
from urgencias_core.data.fixtures import synthetic_visits_path
from urgencias_core.data.loader import load_visits
from urgencias_core.data.timeseries import hourly_timeseries
from urgencias_core.eval.baselines import SeasonalNaiveBaseline
from urgencias_core.models.protocol import HorizonSpec
from urgencias_core.simulation.engine import simulate
from urgencias_core.simulation.los_empirical import EmpiricalLOSSampler

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover - exercised via the core-only install
    raise missing_extra_error("viz", "The synthetic demo") from exc

log = logging.getLogger(__name__)


def run(fixture: Path, outputs: Path) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    log.info("Loading fixture: %s", fixture)
    visits = load_visits(fixture)
    log.info(
        "  %s visits, %s -> %s",
        f"{len(visits):,}",
        visits["arrival"].min().date(),
        visits["arrival"].max().date(),
    )

    log.info("Computing hourly time series...")
    hourly = hourly_timeseries(visits)
    log.info("  %s hours", f"{len(hourly):,}")

    # 1. Occupancy chart (last 7 days)
    last_week = hourly.tail(24 * 7)
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.plot(last_week["timestamp"], last_week["occupancy"], color="#214", linewidth=1.2)
    ax.set_title("Ocupación horaria — última semana de la historia sintética")
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Censo")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.savefig(outputs / "demo_synthetic_occupancy.png", dpi=110, bbox_inches="tight")
    plt.close(fig)

    # 2. Forecast: fit SeasonalNaive on the last 30 days, predict 48 h ahead
    train = hourly.tail(24 * 30).reset_index(drop=True)
    fc = SeasonalNaiveBaseline()
    fc.fit(train, "arrivals")
    horizon = HorizonSpec(grain="h", length=48)
    pred = fc.predict(horizon)
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(pred["timestamp"], pred["q80"], pred["q95"], alpha=0.18, label="P80–P95")
    ax.fill_between(pred["timestamp"], pred["q50"], pred["q80"], alpha=0.30, label="P50–P80")
    ax.plot(pred["timestamp"], pred["q50"], color="#214", linewidth=1.5, label="Mediana")
    ax.set_title("Pronóstico horario de llegadas (SeasonalNaiveBaseline, 48 h)")
    ax.set_xlabel("Tiempo")
    ax.set_ylabel("Llegadas / hora")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.savefig(outputs / "demo_synthetic_forecast.png", dpi=110, bbox_inches="tight")
    plt.close(fig)

    # 3. Simulation
    log.info("Fitting LOS sampler...")
    sampler = EmpiricalLOSSampler(seed=0).fit(visits)
    log.info("Running Monte Carlo simulation (N=500, 24h forward)...")
    mean_arrivals = float(hourly["arrivals"].tail(24 * 14).mean())
    result = simulate(
        arrivals_mean=np.full(24, mean_arrivals),
        start_hour=12,
        los_sampler=sampler,
        current_patients=int(hourly["occupancy"].iloc[-1]),
        n_sims=500,
        seed=1,
    )
    qf = result.quantile_frame()
    fig, ax = plt.subplots(figsize=(10, 3.5))
    x = qf["hour_offset"]
    ax.fill_between(x, qf["q80"], qf["q95"], alpha=0.18, label="P80–P95")
    ax.fill_between(x, qf["q50"], qf["q80"], alpha=0.30, label="P50–P80")
    ax.plot(x, qf["q50"], color="#214", linewidth=1.5, label="Mediana")
    ax.set_title("Simulación Monte Carlo — censo simulado 24 h")
    ax.set_xlabel("Horas desde inicio")
    ax.set_ylabel("Censo")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.savefig(outputs / "demo_synthetic_simulation.png", dpi=110, bbox_inches="tight")
    plt.close(fig)

    # Summary
    log.info("")
    log.info("=== Resumen ===")
    log.info("Visitas:                    %s", f"{len(visits):,}")
    log.info("Horas de historia:          %s", f"{len(hourly):,}")
    log.info("Ocupación media:            %.2f", hourly["occupancy"].mean())
    log.info("Llegadas/hora (últimas 2s): %.2f", mean_arrivals)
    log.info("Mediana forecast P50 (48h): %.2f", pred["q50"].median())
    log.info("Mediana sim P50 (hora 12):  %.2f", qf["q50"].iloc[11])
    log.info("")
    log.info("Artefactos en %s/:", outputs)
    for name in (
        "demo_synthetic_occupancy.png",
        "demo_synthetic_forecast.png",
        "demo_synthetic_simulation.png",
    ):
        log.info("  - %s", name)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Run the synthetic ED pipeline demo.")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=synthetic_visits_path(),
        help="Visit-level parquet to run on (default: the packaged synthetic fixture).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs"),
        help="Directory for the generated PNGs (default: ./outputs).",
    )
    args = parser.parse_args()
    run(fixture=args.fixture, outputs=args.out)


if __name__ == "__main__":
    main()
