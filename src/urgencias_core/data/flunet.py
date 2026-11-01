"""Viral circulation in Chile from WHO FluNet, as an example external regressor.

FluNet is where national influenza centres (in Chile, the ISP) report weekly laboratory
results: specimens processed and detections of influenza, RSV and other respiratory viruses,
split into sentinel and non-sentinel networks since 2020. It is national only (no region or
establishment) and is published with about two weeks of delay.

The weekly workflow copies Chile's series to the repository's ``datos`` branch
(``flunet_chl.csv``), so users read a small file from GitHub instead of querying WHO. With
``source="oms"`` it is downloaded from WHO directly.

Source: WHO FluNet, https://www.who.int/tools/flunet (data reported by the ISP of Chile).
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pandas as pd

from urgencias_core.data.deis import DEFAULT_CACHE_DIR
from urgencias_core.data.mirror import MIRROR_BASE_URL, MirrorUnavailable, _fetch

FLUNET_FILE = "flunet_chl.csv"
WHO_FLUNET_URL = (
    "https://xmart-api-public.who.int/FLUMART/VIW_FNT"
    "?$format=csv&$filter=COUNTRY_CODE%20eq%20%27{country}%27"
)
COLUMNS = [
    "ISO_WEEKSTARTDATE",
    "ORIGIN_SOURCE",
    "SPEC_PROCESSED_NB",
    "INF_ALL",
    "RSV_PROCESSED",
    "RSV",
]


def download_flunet(country: str = "CHL", timeout: float = 120.0) -> pd.DataFrame:
    """Raw FluNet rows for one country (ISO3 code), straight from WHO."""
    resp = httpx.get(WHO_FLUNET_URL.format(country=country), timeout=timeout)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text), low_memory=False)


def load_flunet(
    source: str = "repo",
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    base_url: str = MIRROR_BASE_URL,
    max_age_hours: float = 24,
) -> pd.DataFrame:
    """Raw FluNet rows for Chile: from the repository copy (default) or from WHO."""
    if source == "oms":
        return download_flunet()
    if source != "repo":
        raise ValueError(f"source must be 'repo' or 'oms', not {source!r}")
    path = _fetch(FLUNET_FILE, Path(cache_dir), base_url, max_age_hours)
    return pd.read_csv(path, low_memory=False)


def weekly_positivity(raw: pd.DataFrame) -> pd.DataFrame:
    """Weekly positivity (0-1) for influenza and RSV, sentinel and non-sentinel pooled.

    Returns ``timestamp, flu, rsv, specimens`` with ``timestamp`` aligned to the DEIS weeks
    used everywhere else (W-MON: the 7 days ending on that Monday). A FluNet ISO week
    (Monday-Sunday) is assigned to the DEIS week that shares six of its days, the one ending
    on the following Monday.
    """
    missing = set(COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"FluNet data lacks columns {sorted(missing)}")
    df = raw[COLUMNS].copy()
    start = pd.to_datetime(df["ISO_WEEKSTARTDATE"], errors="coerce", utc=True)
    df["start"] = start.dt.tz_convert(None).dt.normalize()
    df = df.dropna(subset=["start"])
    for c in ("SPEC_PROCESSED_NB", "INF_ALL", "RSV_PROCESSED", "RSV"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # RSV denominators are missing in early years; fall back to all specimens processed.
    df["RSV_PROCESSED"] = df["RSV_PROCESSED"].fillna(df["SPEC_PROCESSED_NB"])
    w = df.groupby("start", as_index=False)[
        ["SPEC_PROCESSED_NB", "INF_ALL", "RSV_PROCESSED", "RSV"]
    ].sum(min_count=1)
    out = pd.DataFrame(
        {
            "timestamp": (w["start"] + pd.Timedelta(days=7)).dt.normalize(),
            "flu": w["INF_ALL"] / w["SPEC_PROCESSED_NB"].where(w["SPEC_PROCESSED_NB"] > 0),
            "rsv": w["RSV"] / w["RSV_PROCESSED"].where(w["RSV_PROCESSED"] > 0),
            "specimens": w["SPEC_PROCESSED_NB"],
        }
    )
    return out.sort_values("timestamp").reset_index(drop=True)


__all__ = [
    "FLUNET_FILE",
    "MirrorUnavailable",
    "download_flunet",
    "load_flunet",
    "weekly_positivity",
]
