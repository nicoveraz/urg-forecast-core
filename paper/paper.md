---
title: 'urgencias-core: A reference pipeline for emergency department occupancy analytics, forecasting, and Monte Carlo simulation in Chile'
tags:
  - Python
  - emergency medicine
  - health services research
  - time series forecasting
  - Monte Carlo simulation
  - capacity planning
  - Chile
authors:
  - name: Nicolás Vera Zúñiga
    orcid: 0000-0000-0000-0000  # TODO: replace with real ORCID
    affiliation: 1
affiliations:
  - name: Eunosia  # TODO: confirm full institutional affiliation
    index: 1
date: 20 July 2026
bibliography: paper.bib
---

# Summary

`urgencias-core` is an open-source Python package that turns visit-level
emergency department (ED) records into operational decision support. It
implements an end-to-end reference pipeline: it converts a table of visits
(one row per patient, with arrival and discharge timestamps) into an hourly
occupancy census, engineers Chile-specific calendar features, produces
probabilistic (quantile) forecasts of arrivals and occupancy under a single
`Forecaster` interface, and runs a Monte Carlo census simulator that propagates
forecast uncertainty and empirical length-of-stay (LOS) into 24-hour-ahead
census bands. A reader for the public DEIS MINSAL *Atenciones de Urgencia*
open dataset lets the same tools run on real Chilean hospital data, and a
minimal, dependency-light web server renders the pipeline's outputs as a
dashboard. The package ships typed code, packaged demo datasets, and console
entry points so that the full pipeline runs immediately after installation.

# Statement of need

ED crowding is a persistent, patient-safety–relevant problem worldwide
[@asplin2003; @hoot2008], and quantitative forecasting of ED demand and
occupancy is a well-studied lever for proactive staffing and surge planning
[@wargon2009; @jones2008; @whitt2019]. Yet the path from published methods to
something a hospital analytics team can actually run is long: the useful
building blocks (a correct visits-to-occupancy transform, calendar features
that reflect the local holiday and school calendar, quantile forecasters with
comparable interfaces, an evaluation harness, and a stochastic occupancy
simulator) are scattered across papers and notebooks, and code released
alongside studies is frequently tied to a single site's data schema or is not
installable at all.

`urgencias-core` addresses this gap for the Chilean context specifically, while
remaining generic enough to adapt elsewhere. It provides:

- **A correct, reusable occupancy transform.** Hourly census is derived from
  arrival/discharge events via a cumulative-sum construction (+1 at arrival,
  −1 at discharge, reindexed onto the hourly grid), avoiding the double-counting
  and boundary errors common in ad-hoc implementations.
- **Local calendar features.** Chilean public holidays (via `holidays`
  [@holidays]), bridge days, the school calendar, and configurable regional
  events are exposed as model features, because ED demand in Chile is strongly
  shaped by these and by the southern-hemisphere winter respiratory season.
- **A uniform forecasting interface.** A `Forecaster` protocol wraps a
  seasonal-naive empirical-quantile baseline, `statsforecast` models
  (AutoARIMA, AutoETS, AutoTheta, MSTL) [@statsforecast], and a per-quantile
  LightGBM regressor [@lightgbm; @sklearn], all producing the same quantile
  columns. An evaluation harness scores them side by side with a built-in
  "complexity must justify itself" warning: a candidate that does not beat the
  baselines by a set margin should not ship.
- **A Monte Carlo occupancy simulator.** Future arrivals sampled from a
  forecast are combined with an empirical LOS sampler conditional on
  (acuity, arrival hour) to produce census uncertainty bands 24 hours ahead —
  the basis for shift and surge decisions [@gul2015].
- **Real-data reproducibility.** A DEIS MINSAL client fetches and caches the
  national open dataset, with a bundled offline snapshot for reproducible runs.

The package is built for practitioners and health-services researchers: it uses
a `src` layout, is fully typed (`py.typed`), splits heavy dependencies into
optional extras so the core installs lightly, and exposes the demos and server
as console scripts. On a 12-week holdout of real weekly attendance for two Los
Lagos hospitals, the harness selects and validates different best models per
site (\autoref{fig:holdout}), illustrating both the workflow and the value of
per-site model selection rather than a one-model-fits-all assumption. The DEIS
demo is framed strictly as a methodological demonstration and is **not** an
operational, clinical, or quality evaluation of any hospital.

![Twelve-week holdout backtest of weekly ED attendance at Hospital de Puerto
Montt (real DEIS MINSAL data). The harness selects `AutoARIMA` here; the true
values fall inside the P80–P95 band for most weeks. Model selection is repeated
per site.\label{fig:holdout}](figures/deis_holdout_puerto_montt.png)

# Functionality and use

After `pip install "urgencias-core[all]"`, three commands run the pipeline on
packaged data and write figures and tables:

```bash
urgencias-demo-synthetic       # visits -> occupancy -> forecast -> simulation
urgencias-demo-deis --offline  # forecasting on real DEIS hospital data
urgencias-server               # minimal dashboard at http://127.0.0.1:8000
```

The library API is organized into `data` (loader, timeseries, DEIS client),
`features` (calendar, weather), `models` (the `Forecaster` protocol and
LightGBM quantile model), `eval` (baselines and the evaluation harness),
`simulation` (empirical LOS sampler and Monte Carlo engine), and `server`.
Optional-dependency extras (`models`, `viz`, `server`, `fetch`) keep the core
install minimal; modules that need a heavier library raise an actionable error
naming the extra to install.

`urgencias-core` is the open foundation of Eunosia, a clinical AI platform for
emergency medicine, and is intended both as directly usable tooling and as a
starting point that a hospital can clone and adapt to its own data.

# Acknowledgements

This work uses open data published by the Departamento de Estadísticas e
Información de Salud (DEIS), Ministerio de Salud de Chile, under Chile's open
data framework.

# References
