"""``urg-forecast``: weekly ED attendance forecast from public DEIS MINSAL data.

Subcommands::

    urg-forecast demo                          # two demo hospitals, offline snapshot
    urg-forecast buscar "puerto montt"         # find an establishment's DEIS code
    urg-forecast pronosticar 24-105 -H 6m      # backtest + forecast, any establishment

Prints a summary with ASCII tables and writes CSVs + PNGs to ``--salida``.
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

from urgencias_core._logging import setup_logging

log = logging.getLogger(__name__)

DEFAULT_HORIZON = "26"
DEFAULT_OUT = Path("urg-forecast-salida")

EPILOG = """\
ejemplos:
  urg-forecast demo
  urg-forecast buscar "osorno"
  urg-forecast pronosticar 24-105
  urg-forecast pronosticar 24-105 --horizonte 12
  urg-forecast pronosticar 24-105 24-115 --horizonte 6m --salida resultados/

Horizonte: semanas (12 o 12s) o meses (6m). El backtest usa las últimas
semanas, tantas como el horizonte (máximo 26), para estimar el error.

Es una base para construir encima, no un pronóstico operacional validado.
"""


def _horizon_type(text: str) -> int:
    from urgencias_core.pipeline import parse_horizon

    try:
        return parse_horizon(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urg-forecast",
        description=(
            "Pronóstico semanal de atenciones de urgencia con datos públicos del DEIS MINSAL."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="muestra la versión y sale")
    sub = parser.add_subparsers(dest="command", metavar="COMANDO")

    def add_forecast_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-H",
            "--horizonte",
            type=_horizon_type,
            default=_horizon_type(DEFAULT_HORIZON),
            metavar="N",
            help="semanas a pronosticar: 12, 12s o 6m (por defecto: 26 semanas)",
        )
        p.add_argument(
            "-o",
            "--salida",
            type=Path,
            default=DEFAULT_OUT,
            metavar="CARPETA",
            help=f"carpeta para CSV y figuras (por defecto: ./{DEFAULT_OUT})",
        )

    p_demo = sub.add_parser(
        "demo",
        help="pronóstico de ejemplo para dos hospitales de Los Lagos",
        description="Pronóstico de los hospitales de Puerto Montt y Frutillar. Descarga los "
        "datos DEIS más recientes y, si no hay conexión, usa el snapshot incluido.",
    )
    add_forecast_options(p_demo)
    p_demo.add_argument(
        "--offline", action="store_true", help="usa directamente el snapshot incluido"
    )

    p_search = sub.add_parser(
        "buscar",
        help="busca el código DEIS de un establecimiento",
        description="Lista establecimientos del DEIS filtrando por nombre o código. "
        "La primera vez descarga el archivo anual (cientos de MB) y lo guarda en caché.",
    )
    p_search.add_argument("texto", nargs="?", default="", help="parte del nombre o código")
    p_search.add_argument(
        "--anio",
        type=int,
        default=datetime.now().year,
        help="año del archivo DEIS donde buscar (por defecto: el actual)",
    )

    p_fc = sub.add_parser(
        "pronosticar",
        help="backtest y pronóstico para uno o más establecimientos",
        description="Descarga los datos DEIS de los establecimientos indicados, compara "
        "tres modelos en un backtest y pronostica con el mejor.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_fc.add_argument(
        "codigos",
        nargs="+",
        metavar="CODIGO",
        help="código DEIS del establecimiento, p. ej. 24-105 o 124105",
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
        help="usa el snapshot incluido (solo hospitales de demostración)",
    )
    return parser


def _forecast(
    codes: list[str],
    horizon: int,
    out: Path,
    start_year: int,
    offline: bool,
    fallback: bool = False,
) -> int:
    from urgencias_core.pipeline import (
        NoDataError,
        facility_name,
        load_deis,
        run_forecast,
        weekly_series,
    )
    from urgencias_core.report import output_dir, summary_text, write_outputs

    log.info("Cargando datos DEIS%s...", " (snapshot offline)" if offline else "")
    try:
        df = load_deis(codes, start_year=start_year, offline=offline, fallback_to_snapshot=fallback)
    except NoDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for code in codes:
        name = facility_name(df, code)
        log.info("Modelando %s (%s)...", name, code)
        try:
            result = run_forecast(
                weekly_series(df, code), horizon, code=code, name=name, source=df.attrs["source"]
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


def _search(text: str, year: int) -> int:
    from urgencias_core.data.deis import list_facilities

    log.info("Leyendo establecimientos DEIS %s (la primera vez descarga el archivo)...", year)
    try:
        fac = list_facilities(year)
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


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    # statsforecast's optimizer warnings mean nothing to a CLI user; the backtest
    # table is the honest measure of whether a model works.
    warnings.filterwarnings("ignore", module=r"statsforecast\..*")
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from urgencias_core import __version__

        print(f"urg-forecast {__version__}")
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "demo":
        from urgencias_core.pipeline import DEMO_FACILITIES

        return _forecast(
            list(DEMO_FACILITIES), args.horizonte, args.salida, 2022, args.offline, fallback=True
        )
    if args.command == "buscar":
        return _search(args.texto, args.anio)
    return _forecast(args.codigos, args.horizonte, args.salida, args.desde, args.offline)


def entrypoint() -> None:
    try:
        sys.exit(main())
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stderr.close()
        sys.exit(0)


if __name__ == "__main__":
    entrypoint()
