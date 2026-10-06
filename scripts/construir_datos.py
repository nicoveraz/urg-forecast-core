"""Build the weekly data published on the repository's ``datos`` branch.

Run by .github/workflows/datos.yml. Two steps:

1. ``espejo``: download DEIS once and write the mirror (daily totals per
   establishment + metadata) that ``urg-forecast`` reads by default.
2. ``demo``: run the default forecast for every establishment with enough
   history and write one small JSON per establishment for the site's demo page.

Usage::

    uv run python scripts/construir_datos.py espejo salida/
    uv run python scripts/construir_datos.py demo salida/ --workers 4
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

HORIZON = 26
HISTORY_WEEKS_SHOWN = 156
MIN_MEDIAN_WEEKLY = 10  # skip establishments with almost no activity


def _round(x: float) -> float:
    return float(round(x, 1))


def forecast_one(code: str, out_dir: str, cache_dir: str) -> dict:
    """Forecast one establishment from the local mirror; return its index entry."""
    warnings.filterwarnings("ignore")
    from urgencias_core.data.mirror import mirror_facilities, mirror_rows
    from urgencias_core.pipeline import (
        COVID_EXCLUDE_YEARS,
        NoDataError,
        min_weeks_needed,
        run_forecast,
        weekly_series,
    )

    base = Path(out_dir).resolve().as_uri() + "/"
    fac = mirror_facilities(cache_dir=cache_dir, base_url=base, max_age_hours=1e9)
    info = fac.set_index("codigo").loc[code].to_dict()
    entry = {
        "c": code,
        "n": info.get("nombre", ""),
        "t": info.get("tipo", ""),
        "r": info.get("region", ""),
        "k": info.get("comuna", ""),
        "s": info.get("servicio", ""),
    }
    df = mirror_rows({code}, cache_dir=cache_dir, base_url=base, max_age_hours=1e9)
    df = df[(df["year"] >= 2022) & ~df["year"].isin(COVID_EXCLUDE_YEARS)]
    weekly = weekly_series(df, code)
    if len(weekly) < min_weeks_needed(HORIZON):
        return entry | {"ok": False, "motivo": f"solo {len(weekly)} semanas completas"}
    if weekly["count"].median() < MIN_MEDIAN_WEEKLY:
        return entry | {"ok": False, "motivo": "muy pocas atenciones semanales"}
    try:
        res = run_forecast(weekly, HORIZON, code=code, name=entry["n"])
    except NoDataError as exc:
        return entry | {"ok": False, "motivo": str(exc)}
    except Exception as exc:  # noqa: BLE001 - one bad series must not stop the batch
        return entry | {"ok": False, "motivo": f"error: {str(exc)[:80]}"}

    hist = res.history.tail(HISTORY_WEEKS_SHOWN)
    detail = entry | {
        "ok": True,
        "historia": [
            [str(t.date()), int(v)] for t, v in zip(hist["timestamp"], hist["count"], strict=False)
        ],
        "pronostico": [
            [str(r.timestamp.date()), _round(r.q50), _round(r.q80), _round(r.q95)]
            for r in res.forecast.itertuples()
        ],
        "backtest": [
            {
                "modelo": m,
                "mae": _round(r["mae"]),
                "mape": _round(100 * r["mape"]),
                "p80": _round(r["qloss_80"]),
            }
            for m, r in res.backtest.sort_values("qloss_80").iterrows()
        ],
        "mejor": res.best,
        "cobertura": list(res.coverage80),
        "ventanas": res.backtest_origins,
        "semanas_backtest": res.backtest_weeks,
        "escala": {k: _round(v) for k, v in res.interval_scale.items()},
    }
    (Path(out_dir) / "demo" / f"{code}.json").write_text(
        json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
    )
    return entry | {"ok": True, "m": res.best, "u": str(res.history["timestamp"].iloc[-1].date())}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("paso", choices=["espejo", "demo"])
    ap.add_argument("salida", type=Path)
    ap.add_argument("--cache", default="data/external/deis_cache")
    ap.add_argument("--desde", type=int, default=2021)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--solo", nargs="*", help="limit the demo to these codes")
    args = ap.parse_args()

    if args.paso == "espejo":
        from urgencias_core.data.mirror import build_mirror

        meta = build_mirror(args.salida, start_year=args.desde, cache_dir=args.cache)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return 0

    # demo: read the mirror just built in `salida` (no network), via a local cache dir
    import shutil

    from urgencias_core.data.mirror import FACILITIES_FILE, META_FILE

    (args.salida / "demo").mkdir(parents=True, exist_ok=True)
    local_cache = args.salida / ".cache"
    (local_cache / "espejo").mkdir(parents=True, exist_ok=True)
    for f in ("diario.parquet", FACILITIES_FILE, META_FILE):
        shutil.copy(args.salida / f, local_cache / "espejo" / f)
    fac = pd.read_csv(args.salida / FACILITIES_FILE, dtype=str)
    codes = args.solo or fac["codigo"].tolist()
    index = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(forecast_one, c, str(args.salida), str(local_cache)): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            index.append(fut.result())
            if i % 25 == 0 or i == len(codes):
                print(f"{i}/{len(codes)}", flush=True)
    index.sort(key=lambda e: (e.get("r") or "~", e.get("n") or ""))
    meta = json.loads((args.salida / META_FILE).read_text())
    payload = {"meta": meta, "horizonte": HORIZON, "establecimientos": index}
    (args.salida / "demo" / "indice.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    shutil.rmtree(local_cache)
    ok = sum(e["ok"] for e in index)
    print(f"demo: {ok} con pronóstico, {len(index) - ok} sin datos suficientes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
