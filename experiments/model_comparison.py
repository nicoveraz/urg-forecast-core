"""Rolling-origin comparison of weekly forecasters on live DEIS data.

The evidence behind the default model set (see docs/model-selection.md). Not
part of the installed package. Usage:

    python experiments/model_comparison.py --offline            # snapshot, quick
    python experiments/model_comparison.py --out results/       # live DEIS
"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from urgencias_core.eval.baselines import (
    SeasonalNaiveBaseline,
    StatsForecastWrapper,
    auto_arima,
    auto_ets,
)
from urgencias_core.eval.harness import quantile_loss
from urgencias_core.models.harmonic import HarmonicRegression
from urgencias_core.models.protocol import HorizonSpec
from urgencias_core.pipeline import FAST_ARIMA, facility_name, load_deis, weekly_series

warnings.filterwarnings("ignore")

QS = (0.5, 0.8, 0.9, 0.95)


def mstl_model(trend: str):
    from statsforecast.models import MSTL, AutoARIMA, AutoETS

    tf = AutoETS(model="ZZN") if trend == "ets" else AutoARIMA(season_length=1)
    return StatsForecastWrapper(MSTL(season_length=[52], trend_forecaster=tf), name=f"MSTL_{trend}")


MODELS = {
    "SeasonalNaive": SeasonalNaiveBaseline,
    "AutoARIMA_fast": lambda: auto_arima(season_length=52, **FAST_ARIMA),
    "AutoARIMA_full": lambda: auto_arima(season_length=52),
    "AutoETS": lambda: auto_ets(season_length=52),
    "MSTL_ets": lambda: mstl_model("ets"),
    "MSTL_arima": lambda: mstl_model("arima"),
    "Harmonic_k3": lambda: HarmonicRegression(k=3),
    "Harmonic_k6": lambda: HarmonicRegression(k=6),
}

SEARCH = [
    ("24-105", None),
    ("24-115", None),
    ("23-100", None),
    (None, "Hospital Base Valdivia"),
    (None, "Hospital de Castro"),
    (None, "Sótero del Río"),
    (None, "Hospital del Salvador"),
    (None, "Hospital de Ovalle"),
]


def resolve_codes(offline: bool) -> list[str]:
    if offline:
        return ["24-105", "24-115"]
    from urgencias_core.data.deis import list_facilities

    fac = list_facilities(pd.Timestamp.now().year)
    codes = []
    for code, name in SEARCH:
        if code:
            codes.append(code)
            continue
        hit = fac[fac["facility_name"].str.contains(name, case=False, regex=False)]
        if len(hit):
            codes.append(str(hit["facility_code"].iloc[0]))
            print(f"  {name} -> {hit['facility_code'].iloc[0]} {hit['facility_name'].iloc[0]}")
        else:
            print(f"  {name}: not found")
    return codes


def evaluate(weekly: pd.DataFrame, h: int, origins: int, step: int, models: dict) -> list[dict]:
    rows = []
    n = len(weekly)
    for k in range(origins):
        cut = n - h - k * step
        if cut < 104 + 26:
            break
        train = weekly.iloc[:cut].reset_index(drop=True)
        test = weekly.iloc[cut : cut + h].reset_index(drop=True)
        spec = HorizonSpec(grain="W-MON", length=h)
        for name, factory in models.items():
            t0 = time.time()
            try:
                m = factory()
                m.fit(train, "count")
                p = m.predict(spec)
            except Exception as e:  # noqa: BLE001
                rows.append(
                    {
                        "model": name,
                        "h": h,
                        "origin": str(test.timestamp.iloc[0].date()),
                        "error": str(e)[:80],
                    }
                )
                continue
            y = test["count"].to_numpy(float)
            row = {
                "model": name,
                "h": h,
                "origin": str(test["timestamp"].iloc[0].date()),
                "mae": float(np.mean(np.abs(y - p["q50"].to_numpy()[: len(y)]))),
                "cover80": float(np.mean(y <= p["q80"].to_numpy()[: len(y)])),
                "secs": time.time() - t0,
            }
            ql = [quantile_loss(y, p[f"q{int(q*100)}"].to_numpy()[: len(y)], q) for q in QS]
            row["pinball_mean"] = float(np.mean(ql))
            row["qloss80"] = ql[1]
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("experiment-results"))
    ap.add_argument("--origins", type=int, default=6)
    ap.add_argument("--step", type=int, default=8)
    ap.add_argument("--models", default=",".join(MODELS))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    models = {k: MODELS[k] for k in args.models.split(",")}

    codes = resolve_codes(args.offline)
    df = load_deis(codes, offline=args.offline)
    all_rows = []
    for code in codes:
        weekly = weekly_series(df, code)
        name = facility_name(df, code)
        if len(weekly) < 104 + 26 + 26:
            print(f"skip {code} {name}: {len(weekly)} weeks")
            continue
        weekly.to_csv(args.out / f"weekly_{code}.csv", index=False)
        print(
            f"{code} {name}: {len(weekly)} weeks, last {weekly.timestamp.iloc[-1].date()}",
            flush=True,
        )
        for h in (12, 26):
            rows = evaluate(weekly, h, args.origins, args.step, models)
            for r in rows:
                r.update(code=code, name=name)
            all_rows += rows
        pd.DataFrame(all_rows).to_csv(args.out / "rows.csv", index=False)

    res = pd.DataFrame(all_rows)
    ok = res.dropna(subset=["pinball_mean"]) if "pinball_mean" in res else res
    # Relative skill per facility/horizon: pinball / SeasonalNaive pinball (lower is better)
    base = ok[ok.model == "SeasonalNaive"].groupby(["code", "h"]).pinball_mean.mean()
    agg = (
        ok.groupby(["model", "code", "h"])
        .agg(
            pinball=("pinball_mean", "mean"),
            mae=("mae", "mean"),
            cover80=("cover80", "mean"),
            secs=("secs", "mean"),
        )
        .reset_index()
    )
    agg["rel_pinball"] = agg.apply(lambda r: r.pinball / base.loc[(r.code, r.h)], axis=1)
    agg["rank"] = agg.groupby(["code", "h"]).pinball.rank()
    summary = (
        agg.groupby(["model", "h"])
        .agg(
            rel_pinball=("rel_pinball", "mean"),
            mean_rank=("rank", "mean"),
            cover80=("cover80", "mean"),
            secs=("secs", "mean"),
        )
        .reset_index()
        .sort_values(["h", "rel_pinball"])
    )
    agg.to_csv(args.out / "by_facility.csv", index=False)
    summary.to_csv(args.out / "summary.csv", index=False)
    with pd.option_context("display.width", 200):
        print("\n=== Summary (rel_pinball = pinball / SeasonalNaive, lower is better) ===")
        print(summary.round(3).to_string(index=False))
        errs = res[res.get("error").notna()] if "error" in res else pd.DataFrame()
        if len(errs):
            print(
                "\nErrors:\n",
                errs[["model", "code", "h", "error"]].drop_duplicates().to_string(index=False),
            )


if __name__ == "__main__":
    main()
