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

## Title (form field, auto-extracted from `paper.md`)

> urg-forecast-core: A reference pipeline for emergency department occupancy analytics, forecasting, and Monte Carlo simulation in Chile

## Main subject (form dropdown — type and select the closest match)

The submission is health-services / health-informatics software whose method
core is time-series forecasting and stochastic simulation. Try these in order
and pick the closest option your dropdown offers:

1. **Health informatics** / Medical informatics
2. Medical and health sciences (or Health services research)
3. Applied statistics / Statistics
4. Operations research

## Message to editors (answers the form's specific prompts)

No part of this JOSS paper has been published or submitted to another
peer-reviewed venue. The repository also contains a longer, more detailed
methods manuscript (`paper/preprint.md`) that I may submit to a preprint or
health-informatics venue in the future; it is a separate paper, not this JOSS
submission, and has not been submitted or published anywhere.

Short description: urg-forecast-core is an open-source Python package that turns
visit-level emergency department records into hourly occupancy series,
probabilistic (quantile) forecasts, and Monte Carlo census bands, with a client
for Chile's public DEIS MINSAL open data and a minimal reference dashboard.

This is a new submission — not a resubmission, and not a second JOSS paper about
this software.

Conflicts of interest: none. I am the sole author; there are no financial
conflicts of interest, and I am not aware of any conflict with potential editors
or reviewers. The software is MIT-licensed and is the open foundation of an
emergency-medicine analytics effort (Eunosia), but this submission promotes no
commercial product.

## Notes

- JOSS's `editorialbot` compiles the paper PDF and runs checks automatically
  once the pre-review issue opens; a local PDF build is only a sanity check.
- At acceptance, JOSS asks for the archived version's DOI — provide
  `10.5281/zenodo.21449611`.
