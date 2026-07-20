"""Filesystem paths to the datasets bundled inside the package.

These resolve via :mod:`importlib.resources`, so they work identically from a
source checkout and an installed wheel. They back the zero-config defaults for
the reference server and the demo entry points.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_SYNTHETIC_VISITS = "synthetic_ed_visits_demo.parquet"
_DEIS_SNAPSHOT = "deis_demo_snapshot.parquet"


def _fixture(name: str) -> Path:
    resource = resources.files("urgencias_core.data").joinpath("_fixtures", name)
    return Path(str(resource))


def synthetic_visits_path() -> Path:
    """Compact one-year synthetic visit-level fixture (the demo default dataset)."""
    return _fixture(_SYNTHETIC_VISITS)


def deis_snapshot_path() -> Path:
    """Frozen offline snapshot of DEIS MINSAL data for the two demo hospitals."""
    return _fixture(_DEIS_SNAPSHOT)


__all__ = ["synthetic_visits_path", "deis_snapshot_path"]
