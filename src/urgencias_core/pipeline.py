"""Deprecated: the contents of this module moved in 0.4 and it will be removed in 0.5.

- data loading and weekly series: :mod:`urgencias_core.data.series`
- the model registry: :mod:`urgencias_core.models.registry`
- backtest, selection and forecast: :mod:`urgencias_core.forecast`
- interval calibration: :mod:`urgencias_core.eval.calibration`

The common entry points are also importable from ``urgencias_core`` directly.
"""

from urgencias_core._compat import moved

__getattr__ = moved(
    "urgencias_core.pipeline",
    {
        "COVID_EXCLUDE_YEARS": "urgencias_core.data.series",
        "TOTAL_CAUSE_GLOSA": "urgencias_core.data.series",
        "DEMO_FACILITIES": "urgencias_core.data.series",
        "SEASON_WEEKS": "urgencias_core.data.series",
        "GRAIN": "urgencias_core.data.series",
        "NoDataError": "urgencias_core.data.series",
        "SOURCE_LIVE": "urgencias_core.data.series",
        "SOURCE_MIRROR": "urgencias_core.data.series",
        "SOURCE_SNAPSHOT": "urgencias_core.data.series",
        "load_deis": "urgencias_core.data.series",
        "daily_totals": "urgencias_core.data.series",
        "to_weekly": "urgencias_core.data.series",
        "weekly_series": "urgencias_core.data.series",
        "facility_name": "urgencias_core.data.series",
        "FAST_ARIMA": "urgencias_core.models.registry",
        "FLUNET_PROY": "urgencias_core.models.registry",
        "default_models": "urgencias_core.models.registry",
        "extra_models": "urgencias_core.models.registry",
        "available_models": "urgencias_core.models.registry",
        "MODEL_INFO": "urgencias_core.models.registry",
        "resolve_models": "urgencias_core.models.registry",
        "parse_horizon": "urgencias_core.forecast",
        "ForecastResult": "urgencias_core.forecast",
        "min_weeks_needed": "urgencias_core.forecast",
        "run_forecast": "urgencias_core.forecast",
        "MAX_BACKTEST_WEEKS": "urgencias_core.forecast",
        "BACKTEST_ORIGINS": "urgencias_core.forecast",
        "BACKTEST_STEP": "urgencias_core.forecast",
        "calibration_factors": "urgencias_core.eval.calibration",
        "apply_calibration": "urgencias_core.eval.calibration",
        "QUANTILES": "urgencias_core.eval.metrics",
        "MIN_TRAIN_WEEKS": "urgencias_core.eval.backtest",
    },
)
