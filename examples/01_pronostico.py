"""Ejemplo 1: pronóstico semanal de un establecimiento, paso a paso.

Lo mismo que hace ``urg-forecast pronosticar``, desde Python: cargar los datos, armar la
serie semanal, comparar modelos en un backtest y pronosticar con el mejor.

    uv run python examples/01_pronostico.py                    # Hospital de Puerto Montt
    uv run python examples/01_pronostico.py --codigo 13-100 -H 12
    uv run python examples/01_pronostico.py --offline          # snapshot incluido, sin red
"""

from __future__ import annotations

import argparse
from pathlib import Path

from urgencias_core import load_deis, run_forecast, weekly_series
from urgencias_core.data.series import facility_name
from urgencias_core.report import summary_text, write_outputs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105", help="código DEIS (urg-forecast buscar)")
    p.add_argument("-H", "--horizonte", type=int, default=26, help="semanas a pronosticar")
    p.add_argument("--offline", action="store_true", help="usar el snapshot incluido")
    p.add_argument("--salida", type=Path, default=Path("salida-ejemplos"))
    a = p.parse_args(argv)

    # 1. Datos: las filas DEIS del establecimiento. Por defecto vienen de la copia
    #    semanal del repositorio; --offline usa el snapshot que trae el paquete.
    df = load_deis([a.codigo], offline=a.offline)
    nombre = facility_name(df, a.codigo)

    # 2. La serie semanal: un DataFrame con `timestamp` (el lunes que cierra cada semana)
    #    y `count` (atenciones). Es la entrada de todo lo demás.
    semanal = weekly_series(df, a.codigo)
    print(f"{nombre}: {len(semanal)} semanas completas, de {semanal.timestamp.min():%Y-%m-%d}")

    # 3. Backtest y pronóstico: cada modelo se evalúa en varias ventanas del pasado,
    #    se elige el de menor pérdida P80 y se pronostica con él.
    resultado = run_forecast(
        semanal, a.horizonte, code=a.codigo, name=nombre, source=df.attrs["source"]
    )

    # 4. El resultado son DataFrames: error por modelo y pronóstico con sus cuantiles.
    print(resultado.backtest[["mae", "qloss_80"]].round(1))
    print(resultado.forecast.head(4).round(0))

    # 5. El mismo resumen y los archivos que entrega el comando.
    print(summary_text(resultado))
    for archivo in write_outputs(resultado, a.salida):
        print("escrito:", archivo)


if __name__ == "__main__":
    main()
