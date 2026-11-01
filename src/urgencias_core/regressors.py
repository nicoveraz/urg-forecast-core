"""External weekly variables (regressors), each with the rules of its source.

A :class:`Regressor` bundles a weekly table (``timestamp`` = the Monday closing each DEIS
week, one numeric column per variable) with what the model needs to use it honestly:

- ``report_delay_weeks``: how many weeks the source takes to publish a week;
- ``known_future``: whether future values are known in advance (a calendar) or not
  (a surveillance series).

:meth:`HarmonicExogenous.from_regressor
<urgencias_core.models.exogenous.HarmonicExogenous.from_regressor>` turns one into a model,
and :func:`~urgencias_core.eval.compare.compare_models` tells whether it helps.

Built in:

- :func:`flunet` — national positivity of influenza and RSV (WHO FluNet), 2 weeks of delay.
- :func:`calendar` — Chilean holidays, bridge days, school holidays and regional events,
  known in advance.

To add your own, write a function that returns a ``Regressor`` (see ``docs/arquitectura.md``)::

    temperatura = Regressor(
        name="temperatura",
        load=lambda: pd.read_csv("temperatura_semanal.csv", parse_dates=["timestamp"]),
        columns=("temp_min",),
        report_delay_weeks=1,
        description="Temperatura mínima semanal, estación Puerto Montt",
    )
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd


@dataclass(frozen=True)
class Regressor:
    """A weekly external variable and the rules of its source."""

    name: str
    load: Callable[[], pd.DataFrame]  # timestamp + columns, in DEIS weeks
    columns: tuple[str, ...]
    report_delay_weeks: int = 0
    known_future: bool = False
    description: str = ""

    def table(self) -> pd.DataFrame:
        """Load the table and check it has ``timestamp`` and the declared columns."""
        df = self.load()
        missing = {"timestamp", *self.columns} - set(df.columns)
        if missing:
            raise ValueError(f"regressor {self.name!r} lacks columns {sorted(missing)}")
        return df


def _flunet_table() -> pd.DataFrame:
    from urgencias_core.data.flunet import load_flunet, weekly_positivity

    return weekly_positivity(load_flunet())


def flunet() -> Regressor:
    """Weekly national positivity (0-1) of influenza (``flu``) and RSV (``rsv``), WHO FluNet."""
    return Regressor(
        name="flunet",
        load=_flunet_table,
        columns=("flu", "rsv"),
        report_delay_weeks=2,
        description="Positividad nacional de influenza y VRS (OMS FluNet, reportada por el ISP)",
    )


@lru_cache(maxsize=1)
def _calendar_table(start: str, end: str) -> pd.DataFrame:
    from urgencias_core.features.calendar import weekly_calendar

    return weekly_calendar(start, end)


def calendar(start: str = "2008-01-01", years_ahead: int = 3) -> Regressor:
    """Chilean calendar per DEIS week: ``holidays`` (on weekdays), ``bridge_days``,
    ``school_holiday`` (share of the week) and ``semana_musical_frutillar``.

    Known in advance, so it also covers the forecast weeks (``years_ahead`` past today).
    For other regional events or exact school dates, build the table with
    :func:`~urgencias_core.features.calendar.weekly_calendar` and your own ``CalendarConfig``.
    """
    end = f"{pd.Timestamp.today().year + years_ahead}-12-31"
    return Regressor(
        name="calendario",
        load=lambda: _calendar_table(start, end).copy(),
        columns=("holidays", "bridge_days", "school_holiday"),
        known_future=True,
        description="Feriados en día hábil, interferiados y vacaciones escolares (Chile)",
    )


def available_regressors() -> dict[str, Callable[[], Regressor]]:
    """The built-in regressors by name."""
    return {"flunet": flunet, "calendario": calendar}


__all__ = ["Regressor", "available_regressors", "calendar", "flunet"]
