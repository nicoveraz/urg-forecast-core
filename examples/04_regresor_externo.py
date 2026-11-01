"""Ejemplo 4: agregar una variable externa (regresor) y medir si mejora el pronóstico.

La variable es la positividad nacional de influenza y VRS (OMS FluNet), pero la receta
sirve para cualquier serie semanal: temperatura, contaminación, vacunación. Son dos pasos:

1. Agregarla sin hacer trampa: ``HarmonicExogenous`` solo usa, en cada ventana, lo que
   ya estaba publicado en esa fecha, y rellena lo que falta con el promedio histórico
   (``"climatology"``) o con una proyección de la propia serie (``"forecast"``).
2. Medir si sirve: ``compare_many`` la compara con el Armónico en las mismas ventanas.

    uv run python examples/04_regresor_externo.py
    uv run python examples/04_regresor_externo.py --codigo 13-100

Necesita red para leer la copia de FluNet del repositorio (el DEIS puede ir --offline).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from urgencias_core import load_deis, weekly_series  # noqa: E402
from urgencias_core.data.flunet import load_flunet, weekly_positivity  # noqa: E402
from urgencias_core.eval.compare import compare_many  # noqa: E402
from urgencias_core.models.exogenous import HarmonicExogenous  # noqa: E402
from urgencias_core.models.harmonic import HarmonicRegression  # noqa: E402
from urgencias_core.models.protocol import HorizonSpec  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105")
    p.add_argument("--ventanas", type=int, default=36)
    p.add_argument("--offline", action="store_true", help="DEIS desde el snapshot incluido")
    p.add_argument("--salida", type=Path, default=Path("salida-ejemplos"))
    a = p.parse_args(argv)

    semanal = weekly_series(load_deis([a.codigo], offline=a.offline), a.codigo)

    # El regresor: una tabla con `timestamp` (lunes de cierre de la semana DEIS) y una
    # columna por variable. weekly_positivity ya la deja así: timestamp, flu, rsv.
    positividad = weekly_positivity(load_flunet())

    def con_virus(futuro: str, rezago: int):
        # FluNet se publica con unas 2 semanas de atraso. La semana t usa la positividad
        # de t - rezago; lo que aún no se publica se rellena según `futuro`.
        return lambda: HarmonicExogenous(
            positividad,
            ["flu", "rsv"],
            lag_weeks=rezago,
            report_delay_weeks=2,
            future=futuro,
        )

    candidatos = {
        "Promedio histórico (rezago 3)": con_virus("climatology", 3),
        "Proyección (rezago 1)": con_virus("forecast", 1),
    }
    resultados = compare_many(
        semanal, ("Armónico", HarmonicRegression), candidatos, origins=a.ventanas
    )
    for cmp in resultados.values():
        print(cmp.text())
        print(cmp.summary().round(3))

    # Qué supuso el modelo para las próximas semanas: dato publicado o proyección.
    modelo = con_virus("forecast", 1)()
    modelo.fit(semanal, "count")
    supuesto = modelo.regressor_path(HorizonSpec(grain="W-MON", length=8))
    print(supuesto.round({"flu": 3, "rsv": 3}))

    a.salida.mkdir(parents=True, exist_ok=True)
    origen = semanal["timestamp"].iloc[-1]
    reciente = positividad[positividad["timestamp"] >= origen - pd.Timedelta(weeks=104)]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for col, etiqueta in (("flu", "Influenza"), ("rsv", "VRS")):
        linea = ax.plot(reciente["timestamp"], 100 * reciente[col], label=etiqueta)[0]
        ax.plot(supuesto["timestamp"], 100 * supuesto[col], "--", color=linea.get_color())
    ax.axvline(origen, color="gray", linestyle=":", label="último dato DEIS")
    ax.set(title="Positividad (FluNet): publicada y lo que supuso el modelo (punteado)", ylabel="%")
    ax.legend()
    ruta = a.salida / "regresor_flunet.png"
    plt.tight_layout()
    plt.savefig(ruta, dpi=120)
    print("escrito:", ruta)


if __name__ == "__main__":
    main()
