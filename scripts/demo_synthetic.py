"""Thin shim: run the synthetic demo from a source checkout.

The implementation lives in :mod:`urgencias_core.demos.synthetic` so it is also
reachable as the ``urgencias-demo-synthetic`` console script after install.

    uv run python scripts/demo_synthetic.py
"""

from urgencias_core.demos.synthetic import main

if __name__ == "__main__":
    main()
