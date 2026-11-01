"""Readable outputs for the descriptive analysis: Spanish text, one figure, CSV files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from tabulate import tabulate  # noqa: E402

from urgencias_core.analysis.descriptive import (  # noqa: E402
    level,
    seasonal_profile,
    summary,
    weekday_profile,
    year_over_year,
    yearly_summary,
)
from urgencias_core.data.series import COVID_EXCLUDE_YEARS  # noqa: E402

MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
TABLE_FMT = "psql"


def week_label(week: int) -> str:
    """'fines de abril' for the DEIS week that closes on the Monday of ISO week ``week``."""
    monday = date.fromisocalendar(2026, int(week), 1)  # 2026 has 53 ISO weeks
    part = "inicios" if monday.day <= 10 else "mediados" if monday.day <= 20 else "fines"
    return f"{part} de {MONTHS_ES[monday.month - 1]}"


def _round(df: pd.DataFrame, digits: int) -> pd.DataFrame:
    return df.round({c: digits for c in df.select_dtypes("number").columns})


def _pct(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:+.1f}%".replace(".", ",")


def analysis_text(
    weekly: pd.DataFrame,
    name: str,
    code: str,
    source: str = "",
    daily: pd.DataFrame | None = None,
) -> str:
    """Plain-text description of an establishment's demand (what ``urg-forecast analizar``
    prints): level and trend, seasonality, the last weeks against last year, a yearly table
    and, with ``daily``, the weekday profile."""
    s = summary(weekly)
    prof = seasonal_profile(weekly)
    yoy = year_over_year(weekly).dropna(subset=["change_pct"])
    excluded = "–".join(str(y) for y in sorted(COVID_EXCLUDE_YEARS))
    title = f"{name} ({code})"
    lines = [title, "=" * len(title), ""]
    if source:
        lines.append(f"Datos       {source}; atenciones totales por semana")
    lines += [
        f"Historia    {s['first_week']:%Y-%m-%d} a {s['last_week']:%Y-%m-%d} "
        f"({s['weeks']} semanas completas; {excluded} excluidos)",
        "",
        f"Nivel       {s['weekly_mean_last_year']:.0f} atenciones por semana en las últimas 52; "
        f"{_pct(s['level_change_pct'])} respecto de las 52 anteriores",
    ]
    hi, lo = s["usual_peak_week"], s["usual_low_week"]
    lines.append(
        f"Estación    la semana típica más alta ({week_label(hi)}) supera en "
        f"{100 * (s['seasonal_amplitude'] - 1):.0f}% a la más baja ({week_label(lo)})"
    )
    if len(yoy):
        last = yoy.iloc[-1]
        lines.append(
            f"Interanual  últimas 4 semanas: {_pct(last['change_pct'])} respecto de las mismas "
            "semanas del año anterior"
        )

    ys = yearly_summary(weekly)
    rows = [
        [
            f"{y}" + ("" if r["complete"] else " *"),
            f"{r['weeks']}",
            f"{r['weekly_mean']:.0f}",
            _pct(r["change_pct"]),
            f"{r['peak_week']:%Y-%m-%d}",
            f"{r['peak']:.0f}",
        ]
        for y, r in ys.iterrows()
    ]
    lines += [
        "",
        "Por año (* año incompleto: compara el promedio semanal, no el total)",
        tabulate(
            rows,
            headers=[
                "Año",
                "Semanas",
                "Promedio semanal",
                "Cambio",
                "Semana más alta",
                "Atenciones",
            ],
            tablefmt=TABLE_FMT,
            disable_numparse=True,
            colalign=("left", "right", "right", "right", "left", "right"),
        ),
    ]

    top = prof.dropna(subset=["index"]).sort_values("index", ascending=False)
    pick = pd.concat([top.head(4), top.tail(3)])
    rows = [
        [f"{w}", week_label(w), f"{100 * (r['index'] - 1):+.0f}%", f"{r['mean']:.0f}"]
        for w, r in pick.iterrows()
    ]
    lines += [
        "",
        "Año típico: las semanas más altas y más bajas, frente al nivel de su año",
        tabulate(
            rows,
            headers=["Semana", "Termina", "Frente al nivel", "Atenciones promedio"],
            tablefmt=TABLE_FMT,
            disable_numparse=True,
            colalign=("right", "left", "right", "right"),
        ),
    ]
    if daily is not None and len(daily):
        wd = weekday_profile(daily)
        rows = [
            [r["name"], f"{r['mean']:.0f}", f"{100 * (r['index'] - 1):+.0f}%"]
            for _, r in wd.iterrows()
        ]
        lines += [
            "",
            "Día de la semana",
            tabulate(
                rows,
                headers=["Día", "Promedio diario", "Frente al promedio"],
                tablefmt=TABLE_FMT,
                disable_numparse=True,
                colalign=("left", "right", "right"),
            ),
        ]
    lines += ["", "Descriptivo: muestra cómo ha sido la demanda, no por qué ni cómo será."]
    return "\n".join(lines)


def analysis_figure(weekly: pd.DataFrame, name: str) -> plt.Figure:
    """Three panels: series and level, the typical year with the latest year on top, and
    the change against the same weeks of the previous year."""
    lv = level(weekly)
    prof = seasonal_profile(weekly)
    yoy = year_over_year(weekly)
    last_year = lv["timestamp"].dt.year.iloc[-1]
    fig, axes = plt.subplots(3, 1, figsize=(10, 10))

    ax = axes[0]
    ax.plot(lv["timestamp"], lv["count"], color="#999", lw=1, label="Semanal")
    ax.plot(lv["timestamp"], lv["level"], color="#214", lw=2, label="Nivel (promedio 52 semanas)")
    ax.set(title=f"{name}: atenciones semanales", ylabel="Atenciones")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.fill_between(
        prof.index,
        prof["low"],
        prof["high"],
        color="#214",
        alpha=0.15,
        label="Mínimo–máximo de los años",
    )
    ax.plot(prof.index, prof["mean"], color="#214", lw=2, label="Promedio")
    cur = lv[lv["timestamp"].dt.year == last_year]
    ax.plot(
        cur["timestamp"].dt.isocalendar().week,
        cur["count"],
        color="#c33",
        lw=1.6,
        marker="o",
        ms=3,
        label=str(last_year),
    )
    ticks = [date.fromisocalendar(2026, w, 1) for w in range(1, 53)]
    first = [i + 1 for i, d in enumerate(ticks) if d.day <= 7]
    ax.set_xticks(first, [MONTHS_ES[ticks[i - 1].month - 1][:3] for i in first])
    ax.set(title="Año típico por semana", ylabel="Atenciones")
    ax.legend(fontsize=8)

    ax = axes[2]
    ax.axhline(0, color="#777", lw=0.8)
    ax.plot(yoy["timestamp"], yoy["change_pct"], color="#214", lw=1.5)
    ax.set(title="Cambio frente a las mismas 4 semanas del año anterior", ylabel="%")
    for a in axes:
        a.grid(True, alpha=0.25)
    fig.tight_layout()
    return fig


def write_analysis(
    weekly: pd.DataFrame,
    out: Path,
    name: str,
    code: str,
    source: str = "",
    daily: pd.DataFrame | None = None,
) -> list[Path]:
    """Write ``analisis.txt``, ``analisis.png`` and the tables as CSV into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "txt": out / "analisis.txt",
        "png": out / "analisis.png",
        "anual": out / "analisis_anual.csv",
        "perfil": out / "analisis_ano_tipico.csv",
        "nivel": out / "analisis_nivel_interanual.csv",
    }
    paths["txt"].write_text(analysis_text(weekly, name, code, source, daily) + "\n", "utf-8")
    fig = analysis_figure(weekly, name)
    fig.savefig(paths["png"], dpi=110, bbox_inches="tight")
    plt.close(fig)
    _round(yearly_summary(weekly), 2).to_csv(paths["anual"], index_label="year")
    _round(seasonal_profile(weekly), 3).to_csv(paths["perfil"])
    lv = level(weekly).merge(
        year_over_year(weekly)[["timestamp", "last_year", "change_pct"]],
        on="timestamp",
        suffixes=("_level", "_yoy"),
    )
    _round(lv, 2).to_csv(paths["nivel"], index=False)
    if daily is not None and len(daily):
        paths["dia"] = out / "analisis_dia_semana.csv"
        _round(weekday_profile(daily), 3).to_csv(paths["dia"], index_label="weekday")
    return list(paths.values())


__all__ = ["analysis_figure", "analysis_text", "week_label", "write_analysis"]
