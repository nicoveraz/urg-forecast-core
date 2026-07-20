"""Runnable demos exposed as console entry points.

- ``urgencias-demo-synthetic`` → :func:`urgencias_core.demos.synthetic.main`
- ``urgencias-demo-deis``      → :func:`urgencias_core.demos.deis.main`
- ``urgencias-server``         → :func:`urgencias_core.demos.server.main`

All three require optional extras (``viz``/``models``/``server``/``fetch``);
running one without its extra raises an actionable error naming the extra.
"""
