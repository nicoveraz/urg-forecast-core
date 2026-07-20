# urg-forecast-core

[![ci](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml/badge.svg)](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/urgencias-core.svg)](https://pypi.org/project/urgencias-core/)
[![Python](https://img.shields.io/pypi/pyversions/urgencias-core.svg)](https://pypi.org/project/urgencias-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/nicoveraz/urg-forecast-core/blob/main/LICENSE)

Reference code for Chilean emergency department (ED) analytics, simulation, and
forecasting. Open foundation of **Eunosia**.

*Leer en [español](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.es.md).*

It turns visit-level ED data into hourly occupancy series, adds Chilean calendar
features, forecasts arrivals/occupancy with quantile bands, and runs a Monte
Carlo census simulator — plus a reader for the public DEIS MINSAL dataset and a
minimal web dashboard.

## Install

```bash
pip install urgencias-core            # core library (data, timeseries, features, simulation)
pip install "urgencias-core[all]"     # everything: models, viz, server, and data fetchers
```

The core install is intentionally light (pandas/numpy/pyarrow/holidays/pydantic).
Heavier capabilities live behind extras — a module that needs one raises a clear
"install the extra" error:

| Extra | Pulls in | Enables |
|---|---|---|
| `models` | lightgbm, statsforecast, scikit-learn | LightGBM/statsforecast quantile forecasters |
| `viz` | matplotlib, tabulate | charts and markdown tables (demos, server) |
| `server` | fastapi, uvicorn, jinja2 (+ `viz`) | the reference dashboard server |
| `fetch` | httpx | DEIS MINSAL and Open-Meteo network clients |
| `all` | all of the above | the demos and the full test suite |

## Quickstart

After `pip install "urgencias-core[all]"`, three console commands are available.
They run on datasets bundled with the package and write to `./outputs`:

```bash
urgencias-demo-synthetic          # full pipeline incl. simulation → 3 PNGs
urgencias-demo-deis --offline     # forecasting on real DEIS hospital data
urgencias-server                  # reference dashboard at http://127.0.0.1:8000
```

From a source checkout with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/nicoveraz/urg-forecast-core
cd urg-forecast-core
uv sync --all-extras

uv run urgencias-demo-synthetic
uv run urgencias-demo-deis --offline
uv run urgencias-server
```

The synthetic demo runs in seconds on a compact one-year synthetic fixture
(~13,000 visits) bundled with the package. The DEIS demo fetches real public
data (or falls back to the bundled offline snapshot) and writes backtesting
tables plus 6-month-ahead forecasts.

## What the pipeline produces

The figures below are the direct output of running the two demos against the
bundled data.

### 1. From visits to an hourly occupancy series

`urgencias_core.data.timeseries` converts the visit-level parquet (one row per
visit, with arrival and discharge timestamps) into an hourly census series using
the event-cumsum trick (+1 at arrival, −1 at discharge, cumulative sum reindexed
to the hourly grid). The figure shows the last week of the synthetic fixture: a
clear diurnal cycle with overnight troughs and evening peaks.

![Synthetic hourly occupancy](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/demo_synthetic_occupancy.png)

### 2. Forecasting layer — 48-hour hourly forecast

On that series, `SeasonalNaiveBaseline` produces a 48-hour hourly forecast with
P50–P80 and P80–P95 quantile bands. The stronger models (`AutoARIMA`,
`AutoETS`, `LGBQuantile`) are compared in the evaluation harness and live behind
the same `Forecaster` interface.

![Synthetic 48h hourly forecast](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/demo_synthetic_forecast.png)

### 3. Monte Carlo simulation engine

`urgencias_core.simulation.engine` takes future arrivals (sampled from the
forecast) and, for each arrival, samples an empirical length-of-stay conditional
on (acuity, arrival hour). Iterating M replicates yields census uncertainty
bands 24 hours ahead — the basis for surge decisions and shift tables.

![24h Monte Carlo simulation](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/demo_synthetic_simulation.png)

### 4. Real data — weekly backtest on DEIS

The DEIS demo runs the same forecasting layer against real ED attendances from
Hospital de Puerto Montt. The harness holds out the last 12 complete weeks
(partial edge weeks are trimmed, since near-real-time DEIS data can under-count
the latest week) and trains on the prior history; `AutoARIMA` is selected by P80
pinball loss and tracks the autumn rise — evidence the pipeline isn't overfit to
the synthetic regime.

![12-week holdout, Puerto Montt](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/deis_holdout_hospital_base_puerto_montt.png)

### 5. Operational 6-month forecast

With the model validated, the demo retrains on all history and emits a 26-week
weekly forecast — the useful horizon for staffing, budget, and supplies. The
P80–P95 band widens with the horizon, as expected.

![6-month forecast, Puerto Montt](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/deis_forecast_hospital_base_puerto_montt.png)

### 6. Reference dashboard

The FastAPI server (`urgencias-server`) exposes four routes with the same charts
as the pipeline, live in the browser. It is deliberately minimal — Jinja2 plus
base64-embedded matplotlib, no JavaScript — a starting point for a hospital to
clone and adapt.

<p align="center">
<img src="https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/dashboard_index.png" width="48%" alt="Dashboard - index"/>
<img src="https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/dashboard_baseline.png" width="48%" alt="Dashboard - descriptive analytics"/>
</p>
<p align="center">
<img src="https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/dashboard_forecast.png" width="48%" alt="Dashboard - forecast"/>
<img src="https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/dashboard_simulation.png" width="48%" alt="Dashboard - simulation"/>
</p>

## What's inside

| Module | Purpose |
|---|---|
| `urgencias_core.data.loader` | Read a visit-level parquet and validate the schema. |
| `urgencias_core.data.timeseries` | Convert visits to an hourly series (arrivals, discharges, occupancy by acuity, mean LOS) via the event-cumsum trick. |
| `urgencias_core.data.deis` | DEIS MINSAL client (fetch + cache + filter to demo hospitals) with an offline snapshot fallback. |
| `urgencias_core.features.calendar` | `holidays.CL` holidays, bridge days, school calendar, configurable regional events. |
| `urgencias_core.features.weather` | Open-Meteo client with on-disk cache, Puerto Montt by default. |
| `urgencias_core.models.protocol` | `Forecaster` protocol and `HorizonSpec` (grain-agnostic: hourly, daily, weekly, monthly). |
| `urgencias_core.models.lgb_quantile` | LightGBM quantile regression, one model per quantile, calendar features. |
| `urgencias_core.eval.baselines` | `SeasonalNaiveBaseline` + `statsforecast` wrappers (AutoARIMA, AutoETS, AutoTheta, MSTL). |
| `urgencias_core.eval.harness` | Side-by-side evaluation with a ≥5% warning rule (a model that doesn't beat the baselines shouldn't ship). |
| `urgencias_core.simulation.los_empirical` | Empirical LOS sampler conditional on (acuity, arrival hour). |
| `urgencias_core.simulation.engine` | Monte Carlo census simulation 24 hours forward. |
| `urgencias_core.server` | Minimal FastAPI server (4 routes, Jinja2, base64 matplotlib, no JS). |

Docstrings are in English; user-facing strings in the server, demo outputs, and
fixtures are in Spanish.

## Public data: DEIS MINSAL

The DEIS demo uses open data from Chile's Ministry of Health Department of Health
Statistics and Information ([deis.minsal.cl](https://deis.minsal.cl/#datosabiertos))
for two hospitals in the Servicio de Salud Reloncaví network: **Hospital de
Puerto Montt** (code 24-105, high-complexity, locally "Hospital Base de Puerto
Montt") and **Hospital de Frutillar** (code 24-115, low-complexity).

DEIS publishes this series from 2008 to the present. The current-year file is
updated weekly during the winter respiratory campaign (March–September) and
roughly monthly otherwise. The demo uses the latest data available at run time
and produces a six-month-ahead forecast.

**Why these two hospitals.** Regional reference centers in Los Lagos with
publicly available data. Chosen on geographic and pragmatic grounds, not on any
evaluation of quality.

**Methodological framing only.** This demo uses public DEIS MINSAL data to show
how the forecasting tools behave on real Chilean hospital data. It is NOT an
operational, clinical, or quality evaluation of either hospital.

**Attribution and license.** Data published by DEIS MINSAL under Chile's open
data framework. If you use this code or derivatives for research, maintain DEIS
attribution and, where relevant, cite `urgencias-core`. The offline snapshot
bundled with the package is a filtered extract of the public dataset for
reproducibility; it does not replace fetching directly from the source for
operational use.

## Project status

`urgencias-core` is an open foundation, developed and maintained by Nicolás
Vera Z. as the base of **Eunosia**, a clinical AI platform for emergency
medicine. It is published on PyPI and maintained on a best-effort basis: while
on 0.x the API may change between minor versions, and issues and pull requests
are welcome but not guaranteed a fast response. If you need commercial support
or bespoke work on top of this foundation, contact the author.

See [`CONTRIBUTING.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/CONTRIBUTING.md)
for development and release procedures, [`docs/decisions.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/decisions.md)
for architecture decisions, and [`docs/roadmap.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/roadmap.md)
for deferred items (xlsx/mdb support for DEIS 2017–2019, neuralforecast, EMR
integration to separate workup from boarding time).

## Citing

If you use `urgencias-core` in research, please cite it. Machine-readable
metadata lives in [`CITATION.cff`](https://github.com/nicoveraz/urg-forecast-core/blob/main/CITATION.cff)
(GitHub renders a "Cite this repository" button from it). Each tagged release is
archived on [Zenodo](https://zenodo.org/) with a DOI.

<!-- After the first Zenodo release, add the concept-DOI badge and BibTeX here:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX) -->

A software paper (JOSS format) and a fuller methods preprint are drafted under
[`paper/`](https://github.com/nicoveraz/urg-forecast-core/tree/main/paper).
Please also mention Eunosia and link back to the repository.

## License

MIT. See [LICENSE](https://github.com/nicoveraz/urg-forecast-core/blob/main/LICENSE).
