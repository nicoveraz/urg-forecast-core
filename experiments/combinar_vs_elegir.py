"""Combine the models or pick one? A nested rolling-origin study.

``run_forecast`` picks one model per establishment on 3 backtest windows. A companion
study (``ventanas_backtest.py``) found that this choice does no better than always using
the Armónico. This script asks whether combining the models does better than choosing:
``Ensamble``, the median of AutoARIMA, Armónico and MSTL quantile by quantile.

For each establishment it runs one long rolling backtest (24-week windows every 8 weeks).
At each test window it takes the 3 windows that end before it, as ``run_forecast`` would
on that date, and compares on the test window, which none of them saw:

- ``elegir``: the model with the lowest P80 loss on those windows among the four default
  models (what ``run_forecast`` does today);
- ``elegir+Ensamble``: the same choice with ``Ensamble`` also competing;
- each model used always, ``Ensamble`` included.

Each arm is scored raw and after the calibration ``run_forecast`` applies (factors from
the same 3 windows). ``Ensamble`` is computed from the members' backtest predictions, which
is what ``MedianEnsemble`` returns, without fitting them twice. Results are written as CSV.
Not part of the installed package.

    uv run python experiments/combinar_vs_elegir.py --espejo CARPETA --out resultados/

``CARPETA`` holds the weekly mirror files (``diario.parquet``, ``establecimientos.csv``,
``meta.json``) from the repository's ``datos`` branch.
"""

from __future__ import annotations

import argparse
import tempfile
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from ventanas_backtest import _weekly, busiest, sign_p

LENGTH, STEP, K = 24, 8, 3  # the 3 windows before a test window are i+3, i+4, i+5
BASE = ("SeasonalNaive", "AutoARIMA", "Armónico", "MSTL")
MEMBERS = ("AutoARIMA", "Armónico", "MSTL")  # those of the registry's Ensamble
METRICS = ("qloss_80", "wis", "covered")


def median_combine(preds: list[pd.DataFrame]) -> pd.DataFrame:
    """Quantile-by-quantile median of the members' predictions, as ``MedianEnsemble``."""
    out = pd.DataFrame({"timestamp": preds[0]["timestamp"].to_numpy()})
    for col in [c for c in preds[0].columns if c.startswith("q")]:
        out[col] = np.median(np.vstack([p[col].to_numpy(dtype=float) for p in preds]), axis=0)
    return out


def one(args: tuple[str, str]) -> pd.DataFrame:
    """Per test window and arm: the model used and its raw and calibrated test scores."""
    code, cache = args
    warnings.filterwarnings("ignore")
    from urgencias_core.eval.backtest import backtest
    from urgencias_core.eval.calibration import apply_calibration, calibration_factors
    from urgencias_core.eval.metrics import WIS_QUANTILES, score
    from urgencias_core.models.registry import default_models

    weekly = _weekly(code, cache)
    run = backtest(weekly, default_models(), LENGTH, 40, STEP, quantiles=WIS_QUANTILES)
    wins = run.windows  # most recent first, STEP weeks apart
    for w in wins:
        members = [w.preds[m] for m in MEMBERS if m in w.preds]
        if members:
            w.preds["Ensamble"] = median_combine(members)
    s = run.scores()
    gap = LENGTH // STEP  # first window that ends before the test window starts
    if s.empty or len(wins) < gap + K + 1:  # no history for one test window
        return pd.DataFrame()
    table = s.pivot(index="origin", columns="model", values="qloss_80")
    rows = []
    for i, test in enumerate(wins):
        if i + gap + K > len(wins):
            break
        sel = wins[i + gap : i + gap + K]
        past = table.loc[[w.origin for w in sel]].mean()
        arms = {
            "elegir": past[list(BASE)].idxmin(),
            "elegir+Ensamble": past[[*BASE, "Ensamble"]].idxmin(),
            **{m: m for m in (*BASE, "Ensamble")},
        }
        for arm, model in arms.items():
            if model not in test.preds:
                continue
            pred = test.preds[model]
            fit = [(w.actual, w.preds[model]) for w in sel if model in w.preds]
            factors = calibration_factors([a for a, _ in fit], [p for _, p in fit], WIS_QUANTILES)
            raw = score(test.actual, pred, WIS_QUANTILES)
            cal = score(test.actual, apply_calibration(pred, factors), WIS_QUANTILES)
            rows.append(
                {
                    "code": code,
                    "test_origin": test.origin,
                    "arm": arm,
                    "model": model,
                    "n": raw["n"],
                    **{m: raw[m] for m in METRICS},
                    **{f"{m}_cal": cal[m] for m in METRICS},
                }
            )
    return pd.DataFrame(rows)


def summary(res: pd.DataFrame) -> str:
    """Each arm against ``elegir``, per establishment, on the same test windows."""
    arms = res["arm"].unique().tolist()
    full = res.groupby(["code", "test_origin"])["arm"].transform("size") == len(arms)
    res = res[full]
    lines = [
        f"{res['code'].nunique()} establecimientos, "
        f"{res.groupby('code')['test_origin'].nunique().median():.0f} ventanas de prueba cada uno"
    ]
    for m in ("qloss_80", "qloss_80_cal", "wis", "wis_cal"):
        per = res.groupby(["code", "arm"])[m].mean().unstack("arm")
        lines.append(f"\n{m} frente a 'elegir' (cambio mediano, total, mejor/peor, p):")
        for arm in [a for a in arms if a != "elegir"]:
            rel = per[arm] / per["elegir"] - 1
            better, worse = int((rel < 0).sum()), int((rel > 0).sum())
            total = per[arm].sum() / per["elegir"].sum() - 1
            lines.append(
                f"  {arm:16s} {100 * rel.median():+6.1f} %  {100 * total:+6.1f} %  "
                f"{better:2d}/{worse:2d}  p = {sign_p(better, better + worse):.2f}"
            )
    cov = res.groupby("arm")[["covered", "covered_cal", "n"]].sum()
    lines.append("\ncobertura P80 en prueba (sin calibrar, calibrado):")
    for arm, r in cov.iterrows():
        lines.append(f"  {arm:16s} {r['covered'] / r['n']:.1%}  {r['covered_cal'] / r['n']:.1%}")
    share = res[res["arm"] == "elegir+Ensamble"]["model"].value_counts(normalize=True)
    lines.append(
        "\ncon Ensamble compitiendo, se elige: "
        + ", ".join(f"{k} {v:.0%}" for k, v in share.items())
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--espejo", required=True, help="carpeta con diario.parquet")
    ap.add_argument("--out", type=Path, default=Path("resultados_combinar"))
    ap.add_argument("--top", type=int, default=40, help="establecimientos con más atenciones")
    ap.add_argument("--codigos", type=Path, help="archivo con los códigos a usar, en vez de --top")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    codes = args.codigos.read_text().split() if args.codigos else busiest(args.espejo, args.top)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as cache:
        # mirror_rows reads <cache>/espejo/; point it at the local copy, no download
        (Path(cache) / "espejo").symlink_to(Path(args.espejo).resolve())
        with ProcessPoolExecutor(args.workers) as pool:
            parts = list(pool.map(one, [(c, cache) for c in codes]))
    skipped = [c for c, p in zip(codes, parts, strict=True) if p.empty]
    if skipped:
        print("sin historia suficiente para una ventana de prueba:", ", ".join(skipped))
    res = pd.concat(parts, ignore_index=True)
    res.to_csv(args.out / "combinar_por_prueba.csv", index=False)
    text = summary(res)
    (args.out / "resumen.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
