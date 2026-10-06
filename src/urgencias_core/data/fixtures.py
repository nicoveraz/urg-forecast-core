"""Filesystem path to the DEIS snapshot bundled inside the package.

Resolves via :mod:`importlib.resources`, so it works identically from a source
checkout and an installed wheel.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_DEIS_SNAPSHOT = "deis_demo_snapshot.parquet"


def deis_snapshot_path() -> Path:
    """Frozen offline snapshot of DEIS MINSAL data for the two demo hospitals."""
    resource = resources.files("urgencias_core.data").joinpath("_fixtures", _DEIS_SNAPSHOT)
    return Path(str(resource))


__all__ = ["deis_snapshot_path"]
