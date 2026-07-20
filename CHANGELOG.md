# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (API may
change between minor versions while on 0.x).

## [Unreleased]

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

### Changed

- Unified formatting on `ruff format` (dropped black).

[Unreleased]: https://github.com/nicoveraz/urg-forecast-core/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nicoveraz/urg-forecast-core/releases/tag/v0.1.0
