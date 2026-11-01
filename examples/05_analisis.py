"""Ejemplo 5: ¿cómo ha sido la demanda? Análisis descriptivo antes de pronosticar.

Nivel y su cambio, el año típico (qué semanas son altas, sin la tendencia), las últimas
semanas frente al año anterior, un resumen por año y el día de la semana. Lo mismo que
``urg-forecast analizar``, pieza por pieza.

    uv run python examples/05_analisis.py
    uv run python examples/05_analisis.py --codigo 13-100
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from urgencias_core import load_deis, weekly_series
from urgencias_core.analysis import (
    level,
    seasonal_profile,
    weekday_profile,
    year_over_year,
    yearly_summary,
)
from urgencias_core.analysis.report import week_label, write_analysis
from urgencias_core.data.series import daily_series, facility_name


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--salida", type=Path, default=Path("salida-ejemplos"))
    a = p.parse_args(argv)

    df = load_deis([a.codigo], offline=a.offline)
    nombre = facility_name(df, a.codigo)
    semanal = weekly_series(df, a.codigo)  # timestamp, count
    pd.set_option("display.width", 120)

    # 1. Por año. El cambio compara las mismas semanas del año anterior, así que un año
    #    a medias (enero a marzo) se compara con enero a marzo.
    anual = yearly_summary(semanal)[["weeks", "weekly_mean", "change_pct", "peak_week"]]
    print(anual.round({"weekly_mean": 0, "change_pct": 1}))

    # 2. Nivel: el promedio de las últimas 52 semanas. Al promediar un año completo
    #    desaparece la estacionalidad y queda la tendencia.
    nivel = level(semanal).dropna(subset=["level"])
    ultimo = nivel.iloc[-1]
    print(f"Nivel actual {ultimo['level']:.0f} por semana ({ultimo['change_pct']:+.1f}% en un año)")

    # 3. Año típico: cada semana frente al nivel de su propio año (index 1,15 = 15% sobre
    #    el nivel), para que el crecimiento no se confunda con la estación.
    perfil = seasonal_profile(semanal).dropna(subset=["index"])
    for semana, fila in perfil.sort_values("index", ascending=False).head(3).iterrows():
        print(f"Semana {semana} ({week_label(semana)}): {100 * (fila['index'] - 1):+.0f}%")

    # 4. Las últimas semanas frente a las mismas del año anterior (sumas de 4 semanas).
    print(year_over_year(semanal).tail(4).round({"change_pct": 1}))

    # 5. Día de la semana: necesita los totales diarios, no los semanales.
    print(weekday_profile(daily_series(df, a.codigo)).round(2))

    # 6. Todo junto: texto, figura y tablas en CSV (lo que escribe `urg-forecast analizar`).
    for archivo in write_analysis(semanal, a.salida / a.codigo, nombre, a.codigo):
        print("escrito:", archivo)


if __name__ == "__main__":
    main()
