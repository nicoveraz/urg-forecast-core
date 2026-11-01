"""Build the weekly data published on the repository's ``datos`` branch.

Run by .github/workflows/datos.yml. Four steps:

1. ``espejo``: download DEIS once and write the mirror (daily totals per
   establishment + metadata) that ``urg-forecast`` reads by default.
2. ``flunet``: copy Chile's WHO FluNet series (viral circulation) for the example
   regressor model ``ArmónicoFluNet``.
3. ``demo``: run the default forecast for every establishment with enough
   history and write one small JSON per establishment for the site's demo page.
4. ``regresor``: the worked example of adding an external regressor. For the busiest
   establishments, compare Armónico with and without external regressors (holidays from
   the calendar, FluNet viral positivity) over many
   backtest windows (:func:`urgencias_core.eval.compare.compare_models`) and write
   ``demo/regresor.json`` for the demo page. Needs ``flunet`` and ``demo`` first.

Usage::

    uv run python scripts/construir_datos.py espejo salida/
    uv run python scripts/construir_datos.py flunet salida/
    uv run python scripts/construir_datos.py demo salida/ --workers 4
    uv run python scripts/construir_datos.py regresor salida/ --workers 4
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

# Regressor example: candidates compared against BASE on many short windows.
REG_TOP = 40  # busiest establishments analysed (each takes a few minutes)
REG_HORIZON, REG_WINDOWS, REG_STEP = 4, 36, 4
REG_BASE = "Armónico"
REG_CANDIDATES = ("ArmónicoFeriados", "ArmónicoFluNet", "ArmónicoFluNetProy")
POSITIVITY_WEEKS_SHOWN = 156


def _round(x: float) -> float:
    return float(round(x, 1))


def analysis_block(weekly: pd.DataFrame) -> dict:
    """Descriptive analysis for the demo page (see urgencias_core.analysis)."""
    from urgencias_core.analysis import (
        seasonal_profile,
        summary,
        year_over_year,
        yearly_summary,
    )
    from urgencias_core.analysis.report import week_label

    s = summary(weekly)
    prof = seasonal_profile(weekly)
    yoy = year_over_year(weekly).dropna(subset=["change_pct"])
    last_year = weekly["timestamp"].iloc[-1].year
    cur = weekly[weekly["timestamp"].dt.year == last_year]

    def num(x, digits=1):
        return None if pd.isna(x) else float(round(float(x), digits))

    return {
        "nivel": num(s["weekly_mean_last_year"], 0),
        "cambio_nivel": num(s["level_change_pct"]),
        "interanual": num(yoy["change_pct"].iloc[-1]) if len(yoy) else None,
        "amplitud": num(100 * (s["seasonal_amplitude"] - 1), 0),
        "alta": [s["usual_peak_week"], week_label(s["usual_peak_week"])],
        "baja": [s["usual_low_week"], week_label(s["usual_low_week"])],
        "anual": [
            [int(y), int(r["weeks"]), num(r["weekly_mean"], 0), num(r["change_pct"])]
            for y, r in yearly_summary(weekly).iterrows()
        ],
        "tipico": [
            [int(w), num(r["mean"], 0), num(r["low"], 0), num(r["high"], 0), num(r["index"], 3)]
            for w, r in prof.iterrows()
        ],
        "anio": last_year,
        "actual": [
            [int(t.isocalendar()[1]), int(v)]
            for t, v in zip(cur["timestamp"], cur["count"], strict=True)
        ],
    }


_POSITIVITY: pd.DataFrame | None = None  # FluNet positivity, loaded once per worker


def _positivity(out_dir: str) -> pd.DataFrame | None:
    """FluNet positivity from the copy just written to ``out_dir`` (None if missing)."""
    global _POSITIVITY
    if _POSITIVITY is None:
        from urgencias_core.data.flunet import FLUNET_FILE, weekly_positivity

        path = Path(out_dir) / FLUNET_FILE
        if not path.exists():
            return None
        _POSITIVITY = weekly_positivity(pd.read_csv(path, low_memory=False))
    return _POSITIVITY


def regressor_block(weekly: pd.DataFrame, out_dir: str) -> dict:
    """Forecasts of Armónico with and without each example regressor, for the demo toggles.

    Raw quantiles (no calibration) so the only difference between the lines is the
    regressor. ``valores`` holds what each model assumed for the forecast weeks.
    """
    from urgencias_core.models.exogenous import HarmonicExogenous, HarmonicFluNet
    from urgencias_core.models.harmonic import HarmonicRegression
    from urgencias_core.models.protocol import HorizonSpec
    from urgencias_core.models.registry import FLUNET_PROY
    from urgencias_core.regressors import calendar

    spec = HorizonSpec(grain="W-MON", length=HORIZON)
    models: dict = {
        "Armónico": HarmonicRegression,
        "ArmónicoFeriados": lambda: HarmonicExogenous.from_regressor(calendar(), ["holidays"]),
    }
    pos = _positivity(out_dir)
    if pos is not None:
        models["ArmónicoFluNet"] = lambda: HarmonicFluNet(positivity=pos)
        models["ArmónicoFluNetProy"] = lambda: HarmonicFluNet(positivity=pos, **FLUNET_PROY)
    out = {}
    for name, factory in models.items():
        try:
            m = factory()
            m.fit(weekly, "count")
            pred = m.predict(spec)
        except Exception:  # noqa: BLE001 - a failing variant just has no toggle
            continue
        item = {
            "pronostico": [
                [str(r.timestamp.date()), _round(r.q50), _round(r.q80)] for r in pred.itertuples()
            ]
        }
        if hasattr(m, "regressor_path"):
            path = m.regressor_path(spec)
            cols = [c for c in path.columns if c != "timestamp"]
            scale = 1 if name == "ArmónicoFeriados" else 100  # positivity in %
            item["valores"] = [
                [str(t.date())] + [_round(scale * float(r[c])) for c in cols]
                for t, (_, r) in zip(path["timestamp"], path.iterrows(), strict=True)
            ]
            item["columnas"] = cols
        out[name] = item
    return out


def forecast_one(code: str, out_dir: str, cache_dir: str) -> dict:
    """Forecast one establishment from the local mirror; return its index entry."""
    warnings.filterwarnings("ignore")
    from urgencias_core.data.mirror import mirror_facilities, mirror_rows
    from urgencias_core.data.series import COVID_EXCLUDE_YEARS, NoDataError, weekly_series
    from urgencias_core.forecast import min_weeks_needed, run_forecast

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
        "analisis": analysis_block(weekly),
        "regresores": regressor_block(weekly, out_dir),
    }
    (Path(out_dir) / "demo" / f"{code}.json").write_text(
        json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
    )
    return entry | {"ok": True, "m": res.best, "u": str(res.history["timestamp"].iloc[-1].date())}


def _local_cache(salida: Path) -> Path:
    """Copy the mirror just built in ``salida`` into a cache dir, so reads need no network."""
    import shutil

    from urgencias_core.data.flunet import FLUNET_FILE
    from urgencias_core.data.mirror import FACILITIES_FILE, META_FILE

    local = salida / ".cache"
    (local / "espejo").mkdir(parents=True, exist_ok=True)
    for f in ("diario.parquet", FACILITIES_FILE, META_FILE, FLUNET_FILE):
        if (salida / f).exists():
            shutil.copy(salida / f, local / "espejo" / f)
    return local


def _pct(x: float) -> float | None:
    return None if pd.isna(x) else float(round(100 * x, 1))


def compare_one(code: str, out_dir: str, cache_dir: str) -> dict:
    """Paired comparison of the regressor candidates against the base for one establishment."""
    warnings.filterwarnings("ignore")
    from urgencias_core.data.flunet import load_flunet, weekly_positivity
    from urgencias_core.data.mirror import mirror_rows
    from urgencias_core.data.series import COVID_EXCLUDE_YEARS, weekly_series
    from urgencias_core.eval.compare import compare_many
    from urgencias_core.models.exogenous import HarmonicFluNet
    from urgencias_core.models.registry import FLUNET_PROY, available_models

    base = Path(out_dir).resolve().as_uri() + "/"
    df = mirror_rows({code}, cache_dir=cache_dir, base_url=base, max_age_hours=1e9)
    df = df[(df["year"] >= 2022) & ~df["year"].isin(COVID_EXCLUDE_YEARS)]
    weekly = weekly_series(df, code)
    pos = weekly_positivity(load_flunet(cache_dir=cache_dir, base_url=base, max_age_hours=1e9))
    models = available_models()
    fixed = {  # same models as the registry, with the positivity already loaded
        "ArmónicoFluNet": lambda: HarmonicFluNet(positivity=pos),
        "ArmónicoFluNetProy": lambda: HarmonicFluNet(positivity=pos, **FLUNET_PROY),
    }
    out: dict = {"c": code, "candidatos": {}}
    windows = None
    comparisons = compare_many(
        weekly,
        (REG_BASE, models[REG_BASE]),
        {c: fixed.get(c, models.get(c)) for c in REG_CANDIDATES},
        horizon_weeks=REG_HORIZON,
        origins=REG_WINDOWS,
        step=REG_STEP,
    )
    for cand, cmp in comparisons.items():
        s = cmp.summary()
        out["candidatos"][cand] = {
            "veredicto": cmp.verdict,
            **{
                part: {
                    "n": int(r["ventanas"]),
                    "gana": int(r["gana"]),
                    "pierde": int(r["pierde"]),
                    "p": float(round(r["p"], 3)),
                    "mediana": _pct(r["cambio_mediano"]),
                    "total": _pct(r["cambio_total"]),
                }
                for part, r in s.iterrows()
            },
        }
        w = cmp.windows.set_index("origin")
        if windows is None:
            windows = w[["base", "winter"]].copy()
        windows[cand] = w["candidate"]
    if windows is not None:
        out["ventanas"] = [
            [str(t.date()), bool(r["winter"]), _round(r["base"])]
            + [None if pd.isna(r[c]) else _round(r[c]) for c in REG_CANDIDATES]
            for t, r in windows.sort_index().iterrows()
        ]
    return out


def regressor_example(salida: Path, workers: int, top: int) -> int:
    """Write ``demo/regresor.json``: FluNet positivity and the paired comparisons."""
    import shutil

    from urgencias_core.data.flunet import FLUNET_FILE, weekly_positivity
    from urgencias_core.models.exogenous import project_series

    if not (salida / FLUNET_FILE).exists():
        print("regresor: no FluNet copy this week; skipped")
        return 0
    pos = weekly_positivity(pd.read_csv(salida / FLUNET_FILE, low_memory=False))
    pos = pos.dropna(subset=["flu", "rsv"])
    proj = {v: project_series(pos, v, 26) for v in ("flu", "rsv")}
    index = json.loads((salida / "demo" / "indice.json").read_text())["establecimientos"]
    ok = [e["c"] for e in index if e["ok"]]
    # busiest = highest median weekly attendance over the last year shown in each detail
    volume = {}
    for code in ok:
        hist = json.loads((salida / "demo" / f"{code}.json").read_text())["historia"][-52:]
        volume[code] = float(pd.Series([v for _, v in hist]).median())
    codes = sorted(volume, key=volume.get, reverse=True)[:top]
    names = {e["c"]: e for e in index}

    local = _local_cache(salida)
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(compare_one, c, str(salida), str(local)): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            code = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:  # noqa: BLE001 - one bad series must not stop the batch
                print(f"regresor: {code} failed ({str(exc)[:80]})")
                continue
            e = names[code]
            results.append(r | {"n": e["n"], "r": e["r"], "t": e["t"], "vol": volume[code]})
            print(f"regresor {i}/{len(codes)}", flush=True)
    shutil.rmtree(local)
    results.sort(key=lambda r: -r["vol"])
    tail = pos.tail(POSITIVITY_WEEKS_SHOWN)
    payload = {
        "base": REG_BASE,
        "candidatos": list(REG_CANDIDATES),
        "horizonte": REG_HORIZON,
        "ventanas": REG_WINDOWS,
        "paso": REG_STEP,
        "flunet_hasta": str(pos["timestamp"].iloc[-1].date()),
        "positividad": [
            [str(t.date()), _round(100 * f), _round(100 * r)]
            for t, f, r in zip(tail["timestamp"], tail["flu"], tail["rsv"], strict=True)
        ],
        "proyeccion": [
            [str(t.date()), _round(100 * proj["flu"][t]), _round(100 * proj["rsv"][t])]
            for t in proj["flu"].index
        ],
        "establecimientos": results,
    }
    (salida / "demo" / "regresor.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    print(f"regresor: {len(results)} establecimientos comparados")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("paso", choices=["espejo", "flunet", "demo", "regresor"])
    ap.add_argument("salida", type=Path)
    ap.add_argument("--cache", default="data/external/deis_cache")
    ap.add_argument("--desde", type=int, default=2021)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--solo", nargs="*", help="limit the demo to these codes")
    ap.add_argument("--top", type=int, default=REG_TOP, help="regresor: establishments")
    args = ap.parse_args()

    if args.paso == "espejo":
        from urgencias_core.data.mirror import build_mirror

        meta = build_mirror(args.salida, start_year=args.desde, cache_dir=args.cache)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return 0

    if args.paso == "flunet":
        from urgencias_core.data.flunet import FLUNET_FILE, download_flunet, weekly_positivity

        raw = download_flunet("CHL")
        weekly_positivity(raw)  # fail here, not in users' hands, if the format changed
        args.salida.mkdir(parents=True, exist_ok=True)
        raw.to_csv(args.salida / FLUNET_FILE, index=False)
        print(f"FluNet CHL: {len(raw)} rows, up to {raw['ISO_WEEKSTARTDATE'].max()}")
        return 0

    if args.paso == "regresor":
        return regressor_example(args.salida, args.workers, args.top)

    # demo: read the mirror just built in `salida` (no network), via a local cache dir
    import shutil

    from urgencias_core.data.mirror import FACILITIES_FILE, META_FILE

    (args.salida / "demo").mkdir(parents=True, exist_ok=True)
    local_cache = _local_cache(args.salida)
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
    from urgencias_core import __version__

    meta = json.loads((args.salida / META_FILE).read_text())
    meta |= {"version": __version__, "calculado": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")}
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
