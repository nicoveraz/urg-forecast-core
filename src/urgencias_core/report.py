"""Turn a :class:`~urgencias_core.pipeline.ForecastResult` into a readable report.

- :func:`summary_text` — plain-text summary with ASCII tables (what the CLI prints).
- :func:`write_outputs` — the same summary plus CSVs and PNG figures in a folder.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from tabulate import tabulate  # noqa: E402

from urgencias_core.pipeline import COVID_EXCLUDE_YEARS, ForecastResult  # noqa: E402

TABLE_FMT = "psql"  # pure ASCII: + - |
STALE_AFTER_WEEKS = 4

DISCLAIMER = (
    "Aviso: pronóstico con modelos estadísticos de base, sin ajuste local.\n"
    "Sirve como punto de partida, no como herramienta operacional validada."
)


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "establecimiento"


def output_dir(base: Path, result: ForecastResult) -> Path:
    return base / f"{slug(result.code)}_{slug(result.name)}"


def _fmt_date(ts) -> str:
    return ts.strftime("%Y-%m-%d")


def backtest_table(result: ForecastResult) -> str:
    t = result.backtest.sort_values("qloss_80")
    rows = [
        [
            name + (" *" if name == result.best else ""),
            f"{r['mae']:.0f}",
            f"{100 * r['mape']:.1f}",
            f"{r['qloss_80']:.1f}",
        ]
        for name, r in t.iterrows()
    ]
    return tabulate(
        rows,
        headers=["Modelo", "MAE", "MAPE %", "Pérdida P80"],
        tablefmt=TABLE_FMT,
        disable_numparse=True,
        colalign=("left", "right", "right", "right"),
    )


def forecast_table(result: ForecastResult) -> str:
    rows = [
        [_fmt_date(r.timestamp), f"{r.q50:.0f}", f"{r.q80:.0f}", f"{r.q95:.0f}"]
        for r in result.forecast.itertuples()
    ]
    return tabulate(
        rows,
        headers=["Semana (termina)", "P50", "P80", "P95"],
        tablefmt=TABLE_FMT,
        disable_numparse=True,
        colalign=("left", "right", "right", "right"),
    )


def _backtest_title(result: ForecastResult) -> str:
    w, k = result.backtest_weeks, result.backtest_origins
    windows = f"{k} ventanas de {w} semanas" if k > 1 else f"últimas {w} semanas"
    return f"Backtest: {windows}, promedio (el modelo elegido se marca con *)"


def _calibration_line(result: ForecastResult) -> str:
    widened = {c: f for c, f in result.interval_scale.items() if f >= 1.05}
    if not widened:
        return ""
    parts = ", ".join(f"{c.upper()} x{f:.1f}" for c, f in sorted(widened.items()))
    return f"Intervalos del pronóstico ensanchados según ese error: {parts}."


def summary_text(result: ForecastResult, today: date | None = None) -> str:
    today = today or date.today()
    h = result.history
    first, last = h["timestamp"].iloc[0], h["timestamp"].iloc[-1]
    lag_weeks = (today - last.date()).days // 7
    covered, n_bt = result.coverage80
    excluded = "–".join(str(y) for y in sorted(COVID_EXCLUDE_YEARS))

    lines = [
        f"{result.name} ({result.code})",
        "=" * len(f"{result.name} ({result.code})"),
        "",
        f"Datos      {result.source}; atenciones totales por semana",
        f"Historia   {_fmt_date(first)} a {_fmt_date(last)} "
        f"({len(h)} semanas completas; {excluded} excluidos)",
        f"Horizonte  {result.horizon_weeks} semanas",
    ]
    if lag_weeks > STALE_AFTER_WEEKS:
        lines.append(
            f"Atención   los datos terminan hace {lag_weeks} semanas; "
            "el pronóstico parte desde esa fecha, no desde hoy."
        )
    lines += [
        "",
        _backtest_title(result),
        backtest_table(result),
        f"Con {result.best}, el valor real quedó bajo el P80 en {covered} de {n_bt} semanas.",
        *([_calibration_line(result)] if _calibration_line(result) else []),
        *(
            [f"Modelos omitidos por error de ajuste: {', '.join(result.skipped)}."]
            if result.skipped
            else []
        ),
        "",
        f"Pronóstico con {result.best}: atenciones semanales",
        forecast_table(result),
        "P50: valor central. P80/P95: 80% y 95% de probabilidad de no superarlo.",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def _plot_backtest(result: ForecastResult, out: Path) -> None:
    hist = result.history.iloc[: -result.backtest_weeks].tail(52)
    actual = result.backtest_actual
    pred = result.backtest_pred
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hist["timestamp"], hist["count"], color="#777", label="Historia")
    ax.plot(actual["timestamp"], actual["count"], color="#c33", lw=2, label="Real")
    ax.fill_between(pred["timestamp"], pred["q80"], pred["q95"], alpha=0.15, label="P80–P95")
    ax.fill_between(pred["timestamp"], pred["q50"], pred["q80"], alpha=0.28, label="P50–P80")
    ax.plot(pred["timestamp"], pred["q50"], color="#214", lw=1.6, label=f"{result.best} P50")
    _style(ax, f"{result.name}: backtest {result.backtest_weeks} semanas")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)


def _plot_forecast(result: ForecastResult, out: Path) -> None:
    hist = result.history.tail(104)
    fc = result.forecast
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hist["timestamp"], hist["count"], color="#444", label="Historia")
    ax.fill_between(fc["timestamp"], fc["q80"], fc["q95"], alpha=0.15, label="P80–P95")
    ax.fill_between(fc["timestamp"], fc["q50"], fc["q80"], alpha=0.28, label="P50–P80")
    ax.plot(fc["timestamp"], fc["q50"], color="#214", lw=1.8, label="P50")
    ax.axvline(hist["timestamp"].iloc[-1], color="#c33", ls="--", alpha=0.7, lw=0.9)
    _style(ax, f"{result.name}: pronóstico {result.horizon_weeks} semanas ({result.best})")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)


def _style(ax, title: str) -> None:
    ax.set_title(title)
    ax.set_xlabel("Semana")
    ax.set_ylabel("Atenciones semanales")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.figure.autofmt_xdate()


def write_outputs(result: ForecastResult, base: Path, today: date | None = None) -> list[Path]:
    """Write summary, tables and figures to ``base/<code>_<name>/``; return the paths."""
    out = output_dir(base, result)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "resumen": out / "resumen.txt",
        "pronostico_csv": out / "pronostico.csv",
        "backtest_csv": out / "backtest.csv",
        "historia_csv": out / "historia_semanal.csv",
        "pronostico_png": out / "pronostico.png",
        "backtest_png": out / "backtest.png",
    }
    paths["resumen"].write_text(summary_text(result, today) + "\n", encoding="utf-8")

    fc = result.forecast[["timestamp", "q50", "q80", "q90", "q95"]].copy()
    fc[["q50", "q80", "q90", "q95"]] = fc[["q50", "q80", "q90", "q95"]].round(1)
    fc.to_csv(paths["pronostico_csv"], index=False)
    result.backtest.round(4).to_csv(paths["backtest_csv"], index_label="modelo")
    result.history.to_csv(paths["historia_csv"], index=False)

    _plot_forecast(result, paths["pronostico_png"])
    _plot_backtest(result, paths["backtest_png"])
    return list(paths.values())


__all__ = ["DISCLAIMER", "output_dir", "summary_text", "write_outputs"]
