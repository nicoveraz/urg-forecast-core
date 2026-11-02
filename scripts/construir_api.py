"""Build the developer reference page (sitio/src/data/api.json) from the package itself.

Each entry pairs a short explanation in Spanish with an example that is **executed** here,
against the offline DEIS snapshot bundled with the package, so the code and its output on
the page are real. Signatures come from ``inspect.signature``, so they follow the code.
``tests/test_api_docs.py`` runs every example and fails if a documented signature changes
without regenerating the page.

    uv run python scripts/construir_api.py            # writes sitio/src/data/api.json
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import json
import sys
import textwrap
import warnings
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sitio" / "src" / "data" / "api.json"
MAX_OUTPUT_LINES = 18


@dataclass
class Entry:
    """One function or class on the page."""

    id: str
    target: str  # "module:attr" or "module:Class.method"; "" for concept entries
    title: str
    text: str  # Spanish explanation (markdown-light: `code` and **bold**)
    params: list[tuple[str, str]] = field(default_factory=list)
    returns: str = ""
    example: str = ""
    run: bool = True  # False for examples that need the network


@dataclass
class Section:
    id: str
    title: str
    text: str
    entries: list[Entry]


SETUP = """
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option("display.width", 74)
pd.set_option("display.max_columns", 7)
pd.set_option("display.precision", 1)
"""

SECTIONS = [
    Section(
        "inicio",
        "Primeros pasos",
        "Todo el paquete trabaja con DataFrames de pandas. Los ejemplos de esta página se "
        "ejecutan tal cual, en orden, con el snapshot del DEIS que trae el paquete "
        "(`offline=True`: Hospital de Puerto Montt y Hospital de Frutillar), así que puedes "
        "copiarlos y obtener lo mismo. Sin `offline=True` leen la copia semanal del "
        "repositorio, con cualquier establecimiento.",
        [
            Entry(
                "instalar",
                "",
                "Instalar",
                "Python 3.11 o 3.12. Instala el paquete desde PyPI; trae el comando "
                "`urg-forecast` y la biblioteca `urgencias_core`. Las funciones de uso común "
                "se importan directo desde `urgencias_core`.",
                example=(
                    "# pip install urg-forecast-core\n"
                    "import urgencias_core\n"
                    "print(urgencias_core.__version__)"
                ),
            ),
            Entry(
                "serie",
                "",
                "La serie semanal",
                "Casi todo recibe la misma entrada: un DataFrame con `timestamp` (el lunes que "
                "cierra cada semana DEIS: los 7 días que terminan ese lunes) y `count` "
                "(atenciones). Solo semanas completas; 2020 y 2021 quedan fuera por la "
                "pandemia. Si traes tus propios datos, arma ese mismo DataFrame y todo lo "
                "demás funciona igual.",
                example=(
                    "from urgencias_core import load_deis, weekly_series\n\n"
                    'df = load_deis(["24-105"], offline=True)\n'
                    'semanal = weekly_series(df, "24-105")\n'
                    "print(semanal.tail(3))"
                ),
            ),
        ],
    ),
    Section(
        "datos",
        "Datos",
        "De dónde vienen las series: el DEIS (copia semanal del repositorio, archivos "
        "completos o snapshot incluido) y el listado de establecimientos.",
        [
            Entry(
                "load_deis",
                "urgencias_core.data.series:load_deis",
                "load_deis",
                "Filas DEIS (diarias, por causa y grupo de edad) de uno o más "
                "establecimientos. Acepta el código en cualquiera de sus formas (`24-105` o "
                "`124105`). La fuente usada queda en `df.attrs['source']`.",
                params=[
                    ("codes", "lista de códigos DEIS"),
                    ("start_year", "primer año (por defecto 2022; 2020-2021 siempre se excluyen)"),
                    ("offline", "usar el snapshot incluido, sin red"),
                    ("source", '`"repo"` (copia semanal, liviana) o `"deis"` (archivos completos)'),
                    ("cache_dir", "dónde guardar las descargas"),
                ],
                returns="DataFrame con `date`, `facility_code`, `facility_name`, `cause_group`, "
                "`age_group`, `count`. Lanza `NoDataError` si no hay datos.",
                example=(
                    'df = load_deis(["24-105"], offline=True)\n'
                    'print(df.attrs["source"])\n'
                    'print(len(df), "filas", list(df.columns))'
                ),
            ),
            Entry(
                "weekly_series",
                "urgencias_core.data.series:weekly_series",
                "weekly_series",
                "Las atenciones totales de un establecimiento por semana DEIS. Recorta las "
                "semanas incompletas de los extremos: la última semana suele llegar con "
                "días faltantes y parecería una caída.",
                params=[("df", "salida de `load_deis`"), ("code", "código DEIS")],
                returns="DataFrame `timestamp, count`.",
                example='semanal = weekly_series(df, "24-105")\nprint(len(semanal), "semanas")',
            ),
            Entry(
                "daily_series",
                "urgencias_core.data.series:daily_series",
                "daily_series",
                "Lo mismo por día. Sirve para el perfil por día de la semana.",
                params=[("df", "salida de `load_deis`"), ("code", "código DEIS")],
                returns="DataFrame `timestamp, count`.",
                example=(
                    "from urgencias_core.data.series import daily_series\n\n"
                    'diaria = daily_series(df, "24-105")\n'
                    "print(diaria.tail(2))"
                ),
            ),
            Entry(
                "codigos",
                "urgencias_core.data.deis:facility_code_variants",
                "facility_code_variants",
                "Las formas de un mismo código. El DEIS publica los establecimientos más "
                "antiguos con el código `SS-NNN` (los dos primeros dígitos indicaban el "
                "Servicio de Salud) y también como `1SSNNN`; los creados después tienen solo "
                "un código de 6 dígitos. Todas las funciones aceptan cualquiera de las formas.",
                params=[("code", "código DEIS")],
                returns="conjunto de formas equivalentes.",
                example=(
                    "from urgencias_core.data.deis import facility_code_variants\n\n"
                    'print(sorted(facility_code_variants("24-105")))'
                ),
            ),
            Entry(
                "mirror_facilities",
                "urgencias_core.data.mirror:mirror_facilities",
                "mirror_facilities",
                "El listado de establecimientos de la copia semanal: código, nombre, tipo "
                "(Hospital, SAPU, SAR, SUR…), región, comuna, servicio de salud y fechas con "
                "datos. Es lo que usa `urg-forecast buscar`. Necesita red.",
                returns="DataFrame con una fila por establecimiento.",
                example=(
                    "from urgencias_core.data.mirror import mirror_facilities\n\n"
                    "est = mirror_facilities()\n"
                    'print(est[est["comuna"] == "Puerto Montt"][["codigo", "nombre", "tipo"]])'
                ),
                run=False,
            ),
        ],
    ),
    Section(
        "analisis",
        "Análisis",
        "Cómo ha sido la demanda, antes de pronosticar. Funciones puras: reciben la serie "
        "semanal y devuelven un DataFrame. Es lo que hace `urg-forecast analizar`.",
        [
            Entry(
                "yearly_summary",
                "urgencias_core.analysis:yearly_summary",
                "yearly_summary",
                "Una fila por año. El cambio compara las **mismas semanas** del año "
                "anterior, así un año incompleto (enero a marzo) se compara con enero a "
                "marzo y no con un año completo.",
                params=[("weekly", "serie semanal")],
                returns="semanas, `complete`, total, promedio semanal, `change_pct`, semana "
                "más alta.",
                example=(
                    "from urgencias_core.analysis import yearly_summary\n\n"
                    'print(yearly_summary(semanal)[["weeks", "weekly_mean", "change_pct"]])'
                ),
            ),
            Entry(
                "seasonal_profile",
                "urgencias_core.analysis:seasonal_profile",
                "seasonal_profile",
                "El año típico: para cada semana del año, el promedio y el rango entre años, "
                "y `index`: cuánto se aleja esa semana del nivel de **su propio año** (1,15 = "
                "15 % sobre el nivel). Así el crecimiento de un año a otro no se confunde con "
                "la estación.",
                params=[("weekly", "serie semanal"), ("years", "usar solo los últimos años")],
                returns="una fila por semana: `mean`, `low`, `high`, `years`, `index`.",
                example=(
                    "from urgencias_core.analysis import seasonal_profile\n\n"
                    "perfil = seasonal_profile(semanal)\n"
                    'altas = perfil.sort_values("index", ascending=False).head(3)\n'
                    'print(altas.to_string(float_format="%.2f"))'
                ),
            ),
            Entry(
                "level",
                "urgencias_core.analysis:level",
                "level y year_over_year",
                "`level` es el promedio de las últimas 52 semanas: al promediar un año "
                "completo desaparece la estación y queda la tendencia. `year_over_year` "
                "compara cada semana con la misma de un año antes (sumas de 4 semanas).",
                params=[("weekly", "serie semanal"), ("window", "semanas del promedio (52)")],
                returns="`timestamp, count, level, change_pct`.",
                example=(
                    "from urgencias_core.analysis import level, year_over_year\n\n"
                    "print(level(semanal).tail(2))\n"
                    'print(year_over_year(semanal)[["timestamp", "change_pct"]].tail(2))'
                ),
            ),
            Entry(
                "analysis_text",
                "urgencias_core.analysis.report:write_analysis",
                "write_analysis",
                "El informe completo: texto en español, una figura y las tablas en CSV, en "
                "una carpeta. `analysis_text` devuelve solo el texto.",
                params=[
                    ("weekly", "serie semanal"),
                    ("out", "carpeta de salida"),
                    ("name, code", "para los títulos"),
                    ("daily", "serie diaria, para el perfil por día de la semana"),
                ],
                returns="lista de archivos escritos.",
                example=(
                    "from pathlib import Path\n"
                    "from urgencias_core.analysis.report import write_analysis\n\n"
                    "archivos = write_analysis(\n"
                    '    semanal, Path("salida"), "Hospital de Puerto Montt", "24-105"\n'
                    ")\n"
                    "print([a.name for a in archivos])"
                ),
            ),
        ],
    ),
    Section(
        "pronostico",
        "Pronóstico",
        "Comparar modelos en el pasado, elegir el mejor y pronosticar. Es lo que hace "
        "`urg-forecast pronosticar`.",
        [
            Entry(
                "run_forecast",
                "urgencias_core.forecast:run_forecast",
                "run_forecast",
                "Cada modelo pronostica semanas pasadas que ya se conocen (ventanas tan "
                "largas como el horizonte, hasta 26 semanas); se elige el mejor, se reajusta "
                "con toda la historia y se pronostica. Mejor es, por defecto, el de menor "
                "pérdida P80 (quedarse corto cuesta 4 veces más que pasarse); `select_by` "
                "cambia el criterio. Con `calibrate=True` las bandas se ensanchan según el "
                "error que tuvo en esas ventanas.",
                params=[
                    ("history", "serie semanal"),
                    ("horizon_weeks", "semanas a pronosticar"),
                    ("models", "nombre → fábrica; por defecto los cuatro de `default_models()`"),
                    (
                        "origins, step",
                        "número de ventanas (3) y semanas entre ellas (8); más ventanas dan una "
                        "elección más estable, no más acertada, a cambio de tiempo",
                    ),
                    ("calibrate", "ensanchar los intervalos según el backtest"),
                    (
                        "select_by",
                        'columna para elegir: `"qloss_80"` (por defecto), `"qloss_50"`, '
                        '`"qloss_90"`, `"qloss_95"`, `"qloss_mean"`, `"wis"`, `"mae"`, o una '
                        "función que reciba la tabla del backtest y devuelva un modelo",
                    ),
                    (
                        "quantiles",
                        "cuantiles del backtest y del pronóstico; por defecto P50 a P95, y "
                        'de P5 a P95 con `select_by="wis"`',
                    ),
                ],
                returns="`ForecastResult`: `best`, `backtest` (error por modelo), `forecast` "
                "(`timestamp, q50, q80, q90, q95`), `coverage80`, `interval_scale`.",
                example=(
                    "from urgencias_core import run_forecast\n\n"
                    'nombre = "Hospital de Puerto Montt"\n'
                    'res = run_forecast(semanal, 12, code="24-105", name=nombre)\n'
                    "print(res.best)\n"
                    'print(res.backtest[["mae", "qloss_80"]])\n'
                    'print(res.forecast[["timestamp", "q50", "q80"]].head(3))'
                ),
            ),
            Entry(
                "quantiles",
                "",
                "Cómo leer los cuantiles",
                "`q50` es el valor central: la mitad de las veces el real queda bajo él. `q80` "
                "y `q95` son los valores que, con 80 % y 95 % de probabilidad, no se superan; "
                "sirven para planificar con margen. La **pérdida P80** (pinball) mide el "
                "error de `q80` castigando más quedarse corto que pasarse; menor es mejor. "
                "`coverage80` cuenta en cuántas semanas del backtest el real quedó bajo `q80` "
                "(lo esperable es cerca de 80 %).",
                example=(
                    "cubiertas, total = res.coverage80\n"
                    'print(f"bajo P80 en {cubiertas} de {total} semanas")\n'
                    "# cuánto se ensanchó cada banda (1 = nada)\n"
                    "print({k: round(v, 2) for k, v in res.interval_scale.items()})"
                ),
            ),
            Entry(
                "summary_text",
                "urgencias_core.report:write_outputs",
                "summary_text y write_outputs",
                "El mismo resumen que imprime el comando (`summary_text`) y los CSV y figuras "
                "que guarda (`write_outputs`).",
                params=[("result", "un `ForecastResult`"), ("base", "carpeta de salida")],
                returns="lista de archivos escritos.",
                example=(
                    "from urgencias_core.report import summary_text, write_outputs\n\n"
                    "print(summary_text(res).splitlines()[0])\n"
                    'print([a.name for a in write_outputs(res, Path("salida"))])'
                ),
            ),
        ],
    ),
    Section(
        "modelos",
        "Modelos",
        "Un modelo es cualquier clase con `fit` y `predict`. Los incluidos se piden por "
        "nombre; uno propio se pasa como fábrica.",
        [
            Entry(
                "forecaster",
                "urgencias_core.models.protocol:Forecaster",
                "Forecaster (contrato)",
                "`fit(history, target_col)` aprende de la serie semanal. `predict(horizon)` "
                "devuelve `horizon.length` filas con `timestamp` y una columna por cuantil de "
                "`horizon.quantiles` (`q50, q80, q90, q95`; con el criterio WIS también "
                "`q5, q10, q20`), ordenadas. El constructor no debe exigir argumentos (o se "
                "registra una función que lo construya). Las fechas futuras salen de "
                "`future_index`.",
                example=(
                    "import numpy as np\n"
                    "from urgencias_core.models.protocol import HorizonSpec, future_index\n\n"
                    "class UltimoAnio:\n"
                    '    """Cada semana = la misma semana del año pasado, ± su variación."""\n'
                    "    def fit(self, history, target_col):\n"
                    '        self.s = history.set_index("timestamp")[target_col]\n'
                    "    def predict(self, horizon):\n"
                    "        fechas = future_index(self.s.index[-1], horizon)\n"
                    "        hace_un_anio = fechas - pd.Timedelta(weeks=52)\n"
                    "        centro = self.s.reindex(hace_un_anio).ffill().bfill().to_numpy()\n"
                    "        d = self.s.diff(52).dropna()\n"
                    '        out = pd.DataFrame({"timestamp": fechas})\n'
                    "        for q, col in zip(horizon.quantiles, horizon.quantile_columns):\n"
                    "            out[col] = centro + max(np.quantile(d, q), 0) * (q > 0.5)\n"
                    "        return out\n\n"
                    "m = UltimoAnio()\n"
                    'm.fit(semanal, "count")\n'
                    'print(m.predict(HorizonSpec(grain="W-MON", length=2)))'
                ),
            ),
            Entry(
                "registry",
                "urgencias_core.models.registry:resolve_models",
                "default_models, available_models, resolve_models",
                "Los modelos por nombre. `default_models()` son los cuatro que se comparan "
                "por defecto; `available_models()` suma los opcionales; `resolve_models` "
                "acepta nombres sin tildes ni mayúsculas, o `'archivo:Clase'` para uno propio.",
                params=[("names", "lista de nombres; `None` = los cuatro por defecto")],
                returns="dict nombre → fábrica (una instancia nueva por ajuste).",
                example=(
                    "from urgencias_core import available_models, default_models\n"
                    "from urgencias_core.models.registry import resolve_models\n\n"
                    "print(list(default_models()))\n"
                    'print(list(resolve_models(["armonicoferiados", "mstl"])))\n'
                    'modelos = default_models() | {"UltimoAnio": UltimoAnio}'
                ),
            ),
        ],
    ),
    Section(
        "evaluacion",
        "Evaluación",
        "Qué tan bien funciona un modelo, y si un cambio ayuda de verdad o es ruido. Todo usa "
        "el mismo motor de backtest: ninguna ventana ve el futuro de otra.",
        [
            Entry(
                "backtest",
                "urgencias_core.eval.backtest:backtest",
                "backtest",
                "Ajusta cada modelo desde cero en ventanas que van hacia atrás desde el "
                "final y guarda lo que predijo. `scores()` da una fila por ventana y modelo.",
                params=[
                    ("history", "serie semanal"),
                    ("models", "nombre → fábrica"),
                    ("length", "semanas de cada ventana"),
                    ("origins, step", "número de ventanas y semanas entre ellas"),
                ],
                returns="`Backtest`: `windows`, `scores()`, `failed`, `pairs(modelo)`. "
                "`scores()` trae `mae`, la pérdida de cada cuantil (`qloss_80`, …), sus dos "
                "partes (`qloss_80_short`: semanas sobre el P80, a 0,8 por atención; "
                "`qloss_80_excess`: bajo él, a 0,2), `qloss_mean` (promedio de P50 a P95), "
                "`wis` (si se pidieron P5, P10 y P20), el ancho `width_80` (P80 menos P50) y "
                "`covered` de `n` semanas bajo el P80. `compare_scores` hace la comparación de "
                "`compare_models` sobre una corrida ya hecha.",
                example=(
                    "from urgencias_core import backtest\n\n"
                    'dos = {"Armónico": modelos["Armónico"], "UltimoAnio": UltimoAnio}\n'
                    "corrida = backtest(semanal, dos, length=4, origins=6, step=8)\n"
                    "errores = corrida.scores()\n"
                    'cols = ["mae", "width_80", "qloss_80_short", "qloss_80_excess", "qloss_80"]\n'
                    'print(errores.groupby("model")[cols].mean().round(1))'
                ),
            ),
            Entry(
                "compare_models",
                "urgencias_core.eval.compare:compare_models",
                "compare_models",
                "¿El candidato le gana a la base de forma consistente? Ajusta ambos en las "
                "mismas ventanas (36 de 4 semanas por defecto), cuenta en cuántas gana, aplica "
                "una prueba de signos y separa invierno del resto. Es `urg-forecast comparar`.",
                params=[
                    ("history", "serie semanal"),
                    ("base, candidate", "pares `(nombre, fábrica)`"),
                    ("horizon_weeks, origins, step", "ventanas (4, 36, 4)"),
                    ("metric", 'qué se compara en cada ventana (por defecto `"qloss_80"`)'),
                ],
                returns="`Comparison`: `verdict` (`mejora`, `empeora`, `sin diferencia "
                "clara`), `text()`, `summary()`, `windows`.",
                example=(
                    "from urgencias_core import compare_models\n"
                    "from urgencias_core.models.harmonic import HarmonicRegression\n\n"
                    'cmp = compare_models(semanal, ("Armónico", HarmonicRegression),\n'
                    '                     ("UltimoAnio", UltimoAnio), origins=8)\n'
                    "print(cmp.text())"
                ),
            ),
        ],
    ),
    Section(
        "regresores",
        "Regresores",
        "Variables externas al DEIS (feriados, virus, clima) con las reglas de su fuente. "
        "Explicación y resultados en la página Regresores.",
        [
            Entry(
                "regressor",
                "urgencias_core.regressors:Regressor",
                "Regressor",
                "Una tabla semanal (`timestamp` + una columna por variable) y las reglas de su "
                "fuente: cuántas semanas tarda en publicarse y si su futuro se conoce. Vienen "
                "`calendar()` (feriados, interferiados, vacaciones escolares; futuro conocido) "
                "y `flunet()` (positividad de influenza y VRS; 2 semanas de atraso).",
                params=[
                    ("load", "función que devuelve la tabla"),
                    ("columns", "columnas que usa el modelo"),
                    ("report_delay_weeks", "atraso de publicación"),
                    ("known_future", "si los valores futuros se conocen"),
                ],
                example=(
                    "from urgencias_core.regressors import calendar\n\n"
                    "cal = calendar()\n"
                    "print(cal.columns, cal.known_future)\n"
                    'cols = ["timestamp", "holidays", "bridge_days", "school_holiday"]\n'
                    "tabla = cal.table()[cols]\n"
                    "print(tabla.query(\"timestamp >= '2026-09-14'\").head(3))"
                ),
            ),
            Entry(
                "from_regressor",
                "urgencias_core.models.exogenous:HarmonicExogenous.from_regressor",
                "HarmonicExogenous.from_regressor",
                "El Armónico más un regresor. En cada ventana solo usa lo que estaba publicado "
                "en esa fecha; lo que falta lo rellena con el promedio histórico "
                '(`"climatology"`) o con una proyección de la serie (`"forecast"`). '
                "`regressor_path` muestra qué supuso para las semanas pronosticadas.",
                params=[
                    ("regressor", "un `Regressor`"),
                    ("columns", "subconjunto de columnas (por defecto todas)"),
                    ("lag_weeks", "la semana t usa el valor de t − rezago"),
                    ("future", '`"climatology"` o `"forecast"`'),
                ],
                returns="un modelo que cumple el contrato `Forecaster`.",
                example=(
                    "from urgencias_core.models.exogenous import HarmonicExogenous\n\n"
                    'feriados = lambda: HarmonicExogenous.from_regressor(cal, ["holidays"])\n'
                    "m = feriados()\n"
                    'm.fit(semanal, "count")\n'
                    'print(m.regressor_path(HorizonSpec(grain="W-MON", length=3)))\n'
                    'cmp = compare_models(semanal, ("Armónico", HarmonicRegression),\n'
                    '                     ("Feriados", feriados), origins=8)\n'
                    "print(cmp.verdict)"
                ),
            ),
        ],
    ),
]


def _resolve(target: str):
    module, _, attr = target.partition(":")
    obj = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def _param(p: inspect.Parameter) -> str:
    prefix = {p.VAR_POSITIONAL: "*", p.VAR_KEYWORD: "**"}.get(p.kind, "")
    out = prefix + p.name
    if p.annotation is not p.empty:
        ann = p.annotation
        out += f": {ann if isinstance(ann, str) else inspect.formatannotation(ann)}"
    if p.default is not p.empty:
        d = p.default
        shown = f'Path("{d}")' if isinstance(d, Path) else repr(d).replace("'", '"')
        out += f" = {shown}"
    return out


def signature(target: str) -> str:
    """``name(params)`` as it reads in the code, for the page and the drift test."""
    if not target:
        return ""
    obj = _resolve(target)
    name = target.partition(":")[2]
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return name
    params = [p for p in sig.parameters.values() if p.name not in ("self", "cls")]
    text = ", ".join(_param(p) for p in params)
    if inspect.isclass(obj) and getattr(obj, "_is_protocol", False):
        return f"class {name}(Protocol)"
    one_line = f"{name}({text})"
    if len(one_line) <= 60:
        return one_line
    body = "".join(f"    {_param(p)},\n" for p in params)
    return f"{name}(\n{body})"


def source(target: str) -> str:
    """``src/...py`` holding the documented object, for the link on the page (no line
    number: it would go stale with every edit above it)."""
    if not target:
        return ""
    obj = inspect.unwrap(_resolve(target))
    obj = getattr(obj, "__func__", obj)
    try:
        path = Path(inspect.getsourcefile(obj)).resolve()
    except (TypeError, OSError):
        return ""
    root = Path(__file__).resolve().parents[1]
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else ""


def run_examples(sections: list[Section] = SECTIONS) -> dict[str, str]:
    """Execute every runnable example in order, in one namespace; return id -> output."""
    ns: dict = {}
    exec(SETUP, ns)  # noqa: S102 - our own example code
    outputs = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for section in sections:
            for e in section.entries:
                if not (e.example and e.run):
                    continue
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    exec(e.example, ns)  # noqa: S102
                lines = buf.getvalue().rstrip().splitlines()
                if len(lines) > MAX_OUTPUT_LINES:
                    lines = lines[:MAX_OUTPUT_LINES] + ["…"]
                outputs[e.id] = "\n".join(lines)
    return outputs


def build() -> dict:
    from urgencias_core import __version__

    outputs = run_examples()
    return {
        "version": __version__,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "text": s.text,
                "entries": [
                    {
                        "id": e.id,
                        "title": e.title,
                        "signature": signature(e.target),
                        "module": e.target.partition(":")[0],
                        "source": source(e.target),
                        "text": e.text,
                        "params": e.params,
                        "returns": e.returns,
                        "example": textwrap.dedent(e.example).strip(),
                        "output": outputs.get(e.id, ""),
                        "run": e.run,
                    }
                    for e in s.entries
                ],
            }
            for s in SECTIONS
        ],
    }


def main() -> int:
    import os
    import tempfile

    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:  # examples write their files here
        os.chdir(tmp)
        try:
            data = build()
        finally:
            os.chdir(here)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(s["entries"]) for s in data["sections"])
    print(f"{OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}: {n} entradas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
