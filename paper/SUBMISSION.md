# JOSS submission notes

Reference material for submitting `urg-forecast-core` to the Journal of Open
Source Software (https://joss.theoj.org). Not part of the distributed package.

## Submission form values

- **Repository URL:** `https://github.com/nicoveraz/urg-forecast-core`
- **Branch:** `main` (paper at `paper/paper.md`, bibliography `paper/paper.bib`)
- **Software version:** `0.1.0`
- **Archive DOI (this version):** `10.5281/zenodo.21449611`
- **Concept DOI (all versions):** `10.5281/zenodo.21449610`
- **License:** MIT

## Subject / title

Full paper title (auto-extracted from `paper.md`):

> urg-forecast-core: A reference pipeline for emergency department occupancy analytics, forecasting, and Monte Carlo simulation in Chile

Shorter subject line, if a form asks for one:

> Submission: urg-forecast-core — an open pipeline for ED occupancy analytics, forecasting, and Monte Carlo simulation

## Message to editors

Dear JOSS editors,

I would like to submit **urg-forecast-core**, an open-source (MIT) Python package
that turns visit-level emergency department (ED) records into operational
decision support: a visits-to-hourly-occupancy transform, Chile-specific
calendar features, a uniform quantile `Forecaster` interface (seasonal-naive,
`statsforecast`, and LightGBM), an evaluation harness, an empirical
length-of-stay Monte Carlo occupancy simulator, a client for the public DEIS
MINSAL open dataset, and a minimal reference dashboard.

**Statement of need.** ED crowding is a well-documented, patient-safety–relevant
problem, and forecasting ED demand and occupancy is an established basis for
proactive staffing and surge planning. The reusable building blocks, however,
are scattered across papers and site-specific notebooks and are frequently not
installable. urg-forecast-core packages them end-to-end for the Chilean context
while remaining adaptable elsewhere, and demonstrates the workflow on real
national open data (DEIS MINSAL).

**Status.**
- Published on PyPI as `urg-forecast-core` 0.1.0 and archived on Zenodo
  (version DOI 10.5281/zenodo.21449611; concept DOI 10.5281/zenodo.21449610).
- ~3,000 lines across the library, 73 automated tests, CI on Python 3.11 and
  3.12, fully typed (`py.typed`), documented, MIT-licensed, with a code of
  conduct and contributing/support guidelines.

**Scope.** The work sits at the intersection of health-services research and
statistics / operations research (time-series forecasting and stochastic
simulation for capacity planning); please route it to whichever track fits best.

I am the sole author and am not aware of any conflicts of interest with
potential editors or reviewers. The DEIS demonstration is framed strictly as a
methodological illustration and is **not** a clinical or quality evaluation of
any hospital.

Thank you for considering the submission.

Nicolás Vera Zúñiga
ORCID 0009-0007-9249-3736
Eunosia, Frutillar, Chile

## Notes

- JOSS's `editorialbot` compiles the paper PDF and runs checks automatically
  once the pre-review issue opens; a local PDF build is only a sanity check.
- At acceptance, JOSS asks for the archived version's DOI — provide
  `10.5281/zenodo.21449611`.
