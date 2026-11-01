# Ejemplos

Scripts cortos que se pueden ejecutar, uno por tarea. Cada uno parte de la serie semanal de
un establecimiento y usa solo la API pública del paquete. Todos aceptan `--codigo` (cualquier
código DEIS, por defecto el Hospital de Puerto Montt) y `--offline` (el snapshot incluido,
sin red). La CI los ejecuta en cada cambio, así que funcionan con la versión actual.

| Ejemplo | Responde | Qué muestra |
|---|---|---|
| [`01_pronostico.py`](01_pronostico.py) | ¿Cuántas atenciones vienen? | Cargar datos, serie semanal, `run_forecast`, leer el resultado y guardar el informe |
| [`02_backtest.py`](02_backtest.py) | ¿Qué modelo funciona mejor acá? | `backtest` en muchas ventanas: error por ventana, ventanas ganadas, cobertura del P80 |
| [`03_modelo_propio.py`](03_modelo_propio.py) | ¿Mi modelo le gana a los incluidos? | Escribir un `Forecaster`, probar su contrato y compararlo con `compare_models` |
| [`04_regresor_externo.py`](04_regresor_externo.py) | ¿Una variable externa mejora el pronóstico? | `HarmonicExogenous` con FluNet: rellenar con promedio histórico o con proyección, y medirlo |
| [`05_analisis.py`](05_analisis.py) | ¿Cómo ha sido la demanda? | Resumen anual, nivel, año típico sin la tendencia, comparación interanual y día de la semana |

```bash
uv run python examples/01_pronostico.py
uv run python examples/02_backtest.py --codigo 13-100 --ventanas 24
uv run python examples/03_modelo_propio.py --offline
uv run python examples/04_regresor_externo.py
uv run python examples/05_analisis.py --codigo 13-100
```

Los gráficos y archivos quedan en `./salida-ejemplos/` (`--salida` lo cambia).

Para agregar un ejemplo: un archivo `NN_nombre.py` con una función `main(argv)`, un
docstring que diga qué pregunta responde, y una línea en `CASES` de
`tests/test_examples.py` con argumentos rápidos. Cómo se organiza el paquete y dónde va
cada cosa está en [`docs/arquitectura.md`](../docs/arquitectura.md).
