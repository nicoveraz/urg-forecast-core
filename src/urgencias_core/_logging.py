"""Console logging setup shared by the command-line entry points.

Library modules log via ``logging.getLogger(__name__)``. ``setup_logging``
sends progress messages to stderr with a print-like format, so the CLI's
stdout carries only the report.
"""

from __future__ import annotations

import logging

_PACKAGE_LOGGER = "urgencias_core"
_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Attach a clean console handler to the ``urgencias_core`` logger.

    Idempotent: safe to call from every entry point. Returns the package
    logger for convenience.
    """
    global _configured
    logger = logging.getLogger(_PACKAGE_LOGGER)
    logger.setLevel(level)
    if not _configured:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _configured = True
    return logger
