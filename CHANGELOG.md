# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (API may
change between minor versions while on 0.x).

## [Unreleased]

## [0.2.0] - unreleased

Scope narrowed to one job: weekly ED attendance forecasting from public DEIS
MINSAL data, as a base to build on. **Breaking:** pin `urg-forecast-core<0.2`
if you depend on the removed modules.

### Added

- `urg-forecast` command with three subcommands: `demo`, `buscar` (find an
  establishment's DEIS code) and `pronosticar` (backtest + forecast for any
  establishment). Prints a summary with ASCII tables and writes CSVs and PNGs
  to a folder per establishment.
- Configurable horizon: `-H 12`, `12s` (weeks) or `6m` (months).
- Rolling backtest: three windows as long as the horizon (max. 26 weeks), 8
  weeks apart; the model with the lowest mean P80 quantile loss is used.
  Models that fail to fit are skipped and reported.
- Model set: SeasonalNaive (reference), AutoARIMA, `HarmonicRegression`
  (trend + annual Fourier terms + AutoARIMA residuals, new in
  `urgencias_core.models.harmonic`) and MSTL. Chosen from a comparison on live
  DEIS data for seven hospitals (`docs/model-selection.md`,
  `experiments/model_comparison.py`). AutoETS was dropped: with a 52-week
  period statsforecast discards its seasonality and the forecast is flat.
- `urg-forecast demo` downloads the latest DEIS data and falls back to the
  bundled snapshot when offline; the summary states which source was used and
  warns when the data are more than four weeks old.
- `urgencias_core.pipeline` (`load_deis`, `weekly_series`, `run_forecast`,
  `parse_horizon`) and `urgencias_core.report`.
- `data.deis.facility_code_variants`, `facilities_in_file`, `list_facilities`
  and `deis_reachable`. Codes are accepted as `24-105` or `124105`.
- `HarnessReport.predictions`: holdout predictions per forecaster.
- The most recent DEIS facility name is shown; skipped DEIS years get short
  Spanish messages.

### Changed

- Single install, no extras: statsforecast, httpx, matplotlib and tabulate are
  now core dependencies; pydantic is no longer needed.
- The previous year's DEIS file is re-downloaded weekly until March, since DEIS
  keeps correcting the just-closed year.
- Default AutoARIMA uses an approximate, bounded search (~1 s instead of ~20 s
  per fit with a 52-week season).
- READMEs rewritten around the command and the extension points.
- PyPI status `3 - Alpha`.

### Removed

Moved out of this repository:

- Visit-level loader and hourly occupancy series (`data.loader`,
  `data.timeseries`) and the synthetic fixture.
- Monte Carlo census simulation (`simulation`).
- Reference dashboard (`server`) and its config file.
- LightGBM quantile forecaster (`models.lgb_quantile`) and Open-Meteo client
  (`features.weather`).
- Commands `urgencias-demo-synthetic`, `urgencias-demo-deis`,
  `urgencias-server`, the `demos` package and the `scripts/` folder.
- Optional extras (`models`, `viz`, `server`, `fetch`, `all`).
- Draft papers under `paper/` and `docs/decisions.md`.

## [0.1.0] - 2026-07-20

First public release — the reference pipeline packaged for `pip install`.

### Added

- Core library: visit-level → hourly occupancy time series (event-cumsum),
  Chilean calendar features, empirical LOS sampler, Monte Carlo occupancy
  simulation, `Forecaster` protocol, seasonal-naive / statsforecast / LightGBM
  quantile forecasters, and an evaluation harness.
- DEIS MINSAL *Atenciones de Urgencia* fetcher with an offline snapshot
  fallback, bundled inside the package.
- Minimal FastAPI reference server with server-rendered charts.
- Console entry points: `urgencias-demo-synthetic`, `urgencias-demo-deis`,
  `urgencias-server`.
- Optional-dependency extras: `models`, `viz`, `server`, `fetch`, `all`. The
  core install ships only pandas/numpy/pyarrow/holidays/pydantic; gated modules
  raise an actionable error naming the extra to install.
- `py.typed` marker, PyPI classifiers/keywords/URLs, and packaged demo
  datasets so the server and demos run out of the box from an installed wheel.
- CI: lint gate, Python 3.11/3.12 test matrix, build + `twine check`, and a
  core-only install job.

### Fixed

- Default server fixture resolved a repo-relative path (`parents[3]`) that
  escaped `site-packages` in an installed wheel; it now resolves the bundled
  fixture via `importlib.resources`.
- DEIS weekly aggregation (`demos.deis._to_weekly`) now trims partial weeks at
  both series edges, not only a fully-empty trailing week. A most-recent week
  with a missing day (near-real-time reporting lag) was kept and appeared as a
  spurious end-of-series drop that contaminated the backtest.

### Changed

- Unified formatting on `ruff format` (dropped black).

[Unreleased]: https://github.com/nicoveraz/urg-forecast-core/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/nicoveraz/urg-forecast-core/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nicoveraz/urg-forecast-core/releases/tag/v0.1.0
