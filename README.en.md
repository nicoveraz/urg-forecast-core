# urg-forecast-core

[![ci](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml/badge.svg)](https://github.com/nicoveraz/urg-forecast-core/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/urg-forecast-core.svg)](https://pypi.org/project/urg-forecast-core/)
[![Python](https://img.shields.io/pypi/pyversions/urg-forecast-core.svg)](https://pypi.org/project/urg-forecast-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/nicoveraz/urg-forecast-core/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21449610.svg)](https://doi.org/10.5281/zenodo.21449610)

**A free, open base for forecasting emergency department demand in Chile from
public DEIS MINSAL data.** One command gives you a backtest and a weekly
forecast for any establishment that reports to DEIS. It is a first
approximation: tuning it to your setting is up to you, and the code is built
for that.

> **A base, not a decision tool.** The models are simple and statistical,
> untuned, on public aggregated data. Use the results to explore and to
> benchmark your own work, not to staff a shift or plan a budget without local
> validation. See [A base, not a product](#a-base-not-a-product).

*Documentación principal en [español](https://github.com/nicoveraz/urg-forecast-core/blob/main/README.md). This is an English translation.*

Full documentation (in Spanish) at
[nicoveraz.github.io/urg-forecast-core](https://nicoveraz.github.io/urg-forecast-core/).

## Quickstart

```bash
pip install urg-forecast-core                          # Python 3.11 or 3.12

urg-forecast demo                                      # Puerto Montt and Frutillar hospitals
urg-forecast buscar "osorno"                           # find your establishment's DEIS code
urg-forecast pronosticar 24-105                        # backtest + 26-week forecast
urg-forecast pronosticar 24-105 -H 6m                  # choose the horizon: 12, 12s (weeks) or 6m (months)
urg-forecast modelos                                   # list available models
urg-forecast pronosticar 24-105 -m AutoARIMA           # use one model instead of comparing
urg-forecast pronosticar 24-105 -m Ensamble -m TBATS   # try extra models
urg-forecast pronosticar 24-105 -m my_module:MyModel   # or your own model
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

Run `urg-forecast -h`, or `urg-forecast <command> -h`, for every option with
examples. Details in the [command reference](#command-reference).

Example output of `urg-forecast demo` with live DEIS data on 2026-10-05 (interface in Spanish):

```text
Hospital de Puerto Montt (24-105)
=================================

Datos      DEIS MINSAL (descarga actualizada); atenciones totales por semana
Historia   2022-01-10 a 2026-09-14 (245 semanas completas; 2020–2021 excluidos)
Horizonte  26 semanas

Backtest: 3 ventanas de 26 semanas, promedio (el modelo elegido se marca con *)
+---------------+-------+----------+---------------+
| Modelo        |   MAE |   MAPE % |   Pérdida P80 |
|---------------+-------+----------+---------------|
| Armónico *    |   207 |     10.7 |          91.0 |
| MSTL          |   231 |     11.9 |          91.6 |
| AutoARIMA     |   232 |     11.7 |         104.0 |
| SeasonalNaive |   359 |     17.6 |         230.0 |
+---------------+-------+----------+---------------+
Con Armónico, el valor real quedó bajo el P80 en 24 de 78 semanas.
Intervalos del pronóstico ensanchados según ese error: P80 x2.8, P90 x2.6, P95 x2.1.

Pronóstico con Armónico: atenciones semanales
+--------------------+-------+-------+-------+
| Semana (termina)   |   P50 |   P80 |   P95 |
|--------------------+-------+-------+-------|
| 2026-09-21         |  2042 |  2259 |  2350 |
| 2026-09-28         |  2027 |  2284 |  2393 |
| ...                |       |       |       |
```

![26-week forecast, Hospital de Puerto Montt](https://raw.githubusercontent.com/nicoveraz/urg-forecast-core/main/docs/img/pronostico_puerto_montt.png)

## Command reference

| Command | What it does |
|---|---|
| `urg-forecast demo` | Forecast for Hospital de Puerto Montt (24-105) and Hospital de Frutillar (24-115). Tries DEIS and falls back to the bundled snapshot offline. |
| `urg-forecast buscar [TEXT]` | Lists DEIS establishments whose name or code contains `TEXT` (all if empty). The first column is the code `pronosticar` takes. |
| `urg-forecast pronosticar CODE [CODE ...]` | Backtest + forecast for one or more establishments. Codes like `24-105` or `124105`. |
| `urg-forecast modelos` | Lists the available models and which are compared by default. |

| Option | Commands | Meaning |
|---|---|---|
| `-H`, `--horizonte` | demo, pronosticar | Horizon: weeks (`12`, `12s`) or months (`6m`). Default 26 weeks. |
| `-o`, `--salida` | demo, pronosticar | Output folder (default `./urg-forecast-salida`); one subfolder per establishment. |
| `-m`, `--modelo` | demo, pronosticar | Model to use, repeatable. A name from `urg-forecast modelos` or `file:Class` for your own. See [Models](#models). |
| `--sin-calibrar` | demo, pronosticar | Do not widen intervals by backtest error. |
| `--desde YEAR` | pronosticar | First DEIS year to use (default 2022). 2020–2021 are always excluded. |
| `--offline` | demo, pronosticar | Bundled snapshot only, no network. It contains only the two demo hospitals. |
| `--anio YEAR` | buscar | DEIS year to search (default current; in early January use the previous one). |
| `--cache DIR` | demo, buscar, pronosticar | Where to store the yearly DEIS ZIPs (see below). |
| `--version` | — | Show the version. |

**Download cache.** DEIS yearly files are large (hundreds of MB). By default
they go to `./data/external/deis_cache/`, **relative to the folder you run the
command from**. To share one cache across folders, set
`URG_FORECAST_CACHE=/path/to/cache` or pass `--cache`.

**Exit codes.** `0` if at least one establishment was forecast, `1` if there
was no data (unknown code, too little history, no connection) or no search
match, `2` for invalid arguments or model. A forecast needs at least
`backtest + 104` complete weeks: 130 weeks with the default 26-week horizon.

## How it works

1. Downloads the yearly DEIS *Atenciones de Urgencia* files and caches them in
   the cache (see above). The current year is re-downloaded when the
   cached copy is older than 7 days, and so is the previous year until March,
   while DEIS is still correcting it. You always model the latest published
   data.
2. Sums total attendances per complete week (partial weeks at the edges are
   dropped, since DEIS reports with a lag). 2020–2021 are excluded (COVID),
   and the 2017–2019 files (xlsx/mdb) are not read yet, so in practice the
   history starts in 2022 even with `--desde`.
3. Backtests four models — seasonal naive (reference), AutoARIMA, a harmonic
   regression and MSTL — over three windows as long as the horizon (max. 26
   weeks), and picks the one with the lowest mean P80 quantile loss. On live
   data for seven hospitals no single model won everywhere, so the choice is
   made per establishment; see
   [`docs/seleccion-de-modelos.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/seleccion-de-modelos.md).
4. Refits that model on all the history and forecasts the horizon you asked for.
5. Widens the forecast intervals by the backtest error when they were too
   narrow there (never narrows them). `--sin-calibrar` turns this off.

`urg-forecast demo` tries DEIS first and falls back to a snapshot bundled with
the package when there is no connection; the summary says which one was used.
`--offline` forces the snapshot.

## A base, not a product

You get a working, tested pipeline from public data to a forecast with an
honest backtest. You do not get:

- **Tuned models.** They are statistical models with no tuning for your
  establishment, no weather and no local events (except holidays in
  `ArmónicoFeriados`).
- **Detail.** It forecasts **total weekly attendances only**, not by cause, age
  or acuity, and not daily or hourly.
- **Exact intervals.** Step 5 widens them by past error, which does not
  anticipate an unusual season.
- **Validation.** It has not been validated as a clinical or operational
  decision tool, and DEIS data are aggregated and published with a lag.

Before relying on a forecast for real decisions, at least:

1. Check the backtest table and the P80 coverage line for *your*
   establishment; short history or a structural change (new service, a change
   in catchment population) makes them unreliable.
2. Compare it with what your team already uses (same week last year, a
   spreadsheet): the model has to beat it to be worth anything.
3. Add what you know locally: covariates, your own models, your own data.
4. Re-run it often; the summary warns when the data are more than four weeks
   old.

The value is in what you add. That is the point of the next two sections.

## Models

Four are compared by default and the best one is used. Four more are available
for experimenting with `-m`:

| Model | Default | In short |
|---|---|---|
| SeasonalNaive | yes | reference: the same week in previous years |
| AutoARIMA | yes | seasonal ARIMA (52 weeks), bounded search |
| Armónico | yes | trend + annual cycle (Fourier) + ARIMA on residuals |
| MSTL | yes | seasonal decomposition + ETS trend |
| TBATS | | trigonometric seasonality with Box-Cox; slow |
| Theta | | trend only; a contrast |
| Ensamble | | median of AutoARIMA, Armónico and MSTL |
| ArmónicoFeriados | | Armónico + Chilean weekday holidays |

Names ignore case and accents (`-m armonicoferiados` works). Details, when each
one helps and how to add your own (in Spanish):
[`docs/modelos.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/modelos.md).
Why the default four:
[`docs/seleccion-de-modelos.md`](https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/seleccion-de-modelos.md).

## Extending it

Everything the command does is a few plain functions over DataFrames:

```python
from urgencias_core import load_deis, weekly_series, run_forecast

df = load_deis(["24-105"])
weekly = weekly_series(df, "24-105")              # timestamp, count
result = run_forecast(weekly, horizon_weeks=12)
result.backtest                                    # per model, averaged over windows
result.forecast                                    # timestamp, q50, q80, q90, q95
```

**Your own model.** Anything with `fit(history, target_col)` and
`predict(horizon)` returning `timestamp, q50, q80, q90, q95` satisfies the
`Forecaster` protocol; `urgencias_core/models/harmonic.py` is a short example.
From the command line, put it in a `.py` file in the current directory and
pass `-m file:Class` (repeat `-m` to compare it against built-in models). In
Python, pass it next to the defaults and it competes in the same backtest:

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
