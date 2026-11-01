"""How good is a forecast: rolling backtest, metrics, calibration and paired comparison."""

from urgencias_core._compat import moved
from urgencias_core.eval.backtest import MIN_TRAIN_WEEKS, Backtest, Window, backtest, window_cuts
from urgencias_core.eval.calibration import apply_calibration, calibration_factors
from urgencias_core.eval.compare import Comparison, compare_many, compare_models, sign_test
from urgencias_core.eval.harness import HarnessReport, run_harness
from urgencias_core.eval.metrics import QUANTILES, quantile_loss, score

__getattr__ = moved(
    "urgencias_core.eval",
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

__all__ = [
    "MIN_TRAIN_WEEKS",
    "QUANTILES",
    "Backtest",
    "Comparison",
    "HarnessReport",
    "Window",
    "apply_calibration",
    "backtest",
    "calibration_factors",
    "compare_many",
    "compare_models",
    "quantile_loss",
    "run_harness",
    "score",
    "sign_test",
    "window_cuts",
]
