"""Ejemplo 4: agregar una variable externa (regresor) y medir si mejora el pronóstico.

Un regresor (``Regressor``) es una tabla semanal más las reglas de su fuente: cuántas
semanas tarda en publicarse y si su futuro se conoce. Vienen dos: la positividad nacional
de influenza y VRS (OMS FluNet, 2 semanas de atraso) y el calendario chileno (feriados,
interferiados, vacaciones escolares: se conoce de antemano). La receta sirve para cualquier
serie semanal: temperatura, contaminación, vacunación. Son dos pasos:

1. Agregarla sin hacer trampa: ``HarmonicExogenous.from_regressor`` solo usa, en cada
   ventana, lo que ya estaba publicado en esa fecha, y rellena lo que falta con el promedio
   histórico (``"climatology"``) o con una proyección de la propia serie (``"forecast"``).
2. Medir si sirve: ``compare_many`` compara cada variante con el Armónico en las mismas
   ventanas.

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
from urgencias_core.eval.compare import compare_many  # noqa: E402
from urgencias_core.models.exogenous import HarmonicExogenous  # noqa: E402
from urgencias_core.models.harmonic import HarmonicRegression  # noqa: E402
from urgencias_core.models.protocol import HorizonSpec  # noqa: E402
from urgencias_core.regressors import Regressor, calendar, flunet  # noqa: E402

# Un regresor propio se declara igual que los incluidos (no se usa en este ejemplo):
TEMPERATURA = Regressor(
    name="temperatura",
    load=lambda: pd.read_csv("temperatura_semanal.csv", parse_dates=["timestamp"]),
    columns=("temp_min",),  # una columna por variable; timestamp = lunes de cierre DEIS
    report_delay_weeks=1,  # se publica con una semana de atraso
)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105")
    p.add_argument("--ventanas", type=int, default=36)
    p.add_argument("--offline", action="store_true", help="DEIS desde el snapshot incluido")
    p.add_argument("--salida", type=Path, default=Path("salida-ejemplos"))
    a = p.parse_args(argv)

    semanal = weekly_series(load_deis([a.codigo], offline=a.offline), a.codigo)

    virus = flunet()  # timestamp, flu, rsv; publicado con 2 semanas de atraso
    positividad = virus.table()

    # Cada variante es una fábrica de modelos (una instancia nueva por ventana).
    candidatos = {
        # La semana t usa la positividad de t - 3; lo no publicado, promedio histórico.
        "FluNet, promedio histórico (rezago 3)": lambda: HarmonicExogenous.from_regressor(
            virus, lag_weeks=3, future="climatology"
        ),
        # La semana t usa t - 1; lo no publicado se proyecta desde la temporada en curso.
        "FluNet, proyección (rezago 1)": lambda: HarmonicExogenous.from_regressor(
            virus, lag_weeks=1, future="forecast"
        ),
        # El calendario se conoce: feriados, interferiados y vacaciones de la misma semana.
        "Calendario": lambda: HarmonicExogenous.from_regressor(calendar()),
    }
    resultados = compare_many(
        semanal, ("Armónico", HarmonicRegression), candidatos, origins=a.ventanas
    )
    for cmp in resultados.values():
        print(cmp.text())
        print(cmp.summary().round(3))

    # Qué supuso el modelo para las próximas semanas: dato publicado o proyección.
    modelo = candidatos["FluNet, proyección (rezago 1)"]()
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
