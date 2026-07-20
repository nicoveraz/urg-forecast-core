"""Thin shim: run the DEIS demo from a source checkout.

The implementation lives in :mod:`urgencias_core.demos.deis` so it is also
reachable as the ``urgencias-demo-deis`` console script after install.

    uv run python scripts/demo_deis.py --offline
"""

from urgencias_core.demos.deis import main

if __name__ == "__main__":
    main()
