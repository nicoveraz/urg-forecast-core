"""Data loading, hourly aggregation, and packaged fixtures.

The DEIS MINSAL fetcher/parser lives in :mod:`urgencias_core.data.deis` and is
intentionally NOT re-exported here — importing it requires the ``fetch`` extra.
"""

from urgencias_core.data.fixtures import deis_snapshot_path, synthetic_visits_path
from urgencias_core.data.loader import SchemaError, load_visits
from urgencias_core.data.timeseries import hourly_timeseries

__all__ = [
    "load_visits",
    "SchemaError",
    "hourly_timeseries",
    "synthetic_visits_path",
    "deis_snapshot_path",
]
