"""``urg-forecast``: weekly ED attendance forecast from public DEIS MINSAL data.

Subcommands::

    urg-forecast demo                          # two demo hospitals, offline snapshot
    urg-forecast buscar "puerto montt"         # find an establishment's DEIS code
    urg-forecast pronosticar 24-105 -H 6m      # backtest + forecast, any establishment
    urg-forecast analizar 24-105               # describe demand: level, season, last year
    urg-forecast modelos                       # list built-in models
    urg-forecast comparar 24-105 -m ArmonicoFluNet   # does a regressor help? many windows

Prints a summary with ASCII tables and writes CSVs + PNGs to ``--salida``.
The interface is in Spanish (the audience is Chilean ED teams); the code and
docstrings are in English. Downloaded DEIS files are cached in ``--cache``
(default: ``$URG_FORECAST_CACHE`` or ``./data/external/deis_cache``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

from urgencias_core._logging import setup_logging

log = logging.getLogger(__name__)

DEFAULT_HORIZON = "26"
DEFAULT_OUT = Path("urg-forecast-salida")
CACHE_ENV = "URG_FORECAST_CACHE"

BASE_NOTE = """\
Es una aproximación inicial: modelos estadísticos simples, sin ajuste local ni
validación clínica u operacional. Ajustarla a tu realidad es trabajo tuyo."""

EPILOG = f"""\
flujo típico:
  1. urg-forecast demo                    # ver qué produce, con dos hospitales
  2. urg-forecast buscar "osorno"         # encontrar el código DEIS
  3. urg-forecast analizar <código>       # cómo ha sido la demanda
  4. urg-forecast pronosticar <código>    # backtest + pronóstico
  5. urg-forecast modelos                 # probar otros modelos con -m

Usa "urg-forecast COMANDO -h" para ver las opciones de cada comando.

códigos de salida: 0 = ok (al menos un establecimiento pronosticado),
1 = sin datos o sin coincidencias, 2 = argumentos o modelo inválidos.

{BASE_NOTE}
"""

DEMO_EPILOG = f"""\
ejemplos:
  urg-forecast demo                       # intenta DEIS, si no hay red usa el snapshot
  urg-forecast demo --offline             # solo el snapshot incluido, sin red
  urg-forecast demo -H 12 -o demo/        # 12 semanas, resultados en ./demo/

{BASE_NOTE}
"""

ANALYZE_EPILOG = f"""\
ejemplos:
  urg-forecast analizar 24-105                 # Hospital de Puerto Montt
  urg-forecast analizar 24-105 24-115 -o res/  # varios establecimientos
  urg-forecast analizar 24-105 --offline       # snapshot incluido, sin red

Describe la serie semanal: nivel y su cambio en el último año, el año típico
(semanas más altas y más bajas frente al nivel de su año), las últimas semanas
frente a las mismas del año anterior, un resumen por año y el día de la semana.
Escribe analisis.txt, analisis.png y las tablas en CSV.

{BASE_NOTE}
"""

SEARCH_EPILOG = """\
ejemplos:
  urg-forecast buscar "puerto montt"
  urg-forecast buscar sapu                # por tipo: Hospital, SAPU, SAR, SUR
  urg-forecast buscar "los lagos"         # por región, comuna o servicio de salud
  urg-forecast buscar 24-1                # también filtra por código
  urg-forecast buscar                     # sin texto: lista todos

El código que aparece en la primera columna es el que recibe "pronosticar".
"""

FORECAST_EPILOG = f"""\
ejemplos:
  urg-forecast pronosticar 24-105                  # 26 semanas (por defecto)
  urg-forecast pronosticar 24-105 -H 12            # 12 semanas
  urg-forecast pronosticar 124105 -H 6m            # mismo hospital, código numérico; 6 meses
  urg-forecast pronosticar 24-105 24-115 -o res/   # varios establecimientos
  urg-forecast pronosticar 24-105 -m AutoARIMA     # un solo modelo, sin comparar
  urg-forecast pronosticar 24-105 -m Ensamble -m TBATS -m MSTL
  urg-forecast pronosticar 24-105 -m mi_modelo:MiClase -m MSTL
  urg-forecast pronosticar 24-105 --criterio p95   # quedarse corto cuesta 19 veces más
  urg-forecast pronosticar 24-105 --criterio wis   # pronóstico completo; agrega P5, P10, P20
  urg-forecast pronosticar 24-105 --ventanas 9     # elige y calibra con 9 ventanas, no 3

Horizonte: semanas (12 o 12s) o meses (6m). El backtest usa tres ventanas
(--ventanas) tan largas como el horizonte (máximo 26 semanas), cada 8 semanas
(--paso), y exige 104 semanas previas de historia completa. Los intervalos se
ensanchan según el error del backtest (--sin-calibrar lo desactiva).

Modelo propio: una clase con fit(history, target_col) y predict(horizon) que
devuelva timestamp, q50, q80, q90, q95, en un .py de la carpeta actual.

{BASE_NOTE}
"""

COMPARE_EPILOG = f"""\
ejemplos:
  urg-forecast comparar 24-105 -m ArmonicoFluNet
  urg-forecast comparar 24-105 -m ArmonicoFluNetProy --base Armonico -H 8
  urg-forecast comparar 24-105 -m mi_modelo:MiClase --ventanas 24 --paso 6
  urg-forecast comparar 24-105 -m ArmonicoFeriados --criterio media

Ajusta ambos modelos en las mismas ventanas (por defecto 36 ventanas de 4 semanas,
cada 4 semanas: unos tres inviernos) y cuenta en cuántas gana el candidato, con
una prueba de signos. Separa invierno (mayo a septiembre) del resto. Con muchos
establecimientos, uno de cada veinte saldrá "mejora" o "empeora" por azar.

{BASE_NOTE}
"""

# --criterio: how the backtest picks the model (or compares two). Score columns in
# urgencias_core.eval.metrics.CRITERIA.
CRITERIO = {
    "p80": "qloss_80",
    "p50": "qloss_50",
    "p90": "qloss_90",
    "p95": "qloss_95",
    "media": "qloss_mean",
    "wis": "wis",
    "mae": "mae",
}
CRITERIO_HELP = (
    "criterio para elegir el modelo en el backtest (por defecto p80). p50, p80, p90 o p95: "
    "pérdida en ese cuantil; elígelo según cuánto peor es quedarse corto que pasarse "
    "(p50: igual; p80: 4 veces; p90: 9; p95: 19). media: promedio de P50 a P95, evalúa el "
    "valor central y la parte alta juntos. wis: el puntaje de intervalos (WIS) de los "
    "centros de pronóstico de influenza, evalúa el pronóstico completo con cuantiles de P5 a "
    "P95. mae: error del valor central. Fíjalo antes de mirar los resultados"
)

MODELS_EPILOG = """\
ejemplos:
  urg-forecast modelos
  urg-forecast pronosticar 24-105 -m Ensamble -m ArmonicoFeriados

Los nombres no distinguen mayúsculas ni tildes.
"""


def _horizon_type(text: str) -> int:
    from urgencias_core.forecast import parse_horizon

    try:
        return parse_horizon(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"se espera un número entero: {text!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"debe ser 1 o más: {n}")
    return n


def _default_cache() -> Path:
    from urgencias_core.data.deis import DEFAULT_CACHE_DIR

    return Path(os.environ.get(CACHE_ENV) or DEFAULT_CACHE_DIR)


def _new_parser(**kwargs) -> argparse.ArgumentParser:
    """Parser with Spanish section titles and help, verbatim epilog."""
    kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
    return argparse.ArgumentParser(add_help=False, **kwargs)


def _spanish(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser._positionals.title = "argumentos"
    parser._optionals.title = "opciones"
    parser.add_argument("-h", "--help", action="help", help="muestra esta ayuda y sale")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = _spanish(
        _new_parser(
            prog="urg-forecast",
            description=(
                "Pronóstico semanal de atenciones de urgencia con datos públicos del\n"
                "DEIS MINSAL: backtest de varios modelos y pronóstico con el mejor."
            ),
            epilog=EPILOG,
        )
    )
    from urgencias_core import __version__

    parser.add_argument(
        "--version",
        action="version",
        version=f"urg-forecast {__version__}",
        help="muestra la versión y sale",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMANDO", title="comandos")

    def add_cache_option(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--fuente",
            choices=["repo", "deis"],
            default="repo",
            help="de dónde leer los datos: 'repo' (por defecto), una copia semanal de los "
            "totales diarios publicada en el repositorio del proyecto; 'deis', los archivos "
            "anuales completos directo del DEIS (cientos de MB por año)",
        )
        p.add_argument(
            "--cache",
            type=Path,
            default=None,
            metavar="CARPETA",
            help=f"dónde guardar las descargas (por defecto: ${CACHE_ENV} "
            "o ./data/external/deis_cache, relativo a la carpeta actual)",
        )

    def add_forecast_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-H",
            "--horizonte",
            type=_horizon_type,
            default=_horizon_type(DEFAULT_HORIZON),
            metavar="N|Nm",
            help="horizonte: semanas (12 o 12s) o meses (6m); por defecto 26 semanas",
        )
        p.add_argument(
            "-o",
            "--salida",
            type=Path,
            default=DEFAULT_OUT,
            metavar="CARPETA",
            help=f"carpeta para CSV y figuras (por defecto: ./{DEFAULT_OUT}); "
            "se crea una subcarpeta por establecimiento",
        )
        p.add_argument(
            "-m",
            "--modelo",
            action="append",
            metavar="NOMBRE",
            help="modelo a usar (repetible): uno de 'urg-forecast modelos' o 'modulo:Clase' "
            "para uno propio. Por defecto compara SeasonalNaive, AutoARIMA, Armonico y MSTL",
        )
        p.add_argument(
            "--sin-calibrar",
            action="store_true",
            help="no ensanchar los intervalos según el error del backtest",
        )
        p.add_argument("--criterio", choices=list(CRITERIO), default="p80", help=CRITERIO_HELP)
        p.add_argument(
            "--ventanas",
            type=_positive,
            default=None,
            metavar="N",
            help="ventanas del backtest para elegir el modelo y calibrar los intervalos "
            "(por defecto 3). Más ventanas dan una elección más estable, pero tardan más y "
            "llegan más atrás en el tiempo; caben las que deje la historia",
        )
        p.add_argument(
            "--paso",
            type=_positive,
            default=None,
            metavar="SEMANAS",
            help="semanas entre ventanas del backtest (por defecto 8)",
        )

    p_demo = _spanish(
        sub.add_parser(
            "demo",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="pronóstico de ejemplo: hospitales de Puerto Montt y Frutillar",
            description=(
                "Pronóstico de ejemplo para el Hospital de Puerto Montt (24-105) y el\n"
                "Hospital de Frutillar (24-115). Descarga los datos DEIS más recientes y,\n"
                "si no hay conexión, usa el snapshot incluido en el paquete."
            ),
            epilog=DEMO_EPILOG,
        )
    )
    add_forecast_options(p_demo)
    p_demo.add_argument(
        "--offline", action="store_true", help="usa directamente el snapshot incluido, sin red"
    )
    add_cache_option(p_demo)

    p_an = _spanish(
        sub.add_parser(
            "analizar",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="describe la demanda de uno o más establecimientos",
            description=(
                "Análisis descriptivo de las atenciones semanales: nivel y tendencia,\n"
                "estacionalidad, comparación con el año anterior y día de la semana."
            ),
            epilog=ANALYZE_EPILOG,
        )
    )
    p_an.add_argument("codigos", nargs="+", metavar="CODIGO", help="código DEIS, p. ej. 24-105")
    p_an.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=DEFAULT_OUT,
        metavar="CARPETA",
        help=f"carpeta para el informe (por defecto: ./{DEFAULT_OUT}); "
        "una subcarpeta por establecimiento",
    )
    p_an.add_argument(
        "--desde",
        type=int,
        default=2022,
        metavar="AÑO",
        help="primer año DEIS a usar (por defecto: 2022; 2020–2021 siempre se excluyen)",
    )
    p_an.add_argument(
        "--offline", action="store_true", help="usa el snapshot incluido (solo 24-105 y 24-115)"
    )
    add_cache_option(p_an)

    p_search = _spanish(
        sub.add_parser(
            "buscar",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="busca el código DEIS de un establecimiento",
            description=(
                "Lista establecimientos públicos del DEIS filtrando por nombre, código, tipo,\n"
                "comuna, región o servicio de salud. Lee el listado del repositorio del proyecto."
            ),
            epilog=SEARCH_EPILOG,
        )
    )
    p_search.add_argument(
        "texto", nargs="?", default="", help="parte del nombre o código (vacío: todos)"
    )
    p_search.add_argument(
        "--anio",
        type=int,
        default=datetime.now().year,
        metavar="AÑO",
        help="con --fuente deis: año del archivo DEIS donde buscar (por defecto: el actual)",
    )
    add_cache_option(p_search)

    p_fc = _spanish(
        sub.add_parser(
            "pronosticar",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="backtest y pronóstico para uno o más establecimientos",
            description=(
                "Descarga los datos DEIS de los establecimientos indicados, compara\n"
                "modelos en un backtest con varias ventanas y pronostica con el de menor\n"
                "pérdida P80 (--criterio cambia el criterio). Por defecto: SeasonalNaive,\n"
                "AutoARIMA, Armónico y MSTL."
            ),
            epilog=FORECAST_EPILOG,
        )
    )
    p_fc.add_argument(
        "codigos",
        nargs="+",
        metavar="CODIGO",
        help="código DEIS, p. ej. 24-105 o 124105 (búscalo con 'urg-forecast buscar')",
    )
    add_forecast_options(p_fc)
    p_fc.add_argument(
        "--desde",
        type=int,
        default=2022,
        metavar="AÑO",
        help="primer año DEIS a usar (por defecto: 2022; 2020–2021 siempre se excluyen)",
    )
    p_fc.add_argument(
        "--offline",
        action="store_true",
        help="usa el snapshot incluido (solo 24-105 y 24-115), sin red",
    )
    add_cache_option(p_fc)

    p_cmp = _spanish(
        sub.add_parser(
            "comparar",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="¿ayuda un regresor? compara dos modelos en muchas ventanas",
            description=(
                "Compara un modelo candidato (p. ej. con un regresor externo) contra uno\n"
                "base en muchas ventanas del backtest, para ver si la diferencia es\n"
                "consistente o solo ruido. Escribe una fila por ventana en --salida."
            ),
            epilog=COMPARE_EPILOG,
        )
    )
    p_cmp.add_argument("codigo", metavar="CODIGO", help="código DEIS, p. ej. 24-105")
    p_cmp.add_argument(
        "-m",
        "--modelo",
        required=True,
        metavar="NOMBRE",
        help="modelo candidato: uno de 'urg-forecast modelos' o 'modulo:Clase'",
    )
    p_cmp.add_argument(
        "--base", default="Armónico", metavar="NOMBRE", help="modelo base (por defecto: Armónico)"
    )
    p_cmp.add_argument(
        "-H",
        "--horizonte",
        type=_horizon_type,
        default=4,
        metavar="N|Nm",
        help="largo de cada ventana (por defecto 4 semanas)",
    )
    p_cmp.add_argument(
        "--ventanas", type=_positive, default=36, metavar="N", help="número de ventanas (36)"
    )
    p_cmp.add_argument(
        "--criterio",
        choices=list(CRITERIO),
        default="p80",
        help="qué se compara en cada ventana (por defecto p80): " + CRITERIO_HELP.split(": ", 1)[1],
    )
    p_cmp.add_argument(
        "--paso", type=_positive, default=4, metavar="SEMANAS", help="semanas entre ventanas (4)"
    )
    p_cmp.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=DEFAULT_OUT,
        metavar="CARPETA",
        help=f"carpeta para el CSV (por defecto: ./{DEFAULT_OUT})",
    )
    p_cmp.add_argument(
        "--desde",
        type=int,
        default=2022,
        metavar="AÑO",
        help="con --fuente deis: primer año DEIS a usar (por defecto: 2022)",
    )
    add_cache_option(p_cmp)

    _spanish(
        sub.add_parser(
            "modelos",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="lista los modelos disponibles",
            description=(
                "Modelos incluidos. Los cuatro primeros se comparan por defecto; el resto\n"
                "se activa con -m NOMBRE. Detalle en docs/modelos.md."
            ),
            epilog=MODELS_EPILOG,
        )
    )
    return parser


def _forecast(
    codes: list[str],
    horizon: int,
    out: Path,
    start_year: int,
    offline: bool,
    fallback: bool = False,
    cache_dir: Path | None = None,
    model_names: list[str] | None = None,
    calibrate: bool = True,
    source: str = "repo",
    select_by: str = "qloss_80",
    origins: int | None = None,
    step: int | None = None,
) -> int:
    from urgencias_core.data.series import NoDataError, facility_name, load_deis, weekly_series
    from urgencias_core.forecast import BACKTEST_ORIGINS, BACKTEST_STEP, run_forecast
    from urgencias_core.models.registry import resolve_models
    from urgencias_core.report import output_dir, summary_text, write_outputs

    if model_names and any(":" in m for m in model_names) and "" not in sys.path:
        sys.path.insert(0, "")  # console scripts don't import from the current directory
    try:
        models = resolve_models(model_names)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    where = " (snapshot offline)" if offline else (" desde el DEIS" if source == "deis" else "")
    log.info("Cargando datos%s...", where)
    try:
        df = load_deis(
            codes,
            start_year=start_year,
            offline=offline,
            fallback_to_snapshot=fallback,
            cache_dir=cache_dir or _default_cache(),
            source=source,
        )
    except NoDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for code in codes:
        name = facility_name(df, code)
        log.info("Modelando %s (%s)...", name, code)
        try:
            result = run_forecast(
                weekly_series(df, code),
                horizon,
                code=code,
                name=name,
                source=df.attrs["source"],
                models=models,
                calibrate=calibrate,
                select_by=select_by,
                origins=origins or BACKTEST_ORIGINS,
                step=step or BACKTEST_STEP,
            )
        except NoDataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue
        if origins and result.backtest_origins < origins:
            print(
                f"nota: con la historia disponible caben {result.backtest_origins} ventanas, "
                f"no {origins}.",
                file=sys.stderr,
            )
        paths = write_outputs(result, out)
        print()
        print(summary_text(result))
        print()
        print(f"Archivos en {output_dir(out, result)}/")
        for p in paths:
            print(f"  {p.name}")
    return 1 if failures == len(codes) else 0


def _search(text: str, year: int, cache_dir: Path | None = None, source: str = "repo") -> int:
    from tabulate import tabulate

    cache = cache_dir or _default_cache()
    if source == "repo":
        from urgencias_core.data.mirror import MirrorUnavailable, mirror_facilities

        try:
            fac = mirror_facilities(cache_dir=cache)
        except MirrorUnavailable as exc:
            print(f"error: {exc}. Revisa tu conexión o usa --fuente deis.", file=sys.stderr)
            return 1
        cols = ["codigo", "nombre", "tipo", "comuna", "region"]
        fac = fac[[c for c in cols if c in fac.columns]]
        headers = ["Código", "Establecimiento", "Tipo", "Comuna", "Región"][: len(fac.columns)]
    else:
        from urgencias_core.data.deis import list_facilities

        log.info("Leyendo establecimientos DEIS %s (la primera vez descarga el archivo)...", year)
        try:
            fac = list_facilities(year, cache_dir=cache)
        except RuntimeError as exc:
            print(f"error: {exc}. Prueba con --anio {year - 1}.", file=sys.stderr)
            return 1
        headers = ["Código", "Establecimiento"]
    if text:
        haystack = fac.astype(str).agg(" ".join, axis=1)
        fac = fac[haystack.str.contains(text, case=False, na=False, regex=False)]
    if fac.empty:
        print(f"Sin coincidencias para {text!r}.")
        return 1
    print(tabulate(fac.values.tolist(), headers=headers, tablefmt="psql"))
    print(f"{len(fac)} establecimiento(s). Siguiente paso: urg-forecast pronosticar <código>")
    return 0


def _analyze(args: argparse.Namespace) -> int:
    from urgencias_core.analysis.report import analysis_text, write_analysis
    from urgencias_core.data.series import (
        NoDataError,
        daily_series,
        facility_name,
        load_deis,
        weekly_series,
    )
    from urgencias_core.report import slug

    try:
        df = load_deis(
            args.codigos,
            start_year=args.desde,
            offline=args.offline,
            cache_dir=args.cache or _default_cache(),
            source=args.fuente,
        )
    except NoDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    done = 0
    for code in args.codigos:
        name = facility_name(df, code)
        weekly = weekly_series(df, code)
        if len(weekly) < 2 * 52:
            print(
                f"error: {name}: se necesitan al menos 104 semanas y hay {len(weekly)}.",
                file=sys.stderr,
            )
            continue
        daily = daily_series(df, code)
        print()
        print(analysis_text(weekly, name, code, df.attrs["source"], daily))
        out = args.salida / f"{slug(code)}_{slug(name)}"
        paths = write_analysis(weekly, out, name, code, df.attrs["source"], daily)
        print()
        print(f"Archivos en {out}/")
        for p in paths:
            print(f"  {p.name}")
        done += 1
    return 0 if done else 1


def _compare(args: argparse.Namespace) -> int:
    from tabulate import tabulate

    from urgencias_core.data.series import NoDataError, facility_name, load_deis, weekly_series
    from urgencias_core.eval.compare import compare_models
    from urgencias_core.models.registry import resolve_models

    if ":" in args.modelo and "" not in sys.path:
        sys.path.insert(0, "")
    try:
        (bname, bf), (cname, cf) = (
            next(iter(resolve_models([args.base]).items())),
            next(iter(resolve_models([args.modelo]).items())),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if bname == cname:
        print("error: el candidato y la base son el mismo modelo", file=sys.stderr)
        return 2
    try:
        df = load_deis(
            [args.codigo],
            start_year=args.desde,
            cache_dir=args.cache or _default_cache(),
            source=args.fuente,
        )
    except NoDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    name = facility_name(df, args.codigo)
    log.info("Comparando %s contra %s en %s (puede tardar unos minutos)...", cname, bname, name)
    cmp = compare_models(
        weekly_series(df, args.codigo),
        (bname, bf),
        (cname, cf),
        horizon_weeks=args.horizonte,
        origins=args.ventanas,
        step=args.paso,
        metric=CRITERIO[args.criterio],
    )
    if cmp.n == 0:
        print("error: no hay historia suficiente para ninguna ventana", file=sys.stderr)
        return 1
    s = cmp.summary()
    rows = [
        [
            k,
            int(r["ventanas"]),
            f"{100 * r['cambio_mediano']:+.1f} %",
            f"{100 * r['cambio_total']:+.1f} %",
            int(r["gana"]),
            int(r["pierde"]),
            f"{r['p']:.2f}",
        ]
        for k, r in s.iterrows()
    ]
    heads = ["Ventanas", "N", "Cambio mediano", "Cambio total", "Gana", "Pierde", "p"]
    print()
    print(f"{name} ({args.codigo})")
    print(tabulate(rows, headers=heads, tablefmt="psql"))
    print(cmp.text())
    out = args.salida / args.codigo
    out.mkdir(parents=True, exist_ok=True)
    path = out / "comparacion.csv"
    cmp.windows.to_csv(path, index=False)
    print(f"Una fila por ventana en {path}")
    return 0


def _list_models() -> int:
    from tabulate import tabulate

    from urgencias_core.models.registry import MODEL_INFO, default_models, extra_models

    rows = [[n, "sí", MODEL_INFO.get(n, "")] for n in default_models()]
    rows += [[n, "", MODEL_INFO.get(n, "")] for n in extra_models()]
    print(tabulate(rows, headers=["Modelo", "Por defecto", "Descripción"], tablefmt="psql"))
    print("Uso: urg-forecast pronosticar <código> -m NOMBRE [-m NOMBRE ...]")
    print("Modelo propio: -m archivo:Clase (ver docs/modelos.md)")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    # statsforecast's optimizer warnings mean nothing to a CLI user; the backtest
    # table is the honest measure of whether a model works.
    warnings.filterwarnings("ignore", module=r"statsforecast\..*")
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "demo":
        from urgencias_core.data.series import DEMO_FACILITIES

        return _forecast(
            list(DEMO_FACILITIES),
            args.horizonte,
            args.salida,
            2022,
            args.offline,
            fallback=True,
            cache_dir=args.cache,
            model_names=args.modelo,
            calibrate=not args.sin_calibrar,
            source=args.fuente,
            select_by=CRITERIO[args.criterio],
            origins=args.ventanas,
            step=args.paso,
        )
    if args.command == "modelos":
        return _list_models()
    if args.command == "analizar":
        return _analyze(args)
    if args.command == "comparar":
        return _compare(args)
    if args.command == "buscar":
        return _search(args.texto, args.anio, cache_dir=args.cache, source=args.fuente)
    return _forecast(
        args.codigos,
        args.horizonte,
        args.salida,
        args.desde,
        args.offline,
        cache_dir=args.cache,
        model_names=args.modelo,
        calibrate=not args.sin_calibrar,
        source=args.fuente,
        select_by=CRITERIO[args.criterio],
        origins=args.ventanas,
        step=args.paso,
    )


def entrypoint() -> None:
    try:
        sys.exit(main())
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stderr.close()
        sys.exit(0)


if __name__ == "__main__":
    entrypoint()
