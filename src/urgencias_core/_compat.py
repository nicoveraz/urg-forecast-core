"""Aliases for names that moved in 0.4, so old imports keep working for one version."""

from __future__ import annotations

import importlib
import warnings
from collections.abc import Callable

REMOVED_IN = "0.5"


def moved(old_module: str, targets: dict[str, str]) -> Callable[[str], object]:
    """A module ``__getattr__`` that forwards ``targets`` (name -> new module) with a warning."""

    def __getattr__(name: str) -> object:
        if name not in targets:
            raise AttributeError(f"module {old_module!r} has no attribute {name!r}")
        new = targets[name]
        warnings.warn(
            f"{old_module}.{name} moved to {new}.{name}; the old path will be removed in "
            f"{REMOVED_IN}",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(importlib.import_module(new), name)

    return __getattr__
