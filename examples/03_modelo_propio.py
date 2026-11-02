"""Ejemplo 3: escribir un modelo propio y ver si le gana a los incluidos.

Un modelo es una clase con ``fit(history, target_col)`` y ``predict(horizon)``, que
devuelve ``timestamp, q50, q80, q90, q95``. Esta pronostica cada semana como el promedio
de esa misma semana en los últimos años. Después se compara con el Armónico en muchas
ventanas: ¿gana de forma consistente o fue suerte?

    uv run python examples/03_modelo_propio.py
    uv run python examples/03_modelo_propio.py --codigo 13-100 --ventanas 24

Para usarla desde la terminal, copia la clase a un ``mi_modelo.py`` y corre
``urg-forecast comparar 24-105 -m mi_modelo:PromedioAnual``.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from urgencias_core import compare_models, default_models, load_deis, run_forecast, weekly_series
from urgencias_core.models.harmonic import HarmonicRegression
from urgencias_core.models.protocol import HorizonSpec, future_index


class PromedioAnual:
    """Cada semana futura = promedio de esa misma semana en los últimos ``años``."""

    def __init__(self, años: int = 3) -> None:
        self.años = años

    def fit(self, history: pd.DataFrame, target_col: str) -> None:
        s = history.set_index("timestamp")[target_col].astype(float)
        self.ultima_semana = s.index[-1]
        recientes = s[s.index > s.index[-1] - pd.DateOffset(years=self.años)]
        self.promedio = recientes.groupby(recientes.index.isocalendar().week).mean()
        # Errores que esta regla tuvo en el pasado, para armar los intervalos.
        estimado = pd.Series(s.index.isocalendar().week.to_numpy()).map(self.promedio)
        self.errores = (s.to_numpy() - estimado.to_numpy())[estimado.notna().to_numpy()]

    def predict(self, horizon: HorizonSpec) -> pd.DataFrame:
        fechas = future_index(self.ultima_semana, horizon)
        centro = fechas.isocalendar().week.map(self.promedio).to_numpy(dtype=float)
        salida = pd.DataFrame({"timestamp": fechas})
        for q, columna in zip(horizon.quantiles, horizon.quantile_columns, strict=True):
            # bajo la mediana (q5, q10, q20, si se piden) el error es negativo
            salida[columna] = centro + (np.quantile(self.errores, q) if q != 0.5 else 0.0)
        return salida


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--codigo", default="24-105")
    p.add_argument("--ventanas", type=int, default=36)
    p.add_argument("--offline", action="store_true")
    a = p.parse_args(argv)

    semanal = weekly_series(load_deis([a.codigo], offline=a.offline), a.codigo)

    # 1. ¿Cumple el contrato? Una prueba rápida antes de compararlo.
    m = PromedioAnual()
    m.fit(semanal, "count")
    pred = m.predict(HorizonSpec(grain="W-MON", length=4))
    assert list(pred.columns) == ["timestamp", "q50", "q80", "q90", "q95"]
    assert (pred["q50"] <= pred["q80"]).all() and (pred["q80"] <= pred["q95"]).all()

    # 2. Junto a los modelos por defecto, como lo haría `urg-forecast pronosticar`. Se
    #    pronostica con Ensamble; con select_by="qloss_80" ganaría el de menor pérdida P80.
    modelos = default_models() | {"PromedioAnual": PromedioAnual}
    resultado = run_forecast(semanal, 12, models=modelos)
    print(resultado.backtest[["mae", "qloss_80"]].sort_values("qloss_80").round(1))

    # 3. Contra el Armónico en muchas ventanas de 4 semanas: gana, pierde y veredicto.
    cmp = compare_models(
        semanal,
        ("Armónico", HarmonicRegression),
        ("PromedioAnual", PromedioAnual),
        origins=a.ventanas,
    )
    print(cmp.summary().round(3))
    print(cmp.text())


if __name__ == "__main__":
    main()
