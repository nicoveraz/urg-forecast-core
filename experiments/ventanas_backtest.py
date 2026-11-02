"""How many backtest windows does model selection need? A nested rolling-origin study.

``run_forecast`` chooses the model on 3 windows as long as the horizon, 8 weeks apart. This
script asks whether more windows choose better models. For each establishment it runs one
long rolling backtest (24-week windows every 8 weeks, so a window's selection windows sit
exactly on the same grid as in ``run_forecast``). At each test window it chooses a model
with the K windows that end before it (K = 3, 6, 9), as ``run_forecast`` would, and scores
that choice on the test window, which none of the K windows saw. Only test windows where
every K is possible are compared, so all K are judged on the same weeks.

It reports, per K, the P80 loss and WIS of the chosen model relative to K = 3 (median over
establishments, and in how many K beats K = 3), and how often the choice changes from one
test window to the next. Results are written as CSV. Not part of the installed package.

    uv run python experiments/ventanas_backtest.py --espejo CARPETA --out resultados/

``CARPETA`` holds the weekly mirror files (``diario.parquet``, ``establecimientos.csv``,
``meta.json``) from the repository's ``datos`` branch.
"""

from __future__ import annotations

import argparse
import tempfile
import warnings
from concurrent.futures import ProcessPoolExecutor
from math import comb
from pathlib import Path

import pandas as pd

LENGTH, STEP = 24, 8  # selection windows of a test window i are i+3, i+4, ... (24 / 8 = 3)
KS = (3, 6, 9)


def _weekly(code: str, cache: str) -> pd.DataFrame:
    from urgencias_core.data.mirror import mirror_rows
    from urgencias_core.data.series import COVID_EXCLUDE_YEARS, weekly_series

    df = mirror_rows({code}, cache_dir=cache, base_url="", max_age_hours=1e9)
    df = df[(df["year"] >= 2022) & ~df["year"].isin(COVID_EXCLUDE_YEARS)]
    return weekly_series(df, code)


def one(args: tuple[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per test window and K: the chosen model and its test scores; plus all window scores.

    The test scores are given raw and after the calibration ``run_forecast`` applies, with
    the factors estimated on the same K windows used for the choice.
    """
    code, cache = args
    warnings.filterwarnings("ignore")
    from urgencias_core.eval.backtest import backtest
    from urgencias_core.eval.calibration import apply_calibration, calibration_factors
    from urgencias_core.eval.metrics import WIS_QUANTILES, score
    from urgencias_core.models.registry import default_models

    weekly = _weekly(code, cache)
    run = backtest(weekly, default_models(), LENGTH, 40, STEP, quantiles=WIS_QUANTILES)
    s = run.scores()
    wins = run.windows  # most recent first, STEP weeks apart
    if s.empty or len(wins) < LENGTH // STEP + max(KS) + 1:  # no history for one test
        return pd.DataFrame(), pd.DataFrame()
    table = s.pivot(index="origin", columns="model", values="qloss_80")
    rows = []
    gap = LENGTH // STEP  # first window that ends before the test window starts
    for i, test in enumerate(wins):
        if i + gap + max(KS) > len(wins):
            break
        for k in KS:
            sel = wins[i + gap : i + gap + k]
            choice = table.loc[[w.origin for w in sel]].mean().idxmin()
            if choice not in test.preds:
                continue
            pred = test.preds[choice]
            fit = [(w.actual, w.preds[choice]) for w in sel if choice in w.preds]
            factors = calibration_factors([a for a, _ in fit], [p for _, p in fit], WIS_QUANTILES)
            raw = score(test.actual, pred, WIS_QUANTILES)
            cal = score(test.actual, apply_calibration(pred, factors), WIS_QUANTILES)
            rows.append(
                {
                    "code": code,
                    "test_origin": test.origin,
                    "k": k,
                    "model": choice,
                    "n": raw["n"],
                    **{f"{m}": raw[m] for m in ("qloss_80", "wis", "covered")},
                    **{f"{m}_cal": cal[m] for m in ("qloss_80", "wis", "covered")},
                    "factor_80": factors.get("q80", 1.0),
                }
            )
    keep = s[["origin", "model", "qloss_80", "wis", "covered", "n"]].assign(code=code)
    return pd.DataFrame(rows), keep


def busiest(espejo: str, top: int) -> list[str]:
    daily = pd.read_parquet(Path(espejo) / "diario.parquet")
    last = daily[daily["date"] >= daily["date"].max() - pd.Timedelta(days=364)]
    return last.groupby("facility_code", observed=True)["count"].sum().nlargest(top).index.tolist()


def sign_p(wins: int, n: int) -> float:
    k = min(wins, n - wins)
    return min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2**n) if n else 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--espejo", required=True, help="carpeta con diario.parquet")
    ap.add_argument("--out", type=Path, default=Path("resultados_ventanas"))
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
    skipped = [c for c, p in zip(codes, parts, strict=True) if p[0].empty]
    if skipped:
        print("sin historia suficiente para una ventana de prueba:", ", ".join(skipped))
    res = pd.concat([p[0] for p in parts], ignore_index=True)
    res.to_csv(args.out / "ventanas_por_prueba.csv", index=False)
    pd.concat([p[1] for p in parts]).to_csv(args.out / "puntajes_por_ventana.csv", index=False)

    full = res.groupby(["code", "test_origin"])["k"].transform("size") == len(KS)
    res = res[full]  # every K judged on the same test windows
    metrics = ["qloss_80", "wis", "qloss_80_cal", "wis_cal"]
    per = res.groupby(["code", "k"])[metrics].mean().unstack("k")
    n_codes, n_tests = res["code"].nunique(), res["test_origin"].nunique()
    lines = [f"{n_codes} establecimientos, {n_tests} ventanas de prueba"]
    cov = res.groupby("k")[["covered", "covered_cal", "n"]].sum()
    for k, r in cov.iterrows():
        lines.append(
            f"K={k}: cobertura P80 en prueba {r['covered'] / r['n']:.1%} sin calibrar, "
            f"{r['covered_cal'] / r['n']:.1%} calibrado"
        )
    for k in KS[1:]:
        for m in metrics:
            rel = per[(m, k)] / per[(m, 3)] - 1
            better, worse = int((rel < 0).sum()), int((rel > 0).sum())
            lines.append(
                f"K={k} vs K=3, {m}: cambio mediano {100 * rel.median():+.1f} %, "
                f"mejor en {better}, peor en {worse} (p = {sign_p(better, better + worse):.2f})"
            )
    flips = (
        res.sort_values("test_origin")
        .groupby(["code", "k"])["model"]
        .apply(lambda s: (s != s.shift()).iloc[1:].mean())
        .groupby("k")
        .mean()
    )
    for k, f in flips.items():
        lines.append(f"K={k}: el modelo elegido cambia de una ventana de prueba a otra el {f:.0%}")
    text = "\n".join(lines)
    (args.out / "resumen.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
