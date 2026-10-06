"""``urg-forecast``: weekly ED attendance forecast from public DEIS MINSAL data.

Subcommands::

    urg-forecast demo                          # two demo hospitals, offline snapshot
    urg-forecast buscar "puerto montt"         # find an establishment's DEIS code
    urg-forecast pronosticar 24-105 -H 6m      # backtest + forecast, any establishment
    urg-forecast modelos                       # list built-in models

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
  3. urg-forecast pronosticar <código>    # backtest + pronóstico
  4. urg-forecast modelos                 # probar otros modelos con -m

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

SEARCH_EPILOG = """\
ejemplos:
  urg-forecast buscar "puerto montt"
  urg-forecast buscar 24-1                # también filtra por código
  urg-forecast buscar --anio 2025 osorno  # si el archivo del año actual aún no existe
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

Horizonte: semanas (12 o 12s) o meses (6m). El backtest usa tres ventanas tan
largas como el horizonte (máximo 26 semanas) y exige 104 semanas previas de
historia completa. Los intervalos se ensanchan según el error del backtest
(--sin-calibrar lo desactiva).

Modelo propio: una clase con fit(history, target_col) y predict(horizon) que
devuelva timestamp, q50, q80, q90, q95, en un .py de la carpeta actual.

{BASE_NOTE}
"""

MODELS_EPILOG = """\
ejemplos:
  urg-forecast modelos
  urg-forecast pronosticar 24-105 -m Ensamble -m ArmonicoFeriados

Los nombres no distinguen mayúsculas ni tildes.
"""


def _horizon_type(text: str) -> int:
    from urgencias_core.pipeline import parse_horizon

    try:
        return parse_horizon(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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
            "--cache",
            type=Path,
            default=None,
            metavar="CARPETA",
            help=f"dónde guardar los ZIP anuales del DEIS (por defecto: ${CACHE_ENV} "
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

    p_search = _spanish(
        sub.add_parser(
            "buscar",
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            help="busca el código DEIS de un establecimiento",
            description=(
                "Lista establecimientos del DEIS filtrando por nombre o código.\n"
                "La primera vez descarga el archivo anual (cientos de MB) y lo guarda en caché."
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
        help="año del archivo DEIS donde buscar (por defecto: el actual)",
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
                "pérdida P80. Por defecto: SeasonalNaive, AutoARIMA, Armónico y MSTL."
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
) -> int:
    from urgencias_core.pipeline import (
        NoDataError,
        facility_name,
        load_deis,
        resolve_models,
        run_forecast,
        weekly_series,
    )
    from urgencias_core.report import output_dir, summary_text, write_outputs

    if model_names and any(":" in m for m in model_names) and "" not in sys.path:
        sys.path.insert(0, "")  # console scripts don't import from the current directory
    try:
        models = resolve_models(model_names)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    log.info("Cargando datos DEIS%s...", " (snapshot offline)" if offline else "")
    try:
        df = load_deis(
            codes,
            start_year=start_year,
            offline=offline,
            fallback_to_snapshot=fallback,
            cache_dir=cache_dir or _default_cache(),
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
            )
        except NoDataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue
        paths = write_outputs(result, out)
        print()
        print(summary_text(result))
        print()
        print(f"Archivos en {output_dir(out, result)}/")
        for p in paths:
            print(f"  {p.name}")
    return 1 if failures == len(codes) else 0


def _search(text: str, year: int, cache_dir: Path | None = None) -> int:
    from urgencias_core.data.deis import list_facilities

    log.info("Leyendo establecimientos DEIS %s (la primera vez descarga el archivo)...", year)
    try:
        fac = list_facilities(year, cache_dir=cache_dir or _default_cache())
    except RuntimeError as exc:
        print(f"error: {exc}. Prueba con --anio {year - 1}.", file=sys.stderr)
        return 1
    if text:
        mask = fac["facility_name"].str.contains(text, case=False, na=False, regex=False) | fac[
            "facility_code"
        ].str.contains(text, case=False, na=False, regex=False)
        fac = fac[mask]
    if fac.empty:
        print(f"Sin coincidencias para {text!r} en DEIS {year}.")
        return 1
    from tabulate import tabulate

    print(tabulate(fac.values.tolist(), headers=["Código", "Establecimiento"], tablefmt="psql"))
    print(f"{len(fac)} establecimiento(s). Siguiente paso: urg-forecast pronosticar <código>")
    return 0


def _list_models() -> int:
    from tabulate import tabulate

    from urgencias_core.pipeline import MODEL_INFO, default_models, extra_models

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
        from urgencias_core.pipeline import DEMO_FACILITIES

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
        )
    if args.command == "modelos":
        return _list_models()
    if args.command == "buscar":
        return _search(args.texto, args.anio, cache_dir=args.cache)
    return _forecast(
        args.codigos,
        args.horizonte,
        args.salida,
        args.desde,
        args.offline,
        cache_dir=args.cache,
        model_names=args.modelo,
        calibrate=not args.sin_calibrar,
    )


def entrypoint() -> None:
    try:
        sys.exit(main())
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stderr.close()
        sys.exit(0)


if __name__ == "__main__":
    entrypoint()
