"""Deprecated: the baseline models moved to :mod:`urgencias_core.models.baselines`."""

from urgencias_core._compat import moved

__getattr__ = moved(
    "urgencias_core.eval.baselines",
    {
        n: "urgencias_core.models.baselines"
        for n in (
            "SeasonalNaiveBaseline",
            "StatsForecastWrapper",
            "auto_arima",
            "auto_ets",
            "auto_theta",
            "mstl",
        )
    },
)
