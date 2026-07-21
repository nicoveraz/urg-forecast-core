"""Feature builders.

The Open-Meteo weather client lives in :mod:`urgencias_core.features.weather`
and needs the ``fetch`` extra, so it is not re-exported here.
"""

from urgencias_core.features.calendar import CalendarConfig, calendar_features

__all__ = ["calendar_features", "CalendarConfig"]
