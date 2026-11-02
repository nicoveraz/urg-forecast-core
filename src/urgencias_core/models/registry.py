"""The built-in models by name: what ``-m NAME`` and ``urg-forecast modelos`` see.

- :func:`default_models`: the models backtested by default; :data:`DEFAULT_MODEL` is the
  one used to forecast.
- :func:`extra_models`: opt-in models for experimenting.
- :data:`MODEL_INFO`: one-line descriptions (Spanish, shown to users).
- :func:`resolve_models`: names (case- and accent-insensitive) or ``"module:Class"``.

To add a built-in model, write its class in ``models/`` and register a factory in
:func:`extra_models` with a line in :data:`MODEL_INFO`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from functools import partial

from urgencias_core.data.series import SEASON_WEEKS
from urgencias_core.models.baselines import SeasonalNaiveBaseline, StatsForecastWrapper, auto_arima
from urgencias_core.models.ensemble import MedianEnsemble
from urgencias_core.models.exogenous import HarmonicExogenous, HarmonicFluNet
from urgencias_core.models.harmonic import HarmonicRegression
from urgencias_core.models.protocol import Forecaster
from urgencias_core.regressors import calendar

# AutoARIMA with a 52-week season is slow with the full search (~20 s per fit).
# The approximate, bounded search below runs in ~1 s; on live DEIS data for seven
# hospitals its quantile loss was within 3% of the full search.
FAST_ARIMA = dict(approximation=True, max_p=2, max_q=2, max_P=1, max_Q=1)

# The model used to forecast unless a criterion asks to choose one (run_forecast). On live
# DEIS data for 40 hospitals it beat choosing a model per establishment (docs/modelos.md).
DEFAULT_MODEL = "Ensamble"
ENSEMBLE_MEMBERS = ("AutoARIMA", "Armónico", "MSTL")


def _mstl() -> Forecaster:
    from statsforecast.models import MSTL, AutoETS

    model = MSTL(season_length=[SEASON_WEEKS], trend_forecaster=AutoETS(model="ZZN"))
    return StatsForecastWrapper(model, name="MSTL")


def default_models() -> dict[str, Callable[[], Forecaster]]:
    """Factories for the models backtested by default (fresh instance per fit).

    ``Ensamble`` (:data:`DEFAULT_MODEL`), the median of AutoARIMA, Armónico and MSTL, is
    the one used to forecast. The other four are backtested next to it for reference:
    SeasonalNaive is the simple benchmark, and a criterion (``select_by``) can choose any
    of them instead. The ensemble is built from the same factories, so the backtest
    combines their predictions instead of fitting them twice.
    """
    single: dict[str, Callable[[], Forecaster]] = {
        "SeasonalNaive": SeasonalNaiveBaseline,
        "AutoARIMA": lambda: auto_arima(season_length=SEASON_WEEKS, **FAST_ARIMA),
        "Armónico": HarmonicRegression,
        "MSTL": _mstl,
    }
    members = {k: single[k] for k in ENSEMBLE_MEMBERS}
    return single | {DEFAULT_MODEL: partial(MedianEnsemble, members)}


def _tbats() -> Forecaster:
    from statsforecast.models import AutoTBATS

    return StatsForecastWrapper(AutoTBATS(season_length=[SEASON_WEEKS]), name="TBATS")


def _theta() -> Forecaster:
    from statsforecast.models import AutoTheta

    return StatsForecastWrapper(AutoTheta(season_length=SEASON_WEEKS), name="Theta")


# ArmónicoFluNetProy: the positivity is projected instead of filled with climatology, so
# a shorter lag can be used (see models.exogenous).
FLUNET_PROY = {"future": "forecast", "lag_weeks": 1}


def extra_models() -> dict[str, Callable[[], Forecaster]]:
    """Opt-in models for experimenting (``-m NAME``); not compared by default."""
    return {
        "TBATS": _tbats,
        "Theta": _theta,
        "ArmónicoFeriados": lambda: HarmonicExogenous.from_regressor(calendar(), ["holidays"]),
        "ArmónicoCalendario": lambda: HarmonicExogenous.from_regressor(calendar()),
        "ArmónicoFluNet": HarmonicFluNet,
        "ArmónicoFluNetProy": lambda: HarmonicFluNet(**FLUNET_PROY),
    }


# One-line descriptions shown by ``urg-forecast modelos``.
MODEL_INFO = {
    "Ensamble": "mediana, cuantil a cuantil, de AutoARIMA, Armónico y MSTL",
    "SeasonalNaive": "referencia: misma semana de años anteriores (cuantiles empíricos)",
    "AutoARIMA": "ARIMA estacional (52 semanas) con búsqueda acotada",
    "Armónico": "tendencia + ciclo anual con términos de Fourier, ARIMA en los residuos",
    "MSTL": "descomposición estacional + tendencia ETS",
    "TBATS": "estacionalidad trigonométrica con Box-Cox y errores ARMA; lento (~15 s)",
    "Theta": "solo tendencia (no detecta el ciclo anual); sirve de contraste",
    "ArmónicoFeriados": "Armónico + feriados chilenos en día hábil de cada semana",
    "ArmónicoCalendario": (
        "Armónico + feriados, interferiados y vacaciones escolares (calendario chileno)"
    ),
    "ArmónicoFluNet": (
        "Armónico + positividad nacional de influenza y VRS (OMS FluNet); "
        "ejemplo de regresor externo"
    ),
    "ArmónicoFluNetProy": (
        "como ArmónicoFluNet, pero proyecta la positividad en vez de usar su promedio "
        "histórico; rezago de 1 semana"
    ),
}


def available_models() -> dict[str, Callable[[], Forecaster]]:
    """All built-in models: the default battery plus the opt-in extras."""
    return default_models() | extra_models()


def _fold(name: str) -> str:
    """Case- and accent-insensitive key, so 'armonico' matches 'Armónico'."""
    import unicodedata

    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def resolve_models(names: list[str] | None) -> dict[str, Callable[[], Forecaster]]:
    """Model factories for ``names``: built-in names or ``"module.path:Class"``.

    ``None`` or an empty list returns :func:`default_models`. A custom class is
    imported from the given module and must be constructible without arguments
    and satisfy the :class:`~urgencias_core.models.protocol.Forecaster`
    protocol. Raises ``ValueError`` for unknown names or bad imports.
    """
    if not names:
        return default_models()
    builtin = available_models()
    lookup = {_fold(k): k for k in builtin}
    out: dict[str, Callable[[], Forecaster]] = {}
    for name in names:
        if ":" in name:
            module_name, _, attr = name.partition(":")
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, attr)
            except (ImportError, AttributeError) as exc:
                raise ValueError(f"no se pudo importar el modelo {name!r}: {exc}") from exc
            if not (hasattr(cls, "fit") and hasattr(cls, "predict")):
                raise ValueError(f"{name!r} no tiene métodos fit y predict")
            out[attr] = cls
        elif _fold(name) in lookup:
            key = lookup[_fold(name)]
            out[key] = builtin[key]
        else:
            raise ValueError(
                f"modelo desconocido: {name!r}. Opciones: {', '.join(builtin)} "
                "o 'modulo:Clase' para un modelo propio ('urg-forecast modelos' los describe)."
            )
    return out


__all__ = [
    "DEFAULT_MODEL",
    "ENSEMBLE_MEMBERS",
    "FAST_ARIMA",
    "FLUNET_PROY",
    "MODEL_INFO",
    "available_models",
    "default_models",
    "extra_models",
    "resolve_models",
]
