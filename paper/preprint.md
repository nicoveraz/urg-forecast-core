# urgencias-core: an open reference pipeline for emergency department occupancy analytics, probabilistic forecasting, and Monte Carlo simulation, with a demonstration on Chilean DEIS open data

**Nicolás Vera Zúñiga**¹

¹ Eunosia, Frutillar, Chile

*Draft preprint — v0.1.0. Intended for arXiv/medRxiv or a health-informatics venue.*

---

## Abstract

**Background.** Emergency department (ED) crowding is a global, patient-safety–relevant problem, and short- and medium-horizon forecasting of ED demand and occupancy is a well-established lever for proactive staffing and surge planning. However, the reusable building blocks — a correct visits-to-occupancy transform, locally appropriate calendar features, comparable quantile forecasters, an evaluation harness, and a stochastic occupancy simulator — remain scattered and are often not installable, reproducible, or adapted to a given country's data.

**Objective.** We present `urgencias-core`, an open-source Python package that packages this pipeline end to end for the Chilean context while remaining generic enough to adapt elsewhere, and we demonstrate it on public national data.

**Methods.** The package converts visit-level records to an hourly occupancy census using an event cumulative-sum construction, engineers Chile-specific calendar features, exposes a uniform `Forecaster` interface over a seasonal-naive baseline, classical statistical models (AutoARIMA, AutoETS, AutoTheta, MSTL), and a per-quantile LightGBM model, and scores them with an evaluation harness using pinball (quantile) loss. A Monte Carlo engine propagates forecast uncertainty and an empirical length-of-stay (LOS) sampler into census bands. We ran a 12-week rolling-origin-free holdout backtest of weekly total ED attendances for two hospitals in the Servicio de Salud Reloncaví (Los Lagos, Chile) using the public DEIS MINSAL *Atenciones de Urgencia* dataset.

**Results.** On the holdout, the harness selected different best models per site by P80 pinball loss: AutoARIMA for the high-complexity Hospital de Puerto Montt (mean absolute error [MAE] 204.9 weekly attendances, P80 pinball loss 65.2) and the seasonal-naive baseline for the low-complexity Hospital de Frutillar (MAE 47.2, P80 pinball loss 16.5). Point-accuracy and calibration rankings did not always agree, underscoring the value of selecting on the operationally relevant quantile.

**Conclusions.** `urgencias-core` lowers the barrier between published ED-forecasting methods and runnable, reproducible tooling. It is released under the MIT license, is installable from PyPI, and is archived on Zenodo. The DEIS demonstration is strictly methodological and is **not** an operational, clinical, or quality evaluation of any hospital.

---

## 1. Introduction

ED crowding degrades timeliness and quality of care and is associated with worse patient outcomes [@asplin2003; @hoot2008]. Because much ED demand is statistically regular — driven by day-of-week and hour-of-day cycles, holidays, school calendars, and, in temperate regions, a pronounced winter respiratory season — forecasting attendance and occupancy is a natural basis for proactive staffing, bed management, and surge response. A substantial literature evaluates statistical and machine-learning models for ED attendance and occupancy forecasting [@wargon2009; @jones2008; @whitt2019], and discrete-event and Monte Carlo simulation are established tools for translating demand into capacity decisions [@gul2015].

Despite this, moving from a published method to something a hospital analytics team can run remains difficult. Three recurring frictions are: (i) the visits-to-occupancy transform is easy to get subtly wrong (double counting, grid-boundary errors); (ii) calendar features must reflect the *local* holiday and school calendar and seasonal structure, which country-agnostic tooling does not encode; and (iii) code released with studies is frequently tied to one site's schema, lacks probabilistic (as opposed to point) forecasts, or is not packaged for installation.

`urgencias-core` targets these frictions for Chile specifically. Its contributions are: a correct, reusable occupancy transform; Chilean calendar features; a uniform quantile-`Forecaster` interface spanning a strong baseline, classical models, and gradient boosting; an evaluation harness that enforces that model complexity must earn its keep; an empirical-LOS Monte Carlo occupancy simulator; a client for the public DEIS MINSAL dataset with an offline snapshot for reproducibility; and a minimal reference dashboard. The software is typed, `src`-layout, and split into optional-dependency extras so that the core installs lightly.

## 2. Data

### 2.1 Synthetic visit-level fixture

Because visit-level ED data are sensitive, the package ships a synthetic generator and a bundled synthetic fixture used for demos, tests, and continuous integration. The generator produces per-visit arrival and discharge timestamps, acuity (a five-level triage scale, C1–C5), and disposition, with realistic structure: day-of-week and hour-of-day arrival shapes, an acuity mix dominated by C3/C4, log-normal LOS by acuity (with a boarding tail for C1/C2), a southern-hemisphere winter peak, and holiday effects. Occupancy emerges endogenously from (arrivals, LOS). The packaged demo fixture spans one year (~13,000 visits); the test fixture spans 2022–2024 (~40,000 visits).

### 2.2 DEIS MINSAL open data

For real-data demonstration we use the *Atenciones de Urgencia* open dataset published by the Departamento de Estadísticas e Información de Salud (DEIS), Ministerio de Salud de Chile [@deis], distributed under Chile's open-data framework. The dataset provides aggregated counts per facility, per date, per cause group; it does **not** contain visit-level timestamps, so it supports the forecasting layer but not the visit-level occupancy simulator. We use two hospitals in the Servicio de Salud Reloncaví (Los Lagos region): **Hospital de Puerto Montt** (DEIS code 24-105, high-complexity) and **Hospital de Frutillar** (24-115, low-complexity). These were chosen on geographic and pragmatic grounds (regional reference centers with publicly available data), not on any evaluation of quality.

We model the "SECCIÓN 1. TOTAL ATENCIONES DE URGENCIA" total, summing daily counts to a weekly (`W-MON`) grain. The pandemic years 2020–2021 are excluded by default because their regime is not representative for planning the current period; a corrupted source header in the 2020 file makes it unusable without a bespoke parser in any case. The bundled offline snapshot covers 2021–2026 (through 2026-04-11), yielding 223 weekly observations per site after aggregation.

**Framing.** The DEIS analysis is a methodological demonstration of how the forecasting tools behave on real Chilean hospital data. It is not an operational, clinical, or quality evaluation of either hospital.

## 3. Methods

### 3.1 Visits to hourly occupancy

Given visits with arrival and discharge timestamps, the hourly census is computed with an event cumulative-sum construction: an arrival contributes +1 and a discharge −1 to an event series, which is summed and reindexed onto a regular hourly grid. The same pass yields hourly arrivals, discharges, occupancy decomposed by acuity, and mean LOS. This avoids the boundary and double-counting errors common in ad-hoc interval-overlap implementations.

### 3.2 Calendar features

`features.calendar` exposes Chilean public holidays via the `holidays` library [@holidays], bridge ("sandwich") days, an approximate national school calendar (summer, winter, and Fiestas Patrias breaks), and configurable regional events (e.g., the Semana Musical de Frutillar). These enter the forecasters as covariates and reflect the local structure of ED demand.

### 3.3 Forecasting interface and models

All forecasters implement a common `Forecaster` protocol — `fit(history, target)` and `predict(horizon)` returning median and quantile columns (P50/P80/P90/P95) — parameterized by a grain-agnostic `HorizonSpec` (hourly, daily, weekly, monthly). Implementations are:

- **SeasonalNaiveBaseline**: empirical quantiles conditional on a grain-specific seasonal key (e.g., (day-of-week, hour) for hourly data; ISO week for weekly data), with a global fallback.
- **statsforecast wrappers** [@statsforecast]: AutoARIMA, AutoETS, AutoTheta, and MSTL, mapping the library's prediction-interval API to the standard quantile columns.
- **LGBQuantileForecaster** [@lightgbm; @sklearn]: one LightGBM regressor per quantile with `objective='quantile'`, using calendar features only (purely seasonal, no autoregressive lags), which keeps it grain-agnostic and honest about information availability at forecast time.

### 3.4 Evaluation harness

`eval.harness` trains every registered forecaster, holds out the last *N* periods, and reports MAE, RMSE, MAPE, and pinball (quantile) loss at each quantile. Pinball loss at quantile *q* is

$$L_q(y,\hat{y}) = \frac{1}{n}\sum_i \max\!\big(q\,(y_i-\hat{y}_i),\,(q-1)(y_i-\hat{y}_i)\big),$$

which rewards calibrated quantiles rather than only point accuracy. The harness applies a "complexity must justify itself" rule: a candidate model that does not beat the best baseline by at least a set margin (default 5% on the check quantile, P80) triggers a visible warning, discouraging shipping complex models that add no value.

### 3.5 Empirical LOS sampler and Monte Carlo simulator

`simulation.los_empirical` builds an empirical LOS distribution conditional on (acuity, arrival hour) from visit-level data. `simulation.engine` then, for each replicate, samples future arrivals (from a forecast or a supplied arrival-rate curve), assigns each arrival a sampled LOS, and accumulates the resulting census forward 24 hours. Iterating *M* replicates yields census quantile bands. This propagates both arrival and LOS uncertainty into occupancy, the quantity most relevant to bed and staffing decisions.

### 3.6 Software architecture

The package uses a `src` layout and is fully typed (`py.typed`). Heavy dependencies are optional extras — `models` (LightGBM/statsforecast/scikit-learn), `viz` (matplotlib/tabulate), `server` (FastAPI/uvicorn/Jinja2), and `fetch` (httpx) — so the core installs with only pandas, NumPy [@numpy], PyArrow, `holidays`, and pydantic; pandas [@pandas] underlies the data layer. Modules requiring an absent extra raise an actionable error. Demos and the reference server (server-rendered HTML with base64-embedded matplotlib, no JavaScript) are exposed as console scripts, and demo datasets are bundled so the pipeline runs immediately after installation.

## 4. Results

### 4.1 Synthetic pipeline

On the synthetic fixture, the occupancy transform reproduces the expected diurnal cycle (overnight troughs, evening peaks); the seasonal-naive baseline yields calibrated 48-hour hourly arrival forecasts; and the Monte Carlo simulator produces 24-hour census bands that widen with horizon (illustrated in the repository figures). These serve as end-to-end sanity checks that the components compose correctly.

### 4.2 DEIS 12-week holdout backtest

We held out the last 12 weeks (2026-01-19 to 2026-04-06) as test and trained on the prior weeks, comparing all five forecasters. Selection uses P80 pinball loss (`qloss_80`). Table 1 reports the results.

**Table 1.** Twelve-week holdout metrics for weekly total ED attendances (lower is better; best `qloss_80` per site in bold).

*Hospital de Puerto Montt (24-105, high-complexity)*

| Model | MAE | RMSE | MAPE | qloss_50 | qloss_80 |
|---|---:|---:|---:|---:|---:|
| SeasonalNaive | 199.6 | 261.4 | 0.11 | 99.8 | 129.6 |
| **AutoARIMA** | 204.9 | 245.4 | 0.12 | 102.4 | **65.2** |
| AutoETS | 260.0 | 328.5 | 0.14 | 130.0 | 101.3 |
| AutoTheta | 255.8 | 322.8 | 0.14 | 127.9 | 107.0 |
| MSTL | 191.0 | 213.5 | 0.11 | 95.5 | 78.3 |

*Hospital de Frutillar (24-115, low-complexity)*

| Model | MAE | RMSE | MAPE | qloss_50 | qloss_80 |
|---|---:|---:|---:|---:|---:|
| **SeasonalNaive** | 47.2 | 66.9 | 0.12 | 23.6 | **16.5** |
| AutoARIMA | 62.7 | 74.2 | 0.16 | 31.3 | 22.3 |
| AutoETS | 47.8 | 57.9 | 0.12 | 23.9 | 21.4 |
| AutoTheta | 60.4 | 74.0 | 0.16 | 30.2 | 17.6 |
| MSTL | 59.7 | 72.2 | 0.16 | 29.9 | 19.0 |

Two observations stand out. First, the selected model differs by site: AutoARIMA for Puerto Montt, seasonal-naive for the smaller, noisier Frutillar series — a one-model-fits-all assumption would be wrong for at least one site. Second, point-accuracy and calibration rankings disagree: at Puerto Montt, MSTL has the best MAE/RMSE (191.0 / 213.5) but AutoARIMA has a markedly better P80 pinball loss (65.2 vs 78.3). Because operational planning uses upper quantiles for surge headroom, selecting on `qloss_80` rather than MAE is the appropriate choice, and the harness does so.

The holdout figure for Puerto Montt shows the true values falling inside the P80–P95 band for most weeks, indicating the selected model is reasonably calibrated over the horizon rather than merely accurate on average.

### 4.3 Operational forecast

With the per-site model selected, the demo retrains on all available history and emits a 26-week (≈6-month) weekly forecast — the horizon useful for staffing, budgeting, and supply planning — with quantile bands that widen with horizon as expected.

## 5. Discussion

The results illustrate the intended workflow rather than a definitive accuracy claim: a strong, cheap baseline; a small battery of comparable probabilistic models; selection on the operationally relevant quantile; and uncertainty carried through to the quantity decisions actually depend on. The divergence between point and quantile rankings is a concrete argument for probabilistic evaluation in this domain. The per-site selection result argues against deploying a single fixed model across a network of heterogeneous hospitals.

The empirical-LOS Monte Carlo simulator is, to our knowledge, an unusually accessible packaging of occupancy simulation for ED planning: it needs only visit-level arrival/discharge/acuity data and a forecast, and it returns calibrated census bands rather than a single trajectory.

## 6. Limitations

- **Aggregated DEIS data.** DEIS provides daily counts, not visit-level timestamps, so the occupancy simulator cannot be exercised on DEIS; the real-data demonstration covers the forecasting layer only.
- **LOS vs. boarding.** The LOS sampler does not separate active clinical workup from boarding (waiting for an inpatient bed); distinguishing them requires an admission-decision timestamp not present in the current schema.
- **Calendar approximations.** The school calendar is approximate and varies year to year; regional events are configurable but incomplete.
- **Excluded years and single holdout.** 2020–2021 are excluded by default; the harness uses a single holdout rather than rolling-origin backtesting (a rolling backtest is on the roadmap).
- **Scope.** The DEIS analysis is methodological and not a clinical or quality evaluation; results depend on the snapshot date and should be reproduced against the live source for any operational use.

## 7. Software availability

`urgencias-core` is released under the MIT license. Source: <https://github.com/nicoveraz/urg-forecast-core>. Install: `pip install "urgencias-core[all]"`. Archived releases and a citable DOI are provided via Zenodo (see `CITATION.cff`). The version described here is 0.1.0.

## Acknowledgements

This work uses open data published by DEIS, Ministerio de Salud de Chile, under Chile's open-data framework.

## References

<!-- Rendered from paper.bib. Verify all citation details and DOIs before submission. -->
