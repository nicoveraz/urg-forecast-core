# Security Policy

## Supported versions

`urg-forecast-core` is on a 0.x release series; only the latest published
version on PyPI receives fixes.

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for a suspected security vulnerability.

Report it privately via GitHub's ["Report a vulnerability"](https://github.com/nicoveraz/urg-forecast-core/security/advisories/new)
(Security → Advisories), or by email to **nicovera@quetru.cl**.

Include a description, steps to reproduce, and the affected version. This is a
best-effort, single-maintainer project: you can expect an initial acknowledgment
within a couple of weeks. Fixes are released as a new PyPI version and noted in
`CHANGELOG.md`.

## Scope

This project is reference code for data analysis and forecasting; it does not
handle authentication or process untrusted network input by default. The DEIS
client fetches from a fixed public endpoint. The package never sends data
anywhere.
