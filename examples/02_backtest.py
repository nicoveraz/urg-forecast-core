"""Ejemplo 2: ¿qué modelo funciona mejor en mi establecimiento?

``run_forecast`` elige con tres ventanas. Para mirar con más calma, ``backtest`` ajusta
cada modelo en muchas ventanas del pasado y entrega el error de cada una, así se ve si
un modelo gana siempre o solo en promedio.

    uv run python examples/02_backtest.py
    uv run python examples/02_backtest.py --codigo 13-100 --ventanas 24 -m Armónico -m MSTL
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from urgencias_core import backtest, load_deis, weekly_series  # noqa: E402
from urgencias_core.models.registry import resolve_models  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105")
    p.add_argument("-m", "--modelo", action="append", help="modelo (repetible); por defecto los 4")
    p.add_argument("-H", "--semanas", type=int, default=4, help="largo de cada ventana")
    p.add_argument("--ventanas", type=int, default=12)
    p.add_argument("--paso", type=int, default=8, help="semanas entre ventanas")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--salida", type=Path, default=Path("salida-ejemplos"))
    a = p.parse_args(argv)

    semanal = weekly_series(load_deis([a.codigo], offline=a.offline), a.codigo)
    modelos = resolve_models(a.modelo)  # nombres -> fábricas; None = los 4 por defecto

    # Cada ventana entrena con todo lo anterior a su origen y se evalúa en las
    # `semanas` siguientes. Ninguna ventana ve el futuro de otra.
    corrida = backtest(semanal, modelos, length=a.semanas, origins=a.ventanas, step=a.paso)
    errores = corrida.scores()  # una fila por (ventana, modelo)

    resumen = errores.groupby("model").agg(
        perdida_p80=("qloss_80", "mean"),
        mae=("mae", "mean"),
        cobertura_p80=("covered", "sum"),
        semanas=("n", "sum"),
    )
    resumen["cobertura_p80"] = resumen["cobertura_p80"] / resumen["semanas"]
    # Cuántas veces fue cada modelo el mejor de su ventana.
    mejor = errores.loc[errores.groupby("origin")["qloss_80"].idxmin(), "model"]
    resumen["ventanas_ganadas"] = mejor.value_counts().reindex(resumen.index, fill_value=0)
    print(f"{len(corrida.windows)} ventanas de {a.semanas} semanas")
    print(resumen.sort_values("perdida_p80").round(2))
    if corrida.failed:
        print("fallaron:", corrida.failed)

    a.salida.mkdir(parents=True, exist_ok=True)
    tabla = errores.pivot(index="origin", columns="model", values="qloss_80")
    ax = tabla.plot(marker="o", figsize=(9, 4))
    ax.set(title=f"Pérdida P80 por ventana, {a.codigo}", xlabel="origen", ylabel="pérdida P80")
    ruta = a.salida / f"backtest_{a.codigo}.png"
    plt.tight_layout()
    plt.savefig(ruta, dpi=120)
    print("escrito:", ruta)


if __name__ == "__main__":
    main()
