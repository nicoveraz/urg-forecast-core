# Registro de cambios

Los cambios relevantes del proyecto se documentan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/) (mientras esté en 0.x, la
API puede cambiar entre versiones menores).

## [Sin publicar]

## [0.2.0] - 2026-10-06

El alcance se acota a una sola tarea: pronóstico semanal de atenciones de
urgencia con datos públicos del DEIS MINSAL, como base para construir encima.
**Rompe compatibilidad:** fija `urg-forecast-core<0.2` si dependes de los
módulos eliminados.

### Agregado

- Comando `urg-forecast` con `demo`, `buscar` (código DEIS de un
  establecimiento), `pronosticar` (backtest y pronóstico para cualquier
  establecimiento) y `modelos` (lista de modelos). Imprime un resumen con tablas
  ASCII y guarda CSV y figuras en una carpeta por establecimiento.
- Horizonte configurable: `-H 12`, `12s` (semanas) o `6m` (meses).
- Backtest con varias ventanas: tres, tan largas como el horizonte (máximo 26
  semanas) y separadas por 8 semanas; se usa el modelo con menor pérdida por
  cuantil P80 promedio. Los modelos que fallan se omiten y se informan.
- Modelos por defecto: SeasonalNaive (referencia), AutoARIMA, Armónico
  (`HarmonicRegression`: tendencia + términos de Fourier anuales + ARIMA en los
  residuos) y MSTL, elegidos a partir de una comparación con datos DEIS en vivo
  de siete hospitales (`docs/seleccion-de-modelos.md`,
  `experiments/model_comparison.py`).
- Modelos extra para experimentar, con `-m`: TBATS, Theta, Ensamble
  (`MedianEnsemble`, mediana por cuantil) y ArmónicoFeriados (feriados chilenos
  en día hábil como covariable, `holidays_per_week`). Documentados en
  `docs/modelos.md`.
- `-m/--modelo` (repetible): modelos incluidos o uno propio como `modulo:Clase`
  importable desde la carpeta actual (`pipeline.resolve_models`). Los nombres
  no distinguen mayúsculas ni tildes.
- Calibración de intervalos: las bandas del pronóstico se ensanchan según el
  error del backtest del modelo elegido cuando ahí resultaron estrechas
  (`pipeline.calibration_factors`, `apply_calibration`); `--sin-calibrar` lo
  desactiva.
- `urg-forecast demo` descarga los datos DEIS más recientes y usa el snapshot
  incluido si no hay conexión; el resumen indica la fuente y avisa si los datos
  tienen más de cuatro semanas.
- `urgencias_core.pipeline` (`load_deis`, `weekly_series`, `run_forecast`,
  `parse_horizon`) y `urgencias_core.report`.
- `data.deis.facility_code_variants`, `facilities_in_file`, `list_facilities` y
  `deis_reachable`. Los códigos se aceptan como `24-105` o `124105`.
- `HarnessReport.predictions`: predicciones de cada modelo en el holdout.
- `--cache CARPETA` en todos los subcomandos y la variable de entorno
  `URG_FORECAST_CACHE` para elegir dónde se guardan los ZIP del DEIS (por
  defecto sigue siendo `./data/external/deis_cache`, relativo a la carpeta
  actual); `load_deis` suma el argumento `cache_dir`.
- `--help` por subcomando con ejemplos, un "flujo típico" y los códigos de
  salida en la ayuda general, y una nota de alcance en cada pantalla de ayuda.

### Cambiado

- Documentación primero en español: `README.md` en español y `README.en.md`
  como traducción; `CONTRIBUTING.md`, `SECURITY.md`, este registro y las
  plantillas de issues en español.
- Una sola instalación, sin extras: statsforecast, httpx, matplotlib y tabulate
  pasan a ser dependencias base; pydantic ya no se necesita.
- El archivo DEIS del año anterior se vuelve a descargar semanalmente hasta
  marzo, porque el DEIS lo sigue corrigiendo.
- AutoARIMA usa por defecto una búsqueda acotada (~1 s en vez de ~20 s por
  ajuste con estacionalidad de 52 semanas).
- Se muestra el nombre más reciente del establecimiento; los años DEIS omitidos
  generan mensajes breves en español.
- `--version` usa la acción estándar de argparse; las pantallas de ayuda están
  completamente en español (títulos de sección y `-h`).
- Los README incluyen una referencia de comandos (opciones, caché, códigos de
  salida) y la sección "Una base, no un producto" con lo que conviene revisar
  antes de usar un pronóstico.
- Estado en PyPI: `3 - Alpha`.

### Eliminado

Salen de este repositorio:

- AutoETS de la comparación por defecto: con periodo de 52 semanas statsforecast
  descarta su estacionalidad y el pronóstico queda plano.
- Carga de datos por atención y serie horaria de ocupación (`data.loader`,
  `data.timeseries`) y el fixture sintético.
- Simulación Monte Carlo de censo (`simulation`).
- Dashboard de referencia (`server`) y su archivo de configuración.
- Modelo LightGBM por cuantiles (`models.lgb_quantile`) y cliente Open-Meteo
  (`features.weather`).
- Comandos `urgencias-demo-synthetic`, `urgencias-demo-deis` y
  `urgencias-server`, el paquete `demos` y la carpeta `scripts/`.
- Extras opcionales (`models`, `viz`, `server`, `fetch`, `all`).
- Borradores de artículos en `paper/` y `docs/decisions.md`.

## [0.1.0] - 2026-07-20

Primera versión pública: el pipeline de referencia empaquetado para `pip install`.

### Agregado

- Librería base: de atenciones a serie horaria de ocupación (suma acumulada de
  eventos), variables de calendario chileno, muestreo empírico de estadía,
  simulación Monte Carlo de ocupación, protocolo `Forecaster`, modelos
  seasonal-naive / statsforecast / LightGBM por cuantiles y arnés de evaluación.
- Cliente DEIS MINSAL *Atenciones de Urgencia* con snapshot offline incluido en
  el paquete.
- Servidor de referencia mínimo en FastAPI con gráficos generados en el servidor.
- Comandos de consola: `urgencias-demo-synthetic`, `urgencias-demo-deis`,
  `urgencias-server`.
- Extras opcionales: `models`, `viz`, `server`, `fetch`, `all`. La instalación
  base incluye solo pandas/numpy/pyarrow/holidays/pydantic; los módulos que
  necesitan un extra dan un error que indica cuál instalar.
- Marcador `py.typed`, metadatos de PyPI y datos de demostración incluidos, para
  que el servidor y los demos funcionen desde el wheel instalado.
- CI: lint, tests en Python 3.11/3.12, build + `twine check` y prueba de
  instalación base.

### Corregido

- El fixture por defecto del servidor se resolvía con una ruta relativa al
  repositorio (`parents[3]`) que salía de `site-packages` en un wheel
  instalado; ahora se resuelve con `importlib.resources`.
- La agregación semanal DEIS (`demos.deis._to_weekly`) ahora descarta semanas
  incompletas en ambos extremos de la serie. Una última semana con un día
  faltante (rezago de reporte) se conservaba y aparecía como una caída falsa al
  final que contaminaba el backtest.

### Cambiado

- Formato unificado con `ruff format` (se dejó black).

[Sin publicar]: https://github.com/nicoveraz/urg-forecast-core/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/nicoveraz/urg-forecast-core/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nicoveraz/urg-forecast-core/releases/tag/v0.1.0
