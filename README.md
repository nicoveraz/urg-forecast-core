# urg-forecast-core

[![ci](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml/badge.svg)](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/urg-forecast-core.svg)](https://pypi.org/project/urg-forecast-core/)
[![Python](https://img.shields.io/pypi/pyversions/urg-forecast-core.svg)](https://pypi.org/project/urg-forecast-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/nicoveraz/urg-forecast-core/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21449610.svg)](https://doi.org/10.5281/zenodo.21449610)

**A free, open base for forecasting emergency department demand in Chile from
public DEIS MINSAL data.** One command gives you a backtest and a weekly
forecast for any establishment that reports to DEIS. It is a starting point to
build on, not a finished product.

*Leer en [español](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.es.md).*

## Quickstart

```bash
pip install urg-forecast-core          # Python 3.11 or 3.12

urg-forecast demo                      # Puerto Montt and Frutillar hospitals
urg-forecast buscar "osorno"           # find your establishment's DEIS code
urg-forecast pronosticar 24-105        # backtest + 26-week forecast
urg-forecast pronosticar 24-105 -H 6m  # choose the horizon: 12, 12s (weeks) or 6m (months)
```

Each run prints a summary with ASCII tables and writes CSVs and figures to
`./urg-forecast-salida/<code>_<name>/` (change it with `-o`):

| File | Content |
|---|---|
| `resumen.txt` | the printed summary |
| `pronostico.csv` | weekly forecast: `q50`, `q80`, `q90`, `q95` |
| `backtest.csv` | error of each model on the backtest window |
| `historia_semanal.csv` | the weekly series that was modeled |
| `pronostico.png`, `backtest.png` | figures |

Example output with the bundled snapshot (`urg-forecast demo --offline`; interface in Spanish):

```text
Hospital de Puerto Montt (24-105)
=================================

Datos      snapshot DEIS incluido en el paquete; atenciones totales por semana
Historia   2022-01-10 a 2026-03-30 (221 semanas completas; 2020–2021 excluidos)
Horizonte  26 semanas
Atención   los datos terminan hace 27 semanas; el pronóstico parte desde esa fecha, no desde hoy.

Backtest: últimas 26 semanas (el mejor modelo se marca con *)
+---------------+-------+----------+---------------+
| Modelo        |   MAE |   MAPE % |   Pérdida P80 |
|---------------+-------+----------+---------------|
| AutoARIMA *   |   124 |      7.5 |          46.1 |
| AutoETS       |   201 |     13.1 |          76.5 |
| SeasonalNaive |   161 |      9.0 |          94.3 |
+---------------+-------+----------+---------------+
El valor real quedó bajo el P80 en 21 de 26 semanas.

Pronóstico con AutoARIMA: atenciones semanales
+--------------------+-------+-------+-------+
| Semana (termina)   |   P50 |   P80 |   P95 |
|--------------------+-------+-------+-------|
| 2026-04-06         |  2127 |  2212 |  2293 |
| ...                |       |       |       |
```

![26-week forecast, Hospital de Puerto Montt](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/pronostico_puerto_montt.png)

## How it works

1. Downloads the yearly DEIS *Atenciones de Urgencia* files and caches them in
   `data/external/deis_cache/`. The current year is re-downloaded when the
   cached copy is older than 7 days, and so is the previous year until March,
   while DEIS is still correcting it. You always model the latest published
   data.
2. Sums total attendances per complete week (partial weeks at the edges are
   dropped, since DEIS reports with a lag). 2020–2021 are excluded (COVID).
3. Backtests three models — seasonal naive, AutoARIMA and AutoETS — on the last
   weeks, as many as the horizon (max. 26), and picks the one with the lowest
   P80 quantile loss.
4. Refits that model on all the history and forecasts the horizon you asked for.

`urg-forecast demo` tries DEIS first and falls back to a snapshot bundled with
the package when there is no connection; the summary says which one was used.
`--offline` forces the snapshot.

## What this is not

- The models are **statistical baselines** with no tuning for your
  establishment, no weather and no local events.
- It forecasts **total weekly attendances only**, not by cause, age or acuity.
- It has not been validated as a clinical or operational decision tool.

The value is in what you add. That is the point of the next section.

## Build on it

Everything the command does is a few plain functions over DataFrames:

```python
from urgencias_core import load_deis, weekly_series, run_forecast

df = load_deis(["24-105"], start_year=2019)
weekly = weekly_series(df, "24-105")              # timestamp, count
result = run_forecast(weekly, horizon_weeks=12)
result.backtest                                    # MAE, MAPE, quantile losses per model
result.forecast                                    # timestamp, q50, q80, q90, q95
```

**Your own model.** Anything with `fit(history, target_col)` and
`predict(horizon)` returning `timestamp, q50, q80, q90, q95` satisfies the
`Forecaster` protocol. Pass it next to the baselines and it competes in the
same backtest:

```python
from urgencias_core.pipeline import default_models

models = default_models() | {"Mine": MyForecaster}
result = run_forecast(weekly, 12, models=models)
```

**Other series.** `load_deis` returns daily counts by cause and age group, so
you can model respiratory causes or pediatrics instead of the total.

**Chilean calendar.** `urgencias_core.features.calendar_features` builds
holiday, bridge-day, school-calendar and regional-event features, ready to use
as covariates.

See [`docs/roadmap.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/roadmap.md)
for known gaps that make good first contributions.

## Public data: DEIS MINSAL

Data come from the open *Atenciones de Urgencia* dataset of Chile's Ministry of
Health ([deis.minsal.cl](https://deis.minsal.cl/#datosabiertos)), published
since 2008 and updated weekly during the winter campaign (March–September). If
you use this code or its outputs, keep the DEIS attribution.

The demo uses Hospital de Puerto Montt (24-105) and Hospital de Frutillar
(24-115), chosen on geographic grounds. It is a methodological illustration,
not an operational or quality evaluation of either hospital.

## Status, contributing and citing

Version 0.x, maintained on a best-effort basis by Nicolás Vera Z.; the API may
change between minor versions. Issues and pull requests are welcome — see
[`CONTRIBUTING.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/CONTRIBUTING.md).
Run the tests with `uv run pytest -q`.

Version 0.2 narrowed the scope to DEIS-based forecasting. Version 0.1.0, which
also included visit-level analytics, Monte Carlo simulation and a dashboard,
remains on PyPI and Zenodo.

If you use it in research, cite it via
[`CITATION.cff`](https://github.com/nicoveraz/urg-forecast-core/blob/main/CITATION.cff)
(concept DOI [10.5281/zenodo.21449610](https://doi.org/10.5281/zenodo.21449610)).

## License

MIT. See [LICENSE](https://github.com/nicoveraz/urg-forecast-core/blob/main/LICENSE).
