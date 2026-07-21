"""Smoke tests for the three console demos — the headline user-facing commands
must run end to end, fully offline. These exercise the ``run()`` orchestration
and ``main()`` argparse wiring that the unit tests don't reach."""

from __future__ import annotations

import pytest

pytest.importorskip("matplotlib")  # every demo renders PNG charts (viz extra)

from urgencias_core.data.fixtures import synthetic_visits_path  # noqa: E402
from urgencias_core.demos import deis as deis_demo  # noqa: E402
from urgencias_core.demos import synthetic as synthetic_demo  # noqa: E402


def test_synthetic_run_writes_the_three_charts(tmp_path):
    synthetic_demo.run(fixture=synthetic_visits_path(), outputs=tmp_path)
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        "demo_synthetic_forecast.png",
        "demo_synthetic_occupancy.png",
        "demo_synthetic_simulation.png",
    ]


def test_synthetic_main_defaults_to_packaged_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["urgencias-demo-synthetic", "--out", str(tmp_path)])
    synthetic_demo.main()
    assert any(tmp_path.glob("*.png"))


def test_deis_run_offline_writes_reports(tmp_path):
    pytest.importorskip("statsforecast")  # the baseline comparison fits models
    deis_demo.run(outputs=tmp_path, offline=True)
    assert (tmp_path / "deis_baseline_comparison.md").exists()
    assert any(tmp_path.glob("deis_holdout_*.png"))


def test_deis_main_wires_argparse_to_run(tmp_path, monkeypatch):
    # main() just parses args and delegates to run(); mock run() so this stays
    # fast (the real end-to-end path is covered by the test above).
    calls: dict = {}
    monkeypatch.setattr(deis_demo, "run", lambda **kw: calls.update(kw))
    monkeypatch.setattr("sys.argv", ["urgencias-demo-deis", "--offline", "--out", str(tmp_path)])
    deis_demo.main()
    assert calls == {"outputs": tmp_path, "offline": True, "start_year": 2022}


def test_server_main_launches_the_app_factory(monkeypatch):
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    from urgencias_core.demos import server as server_demo

    calls: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.update(target=target, kw=kw))
    monkeypatch.setattr("sys.argv", ["urgencias-server"])
    server_demo.main()
    assert calls["target"] == "urgencias_core.server.app:create_app"
    assert calls["kw"].get("factory") is True
