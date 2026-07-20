# Contributing

`urg-forecast-core` is an open foundation maintained on a best-effort basis. Fork
freely, adapt it to your hospital, ship it inside your own product. Pull requests
and issues are welcome; while on 0.x the API may change between minor versions.
If you need commercial support or bespoke work on top of this foundation, contact
the author.

All participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting issues and getting support

- **Bugs and feature requests:** open an issue at
  <https://github.com/nicoveraz/urg-forecast-core/issues>. For a bug, include the
  package version (`pip show urg-forecast-core`), Python version, OS, a minimal
  example, and the full traceback.
- **Questions and usage help:** open an issue with the *question* label, or start
  a discussion if the repository has Discussions enabled.
- **Security reports:** see [SECURITY.md](SECURITY.md) — please do not open a
  public issue for a suspected vulnerability.

## Contributing changes

Fork the repository, create a topic branch, and open a pull request against
`main`. Before pushing, make sure the checks below pass locally; CI runs the same
lint, format, test (Python 3.11 and 3.12), build, and core-only-install jobs on
every pull request.

## Development

```bash
uv sync --all-extras --dev   # full toolchain + all optional deps
uv run pytest -q             # tests
uv run ruff check .          # lint
uv run ruff format .         # format (ruff is the single formatter)
pre-commit install           # optional: run lint/format on commit
```

The package uses a src layout. Heavy dependencies live behind extras
(`models`, `viz`, `server`, `fetch`, `all`); modules that need them guard the
import and raise an actionable error. Keep that pattern when adding code that
depends on an optional library.

## Cutting a release

Releases publish to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC) from `.github/workflows/publish.yml` — no API tokens as secrets.

One-time setup: on PyPI, add this repository and the `pypi` environment as a
trusted publisher for the `urg-forecast-core` project. Optionally validate metadata
first by publishing a pre-release (e.g. `0.1.0rc1`) to TestPyPI.

Per release:

1. Bump `version` in `pyproject.toml` (semver).
2. Move the `## [Unreleased]` notes in `CHANGELOG.md` under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading and update the compare links.
3. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

The `publish` workflow then runs tests, verifies the tag matches the package
version, builds, publishes to PyPI, and creates a GitHub Release with the
changelog section as its notes.

## Archiving on Zenodo (citable DOI)

Releases are archived on [Zenodo](https://zenodo.org/) for a citable DOI.
Metadata for the archive comes from `.zenodo.json`; `CITATION.cff` provides the
citation shown on GitHub.

One-time setup:

1. Sign in to Zenodo with GitHub and, under *GitHub* settings, flip the switch
   **on** for the `urg-forecast-core` repository.
2. Cut a release (the tag flow above creates a GitHub Release). Zenodo detects
   the published GitHub Release, archives the source, and mints two DOIs: a
   **concept DOI** (always resolves to the latest version) and a
   **version DOI** (this specific release).

After the first release:

3. Add the concept DOI to `CITATION.cff` (`doi:` field), the README "Citing"
   section (DOI badge), and `paper/paper.md` if submitting to JOSS.

For submitting the software paper (JOSS), the archived Zenodo DOI is required at
submission; draft papers are under `paper/`. Author ORCID and affiliation are
set in `paper/paper.md`, `CITATION.cff`, and `.zenodo.json`; keep them in sync
if authorship changes.
